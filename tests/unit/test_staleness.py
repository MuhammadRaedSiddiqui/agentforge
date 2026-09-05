"""
Unit tests for staleness detection.

Before this was implemented, `_read_current_state` returned None unconditionally
and `_build_update_actions` never set a state_version, so `check_staleness()`
always took its early-exit `return False`: a concurrent dashboard edit was
silently overwritten. These tests pin the behavior that replaced it.

The false-positive cases matter as much as the true-positive ones. Drift
detection that fires on every run trains operators to click through it.
"""

from typing import Any
from unittest.mock import Mock

import pytest

from orchestrator.approval import build_proposed_action, check_staleness
from orchestrator.current_state_reader import CurrentStateReader, StaleStateReadError
from orchestrator.orchestrator import Orchestrator
from shared.errors import TransientError
from shared.hashing import compute_state_version

pytestmark = pytest.mark.unit


VAPI_BASELINE: dict[str, Any] = {
    "name": "Solara Dental",
    "model": {"provider": "openai", "model": "gpt-4"},
    "voice": {"provider": "vapi", "voiceId": "Elliot"},
    "first_message": "Hi, thanks for calling.",
}


def _update_action(state: dict[str, Any] | None = None):
    baseline = VAPI_BASELINE if state is None else state
    return build_proposed_action(
        platform="vapi",
        operation="update_assistant",
        target="assistant/test_org",
        payload={"assistant_id": "asst-123", "updates": {"name": "New Name"}},
        state_version=compute_state_version(baseline),
        baseline_state=baseline,
        expected_outcome="Update assistant",
    )


def _create_action():
    return build_proposed_action(
        platform="vapi",
        operation="create_assistant",
        target="assistant/test_org",
        payload={"name": "test-assistant"},
        expected_outcome="Create assistant",
    )


def _orchestrator_with_state(state: dict[str, Any] | Exception) -> Orchestrator:
    orch = Orchestrator(Mock())
    reader = Mock()
    if isinstance(state, Exception):
        reader.read_staleness_state = Mock(side_effect=state)
    else:
        reader.read_staleness_state = Mock(return_value=state)
    orch._state_reader = reader
    return orch


class TestCheckStaleness:
    def test_create_action_is_never_stale(self) -> None:
        # Creates have no prior state to be stale against.
        assert check_staleness(_create_action(), None) is False

    def test_unchanged_remote_state_is_not_stale(self) -> None:
        action = _update_action()
        assert check_staleness(action, compute_state_version(VAPI_BASELINE)) is False

    def test_changed_remote_state_is_stale(self) -> None:
        action = _update_action()
        drifted = {**VAPI_BASELINE, "name": "Renamed In Dashboard"}
        assert check_staleness(action, compute_state_version(drifted)) is True


class TestOrchestratorStalenessCheck:
    def test_create_action_skips_the_remote_read(self) -> None:
        orch = _orchestrator_with_state(VAPI_BASELINE)
        assert orch._check_staleness_for_action(_create_action()) is None
        orch.state_reader.read_staleness_state.assert_not_called()

    def test_unchanged_state_reports_not_stale(self) -> None:
        orch = _orchestrator_with_state(VAPI_BASELINE)
        assert orch._is_action_stale(_update_action()) is False

    def test_concurrent_edit_is_detected(self) -> None:
        orch = _orchestrator_with_state({**VAPI_BASELINE, "voice": {"voiceId": "Rohan"}})
        assert orch._is_action_stale(_update_action()) is True

    def test_reads_the_id_from_the_action_payload(self) -> None:
        orch = _orchestrator_with_state(VAPI_BASELINE)
        orch._check_staleness_for_action(_update_action())
        orch.state_reader.read_staleness_state.assert_called_once_with(
            "vapi", "assistant", "asst-123"
        )

    def test_read_failure_is_surfaced_not_swallowed(self) -> None:
        # Unknown state must not be reported as unchanged: that is precisely
        # the bug this feature exists to fix.
        orch = _orchestrator_with_state(StaleStateReadError("vapi unreachable"))
        with pytest.raises(StaleStateReadError):
            orch._is_action_stale(_update_action())

    def test_action_without_a_known_staleness_target_is_rejected(self) -> None:
        orch = _orchestrator_with_state(VAPI_BASELINE)
        action = build_proposed_action(
            platform="supabase_client",
            operation="update_org_record",
            target="organizations/test_org",
            payload={"organization_id": "test_org"},
            state_version="deadbeef",
            baseline_state={"name": "x"},
        )
        with pytest.raises(StaleStateReadError):
            orch._is_action_stale(action)

    def test_action_missing_its_remote_id_is_rejected(self) -> None:
        orch = _orchestrator_with_state(VAPI_BASELINE)
        action = build_proposed_action(
            platform="vapi",
            operation="update_assistant",
            target="assistant/test_org",
            payload={"updates": {"name": "New"}},  # no assistant_id
            state_version="deadbeef",
            baseline_state=VAPI_BASELINE,
        )
        with pytest.raises(StaleStateReadError):
            orch._is_action_stale(action)


