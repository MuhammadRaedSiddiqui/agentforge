"""
Failure injection test: concurrent modification of a remote resource.

Injects the case the staleness check exists for: an update action is planned
against remote state, someone edits that resource in the platform's own
dashboard, and the action then reaches the write. Before staleness detection was
implemented the write went through silently, overwriting the other edit.

Covers the drift decision paths (proceed / abort / revise), the auto-approve
guard, and the case where the remote read itself fails.
"""

from typing import Any
from unittest.mock import Mock

import pytest

from orchestrator.approval import build_proposed_action
from orchestrator.current_state_reader import StaleStateReadError
from orchestrator.orchestrator import Orchestrator
from shared.hashing import compute_state_version

BASELINE: dict[str, Any] = {
    "name": "Solara Dental",
    "model": {"model": "gpt-4"},
    "voice": {"voiceId": "Elliot"},
    "first_message": "Hi, thanks for calling.",
}

# What the assistant looks like after someone renames it in the Vapi dashboard.
DRIFTED: dict[str, Any] = {**BASELINE, "name": "Solara Dental - DO NOT TOUCH"}


def _update_action():
    return build_proposed_action(
        platform="vapi",
        operation="update_assistant",
        target="assistant/test_org",
        payload={"assistant_id": "asst-123", "updates": {"first_message": "New greeting"}},
        state_version=compute_state_version(BASELINE),
        baseline_state=BASELINE,
        retry_policy="none",
        reconciliation_strategy="read_after_write",
        expected_outcome="Update Vapi assistant for test_org",
    )


def _orchestrator(remote_state: dict[str, Any] | Exception) -> tuple[Orchestrator, Mock]:
    internal_store = Mock()
    internal_store.get_deployment.return_value = {
        "deployment_id": "dep_001",
        "organization_id": "test_org",
        "status": "executing",
        "plan": {"actions": []},
    }

    orchestrator = Orchestrator(internal_store)

    reader = Mock()
    if isinstance(remote_state, Exception):
        reader.read_staleness_state = Mock(side_effect=remote_state)
    else:
        reader.read_staleness_state = Mock(return_value=remote_state)
    orchestrator._state_reader = reader

    return orchestrator, internal_store


def _execute(orchestrator: Orchestrator, auto_approve: bool = False) -> dict[str, Any]:
    return orchestrator.execute_deployment(
        deployment_id="dep_001",
        organization_id="test_org",
        operator="test_operator",
        dry_run=False,
        auto_approve=auto_approve,
        proposed_actions=[_update_action()],
    )


