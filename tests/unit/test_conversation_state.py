"""Unit tests for orchestrator/conversation_state.py"""

import pytest
from orchestrator.conversation_state import (
    ConversationState,
    PartialIntakeData,
    SessionPhase,
)


class TestSessionPhase:
    def test_all_phases_defined(self) -> None:
        assert SessionPhase.GATHERING.value == "gathering"
        assert SessionPhase.CONFIRMING.value == "confirming"
        assert SessionPhase.EXECUTING.value == "executing"
        assert SessionPhase.COMPLETE.value == "complete"
        assert SessionPhase.ABORTED.value == "aborted"


class TestPartialIntakeData:
    def test_default_all_none(self) -> None:
        p = PartialIntakeData()
        assert p.org_id is None
        assert p.business_name is None
        assert p.phone_number is None
        assert p.voice_id is None
        assert p.capabilities is None
        assert p.industry is None
        assert p.timezone is None
        assert p.business_hours is None

    def test_required_fields_present_all_filled(self) -> None:
        p = PartialIntakeData(
            org_id="miami_glow",
            business_name="Miami Glow Salon",
            phone_number="+13055551234",
            voice_id="jennifer",
            capabilities=["booking", "cancellation"],
        )
        assert p.required_fields_present() is True

    def test_required_fields_present_missing_one(self) -> None:
        p = PartialIntakeData(
            org_id="miami_glow",
            business_name="Miami Glow Salon",
            phone_number="+13055551234",
            voice_id="jennifer",
            capabilities=None,
        )
        assert p.required_fields_present() is False

    def test_required_fields_present_all_missing(self) -> None:
        p = PartialIntakeData()
        assert p.required_fields_present() is False

    def test_missing_required_fields_all_missing(self) -> None:
        p = PartialIntakeData()
        missing = p.missing_required_fields()
        assert set(missing) == {"org_id", "business_name", "phone_number", "voice_id", "capabilities"}

    def test_missing_required_fields_partial(self) -> None:
        p = PartialIntakeData(
            org_id="test_org",
            business_name="Test Org",
        )
        missing = p.missing_required_fields()
        assert "org_id" not in missing
        assert "business_name" not in missing
        assert "phone_number" in missing
        assert "voice_id" in missing
        assert "capabilities" in missing

    def test_missing_required_fields_none_missing(self) -> None:
        p = PartialIntakeData(
            org_id="test",
            business_name="Test",
            phone_number="+1234",
            voice_id="v1",
            capabilities=["booking"],
        )
        assert p.missing_required_fields() == []

    def test_empty_list_capabilities_counts_as_missing(self) -> None:
        p = PartialIntakeData(
            org_id="test",
            business_name="Test",
            phone_number="+1234",
            voice_id="v1",
            capabilities=[],
        )
        assert p.required_fields_present() is False
        assert "capabilities" in p.missing_required_fields()

    def test_to_dict(self) -> None:
        p = PartialIntakeData(
            org_id="test",
            business_name="Test Biz",
            capabilities=["booking"],
        )
        d = p.to_dict()
        assert d["org_id"] == "test"
        assert d["business_name"] == "Test Biz"
        assert d["capabilities"] == ["booking"]
        assert d["phone_number"] is None


class TestConversationState:
    def test_default_state(self) -> None:
        state = ConversationState()
        assert state.phase == SessionPhase.GATHERING
        assert state.partial_intake.required_fields_present() is False
        assert state.messages == []
        assert state.confirmed_plan is None
        assert state.session_id is None

    def test_phase_can_be_set(self) -> None:
        state = ConversationState()
        state.phase = SessionPhase.CONFIRMING
        assert state.phase == SessionPhase.CONFIRMING

    def test_messages_append(self) -> None:
        state = ConversationState()
        state.messages.append({"role": "user", "parts": ["hello"]})
        assert len(state.messages) == 1
        assert state.messages[0]["role"] == "user"

    def test_confirmed_plan_set(self) -> None:
        state = ConversationState()
        state.confirmed_plan = {"org_id": "test", "capabilities": ["booking"]}
        assert state.confirmed_plan["org_id"] == "test"

    def test_independent_instances(self) -> None:
        state1 = ConversationState()
        state2 = ConversationState()
        state1.messages.append({"role": "user", "parts": ["msg1"]})
        assert len(state2.messages) == 0
