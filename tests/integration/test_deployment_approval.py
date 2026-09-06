"""
Integration test for sequential deployment with per-action approval.

Tests the complete deployment flow:
- Multiple actions executed sequentially
- Each action requires separate approval
- Approved actions execute and persist receipts
- Rejected actions do not execute
- State transitions are correct
- Audit events are recorded
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from adapters.base import AdapterReceipt
from adapters.supabase_internal import SupabaseInternalClient
from orchestrator.approval import build_proposed_action
from orchestrator.orchestrator import Orchestrator
from shared.errors import ConflictError, ValidationError

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_internal_store() -> Any:
    """Mock internal store for testing."""
    store = MagicMock(spec=SupabaseInternalClient)

    # Mock deployment retrieval
    store.get_deployment.return_value = {
        "deployment_id": "dep_test123",
        "organization_id": "test_org",
        "intent": "onboard",
        "status": "in_progress",
    }

    # Mock methods that don't return values
    store.insert_receipt.return_value = None
    store.upsert_external_resource.return_value = None
    store.append_audit_event.return_value = None
    store.update_deployment_status.return_value = None
    store.insert_approval_decision.return_value = None

    return store


@pytest.fixture
def orchestrator(mock_internal_store) -> Any:
    """Create orchestrator with mocked internal store."""
    return Orchestrator(mock_internal_store)


@pytest.fixture
def five_proposed_actions() -> None:
    """Create 5 proposed actions for testing."""
    actions = [
        build_proposed_action(
            platform="vapi",
            operation="create_tool",
            target="availability_tool",
            payload={
                "type": "function",
                "function": {"name": "check_availability", "parameters": {}},
                "server": {"url": "https://api.example.com/tools"},
            },
            expected_outcome="Create availability checking tool",
        ),
        build_proposed_action(
            platform="vapi",
            operation="create_assistant",
            target="main_assistant",
            payload={
                "name": "Test Assistant",
                "model": {"provider": "openai", "model": "gpt-4", "messages": []},
                "voice": {"provider": "11labs", "voiceId": "voice_123"},
            },
            expected_outcome="Create voice assistant",
        ),
        build_proposed_action(
            platform="make",
            operation="create_scenario",
            target="booking_scenario",
            payload={
                "blueprint": {"flow": [], "name": "Booking Flow"},
                "scheduling": {"type": "indefinitely"},
            },
            expected_outcome="Create booking automation scenario",
        ),
        build_proposed_action(
            platform="supabase_client",
            operation="insert_org_record",
            target="test_org",
            payload={
                "organization_id": "test_org",
                "business_name": "Test Organization",
                "timezone": "America/New_York",
            },
            expected_outcome="Create organization record",
        ),
        build_proposed_action(
            platform="render",
            operation="set_env_variable",
            target="DATABASE_URL",
            payload={
                "key": "DATABASE_URL",
                "value": "postgres://localhost/testdb",
            },
            expected_outcome="Configure database connection",
        ),
    ]
    return actions


class TestSequentialDeploymentFlow:
    """Test sequential deployment with per-action approval."""

    def test_five_actions_all_approved(
        self, orchestrator: Any, mock_internal_store: Any, five_proposed_actions: None
    ) -> None:
        """Test deployment with 5 actions, all approved."""

        # Mock adapter responses
        with (
            patch("adapters.vapi.VapiAdapter") as MockVapi,
            patch("adapters.make.MakeAdapter") as MockMake,
            patch("adapters.supabase_client.SupabaseClientAdapter") as MockSupabase,
            patch("adapters.hosting.RenderAdapter") as MockRender,
            patch("cli.prompts.InteractivePrompts.approve_action") as mock_approve,
        ):
            # Setup mock adapters to return receipts
            vapi_adapter = MockVapi.return_value
            vapi_adapter.create_tool.return_value = AdapterReceipt(
                platform="vapi",
                operation="create_tool",
                remote_id="tool_123",
                status="success",
                response_data={"id": "tool_123"},
            )
            vapi_adapter.create_assistant.return_value = AdapterReceipt(
                platform="vapi",
                operation="create_assistant",
                remote_id="asst_123",
                status="success",
                response_data={"id": "asst_123"},
            )

            make_adapter = MockMake.return_value
            make_adapter.create_scenario.return_value = AdapterReceipt(
                platform="make",
                operation="create_scenario",
                remote_id="123",
                status="success",
                response_data={"scenario": {"id": 123}},
            )

            supabase_adapter = MockSupabase.return_value
            supabase_adapter.insert_org_record.return_value = AdapterReceipt(
                platform="supabase_client",
                operation="insert_org_record",
                remote_id="test_org",
                status="success",
                response_data={"organization_id": "test_org"},
            )

            render_adapter = MockRender.return_value
            render_adapter.set_env_variable.return_value = AdapterReceipt(
                platform="render",
                operation="set_env_variable",
                remote_id="DATABASE_URL",
                status="success",
                response_data={"key": "DATABASE_URL"},
            )

            # Mock user approving all actions
            mock_approve.return_value = "approved"

            # Mock _build_proposed_actions to return our test actions
            with patch.object(
                orchestrator, "_build_proposed_actions", return_value=five_proposed_actions
            ):
                result = orchestrator.execute_deployment(
                    deployment_id="dep_test123",
                    organization_id="test_org",
                    operator="test_operator",
                    dry_run=False,
                )

            # Verify result
            assert result["status"] == "completed"
            assert result["total_actions"] == 5
            assert result["completed_actions"] == 5

            # Verify approve_action was called 5 times
            assert mock_approve.call_count == 5

            # Verify receipts were persisted for all 5 actions
            assert mock_internal_store.insert_receipt.call_count == 5

            # Verify audit events were recorded
            assert (
                mock_internal_store.append_audit_event.call_count >= 6
            )  # 5 executions + 1 completion

            # Verify deployment was marked as completed
            mock_internal_store.update_deployment_status.assert_called_with(
                "dep_test123",
                "complete",
            )

    def test_third_action_rejected_abort(
        self, orchestrator: Any, mock_internal_store: Any, five_proposed_actions: None
    ) -> None:
        """Test deployment where third action is rejected with abort."""

        with (
            patch("adapters.vapi.VapiAdapter") as MockVapi,
            patch("adapters.make.MakeAdapter"),
            patch("cli.prompts.InteractivePrompts.approve_action") as mock_approve,
        ):
            # Setup mock adapters
            vapi_adapter = MockVapi.return_value
            vapi_adapter.create_tool.return_value = AdapterReceipt(
                platform="vapi",
                operation="create_tool",
                remote_id="tool_123",
                status="success",
                response_data={"id": "tool_123"},
            )
            vapi_adapter.create_assistant.return_value = AdapterReceipt(
                platform="vapi",
                operation="create_assistant",
                remote_id="asst_123",
                status="success",
                response_data={"id": "asst_123"},
            )

            # Mock user: approve first 2, reject third
            mock_approve.side_effect = ["approved", "approved", "rejected_abort"]

            # Mock _build_proposed_actions
            with patch.object(
                orchestrator, "_build_proposed_actions", return_value=five_proposed_actions
            ):
                result = orchestrator.execute_deployment(
                    deployment_id="dep_test123",
                    organization_id="test_org",
                    operator="test_operator",
                    dry_run=False,
                )

            # Verify result
            assert result["status"] == "aborted"
            assert result["completed_actions"] == 2

            # Verify only 2 receipts were persisted
            assert mock_internal_store.insert_receipt.call_count == 2

            # Verify deployment was marked as aborted
            mock_internal_store.update_deployment_status.assert_called_with(
                "dep_test123",
                "aborted",
            )

    def test_second_action_rejected_revise(
        self, orchestrator: Any, mock_internal_store: Any, five_proposed_actions: None
    ) -> None:
        """Test deployment where second action is rejected with revise."""

        with (
            patch("adapters.vapi.VapiAdapter") as MockVapi,
            patch("cli.prompts.InteractivePrompts.approve_action") as mock_approve,
            patch("cli.prompts.InteractivePrompts.get_revision_instruction") as mock_revision,
        ):
            # Setup mock adapter
            vapi_adapter = MockVapi.return_value
            vapi_adapter.create_tool.return_value = AdapterReceipt(
                platform="vapi",
                operation="create_tool",
                remote_id="tool_123",
                status="success",
                response_data={"id": "tool_123"},
            )

            # Mock user: approve first, reject second for revision
            mock_approve.side_effect = ["approved", "rejected_revise"]
            mock_revision.return_value = "Change the assistant model to GPT-4 Turbo"

            # Mock _build_proposed_actions
            with patch.object(
                orchestrator, "_build_proposed_actions", return_value=five_proposed_actions
            ):
                result = orchestrator.execute_deployment(
                    deployment_id="dep_test123",
                    organization_id="test_org",
                    operator="test_operator",
                    dry_run=False,
                )

            # Verify result
            assert result["status"] == "revision_required"
            assert result["completed_actions"] == 1
            assert "Change the assistant model to GPT-4 Turbo" in result["revision_notes"]

            # Verify only 1 receipt was persisted
            assert mock_internal_store.insert_receipt.call_count == 1


class TestApprovalDecisionPersistence:
    """Test that approval decisions are persisted correctly."""

    def test_approval_decisions_recorded(self, orchestrator: Any, mock_internal_store: Any) -> None:
        """Test that all approval decisions are persisted to internal store."""

        actions = [
            build_proposed_action(
                platform="vapi",
                operation="create_assistant",
                target="test",
                payload={"name": "Test"},
            )
        ]

        with (
            patch("adapters.vapi.VapiAdapter") as MockVapi,
            patch("cli.prompts.InteractivePrompts.approve_action") as mock_approve,
            patch.object(orchestrator, "_build_proposed_actions", return_value=actions),
        ):
            vapi_adapter = MockVapi.return_value
            vapi_adapter.create_assistant.return_value = AdapterReceipt(
                platform="vapi",
                operation="create_assistant",
                remote_id="asst_123",
                status="success",
                response_data={"id": "asst_123"},
            )

            mock_approve.return_value = "approved"

            orchestrator.execute_deployment(
                deployment_id="dep_test123",
                organization_id="test_org",
                operator="test_operator",
                dry_run=False,
            )

            # Verify approval decision was persisted
            assert mock_internal_store.insert_approval_decision.call_count == 1
            call_args = mock_internal_store.insert_approval_decision.call_args
            assert call_args[1]["deployment_id"] == "dep_test123"
            assert call_args[1]["decision"] == "approved"
            assert call_args[1]["decided_by"] == "test_operator"


class TestReceiptPersistence:
    """Test that receipts are persisted before next action."""

    def test_receipt_persisted_before_next_action(
        self, orchestrator: Any, mock_internal_store: Any
    ) -> None:
        """Test that each receipt is persisted before executing next action."""

        actions = [
            build_proposed_action(
                platform="vapi",
                operation="create_tool",
                target="tool_1",
                payload={
                    "type": "function",
                    "function": {},
                    "server": {"url": "https://example.com"},
                },
            ),
            build_proposed_action(
                platform="vapi",
                operation="create_assistant",
                target="asst_1",
                payload={"name": "Test", "model": {}, "voice": {}},
            ),
        ]

        with (
            patch("adapters.vapi.VapiAdapter") as MockVapi,
            patch("cli.prompts.InteractivePrompts.approve_action") as mock_approve,
            patch.object(orchestrator, "_build_proposed_actions", return_value=actions),
        ):
            vapi_adapter = MockVapi.return_value

            # Track call order
            call_order = []

            def track_create_tool(*args, **kwargs):
                call_order.append("create_tool")
                return AdapterReceipt(
                    platform="vapi",
                    operation="create_tool",
                    remote_id="tool_123",
                    status="success",
                    response_data={"id": "tool_123"},
                )

            def track_create_assistant(*args, **kwargs):
                call_order.append("create_assistant")
                return AdapterReceipt(
                    platform="vapi",
                    operation="create_assistant",
                    remote_id="asst_123",
                    status="success",
                    response_data={"id": "asst_123"},
                )

            def track_insert_receipt(*args, **kwargs):
                call_order.append("insert_receipt")

            vapi_adapter.create_tool.side_effect = track_create_tool
            vapi_adapter.create_assistant.side_effect = track_create_assistant
            mock_internal_store.insert_receipt.side_effect = track_insert_receipt

            mock_approve.return_value = "approved"

            orchestrator.execute_deployment(
                deployment_id="dep_test123",
                organization_id="test_org",
                operator="test_operator",
                dry_run=False,
            )

            # Verify execution order: action1, persist1, action2, persist2
            assert call_order.index("create_tool") < call_order.index("insert_receipt")
            first_receipt_idx = call_order.index("insert_receipt")
            # Find second insert_receipt
            second_receipt_idx = call_order.index("insert_receipt", first_receipt_idx + 1)
            assert call_order.index("create_assistant") < second_receipt_idx


class TestAuditEventRecording:
    """Test that audit events are recorded for all state changes."""

    def test_audit_events_for_successful_deployment(
        self, orchestrator: Any, mock_internal_store: Any
    ) -> None:
        """Test that audit events are recorded throughout deployment."""

        actions = [
            build_proposed_action(
                platform="vapi",
                operation="create_assistant",
                target="test",
                payload={"name": "Test", "model": {}, "voice": {}},
            )
        ]

        with (
            patch("adapters.vapi.VapiAdapter") as MockVapi,
            patch("cli.prompts.InteractivePrompts.approve_action") as mock_approve,
            patch.object(orchestrator, "_build_proposed_actions", return_value=actions),
        ):
            vapi_adapter = MockVapi.return_value
            vapi_adapter.create_assistant.return_value = AdapterReceipt(
                platform="vapi",
                operation="create_assistant",
                remote_id="asst_123",
                status="success",
                response_data={"id": "asst_123"},
            )

            mock_approve.return_value = "approved"

            orchestrator.execute_deployment(
                deployment_id="dep_test123",
                organization_id="test_org",
                operator="test_operator",
                dry_run=False,
            )

            # Verify audit events were recorded
            assert mock_internal_store.append_audit_event.call_count >= 2

            # Check event types
            event_calls = mock_internal_store.append_audit_event.call_args_list
            event_types = [call[1]["event_type"] for call in event_calls]

            assert "action_executed" in event_types
            assert "deployment_completed" in event_types


class TestDryRunMode:
    """Test dry-run mode doesn't execute actions."""

    def test_dry_run_no_execution(self, orchestrator: Any, mock_internal_store: Any) -> None:
        """Test that dry-run mode previews actions without executing."""

        actions = [
            build_proposed_action(
                platform="vapi",
                operation="create_assistant",
                target="test",
                payload={"name": "Test"},
            )
        ]

        with (
            patch("adapters.vapi.VapiAdapter") as MockVapi,
            patch.object(orchestrator, "_build_proposed_actions", return_value=actions),
        ):
            result = orchestrator.execute_deployment(
                deployment_id="dep_test123",
                organization_id="test_org",
                operator="test_operator",
                dry_run=True,
            )

            # Verify dry-run status
            assert result["status"] == "dry_run"
            assert result["total_actions"] == 1

            # Verify no adapters were instantiated
            MockVapi.assert_not_called()

            # Verify no receipts were persisted
            assert mock_internal_store.insert_receipt.call_count == 0