@pytest.mark.failure_injection
class TestConcurrentModification:
    def test_unchanged_remote_state_executes_without_prompting(self) -> None:
        """No drift: the operator is never asked about staleness."""
        orchestrator, _ = _orchestrator(BASELINE)
        orchestrator.prompts.approve_action = Mock(return_value="approved")
        orchestrator.prompts.choose_recovery_option = Mock()
        orchestrator._execute_action = Mock(return_value={"status": "success"})

        result = _execute(orchestrator)

        assert result["status"] == "completed"
        orchestrator.prompts.choose_recovery_option.assert_not_called()
        orchestrator._execute_action.assert_called_once()

    def test_drift_aborts_when_operator_declines(self) -> None:
        """The overwrite this feature exists to prevent does not happen."""
        orchestrator, _ = _orchestrator(DRIFTED)
        orchestrator.prompts.choose_recovery_option = Mock(return_value="abort")
        orchestrator.prompts.approve_action = Mock(return_value="approved")
        orchestrator._execute_action = Mock()
        orchestrator._abort_deployment = Mock()

        result = _execute(orchestrator)

        assert result["status"] == "aborted"
        orchestrator._execute_action.assert_not_called()
        orchestrator._abort_deployment.assert_called_once()

    def test_drift_is_shown_to_the_operator(self, capsys: pytest.CaptureFixture) -> None:
        """The operator sees which field changed, not just that a hash differs."""
        orchestrator, _ = _orchestrator(DRIFTED)
        orchestrator.prompts.choose_recovery_option = Mock(return_value="abort")
        orchestrator._abort_deployment = Mock()

        _execute(orchestrator)

        output = capsys.readouterr().out
        assert "name" in output
        assert "Solara Dental - DO NOT TOUCH" in output

    def test_drift_detection_is_audited(self) -> None:
        """The drift itself is auditable, separately from the operator's answer."""
        orchestrator, internal_store = _orchestrator(DRIFTED)
        orchestrator.prompts.choose_recovery_option = Mock(return_value="abort")
        orchestrator._abort_deployment = Mock()

        _execute(orchestrator)

        stale_events = [
            call.kwargs
            for call in internal_store.append_audit_event.call_args_list
            if call.kwargs.get("status") == "stale_detected"
        ]
        assert len(stale_events) == 1
        assert stale_events[0]["detail"]["drifted_fields"] == ["name"]
        assert stale_events[0]["detail"]["operation"] == "update_assistant"

    def test_proceed_rebinds_the_action_to_current_state(self) -> None:
        """Proceeding overwrites knowingly, and re-binds approval to what is there now."""
        orchestrator, _ = _orchestrator(DRIFTED)
        orchestrator.prompts.choose_recovery_option = Mock(return_value="proceed")
        orchestrator.prompts.approve_action = Mock(return_value="approved")
        executed = []
        orchestrator._execute_action = Mock(
            side_effect=lambda **kw: executed.append(kw) or {"status": "success"}
        )

        result = _execute(orchestrator)

        assert result["status"] == "completed"
        action = executed[0]["proposed_action"]
        # Rebound to the drifted state, so a second concurrent edit between the
        # prompt and the write would still be caught.
        assert action.state_version == compute_state_version(DRIFTED)
        assert action.baseline_state == DRIFTED
        # The payload the operator approved is unchanged.
        assert action.payload["updates"] == {"first_message": "New greeting"}

    def test_revise_stops_without_writing(self) -> None:
        orchestrator, _ = _orchestrator(DRIFTED)
        orchestrator.prompts.choose_recovery_option = Mock(return_value="revise")
        orchestrator.prompts.get_revision_instruction = Mock(return_value="re-plan this")
        orchestrator._mark_for_revision = Mock()
        orchestrator._execute_action = Mock()

        result = _execute(orchestrator)

        assert result["status"] == "aborted"
        orchestrator._execute_action.assert_not_called()
        orchestrator._mark_for_revision.assert_called_once()

    def test_auto_approve_aborts_on_drift_instead_of_proceeding(self) -> None:
        """
        Auto-approve exists for CI, where nobody is watching. Letting it answer
        'proceed' would reinstate the silent overwrite under a flag.
        """
        orchestrator, _ = _orchestrator(DRIFTED)
        orchestrator.prompts.choose_recovery_option = Mock()
        orchestrator.prompts.approve_action = Mock(return_value="approved")
        orchestrator._execute_action = Mock()
        orchestrator._abort_deployment = Mock()

        result = _execute(orchestrator, auto_approve=True)

        assert result["status"] == "aborted"
        orchestrator._execute_action.assert_not_called()
        # It must not even ask; there is no operator to answer.
        orchestrator.prompts.choose_recovery_option.assert_not_called()

    def test_unreadable_remote_state_does_not_execute(self) -> None:
        """Unknown state is not unchanged state — the write must not proceed."""
        orchestrator, _ = _orchestrator(StaleStateReadError("vapi unreachable"))
        orchestrator.prompts.approve_action = Mock(return_value="approved")
        orchestrator._execute_action = Mock()

        with pytest.raises(StaleStateReadError):
            _execute(orchestrator)

        orchestrator._execute_action.assert_not_called()
