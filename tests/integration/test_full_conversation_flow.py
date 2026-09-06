"""Integration tests for the full conversational intake flow."""

import json
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.conversation_agent import ConversationAgent
from orchestrator.conversation_state import SessionPhase

pytestmark = pytest.mark.integration


def _make_extraction_model(extractions_per_turn: list[dict]) -> MagicMock:
    """
    Create a mock model that returns different extractions per turn.
    extractions_per_turn[i] is returned on the i-th call with tools.
    """
    mock = MagicMock()
    call_count = {"extract": 0, "response": 0}

    def side_effect(messages, **kwargs):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]

        if kwargs.get("tools"):
            idx = min(call_count["extract"], len(extractions_per_turn) - 1)
            extraction = extractions_per_turn[idx]
            call_count["extract"] += 1

            if extraction:
                mock_tool_call = MagicMock()
                mock_tool_call.function.name = "update_intake"
                mock_tool_call.function.arguments = json.dumps(extraction)
                mock_response.choices[0].message.tool_calls = [mock_tool_call]
            else:
                mock_response.choices[0].message.tool_calls = None
        else:
            call_count["response"] += 1
            mock_response.choices[0].message.content = "Got it. What else do you need?"
            mock_response.choices[0].message.tool_calls = None

        return mock_response

    mock.create_completion.side_effect = side_effect
    return mock


class TestCompleteIntakeInOneTurn:
    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_all_fields_in_one_message(self, mock_path: MagicMock) -> None:
        mock_path.read_text.return_value = "System prompt"
        model = _make_extraction_model(
            [
                {
                    "org_id": "miami_glow_salon",
                    "business_name": "Miami Glow Salon",
                    "phone_number": "+13055551234",
                    "voice_id": "jennifer",
                    "capabilities": ["booking", "cancellation", "rescheduling"],
                    "industry": "salon",
                }
            ]
        )

        agent = ConversationAgent(model)
        state = agent.new_session()

        response, state = agent.turn(
            "Set up Miami Glow Salon, a hair salon. They need booking, "
            "cancellation, and rescheduling. Phone +13055551234, voice jennifer.",
            state,
        )

        assert state.phase == SessionPhase.CONFIRMING
        assert "Miami Glow Salon" in response
        assert state.partial_intake.org_id == "miami_glow_salon"
        assert state.partial_intake.capabilities == ["booking", "cancellation", "rescheduling"]


class TestIncrementalIntakeAcrossTurns:
    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_five_turn_conversation(self, mock_path: MagicMock) -> None:
        mock_path.read_text.return_value = "System prompt"
        model = _make_extraction_model(
            [
                {
                    "business_name": "Downtown Dental",
                    "org_id": "downtown_dental",
                    "industry": "dental",
                },
                {"capabilities": ["booking", "cancellation"]},
                {"phone_number": "+14155556789"},
                {"voice_id": "rachel"},
            ]
        )

        agent = ConversationAgent(model)
        state = agent.new_session()

        # Turn 1: business name
        _, state = agent.turn("I need a voice agent for Downtown Dental", state)
        assert state.phase == SessionPhase.GATHERING
        assert state.partial_intake.business_name == "Downtown Dental"

        # Turn 2: capabilities
        _, state = agent.turn("Booking and cancellation", state)
        assert state.phase == SessionPhase.GATHERING
        assert state.partial_intake.capabilities == ["booking", "cancellation"]

        # Turn 3: phone
        _, state = agent.turn("+14155556789", state)
        assert state.phase == SessionPhase.GATHERING
        assert state.partial_intake.phone_number == "+14155556789"

        # Turn 4: voice (should complete and transition to confirming)
        _, state = agent.turn("Use rachel", state)
        assert state.phase == SessionPhase.CONFIRMING
        assert state.partial_intake.voice_id == "rachel"


class TestCorrectionMidConversation:
    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_correction_updates_field(self, mock_path: MagicMock) -> None:
        mock_path.read_text.return_value = "System prompt"

        model = _make_extraction_model(
            [
                {
                    "org_id": "test_org",
                    "business_name": "Test Org",
                    "phone_number": "+13055551234",
                    "voice_id": "jennifer",
                    "capabilities": ["booking"],
                },
                {"phone_number": "+13055559999"},
            ]
        )

        agent = ConversationAgent(model)
        state = agent.new_session()

        # Turn 1: all fields (moves to confirming)
        _, state = agent.turn("Set up Test Org, booking, +13055551234, jennifer", state)
        assert state.phase == SessionPhase.CONFIRMING

        # Turn 2: correction (applies fix and re-presents plan)
        _, state = agent.turn("Actually the phone number is +13055559999", state)
        assert state.partial_intake.phone_number == "+13055559999"
        assert state.phase == SessionPhase.CONFIRMING


class TestHandoffProducesValidIntake:
    @patch("orchestrator.conversation_agent.SYSTEM_PROMPT_PATH")
    def test_confirmed_plan_has_all_required_fields(self, mock_path: MagicMock) -> None:
        mock_path.read_text.return_value = "System prompt"
        model = _make_extraction_model(
            [
                {
                    "org_id": "test_co",
                    "business_name": "Test Co",
                    "phone_number": "+11234567890",
                    "voice_id": "adam",
                    "capabilities": ["booking", "availability"],
                    "timezone": "America/Chicago",
                }
            ]
        )

        agent = ConversationAgent(model)
        state = agent.new_session()

        # Complete intake in one turn
        _, state = agent.turn("Full intake here", state)
        assert state.phase == SessionPhase.CONFIRMING

        # Confirm
        _, state = agent.turn("yes", state)
        assert state.phase == SessionPhase.EXECUTING
        assert state.confirmed_plan is not None

        plan = state.confirmed_plan
        assert plan["organization_id"] == "test_co"
        assert plan["business_name"] == "Test Co"
        assert plan["phone_number"] == "+11234567890"
        assert plan["voice_id"] == "adam"
        assert plan["enabled_capabilities"] == ["booking", "availability"]
        assert plan["timezone"] == "America/Chicago"
        assert "services_offered" in plan
        assert "external_identifiers" in plan
        assert "business_hours" in plan
