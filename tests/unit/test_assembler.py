"""
Unit tests for package assembler.

Tests cover:
- Provenance enforcement (agent_source must match task target)
- Source mismatch rejection
- Completeness checking (all required artifacts present)
- Validation status verification
- Cross-client reference detection
"""

from orchestrator.assembler import PackageAssembler
from shared.result_object import ResultObject
from shared.task_object import TaskObject


class TestPackageAssembler:
    """Test suite for deployment package assembly."""

    def test_valid_package_assembly(self) -> None:
        """Test that a valid package with all artifacts assembles correctly."""
        tasks = [
            TaskObject(
                task_id="task-1",
                deployment_id="deploy-123",
                agent_target="vapi_agent",
                action_type="generate_assistant_config",
                context_hash="hash-1",
                constraints=[],
                dependencies=[],
                verification_required=True,
                status="pending",
            ),
            TaskObject(
                task_id="task-2",
                deployment_id="deploy-123",
                agent_target="make_agent",
                action_type="generate_scenario_blueprint",
                context_hash="hash-2",
                constraints=[],
                dependencies=["task-1"],
                verification_required=True,
                status="pending",
            ),
        ]

        results = [
            ResultObject(
                task_id="task-1",
                agent_source="vapi_agent",
                content_hash="content-hash-1",
                storage_path="/outputs/vapi_config.json",
                summary="Generated Vapi assistant config",
                field_provenance={"name": {"source": "intake"}, "model": {"source": "inferred"}},
                model_id="gemini-2.5-pro",
                validation_status="verified",
            ),
            ResultObject(
                task_id="task-2",
                agent_source="make_agent",
                content_hash="content-hash-2",
                storage_path="/outputs/make_blueprint.json",
                summary="Generated Make scenario blueprint",
                field_provenance={"name": {"source": "intake"}},
                model_id="gemini-2.5-pro",
                validation_status="verified",
            ),
        ]

        assembler = PackageAssembler()
        package = assembler.assemble(tasks, results)

        assert package.is_complete is True
        assert len(package.artifacts) == 2
        assert package.validation_passed is True
        assert len(package.errors) == 0

    def test_agent_source_mismatch_rejected(self) -> None:
        """Test that results with mismatched agent_source are rejected."""
        tasks = [
            TaskObject(
                task_id="task-1",
                deployment_id="deploy-123",
                agent_target="vapi_agent",
                action_type="generate_assistant_config",
                context_hash="hash-1",
                constraints=[],
                dependencies=[],
                verification_required=True,
                status="pending",
            )
        ]

        results = [
            ResultObject(
                task_id="task-1",
                agent_source="make_agent",  # WRONG! Should be vapi_agent
                content_hash="content-hash-1",
                storage_path="/outputs/vapi_config.json",
                summary="Generated config",
                field_provenance={},
                model_id="gemini-2.5-pro",
                validation_status="verified",
            )
        ]

        assembler = PackageAssembler()
        package = assembler.assemble(tasks, results)

        assert package.is_complete is False
        assert any(
            "source mismatch" in error.lower() or "agent_source" in error.lower()
            for error in package.errors
        )

    def test_missing_result_detected(self) -> None:
        """Test that missing results for tasks are detected."""
        tasks = [
            TaskObject(
                task_id="task-1",
                deployment_id="deploy-123",
                agent_target="vapi_agent",
                action_type="generate_assistant_config",
                context_hash="hash-1",
                constraints=[],
                dependencies=[],
                verification_required=True,
                status="pending",
            ),
            TaskObject(
                task_id="task-2",
                deployment_id="deploy-123",
                agent_target="make_agent",
                action_type="generate_scenario_blueprint",
                context_hash="hash-2",
                constraints=[],
                dependencies=[],
                verification_required=True,
                status="pending",
            ),
        ]

        results = [
            ResultObject(
                task_id="task-1",
                agent_source="vapi_agent",
                content_hash="content-hash-1",
                storage_path="/outputs/vapi_config.json",
                summary="Generated config",
                field_provenance={},
                model_id="gemini-2.5-pro",
                validation_status="verified",
            )
            # Missing result for task-2
        ]

        assembler = PackageAssembler()
        package = assembler.assemble(tasks, results)

        assert package.is_complete is False
        assert any(
            "missing" in error.lower() or "task-2" in error.lower() for error in package.errors
        )

    def test_validation_failed_status_rejected(self) -> None:
        """Test that artifacts with validation_status != 'valid' are rejected."""
        tasks = [
            TaskObject(
                task_id="task-1",
                deployment_id="deploy-123",
                agent_target="vapi_agent",
                action_type="generate_assistant_config",
                context_hash="hash-1",
                constraints=[],
                dependencies=[],
                verification_required=True,
                status="pending",
            )
        ]

        results = [
            ResultObject(
                task_id="task-1",
                agent_source="vapi_agent",
                content_hash="content-hash-1",
                storage_path="/outputs/vapi_config.json",
                summary="Generated config",
                field_provenance={},
                model_id="gemini-2.5-pro",
                validation_status="failed",  # FAILED validation
            )
        ]

        assembler = PackageAssembler()
        package = assembler.assemble(tasks, results)

        assert package.is_complete is False
        assert package.validation_passed is False
        assert any(
            "validation" in error.lower() and "failed" in error.lower() for error in package.errors
        )

    def test_untrusted_provenance_rejected(self) -> None:
        """Test that results with untrusted provenance are rejected."""
        tasks = [
            TaskObject(
                task_id="task-1",
                deployment_id="deploy-123",
                agent_target="vapi_agent",
                action_type="generate_assistant_config",
                context_hash="hash-1",
                constraints=[],
                dependencies=[],
                verification_required=True,
                status="pending",
            )
        ]

        results = [
            ResultObject(
                task_id="task-1",
                agent_source="vapi_agent",
                content_hash="content-hash-1",
                storage_path="/outputs/vapi_config.json",
                summary="Generated config",
                field_provenance={},  # Missing provenance
                model_id="gemini-2.5-pro",
                validation_status="verified",
            )
        ]

        assembler = PackageAssembler()
        package = assembler.assemble(tasks, results)

        assert package.is_complete is False
        assert any("provenance" in error.lower() for error in package.errors)

    def test_manifest_includes_hashes(self) -> None:
        """Test that assembled package manifest includes content hashes."""
        tasks = [
            TaskObject(
                task_id="task-1",
                deployment_id="deploy-123",
                agent_target="vapi_agent",
                action_type="generate_assistant_config",
                context_hash="hash-1",
                constraints=[],
                dependencies=[],
                verification_required=True,
                status="pending",
            )
        ]

        results = [
            ResultObject(
                task_id="task-1",
                agent_source="vapi_agent",
                content_hash="content-hash-1",
                storage_path="/outputs/vapi_config.json",
                summary="Generated config",
                field_provenance={
                    "name": {"source": "intake"},
                },
                model_id="gemini-2.5-pro",
                validation_status="verified",
            )
        ]

        assembler = PackageAssembler()
        package = assembler.assemble(tasks, results)

        assert package.is_complete is True
        assert "content-hash-1" in package.manifest["artifacts"][0]["content_hash"]

    def test_duplicate_task_id_detected(self) -> None:
        """Test that duplicate task IDs in results are detected."""
        tasks = [
            TaskObject(
                task_id="task-1",
                deployment_id="deploy-123",
                agent_target="vapi_agent",
                action_type="generate_assistant_config",
                context_hash="hash-1",
                constraints=[],
                dependencies=[],
                verification_required=True,
                status="pending",
            )
        ]

        results = [
            ResultObject(
                task_id="task-1",
                agent_source="vapi_agent",
                content_hash="content-hash-1",
                storage_path="/outputs/vapi_config.json",
                summary="Generated config",
                field_provenance={
                    "name": {"source": "intake"},
                },
                model_id="gemini-2.5-pro",
                validation_status="verified",
            ),
            ResultObject(
                task_id="task-1",  # DUPLICATE!
                agent_source="vapi_agent",
                content_hash="content-hash-2",
                storage_path="/outputs/vapi_config_v2.json",
                summary="Generated config again",
                field_provenance={
                    "name": {"source": "intake"},
                },
                model_id="gemini-2.5-pro",
                validation_status="verified",
            ),
        ]

        assembler = PackageAssembler()
        package = assembler.assemble(tasks, results)

        assert package.is_complete is False
        assert any("duplicate" in error.lower() for error in package.errors)

    def test_empty_tasks_list(self) -> None:
        """Test that empty tasks list is handled correctly."""
        tasks: list[TaskObject] = []
        results: list[ResultObject] = []

        assembler = PackageAssembler()
        package = assembler.assemble(tasks, results)

        assert package.is_complete is True  # Vacuous truth: no tasks means nothing to assemble
        assert len(package.artifacts) == 0

    def test_field_provenance_tracking(self) -> None:
        """Test that field provenance is correctly tracked in manifest."""
        tasks = [
            TaskObject(
                task_id="task-1",
                deployment_id="deploy-123",
                agent_target="vapi_agent",
                action_type="generate_assistant_config",
                context_hash="hash-1",
                constraints=[],
                dependencies=[],
                verification_required=True,
                status="pending",
            )
        ]

        results = [
            ResultObject(
                task_id="task-1",
                agent_source="vapi_agent",
                content_hash="content-hash-1",
                storage_path="/outputs/vapi_config.json",
                summary="Generated config",
                field_provenance={
                    "name": {"source": "intake-copied"},
                    "model": {"source": "inferred"},
                    "voice": {"source": "defaulted"},
                },
                model_id="gemini-2.5-pro",
                validation_status="verified",
            )
        ]

        assembler = PackageAssembler()
        package = assembler.assemble(tasks, results)

        assert package.is_complete is True
        artifact = package.manifest["artifacts"][0]
        assert artifact["field_provenance"]["name"] == "intake-copied"
        assert artifact["field_provenance"]["model"] == "inferred"
        assert artifact["field_provenance"]["voice"] == "defaulted"
