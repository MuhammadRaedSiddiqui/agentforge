"""
Current-state reader for updates.

Implements T148: Current-state reader (read all relevant external resources
for the organization, compute state hashes)

Also provides the single source of truth for *staleness* projections. An update
action records a state_version when it is planned; immediately before the write
executes, the same projection is read again and re-hashed. If the two differ,
someone changed the resource out from under us. Both hashes must be produced by
`read_staleness_state` so the projections cannot drift apart — a projection
mismatch would report drift on every action and train operators to ignore it.
"""

from typing import Any

from adapters.hosting import RenderAdapter
from adapters.make import MakeAdapter
from adapters.supabase_client import SupabaseClientAdapter
from adapters.supabase_internal import SupabaseInternalClient
from adapters.vapi import VapiAdapter
from shared.errors import PermanentError
from shared.hashing import compute_state_version, hash_json

# Blueprint fields Make returns on GET but that are payload-level concerns, not
# scenario content. They move on their own, so hashing them would manufacture
# drift. See knowledge-base/gotchas/make-blueprint-strip-metadata.md.
_VOLATILE_BLUEPRINT_FIELDS = ("teamId", "scheduling", "description")


class StaleStateReadError(PermanentError):
    """Raised when current state cannot be read for a staleness comparison.

    A failed read means the remote state is *unknown*, which is not the same as
    unchanged. Callers must surface this rather than treating it as "not stale".
    """


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

        # Get external resources from internal store. This was previously
        # wrapped in `except AttributeError: pass` from when the method was
        # unimplemented; it exists now (SupabaseInternalClient.get_external_
        # resources), and swallowing the error here would silently yield an
        # empty resource set — which reads as "nothing deployed" rather than
        # as a failure, and would leave update actions with nothing to check.
        resources: list[dict[str, Any]] = internal_store.get_external_resources(deployment_id)

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

    # ------------------------------------------------------------------
    # Staleness projections
    # ------------------------------------------------------------------

    def read_staleness_state(
        self,
        platform: str,
        resource_type: str,
        remote_id: str,
    ) -> dict[str, Any]:
        """
        Read the narrow, stable projection of a resource used for drift checks.

        Deliberately narrower than the display projections built by
        `read_current_state`: it includes only fields a human editing the
        resource would change. Volatile fields (Make's `is_active` and
        `scheduling`, deploy status, timestamps) are excluded, because drift
        detection that fires on every run is drift detection nobody reads.

        Args:
            platform: Platform name (vapi, make)
            resource_type: Resource type (assistant, scenario)
            remote_id: Remote resource identifier

        Returns:
            Projection dictionary suitable for hashing

        Raises:
            StaleStateReadError: If the resource cannot be read. Unknown state
                is not the same as unchanged state and must not be swallowed.
        """
        key = (platform, resource_type)

        try:
            if key == ("vapi", "assistant"):
                result = self.vapi.get_assistant(remote_id)
                if result.status != "success":
                    raise StaleStateReadError(
                        f"Vapi assistant {remote_id} read returned status {result.status}"
                    )
                data = result.response_data
                return {
                    "name": data.get("name"),
                    "model": data.get("model"),
                    "voice": data.get("voice"),
                    "first_message": data.get("firstMessage"),
                }

            if key == ("make", "scenario"):
                scenario = self.make.get_scenario(int(remote_id))
                if scenario.status != "success":
                    raise StaleStateReadError(
                        f"Make scenario {remote_id} read returned status {scenario.status}"
                    )
                blueprint_receipt = self.make.get_scenario_blueprint(int(remote_id))
                if blueprint_receipt.status != "success":
                    raise StaleStateReadError(
                        f"Make blueprint for scenario {remote_id} returned "
                        f"status {blueprint_receipt.status}"
                    )
                blueprint = blueprint_receipt.response_data.get("blueprint")
                if isinstance(blueprint, dict):
                    blueprint = {
                        k: v for k, v in blueprint.items() if k not in _VOLATILE_BLUEPRINT_FIELDS
                    }
                return {
                    "name": scenario.response_data.get("name"),
                    "blueprint": blueprint,
                }

        except StaleStateReadError:
            raise
        except Exception as error:  # adapter/transport failure
            raise StaleStateReadError(
                f"Could not read current state for {platform}/{resource_type} {remote_id}: {error}"
            ) from error

        raise StaleStateReadError(
            f"No staleness projection defined for {platform}/{resource_type}. "
            "Add one before planning updates against this resource."
        )

    def read_staleness_version(
        self,
        platform: str,
        resource_type: str,
        remote_id: str,
    ) -> str:
        """Read a resource's staleness projection and hash it."""
        return compute_state_version(self.read_staleness_state(platform, resource_type, remote_id))

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
