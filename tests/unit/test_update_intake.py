"""
Unit tests for update-intent intake.

Tests T145: Update-intent intake (existing deployment lookup, change detection,
no-op detection)
"""

from unittest.mock import Mock

import pytest

from orchestrator.intake_schema import (
    detect_changes,
    validate_update_intake,
)


@pytest.mark.unit
class TestUpdateIntake:
    """Test update-intent intake processing."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.mock_store = Mock()

    def test_update_intent_requires_organization_id(self) -> None:
        """Test that update intake requires organization ID."""
        update_intake = {
            "intent": "update_assistant",
            # Missing organization_id
            "updates": {
                "assistant_name": "Updated Assistant",
            },
        }

        result = validate_update_intake(update_intake, self.mock_store)

        assert result["valid"] is False
        assert any("organization" in error.lower() for error in result["errors"])

    def test_update_intent_requires_existing_deployment(self) -> None:
        """Test that update intake requires existing deployment."""
        update_intake = {
            "organization_id": "org-001",
            "intent": "update_assistant",
            "updates": {
                "assistant_name": "Updated Assistant",
            },
        }

        # Mock: no existing deployment
        self.mock_store.get_latest_deployment.return_value = None

        result = validate_update_intake(update_intake, self.mock_store)

        assert result["valid"] is False
        assert any("no existing deployment" in error.lower() for error in result["errors"])

    def test_update_intent_validates_intent_type(self) -> None:
        """Test that update intent type is validated."""
        update_intake = {
            "organization_id": "org-001",
            "intent": "invalid_intent",  # Not a valid DeploymentIntent
            "updates": {},
        }

        # Mock: existing deployment
        self.mock_store.get_latest_deployment.return_value = {
            "id": "deploy-001",
            "organization_id": "org-001",
            "status": "complete",
        }

        result = validate_update_intake(update_intake, self.mock_store)

        assert result["valid"] is False
        assert any("intent" in error.lower() for error in result["errors"])

    def test_detect_changes_identifies_modified_fields(self) -> None:
        """Test that change detection identifies modified fields."""
        current_state = {
            "assistant_name": "Original Assistant",
            "model": "gpt-4",
            "voice": "alloy",
        }

        updates = {
            "assistant_name": "Updated Assistant",  # Changed
            "model": "gpt-4",  # Unchanged
            "voice": "nova",  # Changed
        }

        changes = detect_changes(current_state, updates)

        assert len(changes) == 2
        assert "assistant_name" in changes
        assert "voice" in changes
        assert changes["assistant_name"] == {
            "from": "Original Assistant",
            "to": "Updated Assistant",
        }
        assert changes["voice"] == {
            "from": "alloy",
            "to": "nova",
        }

    def test_detect_changes_handles_no_changes(self) -> None:
        """Test that no-op updates are detected."""
        current_state = {
            "assistant_name": "Assistant",
            "model": "gpt-4",
        }

        updates = {
            "assistant_name": "Assistant",
            "model": "gpt-4",
        }

        changes = detect_changes(current_state, updates)

        assert len(changes) == 0

    def test_detect_changes_handles_new_fields(self) -> None:
        """Test that new fields are detected as additions."""
        current_state = {
            "assistant_name": "Assistant",
        }

        updates = {
            "assistant_name": "Assistant",
            "first_message": "Hello!",  # New field
        }

        changes = detect_changes(current_state, updates)

        assert len(changes) == 1
        assert "first_message" in changes
        assert changes["first_message"] == {
            "from": None,
            "to": "Hello!",
        }

    def test_update_assistant_intent_requires_assistant_fields(self) -> None:
        """Test that update_assistant intent validates assistant fields."""
        update_intake = {
            "organization_id": "org-001",
            "intent": "update_assistant",
            "updates": {
                "scenario_name": "Booking",  # Wrong field for assistant intent
            },
        }

        self.mock_store.get_latest_deployment.return_value = {
            "id": "deploy-001",
            "organization_id": "org-001",
            "status": "complete",
        }

        result = validate_update_intake(update_intake, self.mock_store)

        # Should warn or fail about inappropriate field for intent
        assert result["valid"] is False or len(result.get("warnings", [])) > 0

    def test_update_scenario_intent_requires_scenario_fields(self) -> None:
        """Test that update_scenario intent validates scenario fields."""
        update_intake = {
            "organization_id": "org-001",
            "intent": "update_scenario",
            "updates": {
                "scenario_name": "Updated Booking",
                "schedule": "0 9 * * *",
            },
        }

        self.mock_store.get_latest_deployment.return_value = {
            "id": "deploy-001",
            "organization_id": "org-001",
            "status": "complete",
        }

        result = validate_update_intake(update_intake, self.mock_store)

        assert result["valid"] is True

    def test_status_only_intent_allows_no_updates(self) -> None:
        """Test that status_only intent doesn't require updates."""
        update_intake = {
            "organization_id": "org-001",
            "intent": "status_only",
            # No updates field
        }

        self.mock_store.get_latest_deployment.return_value = {
            "id": "deploy-001",
            "organization_id": "org-001",
            "status": "complete",
        }

        result = validate_update_intake(update_intake, self.mock_store)

        assert result["valid"] is True

    def test_recovery_only_intent_checks_recovery_state(self) -> None:
        """Test that recovery_only intent checks for recovery state."""
        update_intake = {
            "organization_id": "org-001",
            "intent": "recovery_only",
        }

        # Mock: deployment not in recovery state
        self.mock_store.get_latest_deployment.return_value = {
            "id": "deploy-001",
            "organization_id": "org-001",
            "status": "complete",  # Not in recovery
        }

        result = validate_update_intake(update_intake, self.mock_store)

        assert result["valid"] is False
        assert any("recovery" in error.lower() for error in result["errors"])

    def test_validate_update_intake_sets_deployment_id(self) -> None:
        """Test that validation sets the deployment_id from lookup."""
        update_intake = {
            "organization_id": "org-001",
            "intent": "update_assistant",
            "updates": {
                "assistant_name": "Updated",
            },
        }

        self.mock_store.get_latest_deployment.return_value = {
            "id": "deploy-001",
            "organization_id": "org-001",
            "status": "complete",
        }

        result = validate_update_intake(update_intake, self.mock_store)

        assert result["valid"] is True
        assert result["deployment_id"] == "deploy-001"
