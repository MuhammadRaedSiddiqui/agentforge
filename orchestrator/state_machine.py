"""
Deployment state machine for Agent Forge.

Enforces valid state transitions and rejects illegal transitions.
"""

from typing import Dict, List, Optional, Set

from shared.errors import StateTransitionError


class DeploymentStateMachine:
    """
    State machine for deployment lifecycle.

    Enforces valid state transitions and provides clear error messages
    for illegal transitions.
    """

    # Define valid state transitions
    VALID_TRANSITIONS: Dict[str, Set[str]] = {
        "planning": {
            "awaiting_plan_approval",
            "aborted",
        },
        "awaiting_plan_approval": {
            "generating",
            "aborted",
        },
        "generating": {
            "awaiting_action_approval",
            "failed",
            "aborted",
        },
        "awaiting_action_approval": {
            "executing",
            "generating",  # revision requested
            "aborted",
        },
        "executing": {
            "awaiting_action_approval",  # more actions needed
            "verifying",
            "partial",
            "recovery_required",
            "failed",
        },
        "partial": {
            "recovery_required",
        },
        "recovery_required": {
            "executing",  # targeted retry
            "compensating",
            "aborted",  # only when no unresolved live state remains
        },
        "compensating": {
            "failed",  # compensation completed, original deployment failed
            "recovery_required",  # compensation failed or state remains
        },
        "verifying": {
            "complete",
            "recovery_required",
            "failed",
        },
        # Terminal states have no outgoing transitions
        "complete": set(),
        "failed": set(),
        "aborted": set(),
    }

    # Terminal states (no further transitions possible)
    TERMINAL_STATES = {"complete", "failed", "aborted"}

    # States requiring recovery
    RECOVERY_STATES = {"partial", "recovery_required", "compensating"}

    # States where modifications are happening
    MODIFYING_STATES = {
        "planning",
        "awaiting_plan_approval",
        "generating",
        "awaiting_action_approval",
        "executing",
        "verifying",
        "partial",
        "recovery_required",
        "compensating",
    }

    @staticmethod
    def is_valid_transition(current_state: str, new_state: str) -> bool:
        """
        Check if a state transition is valid.

        Args:
            current_state: Current deployment state
            new_state: Proposed new state

        Returns:
            True if transition is valid, False otherwise
        """
        if current_state not in DeploymentStateMachine.VALID_TRANSITIONS:
            return False

        valid_next_states = DeploymentStateMachine.VALID_TRANSITIONS[current_state]
        return new_state in valid_next_states

    @staticmethod
    def validate_transition(current_state: str, new_state: str) -> None:
        """
        Validate a state transition and raise an error if invalid.

        Args:
            current_state: Current deployment state
            new_state: Proposed new state

        Raises:
            StateTransitionError: If transition is not valid
        """
        if current_state == new_state:
            # No transition needed
            return

        if not DeploymentStateMachine.is_valid_transition(current_state, new_state):
            valid_next_states = DeploymentStateMachine.VALID_TRANSITIONS.get(
                current_state, set()
            )

            if not valid_next_states:
                raise StateTransitionError(
                    f"State '{current_state}' is terminal. Cannot transition to '{new_state}'."
                )

            raise StateTransitionError(
                f"Invalid transition from '{current_state}' to '{new_state}'. "
                f"Valid next states: {', '.join(sorted(valid_next_states))}"
            )

    @staticmethod
    def get_valid_next_states(current_state: str) -> List[str]:
        """
        Get list of valid next states from current state.

        Args:
            current_state: Current deployment state

        Returns:
            List of valid next state names (sorted)
        """
        valid_states = DeploymentStateMachine.VALID_TRANSITIONS.get(current_state, set())
        return sorted(valid_states)

    @staticmethod
    def is_terminal(state: str) -> bool:
        """
        Check if a state is terminal (no further transitions possible).

        Args:
            state: State to check

        Returns:
            True if state is terminal
        """
        return state in DeploymentStateMachine.TERMINAL_STATES

    @staticmethod
    def requires_recovery(state: str) -> bool:
        """
        Check if a state requires recovery actions.

        Args:
            state: State to check

        Returns:
            True if state requires recovery
        """
        return state in DeploymentStateMachine.RECOVERY_STATES

    @staticmethod
    def is_modifying(state: str) -> bool:
        """
        Check if a state represents active modification.

        Args:
            state: State to check

        Returns:
            True if state is a modifying state
        """
        return state in DeploymentStateMachine.MODIFYING_STATES

    @staticmethod
    def can_start_new_deployment(state: str, intent: str) -> bool:
        """
        Check if a new deployment can start given current state and intent.

        Args:
            state: Current deployment state
            intent: Proposed deployment intent

        Returns:
            True if new deployment can start
        """
        # Can always start status_only deployments
        if intent == "status_only":
            return True

        # Can start recovery_only if in recovery state
        if intent == "recovery_only":
            return DeploymentStateMachine.requires_recovery(state)

        # For modifying intents, must be in terminal state or no deployment exists
        if DeploymentStateMachine.is_modifying(state):
            return False

        return True

    @staticmethod
    def get_state_description(state: str) -> str:
        """
        Get human-readable description of a state.

        Args:
            state: State name

        Returns:
            Description string
        """
        descriptions = {
            "planning": "Building deployment plan",
            "awaiting_plan_approval": "Waiting for operator to approve plan",
            "generating": "Generating deployment artifacts",
            "awaiting_action_approval": "Waiting for operator to approve action",
            "executing": "Executing approved action",
            "verifying": "Verifying deployment health",
            "partial": "Deployment partially complete",
            "recovery_required": "Recovery actions required",
            "compensating": "Executing compensation actions",
            "complete": "Deployment complete",
            "failed": "Deployment failed",
            "aborted": "Deployment aborted",
        }

        return descriptions.get(state, f"Unknown state: {state}")

    @staticmethod
    def visualize_state_machine() -> str:
        """
        Generate a text visualization of the state machine.

        Returns:
            Multi-line string showing state transitions
        """
        lines = ["Deployment State Machine:", "=" * 50, ""]

        for state in sorted(DeploymentStateMachine.VALID_TRANSITIONS.keys()):
            next_states = DeploymentStateMachine.get_valid_next_states(state)

            terminal_marker = " [TERMINAL]" if DeploymentStateMachine.is_terminal(state) else ""
            recovery_marker = " [RECOVERY]" if DeploymentStateMachine.requires_recovery(state) else ""

            lines.append(f"{state}{terminal_marker}{recovery_marker}")

            if next_states:
                for next_state in next_states:
                    lines.append(f"  → {next_state}")
            else:
                lines.append("  (no outgoing transitions)")

            lines.append("")

        return "\n".join(lines)
