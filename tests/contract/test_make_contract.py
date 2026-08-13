"""
Contract tests for Make adapter.

Verifies that the Make adapter complies with tool-contracts.yaml specifications:
- Request/response structure validation
- Error handling for different HTTP status codes
- Regional zone support (eu1, eu2, us1, us2)
- Blueprint and scenario operations
- Hook operations
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from adapters.base import AdapterReceipt
from adapters.make import MakeAdapter
from shared.errors import (
    AuthorizationError,
    PermanentError,
    TransientError,
    ValidationError,
)


@pytest.fixture
def make_adapter() -> MakeAdapter:
    """Create a Make adapter instance with mocked credentials."""
    with patch.dict(
        "os.environ",
        {
            "MAKE_API_TOKEN": "test_token",
            "MAKE_TEAM_ID": "12345",
            "MAKE_ZONE": "us1",
        },
    ):
        return MakeAdapter()


@pytest.fixture
def mock_scenario_response() -> dict:
    """Mock scenario response matching MakeScenario schema."""
    return {
        "id": 123,
        "name": "Test Scenario",
        "teamId": 12345,
        "isActive": False,
        "isinvalid": False,
        "islocked": False,
        "isPaused": False,
        "scenarioVersion": 1,
        "lastEdit": "2024-01-01T00:00:00Z",
        "scheduling": {"type": "indefinitely"},
    }


@pytest.fixture
def mock_blueprint() -> dict:
    """Mock blueprint matching Make blueprint structure."""
    return {
        "flow": [
            {
                "id": 1,
                "module": "webhook:CustomWebHook",
                "mapper": {},
            }
        ],
        "name": "Test Blueprint",
        "metadata": {},
    }


@pytest.fixture
def mock_hook_response() -> dict:
    """Mock hook response matching MakeHook schema."""
    return {
        "id": 456,
        "name": "Test Hook",
        "teamId": 12345,
        "typeName": "CustomWebHook",
        "url": "https://hook.us1.make.com/abc123",
        "enabled": True,
        "gone": False,
        "queueCount": 0,
    }


class TestMakeScenarioOperations:
    """Test Make scenario operations against contract."""

    def test_create_scenario_success(
        self, make_adapter: MakeAdapter, mock_blueprint: dict, mock_scenario_response: dict
    ) -> None:
        """Test successful scenario creation."""
        scheduling = {"type": "indefinitely"}

        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"scenario": mock_scenario_response}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = make_adapter.create_scenario(mock_blueprint, scheduling)

            # Verify receipt structure
            assert isinstance(receipt, AdapterReceipt)
            assert receipt.platform == "make"
            assert receipt.operation == "create_scenario"
            assert receipt.remote_id == "123"
            assert receipt.status == "success"
            assert receipt.can_retry is False

            # Verify request structure
            mock_request.assert_called_once()
            call_args = mock_request.call_args
            assert "us1.make.com" in call_args[1]["url"]
            assert call_args[1]["method"] == "POST"
            assert "Authorization" in call_args[1]["headers"]
            assert call_args[1]["headers"]["Authorization"] == "Token test_token"

    def test_create_scenario_invalid_blueprint(self, make_adapter: MakeAdapter) -> None:
        """Test scenario creation with invalid blueprint."""
        invalid_blueprints = [
            {},  # Missing required fields
            {"name": "Test"},  # Missing flow
            {"flow": []},  # Missing name
            {"flow": "not-an-array", "name": "Test"},  # flow not an array
        ]

        for blueprint in invalid_blueprints:
            with pytest.raises(ValidationError):
                make_adapter.create_scenario(blueprint, {"type": "indefinitely"})

    def test_create_scenario_does_not_silently_degrade_on_blueprint_error(
        self, make_adapter: MakeAdapter, mock_blueprint: dict
    ) -> None:
        """Test blueprint creation failures propagate instead of silently
        degrading to a single-module webhook stub.

        Regression: the adapter used to retry with a minimal one-module
        blueprint on IM007/SC400 errors, which produced scenarios with only a
        webhook module while the orchestrator reported success.
        """
        from shared.errors import PermanentError

        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.text = "IM007 Module not found 'supabase:searchRows' version '1'"
            mock_response.headers = {}
            mock_request.return_value = mock_response

            with pytest.raises(PermanentError):
                make_adapter.create_scenario(mock_blueprint, {"type": "immediately"})

            mock_request.assert_called_once()
            call_args = mock_request.call_args
            assert call_args[1]["method"] == "POST"

    def test_update_scenario_blueprint_uses_patch(self, make_adapter: MakeAdapter) -> None:
        """Test blueprint update uses PATCH /scenarios/{id} with blueprint as string."""
        blueprint = {
            "name": "Test",
            "flow": [{"id": 1, "module": "gateway:CustomWebHook", "version": 1, "mapper": {}}],
            "metadata": {"version": 1},
        }

        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"scenario": {"id": 123, "name": "Test"}}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = make_adapter.update_scenario_blueprint(123, blueprint, confirmed=True)

            assert receipt.operation == "update_scenario_blueprint"
            assert receipt.remote_id == "123"
            call_args = mock_request.call_args
            assert call_args[1]["method"] == "PATCH"
            assert "/scenarios/123" in call_args[1]["url"]
            assert "/blueprint" not in call_args[1]["url"]
            import json

            payload_blueprint = json.loads(call_args[1]["json"]["blueprint"])
            assert payload_blueprint["name"] == "Test"

    def test_get_scenario_success(
        self, make_adapter: MakeAdapter, mock_scenario_response: dict
    ) -> None:
        """Test successful scenario retrieval."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"scenario": mock_scenario_response}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = make_adapter.get_scenario(123)

            assert receipt.platform == "make"
            assert receipt.operation == "get_scenario"
            assert receipt.remote_id == "123"
            assert receipt.can_retry is True

    def test_list_scenarios_success(
        self, make_adapter: MakeAdapter, mock_scenario_response: dict
    ) -> None:
        """Test successful scenario listing."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"scenarios": [mock_scenario_response]}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = make_adapter.list_scenarios()

            assert receipt.platform == "make"
            assert receipt.operation == "list_scenarios"
            assert "scenarios" in receipt.response_data
            assert receipt.response_data["count"] == 1

    def test_list_scenarios_with_filter(
        self, make_adapter: MakeAdapter, mock_scenario_response: dict
    ) -> None:
        """Test scenario listing with active filter."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            active_scenario = mock_scenario_response.copy()
            active_scenario["isActive"] = True
            mock_response.json.return_value = {"scenarios": [active_scenario]}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            make_adapter.list_scenarios(is_active=True)

            # Verify query parameters included filter
            call_args = mock_request.call_args
            assert "isActive=true" in call_args[1]["url"]

    def test_delete_scenario_success(self, make_adapter: MakeAdapter) -> None:
        """Test successful scenario deletion."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"scenario": 123}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = make_adapter.delete_scenario(123)

            assert receipt.platform == "make"
            assert receipt.operation == "delete_scenario"
            assert receipt.can_retry is True  # Deletion is idempotent

    def test_activate_scenario_success(self, make_adapter: MakeAdapter) -> None:
        """Test successful scenario activation."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"activated": True}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = make_adapter.activate_scenario(123)

            assert receipt.platform == "make"
            assert receipt.operation == "activate_scenario"
            assert receipt.can_retry is False  # Requires reconciliation

    def test_deactivate_scenario_success(self, make_adapter: MakeAdapter) -> None:
        """Test successful scenario deactivation."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"deactivated": True}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = make_adapter.deactivate_scenario(123)

            assert receipt.platform == "make"
            assert receipt.operation == "deactivate_scenario"
            assert receipt.can_retry is True  # Deactivation is idempotent


class TestMakeBlueprintOperations:
    """Test Make blueprint operations against contract."""

    def test_get_scenario_blueprint_success(
        self, make_adapter: MakeAdapter, mock_blueprint: dict
    ) -> None:
        """Test successful blueprint retrieval."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"response": {"blueprint": mock_blueprint}}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = make_adapter.get_scenario_blueprint(123)

            assert receipt.platform == "make"
            assert receipt.operation == "get_scenario_blueprint"
            assert receipt.can_retry is True


