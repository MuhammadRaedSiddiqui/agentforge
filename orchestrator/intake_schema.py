"""
Intake schema validation for Agent Forge.

Validates intake data with capability-specific requirements and normalizes fields.
"""

import re
from typing import Any

from adapters.supabase_internal import SupabaseInternalClient
from shared.ids import normalize_organization_id, validate_organization_id

# Valid IANA timezones (subset - expand as needed)
VALID_TIMEZONES = {
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Phoenix",
    "America/Anchorage",
    "America/Honolulu",
    "America/Toronto",
    "America/Vancouver",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Asia/Dubai",
    "Australia/Sydney",
    "UTC",
}

# Valid capabilities
VALID_CAPABILITIES = {
    "availability",
    "booking",
    "cancellation",
    "rescheduling",
    "human_transfer",
}

# Capabilities whose Make scenario reads the client's Supabase tenant. Every
# generated scenario for these opens with a `supabase:searchRows` module, so
# each one needs the schema migration and the organization row to exist.
#
# This was previously keyed on "booking" alone in three places, which meant an
# availability-only or cancellation-only client deployed scenarios that query a
# tenant nobody ever created — a deployment that succeeds and cannot work.
# human_transfer is absent because it generates no scenario and touches no
# database.
DATABASE_BACKED_CAPABILITIES = frozenset(
    {
        "availability",
        "booking",
        "cancellation",
        "rescheduling",
    }
)


def needs_database(capabilities: list[str] | set[str]) -> bool:
    """Whether this capability set requires a Supabase tenant and migration."""
    return bool(set(capabilities) & DATABASE_BACKED_CAPABILITIES)


class IntakeSchema:
    """
    Intake schema validator.

    Validates required fields, formats, and capability-specific requirements.
    """

    @staticmethod
    def validate_phone_number(phone: str) -> bool:
        """
        Validate E.164 phone number format.

        Args:
            phone: Phone number string

        Returns:
            True if valid E.164 format
        """
        # E.164: +[country code][number] (max 15 digits total)
        pattern = r"^\+[1-9]\d{1,14}$"
        return bool(re.match(pattern, phone))

    @staticmethod
    def validate_timezone(timezone: str) -> bool:
        """
        Validate IANA timezone.

        Args:
            timezone: Timezone string

        Returns:
            True if valid IANA timezone
        """
        return timezone in VALID_TIMEZONES

    @staticmethod
    def validate_capability(capability: str) -> bool:
        """
        Validate capability name.

        Args:
            capability: Capability string

        Returns:
            True if valid capability
        """
        return capability in VALID_CAPABILITIES


