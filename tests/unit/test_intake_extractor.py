"""Unit tests for orchestrator/intake_extractor.py"""

import json
from unittest.mock import MagicMock

import pytest

from orchestrator.conversation_state import PartialIntakeData
from orchestrator.intake_extractor import (
    DAYS_OF_WEEK,
    EXTRACT_FUNCTION,
    _convert_messages,
    apply_correction,
    apply_extraction,
    extract_from_conversation,
    fallback_extract,
    normalize_business_hours,
)

pytestmark = pytest.mark.unit


class TestBusinessHoursExtraction:
    """business_hours was absent from the extraction schema entirely.

    No provider could populate it, so PartialIntakeData.business_hours was
    always None and every conversational onboarding silently deployed the
    Mon-Fri 09:00-17:00 default no matter what the operator said.
    """

    def test_business_hours_is_in_the_extraction_schema(self) -> None:
        properties = EXTRACT_FUNCTION["function"]["parameters"]["properties"]  # type: ignore[index]
        assert "business_hours" in properties
        assert set(properties["business_hours"]["properties"]) == set(DAYS_OF_WEEK)

    def test_normalizes_partial_week_to_all_seven_days(self) -> None:
        result = normalize_business_hours({"saturday": [{"open": "10:00", "close": "14:00"}]})

        assert result is not None
        assert set(result) == set(DAYS_OF_WEEK)
        assert result["saturday"] == [{"open": "10:00", "close": "14:00"}]
        assert result["monday"] == []

    def test_accepts_title_case_days_and_trims(self) -> None:
        result = normalize_business_hours({" Monday ": [{"open": " 09:00 ", "close": "17:00"}]})

        assert result is not None
        assert result["monday"] == [{"open": "09:00", "close": "17:00"}]

    @pytest.mark.parametrize(
        "value",
        [
            None,
            "Mon-Fri 9-5",
            {},
            {"monday": "09:00-17:00"},
            {"monday": [{"open": "9am", "close": "5pm"}]},
            {"monday": [{"open": "25:00", "close": "17:00"}]},
            {"funday": [{"open": "09:00", "close": "17:00"}]},
        ],
    )
    def test_returns_none_when_nothing_usable(self, value: object) -> None:
        """None makes the caller fall back to its default and say so.

        A half-parsed week is worse than no week: it reads as deliberate.
        """
        assert normalize_business_hours(value) is None

    def test_extraction_result_is_normalized(self) -> None:
        mock = MagicMock()
        mock.provider = "openai"
        tool_call = MagicMock()
        tool_call.function.name = "update_intake"
        tool_call.function.arguments = json.dumps(
            {
                "business_name": "Northgate",
                "business_hours": {"Saturday": [{"open": "10:00", "close": "14:00"}]},
            }
        )
        message = MagicMock()
        message.tool_calls = [tool_call]
        response = MagicMock()
        response.choices = [MagicMock(message=message)]
        mock.create_completion.return_value = response

        extracted = extract_from_conversation(
            [{"role": "user", "parts": ["Northgate, open Saturday 10 to 2"]}], mock
        )

        assert set(extracted["business_hours"]) == set(DAYS_OF_WEEK)
        assert extracted["business_hours"]["saturday"] == [{"open": "10:00", "close": "14:00"}]


class TestExtractFunction:
    def test_function_schema_valid(self) -> None:
        assert EXTRACT_FUNCTION["type"] == "function"
        assert EXTRACT_FUNCTION["function"]["name"] == "update_intake"
        props = EXTRACT_FUNCTION["function"]["parameters"]["properties"]
        assert "org_id" in props
        assert "business_name" in props
        assert "phone_number" in props
        assert "voice_id" in props
        assert "capabilities" in props
        assert "industry" in props
        assert "timezone" in props

    def test_no_required_fields_in_schema(self) -> None:
        assert EXTRACT_FUNCTION["function"]["parameters"]["required"] == []


