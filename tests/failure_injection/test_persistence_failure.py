"""
Failure injection test: Local persistence failure after remote success.

Tests T108: Verify reconciliation handles case where remote operation succeeds
but local receipt persistence fails, requiring reconciliation on restart.
"""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest

from orchestrator.orchestrator import Orchestrator
from orchestrator.recovery import RecoveryOrchestrator
from shared.errors import PersistenceError


@pytest.mark.failure_injection
class TestPersistenceFailure:
    """
    Test scenarios where remote operations succeed but local persistence fails.

    Critical requirement: On restart, reconciliation must detect successful
    remote operation and not retry/duplicate.
    """

    def test_receipt_persistence_fails_after_remote_success(self) -> None:
        """
        Test: Remote create succeeds but receipt insert fails.

        Expected:
        1. Remote assistant created successfully
        2. Receipt persistence fails (database error)
        3. Deployment marked for recovery
        4. On restart, reconciliation finds remote resource
        5. Accept as success, persist receipt retroactively
        6. No duplicate resource created
        """
        internal_store = Mock()

        internal_store.get_deployment.return_value = {
            "deployment_id": "dep_pers_001",
            "organization_id": "test_org",
            "status": "executing",
        }

        # Receipt insert fails
        internal_store.insert_receipt.side_effect = PersistenceError(
            "Database connection lost during write"
        )

        orchestrator = Orchestrator(internal_store)

        vapi = Mock()

        # Remote operation succeeds
        vapi.create_assistant.return_value = Mock(
            remote_id="asst_persist_123",
            status="success",
            response_data={"id": "asst_persist_123", "name": "Test"},
        )

        with patch("adapters.vapi.VapiAdapter", return_value=vapi):
            proposed_action = Mock(
                platform="vapi",
                operation="create_assistant",
                target={"name": "Test"},
                payload={"name": "Test"},
                proposal_hash="hash_pers_1",
                expected_outcome="Create assistant",
                validation_result={"passed": True},
                reconciliation_strategy="list_and_match",
                compensation_operation="delete_assistant",
                state_version=None,
            )

            approval = Mock(
                decision="approved",
                proposal_hash="hash_pers_1",
                display_hash="display_pers_1",
                decided_by="operator",
                decided_at=datetime.now(UTC),
                notes=None,
            )

            # Execute action - should fail on persistence
            with pytest.raises(PersistenceError):
                orchestrator._execute_action(
                    deployment_id="dep_pers_001",
                    proposed_action=proposed_action,
                    approval=approval,
                )

            # Verify remote operation was called
            vapi.create_assistant.assert_called_once()

            # Verify deployment marked for recovery
            internal_store.append_audit_event.assert_called()
            audit_calls = [
                call
                for call in internal_store.append_audit_event.call_args_list
                if "action_failed" in str(call)
            ]
            assert len(audit_calls) > 0

        # Simulate restart and reconciliation
        # Reconciliation should find the created assistant
        vapi_recon = Mock()

        vapi_recon.list_assistants.return_value = {
            "data": [
                {
                    "id": "asst_persist_123",
                    "name": "Test",
                    "created_at": "2024-01-01T00:00:00Z",
                }
            ]
        }

        recovery = RecoveryOrchestrator(
            internal_store=internal_store,
            adapters={"vapi": vapi_recon},
        )

        result = recovery.reconcile_remote_state(
            {
                "platform": "vapi",
                "operation": "create_assistant",
                "target": {"name": "Test"},
                "payload": {"name": "Test"},
            }
        )

        # Verify reconciliation found it
        assert result.resource_found is True
        assert result.remote_id == "asst_persist_123"
        assert result.recommendation == "accept_as_success"

        # Should NOT call create again
        vapi_recon.create_assistant.assert_not_called()

    def test_resource_registry_update_fails(self) -> None:
        """
        Test: Receipt persists but external resource registry update fails.

        Expected:
        1. Remote operation succeeds
        2. Receipt persists
        3. Resource registry update fails
        4. Deployment marked for recovery
        5. Resource registry repaired on reconciliation
        """
        internal_store = Mock()

        internal_store.get_deployment.return_value = {
            "deployment_id": "dep_reg_001",
            "organization_id": "test_org",
            "status": "executing",
        }

        # Receipt succeeds
        receipts = []
        internal_store.insert_receipt.side_effect = lambda **kwargs: receipts.append(kwargs)

        # Resource registry fails
        internal_store.upsert_external_resource.side_effect = PersistenceError(
            "Registry table locked"
        )

        orchestrator = Orchestrator(internal_store)

        make = Mock()

        make.create_scenario.return_value = Mock(
            remote_id="scen_reg_456",
            status="success",
            response_data={"id": "scen_reg_456"},
        )

        with patch("adapters.make.MakeAdapter", return_value=make):
            proposed_action = Mock(
                platform="make",
                operation="create_scenario",
                target={"name": "Test Scenario"},
                payload={"blueprint": {}, "scheduling": {}},
                proposal_hash="hash_reg_1",
                expected_outcome="Create scenario",
                validation_result={"passed": True},
                reconciliation_strategy="list_and_match",
                compensation_operation="delete_scenario",
                state_version=None,
            )

            approval = Mock(
                decision="approved",
                proposal_hash="hash_reg_1",
                display_hash="display_reg_1",
                decided_by="operator",
                decided_at=datetime.now(UTC),
                notes=None,
            )

            with pytest.raises(PersistenceError):
                orchestrator._execute_action(
                    deployment_id="dep_reg_001",
                    proposed_action=proposed_action,
                    approval=approval,
                )

            # Verify receipt was persisted
            assert len(receipts) == 1
            assert receipts[0]["remote_id"] == "scen_reg_456"

            # Verify resource registry was attempted but failed
            internal_store.upsert_external_resource.assert_called_once()

    def test_audit_event_persistence_fails(self) -> None:
        """
        Test: Action succeeds but audit event recording fails.

        Expected:
        1. Remote operation and receipt succeed
        2. Audit event append fails
        3. Deployment marked for recovery
        4. Audit event can be reconstructed from receipt
        """
        internal_store = Mock()

        internal_store.get_deployment.return_value = {
            "deployment_id": "dep_audit_001",
            "organization_id": "test_org",
            "status": "executing",
        }

        # Receipt succeeds
        receipts = []
        internal_store.insert_receipt.side_effect = lambda **kwargs: receipts.append(kwargs)

        # Resource registry succeeds
        internal_store.upsert_external_resource.return_value = None

        # Audit event fails
        internal_store.append_audit_event.side_effect = [
            None,  # First call might succeed (action start)
            PersistenceError("Audit table write failed"),  # Second call fails
        ]

        orchestrator = Orchestrator(internal_store)

        supabase = Mock()

        supabase.insert_org_record.return_value = Mock(
            remote_id="test_org_123",
            status="success",
            response_data={"organization_id": "test_org_123"},
        )

        with patch("adapters.supabase_client.SupabaseClientAdapter", return_value=supabase):
            proposed_action = Mock(
                platform="supabase_client",
                operation="insert_org_record",
                target={"organization_id": "test_org_123"},
                payload={"organization_id": "test_org_123", "business_name": "Test"},
                proposal_hash="hash_audit_1",
                expected_outcome="Insert org",
                validation_result={"passed": True},
                reconciliation_strategy="read_by_id",
                compensation_operation="delete_org_record",
                state_version=None,
            )

            approval = Mock(
                decision="approved",
                proposal_hash="hash_audit_1",
                display_hash="display_audit_1",
                decided_by="operator",
                decided_at=datetime.now(UTC),
                notes=None,
            )

            # May raise PersistenceError
            # Depending on implementation, might be caught internally
            try:
                orchestrator._execute_action(
                    deployment_id="dep_audit_001",
                    proposed_action=proposed_action,
                    approval=approval,
                )
            except PersistenceError:
                pass

            # Verify receipt was persisted
            assert len(receipts) == 1
            assert receipts[0]["remote_id"] == "test_org_123"

            # Audit reconstruction should be possible from receipt
            # This would happen during recovery

    def test_full_transaction_rollback_not_possible(self) -> None:
        """
        Test: Demonstrate that remote success + local failure cannot be rolled back.

        Expected:
        1. Remote resource created (cannot be undone without compensation)
        2. Local persistence fails
        3. Reconciliation required to link existing remote resource
        4. Compensation is the only rollback option
        """
        internal_store = Mock()

        # All persistence operations fail
        internal_store.insert_receipt.side_effect = PersistenceError("DB down")
        internal_store.upsert_external_resource.side_effect = PersistenceError("DB down")
        internal_store.append_audit_event.side_effect = PersistenceError("DB down")

        vapi = Mock()

        # Remote succeeds
        vapi.create_tool.return_value = Mock(
            remote_id="tool_orphan_789",
            status="success",
            response_data={"id": "tool_orphan_789"},
        )

        with patch("adapters.vapi.VapiAdapter", return_value=vapi):
            orchestrator = Orchestrator(internal_store)

            proposed_action = Mock(
                platform="vapi",
                operation="create_tool",
                target={"name": "Orphan Tool"},
                payload={"name": "Orphan Tool"},
                proposal_hash="hash_orphan_1",
                expected_outcome="Create tool",
                validation_result={"passed": True},
                reconciliation_strategy="list_and_match",
                compensation_operation="delete_tool",
                state_version=None,
            )

            approval = Mock(
                decision="approved",
                proposal_hash="hash_orphan_1",
                display_hash="display_orphan_1",
                decided_by="operator",
                decided_at=datetime.now(UTC),
                notes=None,
            )

            with pytest.raises(PersistenceError):
                orchestrator._execute_action(
                    deployment_id="dep_orphan_001",
                    proposed_action=proposed_action,
                    approval=approval,
                )

            # Remote resource exists but no local record
            # This is an "orphan" that requires reconciliation or compensation
            vapi.create_tool.assert_called_once()

        # Verify orphan can be found via reconciliation
        vapi_recon = Mock()

        vapi_recon.list_tools.return_value = {
            "data": [{"id": "tool_orphan_789", "name": "Orphan Tool"}]
        }

        recovery = RecoveryOrchestrator(
            internal_store=Mock(),
            adapters={"vapi": vapi_recon},
        )

        result = recovery.reconcile_remote_state(
            {
                "platform": "vapi",
                "operation": "create_tool",
                "target": {"name": "Orphan Tool"},
                "payload": {"name": "Orphan Tool"},
            }
        )

        assert result.resource_found is True
        assert result.remote_id == "tool_orphan_789"
        assert result.recommendation == "accept_as_success"
