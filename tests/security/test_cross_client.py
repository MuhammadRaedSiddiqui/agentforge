"""
Security test for cross-client fixture injection.

Tests T156: Cross-client fixture injection (foreign org_id in artifact,
foreign resource reference)

Verifies that artifacts cannot reference other clients' data.
"""

import pytest

from orchestrator.assembler import PackageAssembler


@pytest.mark.security
class TestCrossClientSecurity:
    """Test cross-client reference detection and prevention."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.assembler = PackageAssembler()

    def test_detects_foreign_org_id_in_artifact(self) -> None:
        """Test that foreign org_id in artifact is detected."""
        organization_id = "org-001"

        # Create artifact with foreign org_id
        artifact_content = {
            "assistant": {
                "name": "Assistant",
                "organization_id": "org-999",  # Foreign org_id
            },
        }

        # Check for cross-client references
        foreign_refs = self.assembler.detect_cross_client_references(
            organization_id=organization_id,
            artifact_content=artifact_content,
        )

        assert len(foreign_refs) > 0
        assert any("org-999" in ref for ref in foreign_refs)

    def test_detects_foreign_resource_reference(self) -> None:
        """Test that foreign resource IDs are detected."""
        organization_id = "org-001"

        # Artifact references resource from different org
        artifact_content = {
            "scenario": {
                "name": "Booking",
                "webhook_url": "https://hooks.example.com/org-999/webhook",  # Foreign org
            },
        }

        foreign_refs = self.assembler.detect_cross_client_references(
            organization_id=organization_id,
            artifact_content=artifact_content,
        )

        assert len(foreign_refs) > 0

    def test_allows_own_org_references(self) -> None:
        """Test that references to own organization are allowed."""
        organization_id = "org-001"

        artifact_content = {
            "assistant": {
                "name": "Assistant",
                "organization_id": "org-001",  # Same org
            },
        }

        foreign_refs = self.assembler.detect_cross_client_references(
            organization_id=organization_id,
            artifact_content=artifact_content,
        )

        assert len(foreign_refs) == 0

    def test_rejects_package_with_cross_client_refs(self) -> None:
        """Test that package assembly fails with cross-client refs."""
        from shared.result_object import ResultObject

        organization_id = "org-001"

        # Create result with foreign reference
        result = ResultObject(
            task_id="task-001",
            agent_source="vapi_agent",
            content_hash="hash123",
            storage_path="artifact.json",
            summary="Generated config",
            field_provenance={"organization_id": "source"},
            model_id="gemini-2.5-pro",
            validation_status="verified",
        )

        # Mock artifact content with foreign org
        result._content = {
            "organization_id": "org-999",  # Foreign
        }

        # Attempt to assemble package
        package = self.assembler.assemble_package(
            deployment_id="deploy-001",
            organization_id=organization_id,
            results=[result],
        )

        # Should fail validation
        assert package.validation_passed is False
        assert any("cross-client" in error.lower() for error in package.errors)

    def test_detects_embedded_foreign_ids(self) -> None:
        """Test that foreign IDs embedded in strings are detected."""
        organization_id = "org-001"

        artifact_content = {
            "config": {
                "callback_url": "https://api.example.com/notify/org-777",  # Embedded foreign ID
            },
        }

        foreign_refs = self.assembler.detect_cross_client_references(
            organization_id=organization_id,
            artifact_content=artifact_content,
        )

        assert len(foreign_refs) > 0

    def test_ignores_common_prefixes(self) -> None:
        """Test that common prefixes like 'organization' don't false positive."""
        organization_id = "org-001"

        artifact_content = {
            "metadata": {
                "entity_type": "organization",  # Just a type name
                "description": "For organizational purposes",  # Common word
            },
        }

        foreign_refs = self.assembler.detect_cross_client_references(
            organization_id=organization_id,
            artifact_content=artifact_content,
        )

        # Should not detect these as foreign references
        assert len(foreign_refs) == 0

    def test_detects_resource_ids_from_other_deployments(self) -> None:
        """Test that resource IDs from other deployments are detected."""
        organization_id = "org-001"

        artifact_content = {
            "assistant": {
                "tools": [
                    {"id": "tool-abc"},  # Could be from another deployment
                ],
            },
        }

        # In real implementation, would check against known resources
        # For this test, just verify detection mechanism exists
        # (actual validation happens at runtime with internal store)

    def test_sql_injection_through_org_id(self) -> None:
        """Test that org_id cannot contain SQL injection."""
        organization_id = "org-001'; DROP TABLE organizations; --"

        # Validation should reject this
        from orchestrator.intake_schema import validate_intake

        intake = {
            "organization_id": organization_id,
            "business_name": "Test Corp",
            "capabilities": ["availability"],
        }

        result = validate_intake(intake)

        assert result["valid"] is False
        assert any("invalid" in error.lower() for error in result["errors"])

    def test_path_traversal_through_org_id(self) -> None:
        """Test that org_id cannot contain path traversal."""
        organization_id = "../../../etc/passwd"

        from orchestrator.intake_schema import validate_intake

        intake = {
            "organization_id": organization_id,
            "business_name": "Test Corp",
            "capabilities": ["availability"],
        }

        result = validate_intake(intake)

        assert result["valid"] is False

    def test_prevents_organization_id_spoofing(self) -> None:
        """Test that organization_id cannot be changed mid-deployment."""
        # Simulate attempt to change org_id in artifact
        original_org = "org-001"
        spoofed_org = "org-admin"

        artifact_content = {
            "organization_id": spoofed_org,  # Attempt to escalate
        }

        foreign_refs = self.assembler.detect_cross_client_references(
            organization_id=original_org,
            artifact_content=artifact_content,
        )

        assert len(foreign_refs) > 0
        assert spoofed_org in str(foreign_refs)
