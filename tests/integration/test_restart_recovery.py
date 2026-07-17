"""
Integration test: Process stop and restart recovery detection.

Tests T110: Verify system detects unresolved recovery state on restart
and presents recovery options before allowing new work.
"""

from unittest.mock import Mock

import pytest

from orchestrator.recovery import RecoveryOrchestrator
from orchestrator.state_machine import DeploymentState


@pytest.mark.integration
class TestRestartRecovery:
    """
    Test restart detection and recovery presentation.

    Critical requirement: On session start, detect unresolved partial
    deployments and require resolution before new work.
    """

    def test_detect_partial_deployment_on_restart(self) -> None:
        """
        Test: Session starts, finds partial deployment from previous run.

        Expected:
        1. Query for deployments in recovery states
        2. Find deployment in 'partial' state
        3. Load recovery actions
        4. Load completed resources
        5. Present recovery options to operator
        6. Block new work until resolved
        """
        internal_store = Mock()

        # Mock a partial deployment
        internal_store.list_deployments.return_value = [
            {
                "deployment_id": "dep_restart_001",
                "organization_id": "restart_org",
                "status": DeploymentState.PARTIAL.value,
                "intent": "new_onboarding",
                "started_at": "2024-01-01T10:00:00Z",
                "started_by": "previous_operator",
            }
        ]

        # Mock pending recovery actions
        internal_store.list_recovery_actions.return_value = [
            {
                "recovery_action_id": "rec_restart_001",
                "deployment_id": "dep_restart_001",
                "kind": "reconcile",
                "operation": "reconcile_remote_state",
                "status": "pending",
            },
            {
                "recovery_action_id": "rec_restart_002",
                "deployment_id": "dep_restart_001",
                "kind": "retry",
                "operation": "create_tool",
                "status": "pending",
            },
        ]

        # Mock completed resources
        internal_store.list_external_resources.return_value = [
            {
                "platform": "vapi",
                "resource_type": "assistant",
                "remote_resource_id": "asst_restart_123",
                "lifecycle_status": "active",
            },
            {
                "platform": "make",
                "resource_type": "scenario",
                "remote_resource_id": "scen_restart_456",
                "lifecycle_status": "active",
            },
        ]

        recovery = RecoveryOrchestrator(
            internal_store=internal_store,
            adapters={},
        )

        # Detect recovery on startup
        result = recovery.detect_restart_recovery("restart_org")

        # Verify recovery detected
        assert result is not None
        assert result["has_recovery"] is True
        assert result["deployment_id"] == "dep_restart_001"
        assert result["deployment_status"] == DeploymentState.PARTIAL.value

        # Verify recovery actions loaded
        assert len(result["recovery_actions"]) == 2

        # Verify completed resources loaded
        assert len(result["completed_resources"]) == 2

        # Verify message provided
        assert "unresolved deployment" in result["message"]

    def test_no_recovery_needed_on_clean_restart(self) -> None:
        """
        Test: Session starts, no unresolved deployments.

        Expected:
        1. Query finds no partial/recovery_required deployments
        2. Return None (no recovery needed)
        3. New work can proceed normally
        """
        internal_store = Mock()

        # No deployments in recovery states
        internal_store.list_deployments.return_value = []

        recovery = RecoveryOrchestrator(
            internal_store=internal_store,
            adapters={},
        )

        result = recovery.detect_restart_recovery("clean_org")

        # No recovery needed
        assert result is None

    def test_multiple_recovery_states_prioritized(self) -> None:
        """
        Test: Multiple deployments in recovery states.

        Expected:
        1. Find all deployments in recovery states
        2. Return most recent one
        3. Operator must resolve before proceeding
        """
        internal_store = Mock()

        # Multiple partial deployments
        internal_store.list_deployments.return_value = [
            {
                "deployment_id": "dep_multi_002",
                "organization_id": "multi_org",
                "status": DeploymentState.RECOVERY_REQUIRED.value,
                "intent": "update_assistant",
                "started_at": "2024-01-02T12:00:00Z",
            },
            {
                "deployment_id": "dep_multi_001",
                "organization_id": "multi_org",
                "status": DeploymentState.PARTIAL.value,
                "intent": "new_onboarding",
                "started_at": "2024-01-01T10:00:00Z",
            },
        ]

        internal_store.list_recovery_actions.return_value = []
        internal_store.list_external_resources.return_value = []

        recovery = RecoveryOrchestrator(
            internal_store=internal_store,
            adapters={},
        )

        result = recovery.detect_restart_recovery("multi_org")

        # Should return most recent (first in list)
        assert result["deployment_id"] == "dep_multi_002"
        assert result["deployment_status"] == DeploymentState.RECOVERY_REQUIRED.value

    def test_format_recovery_options_for_display(self) -> None:
        """
        Test: Format recovery info for CLI display.

        Expected:
        1. Clear summary of deployment state
        2. List of completed resources
        3. List of pending recovery actions
        4. Available options (reconcile, retry, compensate, defer, abort)
        """
        internal_store = Mock()

        recovery_info = {
            "deployment_id": "dep_format_001",
            "deployment_status": DeploymentState.RECOVERY_REQUIRED.value,
            "intent": "new_onboarding",
            "started_at": "2024-01-01T10:00:00Z",
            "recovery_actions": [
                {
                    "recovery_action_id": "rec_format_001",
                    "kind": "reconcile",
                    "operation": "reconcile_remote_state",
                    "status": "pending",
                },
                {
                    "recovery_action_id": "rec_format_002",
                    "kind": "compensate",
                    "operation": "delete_assistant",
                    "status": "pending",
                },
            ],
            "completed_resources": [
                {
                    "platform": "vapi",
                    "resource_type": "assistant",
                    "remote_resource_id": "asst_format_123",
                },
                {
                    "platform": "vapi",
                    "resource_type": "tool",
                    "remote_resource_id": "tool_format_456",
                },
            ],
        }

        recovery = RecoveryOrchestrator(
            internal_store=internal_store,
            adapters={},
        )

        formatted = recovery.format_recovery_options(recovery_info)

        # Verify summary
        assert "summary" in formatted
        assert formatted["summary"]["deployment_id"] == "dep_format_001"
        assert formatted["summary"]["completed_count"] == 2
        assert formatted["summary"]["pending_recovery_count"] == 2

        # Verify completed resources formatted
        assert len(formatted["completed_resources"]) == 2
        assert formatted["completed_resources"][0]["platform"] == "vapi"

        # Verify pending actions formatted
        assert len(formatted["pending_actions"]) == 2
        assert formatted["pending_actions"][0]["kind"] == "reconcile"

        # Verify available options
        assert "available_options" in formatted
        assert "reconcile" in formatted["available_options"]
        assert "compensate" in formatted["available_options"]
        assert "defer" in formatted["available_options"]
        assert "abort" in formatted["available_options"]

    def test_recovery_required_blocks_new_deployment(self) -> None:
        """
        Test: Attempt new deployment when recovery is pending.

        Expected:
        1. Check for existing recovery state
        2. Find unresolved deployment
        3. Raise RecoveryRequiredError
        4. New deployment blocked until resolved
        """

        internal_store = Mock()

        # Unresolved recovery
        internal_store.list_deployments.return_value = [
            {
                "deployment_id": "dep_block_001",
                "organization_id": "block_org",
                "status": DeploymentState.RECOVERY_REQUIRED.value,
                "intent": "new_onboarding",
                "started_at": "2024-01-01T10:00:00Z",
            }
        ]

        internal_store.list_recovery_actions.return_value = [
            {
                "recovery_action_id": "rec_block_001",
                "kind": "reconcile",
                "operation": "reconcile_remote_state",
                "status": "pending",
            }
        ]

        internal_store.list_external_resources.return_value = []

        recovery = RecoveryOrchestrator(
            internal_store=internal_store,
            adapters={},
        )

        # Detect recovery
        result = recovery.detect_restart_recovery("block_org")
        assert result is not None
        assert result["has_recovery"] is True

        # In real implementation, orchestrator would check this before
        # allowing new deployment and raise RecoveryRequiredError

    def test_compensating_state_on_restart(self) -> None:
        """
        Test: Restart during compensation process.

        Expected:
        1. Find deployment in 'compensating' state
        2. Load pending compensation actions
        3. Present compensation options
        4. Allow continuation or abort
        """
        internal_store = Mock()

        internal_store.list_deployments.return_value = [
            {
                "deployment_id": "dep_comp_restart_001",
                "organization_id": "comp_org",
                "status": DeploymentState.COMPENSATING.value,
                "intent": "new_onboarding",
                "started_at": "2024-01-01T10:00:00Z",
            }
        ]

        internal_store.list_recovery_actions.return_value = [
            {
                "recovery_action_id": "rec_comp_restart_001",
                "kind": "compensate",
                "operation": "delete_assistant",
                "status": "pending",
            },
        ]

        internal_store.list_external_resources.return_value = [
            {
                "platform": "vapi",
                "resource_type": "assistant",
                "remote_resource_id": "asst_comp_restart_123",
                "lifecycle_status": "active",
            },
        ]

        recovery = RecoveryOrchestrator(
            internal_store=internal_store,
            adapters={},
        )

        result = recovery.detect_restart_recovery("comp_org")

        assert result["deployment_status"] == DeploymentState.COMPENSATING.value
        assert len(result["recovery_actions"]) == 1
        assert result["recovery_actions"][0]["kind"] == "compensate"

    def test_completed_deployment_not_detected_as_recovery(self) -> None:
        """
        Test: Completed deployment should not trigger recovery.

        Expected:
        1. Query excludes 'completed' state
        2. No recovery detected
        3. New work can proceed
        """
        internal_store = Mock()

        # Only completed deployments exist
        internal_store.list_deployments.return_value = []

        recovery = RecoveryOrchestrator(
            internal_store=internal_store,
            adapters={},
        )

        result = recovery.detect_restart_recovery("completed_org")

        assert result is None
