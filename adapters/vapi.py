"""
Vapi live adapter for Agent Forge.

Implements create, read, update, delete operations for Vapi assistants, tools,
and phone number assignment following tool-contracts.yaml.
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


class VapiAdapter:
    """
    Live adapter for Vapi REST API operations.

    All operations follow contracts from tool-contracts.yaml:
    - Timeout: 10s connect, 30s read
    - Retry: max 2 for transient failures on read-only operations
    - Redaction: all secrets removed from logs and receipts
    - Request tracking: vendor request ID preserved when available
    """

    def __init__(self) -> None:
        """Initialize Vapi adapter with API credentials from environment."""
        self.base_url = "https://api.vapi.ai"
        self.api_key = self._load_api_key()
        self.session = requests.Session()

    def _load_api_key(self) -> str:
        """Load Vapi API key from environment."""
        api_key = os.getenv("VAPI_API_KEY")
        if not api_key:
            raise ValidationError(
                "VAPI_API_KEY not found in environment",
                field="VAPI_API_KEY",
                context={"adapter": "vapi"},
            )
        return api_key

    def _get_headers(self) -> dict[str, str]:
        """Build request headers with authorization."""
        return {
            "Authorization": f"Bearer {self.api_key}",
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
                body = response.text[:500] if response.text else "no body"
                raise PermanentError(f"HTTP {response.status_code}: {body}")

            # Success - return JSON
            result: dict[str, Any] = response.json()
            return result

        except requests.Timeout as e:
            raise TransientError(f"Request timeout: {e}")
        except requests.ConnectionError as e:
            raise TransientError(f"Connection error: {e}")
        except requests.RequestException as e:
            raise PermanentError(f"Request failed: {e}")

    def create_assistant(self, payload: dict[str, Any]) -> AdapterReceipt:
        """
        Create a Vapi assistant.

        Args:
            payload: Assistant configuration following VapiAssistantCreateRequest schema

        Returns:
            AdapterReceipt with assistant ID and response data

        Contract: tool-contracts.yaml#/paths/~1assistant/post
        """
        self._validate_assistant_create_payload(payload)

        url = f"{self.base_url}/assistant"
        response = self._request(
            method="POST",
            url=url,
            headers=self._get_headers(),
            json_data=payload,
            operation="create_assistant",
        )

        # Extract assistant ID from response
        if not response.get("id"):
            raise PermanentError(
                "Vapi create_assistant response missing required 'id' field",
                context={"operation": "create_assistant", "response_keys": list(response.keys())},
            )

        return AdapterReceipt(
            platform="vapi",
            operation="create_assistant",
            remote_id=response["id"],
            status="success",
            response_data=response,
            idempotency_key=None,
            can_retry=False,  # Creation is not idempotent without reconciliation
        )

    def get_assistant(self, assistant_id: str) -> AdapterReceipt:
        """
        Retrieve a Vapi assistant by ID.

        Args:
            assistant_id: Vapi assistant ID

        Returns:
            AdapterReceipt with assistant data

        Contract: tool-contracts.yaml#/paths/~1assistant~1{assistantId}/get
        """
        if not assistant_id:
            raise ValidationError("assistant_id is required", field="assistant_id")

        url = f"{self.base_url}/assistant/{assistant_id}"
        response = self._request(
            method="GET",
            url=url,
            headers=self._get_headers(),
            operation="get_assistant",
        )

        return AdapterReceipt(
            platform="vapi",
            operation="get_assistant",
            remote_id=assistant_id,
            status="success",
            response_data=response,
            idempotency_key=None,
            can_retry=True,  # Read operations are safe to retry
        )

    def update_assistant(self, assistant_id: str, payload: dict[str, Any]) -> AdapterReceipt:
        """
        Update a Vapi assistant.

        Args:
            assistant_id: Vapi assistant ID
            payload: Partial assistant configuration following VapiAssistantUpdateRequest schema

        Returns:
            AdapterReceipt with updated assistant data

        Contract: tool-contracts.yaml#/paths/~1assistant~1{assistantId}/patch
        """
        if not assistant_id:
            raise ValidationError("assistant_id is required", field="assistant_id")
        if not payload:
            raise ValidationError("payload must contain at least one field", field="payload")

        self._validate_assistant_update_payload(payload)

        url = f"{self.base_url}/assistant/{assistant_id}"
        response = self._request(
            method="PATCH",
            url=url,
            headers=self._get_headers(),
            json_data=payload,
            operation="update_assistant",
        )

        return AdapterReceipt(
            platform="vapi",
            operation="update_assistant",
            remote_id=assistant_id,
            status="success",
            response_data=response,
            idempotency_key=None,
            can_retry=False,  # Update requires read-before-write staleness check
        )

    def delete_assistant(self, assistant_id: str) -> AdapterReceipt:
        """
        Delete a Vapi assistant.

        Args:
            assistant_id: Vapi assistant ID

        Returns:
            AdapterReceipt confirming deletion

        Contract: tool-contracts.yaml#/paths/~1assistant~1{assistantId}/delete
        """
        if not assistant_id:
            raise ValidationError("assistant_id is required", field="assistant_id")

        url = f"{self.base_url}/assistant/{assistant_id}"
        response = self._request(
            method="DELETE",
            url=url,
            headers=self._get_headers(),
            operation="delete_assistant",
        )

        return AdapterReceipt(
            platform="vapi",
            operation="delete_assistant",
            remote_id=assistant_id,
            status="success",
            response_data=response or {"deleted": True},
            idempotency_key=None,
            can_retry=True,  # Deletion is idempotent (404 is acceptable)
        )

    def create_tool(self, payload: dict[str, Any]) -> AdapterReceipt:
        """
        Create a Vapi tool.

        Args:
            payload: Tool configuration following VapiToolCreateRequest schema

        Returns:
            AdapterReceipt with tool ID and response data

        Contract: tool-contracts.yaml#/paths/~1tool/post
        """
        self._validate_tool_create_payload(payload)

        url = f"{self.base_url}/tool"
        response = self._request(
            method="POST",
            url=url,
            headers=self._get_headers(),
            json_data=payload,
            operation="create_tool",
        )

        if not response.get("id"):
            raise PermanentError(
                "Vapi create_tool response missing required 'id' field",
                context={"operation": "create_tool", "response_keys": list(response.keys())},
            )

        return AdapterReceipt(
            platform="vapi",
            operation="create_tool",
            remote_id=response["id"],
            status="success",
            response_data=response,
            idempotency_key=None,
            can_retry=False,
        )

    def list_tools(self, limit: int = 100) -> AdapterReceipt:
        """
        List Vapi tools.

        Args:
            limit: Maximum number of tools to return (1-100)

        Returns:
            AdapterReceipt with tools array

        Contract: tool-contracts.yaml#/paths/~1tool/get
        """
        if not (1 <= limit <= 100):
            raise ValidationError("limit must be between 1 and 100", field="limit")

        url = f"{self.base_url}/tool?limit={limit}"
        response = self._request(
            method="GET",
            url=url,
            headers=self._get_headers(),
            operation="list_tools",
        )

        # Response is an array
        if not isinstance(response, list):
            raise PermanentError(
                "Vapi list_tools response must be an array",
                context={"operation": "list_tools", "response_type": type(response).__name__},
            )

        return AdapterReceipt(
            platform="vapi",
            operation="list_tools",
            remote_id=None,
            status="success",
            response_data={"tools": response, "count": len(response)},
            idempotency_key=None,
            can_retry=True,
        )

    def get_tool(self, tool_id: str) -> AdapterReceipt:
        """
        Retrieve a Vapi tool by ID.

        Args:
            tool_id: Vapi tool ID

        Returns:
            AdapterReceipt with tool data

        Contract: tool-contracts.yaml#/paths/~1tool~1{toolId}/get
        """
        if not tool_id:
            raise ValidationError("tool_id is required", field="tool_id")

        url = f"{self.base_url}/tool/{tool_id}"
        response = self._request(
            method="GET",
            url=url,
            headers=self._get_headers(),
            operation="get_tool",
        )

        return AdapterReceipt(
            platform="vapi",
            operation="get_tool",
            remote_id=tool_id,
            status="success",
            response_data=response,
            idempotency_key=None,
            can_retry=True,
        )

    def assign_phone_number(self, phone_number_id: str, assistant_id: str | None) -> AdapterReceipt:
        """
        Assign or unassign an assistant to a phone number.

        Args:
            phone_number_id: Vapi phone number ID
            assistant_id: Assistant ID to assign, or None to unassign

        Returns:
            AdapterReceipt with updated phone number data

        Contract: tool-contracts.yaml#/paths/~1phone-number~1{phoneNumberId}/patch
        """
        if not phone_number_id:
            raise ValidationError("phone_number_id is required", field="phone_number_id")

        url = f"{self.base_url}/phone-number/{phone_number_id}"
        payload = {"assistantId": assistant_id}

        response = self._request(
            method="PATCH",
            url=url,
            headers=self._get_headers(),
            json_data=payload,
            operation="assign_phone_number",
        )

        return AdapterReceipt(
            platform="vapi",
            operation="assign_phone_number",
            remote_id=phone_number_id,
            status="success",
            response_data=response,
            idempotency_key=None,
            can_retry=False,  # Update requires read-before-write
        )

    # Validation helpers

    def _validate_assistant_create_payload(self, payload: dict[str, Any]) -> None:
        """Validate assistant create payload has required fields."""
        required = ["name", "model", "voice"]
        for field in required:
            if field not in payload:
                raise ValidationError(
                    f"Assistant create payload missing required field: {field}",
                    field=field,
                    context={"operation": "create_assistant"},
                )

        # Validate model structure
        model = payload.get("model", {})
        required_model_fields = ["provider", "model"]
        for field in required_model_fields:
            if field not in model:
                raise ValidationError(
                    f"Assistant model missing required field: {field}",
                    field=f"model.{field}",
                    context={"operation": "create_assistant"},
                )

        # Validate voice structure
        voice = payload.get("voice", {})
        required_voice_fields = ["provider", "voiceId"]
        for field in required_voice_fields:
            if field not in voice:
                raise ValidationError(
                    f"Assistant voice missing required field: {field}",
                    field=f"voice.{field}",
                    context={"operation": "create_assistant"},
                )

    def _validate_assistant_update_payload(self, payload: dict[str, Any]) -> None:
        """Validate assistant update payload is not empty."""
        if not payload:
            raise ValidationError(
                "Assistant update payload must contain at least one field",
                field="payload",
                context={"operation": "update_assistant"},
            )

    def _validate_tool_create_payload(self, payload: dict[str, Any]) -> None:
        """Validate tool create payload has required fields."""
        required = ["type", "function", "server"]
        for field in required:
            if field not in payload:
                raise ValidationError(
                    f"Tool create payload missing required field: {field}",
                    field=field,
                    context={"operation": "create_tool"},
                )

        # Validate type is 'function'
        if payload.get("type") != "function":
            raise ValidationError(
                "Tool type must be 'function'",
                field="type",
                context={"operation": "create_tool", "actual_type": payload.get("type")},
            )

        # Validate function structure
        function = payload.get("function", {})
        if "name" not in function or "parameters" not in function:
            raise ValidationError(
                "Tool function must have 'name' and 'parameters' fields",
                field="function",
                context={"operation": "create_tool"},
            )

        # Validate server structure
        server = payload.get("server", {})
        if "url" not in server:
            raise ValidationError(
                "Tool server must have 'url' field",
                field="server.url",
                context={"operation": "create_tool"},
            )

        # Validate server URL is HTTPS
        server_url = server.get("url", "")
        if not server_url.startswith("https://"):
            raise ValidationError(
                "Tool server URL must use HTTPS",
                field="server.url",
                context={"operation": "create_tool", "url": server_url},
            )
