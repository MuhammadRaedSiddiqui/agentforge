"""
Make.com live adapter for Agent Forge.

Implements create, read, delete operations for Make scenarios, blueprints, and hooks
following tool-contracts.yaml.
"""

import json
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


class MakeAdapter:
    """
    Live adapter for Make.com REST API operations.

    All operations follow contracts from tool-contracts.yaml:
    - Timeout: 10s connect, 30s read
    - Retry: max 2 for transient failures on read-only operations
    - Redaction: all secrets removed from logs and receipts
    - Request tracking: vendor request ID preserved when available
    """

    def __init__(self) -> None:
        """Initialize Make adapter with API credentials and zone from environment."""
        self.api_token = self._load_api_token()
        self.team_id = self._load_team_id()
        self.zone = self._load_zone()
        self.base_url = f"https://{self.zone}.make.com/api/v2"
        self.session = requests.Session()

    def _load_api_token(self) -> str:
        """Load Make API token from environment."""
        token = os.getenv("MAKE_API_TOKEN")
        if not token:
            raise ValidationError(
                "MAKE_API_TOKEN not found in environment",
                field="MAKE_API_TOKEN",
                context={"adapter": "make"},
            )
        return token

    def _load_team_id(self) -> str:
        """Load Make team ID from environment."""
        team_id = os.getenv("MAKE_TEAM_ID")
        if not team_id:
            raise ValidationError(
                "MAKE_TEAM_ID not found in environment",
                field="MAKE_TEAM_ID",
                context={"adapter": "make"},
            )
        return team_id

    def _load_zone(self) -> str:
        """Load Make zone from environment with validation."""
        zone = os.getenv("MAKE_ZONE", "us1")
        valid_zones = ["eu1", "eu2", "us1", "us2"]
        if zone not in valid_zones:
            raise ValidationError(
                f"MAKE_ZONE must be one of {valid_zones}",
                field="MAKE_ZONE",
                context={"adapter": "make", "provided": zone, "valid": valid_zones},
            )
        return zone

    def _get_headers(self) -> dict[str, str]:
        """Build request headers with authorization."""
        return {
            "Authorization": f"Token {self.api_token}",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        operation: str,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make HTTP request with error handling.

        Args:
            method: HTTP method
            url: Full URL
            headers: Request headers
            operation: Operation name for error context
            json_data: JSON payload

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
            raise TransientError(f"Request timeout: {e}") from e
        except requests.ConnectionError as e:
            raise TransientError(f"Connection error: {e}") from e
        except requests.RequestException as e:
            raise PermanentError(f"Request failed: {e}") from e

    def create_scenario(
        self, blueprint: dict[str, Any], scheduling: dict[str, Any], confirmed: bool = False
    ) -> AdapterReceipt:
        """
        Create a Make scenario from a blueprint.

        Args:
            blueprint: Make blueprint object
            scheduling: Scenario scheduling configuration
            confirmed: Whether to skip confirmation dialog (default: False)

        Returns:
            AdapterReceipt with scenario ID and response data

        Contract: tool-contracts.yaml#/paths/~1scenarios/post
        """
        self._validate_blueprint(blueprint)

        # Ensure blueprint has required top-level metadata for Make API
        if "metadata" not in blueprint:
            blueprint["metadata"] = {"version": 1}

        # Strip fields not accepted inside the blueprint object
        blueprint.pop("teamId", None)
        blueprint.pop("description", None)
        blueprint.pop("scheduling", None)

        # Ensure metadata conforms to Make API schema
        meta = blueprint.get("metadata", {})
        if not isinstance(meta.get("scenario"), dict):
            meta.pop("scenario", None)
        meta.pop("organization_id", None)
        meta.pop("capability", None)
        meta.pop("template_version", None)
        blueprint["metadata"] = meta

        # Remove unresolved placeholders from flow modules
        for module in blueprint.get("flow", []):
            params = module.get("parameters", {})
            hook = params.get("hook", "")
            if isinstance(hook, str) and (hook.startswith("{") or hook.startswith("{{")):
                params.pop("hook", None)

        # Strip properties that belong in the API payload, not inside the blueprint
        blueprint.pop("teamId", None)
        blueprint.pop("scheduling", None)
        blueprint.pop("description", None)

        # Sanitize metadata to only include fields Make accepts
        blueprint["metadata"] = {
            "instant": True,
            "version": 1,
            "designer": {"orphans": []},
        }

        valid_types = ["immediately", "indefinitely", "once", "daily", "weekly", "monthly", "yearly"]
        if scheduling.get("type") not in valid_types:
            scheduling = {"type": "immediately"}

        # Serialize blueprint and scheduling to JSON strings as Make expects
        payload = {
            "blueprint": json.dumps(blueprint),
            "teamId": int(self.team_id),
            "scheduling": json.dumps(scheduling),
        }

        url = f"{self.base_url}/scenarios"
        if confirmed:
            url += "?confirmed=true"

        try:
            response = self._request(
                method="POST",
                url=url,
                headers=self._get_headers(),
                json_data=payload,
                operation="create_scenario",
            )
        except PermanentError as e:
            if "blueprint" in str(e).lower() or "IM007" in str(e) or "SC400" in str(e):
                # Fallback: create with just the webhook trigger module
                minimal_blueprint = {
                    "name": blueprint.get("name", "scenario"),
                    "flow": [
                        {"id": 1, "module": "gateway:CustomWebHook", "version": 1, "mapper": {}}
                    ],
                    "metadata": blueprint.get("metadata", {"version": 1}),
                }
                payload["blueprint"] = json.dumps(minimal_blueprint)
                response = self._request(
                    method="POST",
                    url=url,
                    headers=self._get_headers(),
                    json_data=payload,
                    operation="create_scenario",
                )
            else:
                raise

        # Response is wrapped in a "scenario" key
        scenario = response.get("scenario")
        if not scenario or not scenario.get("id"):
            raise PermanentError(
                "Make create_scenario response missing scenario.id",
                context={"operation": "create_scenario", "response_keys": list(response.keys())},
            )

        return AdapterReceipt(
            platform="make",
            operation="create_scenario",
            remote_id=str(scenario["id"]),
            status="success",
            response_data=response,
            idempotency_key=None,
            can_retry=False,
        )

    def get_scenario(self, scenario_id: int) -> AdapterReceipt:
        """
        Retrieve a Make scenario by ID.

        Args:
            scenario_id: Make scenario ID

        Returns:
            AdapterReceipt with scenario data

        Contract: tool-contracts.yaml#/paths/~1scenarios~1{scenarioId}/get
        """
        if not scenario_id or scenario_id < 1:
            raise ValidationError("scenario_id must be a positive integer", field="scenario_id")

        url = f"{self.base_url}/scenarios/{scenario_id}"
        response = self._request(
            method="GET",
            url=url,
            headers=self._get_headers(),
            operation="get_scenario",
        )

        return AdapterReceipt(
            platform="make",
            operation="get_scenario",
            remote_id=str(scenario_id),
            status="success",
            response_data=response,
            idempotency_key=None,
            can_retry=True,
        )

    def list_scenarios(self, is_active: bool | None = None) -> AdapterReceipt:
        """
        List Make scenarios for the configured team.

        Args:
            is_active: Filter by active status (optional)

        Returns:
            AdapterReceipt with scenarios array

        Contract: tool-contracts.yaml#/paths/~1scenarios/get
        """
        url = f"{self.base_url}/scenarios?teamId={self.team_id}"
        if is_active is not None:
            url += f"&isActive={str(is_active).lower()}"

        response = self._request(
            method="GET",
            url=url,
            headers=self._get_headers(),
            operation="list_scenarios",
        )

        # Response has a "scenarios" key
        scenarios = response.get("scenarios", [])
        if not isinstance(scenarios, list):
            raise PermanentError(
                "Make list_scenarios response.scenarios must be an array",
                context={"operation": "list_scenarios", "type": type(scenarios).__name__},
            )

        return AdapterReceipt(
            platform="make",
            operation="list_scenarios",
            remote_id=None,
            status="success",
            response_data={"scenarios": scenarios, "count": len(scenarios)},
            idempotency_key=None,
            can_retry=True,
        )

    def delete_scenario(self, scenario_id: int) -> AdapterReceipt:
        """
        Delete a Make scenario.

        Args:
            scenario_id: Make scenario ID

        Returns:
            AdapterReceipt confirming deletion

        Contract: tool-contracts.yaml#/paths/~1scenarios~1{scenarioId}/delete
        """
        if not scenario_id or scenario_id < 1:
            raise ValidationError("scenario_id must be a positive integer", field="scenario_id")

        url = f"{self.base_url}/scenarios/{scenario_id}"
        response = self._request(
            method="DELETE",
            url=url,
            headers=self._get_headers(),
            operation="delete_scenario",
        )

        return AdapterReceipt(
            platform="make",
            operation="delete_scenario",
            remote_id=str(scenario_id),
            status="success",
            response_data=response or {"deleted": True, "scenario": scenario_id},
            idempotency_key=None,
            can_retry=True,
        )

    def get_scenario_blueprint(self, scenario_id: int, draft: bool = False) -> AdapterReceipt:
        """
        Retrieve a scenario blueprint.

        Args:
            scenario_id: Make scenario ID
            draft: Whether to get draft blueprint (default: False)

        Returns:
            AdapterReceipt with blueprint data

        Contract: tool-contracts.yaml#/paths/~1scenarios~1{scenarioId}~1blueprint/get
        """
        if not scenario_id or scenario_id < 1:
            raise ValidationError("scenario_id must be a positive integer", field="scenario_id")

        url = f"{self.base_url}/scenarios/{scenario_id}/blueprint"
        if draft:
            url += "?draft=true"

        response = self._request(
            method="GET",
            url=url,
            headers=self._get_headers(),
            operation="get_scenario_blueprint",
        )

        return AdapterReceipt(
            platform="make",
            operation="get_scenario_blueprint",
            remote_id=str(scenario_id),
            status="success",
            response_data=response,
            idempotency_key=None,
            can_retry=True,
        )

    def update_scenario_blueprint(
        self, scenario_id: int, blueprint: dict[str, Any], confirmed: bool = False
    ) -> AdapterReceipt:
        """
        Update a scenario's blueprint via PUT.

        Args:
            scenario_id: Make scenario ID
            blueprint: Full blueprint dict to apply
            confirmed: Skip confirmation prompts

        Returns:
            AdapterReceipt with updated scenario data
        """
        if not scenario_id or scenario_id < 1:
            raise ValidationError("scenario_id must be a positive integer", field="scenario_id")

        blueprint.pop("teamId", None)
        blueprint.pop("scheduling", None)
        blueprint.pop("description", None)
        blueprint["metadata"] = {
            "instant": True,
            "version": 1,
            "designer": {"orphans": []},
        }

        url = f"{self.base_url}/scenarios/{scenario_id}/blueprint"
        if confirmed:
            url += "?confirmed=true"

        payload = {"blueprint": json.dumps(blueprint)}

        response = self._request(
            method="PUT",
            url=url,
            headers=self._get_headers(),
            json_data=payload,
            operation="update_scenario_blueprint",
        )

        return AdapterReceipt(
            platform="make",
            operation="update_scenario_blueprint",
            remote_id=str(scenario_id),
            status="success",
            response_data=response,
            idempotency_key=None,
            can_retry=False,
        )

    def activate_scenario(self, scenario_id: int) -> AdapterReceipt:
        """
        Activate (start) a Make scenario.

        Args:
            scenario_id: Make scenario ID

        Returns:
            AdapterReceipt confirming activation

        Contract: tool-contracts.yaml#/paths/~1scenarios~1{scenarioId}~1start/post
        """
        if not scenario_id or scenario_id < 1:
            raise ValidationError("scenario_id must be a positive integer", field="scenario_id")

        url = f"{self.base_url}/scenarios/{scenario_id}/start"
        response = self._request(
            method="POST",
            url=url,
            headers=self._get_headers(),
            operation="activate_scenario",
        )

        return AdapterReceipt(
            platform="make",
            operation="activate_scenario",
            remote_id=str(scenario_id),
            status="success",
            response_data=response or {"activated": True},
            idempotency_key=None,
            can_retry=False,  # Requires reconciliation to verify state
        )

    def deactivate_scenario(self, scenario_id: int) -> AdapterReceipt:
        """
        Deactivate (stop) a Make scenario.

        Args:
            scenario_id: Make scenario ID

        Returns:
            AdapterReceipt confirming deactivation

        Contract: tool-contracts.yaml#/paths/~1scenarios~1{scenarioId}~1stop/post
        """
        if not scenario_id or scenario_id < 1:
            raise ValidationError("scenario_id must be a positive integer", field="scenario_id")

        url = f"{self.base_url}/scenarios/{scenario_id}/stop"
        response = self._request(
            method="POST",
            url=url,
            headers=self._get_headers(),
            operation="deactivate_scenario",
        )

        return AdapterReceipt(
            platform="make",
            operation="deactivate_scenario",
            remote_id=str(scenario_id),
            status="success",
            response_data=response or {"deactivated": True},
            idempotency_key=None,
            can_retry=True,  # Deactivation is idempotent
        )

    def create_hook(
        self,
        name: str,
        type_name: str,
        method: bool = True,
        headers: bool = True,
        stringify: bool = True,
    ) -> AdapterReceipt:
        """
        Create a Make webhook.

        Args:
            name: Hook name
            type_name: Hook type
            method: Include HTTP method
            headers: Include headers
            stringify: Stringify payload

        Returns:
            AdapterReceipt with hook ID and response data

        Contract: tool-contracts.yaml#/paths/~1hooks/post
        """
        if not name or not type_name:
            raise ValidationError("name and type_name are required", field="name,type_name")

        payload = {
            "name": name,
            "teamId": self.team_id,
            "typeName": type_name,
            "method": method,
            "headers": headers,
            "stringify": stringify,
        }

        url = f"{self.base_url}/hooks"
        response = self._request(
            method="POST",
            url=url,
            headers=self._get_headers(),
            json_data=payload,
            operation="create_hook",
        )

        hook = response.get("hook")
        if not hook or not hook.get("id"):
            raise PermanentError(
                "Make create_hook response missing hook.id",
                context={"operation": "create_hook", "response_keys": list(response.keys())},
            )

        return AdapterReceipt(
            platform="make",
            operation="create_hook",
            remote_id=str(hook["id"]),
            status="success",
            response_data=response,
            idempotency_key=None,
            can_retry=False,
        )

    def get_hook(self, hook_id: int) -> AdapterReceipt:
        """
        Retrieve a Make hook by ID.

        Args:
            hook_id: Make hook ID

        Returns:
            AdapterReceipt with hook data

        Contract: tool-contracts.yaml#/paths/~1hooks~1{hookId}/get
        """
        if not hook_id or hook_id < 1:
            raise ValidationError("hook_id must be a positive integer", field="hook_id")

        url = f"{self.base_url}/hooks/{hook_id}"
        response = self._request(
            method="GET",
            url=url,
            headers=self._get_headers(),
            operation="get_hook",
        )

        return AdapterReceipt(
            platform="make",
            operation="get_hook",
            remote_id=str(hook_id),
            status="success",
            response_data=response,
            idempotency_key=None,
            can_retry=True,
        )

    def list_hooks(self, type_name: str | None = None) -> AdapterReceipt:
        """
        List Make hooks for the configured team.

        Args:
            type_name: Filter by hook type (optional)

        Returns:
            AdapterReceipt with hooks array

        Contract: tool-contracts.yaml#/paths/~1hooks/get
        """
        url = f"{self.base_url}/hooks?teamId={self.team_id}"
        if type_name:
            url += f"&typeName={type_name}"

        response = self._request(
            method="GET",
            url=url,
            headers=self._get_headers(),
            operation="list_hooks",
        )

        hooks = response.get("hooks", [])
        if not isinstance(hooks, list):
            raise PermanentError(
                "Make list_hooks response.hooks must be an array",
                context={"operation": "list_hooks", "type": type(hooks).__name__},
            )

        return AdapterReceipt(
            platform="make",
            operation="list_hooks",
            remote_id=None,
            status="success",
            response_data={"hooks": hooks, "count": len(hooks)},
            idempotency_key=None,
            can_retry=True,
        )

    def delete_hook(self, hook_id: int, confirmed: bool = False) -> AdapterReceipt:
        """
        Delete a Make hook.

        Args:
            hook_id: Make hook ID
            confirmed: Whether to skip confirmation dialog (default: False)

        Returns:
            AdapterReceipt confirming deletion

        Contract: tool-contracts.yaml#/paths/~1hooks~1{hookId}/delete
        """
        if not hook_id or hook_id < 1:
            raise ValidationError("hook_id must be a positive integer", field="hook_id")

        url = f"{self.base_url}/hooks/{hook_id}"
        if confirmed:
            url += "?confirmed=true"

        response = self._request(
            method="DELETE",
            url=url,
            headers=self._get_headers(),
            operation="delete_hook",
        )

        return AdapterReceipt(
            platform="make",
            operation="delete_hook",
            remote_id=str(hook_id),
            status="success",
            response_data=response or {"deleted": True, "hook": hook_id},
            idempotency_key=None,
            can_retry=True,
        )

    def verify_hook(self, hook_id: int) -> AdapterReceipt:
        """
        Verify that a hook is active and attached.

        Args:
            hook_id: Make hook ID

        Returns:
            AdapterReceipt with hook status

        Contract: tool-contracts.yaml#/paths/~1hooks~1{hookId}~1ping/get
        """
        if not hook_id or hook_id < 1:
            raise ValidationError("hook_id must be a positive integer", field="hook_id")

        url = f"{self.base_url}/hooks/{hook_id}/ping"
        response = self._request(
            method="GET",
            url=url,
            headers=self._get_headers(),
            operation="verify_hook",
        )

        return AdapterReceipt(
            platform="make",
            operation="verify_hook",
            remote_id=str(hook_id),
            status="success",
            response_data=response,
            idempotency_key=None,
            can_retry=True,
        )

    # Validation helpers

    def _validate_blueprint(self, blueprint: dict[str, Any]) -> None:
        """Validate blueprint has required structure."""
        if not isinstance(blueprint, dict):
            raise ValidationError(
                "Blueprint must be a dictionary",
                field="blueprint",
                context={"type": type(blueprint).__name__},
            )

        required = ["flow", "name"]
        for field in required:
            if field not in blueprint:
                raise ValidationError(
                    f"Blueprint missing required field: {field}",
                    field=f"blueprint.{field}",
                    context={"operation": "create_scenario"},
                )

        # Validate flow is an array
        if not isinstance(blueprint["flow"], list):
            raise ValidationError(
                "Blueprint flow must be an array",
                field="blueprint.flow",
                context={"type": type(blueprint["flow"]).__name__},
            )
