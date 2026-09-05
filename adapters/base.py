"""
Base HTTP adapter for external platform integrations.

Provides common functionality for timeouts, retry classification,
redaction, request ID tracking, and typed receipts.
"""

import time
from dataclasses import dataclass
from typing import Any

import requests

from shared.errors import (
    AmbiguousOutcomeError,
    AuthorizationError,
    ConflictError,
    PermanentError,
    TransientError,
)
from shared.redaction import redact_dict, sanitize_url


@dataclass
class AdapterReceipt:
    """
    Typed receipt for an adapter operation.

    Returned by all adapter operations to provide evidence of execution.
    """

    platform: str  # Platform name (vapi, make, render, etc.)
    operation: str  # Operation name (create_assistant, etc.)
    remote_id: str | None  # Remote resource ID
    status: str  # Operation status (success, failed, etc.)
    response_data: dict[str, Any]  # Response data from operation
    idempotency_key: str | None = None  # Idempotency key if applicable
    can_retry: bool = False  # Whether operation is safe to retry

    def to_dict(self) -> dict[str, Any]:
        """Convert receipt to dictionary for storage."""
        return {
            "platform": self.platform,
            "operation": self.operation,
            "remote_id": self.remote_id,
            "status": self.status,
            "response_data": self.response_data,
            "idempotency_key": self.idempotency_key,
            "can_retry": self.can_retry,
            "success": self.status == "success",
        }

    def __getitem__(self, key: str) -> Any:
        """Provide backwards-compatible dict-style access."""
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        """Provide backwards-compatible dict-style access."""
        return self.to_dict().get(key, default)

    def __len__(self) -> int:
        """Allow basic sized checks for legacy call sites."""
        return len(self.to_dict())


@dataclass
class HTTPReceipt:
    """
    Typed receipt for a successful HTTP operation.

    Contains evidence of the operation and its result.
    Legacy format - prefer AdapterReceipt for new code.
    """

    platform: str
    operation: str
    request_id: str | None
    http_status: int
    remote_resource_id: str | None
    remote_version: str | None
    response_summary: str
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        """Convert receipt to dictionary for storage."""
        return {
            "platform": self.platform,
            "operation": self.operation,
            "request_id": self.request_id,
            "http_status": self.http_status,
            "remote_resource_id": self.remote_resource_id,
            "remote_version": self.remote_version,
            "response_summary": self.response_summary,
            "timestamp": self.timestamp,
        }


