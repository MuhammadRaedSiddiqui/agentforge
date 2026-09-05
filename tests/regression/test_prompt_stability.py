"""
Regression tests for system prompts and conversational behavior.

These tests ensure that changes to system prompts don't break expected
conversational patterns and output quality.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.conversation_agent import ConversationAgent
from orchestrator.conversation_state import PartialIntakeData, SessionPhase

pytestmark = pytest.mark.regression


def _make_mock_model(extraction_result: dict | None = None, response_text: str = "OK") -> MagicMock:
    """Create a mock ModelWrapper that returns controlled responses."""
    mock = MagicMock()

    def create_completion_side_effect(messages, **kwargs):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]

        if kwargs.get("tools"):
            if extraction_result:
                mock_tool_call = MagicMock()
                mock_tool_call.function.name = "update_intake"
                mock_tool_call.function.arguments = json.dumps(extraction_result)
                mock_response.choices[0].message.tool_calls = [mock_tool_call]
            else:
                mock_response.choices[0].message.tool_calls = None
        else:
            mock_response.choices[0].message.content = response_text
            mock_response.choices[0].message.tool_calls = None

        return mock_response

    mock.create_completion.side_effect = create_completion_side_effect
    return mock


class TestPromptVersioning:
    """Track system prompt versions to detect unintended changes."""

    def test_system_prompt_exists(self) -> None:
        """Ensure system prompt file exists at expected location."""
        prompt_path = Path("memory/orchestrator_system_prompt.md")
        assert prompt_path.exists(), f"System prompt not found at {prompt_path}"

    def test_system_prompt_not_empty(self) -> None:
        """Ensure system prompt has content."""
        prompt_path = Path("memory/orchestrator_system_prompt.md")
        content = prompt_path.read_text(encoding="utf-8")
        assert len(content) > 100, "System prompt suspiciously short"
        assert "Agent Forge" in content, "System prompt missing key identifier"

    def test_system_prompt_has_required_sections(self) -> None:
        """Ensure system prompt contains critical behavioral guidance."""
        prompt_path = Path("memory/orchestrator_system_prompt.md")
        content = prompt_path.read_text(encoding="utf-8")

        required_sections = [
            "Your role",
            "What you are gathering",
            "How to ask questions",
            "Plan confirmation",
            "What you must never do",
        ]

        for section in required_sections:
            assert section in content, f"System prompt missing required section: {section}"


class TestConversationalBehaviorRegression:
    """Regression tests for conversational patterns that must remain stable."""

    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_no_json_field_names_in_plan_summary(self, mock_path: MagicMock) -> None:
        """
        REGRESSION: Plan summaries must never expose internal field names.

        This is a critical UX requirement - users should see plain language,
        not technical field names like org_id, voice_id, etc.
        """
        mock_path.read_text.return_value = Path("memory/orchestrator_system_prompt.md").read_text(
            encoding="utf-8"
        )
        mock_model = _make_mock_model()
        agent = ConversationAgent(mock_model)
        state = agent.new_session()
        state.partial_intake = PartialIntakeData(
            org_id="test_org",
            business_name="Test Business",
            phone_number="+15551234567",
            voice_id="jennifer",
            capabilities=["booking", "cancellation"],
        )

        summary = agent._build_plan_summary(state)

        # These field names must NEVER appear in user-facing text
        forbidden_terms = [
            "org_id",
            "voice_id",
            "phone_number",
            "business_name",
            "capabilities",
            "enabled_capabilities",
            "organization_id",
        ]

        for term in forbidden_terms:
            assert term not in summary, (
                f"Plan summary contains internal field name '{term}'. "
                f"This breaks the plain-language requirement."
            )

        # Must contain actual values in plain language
        assert "Test Business" in summary
        assert "jennifer" in summary
        assert "+15551234567" in summary

    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_confirmation_keywords_remain_stable(self, mock_path: MagicMock) -> None:
        """
        REGRESSION: Confirmation keywords must remain stable.

        Users expect common affirmatives (yes, ok, proceed) to confirm plans.
        Removing these would break user workflows.
        """
        mock_path.read_text.return_value = Path("memory/orchestrator_system_prompt.md").read_text(
            encoding="utf-8"
        )
        mock_model = _make_mock_model()
        agent = ConversationAgent(mock_model)

        # Core affirmatives that MUST work
        core_affirmatives = ["yes", "y", "ok", "proceed"]

        for affirmative in core_affirmatives:
            state = agent.new_session()
            state.phase = SessionPhase.CONFIRMING
            state.partial_intake = PartialIntakeData(
                org_id="test",
                business_name="Test",
                phone_number="+1234",
                voice_id="v1",
                capabilities=["booking"],
            )

            _, updated_state = agent.turn(affirmative, state)
            assert updated_state.phase == SessionPhase.EXECUTING, (
                f"Affirmative keyword '{affirmative}' failed to confirm. "
                f"This is a critical regression - users expect this to work."
            )

    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_cancellation_keywords_remain_stable(self, mock_path: MagicMock) -> None:
        """
        REGRESSION: Cancellation keywords must remain stable.

        Users expect common negatives (no, cancel, stop) to abort deployments.
        """
        mock_path.read_text.return_value = Path("memory/orchestrator_system_prompt.md").read_text(
            encoding="utf-8"
        )
        mock_model = _make_mock_model()
        agent = ConversationAgent(mock_model)

        # Core negatives that MUST work
        core_negatives = ["no", "cancel", "stop"]

        for negative in core_negatives:
            state = agent.new_session()
            state.phase = SessionPhase.CONFIRMING
            state.partial_intake = PartialIntakeData(
                org_id="test",
                business_name="Test",
                phone_number="+1234",
                voice_id="v1",
                capabilities=["booking"],
            )

            _, updated_state = agent.turn(negative, state)
            assert updated_state.phase == SessionPhase.ABORTED, (
                f"Cancellation keyword '{negative}' failed to abort. "
                f"This is a critical regression - users expect this to work."
            )

    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_greeting_remains_informative(self, mock_path: MagicMock) -> None:
        """
        REGRESSION: Greeting must remain informative and actionable.

        First message sets expectations for the entire conversation.
        """
        mock_path.read_text.return_value = Path("memory/orchestrator_system_prompt.md").read_text(
            encoding="utf-8"
        )
        mock_model = _make_mock_model()
        agent = ConversationAgent(mock_model)

        greeting = agent.greet()

        # Must identify the tool
        assert "Agent Forge" in greeting or "agent" in greeting.lower()

        # Must indicate readiness
        assert any(word in greeting.lower() for word in ["ready", "help", "set up", "tell me"]), (
            "Greeting doesn't indicate readiness or what to do next"
        )

        # Should be concise (not overly verbose)
        assert len(greeting) < 500, "Greeting is too verbose"


class TestPhaseTransitionRegression:
    """Regression tests for phase transition logic."""

    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_gathering_to_confirming_requires_all_fields(self, mock_path: MagicMock) -> None:
        """
        REGRESSION: Must not transition to confirming until all required fields present.

        Transitioning early would result in incomplete deployments.
        """
        mock_path.read_text.return_value = Path("memory/orchestrator_system_prompt.md").read_text(
            encoding="utf-8"
        )

        # Test with missing fields
        incomplete_cases = [
            {"org_id": "test"},  # Missing everything else
            {"org_id": "test", "business_name": "Test"},  # Missing phone, voice, capabilities
            {
                "org_id": "test",
                "business_name": "Test",
                "phone_number": "+1234",
            },  # Missing voice, capabilities
        ]

        for incomplete_data in incomplete_cases:
            mock_model = _make_mock_model(extraction_result=incomplete_data)
            agent = ConversationAgent(mock_model)
            state = agent.new_session()

            _, updated_state = agent.turn("Test input", state)

            assert updated_state.phase == SessionPhase.GATHERING, (
                f"Prematurely transitioned to confirming with incomplete data: {incomplete_data}"
            )

    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_confirming_to_executing_sets_confirmed_plan(self, mock_path: MagicMock) -> None:
        """
        REGRESSION: Transition to executing must set confirmed_plan.

        Execution pipeline depends on this field being present.
        """
        mock_path.read_text.return_value = Path("memory/orchestrator_system_prompt.md").read_text(
            encoding="utf-8"
        )
        mock_model = _make_mock_model()
        agent = ConversationAgent(mock_model)

        state = agent.new_session()
        state.phase = SessionPhase.CONFIRMING
        state.partial_intake = PartialIntakeData(
            org_id="test",
            business_name="Test",
            phone_number="+1234",
            voice_id="v1",
            capabilities=["booking"],
        )

        _, updated_state = agent.turn("yes", state)

        assert updated_state.confirmed_plan is not None, (
            "confirmed_plan not set during transition to EXECUTING. "
            "This will break the execution pipeline."
        )
        assert isinstance(updated_state.confirmed_plan, dict)
        assert "organization_id" in updated_state.confirmed_plan
        assert updated_state.confirmed_plan["organization_id"] == "test"


class TestConfirmedIntakeRegression:
    """Regression tests for confirmed intake structure."""

    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_confirmed_intake_has_required_execution_fields(self, mock_path: MagicMock) -> None:
        """
        REGRESSION: Confirmed intake must contain all fields required by planner.

        Missing fields cause execution failures downstream.
        """
        mock_path.read_text.return_value = Path("memory/orchestrator_system_prompt.md").read_text(
            encoding="utf-8"
        )
        mock_model = _make_mock_model()
        agent = ConversationAgent(mock_model)

        state = agent.new_session()
        state.partial_intake = PartialIntakeData(
            org_id="test",
            business_name="Test",
            phone_number="+1234",
            voice_id="v1",
            capabilities=["booking"],
        )

        confirmed = agent._build_confirmed_intake(state)

        # Fields required by planner/orchestrator
        required_fields = [
            "organization_id",
            "business_name",
            "phone_number",
            "voice_id",
            "enabled_capabilities",
            "timezone",
            "business_hours",
            "services_offered",
            "external_identifiers",
        ]

        for field in required_fields:
            assert field in confirmed, (
                f"Confirmed intake missing required field: {field}. "
                f"This will cause execution failures."
            )

    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_confirmed_intake_maps_field_names_correctly(self, mock_path: MagicMock) -> None:
        """
        REGRESSION: Field name mapping must remain consistent.

        org_id → organization_id
        capabilities → enabled_capabilities

        Changing this mapping breaks the execution pipeline.
        """
        mock_path.read_text.return_value = Path("memory/orchestrator_system_prompt.md").read_text(
            encoding="utf-8"
        )
        mock_model = _make_mock_model()
        agent = ConversationAgent(mock_model)

        state = agent.new_session()
        state.partial_intake = PartialIntakeData(
            org_id="test_org",
            business_name="Test",
            phone_number="+1234",
            voice_id="v1",
            capabilities=["booking", "cancellation"],
        )

        confirmed = agent._build_confirmed_intake(state)

        # Verify field mapping
        assert confirmed["organization_id"] == "test_org", "org_id not mapped to organization_id"
        assert confirmed["enabled_capabilities"] == ["booking", "cancellation"], (
            "capabilities not mapped to enabled_capabilities"
        )

        # Ensure old names are NOT present
        assert "org_id" not in confirmed, "org_id should be mapped to organization_id"
        assert "capabilities" not in confirmed, (
            "capabilities should be mapped to enabled_capabilities"
        )
