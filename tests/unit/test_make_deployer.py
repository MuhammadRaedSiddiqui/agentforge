"""Tests for MakeScenarioDeployer multi-step deployment."""

import json
from unittest.mock import MagicMock

import pytest

from adapters.base import AdapterReceipt
from orchestrator.make_deployer import EXPECTED_MODULE_COUNTS, MakeScenarioDeployer


@pytest.fixture
def mock_adapter():
    adapter = MagicMock()
    adapter.create_hook.return_value = AdapterReceipt(
        platform="make",
        operation="create_hook",
        remote_id="99001",
        status="success",
        response_data={"hook": {"id": 99001}},
        idempotency_key=None,
        can_retry=False,
    )
    adapter.create_scenario.return_value = AdapterReceipt(
        platform="make",
        operation="create_scenario",
        remote_id="55001",
        status="success",
        response_data={"scenario": {"id": 55001}},
        idempotency_key=None,
        can_retry=False,
    )
    adapter.get_scenario_blueprint.return_value = AdapterReceipt(
        platform="make",
        operation="get_scenario_blueprint",
        remote_id="55001",
        status="success",
        response_data={
            "response": {
                "blueprint": {
                    "flow": [{"id": i, "module": "test"} for i in range(1, 5)]
                }
            },
            "code": 200,
        },
        idempotency_key=None,
        can_retry=True,
    )
    adapter.activate_scenario.return_value = AdapterReceipt(
        platform="make",
        operation="activate_scenario",
        remote_id="55001",
        status="success",
        response_data={"scenario": {"id": 55001, "isActive": True}},
        idempotency_key=None,
        can_retry=False,
    )
    adapter.update_scenario_blueprint.return_value = AdapterReceipt(
        platform="make",
        operation="update_scenario_blueprint",
        remote_id="55001",
        status="success",
        response_data={},
        idempotency_key=None,
        can_retry=False,
    )
    return adapter


@pytest.fixture
def availability_blueprint(tmp_path):
    blueprint = {
        "name": "Test - Availability",
        "flow": [
            {"id": 1, "module": "gateway:CustomWebHook", "version": 1, "parameters": {"hook": "{{availability_hook_id}}"}, "mapper": {}},
            {"id": 2, "module": "supabase:searchRows", "version": 1, "parameters": {"__IMTCONN__": "{{supabase_connection_id}}"}, "mapper": {"table": "availability_slots"}},
            {"id": 3, "module": "json:TransformToJSON", "version": 1, "parameters": {}, "mapper": {}},
            {"id": 4, "module": "http:ActionSendData", "version": 3, "parameters": {}, "mapper": {}},
        ],
        "metadata": {"version": 1},
    }
    path = tmp_path / "availability.json"
    path.write_text(json.dumps(blueprint))
    return str(path)


@pytest.mark.unit
class TestMakeScenarioDeployer:
    def test_deploy_creates_hook_first(self, mock_adapter, availability_blueprint):
        deployer = MakeScenarioDeployer(mock_adapter)
        result = deployer.deploy_scenario(
            capability="availability",
            blueprint_path=availability_blueprint,
            hook_name="test-hook",
        )

        mock_adapter.create_hook.assert_called_once_with(
            name="test-hook",
            type_name="gateway-webhook",
            method=True,
            headers=True,
            stringify=True,
        )
        assert result["hook_id"] == "99001"

    def test_deploy_injects_hook_id_into_blueprint(self, mock_adapter, availability_blueprint):
        deployer = MakeScenarioDeployer(mock_adapter)
        deployer.deploy_scenario(
            capability="availability",
            blueprint_path=availability_blueprint,
        )

        call_args = mock_adapter.create_scenario.call_args
        blueprint_arg = call_args[0][0]
        webhook_module = blueprint_arg["flow"][0]
        assert webhook_module["parameters"]["hook"] == 99001

    def test_deploy_injects_connection_id(self, mock_adapter, availability_blueprint):
        deployer = MakeScenarioDeployer(mock_adapter)
        deployer.deploy_scenario(
            capability="availability",
            blueprint_path=availability_blueprint,
            connection_id="12345",
        )

        call_args = mock_adapter.create_scenario.call_args
        blueprint_arg = call_args[0][0]
        supabase_module = blueprint_arg["flow"][1]
        assert supabase_module["parameters"]["__IMTCONN__"] == 12345

    def test_deploy_activates_scenario(self, mock_adapter, availability_blueprint):
        deployer = MakeScenarioDeployer(mock_adapter)
        result = deployer.deploy_scenario(
            capability="availability",
            blueprint_path=availability_blueprint,
        )

        mock_adapter.activate_scenario.assert_called_once_with(55001)
        assert result["activated"] is True

    def test_deploy_verifies_module_count(self, mock_adapter, availability_blueprint):
        deployer = MakeScenarioDeployer(mock_adapter)
        result = deployer.deploy_scenario(
            capability="availability",
            blueprint_path=availability_blueprint,
        )

        mock_adapter.get_scenario_blueprint.assert_called_once_with(55001)
        assert result["module_count"] == 4
        assert result["module_count"] == EXPECTED_MODULE_COUNTS["availability"]

    def test_module_count_includes_nested_router_routes(self):
        """Count all modules including nested router route flows."""
        from orchestrator.make_deployer import MakeScenarioDeployer

        flow = [
            {"id": 1, "module": "gateway:CustomWebHook"},
            {"id": 2, "module": "supabase:searchRows"},
            {
                "id": 3,
                "module": "builtin:BasicRouter",
                "routes": [
                    {"flow": [{"id": 4}, {"id": 5}]},
                    {"flow": [{"id": 6}]},
                ],
            },
            {"id": 7, "module": "http:ActionSendData"},
        ]
        assert MakeScenarioDeployer._count_modules(flow) == 7

    def test_deploy_fallback_on_creation_failure(self, mock_adapter, availability_blueprint):
        from shared.errors import PermanentError

        mock_adapter.create_scenario.side_effect = [
            PermanentError("IM007 blueprint error"),
            AdapterReceipt(
                platform="make", operation="create_scenario",
                remote_id="55002", status="success",
                response_data={"scenario": {"id": 55002}},
                idempotency_key=None, can_retry=False,
            ),
        ]

        deployer = MakeScenarioDeployer(mock_adapter)
        result = deployer.deploy_scenario(
            capability="availability",
            blueprint_path=availability_blueprint,
        )

        assert result["used_fallback"] is True
        assert result["scenario_id"] == 55002
        mock_adapter.update_scenario_blueprint.assert_called_once()

    def test_deploy_returns_scenario_id(self, mock_adapter, availability_blueprint):
        deployer = MakeScenarioDeployer(mock_adapter)
        result = deployer.deploy_scenario(
            capability="availability",
            blueprint_path=availability_blueprint,
        )

        assert result["scenario_id"] == 55001
        assert result["capability"] == "availability"

    def test_expected_module_counts(self):
        assert EXPECTED_MODULE_COUNTS["availability"] == 4
        assert EXPECTED_MODULE_COUNTS["booking"] == 6
        assert EXPECTED_MODULE_COUNTS["cancellation"] == 8
        assert EXPECTED_MODULE_COUNTS["rescheduling"] == 10
