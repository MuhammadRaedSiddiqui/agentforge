"""
Unit tests for Vapi assistant config validator.

Tests cover:
- Required field validation
- Tool reference validation
- Server URL HTTPS requirement
- Secret detection
"""

from typing import Any

import pytest

from agents.vapi_agent.validator import VapiValidator

pytestmark = pytest.mark.unit


class TestVapiAssistantConfigValidator:
    """Test suite for Vapi assistant configuration validation."""

    def test_valid_assistant_config(self) -> None:
        """Test that a valid assistant config passes validation."""
        config: dict[str, Any] = {
            "name": "Test Assistant",
            "model": {"provider": "openai", "model": "gpt-4"},
            "voice": {"provider": "11labs", "voiceId": "test-voice-id"},
            "serverUrl": "https://example.com/webhook",
            "tools": [{"type": "function", "id": "tool-123"}],
        }

        validator = VapiValidator()
        result = validator.validate_assistant_config(config)

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_missing_required_field_name(self) -> None:
        """Test that missing 'name' field is detected."""
        config: dict[str, Any] = {
            "model": {"provider": "openai", "model": "gpt-4"},
            "voice": {"provider": "11labs", "voiceId": "test-voice-id"},
            "serverUrl": "https://example.com/webhook",
        }

        validator = VapiValidator()
        result = validator.validate_assistant_config(config)

        assert result.is_valid is False
        assert any("name" in error.lower() for error in result.errors)

    def test_missing_required_field_model(self) -> None:
        """Test that missing 'model' field is detected."""
        config: dict[str, Any] = {
            "name": "Test Assistant",
            "voice": {"provider": "11labs", "voiceId": "test-voice-id"},
            "serverUrl": "https://example.com/webhook",
        }

        validator = VapiValidator()
        result = validator.validate_assistant_config(config)

        assert result.is_valid is False
        assert any("model" in error.lower() for error in result.errors)

    def test_invalid_tool_reference(self) -> None:
        """Test that invalid tool ID reference is detected."""
        config: dict[str, Any] = {
            "name": "Test Assistant",
            "model": {"provider": "openai", "model": "gpt-4"},
            "voice": {"provider": "11labs", "voiceId": "test-voice-id"},
            "serverUrl": "https://example.com/webhook",
            "tools": [
                {"type": "function", "id": ""}  # Empty tool ID
            ],
        }

        validator = VapiValidator()
        result = validator.validate_assistant_config(config)

        assert result.is_valid is False
        assert any("tool" in error.lower() for error in result.errors)

    def test_server_url_must_be_https(self) -> None:
        """Test that HTTP server URL is rejected (HTTPS required)."""
        config: dict[str, Any] = {
            "name": "Test Assistant",
            "model": {"provider": "openai", "model": "gpt-4"},
            "voice": {"provider": "11labs", "voiceId": "test-voice-id"},
            "serverUrl": "http://example.com/webhook",  # HTTP not HTTPS
            "tools": [],
        }

        validator = VapiValidator()
        result = validator.validate_assistant_config(config)

        assert result.is_valid is False
        assert any("https" in error.lower() for error in result.errors)

    def test_secret_detection_in_config(self) -> None:
        """Test that secrets in config are detected."""
        config: dict[str, Any] = {
            "name": "Test Assistant",
            "model": {"provider": "openai", "model": "gpt-4", "apiKey": "sk-1234567890abcdef"},
            "voice": {"provider": "11labs", "voiceId": "test-voice-id"},
            "serverUrl": "https://example.com/webhook",
        }

        validator = VapiValidator()
        result = validator.validate_assistant_config(config)

        assert result.is_valid is False
        assert any("secret" in error.lower() or "api" in error.lower() for error in result.errors)

    def test_placeholder_detection(self) -> None:
        """Test that unresolved placeholders are detected."""
        config: dict[str, Any] = {
            "name": "{{CLIENT_NAME}} Assistant",
            "model": {"provider": "openai", "model": "gpt-4"},
            "voice": {"provider": "11labs", "voiceId": "test-voice-id"},
            "serverUrl": "https://example.com/webhook",
        }

        validator = VapiValidator()
        result = validator.validate_assistant_config(config)

        assert result.is_valid is False
        assert any("placeholder" in error.lower() for error in result.errors)

    def test_foreign_organization_id_detection(self) -> None:
        """Test that foreign organization IDs are detected."""
        config: dict[str, Any] = {
            "name": "Test Assistant",
            "model": {"provider": "openai", "model": "gpt-4"},
            "voice": {"provider": "11labs", "voiceId": "test-voice-id"},
            "serverUrl": "https://example.com/webhook",
            "metadata": {"organizationId": "other_client_org"},
        }

        validator = VapiValidator()
        result = validator.validate_assistant_config(config, expected_org_id="my_test_org")

        assert result.is_valid is False
        assert any(
            "organization" in error.lower() or "cross-client" in error.lower()
            for error in result.errors
        )

    def test_empty_config(self) -> None:
        """Test that empty config is rejected."""
        config: dict[str, Any] = {}

        validator = VapiValidator()
        result = validator.validate_assistant_config(config)

        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_tool_array_validation(self) -> None:
        """Test that tools array structure is validated."""
        config: dict[str, Any] = {
            "name": "Test Assistant",
            "model": {"provider": "openai", "model": "gpt-4"},
            "voice": {"provider": "11labs", "voiceId": "test-voice-id"},
            "serverUrl": "https://example.com/webhook",
            "tools": "invalid-not-an-array",
        }

        validator = VapiValidator()
        result = validator.validate_assistant_config(config)

        assert result.is_valid is False
        assert any("tool" in error.lower() for error in result.errors)
