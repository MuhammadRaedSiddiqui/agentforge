"""
Integration test for full package generation from fixture.

Tests the complete flow:
1. Load intake fixture
2. Generate all artifacts (Vapi, Make, Supabase, Node.js)
3. Validate all artifacts
4. Assemble package
5. Verify completeness without contacting write endpoints
"""

import json
from pathlib import Path
from typing import Any

import pytest

from agents.make_agent.agent import MakeAgent
from agents.nodejs_agent.agent import NodeJsAgent
from agents.supabase_agent.agent import SupabaseAgent
from agents.vapi_agent.agent import VapiAgent
from orchestrator.assembler import PackageAssembler
from orchestrator.planner import Planner


class TestGenerationPackage:
    """Integration test suite for complete package generation."""

    @pytest.fixture
    def staging_intake(self) -> dict[str, Any]:
        """Load staging client intake fixture."""
        fixture_path = Path("tests/fixtures/staging_client.json")
        with open(fixture_path) as f:
            return json.load(f)

    @pytest.fixture
    def planner(self) -> Planner:
        """Create planner instance."""
        return Planner()

    @pytest.fixture
    def assembler(self) -> PackageAssembler:
        """Create assembler instance."""
        return PackageAssembler()

    def test_full_package_generation_from_fixture(
        self, staging_intake: dict[str, Any], planner: Planner, assembler: PackageAssembler
    ) -> None:
        """
        Test complete package generation flow without live writes.

        This test verifies:
        - All required artifacts are generated
        - All validators pass
        - Package is complete
        - No external write endpoints are contacted
        """
        # Step 1: Generate task plan from intake
        task_graph = planner.create_task_graph(staging_intake, deployment_intent="new_onboarding")
        tasks = task_graph.get_ordered_tasks()

        assert len(tasks) > 0, "Task graph should contain tasks"
        assert all(task.deployment_id == tasks[0].deployment_id for task in tasks), (
            "All tasks should share deployment_id"
        )

        # Step 2: Execute generation tasks (not live deployment tasks)
        generation_tasks = [t for t in tasks if "generate" in t.action_type.lower()]
        assert len(generation_tasks) >= 4, (
            "Should have at least 4 generation tasks (Vapi, Make, Supabase, Node.js)"
        )

        results = []

        # Generate Vapi artifacts
        vapi_tasks = [t for t in generation_tasks if t.agent_target == "vapi_agent"]
        for task in vapi_tasks:
            vapi_agent = VapiAgent()
            result = vapi_agent.execute(task, staging_intake)
            assert result is not None, f"Vapi agent should return result for {task.task_id}"
            assert result.validation_status == "verified", (
                f"Vapi result should be verified: {task.task_id}"
            )
            results.append(result)

        # Generate Make artifacts
        make_tasks = [t for t in generation_tasks if t.agent_target == "make_agent"]
        for task in make_tasks:
            make_agent = MakeAgent()
            result = make_agent.execute(task, staging_intake)
            assert result is not None, f"Make agent should return result for {task.task_id}"
            assert result.validation_status == "verified", (
                f"Make result should be verified: {task.task_id}"
            )
            results.append(result)

        # Generate Supabase artifacts
        supabase_tasks = [t for t in generation_tasks if t.agent_target == "supabase_agent"]
        for task in supabase_tasks:
            supabase_agent = SupabaseAgent()
            result = supabase_agent.execute(task, staging_intake)
            assert result is not None, f"Supabase agent should return result for {task.task_id}"
            assert result.validation_status == "verified", (
                f"Supabase result should be verified: {task.task_id}"
            )
            results.append(result)

        # Generate Node.js artifacts
        nodejs_tasks = [t for t in generation_tasks if t.agent_target == "nodejs_agent"]
        for task in nodejs_tasks:
            nodejs_agent = NodeJsAgent()
            result = nodejs_agent.execute(task, staging_intake)
            assert result is not None, f"Node.js agent should return result for {task.task_id}"
            assert result.validation_status == "verified", (
                f"Node.js result should be verified: {task.task_id}"
            )
            results.append(result)

        # Step 3: Assemble package
        package = assembler.assemble(generation_tasks, results)

        # Verify package completeness
        assert package.is_complete is True, f"Package should be complete. Errors: {package.errors}"
        assert package.validation_passed is True, "All validations should pass"
        assert len(package.artifacts) == len(generation_tasks), (
            "Should have artifact for each generation task"
        )

        # Verify manifest structure
        assert "artifacts" in package.manifest
        assert "deployment_id" in package.manifest
        assert "organization_id" in package.manifest
        assert "package_hash" in package.manifest

        # Verify all artifacts have required fields
        for artifact in package.artifacts:
            assert artifact.content_hash is not None, "Artifact should have content hash"
            assert artifact.storage_path is not None, "Artifact should have storage path"
            assert artifact.field_provenance is not None, "Artifact should have provenance"
            assert artifact.validation_status == "verified", "Artifact should be verified"

    def test_package_generation_no_external_writes(
        self,
        staging_intake: dict[str, Any],
        planner: Planner,
        assembler: PackageAssembler,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify that package generation makes no external write calls.

        Uses monkeypatch to detect any attempted external API calls.
        """
        # Track external calls
        external_calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

        def mock_http_post(*args: Any, **kwargs: Any) -> None:
            external_calls.append(("POST", args, kwargs))
            raise AssertionError("No external POST calls should be made during generation")

        def mock_http_put(*args: Any, **kwargs: Any) -> None:
            external_calls.append(("PUT", args, kwargs))
            raise AssertionError("No external PUT calls should be made during generation")

        def mock_http_delete(*args: Any, **kwargs: Any) -> None:
            external_calls.append(("DELETE", args, kwargs))
            raise AssertionError("No external DELETE calls should be made during generation")

        # Patch HTTP methods
        import requests

        monkeypatch.setattr(requests, "post", mock_http_post)
        monkeypatch.setattr(requests, "put", mock_http_put)
        monkeypatch.setattr(requests, "delete", mock_http_delete)

        # Run generation
        task_graph = planner.create_task_graph(staging_intake, deployment_intent="new_onboarding")
        tasks = task_graph.get_ordered_tasks()
        generation_tasks = [t for t in tasks if "generate" in t.action_type.lower()]

        results = []
        for task in generation_tasks:
            if task.agent_target == "vapi_agent":
                vapi_agent = VapiAgent()
                result = vapi_agent.execute(task, staging_intake)
            elif task.agent_target == "make_agent":
                make_agent = MakeAgent()
                result = make_agent.execute(task, staging_intake)
            elif task.agent_target == "supabase_agent":
                supabase_agent = SupabaseAgent()
                result = supabase_agent.execute(task, staging_intake)
            elif task.agent_target == "nodejs_agent":
                nodejs_agent = NodeJsAgent()
                result = nodejs_agent.execute(task, staging_intake)
            else:
                continue

            results.append(result)

        # Assemble package
        package = assembler.assemble(generation_tasks, results)

        # Verify no external calls were made
        assert len(external_calls) == 0, (
            f"No external write calls should be made. Found: {external_calls}"
        )

    def test_cross_client_reference_detection(
        self, staging_intake: dict[str, Any], planner: Planner, assembler: PackageAssembler
    ) -> None:
        """Test that cross-client references are detected during assembly."""
        task_graph = planner.create_task_graph(staging_intake, deployment_intent="new_onboarding")
        tasks = task_graph.get_ordered_tasks()
        generation_tasks = [t for t in tasks if "generate" in t.action_type.lower()]

        results = []
        vapi_task = next(task for task in generation_tasks if task.agent_target == "vapi_agent")
        for task in [vapi_task]:
            if task.agent_target == "vapi_agent":
                vapi_agent = VapiAgent()
                result = vapi_agent.execute(task, staging_intake)
                artifact_path = Path(result.storage_path)
                artifact_path.write_text(
                    artifact_path.read_text(encoding="utf-8").replace(
                        "agent_forge_staging", "other_client_org"
                    ),
                    encoding="utf-8",
                )
                results.append(result)

        # Assembler should detect cross-client reference
        package = assembler.assemble_package(
            vapi_task.deployment_id, staging_intake["organization_id"], results
        )
        assert any(
            "cross-client" in error.lower() or "foreign" in error.lower()
            for error in package.errors
        ), "Cross-client reference should be detected"

    def test_secret_not_in_artifacts(
        self, staging_intake: dict[str, Any], planner: Planner, assembler: PackageAssembler
    ) -> None:
        """Verify that no secrets appear in generated artifacts."""
        tasks = planner.create_task_graph(staging_intake, deployment_intent="new_onboarding")
        generation_tasks = [t for t in tasks if "generate" in t.action_type.lower()]

        results = []
        for task in generation_tasks:
            if task.agent_target == "vapi_agent":
                agent = VapiAgent()
            elif task.agent_target == "make_agent":
                agent = MakeAgent()
            elif task.agent_target == "supabase_agent":
                agent = SupabaseAgent()
            elif task.agent_target == "nodejs_agent":
                agent = NodeJsAgent()
            else:
                continue

            result = agent.execute(task, staging_intake)
            results.append(result)

            # Read artifact file and scan for secrets
            if result.storage_path:
                with open(result.storage_path) as f:
                    content = f.read()

                # Check for common secret patterns
                assert "sk-" not in content, "OpenAI key pattern should not appear"
                assert "api_key" not in content.lower() or "process.env" in content, (
                    "API key should reference env var"
                )
                assert "Bearer " not in content or "process.env" in content, (
                    "Bearer token should reference env var"
                )

    def test_field_provenance_completeness(
        self, staging_intake: dict[str, Any], planner: Planner, assembler: PackageAssembler
    ) -> None:
        """Verify that all generated fields have provenance."""
        tasks = planner.create_task_graph(staging_intake, deployment_intent="new_onboarding")
        generation_tasks = [t for t in tasks if "generate" in t.action_type.lower()]

        results = []
        for task in generation_tasks[:2]:  # Test first two tasks
            if task.agent_target == "vapi_agent":
                agent = VapiAgent()
            elif task.agent_target == "make_agent":
                agent = MakeAgent()
            else:
                continue

            result = agent.execute(task, staging_intake)
            results.append(result)

            # Verify field provenance is not empty
            assert result.field_provenance is not None, "Field provenance should exist"
            assert len(result.field_provenance) > 0, "Field provenance should contain entries"

            # Verify all provenance values are valid
            valid_sources = ["copied", "derived", "inferred", "defaulted", "template"]
            for field, source in result.field_provenance.items():
                assert isinstance(source, dict), f"Provenance for '{field}' must be structured"
                assert source.get("type") in valid_sources, (
                    f"Invalid provenance source '{source}' for field '{field}'"
                )