def validate_intake(intake: dict[str, Any]) -> dict[str, Any]:
    """
    Validate intake data against schema.

    Args:
        intake: Intake dictionary

    Returns:
        Dictionary with:
        - valid: bool indicating if intake is valid
        - errors: list of error messages (if invalid)
        - normalized_organization_id: normalized org ID
        - warnings: list of warnings (optional)
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Required fields
    required_fields = [
        "organization_id",
        "business_name",
        "phone_number",
        "voice_id",
        "timezone",
        "business_hours",
        "services_offered",
        "enabled_capabilities",
        "external_identifiers",
    ]

    for field in required_fields:
        if field not in intake:
            errors.append(f"Missing required field: {field}")

    # If missing required fields, return early
    if errors:
        # Validate the identifier before returning structural errors so callers
        # receive a clear security-relevant rejection for unsafe values.
        org_id = intake.get("organization_id")
        if isinstance(org_id, str) and org_id:
            normalized_org_id = normalize_organization_id(org_id)
            if not validate_organization_id(normalized_org_id) or normalized_org_id != org_id:
                errors.append(f"Invalid organization_id: {org_id!r}")
        return {
            "valid": False,
            "errors": errors,
        }

    # Validate organization_id
    org_id = intake["organization_id"]
    if not isinstance(org_id, str) or not org_id:
        errors.append("organization_id must be a non-empty string")
    else:
        # Normalize organization ID
        normalized_org_id = normalize_organization_id(org_id)
        if not validate_organization_id(normalized_org_id):
            errors.append(f"organization_id '{org_id}' cannot be normalized to valid format")

    # Validate business_name
    if not intake.get("business_name") or not isinstance(intake["business_name"], str):
        errors.append("business_name must be a non-empty string")

    # Validate phone_number format
    phone = intake.get("phone_number", "")
    if not IntakeSchema.validate_phone_number(phone):
        errors.append(f"phone_number '{phone}' is not valid E.164 format (e.g., +15555550100)")

    # Validate voice_id
    if not intake.get("voice_id"):
        errors.append("voice_id must be provided")

    # Validate timezone
    timezone = intake.get("timezone", "")
    if not IntakeSchema.validate_timezone(timezone):
        errors.append(f"timezone '{timezone}' is not a valid IANA timezone")
        warnings.append(
            f"Valid timezones include: {', '.join(sorted(list(VALID_TIMEZONES)[:5]))}..."
        )

    # Validate business_hours structure
    business_hours = intake.get("business_hours", {})
    if not isinstance(business_hours, dict):
        errors.append("business_hours must be a dictionary")

    # Validate services_offered
    services = intake.get("services_offered", [])
    if not isinstance(services, list):
        errors.append("services_offered must be an array")

    # Validate enabled_capabilities
    capabilities = intake.get("enabled_capabilities", [])
    if not isinstance(capabilities, list):
        errors.append("enabled_capabilities must be an array")
    else:
        for cap in capabilities:
            if not IntakeSchema.validate_capability(cap):
                errors.append(f"Unknown capability: {cap}")

    # Validate capability-specific required fields
    if "booking" in capabilities and not intake.get("booking_calendar_id"):
        errors.append("booking_calendar_id is required when booking capability is enabled")

    if "cancellation" in capabilities:
        if "cancellation_window_hours" not in intake:
            errors.append(
                "cancellation_window_hours is required when cancellation capability is enabled"
            )
        elif intake.get("cancellation_window_hours") is not None:
            window = intake["cancellation_window_hours"]
            if not isinstance(window, int) or window < 0:
                errors.append("cancellation_window_hours must be a non-negative integer")

    if "rescheduling" in capabilities and not intake.get("rescheduling_policy"):
        errors.append("rescheduling_policy is required when rescheduling capability is enabled")

    if "human_transfer" in capabilities:
        if not intake.get("transfer_destination"):
            errors.append(
                "transfer_destination is required when human_transfer capability is enabled"
            )
        elif intake.get("transfer_destination"):
            # Validate transfer destination phone format
            transfer_phone = intake["transfer_destination"]
            if not IntakeSchema.validate_phone_number(transfer_phone):
                errors.append(f"transfer_destination '{transfer_phone}' is not valid E.164 format")

    # Validate external_identifiers
    ext_ids = intake.get("external_identifiers", {})
    if not isinstance(ext_ids, dict):
        errors.append("external_identifiers must be a dictionary")

    # Build result
    result: dict[str, Any] = {
        "valid": len(errors) == 0,
    }

    if errors:
        result["errors"] = errors

    if warnings:
        result["warnings"] = warnings

    # Add normalized organization ID if valid
    if "organization_id" in intake:
        result["normalized_organization_id"] = normalize_organization_id(intake["organization_id"])

    return result


def normalize_intake(intake: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize intake data.

    Applies normalization rules like organization_id lowercase,
    phone number formatting, etc.

    Args:
        intake: Raw intake dictionary

    Returns:
        Normalized intake dictionary
    """
    normalized = intake.copy()

    # Normalize organization_id
    if "organization_id" in normalized:
        normalized["organization_id"] = normalize_organization_id(normalized["organization_id"])

    # Trim whitespace from string fields
    string_fields = ["business_name", "voice_id", "timezone"]
    for field in string_fields:
        if field in normalized and isinstance(normalized[field], str):
            normalized[field] = normalized[field].strip()

    return normalized


