"""
Contract tests for Supabase client adapter.

Verifies that the Supabase client adapter complies with tool-contracts.yaml specifications:
- Table allowlist enforcement (CRITICAL SECURITY BOUNDARY)
- Organization record operations
- Row selection with filters
- Error handling
- PostgREST filter syntax
"""

from unittest.mock import MagicMock, patch

import pytest

from adapters.base import AdapterReceipt
from adapters.supabase_client import ALLOWED_TABLES, SupabaseClientAdapter
from shared.errors import (
    AuthorizationError,
    ConflictError,
    PermanentError,
    TransientError,
    ValidationError,
)


@pytest.fixture
def supabase_adapter() -> SupabaseClientAdapter:
    """Create a Supabase client adapter instance with mocked credentials."""
    with patch.dict(
        "os.environ",
        {
            "SUPABASE_CLIENT_URL": "https://test-project.supabase.co",
            "SUPABASE_CLIENT_SERVICE_ROLE_KEY": "test_service_role_key",
        },
    ):
        return SupabaseClientAdapter()


@pytest.fixture
def mock_org_record() -> dict:
    """Mock organization record response."""
    return {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "organization_id": "test_org",
        "business_name": "Test Organization",
        "timezone": "America/New_York",
        "configuration": {"feature_flags": {"advanced": True}},
        "created_at": "2024-01-01T00:00:00Z",
    }


class TestSupabaseTableAllowlist:
    """Test critical table allowlist enforcement."""

    def test_allowed_table_organizations(self, supabase_adapter: dict) -> None:
        """Test that 'organizations' table is in allowlist."""
        assert "organizations" in ALLOWED_TABLES

    def test_disallowed_table_rejected(self, supabase_adapter: dict) -> None:
        """Test that non-allowlisted tables are rejected."""
        forbidden_tables = [
            "users",
            "accounts",
            "payments",
            "secrets",
            "internal_data",
            "DROP TABLE organizations",  # SQL injection attempt
            "organizations; DROP TABLE users",  # SQL injection attempt
        ]

        for table in forbidden_tables:
            with pytest.raises(ValidationError) as exc_info:
                supabase_adapter.select_rows(table)

            error_msg = str(exc_info.value).lower()
            assert "allowlist" in error_msg or "not in" in error_msg

    def test_table_validation_before_request(self, supabase_adapter: dict) -> None:
        """Test that table validation happens before making any request."""
        # This verifies the security boundary is enforced in code, not database
        with patch("requests.Session.request") as mock_request:
            # If validation is working, request should never be called
            with pytest.raises(ValidationError):
                supabase_adapter.select_rows("forbidden_table")

            # Verify no request was made
            mock_request.assert_not_called()


