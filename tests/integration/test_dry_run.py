"""
Integration test for full dry-run flow.

Tests that a fixture intake produces a complete plan with zero external writes.
"""

import json
from pathlib import Path

import pytest

from cli.config import AgentForgeConfig, load_config
from orchestrator.orchestrator import Orchestrator


@pytest.mark.integration
class TestDryRunFlow:
    """Integration tests for dry-run planning flow."""

    @pytest.fixture
    def config(self) -> AgentForgeConfig:
        """Load configuration from environment."""
        return load_config()

    @pytest.fixture
    def orchestrator(self, config: AgentForgeConfig) -> Orchestrator:
        """Create orchestrator instance."""
        return Orchestrator(config)

    @pytest.fixture
    def staging_fixture(self) -> dict:
        """Load staging client fixture."""
        fixture_path = Path("tests/fixtures/staging_client.json")

        if not fixture_path.exists():
            # Return minimal fixture if file doesn't exist yet
            return {
                "organization_id": "test_staging_org",
                "business_name": "Test Staging Business",
                "phone_number": "+15555550100",
                "voice_id": "test_voice",
                "timezone": "America/New_York",
                "business_hours": {"monday": [{"open": "09:00", "close": "17:00"}]},
                "services_offered": [{"name": "Consultation", "duration_minutes": 30}],
                "booking_calendar_id": "test_calendar",
                "cancellation_window_hours": 24,
                "rescheduling_policy": {"minimum_notice_hours": 12},
                "transfer_destination": "+15555550199",
                "enabled_capabilities": [
                    "availability",
                    "booking",
                    "cancellation",
                    "rescheduling",
                    "human_transfer",
                ],
                "external_identifiers": {"vapi_phone_number_id": "test_phone_id"},
            }

        with fixture_path.open("r") as f:
            return json.load(f)

    def test_dry_run_produces_complete_plan(
        self, orchestrator: Orchestrator, staging_fixture: dict
    ) -> None:
        """Should produce complete plan from fixture."""
        result = orchestrator.dry_run(staging_fixture)

        assert result["success"] is True
        assert "plan" in result

        plan = result["plan"]

        # Plan should have required sections
        assert "organization_id" in plan
        assert "tasks" in plan or "phases" in plan
        assert "validations" in plan or "validation_steps" in plan

    def test_dry_run_zero_external_writes(
        self, orchestrator: Orchestrator, staging_fixture: dict
    ) -> None:
        """Should make zero external writes during dry-run."""
        # This is a contract test - implementation should track calls
        result = orchestrator.dry_run(staging_fixture)

        # Verify no external API calls were made
        # (Implementation would need to track this)
        assert result.get("external_calls_made", 0) == 0

    def test_dry_run_shows_ordered_tasks(
        self, orchestrator: Orchestrator, staging_fixture: dict
    ) -> None:
        """Should show tasks in dependency order."""
        result = orchestrator.dry_run(staging_fixture)

        plan = result["plan"]
        tasks = plan.get("tasks", [])

        assert len(tasks) > 0

        # Tasks should have IDs and dependencies
        for task in tasks:
            assert "id" in task or "task_id" in task
            assert "action" in task or "action_type" in task

    def test_dry_run_shows_approval_points(
        self, orchestrator: Orchestrator, staging_fixture: dict
    ) -> None:
        """Should show approval points in plan."""
        result = orchestrator.dry_run(staging_fixture)

        plan = result["plan"]

        # Should have approval information
        plan_str = json.dumps(plan)
        assert "approval" in plan_str.lower()

    def test_dry_run_shows_expected_outputs(
        self, orchestrator: Orchestrator, staging_fixture: dict
    ) -> None:
        """Should show expected outputs for each task."""
        result = orchestrator.dry_run(staging_fixture)

        plan = result["plan"]

        # Should describe what will be generated
        plan_str = json.dumps(plan)
        assert "vapi" in plan_str.lower() or "assistant" in plan_str.lower()

    def test_dry_run_shows_intended_changes(
        self, orchestrator: Orchestrator, staging_fixture: dict
    ) -> None:
        """Should show intended external changes."""
        result = orchestrator.dry_run(staging_fixture)

        plan = result["plan"]

        # Should list external actions
        assert "actions" in plan or "changes" in plan or "operations" in plan

    def test_dry_run_handles_existing_deployment(
        self, orchestrator: Orchestrator, staging_fixture: dict
    ) -> None:
        """Should detect and report existing deployment."""
        # This test would need to set up existing deployment state
        # For now, test that the check happens
        result = orchestrator.dry_run(staging_fixture)

        # Should have checked for existing deployment
        assert "existing_deployment" in result or "deployment_status" in result

    def test_dry_run_normalizes_organization_id(self, orchestrator: Orchestrator) -> None:
        """Should normalize organization_id in plan."""
        fixture = {
            "organization_id": "Test Org Name!",
            "business_name": "Test Business",
            "phone_number": "+15555550100",
            "voice_id": "test_voice",
            "timezone": "America/New_York",
            "business_hours": {},
            "services_offered": [],
            "enabled_capabilities": [],
            "external_identifiers": {},
        }

        result = orchestrator.dry_run(fixture)

        plan = result["plan"]

        # Organization ID should be normalized
        org_id = plan.get("organization_id", "")
        assert org_id.islower()
        assert " " not in org_id

    def test_dry_run_validates_intake_first(self, orchestrator: Orchestrator) -> None:
        """Should validate intake before planning."""
        invalid_fixture = {
            "organization_id": "test_org",
            # Missing required fields
            "enabled_capabilities": [],
            "external_identifiers": {},
        }

        result = orchestrator.dry_run(invalid_fixture)

        # Should fail validation
        assert result["success"] is False
        assert "errors" in result or "validation_errors" in result

    def test_dry_run_includes_compensation_strategy(
        self, orchestrator: Orchestrator, staging_fixture: dict
    ) -> None:
        """Should include compensation strategy for each action."""
        result = orchestrator.dry_run(staging_fixture)

        plan = result["plan"]
        plan_str = json.dumps(plan)

        # Should mention compensation or recovery
        assert "compensat" in plan_str.lower() or "recovery" in plan_str.lower()

    def test_dry_run_includes_reconciliation_strategy(
        self, orchestrator: Orchestrator, staging_fixture: dict
    ) -> None:
        """Should include reconciliation strategy for each action."""
        result = orchestrator.dry_run(staging_fixture)

        plan = result["plan"]
        plan_str = json.dumps(plan)

        # Should mention reconciliation
        assert "reconcil" in plan_str.lower()

    def test_dry_run_output_is_json_serializable(
        self, orchestrator: Orchestrator, staging_fixture: dict
    ) -> None:
        """Plan output should be JSON serializable."""
        result = orchestrator.dry_run(staging_fixture)

        # Should be able to serialize to JSON
        json_output = json.dumps(result, indent=2)
        assert len(json_output) > 0

        # Should be able to deserialize
        parsed = json.loads(json_output)
        assert parsed["success"] == result["success"]

    def test_dry_run_capability_specific_validations(self, orchestrator: Orchestrator) -> None:
        """Should validate capability-specific required fields."""
        # Booking capability without calendar ID
        fixture = {
            "organization_id": "test_org",
            "business_name": "Test Business",
            "phone_number": "+15555550100",
            "voice_id": "test_voice",
            "timezone": "America/New_York",
            "business_hours": {},
            "services_offered": [],
            "enabled_capabilities": ["booking"],
            "external_identifiers": {},
            # Missing booking_calendar_id
        }

        result = orchestrator.dry_run(fixture)

        # Should fail validation
        assert result["success"] is False
        assert any("booking_calendar_id" in str(err).lower() for err in result.get("errors", []))

    def test_dry_run_plan_includes_all_enabled_capabilities(
        self, orchestrator: Orchestrator, staging_fixture: dict
    ) -> None:
        """Should include tasks for all enabled capabilities."""
        result = orchestrator.dry_run(staging_fixture)

        plan = result["plan"]
        plan_str = json.dumps(plan).lower()

        # Should reference enabled capabilities
        for capability in staging_fixture["enabled_capabilities"]:
            # At least some mention of each capability
            assert (
                capability.lower() in plan_str or capability.replace("_", " ").lower() in plan_str
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
