"""
Security test for redaction functionality.

Verifies that no secret patterns appear in sanitized outputs.
"""

import pytest

from shared.redaction import (
    redact_dict,
    redact_secrets,
    sanitize_error_message,
    sanitize_url,
    scan_for_secrets,
    validate_no_secrets,
)


@pytest.mark.security
class TestRedactionSecurity:
    """Security tests for secret redaction."""

    def test_no_api_keys_in_redacted_content(self) -> None:
        """Redacted content should contain no API keys."""
        content = """
        Configuration:
        API_KEY=sk-1234567890abcdefghijklmnop
        VAPI_KEY=pk-9876543210zyxwvutsrqponmlk
        """

        redacted = redact_secrets(content)

        # Verify no API key patterns remain
        assert "sk-1234567890" not in redacted
        assert "pk-9876543210" not in redacted
        assert validate_no_secrets(redacted)

    def test_no_bearer_tokens_in_redacted_content(self) -> None:
        """Redacted content should contain no Bearer tokens."""
        content = "Authorization: Bearer abc123xyz789token456"

        redacted = redact_secrets(content)

        assert "abc123xyz789" not in redacted
        assert "Bearer ***" in redacted or "***" in redacted

    def test_no_passwords_in_redacted_dict(self) -> None:
        """Redacted dictionaries should mask password values."""
        data = {
            "username": "admin",
            "password": "supersecret123",
            "api_password": "anothersecret456",
        }

        redacted = redact_dict(data)

        assert "supersecret123" not in str(redacted)
        assert "anothersecret456" not in str(redacted)
        assert redacted["username"] == "admin"  # Non-sensitive preserved
        assert redacted["password"] != "supersecret123"

    def test_no_tokens_in_nested_structures(self) -> None:
        """Redaction should work on nested structures."""
        data = {
            "config": {
                "auth": {
                    "token": "secret_token_12345",
                    "api_key": "sk-abcdefghij1234567890",
                }
            },
            "public_value": "visible",
        }

        redacted = redact_dict(data)

        # Convert to string to check all nested values
        import json
        redacted_str = json.dumps(redacted)

        assert "secret_token_12345" not in redacted_str
        assert "sk-abcdefghij1234567890" not in redacted_str
        assert "visible" in redacted_str

    def test_no_credentials_in_urls(self) -> None:
        """URLs should have credentials removed."""
        url = "https://admin:password123@api.example.com/endpoint"

        sanitized = sanitize_url(url)

        assert "admin" not in sanitized
        assert "password123" not in sanitized
        assert "example.com" in sanitized

    def test_no_api_keys_in_query_params(self) -> None:
        """Query parameters with API keys should be redacted."""
        url = "https://api.example.com/data?api_key=secret123&user=test"

        sanitized = sanitize_url(url)

        assert "secret123" not in sanitized
        assert "user=test" in sanitized

    def test_no_secrets_in_error_messages(self) -> None:
        """Error messages should have secrets redacted."""
        try:
            raise Exception("Connection failed: api_key=sk-1234567890abcdef")
        except Exception as e:
            sanitized = sanitize_error_message(e)

            assert "sk-1234567890abcdef" not in sanitized
            assert "Connection failed" in sanitized

    def test_scan_detects_common_secret_patterns(self) -> None:
        """Secret scanner should detect common patterns."""
        content = """
        sk-1234567890abcdefghij
        Bearer abc123xyz789
        api_key=secret123456
        password=mypassword123
        """

        findings = scan_for_secrets(content)

        assert len(findings) > 0
        # Should detect at least the sk- prefix
        assert any("sk-" in f["matched_text"] for f in findings)

    def test_aws_keys_are_detected(self) -> None:
        """AWS access keys should be detected."""
        content = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"

        findings = scan_for_secrets(content)

        assert len(findings) > 0
        assert any("AKIA" in f["matched_text"] for f in findings)

    def test_jwt_tokens_are_detected(self) -> None:
        """JWT tokens should be detected."""
        content = "token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.TJVA95OrM7E2cBab30RMHrHDcEfxjoYZgeFONFh7HgQ"

        findings = scan_for_secrets(content)

        assert len(findings) > 0
        assert any("eyJ" in f["matched_text"] for f in findings)

    def test_validation_passes_for_clean_content(self) -> None:
        """Validation should pass for content without secrets."""
        clean_content = """
        This is clean content.
        It contains no secrets, tokens, or API keys.
        Just regular text and data.
        """

        assert validate_no_secrets(clean_content)

    def test_validation_fails_for_content_with_secrets(self) -> None:
        """Validation should fail for content with secrets."""
        secret_content = "API_KEY=sk-1234567890abcdefghij"

        assert not validate_no_secrets(secret_content)

    def test_redaction_is_idempotent(self) -> None:
        """Redacting already-redacted content should not change it."""
        content = "API_KEY=sk-1234567890abcdefghij"

        redacted_once = redact_secrets(content)
        redacted_twice = redact_secrets(redacted_once)

        assert redacted_once == redacted_twice

    def test_no_partial_secrets_leak(self) -> None:
        """Even partial secrets should not leak."""
        content = "The API key is sk-1234567890abcdefghijklmnop"

        redacted = redact_secrets(content)

        # Check that no substring of 8+ chars from the secret remains
        secret = "1234567890abcdefghij"
        for i in range(len(secret) - 7):
            substring = secret[i:i+8]
            assert substring not in redacted, f"Partial secret leaked: {substring}"

    def test_multiple_secrets_all_redacted(self) -> None:
        """Multiple secrets in the same content should all be redacted."""
        content = """
        GEMINI_API_KEY=AIzaSyABC123DEF456GHI789
        VAPI_API_KEY=sk-1234567890abcdefghij
        MAKE_API_TOKEN=Bearer xyz789abc123
        """

        redacted = redact_secrets(content)

        assert "AIzaSyABC123" not in redacted
        assert "sk-1234567890" not in redacted
        assert "xyz789abc123" not in redacted

    def test_dict_redaction_preserves_structure(self) -> None:
        """Redacted dictionaries should preserve non-sensitive structure."""
        data = {
            "user": "test_user",
            "api_key": "secret123",
            "settings": {
                "timeout": 30,
                "token": "secret456",
            },
            "public_data": [1, 2, 3],
        }

        redacted = redact_dict(data)

        # Structure should be preserved
        assert "user" in redacted
        assert "settings" in redacted
        assert "public_data" in redacted
        assert redacted["user"] == "test_user"
        assert redacted["settings"]["timeout"] == 30
        assert redacted["public_data"] == [1, 2, 3]

        # Secrets should be masked
        assert redacted["api_key"] != "secret123"
        assert redacted["settings"]["token"] != "secret456"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "security"])
