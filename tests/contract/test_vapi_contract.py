"""
Contract tests for Vapi adapter.

Verifies that the Vapi adapter complies with tool-contracts.yaml specifications:
- Request/response structure validation
- Error handling for different HTTP status codes
- Timeout and retry behavior
- Secret redaction
- All required operations implemented
"""

from unittest.mock import MagicMock, patch

import pytest

from adapters.base import AdapterReceipt
from adapters.vapi import VapiAdapter
from shared.errors import (
    AuthorizationError,
    ConflictError,
    PermanentError,
    TransientError,
    ValidationError,
)


@pytest.fixture
def vapi_adapter() -> VapiAdapter:
    """Create a Vapi adapter instance with mocked credentials."""
    with patch.dict("os.environ", {"VAPI_API_KEY": "test_api_key"}):
        return VapiAdapter()


@pytest.fixture
def mock_assistant_response() -> dict:
    """Mock assistant response matching VapiAssistant schema."""
    return {
        "id": "asst_123456",
        "name": "Test Assistant",
        "model": {
            "provider": "openai",
            "model": "gpt-4",
            "messages": [{"role": "system", "content": "You are a helpful assistant."}],
        },
        "voice": {"provider": "11labs", "voiceId": "voice_123"},
        "orgId": "org_123",
        "createdAt": "2024-01-01T00:00:00Z",
        "updatedAt": "2024-01-01T00:00:00Z",
    }


@pytest.fixture
def mock_tool_response() -> dict:
    """Mock tool response matching VapiTool schema."""
    return {
        "id": "tool_123456",
        "type": "function",
        "function": {
            "name": "get_weather",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        },
        "server": {"url": "https://api.example.com/tools"},
        "orgId": "org_123",
        "createdAt": "2024-01-01T00:00:00Z",
        "updatedAt": "2024-01-01T00:00:00Z",
    }


