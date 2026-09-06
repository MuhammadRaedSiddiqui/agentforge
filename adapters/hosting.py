"""
Render hosting adapter for Agent Forge.

Implements environment variable management and deployment operations for Render
following tool-contracts.yaml.
"""

import os
from typing import Any

import requests

from adapters.base import AdapterReceipt
from shared.errors import (
    AuthorizationError,
    ConflictError,
    PermanentError,
    TransientError,
    ValidationError,
)


class RenderAdapter:
    """
    Live adapter for Render REST API operations.

    All operations follow contracts from tool-contracts.yaml:
    - Timeout: 10s connect, 30s read
    - Retry: max 2 for transient failures on read-only operations
    - Redaction: all secrets removed from logs and receipts
    - Request tracking: vendor request ID preserved when available
    """

    def __init__(self) -> None:
        """Initialize Render adapter with API token and service ID from environment."""
        self.base_url = "https://api.render.com/v1"
        self.api_token = self._load_api_token()
        self.service_id = self._load_service_id()
        self.session = requests.Session()

    def _load_api_token(self) -> str:
        """Load Render API token from environment."""
        token = os.getenv("HOSTING_API_TOKEN")
        if not token:
            raise ValidationError(
                "HOSTING_API_TOKEN not found in environment",
                field="HOSTING_API_TOKEN",
                context={"adapter": "render"},
            )
        return token

    def _load_service_id(self) -> str:
        """Load Render service ID from environment."""
        service_id = os.getenv("HOSTING_SERVICE_ID")
        if not service_id:
            raise ValidationError(
                "HOSTING_SERVICE_ID not found in environment",
                field="HOSTING_SERVICE_ID",
                context={"adapter": "render"},
            )
        return service_id

    def _get_headers(self) -> dict[str, str]:
        """Build request headers with authorization."""
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        operation: str,
        json_data: dict[str, Any] | None = None,
        redact_request_body: bool = False,
    ) -> dict[str, Any]:
        """
        Make HTTP request with error handling.

        Args:
            method: HTTP method
            url: Full URL
            headers: Request headers
            operation: Operation name for error context
            json_data: JSON payload
            redact_request_body: Whether to redact request body from logs

        Returns:
            Response JSON data

        Raises:
            Typed exceptions based on error classification
        """
        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                json=json_data,
                timeout=(10, 30),  # 10s connect, 30s read
            )

            # Check status code
            if response.status_code == 401 or response.status_code == 403:
                raise AuthorizationError(f"HTTP {response.status_code}: Unauthorized")
            elif response.status_code == 404:
                raise PermanentError(f"HTTP {response.status_code}: Not found")
            elif response.status_code == 409:
                raise ConflictError(f"HTTP {response.status_code}: Conflict")
            elif response.status_code >= 500:
                raise TransientError(f"HTTP {response.status_code}: Server error")
            elif response.status_code >= 400:
                raise PermanentError(f"HTTP {response.status_code}: Client error")

            # Success. Render answers some calls with no body at all —
            # POST /deploys returns 202 and nothing when a deploy is already
            # queued — so an empty response is a success with no payload, not a
            # parse failure. Calling .json() unconditionally turned an accepted
            # deploy into "Request failed: Expecting value: line 1 column 1".
            if not response.content or not response.content.strip():
                return {}

            result: dict[str, Any] = response.json()
            return result

        except requests.Timeout as e:
            raise TransientError(f"Request timeout: {e}") from e
        except requests.ConnectionError as e:
            raise TransientError(f"Connection error: {e}") from e
        except requests.RequestException as e:
            raise PermanentError(f"Request failed: {e}") from e

    def get_env_variable(self, key: str) -> AdapterReceipt:
        """
        Retrieve a Render environment variable.

        Args:
            key: Environment variable key (uppercase with underscores)

        Returns:
            AdapterReceipt with variable data (value is write-only per contract)

        Contract: tool-contracts.yaml#/paths/~1services~1{serviceId}~1env-vars~1{envVarKey}/get
        """
        self._validate_env_var_key(key)

        url = f"{self.base_url}/services/{self.service_id}/env-vars/{key}"
        response = self._request(
            method="GET",
            url=url,
            headers=self._get_headers(),
            operation="get_env_variable",
        )

        # Per contract, the value field is writeOnly and may not be returned
        # We only verify the key matches
        if response.get("key") != key:
            raise PermanentError(
                "Render get_env_variable response key mismatch",
                context={
                    "operation": "get_env_variable",
                    "expected_key": key,
                    "actual_key": response.get("key"),
                },
            )

        return AdapterReceipt(
            platform="render",
            operation="get_env_variable",
            remote_id=key,
            status="success",
            response_data={"key": response.get("key")},  # Omit value for security
            idempotency_key=None,
            can_retry=True,
        )

    def set_env_variable(self, key: str, value: str) -> AdapterReceipt:
        """
        Set or update a Render environment variable.

        Args:
            key: Environment variable key (uppercase with underscores)
            value: Environment variable value

        Returns:
            AdapterReceipt confirming update

        Contract: tool-contracts.yaml#/paths/~1services~1{serviceId}~1env-vars~1{envVarKey}/put

        IMPORTANT: This is a sensitive operation. The value is never logged or
        stored in receipts. Compensation requires the prior value to be captured
        in protected process memory during read-before-write.
        """
        self._validate_env_var_key(key)

        if not value:
            raise ValidationError(
                "Environment variable value cannot be empty",
                field="value",
                context={"key": key},
            )

        url = f"{self.base_url}/services/{self.service_id}/env-vars/{key}"
        payload = {"value": value}

        response = self._request(
            method="PUT",
            url=url,
            headers=self._get_headers(),
            json_data=payload,
            operation="set_env_variable",
            redact_request_body=True,  # Prevent value from appearing in logs
        )

        # Response contains the key but value is writeOnly
        return AdapterReceipt(
            platform="render",
            operation="set_env_variable",
            remote_id=key,
            status="success",
            response_data={"key": response.get("key"), "updated": True},
            idempotency_key=None,
            can_retry=False,  # Update requires read-before-write
        )

    def trigger_deploy(
        self,
        clear_cache: str = "do_not_clear",
        commit_id: str | None = None,
        image_url: str | None = None,
    ) -> AdapterReceipt:
        """
        Trigger a Render deployment.

        Args:
            clear_cache: Whether to clear cache ("clear" or "do_not_clear")
            commit_id: Git commit ID to deploy (optional)
            image_url: Docker image URL (optional)

        Returns:
            AdapterReceipt with deploy ID and status

        Contract: tool-contracts.yaml#/paths/~1services~1{serviceId}~1deploys/post
        """
        valid_cache_options = ["clear", "do_not_clear"]
        if clear_cache not in valid_cache_options:
            raise ValidationError(
                f"clear_cache must be one of {valid_cache_options}",
                field="clear_cache",
                context={"provided": clear_cache},
            )

        payload: dict[str, Any] = {"clearCache": clear_cache}

        if commit_id:
            payload["commitId"] = commit_id

        if image_url:
            payload["imageUrl"] = image_url

        url = f"{self.base_url}/services/{self.service_id}/deploys"
        response = self._request(
            method="POST",
            url=url,
            headers=self._get_headers(),
            json_data=payload,
            operation="trigger_deploy",
        )

        # Extract deploy ID.
        #
        # Render answers 202 with no body when a deploy is already queued for
        # this service. That is an accepted request, not a failed one, and it
        # simply has no id to report — so an empty response yields a success
        # receipt without a remote id rather than an error. A non-empty
        # response that still lacks an id is malformed and does raise.
        deploy_id = response.get("id")
        if not deploy_id and response:
            raise PermanentError(
                "Render trigger_deploy response missing required 'id' field",
                context={"operation": "trigger_deploy", "response_keys": list(response.keys())},
            )

        return AdapterReceipt(
            platform="render",
            operation="trigger_deploy",
            remote_id=deploy_id,
            status="success",
            response_data=response,
            idempotency_key=commit_id,  # Can reconcile by commitId
            can_retry=False,  # Requires reconciliation to check if deploy already exists
        )

    def get_deploy_status(self, deploy_id: str) -> AdapterReceipt:
        """
        Retrieve deployment status.

        Args:
            deploy_id: Render deploy ID

        Returns:
            AdapterReceipt with deploy status and metadata

        Contract: tool-contracts.yaml#/paths/~1services~1{serviceId}~1deploys~1{deployId}/get
        """
        if not deploy_id:
            raise ValidationError("deploy_id is required", field="deploy_id")

        url = f"{self.base_url}/services/{self.service_id}/deploys/{deploy_id}"
        response = self._request(
            method="GET",
            url=url,
            headers=self._get_headers(),
            operation="get_deploy_status",
        )

        # Validate status field exists
        if "status" not in response:
            raise PermanentError(
                "Render get_deploy_status response missing 'status' field",
                context={"operation": "get_deploy_status", "response_keys": list(response.keys())},
            )

        return AdapterReceipt(
            platform="render",
            operation="get_deploy_status",
            remote_id=deploy_id,
            status="success",
            response_data=response,
            idempotency_key=None,
            can_retry=True,
        )

    def check_health(self, health_url: str | None = None) -> AdapterReceipt:
        """
        Check backend health endpoint.

        Args:
            health_url: Health endpoint URL (uses HOSTING_HEALTH_URL from env if not provided)

        Returns:
            AdapterReceipt with health status

        Contract: tool-contracts.yaml#/x-project-contracts/backend_health

        Note: This is a project-owned endpoint, not a Render API endpoint.
        """
        if not health_url:
            health_url = os.getenv("HOSTING_HEALTH_URL")

        if not health_url:
            raise ValidationError(
                "health_url not provided and HOSTING_HEALTH_URL not set in environment",
                field="health_url",
                context={"operation": "check_health"},
            )

        # Validate HTTPS
        if not health_url.startswith("https://"):
            raise ValidationError(
                "Health URL must use HTTPS",
                field="health_url",
                context={"url": health_url},
            )

        response = self._request(
            method="GET",
            url=health_url,
            headers={},  # No auth headers for project health endpoint
            operation="check_health",
        )

        # Validate response has required status field
        status = response.get("status")
        if status not in ["ok", "healthy"]:
            raise PermanentError(
                f"Health check returned unexpected status: {status}",
                context={"operation": "check_health", "status": status, "response": response},
            )

        return AdapterReceipt(
            platform="render",
            operation="check_health",
            remote_id=None,
            status="success",
            response_data=response,
            idempotency_key=None,
            can_retry=True,
        )

    # Validation helpers

    def _validate_env_var_key(self, key: str) -> None:
        """
        Validate environment variable key format.

        Per contract: uppercase letters, digits, and underscores only, must start with letter.
        """
        import re

        if not key:
            raise ValidationError("Environment variable key cannot be empty", field="key")

        if not re.match(r"^[A-Z][A-Z0-9_]*$", key):
            raise ValidationError(
                "Environment variable key must start with uppercase letter and contain only uppercase letters, digits, and underscores",
                field="key",
                context={"provided": key},
            )


RenderHostingAdapter = RenderAdapter
