"""
Multi-step Make.com scenario deployment.

Handles the full lifecycle: create hook → deploy blueprint → verify → activate.
Falls back to stub+update when full blueprint creation fails.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any

from adapters.make import MakeAdapter

logger = logging.getLogger(__name__)

EXPECTED_MODULE_COUNTS = {
    "availability": 4,
    "booking": 5,
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
        3. Attempt full blueprint creation (with 429 backoff)
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
            type_name="gateway-webhook",
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

        # Step 3: Try creating with full blueprint (with 429/500 backoff)
        scheduling = {"type": "immediately"}
        receipt = None
        last_err: Exception | None = None
        for attempt in range(4):
            try:
                receipt = self.adapter.create_scenario(blueprint, scheduling, confirmed=True)
                break
            except Exception as e:
                last_err = e
                msg = str(e)
                # Only retry transient errors (429/500); permanent errors like IM007 should fallback
                from shared.errors import TransientError

                is_transient = isinstance(e, TransientError) or "500" in msg or "Server error" in msg
                is_rate_limited = "429" in msg or "Rate limited" in msg
                if is_transient and attempt < 3:
                    wait = (5 * (2**attempt)) if is_rate_limited else 1.5
                    logger.warning(
                        f"Full blueprint failed for {capability} (attempt {attempt + 1}/4): {e} — retrying in {wait}s"
                    )
                    time.sleep(wait)
                    continue
                break

        if receipt is not None:
            scenario_id = int(receipt.remote_id)
            result["scenario_id"] = scenario_id
            # Stagger next Make call to avoid burst 429
            time.sleep(1.5)
        else:
            # Step 4: Fallback — create stub, then update blueprint (also with retry)
            logger.warning(f"Full blueprint failed for {capability} after retries: {last_err}")
            result["used_fallback"] = True

            minimal = {
                "name": blueprint.get("name", f"scenario-{capability}"),
                "flow": [
                    {
                        "id": 1,
                        "module": "gateway:CustomWebHook",
                        "version": 1,
                        "parameters": {"hook": int(hook_id)},
                        "mapper": {},
                    }
                ],
                "metadata": {"instant": True, "version": 1, "designer": {"orphans": []}},
            }
            # Retry stub creation
            stub_receipt = None
            for attempt in range(3):
                try:
                    stub_receipt = self.adapter.create_scenario(minimal, scheduling, confirmed=True)
                    break
                except Exception as e:
                    if "429" in str(e) and attempt < 2:
                        time.sleep(5 * (2**attempt))
                        continue
                    raise
            assert stub_receipt is not None
            scenario_id = int(stub_receipt.remote_id)
            result["scenario_id"] = scenario_id

            # Retry blueprint update
            for attempt in range(3):
                try:
                    self.adapter.update_scenario_blueprint(scenario_id, blueprint, confirmed=True)
                    logger.info(f"Applied full blueprint to scenario {scenario_id} via update")
                    break
                except Exception as update_err:
                    msg = str(update_err)
                    if ("429" in msg or "500" in msg) and attempt < 2:
                        wait = 5 * (2**attempt) if "429" in msg else 2
                        logger.warning(
                            f"Blueprint update failed for {capability} (attempt {attempt + 1}/3): {update_err} — retrying in {wait}s"
                        )
                        time.sleep(wait)
                        continue
                    logger.warning(f"Blueprint update also failed for {capability}: {update_err}")
                    break
            time.sleep(1.0)

        # Step 5: Verify module count
        try:
            bp_receipt = self.adapter.get_scenario_blueprint(scenario_id)  # type: ignore[arg-type]
            response = bp_receipt.response_data or {}
            bp_response = response.get("response", response)
            blueprint = bp_response.get("blueprint", bp_response)
            flow = blueprint.get("flow", [])
            result["module_count"] = self._count_modules(flow)

            expected = EXPECTED_MODULE_COUNTS.get(capability, 0)
            if expected and result["module_count"] != expected:
                logger.warning(
                    f"Module count mismatch for {capability}: "
                    f"expected {expected}, got {result['module_count']}"
                )
        except Exception as verify_err:
            logger.warning(f"Could not verify blueprint for {capability}: {verify_err}")

        # Step 6: Activate (with retry for 429)
        for attempt in range(3):
            try:
                self.adapter.activate_scenario(scenario_id)  # type: ignore[arg-type]
                result["activated"] = True
                break
            except Exception as act_err:
                if "429" in str(act_err) and attempt < 2:
                    time.sleep(5 * (2**attempt))
                    continue
                logger.warning(f"Activation failed for {capability}: {act_err}")
                break

        return result

    def _load_blueprint(self, blueprint_path: str) -> dict[str, Any]:
        """Load blueprint from file path."""
        path = Path(blueprint_path)
        if not path.exists():
            raise FileNotFoundError(f"Blueprint not found: {blueprint_path}")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _inject_hook_id(
        self, blueprint: dict[str, Any], capability: str, hook_id: str
    ) -> dict[str, Any]:
        """Replace hook placeholders with real hook ID.

        Make requires the hook parameter to be an integer; passing the string
        remote_id causes IM007 "Invalid value for type hook".
        """
        numeric_hook_id = int(hook_id)
        flow = blueprint.get("flow", [])
        for module in flow:
            if module.get("module") in ("webhook:CustomWebHook", "gateway:CustomWebHook"):
                if "parameters" not in module:
                    module["parameters"] = {}
                module["parameters"]["hook"] = numeric_hook_id
        return blueprint

    def _inject_connection_id(
        self, blueprint: dict[str, Any], connection_id: str
    ) -> dict[str, Any]:
        """Replace connection placeholders with real connection ID.

        Native Make modules reference connections via the ``__IMTCONN__``
        parameter (an integer). Also recurses into router routes.
        """
        numeric_connection_id = int(connection_id)
        flow = blueprint.get("flow", [])

        def inject(modules: list[dict[str, Any]]) -> None:
            for module in modules:
                params = module.get("parameters", {})
                if "__IMTCONN__" in params:
                    # Always ensure integer — handles placeholder {{...}}, string "10111996",
                    # or stale int from a prior generation
                    params["__IMTCONN__"] = numeric_connection_id
                if "connection" in params:
                    conn_val = params.get("connection")
                    if (
                        isinstance(conn_val, str)
                        and (conn_val.startswith("{{") or conn_val.isdigit())
                        or conn_val is None
                    ):
                        params["connection"] = numeric_connection_id
                routes = module.get("routes", [])
                if isinstance(routes, list):
                    for route in routes:
                        if isinstance(route, dict):
                            inject(route.get("flow", []))

        inject(flow)
        return blueprint

    @staticmethod
    def _count_modules(flow: list[dict[str, Any]]) -> int:
        """Count modules including nested router routes."""
        count = 0

        def walk(modules: list[dict[str, Any]]) -> None:
            nonlocal count
            for module in modules:
                count += 1
                routes = module.get("routes", [])
                if isinstance(routes, list):
                    for route in routes:
                        if isinstance(route, dict):
                            walk(route.get("flow", []))

        walk(flow)
        return count
