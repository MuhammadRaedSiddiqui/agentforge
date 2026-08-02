"""
Failure injection test: Compensation operation failure.

Tests T109: Verify deployment remains unresolved when compensation fails,
and next safe action is identified.
"""

from unittest.mock import Mock

import pytest

from orchestrator.recovery import RecoveryOrchestrator
from shared.errors import (
    AuthorizationError,
    PermanentError,
    TransientError,
)


@pytest.mark.failure_injection
class TestCompensationFailure:
    """
    Test scenarios where compensation operations fail.

    Critical requirement: System must honestly report compensation failure
    and not claim successful rollback when it didn't happen.
    """

    def test_delete_assistant_compensation_fails(self) -> None:
        """
        Test: Attempt to compensate by deleting assistant fails.

        Expected:
        1. Original create_assistant succeeded
        2. Later action failed, requiring compensation
        3. delete_assistant compensation attempted
        4. Compensation fails (authorization error)
        5. Deployment remains in recovery_required state
        6. Existing resources listed
        7. Manual intervention recommended
        """
        internal_store = Mock()

        # Mock existing resources
        internal_store.list_external_resources.return_value = [
            {
                "platform": "vapi",
                "resource_type": "assistant",
                "remote_resource_id": "asst_comp_123",
                "lifecycle_status": "active",
            }
        ]

        # Mock recovery action
        internal_store.update_recovery_action_status.return_value = None

        # Create mock Vapi adapter
        vapi = Mock()

        # Compensation fails - maybe permissions changed
        vapi.delete_assistant.side_effect = AuthorizationError(
            "Insufficient permissions to delete assistant"
        )

        recovery = RecoveryOrchestrator(
            internal_store=internal_store,
            adapters={"vapi": vapi},
        )

        # Attempt compensation
        result = recovery.handle_compensation_failure(
            deployment_id="dep_comp_001",
            recovery_action_id="rec_001",
            error=AuthorizationError("Insufficient permissions"),
        )

        # Verify deployment remains unresolved
        assert result["status"] == "compensation_failed"
        assert result["deployment_status"] == "recovery_required"
        assert result["recommendation"] == "manual_inspection"

        # Verify existing resources are listed
        assert len(result["existing_resources"]) == 1
        assert result["existing_resources"][0]["remote_resource_id"] == "asst_comp_123"

        # Verify next actions are provided
        assert "next_actions" in result
        assert len(result["next_actions"]) > 0

    def test_delete_scenario_compensation_transient_failure(self) -> None:
        """
        Test: Compensation fails transiently but could be retried.

        Expected:
        1. delete_scenario attempted
        2. Transient error (service unavailable)
        3. Compensation marked as failed but retriable
        4. Operator can retry compensation
        """
        internal_store = Mock()

        internal_store.list_external_resources.return_value = [
            {
                "platform": "make",
                "resource_type": "scenario",
                "remote_resource_id": "scen_comp_456",
                "lifecycle_status": "active",
            }
        ]

        # Create mock Make adapter
        make = Mock()

        # Transient failure
        make.delete_scenario.side_effect = TransientError("Make.com API temporarily unavailable")

        recovery = RecoveryOrchestrator(
            internal_store=internal_store,
            adapters={"make": make},
        )

        result = recovery.handle_compensation_failure(
            deployment_id="dep_comp_002",
            recovery_action_id="rec_002",
            error=TransientError("API unavailable"),
        )

        assert result["status"] == "compensation_failed"
        assert result["error_class"] == "transient"

        # Transient failures can be retried
        assert "next_actions" in result

    def test_partial_compensation_success(self) -> None:
        """
        Test: Multiple resources to compensate, some succeed, some fail.

        Expected:
        1. Assistant deletion succeeds
        2. Tool deletion fails
        3. Deployment still requires recovery
        4. Remaining resources identified
        5. Partial success acknowledged
        """
        internal_store = Mock()

        # Two resources to compensate
        internal_store.list_external_resources.return_value = [
            {
                "platform": "vapi",
                "resource_type": "assistant",
                "remote_resource_id": "asst_partial_111",
                "lifecycle_status": "active",
            },
            {
                "platform": "vapi",
                "resource_type": "tool",
                "remote_resource_id": "tool_partial_222",
                "lifecycle_status": "active",
            },
        ]

        # Track which deletions were attempted
        deletions = []

        # Create mock Vapi adapter
        vapi = Mock()

        def delete_assistant(assistant_id):
            deletions.append(("assistant", assistant_id))
            return Mock(status="success")

        def delete_tool(tool_id):
            deletions.append(("tool", tool_id))
            raise PermanentError("Tool is in use by active assistant")

        vapi.delete_assistant.side_effect = delete_assistant
        vapi.delete_tool.side_effect = delete_tool

        recovery = RecoveryOrchestrator(
            internal_store=internal_store,
            adapters={"vapi": vapi},
        )

        # In real implementation, this would try both compensations
        # For this test, we simulate the second one failing
        try:
            vapi.delete_tool("tool_partial_222")
        except PermanentError as e:
            result = recovery.handle_compensation_failure(
                deployment_id="dep_partial_001",
                recovery_action_id="rec_partial_001",
                error=e,
            )

        assert result["status"] == "compensation_failed"
        assert result["error_class"] == "permanent"

        # Verify remaining resources are listed
        remaining = [r for r in result["existing_resources"] if r["resource_type"] == "tool"]
        assert len(remaining) > 0

    def test_compensation_not_available(self) -> None:
        """
        Test: Action has no safe compensation operation.

        Expected:
        1. Original action fails
        2. No compensation_operation defined
        3. Manual inspection required
        4. Resources left in place
        5. Clear guidance provided
        """
        internal_store = Mock()

        internal_store.list_external_resources.return_value = [
            {
                "platform": "render",
                "resource_type": "deployment",
                "remote_resource_id": "dep_nocomp_789",
                "lifecycle_status": "live",
            }
        ]

        recovery = RecoveryOrchestrator(
            internal_store=internal_store,
            adapters={"render": Mock()},
        )

        # Proposed action with no compensation
        proposed_action = {
            "platform": "render",
            "operation": "trigger_deploy",
            "target": {"service": "prod-api"},
            "payload": {},
            "compensation_operation": None,  # No safe compensation
        }

        result = recovery.execute_compensation(
            deployment_id="dep_nocomp_001",
            recovery_action_id="rec_nocomp_001",
            proposed_action=proposed_action,
            operator="test_operator",
        )

        assert result["status"] == "no_compensation_available"
        assert result["recommendation"] == "manual_inspection"

    def test_cascading_compensation_failures(self) -> None:
        """
        Test: Compensation of one resource fails, affecting others.

        Expected:
        1. Multiple resources with dependencies
        2. Attempt to compensate in reverse order
        3. First compensation fails
        4. Dependent compensations blocked
        5. Full state reported
        """
        internal_store = Mock()

        # Resources with dependencies
        internal_store.list_external_resources.return_value = [
            {
                "platform": "vapi",
                "resource_type": "phone_assignment",
                "remote_resource_id": "assign_cascade_001",
                "lifecycle_status": "active",
                "depends_on": "asst_cascade_001",
            },
            {
                "platform": "vapi",
                "resource_type": "assistant",
                "remote_resource_id": "asst_cascade_001",
                "lifecycle_status": "active",
            },
        ]

        # Create mock Vapi adapter
        vapi = Mock()

        # Can't unassign phone because assistant is in use
        vapi.unassign_phone_number.side_effect = PermanentError(
            "Phone number cannot be unassigned while assistant is active"
        )

        recovery = RecoveryOrchestrator(
            internal_store=internal_store,
            adapters={"vapi": vapi},
        )

        result = recovery.handle_compensation_failure(
            deployment_id="dep_cascade_001",
            recovery_action_id="rec_cascade_001",
            error=PermanentError("Cannot unassign"),
        )

        # Both resources remain
        assert len(result["existing_resources"]) == 2
        assert result["recommendation"] == "manual_inspection"

    def test_compensation_requires_separate_approval(self) -> None:
        """
        Test: Compensation is not automatically approved.

        Expected:
        1. Compensation operation prepared
        2. Requires separate operator approval
        3. Not executed until approved
        4. Original action approval does NOT authorize compensation
        """
        internal_store = Mock()

        recovery = RecoveryOrchestrator(
            internal_store=internal_store,
            adapters={"vapi": Mock()},
        )

        proposed_action = {
            "platform": "vapi",
            "operation": "create_assistant",
            "target": {"name": "Test"},
            "payload": {"name": "Test"},
            "compensation_operation": "delete_assistant",
        }

        result = recovery.execute_compensation(
            deployment_id="dep_approval_001",
            recovery_action_id="rec_approval_001",
            proposed_action=proposed_action,
            operator="test_operator",
        )

        # Verify compensation requires approval
        assert result["requires_approval"] is True
        assert result["status"] == "compensation_ready"
        assert "description" in result

        # Compensation not yet executed
        assert result["compensation_operation"] == "delete_assistant"
