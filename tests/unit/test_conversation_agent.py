"""Unit tests for orchestrator/conversation_agent.py"""

import json
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.conversation_agent import DEFAULT_BUSINESS_HOURS, ConversationAgent
from orchestrator.conversation_state import (
    PartialIntakeData,
    SessionPhase,
)

pytestmark = pytest.mark.unit


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


class TestConversationAgentInit:
    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_new_session_creates_state(self, mock_path: MagicMock) -> None:
        mock_path.read_text.return_value = "System prompt"
        mock_model = MagicMock()
        agent = ConversationAgent(mock_model)
        state = agent.new_session()
        assert state.phase == SessionPhase.GATHERING
        assert state.session_id is not None
        assert len(state.session_id) == 36  # UUID format

    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_greet_returns_string(self, mock_path: MagicMock) -> None:
        mock_path.read_text.return_value = "System prompt"
        mock_model = MagicMock()
        agent = ConversationAgent(mock_model)
        greeting = agent.greet()
        assert "Agent Forge" in greeting
        assert len(greeting) > 20


class TestPhaseTransitions:
    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_gathering_to_confirming_when_complete(self, mock_path: MagicMock) -> None:
        mock_path.read_text.return_value = "System prompt"
        mock_model = _make_mock_model(
            extraction_result={
                "org_id": "miami_glow",
                "business_name": "Miami Glow Salon",
                "phone_number": "+13055551234",
                "voice_id": "Savannah",
                "capabilities": ["booking", "cancellation"],
            }
        )
        agent = ConversationAgent(mock_model)
        state = agent.new_session()

        response, state = agent.turn(
            "Set up Miami Glow Salon with booking and cancellation, "
            "phone +13055551234, voice jennifer",
            state,
        )

        assert state.phase == SessionPhase.CONFIRMING
        assert "Miami Glow Salon" in response
        assert "booking" in response.lower() or "take bookings" in response.lower()

    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_confirming_to_executing_on_yes(self, mock_path: MagicMock) -> None:
        mock_path.read_text.return_value = "System prompt"
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

        response, state = agent.turn("yes", state)

        assert state.phase == SessionPhase.EXECUTING
        assert state.confirmed_plan is not None
        assert state.confirmed_plan["organization_id"] == "test"
        assert "Confirmed" in response

    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_confirming_to_executing_on_affirmatives(self, mock_path: MagicMock) -> None:
        mock_path.read_text.return_value = "System prompt"
        mock_model = _make_mock_model()
        agent = ConversationAgent(mock_model)

        for word in ["yes", "y", "yep", "yeah", "ok", "proceed", "looks good", "confirmed"]:
            state = agent.new_session()
            state.phase = SessionPhase.CONFIRMING
            state.partial_intake = PartialIntakeData(
                org_id="t",
                business_name="T",
                phone_number="+1",
                voice_id="v",
                capabilities=["booking"],
            )
            _, state = agent.turn(word, state)
            assert state.phase == SessionPhase.EXECUTING, f"Failed on: {word}"

    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_confirming_to_aborted_on_cancel(self, mock_path: MagicMock) -> None:
        mock_path.read_text.return_value = "System prompt"
        mock_model = _make_mock_model()
        agent = ConversationAgent(mock_model)
        state = agent.new_session()
        state.phase = SessionPhase.CONFIRMING
        state.partial_intake = PartialIntakeData(
            org_id="t",
            business_name="T",
            phone_number="+1",
            voice_id="v",
            capabilities=["booking"],
        )

        response, state = agent.turn("cancel", state)

        assert state.phase == SessionPhase.ABORTED
        assert "cancelled" in response.lower() or "nothing" in response.lower()

    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_confirming_returns_to_gathering_on_change(self, mock_path: MagicMock) -> None:
        mock_path.read_text.return_value = "System prompt"
        mock_model = _make_mock_model(
            extraction_result={"voice_id": "Emma"},
            response_text="Got it, updating the voice to Emma.",
        )
        agent = ConversationAgent(mock_model)
        state = agent.new_session()
        state.phase = SessionPhase.CONFIRMING
        state.partial_intake = PartialIntakeData(
            org_id="test",
            business_name="Test",
            phone_number="+1234",
            voice_id="Savannah",
            capabilities=["booking"],
        )

        response, state = agent.turn("Actually use Emma instead", state)

        assert state.partial_intake.voice_id == "Emma"
        assert state.phase == SessionPhase.CONFIRMING


