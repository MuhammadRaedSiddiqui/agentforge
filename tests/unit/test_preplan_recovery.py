"""Tests for safe termination of deployments that fail before planning."""

from unittest.mock import Mock

import pytest

from adapters.supabase_internal import SupabaseInternalClient


def _store_with_deployment(deployment: dict) -> SupabaseInternalClient:
    store = object.__new__(SupabaseInternalClient)
    store.get_deployment = Mock(return_value=deployment)
    store.update = Mock(return_value=[{"deployment_id": "dep-001", "status": "failed"}])
    return store


def test_terminate_preplan_deployment_marks_orphan_failed() -> None:
    store = _store_with_deployment(
        {"deployment_id": "dep-001", "status": "planning", "plan_hash": None}
    )

    store.terminate_preplan_deployment("dep-001", "interrupted before plan persistence")

    payload = store.update.call_args.args[2]
    assert payload["status"] == "failed"
    assert payload["failure_class"] == "local_persistence_failure"
    assert payload["failure_summary"] == "interrupted before plan persistence"
    assert payload["completed_at"]


@pytest.mark.parametrize(
    "deployment",
    [
        {"deployment_id": "dep-001", "status": "generating", "plan_hash": "plan-123"},
        {"deployment_id": "dep-001", "status": "planning", "plan_hash": "plan-123"},
    ],
)
def test_terminate_preplan_deployment_rejects_non_preplan_records(deployment: dict) -> None:
    store = _store_with_deployment(deployment)

    with pytest.raises(ValueError, match="Only planning deployments"):
        store.terminate_preplan_deployment("dep-001", "should not be permitted")

    store.update.assert_not_called()
