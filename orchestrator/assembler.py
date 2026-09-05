"""
Package assembler for Agent Forge.

Assembles validated artifacts into a complete deployment package with:
- Cross-client reference detection
- Field provenance tracking
- Package manifest generation
- Repeated correction escalation
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared.hashing import hash_content
from shared.result_object import ResultObject
from shared.task_object import TaskObject


@dataclass
class DeploymentPackage:
    """Complete deployment package."""

    deployment_id: str
    organization_id: str
    is_complete: bool
    validation_passed: bool
    artifacts: list[ResultObject]
    manifest: dict[str, Any]
    errors: list[str]


class PackageAssembler:
    """
    Assembles and validates complete deployment packages.

    Responsibilities:
    - Collect all task results
    - Verify agent_source matches task target
    - Check validation status
    - Detect cross-client references
    - Track field provenance
    - Generate package manifest
    - Enforce correction limits
    """

    def __init__(self) -> None:
        """Initialize the assembler."""
        self.max_corrections_per_field = 2  # Third attempt = failure

    def assemble(self, tasks: list[TaskObject], results: list[ResultObject]) -> DeploymentPackage:
        """
        Assemble deployment package from task results.

        Args:
            tasks: List of generation tasks
            results: List of task results

        Returns:
            Complete deployment package with validation status
        """
        errors = []

        if not tasks:
            return DeploymentPackage(
                deployment_id="",
                organization_id="",
                is_complete=True,
                validation_passed=True,
                artifacts=[],
                manifest={},
                errors=[],
            )

        deployment_id = tasks[0].deployment_id
        organization_id = self._extract_org_id_from_tasks(tasks)

        # Check completeness: one result per task
        completeness_errors = self._check_completeness(tasks, results)
        errors.extend(completeness_errors)

        # Verify provenance: agent_source must match task target
        provenance_errors = self._verify_provenance(tasks, results)
        errors.extend(provenance_errors)

        # Check validation status
        validation_errors = self._check_validation_status(results)
        errors.extend(validation_errors)

        # Detect cross-client references
        cross_client_errors = self._detect_cross_client_references(results, organization_id)
        errors.extend(cross_client_errors)

        # Check for duplicate results
        duplicate_errors = self._check_duplicates(results)
        errors.extend(duplicate_errors)

        # Generate manifest
        manifest = self._generate_manifest(deployment_id, organization_id, results)

        package = DeploymentPackage(
            deployment_id=deployment_id,
            organization_id=organization_id,
            is_complete=len(errors) == 0,  # Package is complete only if no errors
            validation_passed=len(validation_errors) == 0,
            artifacts=results,
            manifest=manifest,
            errors=errors,
        )

        return package

    def assemble_package(
        self,
        deployment_id: str,
        organization_id: str,
        results: list[ResultObject],
    ) -> DeploymentPackage:
        """
        Backward-compatible wrapper for callers that assemble from results only.
        """
        synthetic_tasks = [
            TaskObject(
                task_id=result.task_id,
                deployment_id=deployment_id,
                agent_target=result.agent_source,
                action_type="generated_artifact",
                context_hash="synthetic-result-assembly",
                constraints=[],
                dependencies=[],
                verification_required=True,
            )
            for result in results
        ]
        package = self.assemble(synthetic_tasks, results)
        if not package.organization_id:
            package.organization_id = organization_id
            package.manifest["organization_id"] = organization_id
        if not package.deployment_id:
            package.deployment_id = deployment_id
            package.manifest["deployment_id"] = deployment_id
        # Synthetic tasks do not carry a full intake context, so apply the
        # tenant boundary using the explicitly supplied organization ID.
        cross_client_errors = self._detect_cross_client_references(results, organization_id)
        if cross_client_errors:
            package.errors.extend(cross_client_errors)
            package.is_complete = False
            package.validation_passed = False
        return package

    def _extract_org_id_from_tasks(self, tasks: list[TaskObject]) -> str:
        """Extract organization ID from task context."""
        # Organization ID should be in task constraints or context
        for task in tasks:
            if (
                hasattr(task, "constraints")
                and isinstance(task.constraints, dict)
                and "organization_id" in task.constraints
            ):
                return task.constraints["organization_id"]
        return ""

    def _check_completeness(
        self, tasks: list[TaskObject], results: list[ResultObject]
    ) -> list[str]:
        """Check that all tasks have corresponding results."""
        errors = []

        task_ids = {task.task_id for task in tasks}
        result_task_ids = {result.task_id for result in results}

        missing = task_ids - result_task_ids
        if missing:
            errors.append(f"Missing results for tasks: {', '.join(sorted(missing))}")

        return errors

    def _verify_provenance(self, tasks: list[TaskObject], results: list[ResultObject]) -> list[str]:
        """Verify that agent_source matches task target."""
        errors = []

        # Build task target map
        task_targets = {task.task_id: task.agent_target for task in tasks}

        for result in results:
            expected_source = task_targets.get(result.task_id)
            if expected_source and result.agent_source != expected_source:
                errors.append(
                    f"Source mismatch for {result.task_id}: "
                    f"expected {expected_source}, got {result.agent_source}"
                )

        return errors

    def _check_validation_status(self, results: list[ResultObject]) -> list[str]:
        """Check that all results have valid validation status."""
        errors = []

        for result in results:
            if result.validation_status not in ("verified", "unverified", "valid"):
                errors.append(
                    f"Validation failed for {result.task_id}: status={result.validation_status}"
                )

            # Check provenance exists and is not empty
            if not result.field_provenance:
                errors.append(f"Missing provenance for {result.task_id}")

        return errors

    def _detect_cross_client_references(
        self, results: list[ResultObject], expected_org_id: str
    ) -> list[str]:
        """
        Detect references to other organization IDs in artifacts.

        Args:
            results: List of results to check
            expected_org_id: Expected organization identifier

        Returns:
            List of cross-client reference errors
        """
        errors: list[str] = []

        if not expected_org_id:
            return errors

        for result in results:
            # Results held in memory have not necessarily been persisted yet.
            # Validate those first so packaging cannot bypass this boundary.
            in_memory_content = getattr(result, "_content", None)
            if in_memory_content is not None:
                foreign_ids = self.detect_cross_client_references(
                    expected_org_id, in_memory_content
                )
                if foreign_ids:
                    errors.append(
                        f"Cross-client references in {result.task_id}: {', '.join(foreign_ids)}"
                    )
                continue
            # Read artifact content
            if not result.storage_path:
                continue

            try:
                artifact_path = Path(result.storage_path)
                if not artifact_path.exists():
                    continue

                with open(artifact_path, encoding="utf-8") as f:
                    content = f.read()

                # Scan for organization IDs
                foreign_ids = self._scan_for_foreign_org_ids(content, expected_org_id)

                if foreign_ids:
                    errors.append(
                        f"Cross-client references in {result.task_id}: {', '.join(foreign_ids)}"
                    )

            except Exception as e:
                errors.append(f"Error scanning {result.task_id}: {str(e)}")

        return errors

    def detect_cross_client_references(
        self, organization_id: str, artifact_content: Any
    ) -> list[str]:
        """Return foreign organization IDs referenced by structured artifact content."""
        if not organization_id:
            return []
        serialized = (
            json.dumps(artifact_content, sort_keys=True)
            if isinstance(artifact_content, (dict, list))
            else str(artifact_content)
        )
        return self._scan_for_foreign_org_ids(serialized, organization_id)

    def _scan_for_foreign_org_ids(self, content: str, expected_org_id: str) -> list[str]:
        """
        Scan content for foreign organization identifiers.

        Args:
            content: Artifact content
            expected_org_id: Expected organization ID

        Returns:
            List of foreign organization IDs found
        """
        foreign_ids = set()

        # Pattern 1: organization_id field in JSON/JS
        pattern1 = r'"organization[_-]?id"\s*[:=]\s*"([a-z0-9_-]+)"'
        matches1 = re.finditer(pattern1, content, re.IGNORECASE)

        for match in matches1:
            org_id = match.group(1)
            if org_id != expected_org_id and "{{" not in org_id:
                foreign_ids.add(org_id)

        # Pattern 2: /webhook/org_id/ paths
        pattern2 = r"/(?:webhook|notify)/([a-z0-9_-]+)(?:/|$)"
        matches2 = re.finditer(pattern2, content)

        for match in matches2:
            org_id = match.group(1)
            if org_id != expected_org_id:
                foreign_ids.add(org_id)

        # Pattern 3: SQL VALUES with organization_id
        pattern3 = r"organization_id\s*[,)]\s*VALUES\s*\([^)]*'([a-z0-9_]+)'"
        matches3 = re.finditer(pattern3, content, re.IGNORECASE)

        for match in matches3:
            org_id = match.group(1)
            if org_id != expected_org_id and "{{" not in org_id:
                foreign_ids.add(org_id)

        # IDs may be embedded in generic route segments, such as
        # ``/org-999/webhook``. Restrict matching to the ID shape rather than
        # broad organization words to avoid false positives in prose.
        for match in re.finditer(
            r"(?<![a-z0-9_-])(org-[a-z0-9_-]+)(?![a-z0-9_-])", content, re.IGNORECASE
        ):
            org_id = match.group(1)
            if org_id != expected_org_id:
                foreign_ids.add(org_id)

        return sorted(foreign_ids)

    def _check_duplicates(self, results: list[ResultObject]) -> list[str]:
        """Check for duplicate task IDs in results."""
        errors = []

        task_ids = [result.task_id for result in results]
        seen = set()
        duplicates = set()

        for task_id in task_ids:
            if task_id in seen:
                duplicates.add(task_id)
            seen.add(task_id)

        if duplicates:
            errors.append(f"Duplicate task IDs in results: {', '.join(sorted(duplicates))}")

        return errors

    def _generate_manifest(
        self, deployment_id: str, organization_id: str, results: list[ResultObject]
    ) -> dict[str, Any]:
        """
        Generate package manifest.

        Args:
            deployment_id: Deployment identifier
            organization_id: Organization identifier
            results: List of results

        Returns:
            Package manifest dictionary
        """
        artifacts = []

        for result in results:
            # Flatten field_provenance from {"field": {"source": "..."}} to {"field": "..."}
            flattened_provenance: dict[str, Any] = {}
            if result.field_provenance:
                for field, value in result.field_provenance.items():
                    if isinstance(value, dict) and "source" in value:
                        flattened_provenance[field] = value["source"]
                    else:
                        flattened_provenance[field] = value

            artifacts.append(
                {
                    "task_id": result.task_id,
                    "agent_source": result.agent_source,
                    "content_hash": result.content_hash,
                    "storage_path": result.storage_path,
                    "summary": result.summary,
                    "field_provenance": flattened_provenance,
                    "model_id": result.model_id,
                    "validation_status": result.validation_status,
                }
            )

        # Compute package hash
        manifest_content = json.dumps(
            {
                "deployment_id": deployment_id,
                "organization_id": organization_id,
                "artifacts": artifacts,
            },
            sort_keys=True,
        )

        package_hash = hash_content(manifest_content)

        manifest = {
            "deployment_id": deployment_id,
            "organization_id": organization_id,
            "package_hash": package_hash,
            "artifact_count": len(artifacts),
            "artifacts": artifacts,
            "provenance_complete": all(result.field_provenance is not None for result in results),
            "validation_complete": all(
                result.validation_status == "verified" for result in results
            ),
        }

        return manifest

    def track_correction_attempts(self, task_id: str, field_name: str, attempt_count: int) -> bool:
        """
        Track correction attempts and escalate on repeated failures.

        Args:
            task_id: Task identifier
            field_name: Field being corrected
            attempt_count: Number of correction attempts

        Returns:
            True if within limits, False if escalation required
        """
        return not attempt_count >= self.max_corrections_per_field

    def assemble_deployment_record(
        self,
        deployment_id: str,
        organization_id: str,
        results: list[ResultObject],
        external_resources: list[dict[str, Any]],
        capabilities: list[str],
    ) -> dict[str, Any]:
        """
        Assemble complete DeploymentRecord for persistence.

        Implements T143: DeploymentRecord assembly (summary, capabilities,
        artifact manifest, resource manifest, verification summary, package hash)

        Args:
            deployment_id: Deployment identifier
            organization_id: Organization identifier
            results: All artifact results
            external_resources: All created external resources
            capabilities: List of capabilities deployed

        Returns:
            Complete deployment record
        """
        # Build artifact manifest
        artifact_manifest = []
        for result in results:
            artifact_manifest.append(
                {
                    "task_id": result.task_id,
                    "agent_source": result.agent_source,
                    "content_hash": result.content_hash,
                    "storage_path": result.storage_path,
                    "validation_status": result.validation_status,
                    "provenance_complete": result.field_provenance is not None,
                }
            )

        # Build resource manifest
        resource_manifest = []
        for resource in external_resources:
            resource_manifest.append(
                {
                    "platform": resource.get("platform"),
                    "resource_type": resource.get("resource_type"),
                    "remote_id": resource.get("remote_id"),
                    "status": resource.get("status"),
                }
            )

        # Verification summary
        verification_summary = {
            "total_artifacts": len(results),
            "artifacts_validated": len([r for r in results if r.validation_status == "valid"]),
            "total_resources": len(external_resources),
            "provenance_complete": all(result.field_provenance is not None for result in results),
        }

        # Compute package hash
        package_content = json.dumps(
            {
                "deployment_id": deployment_id,
                "organization_id": organization_id,
                "artifacts": artifact_manifest,
                "resources": resource_manifest,
            },
            sort_keys=True,
        )

        package_hash = hash_content(package_content)

        # Assemble record
        deployment_record = {
            "deployment_id": deployment_id,
            "organization_id": organization_id,
            "capabilities": capabilities,
            "summary": {
                "artifact_count": len(results),
                "resource_count": len(external_resources),
                "capabilities": capabilities,
            },
            "artifact_manifest": artifact_manifest,
            "resource_manifest": resource_manifest,
            "verification_summary": verification_summary,
            "package_hash": package_hash,
        }

        return deployment_record