class BaseHTTPAdapter:
    """
    Base class for HTTP-based external platform adapters.

    Provides common functionality for all platform integrations.
    """

    # Default timeouts
    DEFAULT_CONNECT_TIMEOUT = 10.0  # seconds
    DEFAULT_READ_TIMEOUT = 30.0  # seconds

    # Retry policy
    MAX_AUTO_RETRIES = 2
    RETRY_DELAY = 1.0  # seconds

    def __init__(
        self,
        platform: str,
        base_url: str,
        api_key: str,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
    ):
        """
        Initialize base HTTP adapter.

        Args:
            platform: Platform name (e.g., "vapi", "make")
            base_url: Base URL for API
            api_key: API key or token
            connect_timeout: Connection timeout in seconds
            read_timeout: Read timeout in seconds
        """
        self.platform = platform
        self.base_url = base_url
        self.api_key = api_key
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout

        # Create session for connection pooling
        self.session = requests.Session()

    def _get_headers(self, additional_headers: dict[str, str] | None = None) -> dict[str, str]:
        """
        Get request headers with authorization.

        Args:
            additional_headers: Optional additional headers

        Returns:
            Dictionary of headers
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "AgentForge/1.0",
        }

        if additional_headers:
            headers.update(additional_headers)

        return headers

    def _classify_error(
        self, response: requests.Response | None, exception: Exception | None
    ) -> tuple[str, Exception]:
        """
        Classify an error into a failure category.

        Args:
            response: HTTP response (if available)
            exception: Exception that occurred

        Returns:
            Tuple of (failure_class, typed_exception)
        """
        # Connection/timeout errors are ambiguous for write operations
        if isinstance(exception, requests.exceptions.Timeout):
            return (
                "ambiguous_outcome",
                AmbiguousOutcomeError(f"Request timeout: {exception}"),
            )

        if isinstance(exception, requests.exceptions.ConnectionError):
            return (
                "ambiguous_outcome",
                AmbiguousOutcomeError(f"Connection error: {exception}"),
            )

        # Response-based classification
        if response is not None:
            status = response.status_code

            # Authorization errors
            if status in (401, 403):
                return ("authorization", AuthorizationError(f"HTTP {status}: Unauthorized"))

            # Conflict errors
            if status == 409:
                return ("conflict", ConflictError(f"HTTP {status}: Conflict"))

            # Rate limiting and service unavailable are transient
            if status in (429, 503):
                return (
                    "transient",
                    TransientError(f"HTTP {status}: Service temporarily unavailable"),
                )

            # Server errors are transient
            if 500 <= status < 600:
                return ("transient", TransientError(f"HTTP {status}: Server error"))

            # Client errors (except conflict) are permanent
            if 400 <= status < 500:
                return ("permanent", PermanentError(f"HTTP {status}: Client error"))

        # Unknown errors are permanent
        return ("permanent", PermanentError(f"Unknown error: {exception}"))

    def _should_retry(self, failure_class: str, is_read_only: bool, attempt: int) -> bool:
        """
        Determine if an operation should be retried.

        Args:
            failure_class: Classified failure type
            is_read_only: Whether operation is read-only
            attempt: Current attempt number (0-indexed)

        Returns:
            True if should retry
        """
        # No retry if we've exceeded max attempts
        if attempt >= self.MAX_AUTO_RETRIES:
            return False

        # Always retry read-only transient failures
        if is_read_only and failure_class == "transient":
            return True

        # Never auto-retry ambiguous outcomes for write operations
        if not is_read_only and failure_class == "ambiguous_outcome":
            return False

        # Retry transient failures for proven idempotent operations (caller must
        # explicitly mark as idempotent); never retry permanent, authorization,
        # or conflict errors.
        return failure_class == "transient"

    def _make_request(
        self,
        method: str,
        endpoint: str,
        operation: str,
        is_read_only: bool = False,
        is_idempotent: bool = False,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        additional_headers: dict[str, str] | None = None,
    ) -> HTTPReceipt:
        """
        Make an HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            endpoint: API endpoint path
            operation: Operation name for receipt
            is_read_only: Whether operation is read-only
            is_idempotent: Whether operation is idempotent
            json_data: JSON request body
            params: Query parameters
            additional_headers: Additional headers

        Returns:
            HTTPReceipt with operation result

        Raises:
            Typed exception based on failure classification
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = self._get_headers(additional_headers)

        last_error = None
        last_response = None

        for attempt in range(self.MAX_AUTO_RETRIES + 1):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json_data,
                    params=params,
                    timeout=(self.connect_timeout, self.read_timeout),
                )

                # Raise for bad status codes
                response.raise_for_status()

                # Success - create receipt
                receipt = HTTPReceipt(
                    platform=self.platform,
                    operation=operation,
                    request_id=response.headers.get("X-Request-ID"),
                    http_status=response.status_code,
                    remote_resource_id=self._extract_resource_id(response),
                    remote_version=self._extract_version(response),
                    response_summary=self._create_response_summary(response),
                    timestamp=time.time(),
                )

                return receipt

            except requests.exceptions.RequestException as e:
                last_error = e
                last_response = getattr(e, "response", None)

                # Classify the error
                failure_class, typed_exception = self._classify_error(last_response, e)

                # Check if we should retry
                should_retry = self._should_retry(
                    failure_class, is_read_only or is_idempotent, attempt
                )

                if not should_retry or attempt >= self.MAX_AUTO_RETRIES:
                    # Out of retries or shouldn't retry - raise typed exception
                    raise typed_exception from e

                # Wait before retry with exponential backoff
                time.sleep(self.RETRY_DELAY * (2**attempt))
                continue

        # Should never reach here, but raise last error if we do
        _, typed_exception = self._classify_error(last_response, last_error)
        raise typed_exception

    def _extract_resource_id(self, response: requests.Response) -> str | None:
        """
        Extract resource ID from response (platform-specific).

        Override in subclasses for platform-specific extraction.

        Args:
            response: HTTP response

        Returns:
            Resource ID if found, None otherwise
        """
        try:
            data = response.json()
            id_value = data.get("id")
            if isinstance(id_value, str):
                return id_value
            return None
        except Exception:
            return None

    def _extract_version(self, response: requests.Response) -> str | None:
        """
        Extract version/etag from response (platform-specific).

        Override in subclasses for platform-specific extraction.

        Args:
            response: HTTP response

        Returns:
            Version string if found, None otherwise
        """
        # Try common headers
        return response.headers.get("ETag") or response.headers.get("X-Version")

    def _create_response_summary(self, response: requests.Response) -> str:
        """
        Create a sanitized, bounded summary of the response.

        Args:
            response: HTTP response

        Returns:
            Sanitized summary string
        """
        try:
            data = response.json()
            # Redact sensitive fields
            sanitized = redact_dict(data)

            # Create bounded summary
            import json

            summary = json.dumps(sanitized)

            # Truncate if too long
            max_length = 500
            if len(summary) > max_length:
                summary = summary[:max_length] + "..."

            return summary

        except Exception:
            return f"HTTP {response.status_code}"

    def get_sanitized_url(self) -> str:
        """
        Get sanitized base URL safe for logging.

        Returns:
            Sanitized URL
        """
        return sanitize_url(self.base_url)

    def close(self) -> None:
        """Close the HTTP session."""
        self.session.close()
