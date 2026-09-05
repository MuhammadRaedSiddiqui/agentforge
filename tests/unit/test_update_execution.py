"""Tests for the update execution flow."""

from unittest.mock import Mock

import pytest

from orchestrator.selective_regenerator import SelectiveRegenerator


@pytest.mark.unit
class TestUpdateFlow:
    def test_determine_affected_vapi(self):
        regen = SelectiveRegenerator()
        affected = regen.determine_affected_artifacts(
            intent="update_assistant",
            changes={"name": {"from": "Old", "to": "New"}},
        )
        assert "vapi_assistant" in affected
        assert "make_scenario" not in affected

    def test_determine_affected_make(self):
        regen = SelectiveRegenerator()
        affected = regen.determine_affected_artifacts(
            intent="update_scenario",
            changes={"capability": {"from": "booking", "to": "booking"}},
        )
        assert "make_scenario" in affected
        assert "vapi_assistant" not in affected

    def test_determine_affected_make_with_webhook_change(self):
        regen = SelectiveRegenerator()
        affected = regen.determine_affected_artifacts(
            intent="update_scenario",
            changes={"webhook_url": {"from": "old.com", "to": "new.com"}},
        )
        assert "make_scenario" in affected
        assert "make_hooks" in affected

    def test_generate_update_tasks_vapi(self):
        regen = SelectiveRegenerator()
        tasks = regen.generate_update_tasks(
            deployment_id="dep-001",
            organization_id="org-test",
            intent="update_assistant",
            changes={"name": {"from": "Old", "to": "New"}},
            current_state={},
        )
        assert len(tasks) == 1
        assert tasks[0].agent_target == "vapi_agent"
        assert tasks[0].action_type == "update_assistant"

    def test_generate_update_tasks_backend(self):
        regen = SelectiveRegenerator()
        tasks = regen.generate_update_tasks(
            deployment_id="dep-002",
            organization_id="org-test",
            intent="update_backend",
            changes={"server_code": {"from": "v1", "to": "v2"}},
            current_state={},
        )
        assert len(tasks) == 2
        targets = {t.agent_target for t in tasks}
        assert "nodejs_agent" in targets
        assert "hosting_adapter" in targets

    def test_build_update_actions_vapi(self):
        import sys

        sys.path.insert(0, ".")
        from cli.main import _build_update_actions
        from shared.task_object import TaskObject

        task = TaskObject(
            task_id="dep-001_vapi_assistant_update",
            deployment_id="dep-001",
            agent_target="vapi_agent",
            action_type="update_assistant",
            context_hash="abc123",
            constraints=[],
            dependencies=[],
            verification_required=True,
            status="pending",
        )

        current_state = {
            "platforms": {"vapi": {"assistants": [{"id": "asst-123", "name": "Old Name"}]}}
        }
        changes = {"name": {"from": "Old Name", "to": "New Name"}}

        # Update actions record the remote state they were planned against, so
        # the builder needs a state reader. Inject a fake rather than letting it
        # construct one that would call Vapi.
        baseline = {"name": "Old Name", "model": None, "voice": None, "first_message": None}
        reader = Mock()
        reader.read_staleness_state = Mock(return_value=baseline)

        actions = _build_update_actions(
            [task], "org-test", changes, current_state, state_reader=reader
        )

        assert len(actions) == 1
        assert actions[0].platform == "vapi"
        assert actions[0].operation == "update_assistant"
        assert actions[0].payload["assistant_id"] == "asst-123"
        assert actions[0].payload["updates"]["name"] == "New Name"

        # The action must be bound to the state it was planned against, or the
        # pre-write staleness check has nothing to compare.
        assert actions[0].state_version is not None
        assert actions[0].baseline_state == baseline
        reader.read_staleness_state.assert_called_once_with("vapi", "assistant", "asst-123")

    def test_build_update_actions_empty_state(self):
        from cli.main import _build_update_actions
        from shared.task_object import TaskObject

        task = TaskObject(
            task_id="dep-001_vapi_assistant_update",
            deployment_id="dep-001",
            agent_target="vapi_agent",
            action_type="update_assistant",
            context_hash="abc123",
            constraints=[],
            dependencies=[],
            verification_required=True,
            status="pending",
        )

        current_state = {"platforms": {"vapi": {"assistants": []}}}
        changes = {"name": {"from": "Old", "to": "New"}}

        actions = _build_update_actions([task], "org-test", changes, current_state)
        assert len(actions) == 0

    def test_preserve_unchanged_resources(self):
        regen = SelectiveRegenerator()
        current_state = {
            "platforms": {
                "vapi": {
                    "assistants": [{"id": "asst-1"}],
                    "tools": [{"id": "tool-1"}, {"id": "tool-2"}],
                },
                "make": {
                    "scenarios": [{"id": "sc-1"}],
                    "hooks": [{"id": "hook-1"}],
                },
            }
        }

        preserved = regen.preserve_unchanged_resources(
            current_state=current_state,
            affected_artifacts={"vapi_assistant"},
        )

        assert "tool-1" in preserved["vapi"]
        assert "tool-2" in preserved["vapi"]
        assert "sc-1" in preserved["make"]
        assert "hook-1" in preserved["make"]
        assert "asst-1" not in preserved["vapi"]
