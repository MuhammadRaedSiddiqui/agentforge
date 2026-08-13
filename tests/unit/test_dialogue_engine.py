"""Unit tests for orchestrator/dialogue_engine.py"""

from orchestrator.conversation_state import PartialIntakeData
from orchestrator.dialogue_engine import (
    FIELD_QUESTIONS,
    VOICE_SUGGESTIONS,
    handle_voice_suggestion_request,
    next_question,
)


class TestNextQuestion:
    def test_returns_none_when_all_required_present(self) -> None:
        partial = PartialIntakeData(
            org_id="test_org",
            business_name="Test Org",
            phone_number="+13055551234",
            voice_id="Elliot",
            capabilities=["booking"],
        )
        assert next_question(partial) is None

    def test_asks_capabilities_first_when_all_missing(self) -> None:
        partial = PartialIntakeData()
        result = next_question(partial)
        assert result == FIELD_QUESTIONS["capabilities"]

    def test_asks_capabilities_when_only_name_given(self) -> None:
        partial = PartialIntakeData(
            org_id="test",
            business_name="Test Biz",
        )
        result = next_question(partial)
        assert result == FIELD_QUESTIONS["capabilities"]

    def test_asks_phone_when_capabilities_present(self) -> None:
        partial = PartialIntakeData(
            org_id="test",
            business_name="Test Biz",
            capabilities=["booking"],
        )
        result = next_question(partial)
        assert result == FIELD_QUESTIONS["phone_number"]

    def test_asks_voice_when_phone_present(self) -> None:
        partial = PartialIntakeData(
            org_id="test",
            business_name="Test Biz",
            capabilities=["booking"],
            phone_number="+13055551234",
        )
        result = next_question(partial)
        assert result == FIELD_QUESTIONS["voice_id"]

    def test_asks_org_id_when_only_missing_required(self) -> None:
        partial = PartialIntakeData(
            business_name="Test Biz",
            phone_number="+13055551234",
            voice_id="Elliot",
            capabilities=["booking"],
        )
        result = next_question(partial)
        assert "org" in result.lower() or "identifier" in result.lower() or "org id" in result.lower()

    def test_asks_business_name_when_only_missing_required(self) -> None:
        partial = PartialIntakeData(
            org_id="test",
            phone_number="+13055551234",
            voice_id="Elliot",
            capabilities=["booking"],
        )
        result = next_question(partial)
        assert "business name" in result.lower()


class TestHandleVoiceSuggestionRequest:
    def test_detects_suggest(self) -> None:
        assert handle_voice_suggestion_request("Can you suggest some?") is True

    def test_detects_options(self) -> None:
        assert handle_voice_suggestion_request("What are the options?") is True

    def test_detects_which_voice(self) -> None:
        assert handle_voice_suggestion_request("which voice should I use?") is True

    def test_detects_recommend(self) -> None:
        assert handle_voice_suggestion_request("What do you recommend?") is True

    def test_detects_voice_options(self) -> None:
        assert handle_voice_suggestion_request("Show me voice options") is True

    def test_does_not_detect_normal_message(self) -> None:
        assert handle_voice_suggestion_request("I want booking capabilities") is False

    def test_does_not_detect_voice_id(self) -> None:
        assert handle_voice_suggestion_request("Use Elliot") is False

    def test_case_insensitive(self) -> None:
        assert handle_voice_suggestion_request("SUGGEST some voices") is True


class TestVoiceSuggestions:
    def test_contains_common_voices(self) -> None:
        assert "Elliot" in VOICE_SUGGESTIONS
        assert "Savannah" in VOICE_SUGGESTIONS
        assert "Clara" in VOICE_SUGGESTIONS
        assert "Kai" in VOICE_SUGGESTIONS
