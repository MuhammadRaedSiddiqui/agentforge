"""
Unit tests for Make.com blueprint validator.

Tests cover:
- Scenario structure validation
- Hook reference validation
- Module allowlist enforcement
- Placeholder detection
- Secret scanning
"""

from agents.make_agent.validator import MakeValidator


class TestMakeBlueprintValidator:
    """Test suite for Make.com blueprint validation."""

    def test_valid_blueprint(self) -> None:
        """Test that a valid Make blueprint passes validation."""
        blueprint = {
            "name": "Test Scenario",
            "flow": [
                {
                    "id": 1,
                    "module": "http:ActionSendData",
                    "parameters": {"url": "https://example.com/webhook", "method": "POST"},
                }
            ],
            "metadata": {"version": "1.0.0"},
        }

        validator = MakeValidator()
        result = validator.validate_blueprint(blueprint)

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_missing_required_field_name(self) -> None:
        """Test that missing 'name' field is detected."""
        blueprint = {
            "flow": [
                {
                    "id": 1,
                    "module": "http:ActionSendData",
                    "parameters": {"url": "https://example.com/webhook"},
                }
            ]
        }

        validator = MakeValidator()
        result = validator.validate_blueprint(blueprint)

        assert result.is_valid is False
        assert any("name" in error.lower() for error in result.errors)

    def test_missing_flow_field(self) -> None:
        """Test that missing 'flow' field is detected."""
        blueprint = {"name": "Test Scenario", "metadata": {"version": "1.0.0"}}

        validator = MakeValidator()
        result = validator.validate_blueprint(blueprint)

        assert result.is_valid is False
        assert any("flow" in error.lower() for error in result.errors)

    def test_empty_flow_array(self) -> None:
        """Test that empty flow array is rejected."""
        blueprint = {"name": "Test Scenario", "flow": []}

        validator = MakeValidator()
        result = validator.validate_blueprint(blueprint)

        assert result.is_valid is False
        assert any("flow" in error.lower() or "empty" in error.lower() for error in result.errors)

    def test_invalid_hook_reference(self) -> None:
        """Test that invalid webhook references are detected."""
        blueprint = {
            "name": "Test Scenario",
            "flow": [
                {
                    "id": 1,
                    "module": "webhook:CustomWebHook",
                    "parameters": {
                        "hookId": ""  # Empty hook ID
                    },
                }
            ],
        }

        validator = MakeValidator()
        result = validator.validate_blueprint(blueprint)

        assert result.is_valid is False
        assert any("hook" in error.lower() for error in result.errors)

    def test_disallowed_module_detected(self) -> None:
        """Test that modules not on allowlist are detected."""
        blueprint = {
            "name": "Test Scenario",
            "flow": [
                {
                    "id": 1,
                    "module": "shell:ExecuteCommand",  # Dangerous module
                    "parameters": {"command": "rm -rf /"},
                }
            ],
        }

        validator = MakeValidator()
        result = validator.validate_blueprint(blueprint)

        assert result.is_valid is False
        assert any(
            "module" in error.lower() or "allowlist" in error.lower() for error in result.errors
        )

    def test_placeholder_detection(self) -> None:
        """Test that unresolved placeholders are detected."""
        blueprint = {
            "name": "{{CLIENT_NAME}} Booking Scenario",
            "flow": [
                {
                    "id": 1,
                    "module": "http:ActionSendData",
                    "parameters": {"url": "https://example.com/webhook"},
                }
            ],
        }

        validator = MakeValidator()
        result = validator.validate_blueprint(blueprint)

        assert result.is_valid is False
        assert any("placeholder" in error.lower() for error in result.errors)

    def test_secret_detection_in_parameters(self) -> None:
        """Test that secrets in parameters are detected."""
        blueprint = {
            "name": "Test Scenario",
            "flow": [
                {
                    "id": 1,
                    "module": "http:ActionSendData",
                    "parameters": {
                        "url": "https://example.com/webhook",
                        "headers": {"Authorization": "Bearer sk-1234567890abcdef"},
                    },
                }
            ],
        }

        validator = MakeValidator()
        result = validator.validate_blueprint(blueprint)

        assert result.is_valid is False
        assert any("secret" in error.lower() for error in result.errors)

    def test_module_structure_validation(self) -> None:
        """Test that module structure is validated."""
        blueprint = {
            "name": "Test Scenario",
            "flow": [
                {
                    "id": 1,
                    # Missing 'module' field
                    "parameters": {"url": "https://example.com/webhook"},
                }
            ],
        }

        validator = MakeValidator()
        result = validator.validate_blueprint(blueprint)

        assert result.is_valid is False
        assert any("module" in error.lower() for error in result.errors)

    def test_allowed_modules_pass_validation(self) -> None:
        """Test that allowed modules pass validation."""
        allowed_modules = [
            "http:ActionSendData",
            "webhook:CustomWebHook",
            "supabase:ActionInsertRow",
            "supabase:ActionSelectRows",
            "json:ParseJSON",
        ]

        for module_name in allowed_modules:
            blueprint = {
                "name": "Test Scenario",
                "flow": [{"id": 1, "module": module_name, "parameters": {}}],
            }

            validator = MakeValidator()
            result = validator.validate_blueprint(blueprint)

            # Should pass module allowlist check (other validations may fail)
            module_errors = [e for e in result.errors if "allowlist" in e.lower()]
            assert len(module_errors) == 0, f"Module {module_name} should be allowed"

    def test_nested_placeholder_detection(self) -> None:
        """Test that placeholders in nested structures are detected."""
        blueprint = {
            "name": "Test Scenario",
            "flow": [
                {
                    "id": 1,
                    "module": "http:ActionSendData",
                    "parameters": {
                        "url": "https://{{DOMAIN}}/webhook",
                        "body": {"client": "{{CLIENT_ID}}"},
                    },
                }
            ],
        }

        validator = MakeValidator()
        result = validator.validate_blueprint(blueprint)

        assert result.is_valid is False
        assert any("placeholder" in error.lower() for error in result.errors)
