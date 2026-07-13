"""
Unit tests for base HTTP adapter.

Tests for timeout, retry classification, redaction, and receipt behavior.
"""

import pytest
import requests
from unittest.mock import Mock, patch

from adapters.base import BaseHTTPAdapter, HTTPReceipt
from shared.errors import (
    AmbiguousOutcomeError,
    AuthorizationError,
    ConflictError,
    PermanentError,
    TransientError,
)


@pytest.mark.unit
class TestBaseHTTPAdapter:
    """Tests for base HTTP adapter functionality."""

    def test_initialization(self) -> None:
        """Should initialize with required parameters."""
        adapter = BaseHTTPAdapter(
            platform="test",
            base_url="https://api.example.com",
            api_key="test_key_123",
        )

        assert adapter.platform == "test"
        assert adapter.base_url == "https://api.example.com"
        assert adapter.api_key == "test_key_123"

    def test_get_headers_includes_authorization(self) -> None:
        """Should include Bearer authorization header."""
        adapter = BaseHTTPAdapter(
            platform="test",
            base_url="https://api.example.com",
            api_key="test_key_123",
        )

        headers = adapter._get_headers()

        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer test_key_123"

    def test_get_headers_includes_content_type(self) -> None:
        """Should include JSON content type."""
        adapter = BaseHTTPAdapter(
            platform="test",
            base_url="https://api.example.com",
            api_key="test_key_123",
        )

        headers = adapter._get_headers()

        assert headers["Content-Type"] == "application/json"

    def test_classify_error_timeout(self) -> None:
        """Timeout errors should be classified as ambiguous."""
        adapter = BaseHTTPAdapter(
            platform="test",
            base_url="https://api.example.com",
            api_key="test_key_123",
        )

        timeout_error = requests.exceptions.Timeout("Request timeout")
        failure_class, typed_error = adapter._classify_error(None, timeout_error)

        assert failure_class == "ambiguous_outcome"
        assert isinstance(typed_error, AmbiguousOutcomeError)

    def test_classify_error_connection_error(self) -> None:
        """Connection errors should be classified as ambiguous."""
        adapter = BaseHTTPAdapter(
            platform="test",
            base_url="https://api.example.com",
            api_key="test_key_123",
        )

        conn_error = requests.exceptions.ConnectionError("Connection failed")
        failure_class, typed_error = adapter._classify_error(None, conn_error)

        assert failure_class == "ambiguous_outcome"
        assert isinstance(typed_error, AmbiguousOutcomeError)

    def test_classify_error_401_unauthorized(self) -> None:
        """401 errors should be classified as authorization."""
        adapter = BaseHTTPAdapter(
            platform="test",
            base_url="https://api.example.com",
            api_key="test_key_123",
        )

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 401

        failure_class, typed_error = adapter._classify_error(mock_response, None)

        assert failure_class == "authorization"
        assert isinstance(typed_error, AuthorizationError)

    def test_classify_error_403_forbidden(self) -> None:
        """403 errors should be classified as authorization."""
        adapter = BaseHTTPAdapter(
            platform="test",
            base_url="https://api.example.com",
            api_key="test_key_123",
        )

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 403

        failure_class, typed_error = adapter._classify_error(mock_response, None)

        assert failure_class == "authorization"
        assert isinstance(typed_error, AuthorizationError)

    def test_classify_error_409_conflict(self) -> None:
        """409 errors should be classified as conflict."""
        adapter = BaseHTTPAdapter(
            platform="test",
            base_url="https://api.example.com",
            api_key="test_key_123",
        )

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 409

        failure_class, typed_error = adapter._classify_error(mock_response, None)

        assert failure_class == "conflict"
        assert isinstance(typed_error, ConflictError)

    def test_classify_error_429_rate_limit(self) -> None:
        """429 errors should be classified as transient."""
        adapter = BaseHTTPAdapter(
            platform="test",
            base_url="https://api.example.com",
            api_key="test_key_123",
        )

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 429

        failure_class, typed_error = adapter._classify_error(mock_response, None)

        assert failure_class == "transient"
        assert isinstance(typed_error, TransientError)

    def test_classify_error_503_service_unavailable(self) -> None:
        """503 errors should be classified as transient."""
        adapter = BaseHTTPAdapter(
            platform="test",
            base_url="https://api.example.com",
            api_key="test_key_123",
        )

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 503

        failure_class, typed_error = adapter._classify_error(mock_response, None)

        assert failure_class == "transient"
        assert isinstance(typed_error, TransientError)

    def test_classify_error_500_server_error(self) -> None:
        """500 errors should be classified as transient."""
        adapter = BaseHTTPAdapter(
            platform="test",
            base_url="https://api.example.com",
            api_key="test_key_123",
        )

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 500

        failure_class, typed_error = adapter._classify_error(mock_response, None)

        assert failure_class == "transient"
        assert isinstance(typed_error, TransientError)

    def test_classify_error_400_client_error(self) -> None:
        """400 errors should be classified as permanent."""
        adapter = BaseHTTPAdapter(
            platform="test",
            base_url="https://api.example.com",
            api_key="test_key_123",
        )

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 400

        failure_class, typed_error = adapter._classify_error(mock_response, None)

        assert failure_class == "permanent"
        assert isinstance(typed_error, PermanentError)

    def test_should_retry_read_only_transient(self) -> None:
        """Should retry read-only transient failures."""
        adapter = BaseHTTPAdapter(
            platform="test",
            base_url="https://api.example.com",
            api_key="test_key_123",
        )

        assert adapter._should_retry("transient", is_read_only=True, attempt=0)

    def test_should_retry_write_ambiguous_no(self) -> None:
        """Should NOT retry write operations with ambiguous outcomes."""
        adapter = BaseHTTPAdapter(
            platform="test",
            base_url="https://api.example.com",
            api_key="test_key_123",
        )

        assert not adapter._should_retry("ambiguous_outcome", is_read_only=False, attempt=0)

    def test_should_retry_max_attempts_exceeded(self) -> None:
        """Should not retry if max attempts exceeded."""
        adapter = BaseHTTPAdapter(
            platform="test",
            base_url="https://api.example.com",
            api_key="test_key_123",
        )

        assert not adapter._should_retry("transient", is_read_only=True, attempt=2)

    def test_should_retry_permanent_error(self) -> None:
        """Should not retry permanent errors."""
        adapter = BaseHTTPAdapter(
            platform="test",
            base_url="https://api.example.com",
            api_key="test_key_123",
        )

        assert not adapter._should_retry("permanent", is_read_only=True, attempt=0)

    def test_should_retry_authorization_error(self) -> None:
        """Should not retry authorization errors."""
        adapter = BaseHTTPAdapter(
            platform="test",
            base_url="https://api.example.com",
            api_key="test_key_123",
        )

        assert not adapter._should_retry("authorization", is_read_only=True, attempt=0)

    def test_extract_resource_id_from_json(self) -> None:
        """Should extract resource ID from JSON response."""
        adapter = BaseHTTPAdapter(
            platform="test",
            base_url="https://api.example.com",
            api_key="test_key_123",
        )

        mock_response = Mock(spec=requests.Response)
        mock_response.json.return_value = {"id": "resource_123", "name": "test"}

        resource_id = adapter._extract_resource_id(mock_response)

        assert resource_id == "resource_123"

    def test_extract_resource_id_missing(self) -> None:
        """Should return None if resource ID not found."""
        adapter = BaseHTTPAdapter(
            platform="test",
            base_url="https://api.example.com",
            api_key="test_key_123",
        )

        mock_response = Mock(spec=requests.Response)
        mock_response.json.return_value = {"name": "test"}

        resource_id = adapter._extract_resource_id(mock_response)

        assert resource_id is None

    def test_get_sanitized_url(self) -> None:
        """Should sanitize URL for logging."""
        adapter = BaseHTTPAdapter(
            platform="test",
            base_url="https://user:password@api.example.com",
            api_key="test_key_123",
        )

        sanitized = adapter.get_sanitized_url()

        assert "password" not in sanitized
        assert "example.com" in sanitized

    def test_http_receipt_to_dict(self) -> None:
        """Should convert receipt to dictionary."""
        receipt = HTTPReceipt(
            platform="test",
            operation="create_resource",
            request_id="req_123",
            http_status=201,
            remote_resource_id="resource_456",
            remote_version="v1",
            response_summary="Created successfully",
            timestamp=1234567890.0,
        )

        receipt_dict = receipt.to_dict()

        assert receipt_dict["platform"] == "test"
        assert receipt_dict["operation"] == "create_resource"
        assert receipt_dict["request_id"] == "req_123"
        assert receipt_dict["http_status"] == 201
        assert receipt_dict["remote_resource_id"] == "resource_456"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
