"""
Unit tests for the Vapi create_assistant execution branch.

A live onboarding reported "SUCCESS, 8 of 8 actions" and produced an assistant
that could not receive a call and could not invoke anything:

  - the generated config defined four tools, and the executor popped them
    before the create call without ever creating them
  - the phone assignment sat inside `contextlib.suppress(Exception)`, so any
    failure was invisible and the action still reported success
  - the tool endpoints were built from HOSTING_HEALTH_URL, so every one of
    them pointed at `.../health/tools/<capability>`

These pin all three, because each failure is silent by nature: the deployment
looks identical whether or not it worked.
"""

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from cli.main import webhook_base_from_health_url
from orchestrator.approval import build_proposed_action
from orchestrator.orchestrator import Orchestrator

pytestmark = pytest.mark.unit

ASSISTANT_ID = "asst-created-1"


def _config(tmp_path: Any, tools: int = 4) -> str:
    config = {
        "name": "Test Assistant",
        "model": {"provider": "openai", "model": "gpt-4", "temperature": 0.7},
        "serverUrl": "https://svc.invalid",
        "metadata": {"organization_id": "test_org"},
        "tools": [
            {
                "type": "function",
                "function": {"name": f"tool_{i}", "parameters": {}},
                "server": {"url": f"https://svc.invalid/tools/{i}"},
            }
            for i in range(tools)
        ],
    }
    path = tmp_path / "assistant_config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return str(path)


def _adapter() -> MagicMock:
    adapter = MagicMock()
    adapter.create_assistant.return_value = MagicMock(remote_id=ASSISTANT_ID, status="success")
    adapter.create_tool.side_effect = [
        MagicMock(remote_id=f"tool-id-{i}", status="success") for i in range(10)
    ]
    return adapter


def _action(config_path: str, phone_number_id: str | None = None):
    return build_proposed_action(
        platform="vapi",
        operation="create_assistant",
        target="assistant/test_org",
        payload={
            "name": "test-assistant",
            "config_path": config_path,
            "content_hash": "a" * 64,
            "phone_number_id": phone_number_id,
        },
        retry_policy="none",
        reconciliation_strategy="list_by_name",
        compensation_operation="delete_assistant",
        expected_outcome="Create Vapi assistant",
    )


def _run(adapter: MagicMock, config_path: str, phone_number_id: str | None = None) -> Any:
    orch = Orchestrator(MagicMock())
    return orch._execute_vapi_action(adapter, _action(config_path, phone_number_id))


class TestToolsAreCreatedAndAttached:
    def test_every_generated_tool_is_created(self, tmp_path: Any) -> None:
        adapter = _adapter()
        _run(adapter, _config(tmp_path, tools=4))

        assert adapter.create_tool.call_count == 4

    def test_tools_are_bound_to_the_assistant(self, tmp_path: Any) -> None:
        adapter = _adapter()
        _run(adapter, _config(tmp_path, tools=3))

        adapter.update_assistant.assert_called_once()
        assistant_id, payload = adapter.update_assistant.call_args[0]
        assert assistant_id == ASSISTANT_ID
        assert payload["model"]["toolIds"] == ["tool-id-0", "tool-id-1", "tool-id-2"]

    def test_binding_resends_the_whole_model_block(self, tmp_path: Any) -> None:
        """Vapi's PATCH replaces `model` wholesale, so a partial one drops config."""
        adapter = _adapter()
        _run(adapter, _config(tmp_path, tools=1))

        model = adapter.update_assistant.call_args[0][1]["model"]
        assert model["provider"] == "openai"
        assert model["model"] == "gpt-4"
        assert model["temperature"] == 0.7

    def test_tools_are_not_sent_inline_to_create(self, tmp_path: Any) -> None:
        """The create endpoint rejects inline tools; they must be stripped."""
        adapter = _adapter()
        _run(adapter, _config(tmp_path))

        created = adapter.create_assistant.call_args[0][0]
        assert "tools" not in created
        assert "metadata" not in created

    def test_no_tools_means_no_update(self, tmp_path: Any) -> None:
        adapter = _adapter()
        _run(adapter, _config(tmp_path, tools=0))

        adapter.update_assistant.assert_not_called()

    def test_tool_creation_failure_is_not_swallowed(self, tmp_path: Any) -> None:
        adapter = _adapter()
        adapter.create_tool.side_effect = RuntimeError("vapi rejected the tool")

        with pytest.raises(RuntimeError):
            _run(adapter, _config(tmp_path))


class TestPhoneNumberBinding:
    def test_phone_number_is_assigned_to_the_new_assistant(self, tmp_path: Any) -> None:
        adapter = _adapter()
        _run(adapter, _config(tmp_path), phone_number_id="phone-1")

        adapter.assign_phone_number.assert_called_once_with("phone-1", ASSISTANT_ID)

    def test_absent_phone_number_is_not_assigned(self, tmp_path: Any) -> None:
        adapter = _adapter()
        _run(adapter, _config(tmp_path), phone_number_id=None)

        adapter.assign_phone_number.assert_not_called()

    def test_assignment_failure_is_not_swallowed(self, tmp_path: Any) -> None:
        """An assistant nobody can call is a failed deployment, not a warning."""
        adapter = _adapter()
        adapter.assign_phone_number.side_effect = RuntimeError("vapi timeout")

        with pytest.raises(RuntimeError):
            _run(adapter, _config(tmp_path), phone_number_id="phone-1")


class TestWebhookBaseFromHealthUrl:
    @pytest.mark.parametrize(
        ("health_url", "expected"),
        [
            ("https://svc.onrender.com/health", "https://svc.onrender.com"),
            ("https://svc.onrender.com/health/", "https://svc.onrender.com"),
            ("https://svc.onrender.com/", "https://svc.onrender.com"),
            ("https://svc.onrender.com", "https://svc.onrender.com"),
            ("https://svc.onrender.com/api/v1/health", "https://svc.onrender.com"),
        ],
    )
    def test_path_is_dropped(self, health_url: str, expected: str) -> None:
        assert webhook_base_from_health_url(health_url) == expected

    def test_tool_endpoint_is_not_nested_under_health(self) -> None:
        base = webhook_base_from_health_url("https://svc.onrender.com/health")
        assert f"{base}/tools/booking" == "https://svc.onrender.com/tools/booking"

    def test_unparseable_value_falls_back_rather_than_inventing_an_origin(self) -> None:
        assert webhook_base_from_health_url("not-a-url/") == "not-a-url"