class TestReadStalenessState:
    def _reader(self) -> CurrentStateReader:
        reader = object.__new__(CurrentStateReader)
        reader.vapi = Mock()
        reader.make = Mock()
        return reader

    def test_vapi_projection_shape(self) -> None:
        reader = self._reader()
        reader.vapi.get_assistant = Mock(
            return_value=Mock(
                status="success",
                response_data={
                    "name": "Solara",
                    "model": {"model": "gpt-4"},
                    "voice": {"voiceId": "Elliot"},
                    "firstMessage": "Hello",
                    "createdAt": "2026-01-01T00:00:00Z",
                },
            )
        )
        state = reader.read_staleness_state("vapi", "assistant", "asst-1")

        assert state == {
            "name": "Solara",
            "model": {"model": "gpt-4"},
            "voice": {"voiceId": "Elliot"},
            "first_message": "Hello",
        }
        # Timestamps move on their own and must stay out of the hash.
        assert "createdAt" not in state

    def test_make_projection_excludes_volatile_fields(self) -> None:
        reader = self._reader()
        reader.make.get_scenario = Mock(
            return_value=Mock(
                status="success",
                # isActive and scheduling change as the scenario runs.
                response_data={"name": "booking", "isActive": True, "scheduling": {}},
            )
        )
        reader.make.get_scenario_blueprint = Mock(
            return_value=Mock(
                status="success",
                response_data={
                    "blueprint": {
                        "name": "booking",
                        "flow": [{"id": 1}],
                        # Payload-level fields Make returns on GET; see
                        # knowledge-base/gotchas/make-blueprint-strip-metadata.md
                        "teamId": 12345,
                        "scheduling": {"type": "immediately"},
                        "description": "whatever",
                    }
                },
            )
        )
        state = reader.read_staleness_state("make", "scenario", "42")

        assert state["name"] == "booking"
        assert state["blueprint"] == {"name": "booking", "flow": [{"id": 1}]}
        assert "is_active" not in state

    def test_make_scenario_hash_is_stable_across_activity(self) -> None:
        # A scenario that has simply been running must not report drift.
        reader = self._reader()
        blueprint = {"name": "booking", "flow": [{"id": 1}]}

        def scenario(is_active: bool) -> Mock:
            return Mock(
                status="success",
                response_data={
                    "name": "booking",
                    "isActive": is_active,
                    "scheduling": {"type": "immediately" if is_active else "indefinitely"},
                },
            )

        reader.make.get_scenario_blueprint = Mock(
            return_value=Mock(status="success", response_data={"blueprint": dict(blueprint)})
        )

        reader.make.get_scenario = Mock(return_value=scenario(True))
        first = reader.read_staleness_version("make", "scenario", "42")

        reader.make.get_scenario = Mock(return_value=scenario(False))
        second = reader.read_staleness_version("make", "scenario", "42")

        assert first == second

    def test_adapter_error_becomes_stale_state_read_error(self) -> None:
        reader = self._reader()
        reader.vapi.get_assistant = Mock(side_effect=TransientError("HTTP 503"))
        with pytest.raises(StaleStateReadError):
            reader.read_staleness_state("vapi", "assistant", "asst-1")

    def test_non_success_receipt_becomes_stale_state_read_error(self) -> None:
        reader = self._reader()
        reader.vapi.get_assistant = Mock(return_value=Mock(status="failed", response_data={}))
        with pytest.raises(StaleStateReadError):
            reader.read_staleness_state("vapi", "assistant", "asst-1")

    def test_undefined_projection_is_an_error_not_an_empty_dict(self) -> None:
        reader = self._reader()
        with pytest.raises(StaleStateReadError):
            reader.read_staleness_state("render", "deploy", "dep-1")