class TestMakeHookOperations:
    """Test Make hook operations against contract."""

    def test_create_hook_success(self, make_adapter: MakeAdapter, mock_hook_response: dict) -> None:
        """Test successful hook creation."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"hook": mock_hook_response}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = make_adapter.create_hook("Test Hook", "CustomWebHook")

            assert receipt.platform == "make"
            assert receipt.operation == "create_hook"
            assert receipt.remote_id == "456"
            assert receipt.can_retry is False

    def test_get_hook_success(self, make_adapter: MakeAdapter, mock_hook_response: dict) -> None:
        """Test successful hook retrieval."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"hook": mock_hook_response}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = make_adapter.get_hook(456)

            assert receipt.platform == "make"
            assert receipt.operation == "get_hook"
            assert receipt.remote_id == "456"

    def test_list_hooks_success(self, make_adapter: MakeAdapter, mock_hook_response: dict) -> None:
        """Test successful hook listing."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"hooks": [mock_hook_response]}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = make_adapter.list_hooks()

            assert receipt.platform == "make"
            assert receipt.operation == "list_hooks"
            assert "hooks" in receipt.response_data
            assert receipt.response_data["count"] == 1

    def test_delete_hook_success(self, make_adapter: MakeAdapter) -> None:
        """Test successful hook deletion."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"hook": 456}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = make_adapter.delete_hook(456)

            assert receipt.platform == "make"
            assert receipt.operation == "delete_hook"
            assert receipt.can_retry is True

    def test_verify_hook_success(self, make_adapter: MakeAdapter) -> None:
        """Test successful hook verification."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "address": "https://hook.us1.make.com/abc123",
                "attached": True,
                "learning": False,
                "gone": False,
            }
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = make_adapter.verify_hook(456)

            assert receipt.platform == "make"
            assert receipt.operation == "verify_hook"
            assert receipt.can_retry is True


class TestMakeZoneSupport:
    """Test Make regional zone support."""

    @pytest.mark.parametrize("zone", ["eu1", "eu2", "us1", "us2"])
    def test_valid_zones(self, zone: Any) -> None:
        """Test that all valid zones are accepted."""
        with patch.dict(
            "os.environ", {"MAKE_API_TOKEN": "test", "MAKE_TEAM_ID": "123", "MAKE_ZONE": zone}
        ):
            adapter = MakeAdapter()
            assert adapter.zone == zone
            assert f"{zone}.make.com" in adapter.base_url

    def test_invalid_zone_rejected(self) -> None:
        """Test that invalid zones are rejected."""
        with patch.dict(
            "os.environ", {"MAKE_API_TOKEN": "test", "MAKE_TEAM_ID": "123", "MAKE_ZONE": "invalid"}
        ):
            with pytest.raises(ValidationError) as exc_info:
                MakeAdapter()
            assert "MAKE_ZONE" in str(exc_info.value)


class TestMakeErrorHandling:
    """Test Make adapter error handling."""

    def test_unauthorized_error(self, make_adapter: MakeAdapter) -> None:
        """Test handling of 401 Unauthorized."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.json.return_value = {"error": "Invalid token"}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            with pytest.raises(AuthorizationError):
                make_adapter.get_scenario(123)

    def test_not_found_error(self, make_adapter: MakeAdapter) -> None:
        """Test handling of 404 Not Found."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.json.return_value = {"error": "Scenario not found"}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            with pytest.raises(PermanentError):
                make_adapter.get_scenario(99999)

    def test_server_error_transient(self, make_adapter: MakeAdapter) -> None:
        """Test handling of 500 Server Error."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.json.return_value = {"error": "Internal server error"}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            with pytest.raises(TransientError):
                make_adapter.get_scenario(123)


