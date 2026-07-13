"""
Unit tests for shared utilities.

Tests for errors, ids, hashing, and redaction modules.
"""

import json
import re
from pathlib import Path

import pytest

from shared.errors import (
    AmbiguousOutcomeError,
    AuthorizationError,
    CompensationError,
    ConflictError,
    PermanentError,
    PersistenceError,
    StateTransitionError,
    TransientError,
    ValidationError,
    classify_error,
)
from shared.hashing import (
    compute_audit_hash,
    compute_display_hash,
    compute_intake_hash,
    compute_proposal_hash,
    compute_state_version,
    hash_content,
    hash_json,
    verify_hash,
)
from shared.ids import (
    generate_idempotency_key,
    generate_knowledge_entry_id,
    generate_task_id,
    generate_uuid,
    normalize_organization_id,
    validate_organization_id,
    validate_uuid,
)
from shared.redaction import (
    mask_value,
    redact_dict,
    redact_secrets,
    sanitize_error_message,
    sanitize_url,
    scan_for_secrets,
    validate_no_secrets,
)


@pytest.mark.unit
class TestErrors:
    """Tests for error hierarchy and classification."""

    def test_error_inheritance(self) -> None:
        """All custom errors should inherit from AgentForgeError."""
        from shared.errors import AgentForgeError

        errors = [
            ValidationError("test"),
            AuthorizationError("test"),
            ConflictError("test"),
            TransientError("test"),
            PermanentError("test"),
            AmbiguousOutcomeError("test"),
            CompensationError("test"),
            PersistenceError("test"),
            StateTransitionError("test"),
        ]

        for error in errors:
            assert isinstance(error, AgentForgeError)

    def test_classify_error_types(self) -> None:
        """Test error classification mapping."""
        assert classify_error(ValidationError("test")) == "validation"
        assert classify_error(AuthorizationError("test")) == "authorization"
        assert classify_error(ConflictError("test")) == "conflict"
        assert classify_error(TransientError("test")) == "transient"
        assert classify_error(PermanentError("test")) == "permanent"
        assert classify_error(AmbiguousOutcomeError("test")) == "ambiguous_outcome"
        assert classify_error(CompensationError("test")) == "compensation_failure"
        assert classify_error(PersistenceError("test")) == "local_persistence_failure"

    def test_classify_unknown_error(self) -> None:
        """Unknown errors should be classified as permanent."""
        assert classify_error(Exception("unknown")) == "permanent"


@pytest.mark.unit
class TestIds:
    """Tests for ID generation and validation."""

    def test_generate_uuid_format(self) -> None:
        """UUID should be valid format."""
        uid = generate_uuid()
        assert validate_uuid(uid)
        assert len(uid) == 36
        assert uid.count("-") == 4

    def test_generate_task_id_format(self) -> None:
        """Task ID should follow expected format."""
        deployment_id = generate_uuid()
        task_id = generate_task_id(deployment_id, "vapi_agent", 1, 1)

        # Should be: {deployment_prefix}-{agent}-{seq:03d}-{attempt}
        parts = task_id.split("-")
        assert len(parts) >= 4
        assert "vapi_agent" in task_id
        assert task_id.endswith("-1")

    def test_generate_task_id_sequence_padding(self) -> None:
        """Task ID should pad sequence to 3 digits."""
        deployment_id = generate_uuid()
        task_id = generate_task_id(deployment_id, "make_agent", 5, 1)

        assert "-005-" in task_id

    def test_generate_knowledge_entry_id(self) -> None:
        """Knowledge entry ID should be deterministic."""
        entry_id = generate_knowledge_entry_id(
            "knowledge-base/gotchas/vapi-timeout.md", "abc123def456"
        )

        assert "knowledge-base-gotchas-vapi-timeout" in entry_id
        assert "abc123de" in entry_id  # First 8 chars of hash

    def test_generate_idempotency_key(self) -> None:
        """Idempotency key should include all components."""
        key = generate_idempotency_key(
            "test_org", "create_assistant", "vapi", "2026-07-13T12:00:00"
        )

        assert "test_org" in key
        assert "create_assistant" in key
        assert "vapi" in key
        assert "2026-07-13" in key

    def test_validate_uuid_valid(self) -> None:
        """Valid UUIDs should pass validation."""
        assert validate_uuid("550e8400-e29b-41d4-a716-446655440000")
        assert validate_uuid(generate_uuid())

    def test_validate_uuid_invalid(self) -> None:
        """Invalid UUIDs should fail validation."""
        assert not validate_uuid("not-a-uuid")
        assert not validate_uuid("12345")
        assert not validate_uuid("")

    def test_validate_organization_id_valid(self) -> None:
        """Valid organization IDs should pass."""
        assert validate_organization_id("test_org")
        assert validate_organization_id("mycompany123")
        assert validate_organization_id("a_b_c_123")

    def test_validate_organization_id_invalid(self) -> None:
        """Invalid organization IDs should fail."""
        assert not validate_organization_id("Test-Org")  # uppercase and dash
        assert not validate_organization_id("test org")  # space
        assert not validate_organization_id("test@org")  # special char
        assert not validate_organization_id("")  # empty

    def test_normalize_organization_id(self) -> None:
        """Organization ID normalization should follow rules."""
        assert normalize_organization_id("Test Org") == "test_org"
        assert normalize_organization_id("My-Company!") == "my_company"
        assert normalize_organization_id("  Spa ces  ") == "spa_ces"
        assert normalize_organization_id("Multiple___Underscores") == "multiple_underscores"


