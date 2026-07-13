"""
Integration test for internal Supabase store.

Tests create organization, insert intake, create deployment, and state transitions.

NOTE: This test requires a configured internal Supabase instance.
Run with: pytest tests/integration/test_internal_store.py -m integration
"""

import os
from datetime import datetime
from uuid import uuid4

import pytest

from adapters.supabase_internal import SupabaseInternalClient
from cli.config import AgentForgeConfig, load_config


@pytest.mark.integration
class TestInternalStore:
    """Integration tests for internal Supabase operational store."""

    @pytest.fixture
    def config(self) -> AgentForgeConfig:
        """Load configuration from environment."""
        if not os.getenv("SUPABASE_INTERNAL_URL"):
            pytest.skip("SUPABASE_INTERNAL_URL not configured")

        return load_config()

    @pytest.fixture
    def client(self, config: AgentForgeConfig) -> SupabaseInternalClient:
        """Create internal Supabase client."""
        return SupabaseInternalClient(config)

    def test_health_check(self, client: SupabaseInternalClient) -> None:
        """Should connect to internal Supabase."""
        assert client.health_check(), "Failed to connect to internal Supabase"

    def test_create_organization(self, client: SupabaseInternalClient) -> None:
        """Should create an organization."""
        org_id = f"test_org_{uuid4().hex[:8]}"

        try:
            org = client.insert(
                "organizations",
                {
                    "organization_id": org_id,
                    "display_name": "Test Organization",
                    "status": "active",
                },
            )

            assert org["organization_id"] == org_id
            assert org["display_name"] == "Test Organization"
            assert org["status"] == "active"

        finally:
            # Cleanup
            try:
                client.delete("organizations", {"organization_id": org_id})
            except Exception:
                pass

    def test_insert_intake(self, client: SupabaseInternalClient) -> None:
        """Should insert an organization intake."""
        org_id = f"test_org_{uuid4().hex[:8]}"

        try:
            # Create organization first
            client.insert(
                "organizations",
                {
                    "organization_id": org_id,
                    "display_name": "Test Organization",
                    "status": "active",
                },
            )

            # Insert intake
            intake = client.insert(
                "organization_intakes",
                {
                    "organization_id": org_id,
                    "version": 1,
                    "business_name": "Test Business",
                    "phone_number": "+15555550100",
                    "voice_id": "test_voice",
                    "timezone": "America/New_York",
                    "business_hours": {"monday": []},
                    "services_offered": [{"name": "Test Service"}],
                    "enabled_capabilities": ["availability"],
                    "external_identifiers": {},
                    "intake_hash": "test_hash_123",
                    "approved_by": "test_operator",
                    "approved_at": datetime.utcnow().isoformat(),
                },
            )

            assert intake["organization_id"] == org_id
            assert intake["version"] == 1
            assert intake["business_name"] == "Test Business"

        finally:
            # Cleanup
            try:
                client.delete("organization_intakes", {"organization_id": org_id})
                client.delete("organizations", {"organization_id": org_id})
            except Exception:
                pass

    def test_create_deployment(self, client: SupabaseInternalClient) -> None:
        """Should create a deployment."""
        org_id = f"test_org_{uuid4().hex[:8]}"

        try:
            # Create organization
            client.insert(
                "organizations",
                {
                    "organization_id": org_id,
                    "display_name": "Test Organization",
                    "status": "active",
                },
            )

            # Create intake
            intake = client.insert(
                "organization_intakes",
                {
                    "organization_id": org_id,
                    "version": 1,
                    "business_name": "Test Business",
                    "phone_number": "+15555550100",
                    "voice_id": "test_voice",
                    "timezone": "America/New_York",
                    "business_hours": {"monday": []},
                    "services_offered": [{"name": "Test Service"}],
                    "enabled_capabilities": ["availability"],
                    "external_identifiers": {},
                    "intake_hash": "test_hash_123",
                    "approved_by": "test_operator",
                    "approved_at": datetime.utcnow().isoformat(),
                },
            )

            # Create deployment
            deployment = client.insert(
                "deployments",
                {
                    "organization_id": org_id,
                    "intake_id": intake["intake_id"],
                    "intent": "new_onboarding",
                    "status": "planning",
                    "constitution_version": "1.0.0",
                    "spec_version": "1.0.0",
                    "started_by": "test_operator",
                },
            )

            assert deployment["organization_id"] == org_id
            assert deployment["intent"] == "new_onboarding"
            assert deployment["status"] == "planning"

        finally:
            # Cleanup
            try:
                client.delete("deployments", {"organization_id": org_id})
                client.delete("organization_intakes", {"organization_id": org_id})
                client.delete("organizations", {"organization_id": org_id})
            except Exception:
                pass

    def test_deployment_state_transitions(self, client: SupabaseInternalClient) -> None:
        """Should transition deployment through states."""
        org_id = f"test_org_{uuid4().hex[:8]}"

        try:
            # Create organization
            client.insert(
                "organizations",
                {
                    "organization_id": org_id,
                    "display_name": "Test Organization",
                    "status": "active",
                },
            )

            # Create intake
            intake = client.insert(
                "organization_intakes",
                {
                    "organization_id": org_id,
                    "version": 1,
                    "business_name": "Test Business",
                    "phone_number": "+15555550100",
                    "voice_id": "test_voice",
                    "timezone": "America/New_York",
                    "business_hours": {"monday": []},
                    "services_offered": [{"name": "Test Service"}],
                    "enabled_capabilities": ["availability"],
                    "external_identifiers": {},
                    "intake_hash": "test_hash_123",
                    "approved_by": "test_operator",
                    "approved_at": datetime.utcnow().isoformat(),
                },
            )

            # Create deployment
            deployment = client.insert(
                "deployments",
                {
                    "organization_id": org_id,
                    "intake_id": intake["intake_id"],
                    "intent": "new_onboarding",
                    "status": "planning",
                    "constitution_version": "1.0.0",
                    "spec_version": "1.0.0",
                    "started_by": "test_operator",
                },
            )

            deployment_id = deployment["deployment_id"]

            # Transition: planning -> awaiting_plan_approval
            updated = client.update(
                "deployments",
                {"deployment_id": deployment_id},
                {"status": "awaiting_plan_approval", "plan_hash": "plan_hash_123"},
            )

            assert len(updated) == 1
            assert updated[0]["status"] == "awaiting_plan_approval"

            # Transition: awaiting_plan_approval -> generating
            updated = client.update(
                "deployments",
                {"deployment_id": deployment_id},
                {"status": "generating"},
            )

            assert updated[0]["status"] == "generating"

            # Transition: generating -> awaiting_action_approval
            updated = client.update(
                "deployments",
                {"deployment_id": deployment_id},
                {"status": "awaiting_action_approval"},
            )

            assert updated[0]["status"] == "awaiting_action_approval"

            # Verify final state
            final_deployment = client.get_by_id(
                "deployments", "deployment_id", deployment_id
            )

            assert final_deployment is not None
            assert final_deployment["status"] == "awaiting_action_approval"

        finally:
            # Cleanup
            try:
                client.delete("deployments", {"organization_id": org_id})
                client.delete("organization_intakes", {"organization_id": org_id})
                client.delete("organizations", {"organization_id": org_id})
            except Exception:
                pass

    def test_query_deployments_by_organization(
        self, client: SupabaseInternalClient
    ) -> None:
        """Should query deployments for an organization."""
        org_id = f"test_org_{uuid4().hex[:8]}"

        try:
            # Create organization
            client.insert(
                "organizations",
                {
                    "organization_id": org_id,
                    "display_name": "Test Organization",
                    "status": "active",
                },
            )

            # Create intake
            intake = client.insert(
                "organization_intakes",
                {
                    "organization_id": org_id,
                    "version": 1,
                    "business_name": "Test Business",
                    "phone_number": "+15555550100",
                    "voice_id": "test_voice",
                    "timezone": "America/New_York",
                    "business_hours": {"monday": []},
                    "services_offered": [{"name": "Test Service"}],
                    "enabled_capabilities": ["availability"],
                    "external_identifiers": {},
                    "intake_hash": "test_hash_123",
                    "approved_by": "test_operator",
                    "approved_at": datetime.utcnow().isoformat(),
                },
            )

            # Create deployment
            client.insert(
                "deployments",
                {
                    "organization_id": org_id,
                    "intake_id": intake["intake_id"],
                    "intent": "new_onboarding",
                    "status": "planning",
                    "constitution_version": "1.0.0",
                    "spec_version": "1.0.0",
                    "started_by": "test_operator",
                },
            )

            # Query deployments
            deployments = client.select(
                "deployments",
                filters={"organization_id": org_id},
                order_by="created_at",
            )

            assert len(deployments) == 1
            assert deployments[0]["organization_id"] == org_id

        finally:
            # Cleanup
            try:
                client.delete("deployments", {"organization_id": org_id})
                client.delete("organization_intakes", {"organization_id": org_id})
                client.delete("organizations", {"organization_id": org_id})
            except Exception:
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