class TestMakeValidation:
    """Test Make adapter input validation."""

    def test_invalid_scenario_id(self, make_adapter: MakeAdapter) -> None:
        """Test that invalid scenario IDs are rejected."""
        invalid_ids = [0, -1, None, "not-a-number"]

        for invalid_id in invalid_ids:
            with pytest.raises((ValidationError, TypeError)):
                make_adapter.get_scenario(invalid_id)

    def test_invalid_hook_id(self, make_adapter: MakeAdapter) -> None:
        """Test that invalid hook IDs are rejected."""
        invalid_ids = [0, -1, None, "not-a-number"]

        for invalid_id in invalid_ids:
            with pytest.raises((ValidationError, TypeError)):
                make_adapter.get_hook(invalid_id)

    def test_empty_hook_name(self, make_adapter: MakeAdapter) -> None:
        """Test that empty hook names are rejected."""
        with pytest.raises(ValidationError):
            make_adapter.create_hook("", "CustomWebHook")


class TestMakeSecretRedaction:
    """Test that API tokens are never exposed."""

    def test_token_not_in_receipt(
        self, make_adapter: MakeAdapter, mock_scenario_response: dict
    ) -> None:
        """Test that API token is not included in receipt."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"scenario": mock_scenario_response}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = make_adapter.get_scenario(123)

            receipt_str = str(receipt.response_data)
            assert "test_token" not in receipt_str
            assert make_adapter.api_token not in receipt_str

    def test_token_not_in_error_messages(self, make_adapter: MakeAdapter) -> None:
        """Test that API token is not included in error messages."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.json.return_value = {"error": "Invalid token"}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            try:
                make_adapter.get_scenario(123)
            except Exception as e:
                error_str = str(e)
                assert "test_token" not in error_str
                assert make_adapter.api_token not in error_str
