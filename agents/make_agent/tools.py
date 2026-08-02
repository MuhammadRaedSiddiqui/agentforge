"""
Tools for Make agent operations.

Provides utilities for:
- Blueprint parameterization
- Hook URL injection
- Scheduling configuration
"""

import json
import re
from re import Match
from typing import Any, cast


def parameterize_blueprint(blueprint: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively parameterize blueprint with context values.

    Replaces placeholders like {{variable_name}} with actual values.

    Args:
        blueprint: Blueprint data structure
        context: Dictionary of values to substitute

    Returns:
        Parameterized blueprint
    """
    return cast(dict[str, Any], _deep_interpolate(blueprint, context))


def _deep_interpolate(data: Any, context: dict[str, Any]) -> Any:
    """
    Recursively interpolate placeholders in data structure.

    Args:
        data: Data to interpolate (dict, list, str, or primitive)
        context: Values to substitute

    Returns:
        Interpolated data
    """
    if isinstance(data, dict):
        return {key: _deep_interpolate(value, context) for key, value in data.items()}
    elif isinstance(data, list):
        return [_deep_interpolate(item, context) for item in data]
    elif isinstance(data, str):
        return _interpolate_string(data, context)
    else:
        return data


def _interpolate_string(text: str, context: dict[str, Any]) -> str:
    """
    Interpolate placeholders in a string.

    Args:
        text: String with placeholders
        context: Values to substitute

    Returns:
        String with placeholders replaced
    """

    def replace_placeholder(match: Match[str]) -> str:
        placeholder = match.group(1)
        if placeholder in context:
            value = context[placeholder]
            # Convert to string, handling special types
            if isinstance(value, (list, dict)):
                return json.dumps(value)
            return str(value)
        # Leave unmatched placeholders as-is
        return match.group(0)

    pattern = r"\{\{([^}]+)\}\}"
    return re.sub(pattern, replace_placeholder, text)


def inject_hook_urls(
    blueprint: dict[str, Any], capability: str, organization_id: str
) -> dict[str, Any]:
    """
    Inject webhook hook URLs into blueprint.

    Args:
        blueprint: Blueprint data
        capability: Capability name (e.g., 'booking', 'availability')
        organization_id: Organization identifier

    Returns:
        Blueprint with hook URLs configured
    """
    # Hook URLs are typically referenced in webhook modules
    # The actual hook creation happens during deployment
    # Here we ensure the structure is correct for hook references

    flow = blueprint.get("flow", [])
    for module in flow:
        if module.get("module") in ("webhook:CustomWebHook", "gateway:CustomWebHook"):
            if "parameters" not in module:
                module["parameters"] = {}

            hook_placeholder = f"{{{{HOOK_{capability.upper()}_ID}}}}"
            module["parameters"]["hook"] = hook_placeholder

            if "metadata" not in module:
                module["metadata"] = {}

            module["metadata"]["capability"] = capability
            module["metadata"]["organization_id"] = organization_id

    return blueprint


def configure_scheduling(
    blueprint: dict[str, Any], schedule_type: str = "immediately"
) -> dict[str, Any]:
    """
    Configure scheduling settings for the scenario.

    Args:
        blueprint: Blueprint data
        schedule_type: Scheduling type ('immediately', 'interval', 'cron')

    Returns:
        Blueprint with scheduling configured
    """
    if "scheduling" not in blueprint:
        blueprint["scheduling"] = {}

    blueprint["scheduling"]["type"] = schedule_type

    # For webhook-triggered scenarios, use "immediately"
    if schedule_type == "immediately":
        blueprint["scheduling"]["type"] = "immediately"

    elif schedule_type == "interval":
        # Default interval settings
        blueprint["scheduling"]["interval"] = 15
        blueprint["scheduling"]["intervalUnit"] = "minutes"

    elif schedule_type == "cron":
        # Default cron settings (every hour)
        blueprint["scheduling"]["cron"] = "0 * * * *"

    return blueprint


def extract_module_list(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract list of modules from blueprint flow.

    Args:
        blueprint: Blueprint data

    Returns:
        List of module definitions
    """
    flow = blueprint.get("flow", [])
    return flow if isinstance(flow, list) else []


def validate_module_allowlist(blueprint: dict[str, Any], allowed_modules: list[str]) -> list[str]:
    """
    Check if all modules in blueprint are on the allowlist.

    Args:
        blueprint: Blueprint data
        allowed_modules: List of allowed module names

    Returns:
        List of disallowed modules found
    """
    disallowed = []
    flow = blueprint.get("flow", [])

    for module in flow:
        module_name = module.get("module", "")
        if module_name and module_name not in allowed_modules:
            disallowed.append(module_name)

    return disallowed


def get_default_allowed_modules() -> list[str]:
    """
    Get default list of allowed Make.com modules.

    Returns:
        List of allowed module names
    """
    return [
        "webhook:CustomWebHook",
        "http:ActionSendData",
        "supabase:ActionSelectRows",
        "supabase:ActionInsertRow",
        "supabase:ActionUpdateRows",
        "supabase:ActionDeleteRow",
        "json:ParseJSON",
        "json:TransformToJSON",
        "builtin:BasicFunction",
        "builtin:BasicRouter",
        "builtin:BasicAggregator",
        "text:Replace",
        "text:Match",
        "util:SetVariable",
        "util:GetVariable",
        "util:Sleep",
    ]


def extract_hook_references(blueprint: dict[str, Any]) -> list[str]:
    """
    Extract all webhook hook references from blueprint.

    Args:
        blueprint: Blueprint data

    Returns:
        List of hook IDs or placeholders
    """
    hook_refs = []
    flow = blueprint.get("flow", [])

    for module in flow:
        if module.get("module") in ("webhook:CustomWebHook", "gateway:CustomWebHook"):
            hook = module.get("parameters", {}).get("hook")
            if hook:
                hook_refs.append(hook)

    return [str(hook_ref) for hook_ref in hook_refs]


def extract_supabase_operations(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract all Supabase operations from blueprint.

    Args:
        blueprint: Blueprint data

    Returns:
        List of Supabase operation details
    """
    operations = []
    flow = blueprint.get("flow", [])

    supabase_modules = [
        "supabase:ActionSelectRows",
        "supabase:ActionInsertRow",
        "supabase:ActionUpdateRows",
        "supabase:ActionDeleteRow",
    ]

    for module in flow:
        if module.get("module") in supabase_modules:
            operations.append(
                {
                    "module": module.get("module"),
                    "table": module.get("parameters", {}).get("table"),
                    "filters": module.get("parameters", {}).get("filter", []),
                    "mapper": module.get("mapper", {}),
                }
            )

    return operations


def validate_organization_references(blueprint: dict[str, Any], expected_org_id: str) -> list[str]:
    """
    Check for references to organization IDs and verify they match expected ID.

    Args:
        blueprint: Blueprint data
        expected_org_id: Expected organization identifier

    Returns:
        List of foreign organization IDs found
    """
    foreign_orgs = []
    blueprint_str = json.dumps(blueprint)

    # Find all organization_id references
    pattern = r'"organization_id"\s*:\s*"([^"]+)"'
    matches = re.finditer(pattern, blueprint_str)

    for match in matches:
        org_id = match.group(1)
        # Skip placeholders
        if "{{" not in org_id and org_id != expected_org_id:
            foreign_orgs.append(org_id)

    return foreign_orgs


def sanitize_blueprint_for_export(blueprint: dict[str, Any]) -> dict[str, Any]:
    """
    Sanitize blueprint for export by removing internal metadata.

    Args:
        blueprint: Blueprint data

    Returns:
        Sanitized blueprint
    """
    sanitized = blueprint.copy()

    # Remove designer metadata (not needed for import)
    if "metadata" in sanitized and "designer" in sanitized["metadata"]:
        sanitized["metadata"] = {k: v for k, v in sanitized["metadata"].items() if k != "designer"}

    # Remove internal IDs that get regenerated on import
    flow = sanitized.get("flow", [])
    for module in flow:
        if "metadata" in module and "designer" in module["metadata"]:
            module["metadata"] = {k: v for k, v in module["metadata"].items() if k != "designer"}

    return sanitized


def compute_blueprint_complexity(blueprint: dict[str, Any]) -> dict[str, int]:
    """
    Compute complexity metrics for a blueprint.

    Args:
        blueprint: Blueprint data

    Returns:
        Dictionary of complexity metrics
    """
    flow = blueprint.get("flow", [])

    module_count = len(flow)
    router_count = sum(1 for m in flow if "Router" in m.get("module", ""))
    supabase_ops = sum(1 for m in flow if m.get("module", "").startswith("supabase:"))
    webhook_count = sum(1 for m in flow if "webhook" in m.get("module", "").lower())

    return {
        "total_modules": module_count,
        "routers": router_count,
        "supabase_operations": supabase_ops,
        "webhooks": webhook_count,
        "complexity_score": module_count + (router_count * 2) + supabase_ops,
    }
