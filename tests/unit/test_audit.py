"""
Unit tests for audit event recording.

Tests T132: Audit event recording (required fields, redaction, hash chain,
append-only)
"""

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from orchestrator.audit import (
    AuditEventType,
    AuditEventWriter,
    record_action_execution,
    record_approval_decision,
    record_deployment_created,
    record_state_transition,
)


@pytest.mark.unit
class TestAuditEventRecording:
    """Test audit event recording functionality."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        # Mock internal store
        self.mock_store = Mock()
        self.mock_store.insert_audit_event = Mock(return_value="event-001")
        self.mock_store.get_last_audit_event = Mock(return_value=None)
        self.mock_store.get_audit_events = Mock(return_value=[])

        # Create audit writer
        self.audit_writer = AuditEventWriter(self.mock_store)

    def test_record_event_includes_required_fields(self) -> None:
        """Test that recorded events include all required fields."""
        event_id = self.audit_writer.record_event(
            deployment_id="deploy-001",
            event_type=AuditEventType.DEPLOYMENT_CREATED,
            actor="operator@example.com",
            subject="deploy-001",
            status="created",
            detail={"organization_id": "org-001"},
            session_id="session-001",
        )

        # Verify event was inserted
        assert event_id == "event-001"
        assert self.mock_store.insert_audit_event.called

        # Get the event that was inserted
        call_args = self.mock_store.insert_audit_event.call_args
        event = call_args[0][0]

        # Verify required fields
        assert event["deployment_id"] == "deploy-001"
        assert event["event_type"] == "deployment_created"
        assert event["actor"] == "operator@example.com"
        assert event["subject"] == "deploy-001"
        assert event["status"] == "created"
        assert event["detail"] == {"organization_id": "org-001"}
        assert event["session_id"] == "session-001"
        assert "event_hash" in event
        assert "created_at" in event

    def test_redacts_secrets_in_detail(self) -> None:
        """Test that secrets in detail are redacted."""
        event_id = self.audit_writer.record_event(
            deployment_id="deploy-001",
            event_type=AuditEventType.ACTION_SUCCEEDED,
            actor="system",
            subject="action-001",
            status="succeeded",
            detail={
                "platform": "vapi",
                "api_key": "sk_live_12345",
                "response": "success",
            },
        )

        # Get the event that was inserted
        call_args = self.mock_store.insert_audit_event.call_args
        event = call_args[0][0]

        # Verify secret was redacted
        assert "api_key" in event["detail"]
        assert event["detail"]["api_key"] == "[REDACTED]"
        assert event["detail"]["platform"] == "vapi"
        assert event["detail"]["response"] == "success"

    def test_hash_chain_first_event_null_previous(self) -> None:
        """Test that first event has null previous_hash."""
        # First event - no previous
        self.mock_store.get_last_audit_event.return_value = None

        event_id = self.audit_writer.record_event(
            deployment_id="deploy-001",
            event_type=AuditEventType.DEPLOYMENT_CREATED,
            actor="operator",
            subject="deploy-001",
            status="created",
        )

        # Get the event
        call_args = self.mock_store.insert_audit_event.call_args
        event = call_args[0][0]

        # First event should have null previous_hash
        assert event["previous_hash"] is None
        assert event["event_hash"] is not None

    def test_hash_chain_subsequent_events_link(self) -> None:
        """Test that subsequent events link to previous event hash."""
        # First event
        self.mock_store.get_last_audit_event.return_value = None
        event1_id = self.audit_writer.record_event(
            deployment_id="deploy-001",
            event_type=AuditEventType.DEPLOYMENT_CREATED,
            actor="operator",
            subject="deploy-001",
            status="created",
        )

        # Get first event hash
        call_args = self.mock_store.insert_audit_event.call_args
        event1 = call_args[0][0]
        event1_hash = event1["event_hash"]

        # Second event - should link to first
        self.mock_store.get_last_audit_event.return_value = event1

        event2_id = self.audit_writer.record_event(
            deployment_id="deploy-001",
            event_type=AuditEventType.TASK_STARTED,
            actor="system",
            subject="task-001",
            status="started",
        )

        # Get second event
        call_args = self.mock_store.insert_audit_event.call_args
        event2 = call_args[0][0]

        # Second event should link to first
        assert event2["previous_hash"] == event1_hash
        assert event2["event_hash"] != event1_hash

    def test_verify_chain_valid(self) -> None:
        """Test hash chain verification for valid chain."""
        # Create mock events with valid chain
        events = [
            {
                "id": "event-001",
                "event_hash": "hash1",
                "previous_hash": None,
            },
            {
                "id": "event-002",
                "event_hash": "hash2",
                "previous_hash": "hash1",
            },
            {
                "id": "event-003",
                "event_hash": "hash3",
                "previous_hash": "hash2",
            },
        ]

        self.mock_store.get_audit_events.return_value = events

        result = self.audit_writer.verify_chain("deploy-001")

        assert result["valid"] is True
        assert result["event_count"] == 3
        assert len(result["breaks"]) == 0

    def test_verify_chain_detects_break(self) -> None:
        """Test hash chain verification detects breaks."""
        # Create mock events with broken chain
        events = [
            {
                "id": "event-001",
                "event_hash": "hash1",
                "previous_hash": None,
            },
            {
                "id": "event-002",
                "event_hash": "hash2",
                "previous_hash": "hash1",
            },
            {
                "id": "event-003",
                "event_hash": "hash3",
                "previous_hash": "wrong-hash",  # Break here
            },
        ]

        self.mock_store.get_audit_events.return_value = events

        result = self.audit_writer.verify_chain("deploy-001")

        assert result["valid"] is False
        assert result["event_count"] == 3
        assert len(result["breaks"]) == 1
        assert result["breaks"][0]["event_index"] == 2
        assert result["breaks"][0]["event_id"] == "event-003"

    def test_verify_chain_first_event_non_null_previous(self) -> None:
        """Test chain verification detects first event with non-null previous."""
        events = [
            {
                "id": "event-001",
                "event_hash": "hash1",
                "previous_hash": "should-be-null",  # Invalid
            },
        ]

        self.mock_store.get_audit_events.return_value = events

        result = self.audit_writer.verify_chain("deploy-001")

        assert result["valid"] is False
        assert len(result["breaks"]) == 1
        assert "non-null previous_hash" in result["breaks"][0]["issue"]

    def test_record_deployment_created(self) -> None:
        """Test helper for recording deployment creation."""
        event_id = record_deployment_created(
            audit_writer=self.audit_writer,
            deployment_id="deploy-001",
            organization_id="org-001",
            operator="operator@example.com",
            intent="new_onboarding",
            session_id="session-001",
        )

        assert event_id == "event-001"

        # Verify correct event type and details
        call_args = self.mock_store.insert_audit_event.call_args
        event = call_args[0][0]

        assert event["event_type"] == "deployment_created"
        assert event["actor"] == "operator@example.com"
        assert event["detail"]["organization_id"] == "org-001"
        assert event["detail"]["intent"] == "new_onboarding"

    def test_record_state_transition(self) -> None:
        """Test helper for recording state transition."""
        event_id = record_state_transition(
            audit_writer=self.audit_writer,
            deployment_id="deploy-001",
            actor="operator",
            from_state="planning",
            to_state="generating",
            reason="Plan approved",
        )

        assert event_id == "event-001"

        # Verify event details
        call_args = self.mock_store.insert_audit_event.call_args
        event = call_args[0][0]

        assert event["event_type"] == "deployment_state_transition"
        assert event["detail"]["from_state"] == "planning"
        assert event["detail"]["to_state"] == "generating"
        assert event["detail"]["reason"] == "Plan approved"

    def test_record_approval_decision_approved(self) -> None:
        """Test helper for recording approval decision."""
        event_id = record_approval_decision(
            audit_writer=self.audit_writer,
            deployment_id="deploy-001",
            action_id="action-001",
            operator="operator@example.com",
            decision="approved",
            proposal_hash="hash123",
            display_hash="display456",
        )

        assert event_id == "event-001"

        # Verify event details
        call_args = self.mock_store.insert_audit_event.call_args
        event = call_args[0][0]

        assert event["event_type"] == "approval_granted"
        assert event["actor"] == "operator@example.com"
        assert event["subject"] == "action-001"
        assert event["status"] == "approved"

    def test_record_action_execution(self) -> None:
        """Test helper for recording action execution."""
        event_id = record_action_execution(
            audit_writer=self.audit_writer,
            deployment_id="deploy-001",
            action_id="action-001",
            platform="vapi",
            operation="create_assistant",
            status="succeeded",
            receipt_id="receipt-001",
        )

        assert event_id == "event-001"

        # Verify event details
        call_args = self.mock_store.insert_audit_event.call_args
        event = call_args[0][0]

        assert event["event_type"] == "action_succeeded"
        assert event["detail"]["platform"] == "vapi"
        assert event["detail"]["operation"] == "create_assistant"
        assert event["detail"]["receipt_id"] == "receipt-001"

    def test_event_immutable_created_at(self) -> None:
        """Test that events include immutable timestamp."""
        before = datetime.now(UTC)

        event_id = self.audit_writer.record_event(
            deployment_id="deploy-001",
            event_type=AuditEventType.DEPLOYMENT_CREATED,
            actor="operator",
            subject="deploy-001",
            status="created",
        )

        after = datetime.now(UTC)

        # Get event
        call_args = self.mock_store.insert_audit_event.call_args
        event = call_args[0][0]

        # Verify timestamp is within range
        created_at = datetime.fromisoformat(event["created_at"].replace("Z", "+00:00"))
        assert before <= created_at <= after