class TestVapiAssistantOperations:
    """Test Vapi assistant operations against contract."""

    def test_create_assistant_success(
        self, vapi_adapter: VapiAdapter, mock_assistant_response: dict
    ) -> None:
        """Test successful assistant creation."""
        payload = {
            "name": "Test Assistant",
            "model": {
                "provider": "openai",
                "model": "gpt-4",
                "messages": [{"role": "system", "content": "You are a helpful assistant."}],
            },
            "voice": {"provider": "11labs", "voiceId": "voice_123"},
        }

        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = mock_assistant_response
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = vapi_adapter.create_assistant(payload)

            # Verify receipt structure
            assert isinstance(receipt, AdapterReceipt)
            assert receipt.platform == "vapi"
            assert receipt.operation == "create_assistant"
            assert receipt.remote_id == "asst_123456"
            assert receipt.status == "success"
            assert receipt.can_retry is False

            # Verify request was made correctly
            mock_request.assert_called_once()
            call_args = mock_request.call_args
            assert call_args[1]["url"] == "https://api.vapi.ai/assistant"
            assert call_args[1]["method"] == "POST"
            assert "Authorization" in call_args[1]["headers"]
            assert call_args[1]["headers"]["Authorization"] == "Bearer test_api_key"

    def test_create_assistant_missing_required_fields(self, vapi_adapter: VapiAdapter) -> None:
        """Test assistant creation with missing required fields."""
        invalid_payloads = [
            {},  # Empty
            {"name": "Test"},  # Missing model and voice
            {"name": "Test", "model": {}},  # Missing voice
            {"name": "Test", "voice": {}},  # Missing model
        ]

        for payload in invalid_payloads:
            with pytest.raises(ValidationError):
                vapi_adapter.create_assistant(payload)

    def test_get_assistant_success(
        self, vapi_adapter: VapiAdapter, mock_assistant_response: dict
    ) -> None:
        """Test successful assistant retrieval."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_assistant_response
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = vapi_adapter.get_assistant("asst_123456")

            assert receipt.platform == "vapi"
            assert receipt.operation == "get_assistant"
            assert receipt.remote_id == "asst_123456"
            assert receipt.can_retry is True

    def test_get_assistant_not_found(self, vapi_adapter: VapiAdapter) -> None:
        """Test assistant retrieval with 404 error."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.json.return_value = {"error": "Assistant not found"}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            with pytest.raises(PermanentError) as exc_info:
                vapi_adapter.get_assistant("asst_nonexistent")

            assert "404" in str(exc_info.value)

    def test_update_assistant_success(
        self, vapi_adapter: VapiAdapter, mock_assistant_response: dict
    ) -> None:
        """Test successful assistant update."""
        payload = {"name": "Updated Assistant"}

        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            updated_response = mock_assistant_response.copy()
            updated_response["name"] = "Updated Assistant"
            mock_response.json.return_value = updated_response
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = vapi_adapter.update_assistant("asst_123456", payload)

            assert receipt.platform == "vapi"
            assert receipt.operation == "update_assistant"
            assert receipt.can_retry is False

    def test_delete_assistant_success(
        self, vapi_adapter: VapiAdapter, mock_assistant_response: dict
    ) -> None:
        """Test successful assistant deletion."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_assistant_response
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = vapi_adapter.delete_assistant("asst_123456")

            assert receipt.platform == "vapi"
            assert receipt.operation == "delete_assistant"
            assert receipt.can_retry is True  # Deletion is idempotent


class TestVapiToolOperations:
    """Test Vapi tool operations against contract."""

    def test_create_tool_success(self, vapi_adapter: VapiAdapter, mock_tool_response: dict) -> None:
        """Test successful tool creation."""
        payload = {
            "type": "function",
            "function": {
                "name": "get_weather",
                "parameters": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"],
                },
            },
            "server": {"url": "https://api.example.com/tools"},
        }

        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = mock_tool_response
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = vapi_adapter.create_tool(payload)

            assert receipt.platform == "vapi"
            assert receipt.operation == "create_tool"
            assert receipt.remote_id == "tool_123456"

    def test_create_tool_invalid_server_url(self, vapi_adapter: VapiAdapter) -> None:
        """Test tool creation with non-HTTPS server URL."""
        payload = {
            "type": "function",
            "function": {
                "name": "get_weather",
                "parameters": {"type": "object", "properties": {}},
            },
            "server": {"url": "http://insecure.example.com/tools"},  # HTTP not HTTPS
        }

        with pytest.raises(ValidationError) as exc_info:
            vapi_adapter.create_tool(payload)

        assert "HTTPS" in str(exc_info.value)

    def test_list_tools_success(self, vapi_adapter: VapiAdapter, mock_tool_response: dict) -> None:
        """Test successful tool listing."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [mock_tool_response]
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = vapi_adapter.list_tools()

            assert receipt.platform == "vapi"
            assert receipt.operation == "list_tools"
            assert "tools" in receipt.response_data
            assert len(receipt.response_data["tools"]) == 1

    def test_get_tool_success(self, vapi_adapter: VapiAdapter, mock_tool_response: dict) -> None:
        """Test successful tool retrieval."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_tool_response
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = vapi_adapter.get_tool("tool_123456")

            assert receipt.platform == "vapi"
            assert receipt.operation == "get_tool"
            assert receipt.remote_id == "tool_123456"


class TestVapiPhoneOperations:
    """Test Vapi phone number operations against contract."""

    def test_assign_phone_number_success(self, vapi_adapter: VapiAdapter) -> None:
        """Test successful phone number assignment."""
        mock_response_data = {
            "id": "phone_123456",
            "number": "+15551234567",
            "assistantId": "asst_123456",
        }

        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = vapi_adapter.assign_phone_number("phone_123456", "asst_123456")

            assert receipt.platform == "vapi"
            assert receipt.operation == "assign_phone_number"
            assert receipt.remote_id == "phone_123456"

    def test_unassign_phone_number_success(self, vapi_adapter: VapiAdapter) -> None:
        """Test successful phone number unassignment."""
        mock_response_data = {
            "id": "phone_123456",
            "number": "+15551234567",
            "assistantId": None,
        }

        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = vapi_adapter.assign_phone_number("phone_123456", None)

            assert receipt.platform == "vapi"
            assert receipt.operation == "assign_phone_number"


class TestVapiErrorHandling:
    """Test Vapi adapter error handling."""

    def test_unauthorized_error(self, vapi_adapter: VapiAdapter) -> None:
        """Test handling of 401 Unauthorized."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.json.return_value = {"error": "Invalid API key"}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            with pytest.raises(AuthorizationError):
                vapi_adapter.get_assistant("asst_123456")

    def test_conflict_error(self, vapi_adapter: VapiAdapter) -> None:
        """Test handling of 409 Conflict."""
        payload = {"name": "Test Assistant", "model": {}, "voice": {}}

        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 409
            mock_response.json.return_value = {"error": "Resource already exists"}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            # Note: create_assistant has validation, so we patch that too
            with patch.object(vapi_adapter, "_validate_assistant_create_payload"):
                with pytest.raises(ConflictError):
                    vapi_adapter.create_assistant(payload)

    def test_server_error_transient(self, vapi_adapter: VapiAdapter) -> None:
        """Test handling of 500 Server Error as transient."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.json.return_value = {"error": "Internal server error"}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            with pytest.raises(TransientError):
                vapi_adapter.get_assistant("asst_123456")

    def test_timeout_handling(self, vapi_adapter: VapiAdapter) -> None:
        """Test timeout handling."""
        import requests

        with patch("requests.Session.request") as mock_request:
            mock_request.side_effect = requests.Timeout("Connection timeout")

            with pytest.raises(TransientError):
                vapi_adapter.get_assistant("asst_123456")


class TestVapiSecretRedaction:
    """Test that API keys are never exposed in logs or receipts."""

    def test_api_key_not_in_receipt(
        self, vapi_adapter: VapiAdapter, mock_assistant_response: dict
    ) -> None:
        """Test that API key is not included in receipt."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_assistant_response
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = vapi_adapter.get_assistant("asst_123456")

            # Convert receipt to string to check for key leakage
            receipt_str = str(receipt.response_data)
            assert "test_api_key" not in receipt_str
            assert vapi_adapter.api_key not in receipt_str

    def test_api_key_not_in_error_messages(self, vapi_adapter: VapiAdapter) -> None:
        """Test that API key is not included in error messages."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.json.return_value = {"error": "Invalid API key"}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            try:
                vapi_adapter.get_assistant("asst_123456")
            except Exception as e:
                error_str = str(e)
                assert "test_api_key" not in error_str
                assert vapi_adapter.api_key not in error_str
