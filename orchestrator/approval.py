"""
Approval flow for Agent Forge.

Implements proposed action construction, approval display, and decision recording
following the per-action approval requirement from the constitution.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from shared.errors import ConflictError, ValidationError
from shared.hashing import hash_content, hash_json


@dataclass
class ProposedAction:
    """
    Represents a proposed external action requiring human approval.

    Every external side effect must be wrapped in a ProposedAction with:
    - Immutable proposal hash binding the exact operation
    - Platform, operation, and target identification
    - Payload hash for verification
    - State version for staleness detection
    - Idempotency key for safe retry
    - Retry policy and reconciliation strategy
    - Compensation operation for rollback
    """

    platform: str  # vapi, make, render, supabase_client
    operation: str  # create_assistant, create_scenario, set_env_variable, etc.
    target: str  # Resource identifier or name
    payload_hash: str  # SHA-256 of serialized payload
    state_version: str | None  # Current state hash before write
    proposal_hash: str  # Computed from all above fields
    idempotency_key: str | None  # For safe retry
    retry_policy: str  # none, read_only, proven_idempotent
    reconciliation_strategy: str  # How to verify remote state
    compensation_operation: str | None  # Reverse operation if needed
    payload: dict[str, Any]  # Actual payload (not hashed)
    validation_result: dict[str, Any] | None = None  # From validator
    expected_outcome: str | None = None  # Human-readable expectation


def build_proposed_action(
    platform: str,
    operation: str,
    target: str,
    payload: dict[str, Any],
    state_version: str | None = None,
    idempotency_key: str | None = None,
    retry_policy: str = "none",
    reconciliation_strategy: str = "read_after_write",
    compensation_operation: str | None = None,
    validation_result: dict[str, Any] | None = None,
    expected_outcome: str | None = None,
) -> ProposedAction:
    """
    Build a ProposedAction with computed proposal hash.

    The proposal hash is computed from all immutable fields to ensure
    approval is bound to the exact operation.

    Args:
        platform: Target platform
        operation: Operation name
        target: Resource identifier
        payload: Operation payload
        state_version: Current state hash (for updates)
        idempotency_key: Key for safe retry
        retry_policy: Retry classification
        reconciliation_strategy: How to verify
        compensation_operation: Reverse operation
        validation_result: Validation status
        expected_outcome: Human-readable outcome

    Returns:
        ProposedAction with computed proposal_hash
    """
    # Validate required fields
    if not platform or not operation or not target:
        raise ValidationError(
            "platform, operation, and target are required",
            field="platform,operation,target",
            context={"platform": platform, "operation": operation, "target": target},
        )

    if not payload:
        raise ValidationError(
            "payload cannot be empty",
            field="payload",
            context={"platform": platform, "operation": operation},
        )

    # Compute payload hash
    payload_hash = hash_json(payload)

    # Compute proposal hash from immutable fields
    proposal_data = {
        "platform": platform,
        "operation": operation,
        "target": target,
        "payload_hash": payload_hash,
        "state_version": state_version,
        "idempotency_key": idempotency_key,
    }
    proposal_hash = hash_json(proposal_data)

    return ProposedAction(
        platform=platform,
        operation=operation,
        target=target,
        payload_hash=payload_hash,
        state_version=state_version,
        proposal_hash=proposal_hash,
        idempotency_key=idempotency_key,
        retry_policy=retry_policy,
        reconciliation_strategy=reconciliation_strategy,
        compensation_operation=compensation_operation,
        payload=payload,
        validation_result=validation_result,
        expected_outcome=expected_outcome,
    )


@dataclass
class ApprovalDecision:
    """
    Records a human approval decision for a proposed action.

    The decision is bound to the proposal hash to prevent approval
    from being reused for a different action.
    """

    proposal_hash: str  # Must match the ProposedAction
    decision: str  # approved, rejected_abort, rejected_revise
    display_hash: str  # Hash of what was shown to operator
    decided_at: datetime
    decided_by: str  # Operator identifier
    notes: str | None = None


def record_approval_decision(
    proposed_action: ProposedAction,
    decision: str,
    display_content: str,
    operator: str,
    notes: str | None = None,
) -> ApprovalDecision:
    """
    Record an approval decision bound to a proposal hash.

    Args:
        proposed_action: The proposed action
        decision: approved, rejected_abort, rejected_revise
        display_content: What was shown to the operator
        operator: Operator identifier
        notes: Optional operator notes

    Returns:
        ApprovalDecision with computed display_hash

    Raises:
        ValidationError: If decision is invalid
    """
    valid_decisions = ["approved", "rejected_abort", "rejected_revise"]
    if decision not in valid_decisions:
        raise ValidationError(
            f"decision must be one of {valid_decisions}",
            field="decision",
            context={"provided": decision, "valid": valid_decisions},
        )

    # Compute hash of what was displayed
    display_hash = hash_content(display_content)

    return ApprovalDecision(
        proposal_hash=proposed_action.proposal_hash,
        decision=decision,
        display_hash=display_hash,
        decided_at=datetime.now(UTC),
        decided_by=operator,
        notes=notes,
    )


def verify_approval_matches_proposal(
    approval: ApprovalDecision,
    proposed_action: ProposedAction,
) -> None:
    """
    Verify that an approval decision matches the proposed action.

    This prevents an approval from being reused for a different action.

    Args:
        approval: The approval decision
        proposed_action: The proposed action to execute

    Raises:
        ConflictError: If hashes don't match
    """
    if approval.proposal_hash != proposed_action.proposal_hash:
        raise ConflictError(
            "Approval proposal_hash does not match proposed_action",
            resource="approval",
            context={
                "approval_hash": approval.proposal_hash,
                "proposal_hash": proposed_action.proposal_hash,
            },
        )

    if approval.decision != "approved":
        raise ConflictError(
            f"Cannot execute action with decision: {approval.decision}",
            resource="approval",
            context={"decision": approval.decision},
        )


def format_proposal_display(proposed_action: ProposedAction) -> str:
    """
    Format a proposed action for human review.

    Returns a human-readable string showing:
    - Platform and operation
    - Target resource
    - Payload (sanitized)
    - State version (if update)
    - Validation result
    - Expected outcome

    Args:
        proposed_action: The proposed action

    Returns:
        Formatted display string
    """
    lines = [
        "=" * 70,
        "PROPOSED ACTION - APPROVAL REQUIRED",
        "=" * 70,
        "",
        f"Platform: {proposed_action.platform}",
        f"Operation: {proposed_action.operation}",
        f"Target: {proposed_action.target}",
        "",
    ]

    # Expected outcome
    if proposed_action.expected_outcome:
        lines.append(f"Expected Outcome: {proposed_action.expected_outcome}")
        lines.append("")

    # State version (for updates)
    if proposed_action.state_version:
        lines.append(f"Current State Version: {proposed_action.state_version[:12]}...")
        lines.append("")

    # Validation result
    if proposed_action.validation_result:
        validation_status = proposed_action.validation_result.get("status", "unknown")
        lines.append(f"Validation: {validation_status}")
        if validation_status != "pass":
            issues = proposed_action.validation_result.get("issues", [])
            if issues:
                lines.append("Validation Issues:")
                for issue in issues:
                    lines.append(f"  - {issue}")
        lines.append("")

    # Payload (pretty-printed, sanitized)
    lines.append("Payload:")
    try:
        from shared.redaction import redact_dict

        sanitized_payload = redact_dict(proposed_action.payload)
        payload_str = json.dumps(sanitized_payload, indent=2)
        for line in payload_str.split("\n"):
            lines.append(f"  {line}")
    except Exception as e:
        lines.append(f"  <Error formatting payload: {e}>")

    lines.append("")

    # Metadata
    lines.append("Metadata:")
    lines.append(f"  Proposal Hash: {proposed_action.proposal_hash[:12]}...")
    lines.append(f"  Payload Hash: {proposed_action.payload_hash[:12]}...")
    lines.append(f"  Retry Policy: {proposed_action.retry_policy}")
    if proposed_action.idempotency_key:
        lines.append(f"  Idempotency Key: {proposed_action.idempotency_key}")
    if proposed_action.compensation_operation:
        lines.append(f"  Compensation: {proposed_action.compensation_operation}")

    lines.append("")
    lines.append("=" * 70)

    return "\n".join(lines)


def check_staleness(
    proposed_action: ProposedAction,
    current_state_version: str | None,
) -> bool:
    """
    Check if a proposed action is stale based on state version.

    An action is stale if:
    - It was created with a state_version (indicating an update)
    - The current state version differs from the proposal's state_version

    Args:
        proposed_action: The proposed action
        current_state_version: Current state hash from authoritative read

    Returns:
        True if stale, False if current
    """
    # If no state_version in proposal, it's a create operation (not an update)
    if not proposed_action.state_version:
        return False

    # If state_version exists, it must match current state
    return proposed_action.state_version != current_state_version