class DeploymentIntent:
    """Deployment intent types."""

    NEW_ONBOARDING = "new_onboarding"
    UPDATE_ASSISTANT = "update_assistant"
    UPDATE_SCENARIO = "update_scenario"
    UPDATE_SCHEMA = "update_schema"
    UPDATE_BACKEND = "update_backend"
    STATUS_ONLY = "status_only"
    RECOVERY_ONLY = "recovery_only"


def validate_update_intake(
    update_intake: dict[str, Any],
    internal_store: SupabaseInternalClient,
) -> dict[str, Any]:
    """
    Validate update-intent intake.

    Implements T147: Update-intent intake (select existing org, modification
    type, collect changed fields only)

    Args:
        update_intake: Update intake dictionary
        internal_store: Internal store client for deployment lookup

    Returns:
        Validation result with deployment_id if valid
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Require organization_id
    organization_id = update_intake.get("organization_id")
    if not organization_id:
        errors.append("organization_id is required for updates")
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
        }

    # Lookup existing deployment
    existing_deployment = internal_store.get_latest_deployment(organization_id)
    if not existing_deployment:
        errors.append(f"No existing deployment found for organization: {organization_id}")
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
        }

    deployment_id = existing_deployment["id"]
    current_status = existing_deployment.get("status")

    # Validate intent
    intent = update_intake.get("intent")
    valid_intents = [
        DeploymentIntent.UPDATE_ASSISTANT,
        DeploymentIntent.UPDATE_SCENARIO,
        DeploymentIntent.UPDATE_SCHEMA,
        DeploymentIntent.UPDATE_BACKEND,
        DeploymentIntent.STATUS_ONLY,
        DeploymentIntent.RECOVERY_ONLY,
    ]

    if intent not in valid_intents:
        errors.append(
            f"Invalid intent for update: {intent}. Must be one of: {', '.join(valid_intents)}"
        )

    # Intent-specific validation
    if intent == DeploymentIntent.RECOVERY_ONLY:
        # Must be in recovery state
        if current_status not in ["partial", "recovery_required", "compensating"]:
            errors.append(
                f"recovery_only intent requires deployment in recovery state, current: {current_status}"
            )

    elif intent == DeploymentIntent.STATUS_ONLY:
        # No updates required
        pass

    else:
        # Other intents require updates field
        updates = update_intake.get("updates")
        if not updates:
            errors.append(f"Intent {intent} requires 'updates' field")
        else:
            # Validate intent-specific fields
            if intent == DeploymentIntent.UPDATE_ASSISTANT:
                assistant_fields = [
                    "assistant_name",
                    "model",
                    "voice",
                    "first_message",
                    "system_prompt",
                ]
                has_assistant_field = any(field in updates for field in assistant_fields)
                if not has_assistant_field:
                    errors.append(
                        "update_assistant intent requires at least one assistant field in updates"
                    )

            elif intent == DeploymentIntent.UPDATE_SCENARIO:
                scenario_fields = ["scenario_name", "schedule", "enabled"]
                has_scenario_field = any(field in updates for field in scenario_fields)
                if not has_scenario_field:
                    errors.append(
                        "update_scenario intent requires at least one scenario field in updates"
                    )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "deployment_id": deployment_id if len(errors) == 0 else None,
        "current_status": current_status,
    }


def detect_changes(
    current_state: dict[str, Any],
    updates: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """
    Detect changes between current state and updates.

    Implements T150: No-change detection (if requested state matches current
    state, report no change)

    Args:
        current_state: Current state dictionary
        updates: Proposed updates dictionary

    Returns:
        Dictionary of changes with 'from' and 'to' values
    """
    changes = {}

    for field, new_value in updates.items():
        current_value = current_state.get(field)

        if current_value != new_value:
            changes[field] = {
                "from": current_value,
                "to": new_value,
            }

    return changes