class TestSupabaseSelectOperations:
    """Test Supabase row selection operations."""

    def test_select_rows_success(self, supabase_adapter: dict, mock_org_record: dict) -> None:
        """Test successful row selection."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [mock_org_record]
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = supabase_adapter.select_rows("organizations")

            # Verify receipt structure
            assert isinstance(receipt, AdapterReceipt)
            assert receipt.platform == "supabase_client"
            assert receipt.operation == "select_rows"
            assert receipt.can_retry is True
            assert "rows" in receipt.response_data
            assert receipt.response_data["count"] == 1
            assert receipt.response_data["table"] == "organizations"

            # Verify request structure
            mock_request.assert_called_once()
            call_args = mock_request.call_args
            assert "test-project.supabase.co/rest/v1" in call_args[1]["url"]
            assert call_args[1]["method"] == "GET"
            assert "apikey" in call_args[1]["headers"]
            assert "Authorization" in call_args[1]["headers"]

    def test_select_rows_with_organization_filter(
        self, supabase_adapter: dict, mock_org_record: dict
    ) -> None:
        """Test row selection with organization_id filter."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [mock_org_record]
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = supabase_adapter.select_rows(
                "organizations",
                organization_id="test_org",
            )

            # Verify PostgREST filter syntax in URL
            call_args = mock_request.call_args
            url = call_args[1]["url"]
            assert "organization_id=eq.test_org" in url

    def test_select_rows_with_select_fields(
        self, supabase_adapter: dict, mock_org_record: dict
    ) -> None:
        """Test row selection with specific fields."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [{"organization_id": "test_org"}]
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = supabase_adapter.select_rows(
                "organizations",
                select_fields="organization_id,business_name",
            )

            # Verify select parameter in URL
            call_args = mock_request.call_args
            url = call_args[1]["url"]
            assert "select=organization_id,business_name" in url

    def test_select_rows_empty_result(self, supabase_adapter: dict) -> None:
        """Test handling of empty result set."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = []
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = supabase_adapter.select_rows("organizations")

            assert receipt.response_data["count"] == 0
            assert receipt.response_data["rows"] == []

    def test_select_rows_non_array_response(self, supabase_adapter: dict) -> None:
        """Test handling of invalid response format."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"error": "not an array"}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            with pytest.raises(PermanentError) as exc_info:
                supabase_adapter.select_rows("organizations")

            assert "array" in str(exc_info.value).lower()


class TestSupabaseInsertOperations:
    """Test Supabase organization record insertion."""

    def test_insert_org_record_success(self, supabase_adapter: dict, mock_org_record: dict) -> None:
        """Test successful organization record insertion."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = [mock_org_record]
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = supabase_adapter.insert_org_record(
                organization_id="test_org",
                business_name="Test Organization",
                timezone="America/New_York",
                configuration={"feature_flags": {"advanced": True}},
            )

            # Verify receipt structure
            assert receipt.platform == "supabase_client"
            assert receipt.operation == "insert_org_record"
            assert receipt.remote_id == "test_org"
            assert receipt.idempotency_key == "test_org"  # org_id is immutable
            assert receipt.can_retry is False  # Requires reconciliation

            # Verify request
            call_args = mock_request.call_args
            assert call_args[1]["method"] == "POST"
            assert "/organizations" in call_args[1]["url"]

            # Verify payload
            payload = call_args[1]["json"]
            assert payload["organization_id"] == "test_org"
            assert payload["display_name"] == "Test Organization"
            assert payload["timezone"] == "America/New_York"
            assert payload["metadata"] == {"feature_flags": {"advanced": True}}

    def test_insert_org_record_minimal(self, supabase_adapter: dict, mock_org_record: dict) -> None:
        """Test organization record insertion with only required fields."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = [mock_org_record]
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = supabase_adapter.insert_org_record(
                organization_id="test_org",
                business_name="Test Organization",
            )

            # Verify only required fields in payload
            call_args = mock_request.call_args
            payload = call_args[1]["json"]
            assert "organization_id" in payload
            assert "display_name" in payload
            assert "timezone" not in payload or payload["timezone"] is None
            assert "metadata" not in payload or payload["metadata"] is None

    def test_insert_org_record_missing_required_fields(self, supabase_adapter: dict) -> None:
        """Test that missing required fields are rejected."""
        with pytest.raises(ValidationError):
            supabase_adapter.insert_org_record(
                organization_id="",
                business_name="Test",
            )

        with pytest.raises(ValidationError):
            supabase_adapter.insert_org_record(
                organization_id="test",
                business_name="",
            )

    def test_insert_org_record_invalid_org_id_format(self, supabase_adapter: dict) -> None:
        """Test that invalid organization_id formats are rejected."""
        invalid_org_ids = [
            "UPPERCASE",  # Must be lowercase
            "has-dashes",  # No dashes allowed
            "has spaces",  # No spaces allowed
            "has@special",  # No special chars
            "123start",  # Can't start with number (debatable, but good practice)
        ]

        for invalid_id in invalid_org_ids:
            with pytest.raises(ValidationError) as exc_info:
                supabase_adapter.insert_org_record(
                    organization_id=invalid_id,
                    business_name="Test",
                )

            error_msg = str(exc_info.value).lower()
            assert "organization_id" in error_msg

    def test_insert_org_record_valid_org_id_formats(
        self, supabase_adapter: dict, mock_org_record: dict
    ) -> None:
        """Test that valid organization_id formats are accepted."""
        valid_org_ids = [
            "test_org",
            "testorg",
            "test123",
            "org_123",
            "a",  # Single character
        ]

        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = [mock_org_record]
            mock_response.headers = {}
            mock_request.return_value = mock_response

            for valid_id in valid_org_ids:
                try:
                    supabase_adapter.insert_org_record(
                        organization_id=valid_id,
                        business_name="Test",
                    )
                except ValidationError as e:
                    pytest.fail(f"Valid org_id '{valid_id}' was rejected: {e}")

    def test_insert_org_record_empty_response(self, supabase_adapter: dict) -> None:
        """Test handling of empty response array."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = []  # Empty array
            mock_response.headers = {}
            mock_request.return_value = mock_response

            with pytest.raises(PermanentError) as exc_info:
                supabase_adapter.insert_org_record(
                    organization_id="test_org",
                    business_name="Test",
                )

            assert "empty" in str(exc_info.value).lower()


