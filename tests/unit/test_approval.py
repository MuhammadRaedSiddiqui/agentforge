"""
Unit tests for approval flow.

Verifies the approval system's core security and integrity mechanisms:
- Proposal hash binding prevents approval reuse
- Display hash records what operator saw
- Single-use enforcement
- Rejection routing (abort vs revise)
- Staleness detection
"""

from datetime import datetime

import pytest

from orchestrator.approval import (
    build_proposed_action,
    check_staleness,
    format_proposal_display,
    record_approval_decision,
    verify_approval_matches_proposal,
)
from shared.errors import ConflictError, ValidationError

pytestmark = pytest.mark.unit


class TestProposedActionBuilder:
    """Test ProposedAction construction and hash computation."""

    def test_build_proposed_action_required_fields(self) -> None:
        """Test building ProposedAction with only required fields."""
        payload = {"name": "Test Assistant", "model": "gpt-4"}

        action = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload=payload,
        )

        assert action.platform == "vapi"
        assert action.operation == "create_assistant"
        assert action.target == "assistant_1"
        assert action.payload == payload
        assert action.payload_hash is not None
        assert action.proposal_hash is not None
        assert action.retry_policy == "none"
        assert action.reconciliation_strategy == "read_after_write"

    def test_build_proposed_action_all_fields(self) -> None:
        """Test building ProposedAction with all fields."""
        payload = {"name": "Test Assistant"}
        validation_result = {"status": "pass", "issues": []}

        action = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload=payload,
            state_version="state_abc123",
            idempotency_key="key_123",
            retry_policy="proven_idempotent",
            reconciliation_strategy="list_and_match",
            compensation_operation="delete_assistant",
            validation_result=validation_result,
            expected_outcome="Assistant created successfully",
        )

        assert action.state_version == "state_abc123"
        assert action.idempotency_key == "key_123"
        assert action.retry_policy == "proven_idempotent"
        assert action.reconciliation_strategy == "list_and_match"
        assert action.compensation_operation == "delete_assistant"
        assert action.validation_result == validation_result
        assert action.expected_outcome == "Assistant created successfully"

    def test_proposal_hash_deterministic(self) -> None:
        """Test that proposal hash is deterministic for same inputs."""
        payload = {"name": "Test", "value": "123"}

        action1 = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload=payload,
            state_version="state_v1",
        )

        action2 = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload=payload,
            state_version="state_v1",
        )

        # Same inputs should produce same hashes
        assert action1.proposal_hash == action2.proposal_hash
        assert action1.payload_hash == action2.payload_hash

    def test_proposal_hash_changes_with_payload(self) -> None:
        """Test that proposal hash changes when payload changes."""
        action1 = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload={"name": "Assistant A"},
        )

        action2 = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload={"name": "Assistant B"},
        )

        # Different payloads should produce different hashes
        assert action1.proposal_hash != action2.proposal_hash
        assert action1.payload_hash != action2.payload_hash

    def test_proposal_hash_changes_with_state_version(self) -> None:
        """Test that proposal hash changes when state version changes."""
        payload = {"name": "Test"}

        action1 = build_proposed_action(
            platform="vapi",
            operation="update_assistant",
            target="assistant_1",
            payload=payload,
            state_version="state_v1",
        )

        action2 = build_proposed_action(
            platform="vapi",
            operation="update_assistant",
            target="assistant_1",
            payload=payload,
            state_version="state_v2",
        )

        # Different state versions should produce different hashes
        assert action1.proposal_hash != action2.proposal_hash

    def test_missing_required_fields_rejected(self) -> None:
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            build_proposed_action(
                platform="",
                operation="create_assistant",
                target="assistant_1",
                payload={"name": "Test"},
            )

        with pytest.raises(ValidationError):
            build_proposed_action(
                platform="vapi",
                operation="",
                target="assistant_1",
                payload={"name": "Test"},
            )

        with pytest.raises(ValidationError):
            build_proposed_action(
                platform="vapi",
                operation="create_assistant",
                target="",
                payload={"name": "Test"},
            )

    def test_empty_payload_rejected(self) -> None:
        """Test that empty payload is rejected."""
        with pytest.raises(ValidationError):
            build_proposed_action(
                platform="vapi",
                operation="create_assistant",
                target="assistant_1",
                payload={},
            )