class TestApplyExtraction:
    def test_fills_empty_fields(self) -> None:
        partial = PartialIntakeData()
        extracted = {"business_name": "Miami Glow Salon", "org_id": "miami_glow_salon"}
        result = apply_extraction(partial, extracted)
        assert result.business_name == "Miami Glow Salon"
        assert result.org_id == "miami_glow_salon"

    def test_does_not_overwrite_existing_field(self) -> None:
        partial = PartialIntakeData(business_name="Original Name")
        extracted = {"business_name": "New Name", "org_id": "new_org"}
        result = apply_extraction(partial, extracted)
        assert result.business_name == "Original Name"
        assert result.org_id == "new_org"

    def test_ignores_empty_values(self) -> None:
        partial = PartialIntakeData()
        extracted = {"business_name": "", "org_id": "valid_org"}
        result = apply_extraction(partial, extracted)
        assert result.business_name is None
        assert result.org_id == "valid_org"

    def test_ignores_none_values(self) -> None:
        partial = PartialIntakeData()
        extracted = {"business_name": None, "org_id": "valid_org"}
        result = apply_extraction(partial, extracted)
        assert result.business_name is None
        assert result.org_id == "valid_org"

    def test_ignores_unknown_fields(self) -> None:
        partial = PartialIntakeData()
        extracted = {"unknown_field": "value", "org_id": "valid"}
        result = apply_extraction(partial, extracted)
        assert result.org_id == "valid"
        assert not hasattr(result, "unknown_field")

    def test_sets_capabilities_list(self) -> None:
        partial = PartialIntakeData()
        extracted = {"capabilities": ["booking", "cancellation"]}
        result = apply_extraction(partial, extracted)
        assert result.capabilities == ["booking", "cancellation"]


class TestApplyCorrection:
    def test_overwrites_existing_value(self) -> None:
        partial = PartialIntakeData(phone_number="+13055551234")
        result = apply_correction(partial, "phone_number", "+13055559999")
        assert result.phone_number == "+13055559999"

    def test_sets_new_value(self) -> None:
        partial = PartialIntakeData()
        result = apply_correction(partial, "voice_id", "rachel")
        assert result.voice_id == "rachel"

    def test_ignores_invalid_field(self) -> None:
        partial = PartialIntakeData(org_id="test")
        result = apply_correction(partial, "nonexistent_field", "value")
        assert result.org_id == "test"


class TestConvertMessages:
    def test_converts_user_message(self) -> None:
        messages = [{"role": "user", "parts": ["Hello there"]}]
        converted = _convert_messages(messages)
        assert converted == [{"role": "user", "content": "Hello there"}]

    def test_converts_model_to_assistant(self) -> None:
        messages = [{"role": "model", "parts": ["Hi!"]}]
        converted = _convert_messages(messages)
        assert converted == [{"role": "assistant", "content": "Hi!"}]

    def test_handles_empty_parts(self) -> None:
        messages = [{"role": "user", "parts": []}]
        converted = _convert_messages(messages)
        assert converted == [{"role": "user", "content": ""}]


class TestExtractFromConversation:
    def test_returns_empty_on_exception(self) -> None:
        mock_model = MagicMock()
        mock_model.create_completion.side_effect = Exception("API error")
        messages = [{"role": "user", "parts": ["Test message"]}]
        result = extract_from_conversation(messages, mock_model)
        assert result == {}

    def test_returns_empty_on_no_tool_calls(self) -> None:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.tool_calls = None
        mock_model.create_completion.return_value = mock_response
        messages = [{"role": "user", "parts": ["Hello"]}]
        result = extract_from_conversation(messages, mock_model)
        assert result == {}

    def test_extracts_from_tool_call(self) -> None:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_tool_call = MagicMock()
        mock_tool_call.function.name = "update_intake"
        mock_tool_call.function.arguments = json.dumps(
            {
                "business_name": "Miami Glow Salon",
                "org_id": "miami_glow_salon",
                "capabilities": ["booking", "cancellation"],
            }
        )
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.tool_calls = [mock_tool_call]
        mock_model.create_completion.return_value = mock_response

        messages = [
            {"role": "user", "parts": ["Set up Miami Glow Salon with booking and cancellation"]}
        ]
        result = extract_from_conversation(messages, mock_model)
        assert result["business_name"] == "Miami Glow Salon"
        assert result["org_id"] == "miami_glow_salon"
        assert result["capabilities"] == ["booking", "cancellation"]

    def test_filters_empty_values_from_extraction(self) -> None:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_tool_call = MagicMock()
        mock_tool_call.function.name = "update_intake"
        mock_tool_call.function.arguments = json.dumps(
            {
                "business_name": "Test",
                "phone_number": "",
                "voice_id": None,
            }
        )
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.tool_calls = [mock_tool_call]
        mock_model.create_completion.return_value = mock_response

        messages = [{"role": "user", "parts": ["My business is Test"]}]
        result = extract_from_conversation(messages, mock_model)
        assert result == {"business_name": "Test"}

    def test_returns_empty_on_empty_response(self) -> None:
        mock_model = MagicMock()
        mock_model.create_completion.return_value = None
        messages = [{"role": "user", "parts": ["test"]}]
        result = extract_from_conversation(messages, mock_model)
        assert result == {}


