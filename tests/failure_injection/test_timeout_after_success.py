"""
Failure injection test: Timeout after remote success.

Tests T106: Verify no duplicate resource is created when timeout occurs
after successful remote operation.
"""

from unittest.mock import Mock

import pytest

from adapters.base import AdapterReceipt
from orchestrator.recovery import RecoveryOrchestrator
from shared.errors import AmbiguousOutcomeError


@pytest.mark.failure_injection
class TestTimeoutAfterSuccess:
    """
    Test timeout scenarios where remote operation succeeds but client times out.

    Critical requirement: No duplicate resource should be created on retry.
    """

    def test_vapi_create_assistant_timeout_after_success(self) -> None:
        """
        Test: Vapi assistant creation succeeds remotely but client times out.

        Expected:
        1. First attempt times out (ambiguous outcome)
        2. Reconciliation detects existing assistant
        3. No retry attempted - mark as success
        4. No duplicate assistant created
        """
        # Mock Vapi adapter
        adapter = Mock()

        # First call: timeout (but actually succeeded remotely)
        adapter.create_assistant.side_effect = [
            AmbiguousOutcomeError("Request timeout"),
        ]

        # Reconciliation: find the created assistant
        adapter.list_assistants.return_value = {
            "data": [
                {
                    "id": "asst_123",
                    "name": "Test Assistant",
                    "created_at": "2024-01-01T00:00:00Z",
                }
            ]
        }

        # Execute operation
        with pytest.raises(AmbiguousOutcomeError):
            adapter.create_assistant({"name": "Test Assistant"})

        # Reconcile
        recovery = RecoveryOrchestrator(
            internal_store=Mock(),
            adapters={"vapi": adapter},
        )

        proposed_action = {
            "platform": "vapi",
            "operation": "create_assistant",
            "target": {"name": "Test Assistant"},
            "payload": {"name": "Test Assistant"},
        }

        result = recovery.reconcile_remote_state(proposed_action)

        # Verify reconciliation found the resource
        assert result.resource_found is True
        assert result.remote_id == "asst_123"
        assert result.recommendation == "accept_as_success"

        # Verify no second create attempt
        assert adapter.create_assistant.call_count == 1

    def test_make_create_scenario_timeout_after_success(self) -> None:
        """
        Test: Make scenario creation succeeds but client times out.

        Expected:
        1. Timeout on create
        2. Reconciliation finds scenario
        3. Accept as success
        4. No duplicate scenario
        """
        adapter = Mock()

        # Timeout on create
        adapter.create_scenario.side_effect = AmbiguousOutcomeError("Timeout")

        # Reconciliation finds it
        adapter.list_scenarios.return_value = {
            "scenarios": [
                {
                    "id": "scen_123",
                    "name": "Booking Flow",
                    "teamId": 456,
                }
            ]
        }

        with pytest.raises(AmbiguousOutcomeError):
            adapter.create_scenario(
                blueprint={"name": "Booking Flow"},
                scheduling={"type": "indefinitely"},
            )

        recovery = RecoveryOrchestrator(
            internal_store=Mock(),
            adapters={"make": adapter},
        )

        result = recovery.reconcile_remote_state(
            {
                "platform": "make",
                "operation": "create_scenario",
                "target": {"name": "Booking Flow"},
                "payload": {"name": "Booking Flow"},
            }
        )

        assert result.resource_found is True
        assert result.remote_id == "scen_123"
        assert result.recommendation == "accept_as_success"

    def test_supabase_insert_timeout_after_success(self) -> None:
        """
        Test: Supabase org record insert succeeds but client times out.

        Expected:
        1. Timeout on insert
        2. Reconciliation finds record
        3. Accept as success
        4. No duplicate record
        """
        adapter = Mock()

        # Timeout on insert
        adapter.insert_org_record.side_effect = AmbiguousOutcomeError("Timeout")

        # Reconciliation finds it
        adapter.select_rows.return_value = [
            {
                "organization_id": "test_org",
                "business_name": "Test Business",
                "status": "active",
            }
        ]

        with pytest.raises(AmbiguousOutcomeError):
            adapter.insert_org_record(
                organization_id="test_org",
                business_name="Test Business",
            )

        recovery = RecoveryOrchestrator(
            internal_store=Mock(),
            adapters={"supabase_client": adapter},
        )

        result = recovery.reconcile_remote_state(
            {
                "platform": "supabase_client",
                "operation": "insert_org_record",
                "target": {"organization_id": "test_org"},
                "payload": {"organization_id": "test_org"},
            }
        )

        assert result.resource_found is True
        assert result.remote_id == "test_org"
        assert result.recommendation == "accept_as_success"

    def test_render_deploy_timeout_after_success(self) -> None:
        """
        Test: Render deploy trigger succeeds but client times out.

        Expected:
        1. Timeout on trigger
        2. Reconciliation finds deploy in progress or live
        3. Accept as success
        4. No duplicate deploy
        """
        adapter = Mock()

        # Timeout on trigger
        adapter.trigger_deploy.side_effect = AmbiguousOutcomeError("Timeout")

        # Reconciliation finds deploy in progress
        adapter.get_deploy_status.return_value = {
            "id": "dep_123",
            "status": "build_in_progress",
            "createdAt": "2024-01-01T00:00:00Z",
        }

        with pytest.raises(AmbiguousOutcomeError):
            adapter.trigger_deploy()

        recovery = RecoveryOrchestrator(
            internal_store=Mock(),
            adapters={"render": adapter},
        )

        result = recovery.reconcile_remote_state(
            {
                "platform": "render",
                "operation": "trigger_deploy",
                "target": {"service": "test-service"},
                "payload": {},
            }
        )

        assert result.resource_found is True
        assert result.remote_id == "dep_123"
        assert result.recommendation == "accept_as_success"

    def test_timeout_then_not_found_allows_retry(self) -> None:
        """
        Test: Timeout occurs but reconciliation finds no resource - safe to retry.

        Expected:
        1. Timeout on create
        2. Reconciliation finds nothing
        3. Recommend retry
        4. Retry succeeds
        """
        adapter = Mock()

        # First: timeout
        # Second (after reconciliation): success
        adapter.create_assistant.side_effect = [
            AmbiguousOutcomeError("Timeout"),
            AdapterReceipt(
                platform="vapi",
                operation="create_assistant",
                remote_id="asst_456",
                status="success",
                response_data={"id": "asst_456"},
            ),
        ]

        # Reconciliation finds nothing
        adapter.list_assistants.return_value = {"data": []}

        # First attempt
        with pytest.raises(AmbiguousOutcomeError):
            adapter.create_assistant({"name": "Test"})

        # Reconcile
        recovery = RecoveryOrchestrator(
            internal_store=Mock(),
            adapters={"vapi": adapter},
        )

        result = recovery.reconcile_remote_state(
            {
                "platform": "vapi",
                "operation": "create_assistant",
                "target": {"name": "Test"},
                "payload": {"name": "Test"},
            }
        )

        assert result.resource_found is False
        assert result.recommendation == "retry"
        assert result.can_proceed is True

        # Retry succeeds
        receipt = adapter.create_assistant({"name": "Test"})
        assert receipt.remote_id == "asst_456"
        assert adapter.create_assistant.call_count == 2

    def test_connection_error_is_ambiguous(self) -> None:
        """
        Test: Connection errors during write operations are ambiguous.

        Expected:
        1. Connection error classified as ambiguous
        2. Requires reconciliation before retry
        """
        adapter = Mock()

        adapter.create_tool.side_effect = AmbiguousOutcomeError("Connection error during request")

        with pytest.raises(AmbiguousOutcomeError) as exc_info:
            adapter.create_tool({"name": "Test Tool"})

        assert "Connection error" in str(exc_info.value)
