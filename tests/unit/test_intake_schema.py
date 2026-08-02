"""
Unit tests for intake schema validation.

Tests for valid intake, missing fields, invalid formats, and capability-specific
required fields.
"""

import pytest

from orchestrator.intake_schema import validate_intake


@pytest.mark.unit
class TestIntakeSchema:
    """Tests for intake schema validation."""

    def test_valid_minimal_intake(self) -> None:
        """Should accept valid minimal intake."""
        intake = {
            "organization_id": "test_org",
            "business_name": "Test Business",
            "phone_number": "+15555550100",
            "voice_id": "test_voice_id",
            "timezone": "America/New_York",
            "business_hours": {"monday": [{"open": "09:00", "close": "17:00"}]},
            "services_offered": [{"name": "Consultation", "duration_minutes": 30}],
            "enabled_capabilities": ["availability"],
            "external_identifiers": {},
        }

        result = validate_intake(intake)
        assert result["valid"] is True
        assert "errors" not in result or len(result["errors"]) == 0

    def test_missing_required_field_business_name(self) -> None:
        """Should reject intake missing business_name."""
        intake = {
            "organization_id": "test_org",
            # business_name missing
            "phone_number": "+15555550100",
            "voice_id": "test_voice_id",
            "timezone": "America/New_York",
            "business_hours": {},
            "services_offered": [],
            "enabled_capabilities": [],
            "external_identifiers": {},
        }

        result = validate_intake(intake)
        assert result["valid"] is False
        assert any("business_name" in str(err).lower() for err in result["errors"])

    def test_missing_required_field_phone_number(self) -> None:
        """Should reject intake missing phone_number."""
        intake = {
            "organization_id": "test_org",
            "business_name": "Test Business",
            # phone_number missing
            "voice_id": "test_voice_id",
            "timezone": "America/New_York",
            "business_hours": {},
            "services_offered": [],
            "enabled_capabilities": [],
            "external_identifiers": {},
        }

        result = validate_intake(intake)
        assert result["valid"] is False
        assert any("phone_number" in str(err).lower() for err in result["errors"])

    def test_invalid_phone_number_format(self) -> None:
        """Should reject invalid E.164 phone number."""
        intake = {
            "organization_id": "test_org",
            "business_name": "Test Business",
            "phone_number": "555-1234",  # Invalid format
            "voice_id": "test_voice_id",
            "timezone": "America/New_York",
            "business_hours": {},
            "services_offered": [],
            "enabled_capabilities": [],
            "external_identifiers": {},
        }

        result = validate_intake(intake)
        assert result["valid"] is False
        assert any(
            "phone" in str(err).lower() and "format" in str(err).lower() for err in result["errors"]
        )

    def test_invalid_timezone(self) -> None:
        """Should reject invalid IANA timezone."""
        intake = {
            "organization_id": "test_org",
            "business_name": "Test Business",
            "phone_number": "+15555550100",
            "voice_id": "test_voice_id",
            "timezone": "Invalid/Timezone",  # Not a valid IANA timezone
            "business_hours": {},
            "services_offered": [],
            "enabled_capabilities": [],
            "external_identifiers": {},
        }

        result = validate_intake(intake)
        assert result["valid"] is False
        assert any("timezone" in str(err).lower() for err in result["errors"])

    def test_booking_capability_requires_calendar_id(self) -> None:
        """Should require booking_calendar_id when booking capability enabled."""
        intake = {
            "organization_id": "test_org",
            "business_name": "Test Business",
            "phone_number": "+15555550100",
            "voice_id": "test_voice_id",
            "timezone": "America/New_York",
            "business_hours": {},
            "services_offered": [],
            "enabled_capabilities": ["booking"],
            "external_identifiers": {},
            # booking_calendar_id missing
        }

        result = validate_intake(intake)
        assert result["valid"] is False
        assert any("booking_calendar_id" in str(err).lower() for err in result["errors"])

    def test_cancellation_capability_requires_window(self) -> None:
        """Should require cancellation_window_hours when cancellation enabled."""
        intake = {
            "organization_id": "test_org",
            "business_name": "Test Business",
            "phone_number": "+15555550100",
            "voice_id": "test_voice_id",
            "timezone": "America/New_York",
            "business_hours": {},
            "services_offered": [],
            "enabled_capabilities": ["cancellation"],
            "external_identifiers": {},
            # cancellation_window_hours missing
        }

        result = validate_intake(intake)
        assert result["valid"] is False
        assert any("cancellation_window_hours" in str(err).lower() for err in result["errors"])

    def test_rescheduling_capability_requires_policy(self) -> None:
        """Should require rescheduling_policy when rescheduling enabled."""
        intake = {
            "organization_id": "test_org",
            "business_name": "Test Business",
            "phone_number": "+15555550100",
            "voice_id": "test_voice_id",
            "timezone": "America/New_York",
            "business_hours": {},
            "services_offered": [],
            "enabled_capabilities": ["rescheduling"],
            "external_identifiers": {},
            # rescheduling_policy missing
        }

        result = validate_intake(intake)
        assert result["valid"] is False
        assert any("rescheduling_policy" in str(err).lower() for err in result["errors"])

    def test_transfer_capability_requires_destination(self) -> None:
        """Should require transfer_destination when human_transfer enabled."""
        intake = {
            "organization_id": "test_org",
            "business_name": "Test Business",
            "phone_number": "+15555550100",
            "voice_id": "test_voice_id",
            "timezone": "America/New_York",
            "business_hours": {},
            "services_offered": [],
            "enabled_capabilities": ["human_transfer"],
            "external_identifiers": {},
            # transfer_destination missing
        }

        result = validate_intake(intake)
        assert result["valid"] is False
        assert any("transfer_destination" in str(err).lower() for err in result["errors"])

    def test_organization_id_normalization(self) -> None:
        """Should normalize organization_id to lowercase slug."""
        intake = {
            "organization_id": "Test-Org Name!",
            "business_name": "Test Business",
            "phone_number": "+15555550100",
            "voice_id": "test_voice_id",
            "timezone": "America/New_York",
            "business_hours": {},
            "services_offered": [],
            "enabled_capabilities": [],
            "external_identifiers": {},
        }

        result = validate_intake(intake)

        # Should normalize organization_id
        assert result.get("normalized_organization_id") == "test_org_name"

    def test_empty_capabilities_allowed(self) -> None:
        """Should allow empty capabilities list."""
        intake = {
            "organization_id": "test_org",
            "business_name": "Test Business",
            "phone_number": "+15555550100",
            "voice_id": "test_voice_id",
            "timezone": "America/New_York",
            "business_hours": {},
            "services_offered": [],
            "enabled_capabilities": [],  # Empty is allowed
            "external_identifiers": {},
        }

        result = validate_intake(intake)
        assert result["valid"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