class TestSupabaseUpdateOperations:
    """Test Supabase organization record update operations."""

    def test_update_org_record_success(self, supabase_adapter: dict, mock_org_record: dict) -> None:
        """Test successful organization record update."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            updated_record = mock_org_record.copy()
            updated_record["business_name"] = "Updated Name"
            mock_response.json.return_value = [updated_record]
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = supabase_adapter.update_org_record(
                organization_id="test_org",
                updates={"business_name": "Updated Name"},
            )

            assert receipt.platform == "supabase_client"
            assert receipt.operation == "update_org_record"
            assert receipt.can_retry is False  # Updates require read-before-write

    def test_update_org_record_immutable_org_id_rejected(self, supabase_adapter: dict) -> None:
        """Test that attempting to update organization_id is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            supabase_adapter.update_org_record(
                organization_id="test_org",
                updates={"organization_id": "new_id"},
            )

        assert "immutable" in str(exc_info.value).lower()

    def test_update_org_record_not_found(self, supabase_adapter: dict) -> None:
        """Test handling of update when record doesn't exist."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = []  # No records updated
            mock_response.headers = {}
            mock_request.return_value = mock_response

            with pytest.raises(PermanentError) as exc_info:
                supabase_adapter.update_org_record(
                    organization_id="nonexistent",
                    updates={"business_name": "Test"},
                )

            assert "not found" in str(exc_info.value).lower()


class TestSupabaseDeleteOperations:
    """Test Supabase organization record deletion (compensation)."""

    def test_delete_org_record_success(self, supabase_adapter: dict, mock_org_record: dict) -> None:
        """Test successful organization record deletion."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [mock_org_record]
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = supabase_adapter.delete_org_record("test_org")

            assert receipt.platform == "supabase_client"
            assert receipt.operation == "delete_org_record"
            assert receipt.can_retry is True  # Deletion is idempotent

    def test_delete_org_record_missing_org_id(self, supabase_adapter: dict) -> None:
        """Test that empty organization_id is rejected."""
        with pytest.raises(ValidationError):
            supabase_adapter.delete_org_record("")


class TestSupabaseErrorHandling:
    """Test Supabase adapter error handling."""

    def test_unauthorized_error(self, supabase_adapter: dict) -> None:
        """Test handling of 401 Unauthorized."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.json.return_value = {"error": "Invalid API key"}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            with pytest.raises(AuthorizationError):
                supabase_adapter.select_rows("organizations")

    def test_forbidden_error(self, supabase_adapter: dict) -> None:
        """Test handling of 403 Forbidden (RLS policy violation)."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 403
            mock_response.json.return_value = {"error": "RLS policy violation"}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            with pytest.raises(AuthorizationError):
                supabase_adapter.select_rows("organizations")

    def test_conflict_error(self, supabase_adapter: dict) -> None:
        """Test handling of 409 Conflict (duplicate key)."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 409
            mock_response.json.return_value = {"error": "Duplicate key"}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            with pytest.raises(ConflictError):
                supabase_adapter.insert_org_record(
                    organization_id="test_org",
                    business_name="Test",
                )

    def test_server_error_transient(self, supabase_adapter: dict) -> None:
        """Test handling of 500 Server Error."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.json.return_value = {"error": "Internal server error"}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            with pytest.raises(TransientError):
                supabase_adapter.select_rows("organizations")


class TestSupabaseSecretProtection:
    """Test that service role keys are never exposed."""

    def test_service_role_key_not_in_receipt(
        self, supabase_adapter: dict, mock_org_record: dict
    ) -> None:
        """Test that service role key is not included in receipt."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [mock_org_record]
            mock_response.headers = {}
            mock_request.return_value = mock_response

            receipt = supabase_adapter.select_rows("organizations")

            receipt_str = str(receipt.response_data)
            assert "test_service_role_key" not in receipt_str
            assert supabase_adapter.service_role_key not in receipt_str

    def test_service_role_key_not_in_error_messages(self, supabase_adapter: dict) -> None:
        """Test that service role key is not included in error messages."""
        with patch("requests.Session.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.json.return_value = {"error": "Invalid key"}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            try:
                supabase_adapter.select_rows("organizations")
            except Exception as e:
                error_str = str(e)
                assert "test_service_role_key" not in error_str
                assert supabase_adapter.service_role_key not in error_str


class TestSupabaseURLValidation:
    """Test Supabase URL validation."""

    def test_https_required(self) -> None:
        """Test that non-HTTPS URLs are rejected."""
        with patch.dict(
            "os.environ",
            {
                "SUPABASE_CLIENT_URL": "http://insecure.supabase.co",
                "SUPABASE_CLIENT_SERVICE_ROLE_KEY": "test_key",
            },
        ):
            with pytest.raises(ValidationError) as exc_info:
                SupabaseClientAdapter()

            assert "HTTPS" in str(exc_info.value)

    def test_missing_url(self) -> None:
        """Test that missing URL raises error."""
        with patch.dict("os.environ", {"SUPABASE_CLIENT_SERVICE_ROLE_KEY": "test_key"}):
            with pytest.raises(ValidationError) as exc_info:
                SupabaseClientAdapter()

            assert "SUPABASE_CLIENT_URL" in str(exc_info.value)

    def test_missing_key(self) -> None:
        """Test that missing service role key raises error."""
        with patch.dict("os.environ", {"SUPABASE_CLIENT_URL": "https://test.supabase.co"}):
            with pytest.raises(ValidationError) as exc_info:
                SupabaseClientAdapter()

            assert "SERVICE_ROLE_KEY" in str(exc_info.value)