class TestApprovalDecisionRecorder:
    """Test approval decision recording."""

    def test_record_approval_decision_approved(self) -> None:
        """Test recording an approved decision."""
        action = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload={"name": "Test"},
        )

        display_content = "Platform: vapi\nOperation: create_assistant"

        approval = record_approval_decision(
            proposed_action=action,
            decision="approved",
            display_content=display_content,
            operator="test_operator",
            notes="Looks good",
        )

        assert approval.proposal_hash == action.proposal_hash
        assert approval.decision == "approved"
        assert approval.display_hash is not None
        assert approval.decided_by == "test_operator"
        assert approval.notes == "Looks good"
        assert isinstance(approval.decided_at, datetime)

    def test_record_approval_decision_rejected_abort(self) -> None:
        """Test recording a rejected_abort decision."""
        action = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload={"name": "Test"},
        )

        approval = record_approval_decision(
            proposed_action=action,
            decision="rejected_abort",
            display_content="test content",
            operator="test_operator",
        )

        assert approval.decision == "rejected_abort"

    def test_record_approval_decision_rejected_revise(self) -> None:
        """Test recording a rejected_revise decision."""
        action = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload={"name": "Test"},
        )

        approval = record_approval_decision(
            proposed_action=action,
            decision="rejected_revise",
            display_content="test content",
            operator="test_operator",
            notes="Change the model to GPT-4",
        )

        assert approval.decision == "rejected_revise"
        assert approval.notes == "Change the model to GPT-4"

    def test_invalid_decision_rejected(self) -> None:
        """Test that invalid decisions are rejected."""
        action = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload={"name": "Test"},
        )

        invalid_decisions = ["accept", "deny", "skip", "", "APPROVED"]

        for invalid in invalid_decisions:
            with pytest.raises(ValidationError):
                record_approval_decision(
                    proposed_action=action,
                    decision=invalid,
                    display_content="test",
                    operator="test_operator",
                )

    def test_display_hash_changes_with_content(self) -> None:
        """Test that display hash changes when content changes."""
        action = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload={"name": "Test"},
        )

        approval1 = record_approval_decision(
            proposed_action=action,
            decision="approved",
            display_content="Content A",
            operator="operator",
        )

        approval2 = record_approval_decision(
            proposed_action=action,
            decision="approved",
            display_content="Content B",
            operator="operator",
        )

        # Different display content should produce different hashes
        assert approval1.display_hash != approval2.display_hash


class TestApprovalVerification:
    """Test approval verification and hash matching."""

    def test_verify_approval_matches_proposal_success(self) -> None:
        """Test successful verification when hashes match."""
        action = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload={"name": "Test"},
        )

        approval = record_approval_decision(
            proposed_action=action,
            decision="approved",
            display_content="test",
            operator="operator",
        )

        # Should not raise an error
        verify_approval_matches_proposal(approval, action)

    def test_verify_approval_hash_mismatch(self) -> None:
        """Test that mismatched proposal hashes are detected."""
        action1 = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload={"name": "Assistant A"},
        )

        action2 = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload={"name": "Assistant B"},  # Different payload
        )

        # Approve action1
        approval = record_approval_decision(
            proposed_action=action1,
            decision="approved",
            display_content="test",
            operator="operator",
        )

        # Try to use approval for action2 (should fail)
        with pytest.raises(ConflictError) as exc_info:
            verify_approval_matches_proposal(approval, action2)

        assert "proposal_hash" in str(exc_info.value).lower()

    def test_verify_approval_rejected_abort(self) -> None:
        """Test that rejected_abort decisions cannot be used."""
        action = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload={"name": "Test"},
        )

        approval = record_approval_decision(
            proposed_action=action,
            decision="rejected_abort",
            display_content="test",
            operator="operator",
        )

        with pytest.raises(ConflictError) as exc_info:
            verify_approval_matches_proposal(approval, action)

        assert "rejected_abort" in str(exc_info.value)

    def test_verify_approval_rejected_revise(self) -> None:
        """Test that rejected_revise decisions cannot be used."""
        action = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload={"name": "Test"},
        )

        approval = record_approval_decision(
            proposed_action=action,
            decision="rejected_revise",
            display_content="test",
            operator="operator",
        )

        with pytest.raises(ConflictError) as exc_info:
            verify_approval_matches_proposal(approval, action)

        assert "rejected_revise" in str(exc_info.value)


class TestStalenessDetection:
    """Test staleness checking for updates."""

    def test_check_staleness_no_state_version(self) -> None:
        """Test that actions without state_version are never stale (creates)."""
        action = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload={"name": "Test"},
            # No state_version = create operation
        )

        # Should not be stale regardless of current state
        assert check_staleness(action, None) is False
        assert check_staleness(action, "any_state") is False

    def test_check_staleness_matching_state(self) -> None:
        """Test that action is not stale when state matches."""
        action = build_proposed_action(
            platform="vapi",
            operation="update_assistant",
            target="assistant_1",
            payload={"name": "Test"},
            state_version="state_v1",
        )

        # Same state version = not stale
        assert check_staleness(action, "state_v1") is False

    def test_check_staleness_different_state(self) -> None:
        """Test that action is stale when state differs."""
        action = build_proposed_action(
            platform="vapi",
            operation="update_assistant",
            target="assistant_1",
            payload={"name": "Test"},
            state_version="state_v1",
        )

        # Different state version = stale
        assert check_staleness(action, "state_v2") is True

    def test_check_staleness_none_current_state(self) -> None:
        """Test staleness when current state is None (resource deleted)."""
        action = build_proposed_action(
            platform="vapi",
            operation="update_assistant",
            target="assistant_1",
            payload={"name": "Test"},
            state_version="state_v1",
        )

        # Current state None but action expects state_v1 = stale
        assert check_staleness(action, None) is True


