"""
Multi-step Make.com scenario deployment.

Handles the full lifecycle: create hook → deploy blueprint → verify → activate.
Falls back to stub+update when full blueprint creation fails.
"""

import json
import logging
from pathlib import Path
from typing import Any

from adapters.make import MakeAdapter

logger = logging.getLogger(__name__)

EXPECTED_MODULE_COUNTS = {
    "availability": 4,
    "booking": 6,
    "cancellation": 8,
    "rescheduling": 10,
}


class MakeScenarioDeployer:
    """Orchestrates multi-step Make.com scenario deployment."""

    def __init__(self, adapter: MakeAdapter) -> None:
        self.adapter = adapter

    def deploy_scenario(
        self,
        capability: str,
        blueprint_path: str,
        hook_name: str | None = None,
        connection_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Deploy a full Make.com scenario with hook creation and verification.

        Steps:
        1. Create webhook hook (get real hook ID)
        2. Load and parameterize blueprint with hook ID
        3. Attempt full blueprint creation
        4. If full fails, create stub then update with full blueprint
        5. Verify module count
        6. Activate scenario

        Returns:
            Dict with scenario_id, hook_id, module_count, activated status
        """
        result: dict[str, Any] = {
            "capability": capability,
            "scenario_id": None,
            "hook_id": None,
            "module_count": 0,
            "activated": False,
            "used_fallback": False,
        }

        # Step 1: Create hook
        hook_receipt = self.adapter.create_hook(
            name=hook_name or f"hook-{capability}",
            type_name="web",
            method=True,
            headers=True,
            stringify=True,
        )
        hook_id = hook_receipt.remote_id
        result["hook_id"] = hook_id
        logger.info(f"Created hook {hook_id} for {capability}")

        # Step 2: Load blueprint and inject hook ID
        blueprint = self._load_blueprint(blueprint_path)
        blueprint = self._inject_hook_id(blueprint, capability, hook_id)

        if connection_id:
            blueprint = self._inject_connection_id(blueprint, connection_id)

        # Step 3: Try creating with full blueprint
        scheduling = {"type": "immediately"}
        try:
            receipt = self.adapter.create_scenario(blueprint, scheduling, confirmed=True)
            scenario_id = int(receipt.remote_id)
            result["scenario_id"] = scenario_id
        except Exception as e:
            logger.warning(f"Full blueprint failed for {capability}: {e}")
            result["used_fallback"] = True

            # Step 4: Fallback — create stub, then update blueprint
            minimal = {
                "name": blueprint.get("name", f"scenario-{capability}"),
                "flow": [
                    {"id": 1, "module": "gateway:CustomWebHook", "version": 1, "parameters": {"hook": hook_id}, "mapper": {}}
                ],
                "metadata": {"instant": True, "version": 1, "designer": {"orphans": []}},
            }
            receipt = self.adapter.create_scenario(minimal, scheduling, confirmed=True)
            scenario_id = int(receipt.remote_id)
            result["scenario_id"] = scenario_id

            try:
                self.adapter.update_scenario_blueprint(scenario_id, blueprint, confirmed=True)
                logger.info(f"Applied full blueprint to scenario {scenario_id} via update")
            except Exception as update_err:
                logger.warning(f"Blueprint update also failed for {capability}: {update_err}")

        # Step 5: Verify module count
        try:
            bp_receipt = self.adapter.get_scenario_blueprint(scenario_id)
            response = bp_receipt.response_data or {}
            bp_response = response.get("response", response)
            flow = bp_response.get("flow", [])
            result["module_count"] = len(flow)

            expected = EXPECTED_MODULE_COUNTS.get(capability, 0)
            if expected and len(flow) != expected:
                logger.warning(
                    f"Module count mismatch for {capability}: "
                    f"expected {expected}, got {len(flow)}"
                )
        except Exception as verify_err:
            logger.warning(f"Could not verify blueprint for {capability}: {verify_err}")

        # Step 6: Activate
        try:
            self.adapter.activate_scenario(scenario_id)
            result["activated"] = True
        except Exception as act_err:
            logger.warning(f"Activation failed for {capability}: {act_err}")

        return result

    def _load_blueprint(self, blueprint_path: str) -> dict[str, Any]:
        """Load blueprint from file path."""
        path = Path(blueprint_path)
        if not path.exists():
            raise FileNotFoundError(f"Blueprint not found: {blueprint_path}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _inject_hook_id(
        self, blueprint: dict[str, Any], capability: str, hook_id: str
    ) -> dict[str, Any]:
        """Replace hook placeholders with real hook ID."""
        flow = blueprint.get("flow", [])
        for module in flow:
            if module.get("module") in ("webhook:CustomWebHook", "gateway:CustomWebHook"):
                if "parameters" not in module:
                    module["parameters"] = {}
                module["parameters"]["hook"] = hook_id
        return blueprint

    def _inject_connection_id(
        self, blueprint: dict[str, Any], connection_id: str
    ) -> dict[str, Any]:
        """Replace connection placeholders with real connection ID."""
        flow = blueprint.get("flow", [])
        for module in flow:
            params = module.get("parameters", {})
            conn = params.get("connection")
            if isinstance(conn, str) and (
                conn.startswith("{{") or conn == "{{supabase_connection_id}}"
            ):
                params["connection"] = connection_id
        return blueprint
