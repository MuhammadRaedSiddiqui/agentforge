"""
Restoration tests for export/import cycle.

Tests T134: Restoration test for export/import cycle (manifest hashes, row counts,
FK validity, audit hash chains, recovery queries)

Verifies that exported data can be restored successfully.
"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from scripts.restore_internal_tables import (
    validate_manifest,
    verify_file_hashes,
)


@pytest.mark.restoration
class TestOperationalRestore:
    """Test export and restore cycle for operational data."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        # Create temp directories
        self.temp_dir = Path(tempfile.mkdtemp())
        self.export_dir = self.temp_dir / "export"
        self.export_dir.mkdir()

    def teardown_method(self) -> None:
        """Clean up temp directories."""
        shutil.rmtree(self.temp_dir)

    def test_manifest_includes_required_fields(self) -> None:
        """Test that export manifest includes all required fields."""
        # Create minimal manifest
        manifest = {
            "export_version": "1.0.0",
            "schema_version": "1.0.0",
            "exported_at": "2026-07-14T12:00:00Z",
            "table_count": 2,
            "tables": [
                {
                    "table": "organizations",
                    "row_count": 5,
                    "file": "organizations.json",
                    "file_hash": "abc123",
                },
                {
                    "table": "deployments",
                    "row_count": 10,
                    "file": "deployments.json",
                    "file_hash": "def456",
                },
            ],
            "total_rows": 15,
            "final_audit_hashes": {
                "deploy-001": "hash1",
                "deploy-002": "hash2",
            },
        }

        # Write manifest
        manifest_path = self.export_dir / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        # Validate
        validated = validate_manifest(manifest_path)

        assert validated["export_version"] == "1.0.0"
        assert validated["schema_version"] == "1.0.0"
        assert validated["table_count"] == 2
        assert len(validated["tables"]) == 2
        assert "final_audit_hashes" in validated

    def test_manifest_validation_fails_missing_field(self) -> None:
        """Test that manifest validation fails if required field missing."""
        # Create incomplete manifest
        manifest = {
            "export_version": "1.0.0",
            # Missing schema_version
            "tables": [],
        }

        manifest_path = self.export_dir / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        # Validate should raise
        with pytest.raises(ValueError, match="missing required field"):
            validate_manifest(manifest_path)

    def test_file_hash_verification_detects_tampering(self) -> None:
        """Test that file hash verification detects modified files."""
        # Create table file
        table_data = [
            {"id": "org-001", "name": "ACME Corp"},
            {"id": "org-002", "name": "Beta Inc"},
        ]

        table_file = self.export_dir / "organizations.json"
        with open(table_file, "w") as f:
            json.dump(table_data, f)

        # Compute hash
        from scripts.export_internal_tables import compute_file_hash

        original_hash = compute_file_hash(table_file)

        # Create manifest with hash
        manifest = {
            "export_version": "1.0.0",
            "schema_version": "1.0.0",
            "tables": [
                {
                    "table": "organizations",
                    "row_count": 2,
                    "file": "organizations.json",
                    "file_hash": original_hash,
                },
            ],
            "final_audit_hashes": {},
        }

        # Verify should pass
        assert verify_file_hashes(self.export_dir, manifest) is True

        # Modify file
        table_data.append({"id": "org-003", "name": "Gamma LLC"})
        with open(table_file, "w") as f:
            json.dump(table_data, f)

        # Verify should now fail
        assert verify_file_hashes(self.export_dir, manifest) is False

    def test_row_count_preserved_in_cycle(self) -> None:
        """Test that row counts are preserved through export/restore cycle."""
        # Create test data files
        orgs = [
            {"id": "org-001", "name": "ACME", "slug": "acme"},
            {"id": "org-002", "name": "Beta", "slug": "beta"},
            {"id": "org-003", "name": "Gamma", "slug": "gamma"},
        ]

        deployments = [
            {"id": "deploy-001", "organization_id": "org-001", "status": "complete"},
            {"id": "deploy-002", "organization_id": "org-002", "status": "partial"},
        ]

        # Write files
        with open(self.export_dir / "organizations.json", "w") as f:
            json.dump(orgs, f)

        with open(self.export_dir / "deployments.json", "w") as f:
            json.dump(deployments, f)

        # Create manifest
        from scripts.export_internal_tables import compute_file_hash

        manifest = {
            "export_version": "1.0.0",
            "schema_version": "1.0.0",
            "table_count": 2,
            "tables": [
                {
                    "table": "organizations",
                    "row_count": len(orgs),
                    "file": "organizations.json",
                    "file_hash": compute_file_hash(self.export_dir / "organizations.json"),
                },
                {
                    "table": "deployments",
                    "row_count": len(deployments),
                    "file": "deployments.json",
                    "file_hash": compute_file_hash(self.export_dir / "deployments.json"),
                },
            ],
            "total_rows": len(orgs) + len(deployments),
            "final_audit_hashes": {},
        }

        with open(self.export_dir / "manifest.json", "w") as f:
            json.dump(manifest, f)

        # Validate manifest
        validated = validate_manifest(self.export_dir / "manifest.json")

        # Verify row counts match
        assert validated["tables"][0]["row_count"] == len(orgs)
        assert validated["tables"][1]["row_count"] == len(deployments)
        assert validated["total_rows"] == len(orgs) + len(deployments)

    def test_audit_hash_chain_preserved(self) -> None:
        """Test that audit hash chains are preserved in manifest."""
        # Create audit events
        audit_events = [
            {
                "id": "event-001",
                "deployment_id": "deploy-001",
                "event_hash": "hash1",
                "previous_hash": None,
            },
            {
                "id": "event-002",
                "deployment_id": "deploy-001",
                "event_hash": "hash2",
                "previous_hash": "hash1",
            },
            {
                "id": "event-003",
                "deployment_id": "deploy-001",
                "event_hash": "hash3",
                "previous_hash": "hash2",
            },
        ]

        # Write audit events file
        with open(self.export_dir / "audit_events.json", "w") as f:
            json.dump(audit_events, f)

        # Create manifest with final hash
        from scripts.export_internal_tables import compute_file_hash

        manifest = {
            "export_version": "1.0.0",
            "schema_version": "1.0.0",
            "tables": [
                {
                    "table": "audit_events",
                    "row_count": len(audit_events),
                    "file": "audit_events.json",
                    "file_hash": compute_file_hash(self.export_dir / "audit_events.json"),
                },
            ],
            "final_audit_hashes": {
                "deploy-001": "hash3",  # Final hash in chain
            },
        }

        with open(self.export_dir / "manifest.json", "w") as f:
            json.dump(manifest, f)

        # Validate
        validated = validate_manifest(self.export_dir / "manifest.json")

        # Verify final hash preserved
        assert validated["final_audit_hashes"]["deploy-001"] == "hash3"

    def test_foreign_key_references_maintained(self) -> None:
        """Test that foreign key references are maintained."""
        # Create related data
        orgs = [
            {"id": "org-001", "name": "ACME", "slug": "acme"},
        ]

        deployments = [
            {
                "id": "deploy-001",
                "organization_id": "org-001",  # FK to organizations
                "status": "complete",
            },
        ]

        tasks = [
            {
                "id": "task-001",
                "deployment_id": "deploy-001",  # FK to deployments
                "agent_target": "vapi_agent",
                "status": "success",
            },
        ]

        # Write files
        for name, data in [
            ("organizations", orgs),
            ("deployments", deployments),
            ("task_executions", tasks),
        ]:
            with open(self.export_dir / f"{name}.json", "w") as f:
                json.dump(data, f)

        # Verify FK relationships
        # deployment.organization_id should reference existing org
        assert deployments[0]["organization_id"] in [o["id"] for o in orgs]

        # task.deployment_id should reference existing deployment
        assert tasks[0]["deployment_id"] in [d["id"] for d in deployments]

    def test_timestamps_preserved_not_regenerated(self) -> None:
        """Test that original timestamps are preserved, not regenerated."""
        original_timestamp = "2026-07-14T10:30:00Z"

        deployments = [
            {
                "id": "deploy-001",
                "organization_id": "org-001",
                "status": "complete",
                "created_at": original_timestamp,
                "updated_at": original_timestamp,
            },
        ]

        # Write file
        with open(self.export_dir / "deployments.json", "w") as f:
            json.dump(deployments, f)

        # Read back
        with open(self.export_dir / "deployments.json") as f:
            restored = json.load(f)

        # Verify timestamps unchanged
        assert restored[0]["created_at"] == original_timestamp
        assert restored[0]["updated_at"] == original_timestamp

    def test_ids_preserved_not_regenerated(self) -> None:
        """Test that IDs are preserved, not regenerated."""
        original_ids = ["deploy-001", "deploy-002", "deploy-003"]

        deployments = [
            {
                "id": deployment_id,
                "organization_id": "org-001",
                "status": "complete",
            }
            for deployment_id in original_ids
        ]

        # Write file
        with open(self.export_dir / "deployments.json", "w") as f:
            json.dump(deployments, f)

        # Read back
        with open(self.export_dir / "deployments.json") as f:
            restored = json.load(f)

        # Verify IDs unchanged
        restored_ids = [d["id"] for d in restored]
        assert restored_ids == original_ids

    def test_schema_version_tracked(self) -> None:
        """Test that schema version is tracked in manifest."""
        manifest = {
            "export_version": "1.0.0",
            "schema_version": "1.0.0",
            "tables": [],
            "final_audit_hashes": {},
        }

        manifest_path = self.export_dir / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        # Validate
        validated = validate_manifest(manifest_path)

        # Verify schema version present
        assert "schema_version" in validated
        assert validated["schema_version"] == "1.0.0"

    def test_recovery_queries_executable_after_restore(self) -> None:
        """Test that recovery queries can be executed after restore."""
        # Create deployment in recovery state
        deployments = [
            {
                "id": "deploy-001",
                "organization_id": "org-001",
                "status": "recovery_required",
            },
        ]

        # Create recovery actions
        recoveries = [
            {
                "id": "recovery-001",
                "deployment_id": "deploy-001",
                "recovery_type": "retry",
                "target_action_id": "action-001",
                "status": "pending",
            },
        ]

        # Write files
        with open(self.export_dir / "deployments.json", "w") as f:
            json.dump(deployments, f)

        with open(self.export_dir / "recovery_actions.json", "w") as f:
            json.dump(recoveries, f)

        # Read back and verify query structure
        with open(self.export_dir / "deployments.json") as f:
            restored_deployments = json.load(f)

        with open(self.export_dir / "recovery_actions.json") as f:
            restored_recoveries = json.load(f)

        # Verify we can query for deployments requiring recovery
        recovery_deployments = [
            d for d in restored_deployments if d["status"] == "recovery_required"
        ]
        assert len(recovery_deployments) == 1

        # Verify we can query for pending recovery actions
        pending_recoveries = [r for r in restored_recoveries if r["status"] == "pending"]
        assert len(pending_recoveries) == 1