@pytest.mark.unit
class TestHashing:
    """Tests for content hashing."""

    def test_hash_content_string(self) -> None:
        """Hash of string content should be deterministic."""
        content = "test content"
        hash1 = hash_content(content)
        hash2 = hash_content(content)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex

    def test_hash_content_bytes(self) -> None:
        """Hash should work with bytes."""
        content_bytes = b"test content"
        hash_result = hash_content(content_bytes)

        assert len(hash_result) == 64

    def test_hash_json_deterministic(self) -> None:
        """JSON hashing should be deterministic with key sorting."""
        data1 = {"b": 2, "a": 1, "c": 3}
        data2 = {"a": 1, "c": 3, "b": 2}

        hash1 = hash_json(data1)
        hash2 = hash_json(data2)

        assert hash1 == hash2

    def test_compute_proposal_hash(self) -> None:
        """Proposal hash should bind all components."""
        hash1 = compute_proposal_hash(
            "vapi",
            "create_assistant",
            {"name": "test"},
            "payload123",
            "v1",
            ["dep1"],
        )

        # Change one component - hash should differ
        hash2 = compute_proposal_hash(
            "vapi",
            "create_assistant",
            {"name": "test"},
            "payload456",  # Different payload
            "v1",
            ["dep1"],
        )

        assert hash1 != hash2

    def test_verify_hash_success(self) -> None:
        """Hash verification should succeed for matching content."""
        content = "test content"
        expected_hash = hash_content(content)

        assert verify_hash(content, expected_hash)

    def test_verify_hash_failure(self) -> None:
        """Hash verification should fail for non-matching content."""
        content = "test content"
        wrong_hash = hash_content("different content")

        assert not verify_hash(content, wrong_hash)


@pytest.mark.unit
class TestRedaction:
    """Tests for secret redaction."""

    def test_scan_for_secrets_api_keys(self) -> None:
        """Should detect common API key patterns."""
        content = "API_KEY=sk-1234567890abcdefghij"
        findings = scan_for_secrets(content)

        assert len(findings) > 0
        assert any("sk-" in f["matched_text"] for f in findings)

    def test_scan_for_secrets_bearer_tokens(self) -> None:
        """Should detect Bearer tokens."""
        content = "Authorization: Bearer abc123xyz789"
        findings = scan_for_secrets(content)

        assert len(findings) > 0

    def test_redact_secrets_api_keys(self) -> None:
        """Should redact API keys."""
        content = "My key is sk-1234567890abcdefghij"
        redacted = redact_secrets(content)

        assert "sk-***" in redacted
        assert "sk-1234567890" not in redacted

    def test_redact_dict_sensitive_keys(self) -> None:
        """Should redact sensitive dictionary keys."""
        data = {
            "api_key": "secret123",
            "name": "test",
            "password": "pass123",
        }

        redacted = redact_dict(data)

        assert redacted["api_key"] == "secr***"
        assert redacted["name"] == "test"  # Not sensitive
        assert redacted["password"] != "pass123"

    def test_redact_dict_nested(self) -> None:
        """Should redact nested dictionaries."""
        data = {
            "config": {
                "token": "secret123",
                "public_value": "visible",
            }
        }

        redacted = redact_dict(data)

        assert redacted["config"]["token"] != "secret123"
        assert redacted["config"]["public_value"] == "visible"

    def test_mask_value(self) -> None:
        """Should mask values correctly."""
        assert mask_value("secret123", 4) == "secr***"
        assert mask_value("ab", 4) == "***"
        assert mask_value("", 4) == "***"

    def test_validate_no_secrets_clean(self) -> None:
        """Should pass for content without secrets."""
        assert validate_no_secrets("This is clean content")
        assert validate_no_secrets({"name": "test", "value": 123})

    def test_validate_no_secrets_with_secret(self) -> None:
        """Should fail for content with secrets."""
        assert not validate_no_secrets("api_key=sk-1234567890abcdefghij")

    def test_sanitize_url_with_credentials(self) -> None:
        """Should remove credentials from URLs."""
        url = "https://user:password@example.com/api"
        sanitized = sanitize_url(url)

        assert "user" not in sanitized
        assert "password" not in sanitized
        assert "example.com" in sanitized

    def test_sanitize_url_with_api_key_param(self) -> None:
        """Should redact API key query parameters."""
        url = "https://api.example.com/data?api_key=secret123&other=value"
        sanitized = sanitize_url(url)

        assert "secret123" not in sanitized
        assert "api_key=***" in sanitized
        assert "other=value" in sanitized


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
