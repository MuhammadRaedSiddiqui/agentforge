"""
Unit tests for orchestrator/deployment_verifier.py.

These encode the failure that motivated the module: a deployment reported
"8 of 8 actions", every receipt was green, and the client had no tools
attached and a phone number bound to somebody else's assistant. The point of
verification is that the deployment must fail in exactly that situation, so
most of these assert that a *successful-looking* deployment is rejected.
"""

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from orchestrator.approval import build_proposed_action
from orchestrator.deployment_verifier import (
    expected_tool_count,
    verify_onboarding,
)

pytestmark = pytest.mark.unit

ASSISTANT_ID = "asst-1"
PHONE_ID = "phone-1"


def _config(tmp_path: Any, tools: int) -> str:
    path = tmp_path / "assistant_config.json"
    path.write_text(
        json.dumps({"name": "A", "tools": [{"function": {"name": f"t{i}"}} for i in range(tools)]}),
        encoding="utf-8",
    )
    return str(path)


def _actions(config_path: str | None, phone_number_id: str | None = PHONE_ID) -> list:
    return [
        build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant/org",
            payload={"config_path": config_path, "phone_number_id": phone_number_id},
            retry_policy="none",
            reconciliation_strategy="list_by_name",
            compensation_operation="delete_assistant",
            expected_outcome="Create assistant",
        )
    ]


def _results(remote_id: str | None = ASSISTANT_ID) -> list[dict[str, Any]]:
    return [{"platform": "vapi", "operation": "create_assistant", "remote_id": remote_id}]


def _adapter(tool_ids: list[str] | None, bound_assistant: str | None = ASSISTANT_ID) -> MagicMock:
    adapter = MagicMock()
    adapter.get_assistant.return_value = MagicMock(
        response_data={"model": {"toolIds": tool_ids} if tool_ids is not None else {}}
    )
    adapter.list_phone_numbers.return_value = MagicMock(
        response_data={
            "phone_numbers": [
                {"id": PHONE_ID, "number": "+15550001111", "assistantId": bound_assistant}
            ]
        }
    )
    return adapter


class TestExpectedToolCount:
    def test_counts_tools_in_the_generated_config(self, tmp_path: Any) -> None:
        assert expected_tool_count(_config(tmp_path, 4)) == 4

    @pytest.mark.parametrize("value", [None, "", "/nonexistent/path.json"])
    def test_missing_config_expects_nothing(self, value: str | None) -> None:
        assert expected_tool_count(value) == 0

    def test_unreadable_config_expects_nothing(self, tmp_path: Any) -> None:
        path = tmp_path / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        assert expected_tool_count(str(path)) == 0


class TestToolVerification:
    def test_deployment_with_no_tools_attached_fails(self, tmp_path: Any) -> None:
        """The exact shape of the live failure: 4 declared, 0 attached."""
        failures = verify_onboarding(
            _actions(_config(tmp_path, 4)), _results(), _adapter(tool_ids=None)
        )

        assert any(f.check == "assistant_tools_attached" for f in failures)

    def test_partial_attachment_fails(self, tmp_path: Any) -> None:
        failures = verify_onboarding(
            _actions(_config(tmp_path, 4)), _results(), _adapter(["t1", "t2"])
        )

        assert any(f.check == "assistant_tools_attached" for f in failures)

    def test_full_attachment_passes(self, tmp_path: Any) -> None:
        failures = verify_onboarding(
            _actions(_config(tmp_path, 2)), _results(), _adapter(["t1", "t2"])
        )

        assert failures == []

    def test_unreadable_assistant_is_a_failure_not_a_pass(self, tmp_path: Any) -> None:
        """Unknown state is not evidence of success."""
        adapter = _adapter(["t1"])
        adapter.get_assistant.side_effect = RuntimeError("network down")

        failures = verify_onboarding(_actions(_config(tmp_path, 1)), _results(), adapter)

        assert any(f.check == "assistant_readable" for f in failures)

    def test_config_declaring_no_tools_is_not_checked(self, tmp_path: Any) -> None:
        failures = verify_onboarding(
            _actions(_config(tmp_path, 0), phone_number_id=None), _results(), _adapter(None)
        )

        assert failures == []


class TestPhoneVerification:
    def test_phone_bound_to_another_assistant_fails(self, tmp_path: Any) -> None:
        """The live failure: the number stayed on the previous assistant."""
        failures = verify_onboarding(
            _actions(_config(tmp_path, 1)),
            _results(),
            _adapter(["t1"], bound_assistant="someone-else"),
        )

        assert any(f.check == "phone_bound_to_assistant" for f in failures)

    def test_correctly_bound_phone_passes(self, tmp_path: Any) -> None:
        failures = verify_onboarding(
            _actions(_config(tmp_path, 1)),
            _results(),
            _adapter(["t1"], bound_assistant=ASSISTANT_ID),
        )

        assert failures == []

    def test_unbound_phone_fails(self, tmp_path: Any) -> None:
        failures = verify_onboarding(
            _actions(_config(tmp_path, 1)), _results(), _adapter(["t1"], bound_assistant=None)
        )

        assert any(f.check == "phone_bound_to_assistant" for f in failures)

    def test_missing_phone_number_on_account_fails(self, tmp_path: Any) -> None:
        adapter = _adapter(["t1"])
        adapter.list_phone_numbers.return_value = MagicMock(response_data={"phone_numbers": []})

        failures = verify_onboarding(_actions(_config(tmp_path, 1)), _results(), adapter)

        assert any(f.check == "phone_bound_to_assistant" for f in failures)

    def test_no_phone_requested_is_not_checked(self, tmp_path: Any) -> None:
        failures = verify_onboarding(
            _actions(_config(tmp_path, 1), phone_number_id=None), _results(), _adapter(["t1"])
        )

        assert failures == []


class TestVerificationScope:
    def test_all_failures_are_reported_together(self, tmp_path: Any) -> None:
        """An operator fixing a broken deployment wants the whole list."""
        failures = verify_onboarding(
            _actions(_config(tmp_path, 4)),
            _results(),
            _adapter(tool_ids=None, bound_assistant="someone-else"),
        )

        assert {f.check for f in failures} == {
            "assistant_tools_attached",
            "phone_bound_to_assistant",
        }

    def test_missing_remote_id_is_reported(self, tmp_path: Any) -> None:
        failures = verify_onboarding(_actions(_config(tmp_path, 4)), _results(None), _adapter(None))

        assert [f.check for f in failures] == ["assistant_created"]

    def test_deployment_without_an_assistant_is_not_checked(self) -> None:
        """Update-only or Make-only deployments have nothing to verify here."""
        assert verify_onboarding([], [], _adapter(None)) == []
