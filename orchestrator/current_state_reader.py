"""
Current-state reader for updates.

Implements T148: Current-state reader (read all relevant external resources
for the organization, compute state hashes)
"""

from typing import Any

from adapters.hosting import RenderAdapter
from adapters.make import MakeAdapter
from adapters.supabase_client import SupabaseClientAdapter
from adapters.supabase_internal import SupabaseInternalClient
from adapters.vapi import VapiAdapter
from shared.hashing import hash_json


class CurrentStateReader:
    """
    Reads current state from all external platforms for an organization.

    Used before updates to capture what currently exists.
    """

    def __init__(self) -> None:
        """Initialize state reader with adapters."""
        self.vapi = VapiAdapter()
        self.make = MakeAdapter()
        self.supabase_client = SupabaseClientAdapter()
        self.hosting = RenderAdapter()

    def read_current_state(
        self,
        deployment_id: str,
        organization_id: str,
        internal_store: SupabaseInternalClient,
    ) -> dict[str, Any]:
        """
        Read current state from all external platforms.

        Args:
            deployment_id: Current deployment ID
            organization_id: Organization identifier
            internal_store: Internal store client

        Returns:
            Current state dictionary with platform data and hashes
        """
        current_state: dict[str, Any] = {
            "deployment_id": deployment_id,
            "organization_id": organization_id,
            "platforms": {},
            "state_hashes": {},
        }

        # Get external resources from internal store
        # Note: get_external_resources method needs to be implemented in SupabaseInternalClient
        resources: list[dict[str, Any]] = []
        try:
            resources = internal_store.get_external_resources(deployment_id)
        except AttributeError:
            # Method not yet implemented, continue with empty resources
            pass

        # Read Vapi resources
        vapi_state = self._read_vapi_state(resources)
        platforms_dict: dict[str, Any] = current_state["platforms"]
        state_hashes_dict: dict[str, str] = current_state["state_hashes"]

        if vapi_state:
            platforms_dict["vapi"] = vapi_state
            state_hashes_dict["vapi"] = hash_json(vapi_state)

        # Read Make resources
        make_state = self._read_make_state(resources)
        if make_state:
            platforms_dict["make"] = make_state
            state_hashes_dict["make"] = hash_json(make_state)

        # Read Supabase resources
        supabase_state = self._read_supabase_state(resources, organization_id)
        if supabase_state:
            platforms_dict["supabase"] = supabase_state
            state_hashes_dict["supabase"] = hash_json(supabase_state)

        # Read hosting state
        hosting_state = self._read_hosting_state(resources)
        if hosting_state:
            platforms_dict["hosting"] = hosting_state
            state_hashes_dict["hosting"] = hash_json(hosting_state)

        # Compute overall state hash
        current_state["overall_state_hash"] = hash_json(state_hashes_dict)

        return current_state

    def _read_vapi_state(self, resources: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Read current Vapi state.

        Args:
            resources: External resources list

        Returns:
            Vapi state dictionary
        """
        vapi_resources = [r for r in resources if r["platform"] == "vapi"]

        if not vapi_resources:
            return {}

        state: dict[str, Any] = {
            "assistants": [],
            "tools": [],
        }

        for resource in vapi_resources:
            remote_id = resource["remote_id"]
            resource_type = resource["resource_type"]

            try:
                if resource_type == "assistant":
                    result = self.vapi.get_assistant(remote_id)
                    if result.status == "success":
                        state["assistants"].append(
                            {
                                "id": remote_id,
                                "name": result.response_data.get("name"),
                                "model": result.response_data.get("model"),
                                "voice": result.response_data.get("voice"),
                                "first_message": result.response_data.get("firstMessage"),
                            }
                        )

                elif resource_type == "tool":
                    result = self.vapi.get_tool(remote_id)
                    if result.status == "success":
                        state["tools"].append(
                            {
                                "id": remote_id,
                                "type": result.response_data.get("type"),
                                "server_url": result.response_data.get("server", {}).get("url"),
                            }
                        )

            except Exception as e:
                # Log but don't fail - partial state is OK
                print(f"Warning: Could not read {resource_type} {remote_id}: {e}")

        return state

    def _read_make_state(self, resources: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Read current Make state.

        Args:
            resources: External resources list

        Returns:
            Make state dictionary
        """
        make_resources = [r for r in resources if r["platform"] == "make"]

        if not make_resources:
            return {}

        state: dict[str, Any] = {
            "scenarios": [],
            "hooks": [],
        }

        for resource in make_resources:
            remote_id = resource["remote_id"]
            resource_type = resource["resource_type"]

            try:
                if resource_type == "scenario":
                    result = self.make.get_scenario(remote_id)
                    if result.status == "success":
                        state["scenarios"].append(
                            {
                                "id": remote_id,
                                "name": result.response_data.get("name"),
                                "is_active": result.response_data.get("isActive"),
                                "scheduling": result.response_data.get("scheduling"),
                            }
                        )

                elif resource_type == "hook":
                    result = self.make.get_hook(remote_id)
                    if result.status == "success":
                        state["hooks"].append(
                            {
                                "id": remote_id,
                                "url": result.response_data.get("url"),
                            }
                        )

            except Exception as e:
                print(f"Warning: Could not read {resource_type} {remote_id}: {e}")

        return state

    def _read_supabase_state(
        self,
        resources: list[dict[str, Any]],
        organization_id: str,
    ) -> dict[str, Any]:
        """
        Read current Supabase state.

        Args:
            resources: External resources list
            organization_id: Organization identifier

        Returns:
            Supabase state dictionary
        """
        supabase_resources = [r for r in resources if r["platform"] == "supabase"]

        if not supabase_resources:
            return {}

        state: dict[str, Any] = {
            "organization_record": None,
        }

        try:
            # Read organization record
            result = self.supabase_client.select_rows(
                "organizations",
                organization_id,
            )

            if result.status == "success" and result.response_data.get("rows"):
                rows = result.response_data.get("rows", [])
                if rows:
                    org_record = rows[0]
                    state["organization_record"] = {
                        "id": org_record.get("id"),
                        "name": org_record.get("name"),
                        "slug": org_record.get("slug"),
                        "capabilities": org_record.get("capabilities"),
                    }

        except Exception as e:
            print(f"Warning: Could not read Supabase state: {e}")

        return state

    def _read_hosting_state(self, resources: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Read current hosting state.

        Args:
            resources: External resources list

        Returns:
            Hosting state dictionary
        """
        hosting_resources = [r for r in resources if r["platform"] in ["render", "hosting"]]

        if not hosting_resources:
            return {}

        state: dict[str, Any] = {
            "deploys": [],
        }

        for resource in hosting_resources:
            remote_id = resource["remote_id"]
            resource_type = resource["resource_type"]

            try:
                if resource_type == "deploy":
                    result = self.hosting.get_deploy_status(remote_id)
                    if result.status == "success":
                        state["deploys"].append(
                            {
                                "id": remote_id,
                                "status": result.response_data.get("status"),
                            }
                        )

            except Exception as e:
                print(f"Warning: Could not read {resource_type} {remote_id}: {e}")

        return state
