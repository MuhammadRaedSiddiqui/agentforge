"""
Deployment lookup for existing or partial deployments.

Checks for existing deployments and their status before allowing new work.
"""

from typing import Dict, List, Optional

from adapters.supabase_internal import SupabaseInternalClient
from orchestrator.state_machine import DeploymentStateMachine


class DeploymentLookup:
    """
    Lookup existing deployments for an organization.

    Provides information about deployment status and whether
    new work can proceed.
    """

    def __init__(self, internal_client: SupabaseInternalClient):
        """
        Initialize deployment lookup.

        Args:
            internal_client: Supabase internal client
        """
        self.client = internal_client

    def get_latest_deployment(
        self, organization_id: str
    ) -> Optional[Dict[str, any]]:
        """
        Get latest deployment for organization.

        Args:
            organization_id: Normalized organization identifier

        Returns:
            Latest deployment record or None if no deployments exist
        """
        deployments = self.client.select(
            "deployments",
            filters={"organization_id": organization_id},
            order_by="created_at",
            limit=1,
        )

        if deployments and len(deployments) > 0:
            return deployments[0]

        return None

    def get_active_deployment(
        self, organization_id: str
    ) -> Optional[Dict[str, any]]:
        """
        Get active (non-terminal) deployment for organization.

        Args:
            organization_id: Normalized organization identifier

        Returns:
            Active deployment or None
        """
        latest = self.get_latest_deployment(organization_id)

        if not latest:
            return None

        status = latest.get("status")

        # Check if terminal
        if DeploymentStateMachine.is_terminal(status):
            return None

        return latest

    def has_unresolved_recovery(self, organization_id: str) -> bool:
        """
        Check if organization has unresolved recovery actions.

        Args:
            organization_id: Normalized organization identifier

        Returns:
            True if unresolved recovery exists
        """
        latest = self.get_latest_deployment(organization_id)

        if not latest:
            return False

        status = latest.get("status")

        # Check if in recovery state
        if not DeploymentStateMachine.requires_recovery(status):
            return False

        # Check for unresolved recovery actions
        deployment_id = latest.get("deployment_id")

        if not deployment_id:
            return False

        recovery_actions = self.client.select(
            "recovery_actions",
            filters={"deployment_id": deployment_id},
        )

        # Check if any recovery actions are pending or failed
        unresolved = [
            action for action in recovery_actions
            if action.get("status") in ["pending", "failed", "approved", "running"]
        ]

        return len(unresolved) > 0

    def can_start_new_deployment(
        self, organization_id: str, intent: str
    ) -> Dict[str, any]:
        """
        Check if new deployment can start for organization.

        Args:
            organization_id: Normalized organization identifier
            intent: Proposed deployment intent

        Returns:
            Dictionary with:
            - can_start: bool indicating if new deployment can start
            - reason: explanation if cannot start
            - existing_deployment: existing deployment info (if any)
            - requires_recovery: bool if recovery needed first
        """
        latest = self.get_latest_deployment(organization_id)

        if not latest:
            # No existing deployment, can start
            return {
                "can_start": True,
                "reason": "No existing deployment",
                "existing_deployment": None,
                "requires_recovery": False,
            }

        status = latest.get("status")

        # Check if new deployment can start given current state
        can_start = DeploymentStateMachine.can_start_new_deployment(status, intent)

        if can_start:
            return {
                "can_start": True,
                "reason": f"Existing deployment is in terminal state: {status}",
                "existing_deployment": latest,
                "requires_recovery": False,
            }

        # Cannot start new deployment
        reason = f"Existing deployment is in state: {status}"

        # Check if recovery is required
        requires_recovery = DeploymentStateMachine.requires_recovery(status)

        if requires_recovery:
            reason += " (recovery required)"

        return {
            "can_start": False,
            "reason": reason,
            "existing_deployment": latest,
            "requires_recovery": requires_recovery,
        }

    def get_deployment_history(
        self, organization_id: str, limit: int = 10
    ) -> List[Dict[str, any]]:
        """
        Get deployment history for organization.

        Args:
            organization_id: Normalized organization identifier
            limit: Maximum number of deployments to return

        Returns:
            List of deployment records, most recent first
        """
        # Query with descending order (most recent first)
        deployments = self.client.select(
            "deployments",
            filters={"organization_id": organization_id},
            order_by="created_at desc",
            limit=limit,
        )

        return deployments

    def get_partial_deployment_summary(
        self, deployment_id: str
    ) -> Dict[str, any]:
        """
        Get summary of partial deployment progress.

        Args:
            deployment_id: Deployment identifier

        Returns:
            Dictionary with:
            - deployment_id: deployment identifier
            - status: current status
            - completed_tasks: number of completed tasks
            - total_tasks: total number of tasks
            - completed_actions: list of completed actions
            - pending_actions: list of pending actions
        """
        # Get deployment
        deployment = self.client.get_by_id("deployments", "deployment_id", deployment_id)

        if not deployment:
            return {
                "deployment_id": deployment_id,
                "status": "not_found",
            }

        # Get tasks
        tasks = self.client.select(
            "task_executions",
            filters={"deployment_id": deployment_id},
        )

        completed_tasks = [t for t in tasks if t.get("status") == "success"]

        # Get actions
        actions = self.client.select(
            "proposed_actions",
            filters={"deployment_id": deployment_id},
        )

        completed_actions = [
            {
                "platform": a.get("platform"),
                "operation": a.get("operation"),
                "status": a.get("status"),
            }
            for a in actions
            if a.get("status") == "succeeded"
        ]

        pending_actions = [
            {
                "platform": a.get("platform"),
                "operation": a.get("operation"),
                "status": a.get("status"),
            }
            for a in actions
            if a.get("status") in ["proposed", "validated", "awaiting_approval", "approved"]
        ]

        return {
            "deployment_id": deployment_id,
            "status": deployment.get("status"),
            "completed_tasks": len(completed_tasks),
            "total_tasks": len(tasks),
            "completed_actions": completed_actions,
            "pending_actions": pending_actions,
        }

    def get_external_resources(
        self, organization_id: str
    ) -> List[Dict[str, any]]:
        """
        Get all external resources for organization.

        Args:
            organization_id: Normalized organization identifier

        Returns:
            List of external resource records
        """
        resources = self.client.select(
            "external_resources",
            filters={"organization_id": organization_id},
        )

        return resources