class TestFallbackExtract:
    """Deterministic regex fallback used when the model refuses tool calls."""

    def test_extracts_all_fields_from_full_message(self) -> None:
        messages = [
            {
                "role": "user",
                "parts": [
                    "I want to onboard a new client called Sunrise Dental Studio. "
                    "The organization ID is sunrise_dental. The business phone number is "
                    "+12025550189. We need: availability check, booking, cancellation with "
                    "24-hour window, rescheduling, and human transfer to the front desk. "
                    "Timezone America/New_York."
                ],
            }
        ]
        result = fallback_extract(messages)
        assert result["org_id"] == "sunrise_dental"
        assert result["business_name"] == "Sunrise Dental Studio"
        assert result["phone_number"] == "+12025550189"
        assert result["timezone"] == "America/New_York"
        assert result["capabilities"] == [
            "availability",
            "booking",
            "cancellation",
            "rescheduling",
            "human_transfer",
        ]

    def test_extracts_voice_from_known_list(self) -> None:
        messages = [{"role": "user", "parts": ["Use the Elliot voice please"]}]
        result = fallback_extract(messages)
        assert result["voice_id"] == "Elliot"

    def test_extracts_voice_case_insensitive(self) -> None:
        messages = [{"role": "user", "parts": ["Use the savannah voice please"]}]
        result = fallback_extract(messages)
        assert result["voice_id"] == "Savannah"

    def test_returns_empty_for_no_match(self) -> None:
        messages = [{"role": "user", "parts": ["Hello there"]}]
        assert fallback_extract(messages) == {}

    def test_ignores_assistant_messages(self) -> None:
        messages = [
            {"role": "user", "parts": ["Set up a salon"]},
            {"role": "model", "parts": ["What voice? +15551234567"]},
        ]
        result = fallback_extract(messages)
        assert "phone_number" not in result

    def test_used_when_model_returns_text_only(self) -> None:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].message.content = "Got it, onboarding now."
        mock_model.provider = "meta"
        mock_model.create_completion.return_value = mock_response

        messages = [
            {
                "role": "user",
                "parts": [
                    "Client called Test Dental, org id test_dental, phone +13055551234, "
                    "capabilities booking and cancellation."
                ],
            }
        ]
        result = extract_from_conversation(messages, mock_model)
        assert result["org_id"] == "test_dental"
        assert result["phone_number"] == "+13055551234"
        assert result["capabilities"] == ["booking", "cancellation"]

    def test_fallback_runs_for_all_providers_as_last_resort(self) -> None:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].message.content = "text"
        mock_model.provider = "openai"
        mock_model.create_completion.return_value = mock_response

        messages = [
            {
                "role": "user",
                "parts": [
                    "Client called Test Dental, org id test_dental, phone +13055551234, "
                    "capabilities booking."
                ],
            }
        ]
        result = extract_from_conversation(messages, mock_model)
        assert result["org_id"] == "test_dental"
        assert result["phone_number"] == "+13055551234"
        assert result["capabilities"] == ["booking"]
