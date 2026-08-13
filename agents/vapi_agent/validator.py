"""
Vapi artifact validator.

Validates generated Vapi assistant configurations for:
- Schema conformance
- Tool ID references
- Server URL HTTPS requirement
- Placeholder resolution
- Foreign organization ID detection
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


class VapiValidator:
    """Validator for Vapi assistant configurations."""

    REQUIRED_FIELDS = ["name", "model", "voice"]
    SECRET_PATTERNS = [
        r"sk-[a-zA-Z0-9]{20,}",  # OpenAI-style keys
        r"Bearer\s+[a-zA-Z0-9_\-]{20,}",  # Bearer tokens
        r'api[_-]?key["\']?\s*[:=]\s*["\']([^"\']{10,})',  # API keys
    ]

    def __init__(self) -> None:
        """Initialize the validator."""
        pass

    def validate_assistant_config(
        self, config: dict[str, Any], expected_org_id: str | None = None
    ) -> ValidationResult:
        """
        Validate a Vapi assistant configuration.

        Args:
            config: Assistant configuration to validate
            expected_org_id: Expected organization ID for cross-client check

        Returns:
            ValidationResult with validation status and any errors
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Check required fields
        for field in self.REQUIRED_FIELDS:
            if field not in config:
                errors.append(f"Missing required field: {field}")

        # Validate name
        if "name" in config:
            name = config["name"]
            if not isinstance(name, str) or len(name.strip()) == 0:
                errors.append("Field 'name' must be a non-empty string")

        # Validate model
        if "model" in config:
            model_errors = self._validate_model(config["model"])
            errors.extend(model_errors)

        # Validate voice
        if "voice" in config:
            voice_errors = self._validate_voice(config["voice"])
            errors.extend(voice_errors)

        # Validate server URL
        if "serverUrl" in config:
            url_errors = self._validate_server_url(config["serverUrl"])
            errors.extend(url_errors)

        # Validate tools
        if "tools" in config:
            tool_errors = self._validate_tools(config["tools"])
            errors.extend(tool_errors)

        # Check for unresolved placeholders
        placeholder_errors = self._check_placeholders(config)
        errors.extend(placeholder_errors)

        # Check for secrets
        secret_errors = self._check_secrets(config)
        errors.extend(secret_errors)

        # Check for foreign organization IDs
        if expected_org_id:
            foreign_org_errors = self._check_foreign_org_ids(config, expected_org_id)
            errors.extend(foreign_org_errors)

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

    def _validate_model(self, model: Any) -> list[str]:
        """Validate model configuration."""
        errors = []

        if not isinstance(model, dict):
            errors.append("Field 'model' must be an object")
            return errors

        if "provider" not in model:
            errors.append("Model missing required field 'provider'")

        if "model" not in model:
            errors.append("Model missing required field 'model'")

        # Check for API keys in model config
        if "apiKey" in model or "api_key" in model:
            errors.append("Model contains API key - secrets must not be in config")

        return errors

    def _validate_voice(self, voice: Any) -> list[str]:
        """Validate voice configuration."""
        errors = []

        if not isinstance(voice, dict):
            errors.append("Field 'voice' must be an object")
            return errors

        if "provider" not in voice:
            errors.append("Voice missing required field 'provider'")

        if "voiceId" not in voice:
            errors.append("Voice missing required field 'voiceId'")

        # Vapi built-in voices must use provider "vapi" with a known voice ID.
        # A third-party provider (e.g. 11labs) without matching credentials
        # causes "Couldn't Find <provider> Voice" at call time.
        if voice.get("provider") == "vapi":
            from shared.vapi_voices import is_valid_vapi_voice

            voice_id = voice.get("voiceId")
            if not voice_id or not is_valid_vapi_voice(voice_id):
                errors.append(
                    f"Voice '{voice_id}' is not a valid Vapi built-in voice ID. "
                    f"Use one of the IDs listed in shared.vapi_voices."
                )

        return errors

    def _validate_server_url(self, url: str) -> list[str]:
        """Validate server URL uses HTTPS."""
        errors: list[str] = []

        if not isinstance(url, str):
            errors.append("serverUrl must be a string")
            return errors

        # Allow placeholders
        if "{{" in url:
            return errors

        if not url.startswith("https://"):
            errors.append("serverUrl must use HTTPS protocol")

        return errors

    def _validate_tools(self, tools: Any) -> list[str]:
        """Validate tools array."""
        errors = []

        if not isinstance(tools, list):
            errors.append("Field 'tools' must be an array")
            return errors

        for i, tool in enumerate(tools):
            if not isinstance(tool, dict):
                errors.append(f"Tool at index {i} must be an object")
                continue

            # Check for tool ID or function name
            has_id = "id" in tool and tool["id"]
            has_function = "function" in tool and isinstance(tool["function"], dict)

            if not has_id and not has_function:
                errors.append(f"Tool at index {i} must have either 'id' or 'function' field")

            # If function exists, validate it
            if has_function:
                function = tool["function"]
                if "name" not in function or not function["name"]:
                    errors.append(f"Tool at index {i}: function missing 'name'")

        return errors

    def _check_placeholders(self, config: dict[str, Any]) -> list[str]:
        """Check for unresolved placeholders."""
        errors = []

        config_str = json.dumps(config)

        # Find all placeholders
        pattern = r"\{\{([^}]+)\}\}"
        matches = re.finditer(pattern, config_str)

        unresolved = set()
        for match in matches:
            placeholder = match.group(1)
            # Allow certain runtime placeholders
            if placeholder not in ["WEBHOOK_SECRET"]:
                unresolved.add(placeholder)

        if unresolved:
            errors.append(f"Unresolved placeholders found: {', '.join(sorted(unresolved))}")

        return errors

    def _check_secrets(self, config: dict[str, Any]) -> list[str]:
        """Check for embedded secrets."""
        errors = []

        config_str = json.dumps(config)

        for pattern in self.SECRET_PATTERNS:
            matches = re.finditer(pattern, config_str, re.IGNORECASE)
            for match in matches:
                # Exclude placeholders
                if "{{" not in match.group(0):
                    errors.append(f"Secret pattern detected: {match.group(0)[:30]}...")

        # Check for common secret field names with non-placeholder values
        def check_dict_for_secrets(d: dict, path: str = "") -> None:
            for key, value in d.items():
                current_path = f"{path}.{key}" if path else key
                if isinstance(value, dict):
                    check_dict_for_secrets(value, current_path)
                elif isinstance(value, str):
                    key_lower = key.lower()
                    if (
                        any(
                            secret_key in key_lower
                            for secret_key in ["key", "secret", "token", "password"]
                        )
                        and value
                        and "{{" not in value
                        and len(value) > 10
                    ):
                        errors.append(
                            f"Potential secret in field '{current_path}': {value[:20]}..."
                        )

        check_dict_for_secrets(config)

        return errors

    def _check_foreign_org_ids(self, config: dict[str, Any], expected_org_id: str) -> list[str]:
        """Check for references to other organization IDs."""
        errors = []

        config_str = json.dumps(config)

        # Pattern to find organization_id references
        pattern = r'"organization[_-]?id"\s*:\s*"([^"]+)"'
        matches = re.finditer(pattern, config_str, re.IGNORECASE)

        foreign_ids = set()
        for match in matches:
            org_id = match.group(1)
            # Skip placeholders
            if "{{" not in org_id and org_id != expected_org_id:
                foreign_ids.add(org_id)

        if foreign_ids:
            errors.append(f"Cross-client references detected: {', '.join(sorted(foreign_ids))}")

        return errors

    def validate_tool_schema(self, tool: dict[str, Any]) -> ValidationResult:
        """
        Validate a tool schema.

        Args:
            tool: Tool definition to validate

        Returns:
            ValidationResult
        """
        errors = []

        if "function" not in tool:
            errors.append("Tool missing 'function' field")
            return ValidationResult(is_valid=False, errors=errors)

        function = tool["function"]

        if "name" not in function:
            errors.append("Function missing 'name' field")

        if "parameters" not in function:
            errors.append("Function missing 'parameters' field")
        elif isinstance(function["parameters"], dict):
            params = function["parameters"]
            if "type" not in params or params["type"] != "object":
                errors.append("Function parameters must be of type 'object'")

            if "properties" not in params:
                errors.append("Function parameters missing 'properties'")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