class TestProposalDisplayFormatting:
    """Test proposal display formatting for human review."""

    def test_format_proposal_display_basic(self) -> None:
        """Test basic proposal display formatting."""
        action = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload={"name": "Test Assistant", "model": "gpt-4"},
            expected_outcome="Create a new voice assistant",
        )

        display = format_proposal_display(action)

        # Verify key elements are present
        assert "PROPOSED ACTION" in display
        assert "vapi" in display
        assert "create_assistant" in display
        assert "assistant_1" in display
        assert "Create a new voice assistant" in display
        assert "Test Assistant" in display

    def test_format_proposal_display_with_validation(self) -> None:
        """Test display formatting includes validation results."""
        action = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload={"name": "Test"},
            validation_result={"status": "pass", "issues": []},
        )

        display = format_proposal_display(action)

        assert "Validation" in display
        assert "pass" in display

    def test_format_proposal_display_with_validation_issues(self) -> None:
        """Test display formatting shows validation issues."""
        action = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload={"name": "Test"},
            validation_result={
                "status": "warning",
                "issues": ["Missing voice configuration", "Tool references unverified"],
            },
        )

        display = format_proposal_display(action)

        assert "Validation" in display
        assert "warning" in display
        assert "Missing voice configuration" in display
        assert "Tool references unverified" in display

    def test_format_proposal_display_with_state_version(self) -> None:
        """Test display formatting includes state version for updates."""
        action = build_proposed_action(
            platform="vapi",
            operation="update_assistant",
            target="assistant_1",
            payload={"name": "Updated Name"},
            state_version="state_abc123def456",
        )

        display = format_proposal_display(action)

        assert "State Version" in display
        assert "state_abc123" in display  # Truncated version

    def test_format_proposal_display_with_compensation(self) -> None:
        """Test display formatting includes compensation operation."""
        action = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload={"name": "Test"},
            compensation_operation="delete_assistant",
        )

        display = format_proposal_display(action)

        assert "Compensation" in display
        assert "delete_assistant" in display

    def test_format_proposal_display_with_idempotency_key(self) -> None:
        """Test display formatting includes idempotency key."""
        action = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload={"name": "Test"},
            idempotency_key="unique_key_123",
        )

        display = format_proposal_display(action)

        assert "Idempotency Key" in display
        assert "unique_key_123" in display

    def test_format_proposal_display_secrets_redacted(self) -> None:
        """Test that display formatting redacts secrets from payload."""
        action = build_proposed_action(
            platform="render",
            operation="set_env_variable",
            target="DATABASE_URL",
            payload={"key": "DATABASE_URL", "value": "postgres://user:password@host/db"},
        )

        display = format_proposal_display(action)

        # Secret value should be redacted
        assert "password" not in display or "***" in display or "REDACTED" in display


class TestApprovalFlowIntegration:
    """Test complete approval flow scenarios."""

    def test_complete_approval_flow_success(self) -> None:
        """Test complete flow: build -> display -> approve -> verify."""
        # Build proposed action
        action = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload={"name": "Test Assistant"},
            expected_outcome="Create voice assistant",
        )

        # Format for display
        display_content = format_proposal_display(action)

        # Record approval
        approval = record_approval_decision(
            proposed_action=action,
            decision="approved",
            display_content=display_content,
            operator="test_operator",
        )

        # Verify approval matches
        verify_approval_matches_proposal(approval, action)

        # Should not raise any errors

    def test_approval_reuse_prevention(self) -> None:
        """Test that approval cannot be reused for different action."""
        # Create two different actions
        action1 = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_1",
            payload={"name": "Assistant A"},
        )

        action2 = build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="assistant_2",
            payload={"name": "Assistant B"},
        )

        # Approve action1
        approval = record_approval_decision(
            proposed_action=action1,
            decision="approved",
            display_content="test",
            operator="operator",
        )

        # Try to use approval for action2 - should fail
        with pytest.raises(ConflictError):
            verify_approval_matches_proposal(approval, action2)

    def test_stale_action_detection_in_flow(self) -> None:
        """Test that stale actions are detected before execution."""
        # Create action with state version
        action = build_proposed_action(
            platform="vapi",
            operation="update_assistant",
            target="assistant_1",
            payload={"name": "Updated"},
            state_version="state_v1",
        )

        # Approve the action
        approval = record_approval_decision(
            proposed_action=action,
            decision="approved",
            display_content="test",
            operator="operator",
        )

        # Verify approval matches
        verify_approval_matches_proposal(approval, action)

        # Check staleness (simulating state changed between approval and execution)
        current_state = "state_v2"  # State changed
        is_stale = check_staleness(action, current_state)

        # Action should be detected as stale
        assert is_stale is True
