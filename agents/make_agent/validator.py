"""
Make.com artifact validator.

Validates generated Make.com blueprints for:
- Blueprint structure conformance
- Hook references validity
- Module allowlist enforcement
- Placeholder resolution
- Secret scanning
"""

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ValidationResult:
    """Result of validation check."""

    is_valid: bool
    errors: list[str]
    warnings: list[str] | None = None

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []


class MakeValidator:
    """Validator for Make.com scenario blueprints."""

    REQUIRED_FIELDS = ["name", "flow"]

    ALLOWED_MODULES = [
        "webhook:CustomWebHook",
        "gateway:CustomWebHook",
        "http:ActionSendData",
        "supabase:searchRows",
        "supabase:createARow",
        "supabase:upsertARecord",
        "supabase:deleteRows",
        "supabase:makeAnApiCall",
        "supabase:getRowsCount",
        "json:ParseJSON",
        "json:TransformToJSON",
        "code:ExecuteCode",
        "builtin:BasicRouter",
        "builtin:BasicAggregator",
        "text:Replace",
        "text:Match",
        "util:SetVariable",
        "util:GetVariable",
        "util:Sleep",
    ]

    SECRET_PATTERNS = [
        r"sk-[a-zA-Z0-9]{10,}",
        r"Bearer\s+[a-zA-Z0-9_\-]{10,}",
        r'api[_-]?key["\']?\s*[:=]\s*["\']([^"\']{10,})',
    ]

    def __init__(self) -> None:
        """Initialize the validator."""
        pass

    def validate_blueprint(self, blueprint: dict[str, Any]) -> ValidationResult:
        """
        Validate a Make.com scenario blueprint.

        Args:
            blueprint: Blueprint configuration to validate

        Returns:
            ValidationResult with validation status and any errors
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Check required fields
        for field in self.REQUIRED_FIELDS:
            if field not in blueprint:
                errors.append(f"Missing required field: {field}")

        # Validate name
        if "name" in blueprint:
            if not isinstance(blueprint["name"], str) or len(blueprint["name"].strip()) == 0:
                errors.append("Field 'name' must be a non-empty string")

        # Validate flow
        if "flow" in blueprint:
            flow_errors = self._validate_flow(blueprint["flow"])
            errors.extend(flow_errors)

        # Check for unresolved placeholders
        placeholder_errors = self._check_placeholders(blueprint)
        errors.extend(placeholder_errors)

        # Check for secrets
        secret_errors = self._check_secrets(blueprint)
        errors.extend(secret_errors)

        # Validate module allowlist
        allowlist_errors = self._check_module_allowlist(blueprint)
        errors.extend(allowlist_errors)

        # Validate hook references
        hook_errors = self._validate_hook_references(blueprint)
        errors.extend(hook_errors)

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

    def _validate_flow(self, flow: Any) -> list[str]:
        """Validate the flow array."""
        errors = []

        if not isinstance(flow, list):
            errors.append("Field 'flow' must be an array")
            return errors

        if len(flow) == 0:
            errors.append("Field 'flow' cannot be empty")

        for i, module in enumerate(flow):
            if not isinstance(module, dict):
                errors.append(f"Module at index {i} must be an object")
                continue

            # Check required module fields
            if "id" not in module:
                errors.append(f"Module at index {i} missing required field 'id'")

            if "module" not in module:
                errors.append(f"Module at index {i} missing required field 'module'")

            # Validate module structure
            module_errors = self._validate_module(module, i)
            errors.extend(module_errors)

            # Recurse into router routes
            routes = module.get("routes", [])
            if isinstance(routes, list):
                for route_idx, route in enumerate(routes):
                    if not isinstance(route, dict):
                        errors.append(f"Module at index {i} route {route_idx} must be an object")
                        continue
                    route_flow = route.get("flow", [])
                    route_errors = self._validate_flow(route_flow)
                    errors.extend(
                        [f"Module at index {i} route {route_idx}: {e}" for e in route_errors]
                    )

        return errors

    def _validate_module(self, module: dict[str, Any], index: int) -> list[str]:
        """Validate a single module."""
        errors = []

        module_name = module.get("module", "")

        # Check module name format
        if module_name and ":" not in module_name:
            errors.append(f"Module at index {index}: invalid module name format '{module_name}'")

        # Validate webhook modules
        if "webhook" in module_name.lower():
            if "parameters" not in module:
                errors.append(f"Module at index {index}: webhook module missing 'parameters'")
            elif "hook" not in module.get("parameters", {}):
                errors.append(f"Module at index {index}: webhook module missing 'hook' parameter")

        return errors

    def _check_placeholders(self, blueprint: dict[str, Any]) -> list[str]:
        """Check for unresolved placeholders."""
        errors = []

        blueprint_str = json.dumps(blueprint)

        # Find all placeholders
        pattern = r"\{\{([^}]+)\}\}"
        matches = re.finditer(pattern, blueprint_str)

        unresolved = set()
        for match in matches:
            placeholder = match.group(1)
            # Allow certain runtime placeholders
            allowed_placeholders = [
                "SUPABASE_CONNECTION_ID",
                "HOOK_AVAILABILITY_ID",
                "HOOK_BOOKING_ID",
                "HOOK_CANCELLATION_ID",
                "HOOK_RESCHEDULING_ID",
            ]
            if not any(allowed in placeholder for allowed in allowed_placeholders):
                # Make expressions can be direct module references (``2.rows``)
                # or functions around them (``length(2.rows)`` / ``if(...)``).
                if not re.match(r"^(?:now|\d+\.|(?:if|ifempty|length)\()", placeholder):
                    unresolved.add(placeholder)

        if unresolved:
            errors.append(f"Unresolved placeholders found: {', '.join(sorted(unresolved))}")

        return errors

    def _check_secrets(self, blueprint: dict[str, Any]) -> list[str]:
        """Check for embedded secrets."""
        errors = []

        blueprint_str = json.dumps(blueprint)

        for pattern in self.SECRET_PATTERNS:
            matches = re.finditer(pattern, blueprint_str, re.IGNORECASE)
            for match in matches:
                # Exclude placeholders
                if "{{" not in match.group(0):
                    errors.append(f"Secret pattern detected: {match.group(0)[:30]}...")

        return errors

    def _check_module_allowlist(self, blueprint: dict[str, Any]) -> list[str]:
        """Check that all modules are on the allowlist."""
        errors = []

        flow = blueprint.get("flow", [])

        def walk(modules: Any) -> None:
            if not isinstance(modules, list):
                return
            for i, module in enumerate(modules):
                if not isinstance(module, dict):
                    continue
                module_name = module.get("module", "")
                if module_name and module_name not in self.ALLOWED_MODULES:
                    errors.append(f"Module at index {i}: '{module_name}' not on allowlist")
                routes = module.get("routes", [])
                if isinstance(routes, list):
                    for route in routes:
                        if isinstance(route, dict):
                            walk(route.get("flow", []))

        walk(flow)
        return errors

    def _validate_hook_references(self, blueprint: dict[str, Any]) -> list[str]:
        """Validate webhook hook references."""
        errors = []

        flow = blueprint.get("flow", [])

        def walk(modules: Any) -> None:
            if not isinstance(modules, list):
                return
            for i, module in enumerate(modules):
                if not isinstance(module, dict):
                    continue
                if module.get("module") in ("webhook:CustomWebHook", "gateway:CustomWebHook"):
                    hook = module.get("parameters", {}).get("hook")
                    if not hook:
                        errors.append(f"Module at index {i}: webhook missing hook ID")
                    elif isinstance(hook, str) and len(hook.strip()) == 0:
                        errors.append(f"Module at index {i}: webhook hook ID is empty")
                routes = module.get("routes", [])
                if isinstance(routes, list):
                    for route in routes:
                        if isinstance(route, dict):
                            walk(route.get("flow", []))

        walk(flow)
        return errors

    def validate_supabase_operations(self, blueprint: dict[str, Any]) -> ValidationResult:
        """
        Validate Supabase operations in the blueprint.

        Args:
            blueprint: Blueprint to validate

        Returns:
            ValidationResult
        """
        errors = []
        warnings = []

        supabase_modules = {
            "supabase:searchRows",
            "supabase:createARow",
            "supabase:upsertARecord",
            "supabase:deleteRows",
            "supabase:getRowsCount",
        }
        flow = blueprint.get("flow", [])

        def walk(modules: Any) -> None:
            if not isinstance(modules, list):
                return
            for i, module in enumerate(modules):
                if not isinstance(module, dict):
                    continue
                module_name = module.get("module", "")
                if module_name in supabase_modules:
                    params = module.get("parameters", {})
                    mapper = module.get("mapper", {})

                    # Connection must be present (__IMTCONN__ placeholder or value)
                    if "__IMTCONN__" not in params:
                        errors.append(
                            f"Module at index {i}: Supabase operation missing '__IMTCONN__' parameter"
                        )

                    # Table goes in the mapper for native Supabase modules
                    if module_name in ("supabase:searchRows", "supabase:createARow") and "table" not in mapper:
                        errors.append(
                            f"Module at index {i}: Supabase operation missing 'table' in mapper"
                        )

                    # Check for organization_id isolation in mapper
                    if "organization_id" not in mapper and "organization_id" not in json.dumps(
                        module
                    ):
                        warnings.append(
                            f"Module at index {i}: Supabase operation may lack organization_id isolation"
                        )
                routes = module.get("routes", [])
                if isinstance(routes, list):
                    for route in routes:
                        if isinstance(route, dict):
                            walk(route.get("flow", []))

        walk(flow)

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)
