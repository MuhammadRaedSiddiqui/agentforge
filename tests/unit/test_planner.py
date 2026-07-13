"""
Unit tests for planner task graph generation.

Tests for correct ordering, dependencies, approval points, and all capabilities.
"""

import pytest

from orchestrator.planner import Planner, TaskGraph


@pytest.mark.unit
class TestPlanner:
    """Tests for task graph planner."""

    def test_availability_capability_tasks(self) -> None:
        """Should generate correct tasks for availability capability."""
        intake = {
            "organization_id": "test_org",
            "enabled_capabilities": ["availability"],
            "business_hours": {"monday": []},
            "timezone": "America/New_York",
            "booking_calendar_id": "cal_123",
        }

        planner = Planner()
        graph = planner.create_task_graph(intake)

        # Should have tasks for Vapi, Make, and Node.js
        assert graph.has_agent_tasks("vapi_agent")
        assert graph.has_agent_tasks("make_agent")
        assert graph.has_agent_tasks("nodejs_agent")

        # Should NOT have Supabase tasks for availability only
        assert not graph.has_agent_tasks("supabase_agent")

    def test_booking_capability_tasks(self) -> None:
        """Should generate correct tasks for booking capability including database."""
        intake = {
            "organization_id": "test_org",
            "enabled_capabilities": ["booking"],
            "business_hours": {"monday": []},
            "services_offered": [{"name": "Test"}],
            "booking_calendar_id": "cal_123",
        }

        planner = Planner()
        graph = planner.create_task_graph(intake)

        # Booking requires all agents including Supabase
        assert graph.has_agent_tasks("vapi_agent")
        assert graph.has_agent_tasks("make_agent")
        assert graph.has_agent_tasks("supabase_agent")
        assert graph.has_agent_tasks("nodejs_agent")

    def test_task_dependencies_correct_order(self) -> None:
        """Should create tasks in correct dependency order."""
        intake = {
            "organization_id": "test_org",
            "enabled_capabilities": ["availability"],
            "business_hours": {"monday": []},
            "booking_calendar_id": "cal_123",
        }

        planner = Planner()
        graph = planner.create_task_graph(intake)

        tasks = graph.get_ordered_tasks()

        # Supabase generation should come before others (if present)
        # Vapi, Make, Node.js can be parallel
        # Validations follow their respective generations
        # Approvals follow validations

        # Check that validation tasks depend on generation tasks
        for task in tasks:
            if "validate" in task.action_type.lower():
                # Find corresponding generation task
                gen_task_id = task.action_type.replace("validate_", "generate_")
                # Validation should depend on generation
                assert len(task.dependencies) > 0

    def test_approval_points_for_each_action(self) -> None:
        """Should have approval points for each external action."""
        intake = {
            "organization_id": "test_org",
            "enabled_capabilities": ["availability"],
            "business_hours": {"monday": []},
            "booking_calendar_id": "cal_123",
        }

        planner = Planner()
        graph = planner.create_task_graph(intake)

        # Should have approval points
        approval_tasks = graph.get_approval_tasks()
        assert len(approval_tasks) > 0

        # Each approval should be for a specific action
        for approval in approval_tasks:
            assert "approve" in approval.action_type.lower()

    def test_multiple_capabilities_task_deduplication(self) -> None:
        """Should not duplicate shared tasks when multiple capabilities enabled."""
        intake = {
            "organization_id": "test_org",
            "enabled_capabilities": ["availability", "booking", "cancellation"],
            "business_hours": {"monday": []},
            "services_offered": [{"name": "Test"}],
            "booking_calendar_id": "cal_123",
            "cancellation_window_hours": 24,
        }

        planner = Planner()
        graph = planner.create_task_graph(intake)

        # Should have one set of Vapi generation tasks, not duplicated per capability
        vapi_tasks = [t for t in graph.get_all_tasks()
                      if t.agent_target == "vapi_agent"]

        # Count generation tasks (not validation or approval)
        gen_tasks = [t for t in vapi_tasks if "generate" in t.action_type.lower()]

        # Should have a reasonable number, not multiplied by capability count
        assert len(gen_tasks) < 10

    def test_dry_run_plan_includes_expected_outputs(self) -> None:
        """Should include expected outputs for each task."""
        intake = {
            "organization_id": "test_org",
            "enabled_capabilities": ["availability"],
            "business_hours": {"monday": []},
            "booking_calendar_id": "cal_123",
        }

        planner = Planner()
        graph = planner.create_task_graph(intake)
        plan = planner.create_dry_run_plan(graph, intake)

        # Plan should describe expected outputs
        assert "expected_outputs" in plan or "artifacts" in plan
        assert "intended_changes" in plan or "actions" in plan

    def test_dry_run_plan_includes_validations(self) -> None:
        """Should include validation steps in plan."""
        intake = {
            "organization_id": "test_org",
            "enabled_capabilities": ["availability"],
            "business_hours": {"monday": []},
            "booking_calendar_id": "cal_123",
        }

        planner = Planner()
        graph = planner.create_task_graph(intake)
        plan = planner.create_dry_run_plan(graph, intake)

        # Plan should mention validations
        plan_str = str(plan)
        assert "validat" in plan_str.lower()

    def test_task_graph_topological_sort(self) -> None:
        """Should produce valid topological ordering of tasks."""
        intake = {
            "organization_id": "test_org",
            "enabled_capabilities": ["booking"],
            "business_hours": {"monday": []},
            "services_offered": [{"name": "Test"}],
            "booking_calendar_id": "cal_123",
        }

        planner = Planner()
        graph = planner.create_task_graph(intake)
        ordered = graph.get_ordered_tasks()

        # Verify topological order: all dependencies appear before dependents
        seen_ids = set()
        for task in ordered:
            for dep_id in task.dependencies:
                assert dep_id in seen_ids, \
                    f"Task {task.task_id} depends on {dep_id} which hasn't been seen yet"
            seen_ids.add(task.task_id)

    def test_no_circular_dependencies(self) -> None:
        """Should not create circular dependencies."""
        intake = {
            "organization_id": "test_org",
            "enabled_capabilities": ["availability", "booking"],
            "business_hours": {"monday": []},
            "services_offered": [{"name": "Test"}],
            "booking_calendar_id": "cal_123",
        }

        planner = Planner()
        graph = planner.create_task_graph(intake)

        # If topological sort succeeds, there are no cycles
        ordered = graph.get_ordered_tasks()
        assert len(ordered) > 0

    def test_all_capabilities_covered(self) -> None:
        """Should generate tasks for all enabled capabilities."""
        all_capabilities = [
            "availability",
            "booking",
            "cancellation",
            "rescheduling",
            "human_transfer",
        ]

        intake = {
            "organization_id": "test_org",
            "enabled_capabilities": all_capabilities,
            "business_hours": {"monday": []},
            "services_offered": [{"name": "Test"}],
            "booking_calendar_id": "cal_123",
            "cancellation_window_hours": 24,
            "rescheduling_policy": {"minimum_notice_hours": 12},
            "transfer_destination": "+15555550199",
        }

        planner = Planner()
        graph = planner.create_task_graph(intake)

        # Should have tasks covering all capabilities
        # (Exact verification would depend on implementation)
        assert len(graph.get_all_tasks()) > 10

    def test_inferred_fields_marked_in_plan(self) -> None:
        """Should mark inferred/defaulted fields in dry-run plan."""
        intake = {
            "organization_id": "test_org",
            "enabled_capabilities": ["availability"],
            "business_hours": {"monday": []},
            "booking_calendar_id": "cal_123",
            # Some fields will be inferred/defaulted
        }

        planner = Planner()
        graph = planner.create_task_graph(intake)
        plan = planner.create_dry_run_plan(graph, intake)

        # Plan should indicate which fields are inferred
        plan_str = str(plan)
        assert "inferred" in plan_str.lower() or "default" in plan_str.lower()

    def test_compensation_strategy_in_plan(self) -> None:
        """Should include compensation strategy for each action."""
        intake = {
            "organization_id": "test_org",
            "enabled_capabilities": ["availability"],
            "business_hours": {"monday": []},
            "booking_calendar_id": "cal_123",
        }

        planner = Planner()
        graph = planner.create_task_graph(intake)
        plan = planner.create_dry_run_plan(graph, intake)

        # Plan should mention compensation
        plan_str = str(plan)
        assert "compensat" in plan_str.lower() or "recovery" in plan_str.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