class TestPlanSummaryDefaults:
    """The summary must describe what actually deploys.

    Timezone and business hours are optional, so a failed extraction silently
    substitutes a default. A live session dropped a stated "Saturday 10am to
    2pm" this way: the summary never mentioned hours, so the operator confirmed
    a plan that said nothing about the field being defaulted underneath them.
    """

    @staticmethod
    def _agent() -> ConversationAgent:
        return ConversationAgent(_make_mock_model())

    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_summary_marks_hours_and_timezone_as_defaulted(self, mock_path: MagicMock) -> None:
        mock_path.read_text.return_value = "System prompt"
        agent = self._agent()
        state = agent.new_session()
        state.partial_intake = PartialIntakeData(
            org_id="northgate_dental",
            business_name="Northgate Dental Studio",
            phone_number="+19086846982",
            voice_id="Elliot",
            capabilities=["booking"],
        )

        summary = agent._build_plan_summary(state)

        assert "default" in summary.lower()
        assert "America/New_York" in summary
        # Closed days are shown, so a dropped day is visible rather than absent.
        assert "Saturday" in summary
        assert "closed" in summary

    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_summary_does_not_cry_default_when_hours_were_captured(
        self, mock_path: MagicMock
    ) -> None:
        mock_path.read_text.return_value = "System prompt"
        agent = self._agent()
        state = agent.new_session()
        state.partial_intake = PartialIntakeData(
            org_id="northgate_dental",
            business_name="Northgate Dental Studio",
            phone_number="+19086846982",
            voice_id="Elliot",
            capabilities=["booking"],
            timezone="America/Chicago",
            business_hours={"saturday": [{"open": "10:00", "close": "14:00"}]},
        )

        summary = agent._build_plan_summary(state)

        assert "default" not in summary.lower()
        assert "America/Chicago" in summary
        assert "10:00-14:00" in summary

    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_default_hours_are_not_shared_between_intakes(self, mock_path: MagicMock) -> None:
        """The module-level default must not be mutable through a built intake."""
        mock_path.read_text.return_value = "System prompt"
        agent = self._agent()
        state = agent.new_session()
        state.partial_intake = PartialIntakeData(
            org_id="a",
            business_name="A",
            phone_number="+15550001111",
            voice_id="Elliot",
            capabilities=["booking"],
        )

        first = agent._build_confirmed_intake(state)
        first["business_hours"]["monday"].append({"open": "00:00", "close": "23:59"})  # type: ignore[index,union-attr]
        second = agent._build_confirmed_intake(state)

        assert second["business_hours"]["monday"] == [{"open": "09:00", "close": "17:00"}]  # type: ignore[index]
        assert DEFAULT_BUSINESS_HOURS["monday"] == [{"open": "09:00", "close": "17:00"}]


class TestPlanSummary:
    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_plan_summary_plain_language(self, mock_path: MagicMock) -> None:
        mock_path.read_text.return_value = "System prompt"
        mock_model = _make_mock_model()
        agent = ConversationAgent(mock_model)
        state = agent.new_session()
        state.partial_intake = PartialIntakeData(
            org_id="miami_glow",
            business_name="Miami Glow Salon",
            phone_number="+13055551234",
            voice_id="jennifer",
            capabilities=["booking", "cancellation", "rescheduling"],
        )

        summary = agent._build_plan_summary(state)

        assert "Miami Glow Salon" in summary
        assert "jennifer" in summary
        assert "+13055551234" in summary
        assert "take bookings" in summary
        assert "handle cancellations" in summary
        assert "reschedule appointments" in summary
        assert "Supabase" in summary
        assert "webhook" in summary.lower()
        # Must not contain JSON field names
        assert "org_id" not in summary
        assert "voice_id" not in summary
        assert "phone_number" not in summary

    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_plan_summary_no_json_field_names(self, mock_path: MagicMock) -> None:
        mock_path.read_text.return_value = "System prompt"
        mock_model = _make_mock_model()
        agent = ConversationAgent(mock_model)
        state = agent.new_session()
        state.partial_intake = PartialIntakeData(
            org_id="dental_clinic",
            business_name="Downtown Dental",
            phone_number="+14155556789",
            voice_id="rachel",
            capabilities=["booking", "availability"],
        )

        summary = agent._build_plan_summary(state)

        json_field_names = ["org_id", "voice_id", "phone_number", "business_name", "capabilities"]
        for field_name in json_field_names:
            assert field_name not in summary, (
                f"Found JSON field name '{field_name}' in plan summary"
            )


class TestVoiceSuggestions:
    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_voice_suggestion_request_returns_options(self, mock_path: MagicMock) -> None:
        mock_path.read_text.return_value = "System prompt"
        mock_model = _make_mock_model()
        agent = ConversationAgent(mock_model)
        state = agent.new_session()

        response, state = agent.turn("Can you suggest some voices?", state)

        assert "Elliot" in response
        assert "Savannah" in response
        assert state.phase == SessionPhase.GATHERING


class TestConfirmedIntake:
    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_confirmed_intake_contains_all_fields(self, mock_path: MagicMock) -> None:
        mock_path.read_text.return_value = "System prompt"
        mock_model = _make_mock_model()
        agent = ConversationAgent(mock_model)
        state = agent.new_session()
        state.partial_intake = PartialIntakeData(
            org_id="test_org",
            business_name="Test Org",
            phone_number="+11234567890",
            voice_id="jennifer",
            capabilities=["booking"],
            industry="salon",
            timezone="America/New_York",
        )

        result = agent._build_confirmed_intake(state)

        assert result["organization_id"] == "test_org"
        assert result["business_name"] == "Test Org"
        assert result["phone_number"] == "+11234567890"
        assert result["voice_id"] == "jennifer"
        assert result["enabled_capabilities"] == ["booking"]
        assert result["industry"] == "salon"
        assert result["timezone"] == "America/New_York"
        assert "services_offered" in result
        assert "external_identifiers" in result
        assert "business_hours" in result
