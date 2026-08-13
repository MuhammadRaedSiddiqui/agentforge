"""Tests for DeploymentLookup latest-deployment selection."""

import pytest

from orchestrator.deployment_lookup import DeploymentLookup
from orchestrator.state_machine import DeploymentStateMachine


class MockStore:
    """Minimal fake of SupabaseInternalClient.select for lookup tests."""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = list(rows)
        self._calls = []

    def select(self, table, columns="*", filters=None, order_by=None, limit=None):
        self._calls.append(
            {
                "table": table,
                "filters": dict(filters or {}),
                "order_by": order_by,
                "limit": limit,
            }
        )
        rows = list(self._rows)
        if filters:
            for key, value in filters.items():
                rows = [r for r in rows if r.get(key) == value]
        if order_by:
            parts = order_by.strip().split()
            column = parts[0]
            desc = len(parts) > 1 and parts[1].lower() == "desc"
            rows.sort(key=lambda r: r.get(column) or "", reverse=desc)
        if limit:
            rows = rows[:limit]
        return rows

    def get_latest_deployment(self, organization_id: str) -> dict | None:
        rows = self.select(
            "deployments",
            filters={"organization_id": organization_id},
            order_by="created_at desc",
            limit=1,
        )
        return rows[0] if rows else None


def _row(deployment_id: str, status: str, created_at: str) -> dict:
    return {
        "deployment_id": deployment_id,
        "organization_id": "sunrise_dental",
        "status": status,
        "created_at": created_at,
    }


@pytest.mark.unit
class TestDeploymentLookupLatest:
    def test_latest_picks_newest(self) -> None:
        """Should return the newest deployment, not the oldest."""
        rows = [
            _row("old-aborted", "aborted", "2026-08-10T07:01:00+00:00"),
            _row("new-recovery", "recovery_required", "2026-08-10T10:32:00+00:00"),
        ]
        lookup = DeploymentLookup(MockStore(rows))

        latest = lookup.get_latest_deployment("sunrise_dental")

        assert latest["deployment_id"] == "new-recovery"
        assert latest["status"] == "recovery_required"

    def test_latest_deployment_order_is_descending(self) -> None:
        """Should query with descending created_at ordering."""
        lookup = DeploymentLookup(MockStore([]))

        lookup.get_latest_deployment("sunrise_dental")

        call = lookup.client._calls[-1]
        assert call["order_by"] == "created_at desc"

    def test_can_start_new_deployment_blocked_by_latest_recovery(self) -> None:
        """Should block new deployment when the newest is recovery_required."""
        rows = [
            _row("old-aborted", "aborted", "2026-08-10T07:01:00+00:00"),
            _row("new-recovery", "recovery_required", "2026-08-10T10:32:00+00:00"),
        ]
        lookup = DeploymentLookup(MockStore(rows))

        result = lookup.can_start_new_deployment("sunrise_dental", "new_onboarding")

        assert result["can_start"] is False
        assert "recovery_required" in result["reason"]
        assert result["requires_recovery"] is True
        assert result["existing_deployment"]["deployment_id"] == "new-recovery"

    def test_can_start_new_deployment_after_latest_aborted(self) -> None:
        """Should allow new deployment when the newest deployment is terminal."""
        rows = [
            _row("old-recovery", "recovery_required", "2026-08-10T07:01:00+00:00"),
            _row("new-aborted", "aborted", "2026-08-10T10:32:00+00:00"),
        ]
        lookup = DeploymentLookup(MockStore(rows))

        result = lookup.can_start_new_deployment("sunrise_dental", "new_onboarding")

        assert result["can_start"] is True
        assert result["existing_deployment"]["deployment_id"] == "new-aborted"

    def test_has_unresolved_recovery_false_when_latest_terminal(self) -> None:
        """Should not report unresolved recovery when the latest is terminal."""
        rows = [
            _row("old-recovery", "recovery_required", "2026-08-10T07:01:00+00:00"),
            _row("new-aborted", "aborted", "2026-08-10T10:32:00+00:00"),
        ]
        store = MockStore(rows)
        store.select = lambda *a, **k: []  # no recovery_actions rows
        lookup = DeploymentLookup(store)

        assert lookup.has_unresolved_recovery("sunrise_dental") is False

    def test_state_machine_abort_from_recovery_required(self) -> None:
        """recovery_required -> aborted is a permitted transition."""
        assert DeploymentStateMachine.is_valid_transition("recovery_required", "aborted")