class TestOrganizationMismatch:
    """Test that deployment organization validation works."""

    def test_organization_mismatch_rejected(
        self, orchestrator: Any, mock_internal_store: Any
    ) -> None:
        """Test that organization mismatch is detected and rejected."""

        # Mock deployment with different organization
        mock_internal_store.get_deployment.return_value = {
            "deployment_id": "dep_test123",
            "organization_id": "different_org",
            "intent": "onboard",
            "status": "in_progress",
        }

        with pytest.raises(ConflictError) as exc_info:
            orchestrator.execute_deployment(
                deployment_id="dep_test123",
                organization_id="test_org",  # Different from deployment
                operator="test_operator",
                dry_run=False,
            )

        assert "organization_id" in str(exc_info.value).lower()


class TestDeploymentNotFound:
    """Test handling of non-existent deployments."""

    def test_deployment_not_found(self, orchestrator: Any, mock_internal_store: Any) -> None:
        """Test that non-existent deployment is handled."""

        mock_internal_store.get_deployment.return_value = None

        with pytest.raises(ValidationError) as exc_info:
            orchestrator.execute_deployment(
                deployment_id="dep_nonexistent",
                organization_id="test_org",
                operator="test_operator",
                dry_run=False,
            )

        assert "not found" in str(exc_info.value).lower()
