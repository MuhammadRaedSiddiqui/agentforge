"""
Unit tests for deployment state machine.

Tests for valid and invalid state transitions.
"""

import pytest

from orchestrator.state_machine import DeploymentStateMachine
from shared.errors import StateTransitionError


@pytest.mark.unit
class TestDeploymentStateMachine:
    """Tests for deployment state machine transitions."""

    def test_valid_transition_planning_to_awaiting_plan_approval(self) -> None:
        """Should allow planning -> awaiting_plan_approval."""
        assert DeploymentStateMachine.is_valid_transition("planning", "awaiting_plan_approval")

    def test_valid_transition_awaiting_plan_approval_to_generating(self) -> None:
        """Should allow awaiting_plan_approval -> generating."""
        assert DeploymentStateMachine.is_valid_transition("awaiting_plan_approval", "generating")

    def test_valid_transition_generating_to_awaiting_action_approval(self) -> None:
        """Should allow generating -> awaiting_action_approval."""
        assert DeploymentStateMachine.is_valid_transition("generating", "awaiting_action_approval")

    def test_valid_transition_awaiting_action_to_executing(self) -> None:
        """Should allow awaiting_action_approval -> executing."""
        assert DeploymentStateMachine.is_valid_transition("awaiting_action_approval", "executing")

    def test_valid_transition_executing_to_verifying(self) -> None:
        """Should allow executing -> verifying."""
        assert DeploymentStateMachine.is_valid_transition("executing", "verifying")

    def test_valid_transition_verifying_to_complete(self) -> None:
        """Should allow verifying -> complete."""
        assert DeploymentStateMachine.is_valid_transition("verifying", "complete")

    def test_valid_transition_executing_to_recovery_required(self) -> None:
        """Should allow executing -> recovery_required on failure."""
        assert DeploymentStateMachine.is_valid_transition("executing", "recovery_required")

    def test_valid_transition_recovery_required_to_executing(self) -> None:
        """Should allow recovery_required -> executing for retry."""
        assert DeploymentStateMachine.is_valid_transition("recovery_required", "executing")

    def test_valid_transition_recovery_required_to_compensating(self) -> None:
        """Should allow recovery_required -> compensating."""
        assert DeploymentStateMachine.is_valid_transition("recovery_required", "compensating")

    def test_valid_transition_revision_flow(self) -> None:
        """Should allow awaiting_action_approval -> generating for revision."""
        assert DeploymentStateMachine.is_valid_transition("awaiting_action_approval", "generating")

    def test_valid_transition_abort_from_planning(self) -> None:
        """Should allow aborting from planning."""
        assert DeploymentStateMachine.is_valid_transition("planning", "aborted")

    def test_invalid_transition_planning_to_executing(self) -> None:
        """Should not allow planning -> executing (skips steps)."""
        assert not DeploymentStateMachine.is_valid_transition("planning", "executing")

    def test_invalid_transition_complete_to_anything(self) -> None:
        """Should not allow transitions from complete (terminal)."""
        assert not DeploymentStateMachine.is_valid_transition("complete", "executing")
        assert not DeploymentStateMachine.is_valid_transition("complete", "planning")

    def test_invalid_transition_failed_to_anything(self) -> None:
        """Should not allow transitions from failed (terminal)."""
        assert not DeploymentStateMachine.is_valid_transition("failed", "executing")
        assert not DeploymentStateMachine.is_valid_transition("failed", "recovery_required")

    def test_invalid_transition_aborted_to_anything(self) -> None:
        """Should not allow transitions from aborted (terminal)."""
        assert not DeploymentStateMachine.is_valid_transition("aborted", "planning")

    def test_validate_transition_success(self) -> None:
        """validate_transition should not raise for valid transitions."""
        # Should not raise
        DeploymentStateMachine.validate_transition("planning", "awaiting_plan_approval")

    def test_validate_transition_same_state(self) -> None:
        """validate_transition should allow same state (no-op)."""
        # Should not raise
        DeploymentStateMachine.validate_transition("planning", "planning")

    def test_validate_transition_failure(self) -> None:
        """validate_transition should raise for invalid transitions."""
        with pytest.raises(StateTransitionError) as exc_info:
            DeploymentStateMachine.validate_transition("planning", "executing")

        assert "Invalid transition" in str(exc_info.value)
        assert "planning" in str(exc_info.value)
        assert "executing" in str(exc_info.value)

    def test_validate_transition_from_terminal_state(self) -> None:
        """validate_transition should indicate terminal state."""
        with pytest.raises(StateTransitionError) as exc_info:
            DeploymentStateMachine.validate_transition("complete", "executing")

        assert "terminal" in str(exc_info.value).lower()

    def test_get_valid_next_states_planning(self) -> None:
        """Should return correct next states for planning."""
        next_states = DeploymentStateMachine.get_valid_next_states("planning")

        assert "awaiting_plan_approval" in next_states
        assert "aborted" in next_states
        assert len(next_states) == 2

    def test_get_valid_next_states_terminal(self) -> None:
        """Should return empty list for terminal states."""
        assert DeploymentStateMachine.get_valid_next_states("complete") == []
        assert DeploymentStateMachine.get_valid_next_states("failed") == []
        assert DeploymentStateMachine.get_valid_next_states("aborted") == []

    def test_is_terminal_states(self) -> None:
        """Should correctly identify terminal states."""
        assert DeploymentStateMachine.is_terminal("complete")
        assert DeploymentStateMachine.is_terminal("failed")
        assert DeploymentStateMachine.is_terminal("aborted")
        assert not DeploymentStateMachine.is_terminal("planning")
        assert not DeploymentStateMachine.is_terminal("executing")

    def test_requires_recovery_states(self) -> None:
        """Should correctly identify recovery states."""
        assert DeploymentStateMachine.requires_recovery("partial")
        assert DeploymentStateMachine.requires_recovery("recovery_required")
        assert DeploymentStateMachine.requires_recovery("compensating")
        assert not DeploymentStateMachine.requires_recovery("planning")
        assert not DeploymentStateMachine.requires_recovery("complete")

    def test_is_modifying_states(self) -> None:
        """Should correctly identify modifying states."""
        assert DeploymentStateMachine.is_modifying("planning")
        assert DeploymentStateMachine.is_modifying("generating")
        assert DeploymentStateMachine.is_modifying("executing")
        assert not DeploymentStateMachine.is_modifying("complete")
        assert not DeploymentStateMachine.is_modifying("failed")

    def test_can_start_new_deployment_status_only(self) -> None:
        """Should always allow status_only deployments."""
        assert DeploymentStateMachine.can_start_new_deployment("executing", "status_only")
        assert DeploymentStateMachine.can_start_new_deployment("complete", "status_only")

    def test_can_start_new_deployment_recovery_only(self) -> None:
        """Should allow recovery_only in recovery states."""
        assert DeploymentStateMachine.can_start_new_deployment("recovery_required", "recovery_only")
        assert not DeploymentStateMachine.can_start_new_deployment("complete", "recovery_only")

    def test_can_start_new_deployment_modifying_blocked(self) -> None:
        """Should block new modifying deployments when one is active."""
        assert not DeploymentStateMachine.can_start_new_deployment("executing", "new_onboarding")
        assert not DeploymentStateMachine.can_start_new_deployment("generating", "update_assistant")

    def test_can_start_new_deployment_after_terminal(self) -> None:
        """Should allow new deployments after terminal state."""
        assert DeploymentStateMachine.can_start_new_deployment("complete", "new_onboarding")
        assert DeploymentStateMachine.can_start_new_deployment("failed", "new_onboarding")

    def test_get_state_description(self) -> None:
        """Should return human-readable descriptions."""
        desc = DeploymentStateMachine.get_state_description("planning")
        assert len(desc) > 0
        assert "plan" in desc.lower()

        desc = DeploymentStateMachine.get_state_description("complete")
        assert "complete" in desc.lower()

    def test_visualize_state_machine(self) -> None:
        """Should generate state machine visualization."""
        viz = DeploymentStateMachine.visualize_state_machine()

        assert "planning" in viz
        assert "complete" in viz
        assert "→" in viz
        assert "TERMINAL" in viz


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
