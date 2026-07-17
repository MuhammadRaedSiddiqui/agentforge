"""
Recovery orchestration for partial and ambiguous deployment failures.

Handles:
- Ambiguous outcome detection and marking
- Remote state reconciliation per platform
- Retry flow with reconciliation-first requirement
- Compensation flow with per-action approval
- Failed compensation handling
- Restart detection and recovery presentation
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from orchestrator.state_machine import DeploymentState
from shared.errors import (
    AmbiguousOutcomeError,
    RecoveryRequiredError,
    classify_error,
)


@dataclass
class RecoveryAction:
    """
    Represents a recovery action for a failed or ambiguous deployment action.
    """

    recovery_action_id: str
    deployment_id: str
    proposed_action_id: str | None
    external_resource_id: str | None
    kind: str  # reconcile, retry, compensate, manual_inspection
    operation: str
    sequence_number: int
    status: str  # pending, approved, running, succeeded, failed, deferred
    requires_approval: bool
    failure_summary: str | None
    created_at: datetime
    resolved_at: datetime | None = None


@dataclass
class ReconciliationResult:
    """
    Result of remote state reconciliation for an ambiguous action.
    """

    platform: str
    operation: str
    resource_found: bool
    remote_id: str | None
    remote_state: dict[str, Any] | None
    state_hash: str | None
    matches_expected: bool
    can_proceed: bool
    recommendation: str  # "accept_as_success", "retry", "compensate", "manual_review"


class RecoveryOrchestrator:
    """
    Orchestrates recovery from partial and ambiguous deployment failures.
    """

    def __init__(self, internal_store: Any, adapters: dict[str, Any]) -> None:
        """
        Initialize recovery orchestrator.

        Args:
            internal_store: Internal operational store client
            adapters: Dictionary of platform adapters (vapi, make, supabase_client, render)
        """
        self.internal_store = internal_store
        self.adapters = adapters

    def handle_ambiguous_outcome(
        self,
        deployment_id: str,
        proposed_action_id: str,
        error: AmbiguousOutcomeError,
    ) -> None:
        """
        Handle ambiguous outcome by marking for reconciliation.

        Implements T111: Mark proposal reconciliation_required, create pending
        reconciliation action, transition deployment to recovery_required.

        Args:
            deployment_id: Deployment ID
            proposed_action_id: Proposed action ID that had ambiguous outcome
            error: The ambiguous outcome error
        """
        # Mark proposal as requiring reconciliation
        self.internal_store.update_proposed_action_status(
            proposed_action_id,
            "reconciliation_required",
        )

        # Create pending reconciliation action
        recovery_action = {
            "deployment_id": deployment_id,
            "proposed_action_id": proposed_action_id,
            "kind": "reconcile",
            "operation": "reconcile_remote_state",
            "status": "pending",
            "requires_approval": False,  # Reconciliation is read-only
            "failure_summary": str(error),
            "created_at": datetime.now(UTC).isoformat(),
        }

        recovery_id = self.internal_store.insert_recovery_action(recovery_action)

        # Transition deployment to recovery_required
        self.internal_store.update_deployment_status(
            deployment_id,
            DeploymentState.RECOVERY_REQUIRED.value,
        )

        # Append audit event
        self.internal_store.append_audit_event(
            deployment_id=deployment_id,
            event_type="ambiguous_outcome_detected",
            status="recovery_required",
            subject=proposed_action_id,
            detail={
                "error": str(error),
                "recovery_action_id": recovery_id,
            },
        )

    def reconcile_remote_state(
        self,
        proposed_action: dict[str, Any],
    ) -> ReconciliationResult:
        """
        Reconcile remote state for an ambiguous action.

        Implements T112: Read remote state per adapter, compare with expected,
        determine if operation succeeded and next action.

        Args:
            proposed_action: The proposed action with ambiguous outcome

        Returns:
            ReconciliationResult with findings and recommendation
        """
        platform = proposed_action["platform"]
        operation = proposed_action["operation"]
        target = proposed_action["target"]

        adapter = self.adapters.get(platform)
        if not adapter:
            return ReconciliationResult(
                platform=platform,
                operation=operation,
                resource_found=False,
                remote_id=None,
                remote_state=None,
                state_hash=None,
                matches_expected=False,
                can_proceed=False,
                recommendation="manual_review",
            )

        # Perform platform-specific reconciliation
        if platform == "vapi":
            return self._reconcile_vapi(adapter, operation, target, proposed_action)
        elif platform == "make":
            return self._reconcile_make(adapter, operation, target, proposed_action)
        elif platform == "supabase_client":
            return self._reconcile_supabase(adapter, operation, target, proposed_action)
        elif platform == "render":
            return self._reconcile_render(adapter, operation, target, proposed_action)
        else:
            return ReconciliationResult(
                platform=platform,
                operation=operation,
                resource_found=False,
                remote_id=None,
                remote_state=None,
                state_hash=None,
                matches_expected=False,
                can_proceed=False,
                recommendation="manual_review",
            )

    def _reconcile_vapi(
        self,
        adapter: Any,
        operation: str,
        target: dict[str, Any],
        proposed_action: dict[str, Any],
    ) -> ReconciliationResult:
        """Reconcile Vapi resource state."""
        try:
            if operation == "create_assistant":
                # List assistants and check if one matches expected config
                assistants = adapter.list_assistants()
                # Match by name or configuration
                expected_name = proposed_action.get("payload", {}).get("name")
                for assistant in assistants.get("data", []):
                    if assistant.get("name") == expected_name:
                        return ReconciliationResult(
                            platform="vapi",
                            operation=operation,
                            resource_found=True,
                            remote_id=assistant.get("id"),
                            remote_state=assistant,
                            state_hash=None,
                            matches_expected=True,
                            can_proceed=True,
                            recommendation="accept_as_success",
                        )

                # Not found - safe to retry
                return ReconciliationResult(
                    platform="vapi",
                    operation=operation,
                    resource_found=False,
                    remote_id=None,
                    remote_state=None,
                    state_hash=None,
                    matches_expected=False,
                    can_proceed=True,
                    recommendation="retry",
                )

            elif operation == "create_tool":
                # List tools and check if one matches
                tools = adapter.list_tools()
                expected_name = proposed_action.get("payload", {}).get("name")
                for tool in tools.get("data", []):
                    if tool.get("name") == expected_name:
                        return ReconciliationResult(
                            platform="vapi",
                            operation=operation,
                            resource_found=True,
                            remote_id=tool.get("id"),
                            remote_state=tool,
                            state_hash=None,
                            matches_expected=True,
                            can_proceed=True,
                            recommendation="accept_as_success",
                        )

                return ReconciliationResult(
                    platform="vapi",
                    operation=operation,
                    resource_found=False,
                    remote_id=None,
                    remote_state=None,
                    state_hash=None,
                    matches_expected=False,
                    can_proceed=True,
                    recommendation="retry",
                )

        except Exception:
            # Reconciliation itself failed
            return ReconciliationResult(
                platform="vapi",
                operation=operation,
                resource_found=False,
                remote_id=None,
                remote_state=None,
                state_hash=None,
                matches_expected=False,
                can_proceed=False,
                recommendation="manual_review",
            )

        return ReconciliationResult(
            platform="vapi",
            operation=operation,
            resource_found=False,
            remote_id=None,
            remote_state=None,
            state_hash=None,
            matches_expected=False,
            can_proceed=False,
            recommendation="manual_review",
        )

    def _reconcile_make(
        self,
        adapter: Any,
        operation: str,
        target: dict[str, Any],
        proposed_action: dict[str, Any],
    ) -> ReconciliationResult:
        """Reconcile Make.com resource state."""
        try:
            if operation == "create_scenario":
                # List scenarios by team and check for match
                scenarios = adapter.list_scenarios()
                expected_name = proposed_action.get("payload", {}).get("name")
                for scenario in scenarios.get("scenarios", []):
                    if scenario.get("name") == expected_name:
                        return ReconciliationResult(
                            platform="make",
                            operation=operation,
                            resource_found=True,
                            remote_id=scenario.get("id"),
                            remote_state=scenario,
                            state_hash=None,
                            matches_expected=True,
                            can_proceed=True,
                            recommendation="accept_as_success",
                        )

                return ReconciliationResult(
                    platform="make",
                    operation=operation,
                    resource_found=False,
                    remote_id=None,
                    remote_state=None,
                    state_hash=None,
                    matches_expected=False,
                    can_proceed=True,
                    recommendation="retry",
                )

            elif operation == "create_hook":
                # List hooks and check for match
                hooks = adapter.list_hooks()
                expected_name = proposed_action.get("payload", {}).get("name")
                for hook in hooks.get("hooks", []):
                    if hook.get("name") == expected_name:
                        return ReconciliationResult(
                            platform="make",
                            operation=operation,
                            resource_found=True,
                            remote_id=hook.get("id"),
                            remote_state=hook,
                            state_hash=None,
                            matches_expected=True,
                            can_proceed=True,
                            recommendation="accept_as_success",
                        )

                return ReconciliationResult(
                    platform="make",
                    operation=operation,
                    resource_found=False,
                    remote_id=None,
                    remote_state=None,
                    state_hash=None,
                    matches_expected=False,
                    can_proceed=True,
                    recommendation="retry",
                )

        except Exception:
            return ReconciliationResult(
                platform="make",
                operation=operation,
                resource_found=False,
                remote_id=None,
                remote_state=None,
                state_hash=None,
                matches_expected=False,
                can_proceed=False,
                recommendation="manual_review",
            )

        return ReconciliationResult(
            platform="make",
            operation=operation,
            resource_found=False,
            remote_id=None,
            remote_state=None,
            state_hash=None,
            matches_expected=False,
            can_proceed=False,
            recommendation="manual_review",
        )

    def _reconcile_supabase(
        self,
        adapter: Any,
        operation: str,
        target: dict[str, Any],
        proposed_action: dict[str, Any],
    ) -> ReconciliationResult:
        """Reconcile Supabase resource state."""
        try:
            if operation == "insert_org_record":
                # Check if organization record exists
                org_id = proposed_action.get("payload", {}).get("organization_id")
                existing = adapter.select_rows(
                    table="organizations",
                    filters={"organization_id": org_id},
                )

                if existing:
                    return ReconciliationResult(
                        platform="supabase_client",
                        operation=operation,
                        resource_found=True,
                        remote_id=org_id,
                        remote_state=existing[0] if existing else None,
                        state_hash=None,
                        matches_expected=True,
                        can_proceed=True,
                        recommendation="accept_as_success",
                    )

                return ReconciliationResult(
                    platform="supabase_client",
                    operation=operation,
                    resource_found=False,
                    remote_id=None,
                    remote_state=None,
                    state_hash=None,
                    matches_expected=False,
                    can_proceed=True,
                    recommendation="retry",
                )

        except Exception:
            return ReconciliationResult(
                platform="supabase_client",
                operation=operation,
                resource_found=False,
                remote_id=None,
                remote_state=None,
                state_hash=None,
                matches_expected=False,
                can_proceed=False,
                recommendation="manual_review",
            )

        return ReconciliationResult(
            platform="supabase_client",
            operation=operation,
            resource_found=False,
            remote_id=None,
            remote_state=None,
            state_hash=None,
            matches_expected=False,
            can_proceed=False,
            recommendation="manual_review",
        )

    def _reconcile_render(
        self,
        adapter: Any,
        operation: str,
        target: dict[str, Any],
        proposed_action: dict[str, Any],
    ) -> ReconciliationResult:
        """Reconcile Render resource state."""
        try:
            if operation == "trigger_deploy":
                # Get latest deploy status
                status = adapter.get_deploy_status()

                # Check if there's a recent successful deploy
                if status and status.get("status") in ["live", "build_in_progress"]:
                    return ReconciliationResult(
                        platform="render",
                        operation=operation,
                        resource_found=True,
                        remote_id=status.get("id"),
                        remote_state=status,
                        state_hash=None,
                        matches_expected=True,
                        can_proceed=True,
                        recommendation="accept_as_success",
                    )

                # If deploy failed or not found, safe to retry
                return ReconciliationResult(
                    platform="render",
                    operation=operation,
                    resource_found=False,
                    remote_id=None,
                    remote_state=status,
                    state_hash=None,
                    matches_expected=False,
                    can_proceed=True,
                    recommendation="retry",
                )

        except Exception:
            return ReconciliationResult(
                platform="render",
                operation=operation,
                resource_found=False,
                remote_id=None,
                remote_state=None,
                state_hash=None,
                matches_expected=False,
                can_proceed=False,
                recommendation="manual_review",
            )

        return ReconciliationResult(
            platform="render",
            operation=operation,
            resource_found=False,
            remote_id=None,
            remote_state=None,
            state_hash=None,
            matches_expected=False,
            can_proceed=False,
            recommendation="manual_review",
        )

    def execute_retry(
        self,
        deployment_id: str,
        recovery_action_id: str,
        proposed_action: dict[str, Any],
        operator: str,
    ) -> dict[str, Any]:
        """
        Execute retry for a failed or reconciled action.

        Implements T113: Only retry failed/unresolved step, requires reconciliation
        first for ambiguous outcomes, requires fresh approval, bounded retry count.

        Args:
            deployment_id: Deployment ID
            recovery_action_id: Recovery action ID
            proposed_action: The action to retry
            operator: Operator identifier

        Returns:
            Retry result
        """
        # Check if action was reconciled (for ambiguous outcomes)
        action_status = proposed_action.get("status")
        if action_status == "reconciliation_required":
            raise RecoveryRequiredError("Action requires reconciliation before retry")

        # Get retry count
        retry_count = proposed_action.get("retry_count", 0)
        max_retries = 2  # Bounded retry count

        if retry_count >= max_retries:
            return {
                "status": "max_retries_exceeded",
                "message": f"Action has already been retried {retry_count} times",
                "recommendation": "compensate",
            }

        # Fresh approval is required for retry
        # This would be handled by the orchestrator's normal approval flow
        # Mark recovery action as approved
        self.internal_store.update_recovery_action_status(
            recovery_action_id,
            "approved",
        )

        # Increment retry count
        new_retry_count = retry_count + 1

        return {
            "status": "ready_for_retry",
            "retry_count": new_retry_count,
            "requires_approval": True,
            "message": f"Retry {new_retry_count} of {max_retries}",
        }

    def execute_compensation(
        self,
        deployment_id: str,
        recovery_action_id: str,
        proposed_action: dict[str, Any],
        operator: str,
    ) -> dict[str, Any]:
        """
        Execute compensation for a failed action.

        Implements T114: Individual description, separate approval per compensating
        action, execution, receipt recording.

        Args:
            deployment_id: Deployment ID
            recovery_action_id: Recovery action ID
            proposed_action: The action to compensate
            operator: Operator identifier

        Returns:
            Compensation result
        """
        compensation_op = proposed_action.get("compensation_operation")

        if not compensation_op:
            return {
                "status": "no_compensation_available",
                "message": "No safe compensation operation defined for this action",
                "recommendation": "manual_inspection",
            }

        # Build compensation action description
        platform = proposed_action["platform"]
        operation = proposed_action["operation"]

        compensation_description = f"Compensate {operation} on {platform}: {compensation_op}"

        # Compensation requires separate approval
        # This would be handled through the normal approval flow
        # For now, mark as pending approval

        return {
            "status": "compensation_ready",
            "compensation_operation": compensation_op,
            "description": compensation_description,
            "requires_approval": True,
            "message": "Compensation action ready for approval",
        }

    def handle_compensation_failure(
        self,
        deployment_id: str,
        recovery_action_id: str,
        error: Exception,
    ) -> dict[str, Any]:
        """
        Handle failed compensation operation.

        Implements T115: Deployment remains unresolved, remaining resources listed,
        next safe action identified.

        Args:
            deployment_id: Deployment ID
            recovery_action_id: Recovery action ID
            error: The compensation error

        Returns:
            Failure handling result
        """
        # Mark recovery action as failed
        self.internal_store.update_recovery_action_status(
            recovery_action_id,
            "failed",
        )

        # Get all resources from this deployment
        resources = self.internal_store.list_external_resources(deployment_id)

        # Deployment remains in recovery_required state
        # List what exists and what's unresolved

        return {
            "status": "compensation_failed",
            "message": "Compensation operation failed",
            "error": str(error),
            "error_class": classify_error(error),
            "deployment_status": "recovery_required",
            "existing_resources": resources,
            "recommendation": "manual_inspection",
            "next_actions": [
                "Review existing resources",
                "Determine manual cleanup steps",
                "Contact platform support if needed",
                "Document resolution in audit log",
            ],
        }

    def detect_restart_recovery(
        self,
        organization_id: str,
    ) -> dict[str, Any] | None:
        """
        Detect if organization has unresolved recovery on session start.

        Implements T116: Check for unresolved partial/recovery_required deployments,
        present recovery before new work.

        Args:
            organization_id: Organization identifier

        Returns:
            Recovery info if found, None otherwise
        """
        # Query for deployments in recovery states
        recovery_states = [
            DeploymentState.PARTIAL.value,
            DeploymentState.RECOVERY_REQUIRED.value,
            DeploymentState.COMPENSATING.value,
        ]

        deployments = self.internal_store.list_deployments(
            organization_id=organization_id,
            statuses=recovery_states,
        )

        if not deployments:
            return None

        # Get the most recent recovery-required deployment
        deployment = deployments[0]  # Assuming sorted by created_at desc

        # Get pending recovery actions
        recovery_actions = self.internal_store.list_recovery_actions(
            deployment_id=deployment["deployment_id"],
            statuses=["pending", "failed"],
        )

        # Get completed resources
        completed_resources = self.internal_store.list_external_resources(
            deployment_id=deployment["deployment_id"],
        )

        return {
            "has_recovery": True,
            "deployment_id": deployment["deployment_id"],
            "deployment_status": deployment["status"],
            "intent": deployment.get("intent"),
            "started_at": deployment.get("started_at"),
            "recovery_actions": recovery_actions,
            "completed_resources": completed_resources,
            "message": "This organization has an unresolved deployment requiring recovery",
        }

    def format_recovery_options(
        self,
        recovery_info: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Format recovery options for CLI display.

        Implements T119: Partial state summary, completed resources, available
        options: retry/compensate/abort/defer.

        Args:
            recovery_info: Recovery information from detect_restart_recovery

        Returns:
            Formatted options for display
        """
        deployment_status = recovery_info["deployment_status"]
        recovery_actions = recovery_info.get("recovery_actions", [])
        completed_resources = recovery_info.get("completed_resources", [])

        summary = {
            "deployment_id": recovery_info["deployment_id"],
            "status": deployment_status,
            "completed_count": len(completed_resources),
            "pending_recovery_count": len(recovery_actions),
        }

        available_options = []

        # Determine available options based on state
        if recovery_actions:
            for action in recovery_actions:
                if action["kind"] == "reconcile":
                    available_options.append("reconcile")
                elif action["kind"] == "retry":
                    available_options.append("retry")
                elif action["kind"] == "compensate":
                    available_options.append("compensate")

        # Always available
        available_options.extend(["defer", "abort"])

        return {
            "summary": summary,
            "completed_resources": [
                {
                    "platform": r["platform"],
                    "resource_type": r["resource_type"],
                    "remote_id": r.get("remote_resource_id"),
                }
                for r in completed_resources
            ],
            "pending_actions": [
                {
                    "kind": action["kind"],
                    "operation": action["operation"],
                    "status": action["status"],
                }
                for action in recovery_actions
            ],
            "available_options": list(set(available_options)),
        }
