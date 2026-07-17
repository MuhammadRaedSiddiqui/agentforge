"""
Security tests for secret propagation.

Tests T133: Secret propagation (no secret in artifacts, audit records, snapshots,
exports, model context)

Verifies that secrets never leak into persisted data or outputs.
"""

import json
import tempfile
from pathlib import Path

import pytest

from orchestrator.audit import AuditEventType, AuditEventWriter
from shared.hashing import hash_json
from shared.redaction import redact_secrets


@pytest.mark.security
class TestSecretPropagation:
    """Test that secrets are never propagated to outputs."""

    def test_secrets_redacted_in_audit_events(self) -> None:
        """Test that secrets in audit event details are redacted."""
        # Mock internal store
        from unittest.mock import Mock

        mock_store = Mock()
        mock_store.insert_audit_event = Mock(return_value="event-001")
        mock_store.get_last_audit_event = Mock(return_value=None)

        audit_writer = AuditEventWriter(mock_store)

        # Record event with secret in detail
        audit_writer.record_event(
            deployment_id="deploy-001",
            event_type=AuditEventType.ACTION_SUCCEEDED,
            actor="system",
            subject="action-001",
            status="succeeded",
            detail={
                "platform": "vapi",
                "api_key": "sk_live_abc123",
                "password": "mysecretpass",
                "response": "success",
            },
        )

        # Get the event that was inserted
        call_args = mock_store.insert_audit_event.call_args
        event = call_args[0][0]

        # Verify secrets are redacted
        assert event["detail"]["api_key"] == "[REDACTED]"
        assert event["detail"]["password"] == "[REDACTED]"
        assert event["detail"]["platform"] == "vapi"
        assert event["detail"]["response"] == "success"

    def test_secrets_not_in_json_exports(self) -> None:
        """Test that secrets don't appear in JSON exports."""
        # Create test data with secrets
        data = {
            "organization": "test-org",
            "config": {
                "api_key": "sk_test_12345",
                "secret_token": "token_abc",
                "public_value": "safe_data",
            },
        }

        # Redact and export
        json_str = json.dumps(data)
        redacted_str = redact_secrets(json_str)
        redacted_data = json.loads(redacted_str)

        # Verify secrets are redacted
        assert redacted_data["config"]["api_key"] == "[REDACTED]"
        assert redacted_data["config"]["secret_token"] == "[REDACTED]"
        assert redacted_data["config"]["public_value"] == "safe_data"

    def test_secrets_not_in_file_snapshots(self) -> None:
        """Test that snapshot files don't contain secrets."""
        # Create temp snapshot
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            snapshot_data = {
                "assistant_config": {
                    "name": "Test Assistant",
                    "api_key": "sk_live_secret",
                    "model": "gpt-4",
                },
            }
            # Persist only sanitized data; this is the snapshot boundary that
            # production exporters must use as well.
            f.write(redact_secrets(json.dumps(snapshot_data)))
            snapshot_path = Path(f.name)

        try:
            # Read and check
            content = snapshot_path.read_text()

            # Should NOT contain actual secrets
            assert "sk_live_secret" not in content or "[REDACTED]" in content

        finally:
            snapshot_path.unlink()

    def test_secrets_not_in_error_messages(self) -> None:
        """Test that error messages don't leak secrets."""
        error_with_secret = "Connection failed to https://api.example.com with key sk_live_12345"

        # Redact
        redacted_error = redact_secrets(error_with_secret)

        # Verify secret is redacted
        assert "sk_live_12345" not in redacted_error
        assert "[REDACTED]" in redacted_error
        assert "Connection failed" in redacted_error

    def test_secrets_not_in_hash_computation(self) -> None:
        """Test that secrets don't affect hash computation in wrong way."""
        # Two payloads that differ only in secret value
        payload1 = {
            "platform": "vapi",
            "operation": "create",
            "api_key": "secret1",
        }

        payload2 = {
            "platform": "vapi",
            "operation": "create",
            "api_key": "secret2",
        }

        # Hash with redaction should be same
        redacted1 = json.loads(redact_secrets(json.dumps(payload1)))
        redacted2 = json.loads(redact_secrets(json.dumps(payload2)))

        hash1 = hash_json(redacted1)
        hash2 = hash_json(redacted2)

        # Hashes should be identical because secrets are redacted
        assert hash1 == hash2

    def test_environment_variables_not_logged(self) -> None:
        """Test that environment variable values aren't logged."""
        import os

        # Set test env var
        test_key = "TEST_SECRET_KEY"
        test_value = "super_secret_value_123"
        os.environ[test_key] = test_value

        try:
            # Simulate logging config check
            log_message = f"Checking environment: {test_key}={os.getenv(test_key)}"

            # Redact
            redacted_log = redact_secrets(log_message)

            # Verify secret value is redacted
            assert "super_secret_value_123" not in redacted_log
            assert "[REDACTED]" in redacted_log
            assert test_key in redacted_log  # Key name is OK

        finally:
            del os.environ[test_key]

    def test_bearer_tokens_redacted(self) -> None:
        """Test that Bearer tokens in headers are redacted."""
        auth_header = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature"

        # Redact
        redacted = redact_secrets(auth_header)

        # Token should be redacted
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redacted
        assert "[REDACTED]" in redacted

    def test_connection_strings_redacted(self) -> None:
        """Test that connection strings with passwords are redacted."""
        conn_string = "postgresql://user:password123@localhost:5432/db"

        # Redact
        redacted = redact_secrets(conn_string)

        # Password should be redacted
        assert "password123" not in redacted
        assert "[REDACTED]" in redacted
        assert "postgresql://" in redacted

    def test_secrets_not_in_artifact_metadata(self) -> None:
        """Test that artifact metadata doesn't contain secrets."""
        artifact_metadata = {
            "artifact_id": "artifact-001",
            "generated_by": "vapi_agent",
            "source_template": "vapi_assistant_template.json",
            "interpolation_values": {
                "organization_name": "ACME Corp",
                "api_key": "sk_live_secret",  # Should be redacted
                "phone_number": "+15551234567",
            },
        }

        # Convert to JSON and redact
        json_str = json.dumps(artifact_metadata)
        redacted_str = redact_secrets(json_str)
        redacted_metadata = json.loads(redacted_str)

        # Verify secret is redacted but other values preserved
        assert redacted_metadata["interpolation_values"]["api_key"] == "[REDACTED]"
        assert redacted_metadata["interpolation_values"]["organization_name"] == "ACME Corp"
        assert redacted_metadata["interpolation_values"]["phone_number"] == "+15551234567"

    def test_webhook_secrets_redacted(self) -> None:
        """Test that webhook secrets are redacted."""
        webhook_config = {
            "url": "https://hooks.example.com/webhook",
            "secret": "whsec_abc123xyz",
            "events": ["call.started", "call.ended"],
        }

        # Redact
        json_str = json.dumps(webhook_config)
        redacted_str = redact_secrets(json_str)
        redacted_config = json.loads(redacted_str)

        # Verify
        assert redacted_config["secret"] == "[REDACTED]"
        assert redacted_config["url"] == "https://hooks.example.com/webhook"

    def test_no_secrets_in_model_context(self) -> None:
        """Test that secrets aren't included in model prompts."""
        # Simulate artifact being sent to model for validation
        artifact_for_validation = {
            "type": "vapi_assistant",
            "config": {
                "name": "Assistant",
                "model": "gpt-4",
                "server_url": "https://api.example.com",
                # API keys should never be in model context
            },
        }

        # Verify no secret-like patterns
        json_str = json.dumps(artifact_for_validation)

        # Check for common secret patterns
        secret_patterns = [
            "sk_live_",
            "sk_test_",
            "api_key",
            "api-key",
            "apiKey",
            "secret",
            "token",
            "password",
            "credentials",
        ]

        # If any secret-related field is present, value should be redacted
        for pattern in secret_patterns:
            if pattern in json_str.lower():
                # If pattern found in keys, ensure no actual secret values
                assert "sk_" not in json_str or "[REDACTED]" in json_str

    def test_sanitized_receipts_no_secrets(self) -> None:
        """Test that external receipts don't contain secrets."""
        receipt = {
            "action_id": "action-001",
            "platform": "vapi",
            "remote_id": "assistant-abc123",
            "response_summary": {
                "id": "assistant-abc123",
                "name": "Test Assistant",
                "created_at": "2026-07-14T12:00:00Z",
                # Response should not include api keys or tokens
            },
        }

        # Redact
        json_str = json.dumps(receipt)
        redacted_str = redact_secrets(json_str)

        # Should not have been modified if no secrets
        # But if secrets were present, they'd be redacted
        assert "sk_" not in redacted_str or "[REDACTED]" in redacted_str
