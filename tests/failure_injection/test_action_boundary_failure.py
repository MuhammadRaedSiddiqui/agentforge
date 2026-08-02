"""
Failure injection test: Failure at each action boundary.

Tests T107: Verify correct partial state is recorded when failure occurs
at each possible action boundary in the deployment sequence.
"""

from unittest.mock import Mock, patch

import pytest

from orchestrator.orchestrator import Orchestrator
from orchestrator.state_machine import DeploymentState
from shared.errors import (
    PermanentError,
    TransientError,
)


@pytest.mark.failure_injection
class TestActionBoundaryFailure:
    """
    Test failures at each action boundary in deployment sequence.

    Verifies that partial state is correctly recorded and subsequent
    actions are not attempted.
    """

    def test_failure_after_first_action(self) -> None:
        """
        Test: First action succeeds, second fails.

        Expected:
        1. First action completes and receipt recorded
        2. Second action fails
        3. Deployment marked as partial/recovery_required
        4. Third action never attempted
        5. Completed work is preserved
        """
        internal_store = Mock()

        # Mock deployment with 3 actions
        internal_store.get_deployment.return_value = {
            "deployment_id": "dep_001",
            "organization_id": "test_org",
            "status": "executing",
            "plan": {
                "actions": [
                    {"platform": "vapi", "operation": "create_assistant"},
                    {"platform": "vapi", "operation": "create_tool"},
                    {"platform": "vapi", "operation": "assign_phone_number"},
                ]
            },
        }

        # Track state updates
        state_updates = []
        internal_store.update_deployment_status.side_effect = (
            lambda dep_id, status: state_updates.append(status)
        )

        # Track completed receipts
        receipts = []
        internal_store.insert_receipt.side_effect = lambda **kwargs: receipts.append(kwargs)

        orchestrator = Orchestrator(internal_store)

        # Mock adapters
        with patch("adapters.vapi.VapiAdapter") as MockVapi:
            vapi = MockVapi.return_value

            # First action succeeds
            vapi.create_assistant.return_value = Mock(
                remote_id="asst_123",
                status="success",
                response_data={"id": "asst_123"},
            )

            # Second action fails
            vapi.create_tool.side_effect = TransientError("Service unavailable")

            # Third action should not be called
            vapi.assign_phone_number.return_value = Mock()

            # Build minimal proposed actions
            proposed_actions = [
                Mock(
                    platform="vapi",
                    operation="create_assistant",
                    target={"name": "Test"},
                    payload={"name": "Test"},
                    proposal_hash="hash1",
                    payload_hash="payload_hash_1",
                    expected_outcome="Create assistant",
                    validation_result={"passed": True},
                    reconciliation_strategy="list_and_match",
                    compensation_operation="delete_assistant",
                    state_version=None,
                ),
                Mock(
                    platform="vapi",
                    operation="create_tool",
                    target={"name": "Tool"},
                    payload={"name": "Tool"},
                    proposal_hash="hash2",
                    payload_hash="payload_hash_2",
                    expected_outcome="Create tool",
                    validation_result={"passed": True},
                    reconciliation_strategy="list_and_match",
                    compensation_operation="delete_tool",
                    state_version=None,
                ),
                Mock(
                    platform="vapi",
                    operation="assign_phone_number",
                    target={"phone": "+15555550199"},
                    payload={"phone_number_id": "ph_123"},
                    proposal_hash="hash3",
                    payload_hash="payload_hash_3",
                    expected_outcome="Assign phone",
                    validation_result={"passed": True},
                    reconciliation_strategy="read_and_verify",
                    compensation_operation="unassign_phone_number",
                    state_version=None,
                ),
            ]

            orchestrator._build_proposed_actions = Mock(return_value=proposed_actions)

            # Mock approval prompts - all approved
            orchestrator.prompts.approve_action = Mock(return_value="approved")

            # Execute deployment
            with pytest.raises(TransientError):
                orchestrator.execute_deployment(
                    deployment_id="dep_001",
                    organization_id="test_org",
                    operator="test_operator",
                    dry_run=False,
                )

            # Verify first action completed
            assert len(receipts) == 1
            assert receipts[0]["platform"] == "vapi"
            assert receipts[0]["operation"] == "create_assistant"
            assert receipts[0]["remote_id"] == "asst_123"

            # Verify deployment marked for recovery
            assert DeploymentState.RECOVERY_REQUIRED.value in state_updates

            # Verify third action never attempted
            vapi.assign_phone_number.assert_not_called()

    def test_failure_before_any_action(self) -> None:
        """
        Test: Failure during planning/validation before any action executes.

        Expected:
        1. No receipts recorded
        2. No external resources created
        3. Deployment marked as failed (not recovery_required)
        4. Safe to retry entire deployment
        """
        internal_store = Mock()

        internal_store.get_deployment.side_effect = PermanentError("Deployment plan corrupted")

        orchestrator = Orchestrator(internal_store)

        with pytest.raises(PermanentError):
            orchestrator.execute_deployment(
                deployment_id="dep_001",
                organization_id="test_org",
                operator="test_operator",
            )

        # Verify no receipts
        internal_store.insert_receipt.assert_not_called()

        # Verify no resource upserts
        internal_store.upsert_external_resource.assert_not_called()

    def test_failure_after_all_but_last_action(self) -> None:
        """
        Test: Last action in sequence fails.

        Expected:
        1. All previous actions complete successfully
        2. Receipts recorded for each
        3. Last action fails
        4. Deployment marked for recovery
        5. Retry can complete just the last action
        """
        internal_store = Mock()

        internal_store.get_deployment.return_value = {
            "deployment_id": "dep_002",
            "organization_id": "test_org",
            "status": "executing",
        }

        receipts = []
        internal_store.insert_receipt.side_effect = lambda **kwargs: receipts.append(kwargs)

        orchestrator = Orchestrator(internal_store)

        # Mock two successful actions, one failure
        with patch("adapters.vapi.VapiAdapter") as MockVapi:
            vapi = MockVapi.return_value

            vapi.create_assistant.return_value = Mock(
                remote_id="asst_456",
                status="success",
                response_data={"id": "asst_456"},
            )

            vapi.create_tool.return_value = Mock(
                remote_id="tool_789",
                status="success",
                response_data={"id": "tool_789"},
            )

            # Last action fails
            vapi.assign_phone_number.side_effect = PermanentError("Phone number already assigned")

            proposed_actions = [
                Mock(
                    platform="vapi",
                    operation="create_assistant",
                    target={},
                    payload={},
                    proposal_hash="hash1",
                    payload_hash="payload_hash_1",
                    expected_outcome="",
                    validation_result={"passed": True},
                    reconciliation_strategy="list_and_match",
                    compensation_operation=None,
                    state_version=None,
                ),
                Mock(
                    platform="vapi",
                    operation="create_tool",
                    target={},
                    payload={},
                    proposal_hash="hash2",
                    payload_hash="payload_hash_2",
                    expected_outcome="",
                    validation_result={"passed": True},
                    reconciliation_strategy="list_and_match",
                    compensation_operation=None,
                    state_version=None,
                ),
                Mock(
                    platform="vapi",
                    operation="assign_phone_number",
                    target={},
                    payload={"phone_number_id": "ph_123", "assistant_id": "asst_456"},
                    proposal_hash="hash3",
                    payload_hash="payload_hash_3",
                    expected_outcome="",
                    validation_result={"passed": True},
                    reconciliation_strategy="read_and_verify",
                    compensation_operation=None,
                    state_version=None,
                ),
            ]

            orchestrator._build_proposed_actions = Mock(return_value=proposed_actions)
            orchestrator.prompts.approve_action = Mock(return_value="approved")

            with pytest.raises(PermanentError):
                orchestrator.execute_deployment(
                    deployment_id="dep_002",
                    organization_id="test_org",
                    operator="test_operator",
                    dry_run=False,
                )

            # Verify first two actions completed
            assert len(receipts) == 2
            assert receipts[0]["remote_id"] == "asst_456"
            assert receipts[1]["remote_id"] == "tool_789"

    def test_mixed_platform_failure_boundary(self) -> None:
        """
        Test: Multi-platform deployment with failure mid-sequence.

        Expected:
        1. Vapi action succeeds
        2. Make action succeeds
        3. Supabase action fails
        4. Render action never attempted
        5. Each platform's completed work preserved
        """
        internal_store = Mock()

        internal_store.get_deployment.return_value = {
            "deployment_id": "dep_003",
            "organization_id": "multi_org",
            "status": "executing",
        }

        receipts = []
        internal_store.insert_receipt.side_effect = lambda **kwargs: receipts.append(kwargs)

        orchestrator = Orchestrator(internal_store)

        with (
            patch("adapters.vapi.VapiAdapter") as MockVapi,
            patch("adapters.make.MakeAdapter") as MockMake,
            patch("adapters.supabase_client.SupabaseClientAdapter") as MockSupabase,
            patch("adapters.hosting.RenderAdapter") as MockRender,
        ):
            vapi = MockVapi.return_value
            make = MockMake.return_value
            supabase = MockSupabase.return_value
            render = MockRender.return_value

            # Success, success, failure, not-called
            vapi.create_assistant.return_value = Mock(
                remote_id="asst_111",
                status="success",
                response_data={"id": "asst_111"},
            )

            make.create_scenario.return_value = Mock(
                remote_id="scen_222",
                status="success",
                response_data={"id": "scen_222"},
            )

            supabase.insert_org_record.side_effect = TransientError("Database connection timeout")

            render.trigger_deploy.return_value = Mock()

            proposed_actions = [
                Mock(
                    platform="vapi",
                    operation="create_assistant",
                    target={},
                    payload={},
                    proposal_hash="h1",
                    payload_hash="payload_hash_h1",
                    expected_outcome="",
                    validation_result={"passed": True},
                    reconciliation_strategy="list",
                    compensation_operation=None,
                    state_version=None,
                ),
                Mock(
                    platform="make",
                    operation="create_scenario",
                    target={},
                    payload={
                        "blueprint": {},
                        "scheduling": {},
                    },
                    proposal_hash="h2",
                    payload_hash="payload_hash_h2",
                    expected_outcome="",
                    validation_result={"passed": True},
                    reconciliation_strategy="list",
                    compensation_operation=None,
                    state_version=None,
                ),
                Mock(
                    platform="supabase_client",
                    operation="insert_org_record",
                    target={},
                    payload={
                        "organization_id": "multi_org",
                        "business_name": "Multi Org",
                    },
                    proposal_hash="h3",
                    payload_hash="payload_hash_h3",
                    expected_outcome="",
                    validation_result={"passed": True},
                    reconciliation_strategy="read",
                    compensation_operation=None,
                    state_version=None,
                ),
                Mock(
                    platform="render",
                    operation="trigger_deploy",
                    target={},
                    payload={},
                    proposal_hash="h4",
                    payload_hash="payload_hash_h4",
                    expected_outcome="",
                    validation_result={"passed": True},
                    reconciliation_strategy="read",
                    compensation_operation=None,
                    state_version=None,
                ),
            ]

            orchestrator._build_proposed_actions = Mock(return_value=proposed_actions)
            orchestrator.prompts.approve_action = Mock(return_value="approved")

            with pytest.raises(TransientError):
                orchestrator.execute_deployment(
                    deployment_id="dep_003",
                    organization_id="multi_org",
                    operator="test_operator",
                    dry_run=False,
                )

            # Verify two platforms completed
            assert len(receipts) == 2
            assert receipts[0]["platform"] == "vapi"
            assert receipts[1]["platform"] == "make"

            # Verify render never called
            render.trigger_deploy.assert_not_called()
