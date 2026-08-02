"""
Audit event recording for Agent Forge.

Implements T135: Audit event writer with:
- Event type catalog
- Actor and subject tracking
- Sanitized detail storage
- Hash computation and chain linkage
- Append-only enforcement

Every deployment decision is recorded as an immutable audit event.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any, cast

from adapters.supabase_internal import SupabaseInternalClient
from shared.hashing import hash_json
from shared.redaction import redact_dict, redact_secrets


class AuditEventType(Enum):
    """Catalog of audit event types."""

    # Deployment lifecycle
    DEPLOYMENT_CREATED = "deployment_created"
    DEPLOYMENT_STATE_TRANSITION = "deployment_state_transition"
    DEPLOYMENT_COMPLETED = "deployment_completed"
    DEPLOYMENT_FAILED = "deployment_failed"
    DEPLOYMENT_ABORTED = "deployment_aborted"

    # Task execution
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_VALIDATION_PASSED = "task_validation_passed"
    TASK_VALIDATION_FAILED = "task_validation_failed"

    # Approval flow
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_REJECTED_ABORT = "approval_rejected_abort"
    APPROVAL_REJECTED_REVISE = "approval_rejected_revise"

    # Action execution
    ACTION_EXECUTING = "action_executing"
    ACTION_SUCCEEDED = "action_succeeded"
    ACTION_FAILED = "action_failed"
    ACTION_AMBIGUOUS = "action_ambiguous"

    # Recovery
    RECOVERY_STARTED = "recovery_started"
    RECOVERY_RECONCILED = "recovery_reconciled"
    RETRY_ATTEMPTED = "retry_attempted"
    COMPENSATION_STARTED = "compensation_started"
    COMPENSATION_SUCCEEDED = "compensation_succeeded"
    COMPENSATION_FAILED = "compensation_failed"

    # Corrections
    CORRECTION_REQUESTED = "correction_requested"
    CORRECTION_APPLIED = "correction_applied"
    CORRECTION_ESCALATED = "correction_escalated"


class AuditEventWriter:
    """
    Writes audit events to the internal operational store.

    Events are immutable, hash-chained, and sanitized.
    """

    def __init__(self, internal_store: SupabaseInternalClient) -> None:
        """
        Initialize audit event writer.

        Args:
            internal_store: SupabaseInternalClient instance
        """
        self.internal_store = internal_store

    def record_event(
        self,
        deployment_id: str,
        event_type: AuditEventType,
        actor: str,
        subject: str,
        status: str,
        detail: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> str:
        """
        Record an audit event.

        Args:
            deployment_id: Deployment this event belongs to
            event_type: Type of event from AuditEventType enum
            actor: Who performed the action (operator, system, agent_name)
            subject: What was acted upon (task_id, action_id, artifact_id)
            status: Outcome status (started, success, failed, etc.)
            detail: Additional sanitized detail (secrets removed)
            session_id: Optional session identifier

        Returns:
            Event ID
        """
        # Sanitize detail if provided
        sanitized_detail = self._sanitize_detail(detail) if detail else None

        # Get previous event hash for chain
        previous_hash = self._get_last_event_hash(deployment_id)

        # Compute event hash
        event_data = {
            "deployment_id": deployment_id,
            "event_type": event_type.value,
            "actor": actor,
            "subject": subject,
            "status": status,
            "detail": sanitized_detail,
            "previous_hash": previous_hash,
        }

        event_hash = hash_json(event_data)

        # Record event
        event = {
            "deployment_id": deployment_id,
            "session_id": session_id,
            "event_type": event_type.value,
            "actor": actor,
            "subject": subject,
            "status": status,
            "detail": sanitized_detail,
            "event_hash": event_hash,
            "previous_hash": previous_hash,
            "created_at": datetime.now(UTC).isoformat(),
        }

        # Insert into store (append-only)
        event_id = self.internal_store.insert_audit_event(event)

        return str(event_id)

    @staticmethod
    def _sanitize_detail(detail: dict[str, Any]) -> dict[str, Any]:
        """Redact sensitive detail values without corrupting structured data."""
        redacted = redact_dict(detail)
        sensitive_key_parts = {
            "api_key",
            "apikey",
            "api-key",
            "secret",
            "token",
            "password",
            "authorization",
            "auth",
            "private_key",
            "credential",
        }

        def fully_redact(value: Any) -> Any:
            if isinstance(value, dict):
                return {
                    key: "[REDACTED]"
                    if any(part in key.lower() for part in sensitive_key_parts)
                    else fully_redact(child)
                    for key, child in value.items()
                }
            if isinstance(value, list):
                return [fully_redact(item) for item in value]
            return value

        return cast(dict[str, Any], fully_redact(redacted))

    def _get_last_event_hash(self, deployment_id: str) -> str | None:
        """
        Get the hash of the last event in the chain for this deployment.

        Args:
            deployment_id: Deployment identifier

        Returns:
            Previous event hash, or None if this is the first event
        """
        last_event = self.internal_store.get_last_audit_event(deployment_id)

        if last_event:
            event_hash = last_event.get("event_hash")
            return str(event_hash) if event_hash is not None else None

        return None

    def verify_chain(self, deployment_id: str) -> dict[str, Any]:
        """
        Verify the hash chain for a deployment's audit events.

        Args:
            deployment_id: Deployment identifier

        Returns:
            Verification result with any breaks detected
        """
        events = self.internal_store.get_audit_events(deployment_id)

        if not events:
            return {
                "valid": True,
                "event_count": 0,
                "message": "No events to verify",
            }

        breaks = []

        for i, event in enumerate(events):
            # First event should have null previous_hash
            if i == 0:
                if event.get("previous_hash") is not None:
                    breaks.append(
                        {
                            "event_index": i,
                            "event_id": event.get("id"),
                            "issue": "First event has non-null previous_hash",
                        }
                    )
                continue

            # Subsequent events should chain to previous
            previous_event = events[i - 1]
            expected_previous = previous_event.get("event_hash")
            actual_previous = event.get("previous_hash")

            if expected_previous != actual_previous:
                breaks.append(
                    {
                        "event_index": i,
                        "event_id": event.get("id"),
                        "issue": "Hash chain break",
                        "expected_previous": expected_previous,
                        "actual_previous": actual_previous,
                    }
                )

        return {
            "valid": len(breaks) == 0,
            "event_count": len(events),
            "breaks": breaks,
            "message": "Hash chain valid"
            if len(breaks) == 0
            else f"{len(breaks)} break(s) detected",
        }


def record_deployment_created(
    audit_writer: AuditEventWriter,
    deployment_id: str,
    organization_id: str,
    operator: str,
    intent: str,
    session_id: str | None = None,
) -> str:
    """
    Record deployment creation event.

    Args:
        audit_writer: AuditEventWriter instance
        deployment_id: Deployment identifier
        organization_id: Organization identifier
        operator: Operator identifier
        intent: Deployment intent
        session_id: Optional session identifier

    Returns:
        Event ID
    """
    return audit_writer.record_event(
        deployment_id=deployment_id,
        event_type=AuditEventType.DEPLOYMENT_CREATED,
        actor=operator,
        subject=deployment_id,
        status="created",
        detail={
            "organization_id": organization_id,
            "intent": intent,
        },
        session_id=session_id,
    )


def record_state_transition(
    audit_writer: AuditEventWriter,
    deployment_id: str,
    actor: str,
    from_state: str,
    to_state: str,
    reason: str | None = None,
    session_id: str | None = None,
) -> str:
    """
    Record deployment state transition.

    Args:
        audit_writer: AuditEventWriter instance
        deployment_id: Deployment identifier
        actor: Who triggered the transition
        from_state: Previous state
        to_state: New state
        reason: Optional reason for transition
        session_id: Optional session identifier

    Returns:
        Event ID
    """
    return audit_writer.record_event(
        deployment_id=deployment_id,
        event_type=AuditEventType.DEPLOYMENT_STATE_TRANSITION,
        actor=actor,
        subject=deployment_id,
        status=to_state,
        detail={
            "from_state": from_state,
            "to_state": to_state,
            "reason": reason,
        },
        session_id=session_id,
    )


def record_approval_decision(
    audit_writer: AuditEventWriter,
    deployment_id: str,
    action_id: str,
    operator: str,
    decision: str,
    proposal_hash: str,
    display_hash: str,
    session_id: str | None = None,
) -> str:
    """
    Record approval decision event.

    Args:
        audit_writer: AuditEventWriter instance
        deployment_id: Deployment identifier
        action_id: Action identifier
        operator: Operator who made decision
        decision: Decision (approved, rejected_abort, rejected_revise)
        proposal_hash: Proposal hash
        display_hash: Display hash
        session_id: Optional session identifier

    Returns:
        Event ID
    """
    event_type_map = {
        "approved": AuditEventType.APPROVAL_GRANTED,
        "rejected_abort": AuditEventType.APPROVAL_REJECTED_ABORT,
        "rejected_revise": AuditEventType.APPROVAL_REJECTED_REVISE,
    }

    event_type = event_type_map.get(decision, AuditEventType.APPROVAL_REQUESTED)

    return audit_writer.record_event(
        deployment_id=deployment_id,
        event_type=event_type,
        actor=operator,
        subject=action_id,
        status=decision,
        detail={
            "proposal_hash": proposal_hash,
            "display_hash": display_hash,
        },
        session_id=session_id,
    )


def record_action_execution(
    audit_writer: AuditEventWriter,
    deployment_id: str,
    action_id: str,
    platform: str,
    operation: str,
    status: str,
    receipt_id: str | None = None,
    error_message: str | None = None,
    session_id: str | None = None,
) -> str:
    """
    Record action execution event.

    Args:
        audit_writer: AuditEventWriter instance
        deployment_id: Deployment identifier
        action_id: Action identifier
        platform: Platform (vapi, make, supabase, render)
        operation: Operation type
        status: Status (executing, succeeded, failed, ambiguous)
        receipt_id: Optional receipt identifier
        error_message: Optional sanitized error message
        session_id: Optional session identifier

    Returns:
        Event ID
    """
    event_type_map = {
        "executing": AuditEventType.ACTION_EXECUTING,
        "succeeded": AuditEventType.ACTION_SUCCEEDED,
        "failed": AuditEventType.ACTION_FAILED,
        "ambiguous": AuditEventType.ACTION_AMBIGUOUS,
    }

    event_type = event_type_map.get(status, AuditEventType.ACTION_EXECUTING)

    detail = {
        "platform": platform,
        "operation": operation,
    }

    if receipt_id:
        detail["receipt_id"] = receipt_id

    if error_message:
        # Redact any secrets in error message
        detail["error_message"] = redact_secrets(error_message)

    return audit_writer.record_event(
        deployment_id=deployment_id,
        event_type=event_type,
        actor="system",
        subject=action_id,
        status=status,
        detail=detail,
        session_id=session_id,
    )
