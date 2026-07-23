"""Unit tests for orchestrator/intake_extractor.py"""

import json
from unittest.mock import MagicMock, patch

import pytest
from orchestrator.conversation_state import PartialIntakeData
from orchestrator.intake_extractor import (
    EXTRACT_FUNCTION,
    apply_correction,
    apply_extraction,
    extract_from_conversation,
    _convert_messages,
)


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
        mock_tool_call.function.arguments = json.dumps({
            "business_name": "Miami Glow Salon",
            "org_id": "miami_glow_salon",
            "capabilities": ["booking", "cancellation"],
        })
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.tool_calls = [mock_tool_call]
        mock_model.create_completion.return_value = mock_response

        messages = [{"role": "user", "parts": ["Set up Miami Glow Salon with booking and cancellation"]}]
        result = extract_from_conversation(messages, mock_model)
        assert result["business_name"] == "Miami Glow Salon"
        assert result["org_id"] == "miami_glow_salon"
        assert result["capabilities"] == ["booking", "cancellation"]

    def test_filters_empty_values_from_extraction(self) -> None:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_tool_call = MagicMock()
        mock_tool_call.function.name = "update_intake"
        mock_tool_call.function.arguments = json.dumps({
            "business_name": "Test",
            "phone_number": "",
            "voice_id": None,
        })
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
