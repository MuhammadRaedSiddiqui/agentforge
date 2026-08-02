"""
Deployment history rendering for Agent Forge.

Implements T137: Deployment history renderer (ordered timeline of tasks,
actions, approvals, external requests, corrections, retries, compensations,
state transitions)
"""

from typing import Any, cast

from adapters.supabase_internal import SupabaseInternalClient


class DeploymentHistory:
    """
    Renders deployment history from audit events and operational records.

    Provides ordered timeline of all deployment activities.
    """

    def __init__(self, internal_store: SupabaseInternalClient) -> None:
        """
        Initialize history renderer.

        Args:
            internal_store: SupabaseInternalClient instance
        """
        self.internal_store = internal_store

    def render_deployment_history(
        self,
        deployment_id: str,
        output_format: str = "text",
    ) -> dict[str, Any] | str:
        """
        Render complete deployment history.

        Args:
            deployment_id: Deployment identifier
            output_format: Output format ('text' or 'json')

        Returns:
            Formatted deployment history
        """
        # Get deployment
        deployment = self.internal_store.get_deployment(deployment_id)
        if not deployment:
            return {
                "error": f"Deployment not found: {deployment_id}",
            }

        # Get all related records
        audit_events = self.internal_store.get_audit_events(deployment_id)
        tasks = self.internal_store.get_task_executions(deployment_id)
        actions = self.internal_store.get_proposed_actions(deployment_id)
        approvals = self.internal_store.get_approval_decisions(deployment_id)
        attempts = self.internal_store.get_external_attempts(deployment_id)
        receipts = self.internal_store.get_external_receipts(deployment_id)
        recoveries = self.internal_store.get_recovery_actions(deployment_id)

        # Build timeline
        timeline = self._build_timeline(
            deployment=deployment,
            audit_events=audit_events,
            tasks=tasks,
            actions=actions,
            approvals=approvals,
            attempts=attempts,
            receipts=receipts,
            recoveries=recoveries,
        )

        # Format output
        if output_format == "json":
            return {
                "deployment_id": deployment_id,
                "organization_id": deployment["organization_id"],
                "status": deployment["status"],
                "created_at": deployment["created_at"],
                "updated_at": deployment["updated_at"],
                "timeline": timeline,
                "summary": self._generate_summary(timeline),
            }
        else:
            return self._format_text_output(deployment, timeline)

    def _build_timeline(
        self,
        deployment: dict[str, Any],
        audit_events: list[dict[str, Any]],
        tasks: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        approvals: list[dict[str, Any]],
        attempts: list[dict[str, Any]],
        receipts: list[dict[str, Any]],
        recoveries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Build ordered timeline from all records.

        Args:
            deployment: Deployment record
            audit_events: Audit events
            tasks: Task executions
            actions: Proposed actions
            approvals: Approval decisions
            attempts: External request attempts
            receipts: External receipts
            recoveries: Recovery actions

        Returns:
            Ordered timeline entries
        """
        timeline = []

        # Add audit events
        for event in audit_events:
            timeline.append(
                {
                    "timestamp": event["created_at"],
                    "type": "audit",
                    "event_type": event["event_type"],
                    "actor": event.get("actor") or event.get("actor_id", "system"),
                    "subject": event.get("subject")
                    or event.get("subject_id", deployment["deployment_id"]),
                    "status": event["status"],
                    "detail": event.get("detail"),
                }
            )

        # Add task executions
        for task in tasks:
            timeline.append(
                {
                    "timestamp": task["created_at"],
                    "type": "task",
                    "task_id": task["id"],
                    "agent_target": task["agent_target"],
                    "action_type": task["action_type"],
                    "status": task["status"],
                }
            )

        # Add approval decisions
        for approval in approvals:
            timeline.append(
                {
                    "timestamp": approval["created_at"],
                    "type": "approval",
                    "action_id": approval["action_id"],
                    "decision": approval["decision"],
                    "operator": approval.get("operator"),
                }
            )

        # Add external attempts
        for attempt in attempts:
            timeline.append(
                {
                    "timestamp": attempt["created_at"],
                    "type": "external_attempt",
                    "action_id": attempt["action_id"],
                    "platform": attempt["platform"],
                    "operation": attempt["operation"],
                    "attempt_number": attempt["attempt_number"],
                }
            )

        # Add external receipts
        for receipt in receipts:
            timeline.append(
                {
                    "timestamp": receipt["created_at"],
                    "type": "receipt",
                    "action_id": receipt["action_id"],
                    "remote_id": receipt.get("remote_id"),
                    "success": True,
                }
            )

        # Add recovery actions
        for recovery in recoveries:
            timeline.append(
                {
                    "timestamp": recovery["created_at"],
                    "type": "recovery",
                    "recovery_type": recovery["recovery_type"],
                    "target_action_id": recovery["target_action_id"],
                    "status": recovery["status"],
                }
            )

        # Sort by timestamp
        timeline.sort(key=lambda x: x["timestamp"])

        return timeline

    def _generate_summary(self, timeline: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Generate summary statistics from timeline.

        Args:
            timeline: Timeline entries

        Returns:
            Summary statistics
        """
        return {
            "total_events": len(timeline),
            "tasks_executed": len([e for e in timeline if e["type"] == "task"]),
            "approvals_requested": len([e for e in timeline if e["type"] == "approval"]),
            "external_attempts": len([e for e in timeline if e["type"] == "external_attempt"]),
            "receipts_recorded": len([e for e in timeline if e["type"] == "receipt"]),
            "recoveries_attempted": len([e for e in timeline if e["type"] == "recovery"]),
            "state_transitions": len(
                [e for e in timeline if e.get("event_type") == "deployment_state_transition"]
            ),
        }

    def _format_text_output(
        self,
        deployment: dict[str, Any],
        timeline: list[dict[str, Any]],
    ) -> str:
        """
        Format timeline as text output.

        Args:
            deployment: Deployment record
            timeline: Timeline entries

        Returns:
            Formatted text
        """
        lines = []

        # Header
        lines.append("=" * 80)
        lines.append(f"DEPLOYMENT HISTORY: {deployment['deployment_id']}")
        lines.append("=" * 80)
        lines.append(f"Organization: {deployment['organization_id']}")
        lines.append(f"Status: {deployment['status']}")
        lines.append(f"Created: {deployment['created_at']}")
        lines.append(f"Updated: {deployment['updated_at']}")
        lines.append("")

        # Timeline
        lines.append("TIMELINE")
        lines.append("-" * 80)

        for entry in timeline:
            timestamp = entry["timestamp"]
            entry_type = entry["type"]

            if entry_type == "audit":
                lines.append(
                    f"[{timestamp}] AUDIT: {entry['event_type']} - "
                    f"{entry['actor']} → {entry['subject']} ({entry['status']})"
                )

            elif entry_type == "task":
                lines.append(
                    f"[{timestamp}] TASK: {entry['task_id']} - "
                    f"{entry['agent_target']} {entry['action_type']} ({entry['status']})"
                )

            elif entry_type == "approval":
                lines.append(
                    f"[{timestamp}] APPROVAL: {entry['action_id']} - "
                    f"{entry['decision']} by {entry.get('operator', 'unknown')}"
                )

            elif entry_type == "external_attempt":
                lines.append(
                    f"[{timestamp}] EXTERNAL: {entry['platform']} "
                    f"{entry['operation']} (attempt {entry['attempt_number']})"
                )

            elif entry_type == "receipt":
                lines.append(
                    f"[{timestamp}] RECEIPT: {entry['action_id']} - "
                    f"remote_id: {entry.get('remote_id', 'N/A')}"
                )

            elif entry_type == "recovery":
                lines.append(
                    f"[{timestamp}] RECOVERY: {entry['recovery_type']} "
                    f"for {entry['target_action_id']} ({entry['status']})"
                )

        lines.append("")

        # Summary
        summary = self._generate_summary(timeline)
        lines.append("SUMMARY")
        lines.append("-" * 80)
        lines.append(f"Total events: {summary['total_events']}")
        lines.append(f"Tasks executed: {summary['tasks_executed']}")
        lines.append(f"Approvals requested: {summary['approvals_requested']}")
        lines.append(f"External attempts: {summary['external_attempts']}")
        lines.append(f"Receipts recorded: {summary['receipts_recorded']}")
        lines.append(f"Recoveries attempted: {summary['recoveries_attempted']}")
        lines.append(f"State transitions: {summary['state_transitions']}")
        lines.append("=" * 80)

        return "\n".join(lines)

    def render_organization_history(
        self,
        organization_id: str,
        output_format: str = "text",
    ) -> dict[str, Any] | str:
        """
        Render history for all deployments in an organization.

        Args:
            organization_id: Organization identifier
            output_format: Output format ('text' or 'json')

        Returns:
            Formatted organization history
        """
        # Get all deployments for organization
        deployments = self.internal_store.get_deployments_for_organization(organization_id)

        if not deployments:
            return {
                "error": f"No deployments found for organization: {organization_id}",
            }

        # Render each deployment
        deployment_histories = []

        for deployment in deployments:
            history = self.render_deployment_history(
                deployment["deployment_id"],
                output_format="json",  # Always get structured data
            )
            # Cast since we know it's a dict when format is 'json'
            deployment_histories.append(cast(dict[str, Any], history))

        if output_format == "json":
            return {
                "organization_id": organization_id,
                "deployment_count": len(deployments),
                "deployments": deployment_histories,
            }
        else:
            # Format as text
            lines = []
            lines.append("=" * 80)
            lines.append(f"ORGANIZATION HISTORY: {organization_id}")
            lines.append("=" * 80)
            lines.append(f"Total deployments: {len(deployments)}")
            lines.append("")

            for history in deployment_histories:
                lines.append(f"\nDeployment: {history['deployment_id']}")
                lines.append(f"Status: {history['status']}")
                lines.append(f"Events: {history['summary']['total_events']}")
                lines.append("-" * 40)

            return "\n".join(lines)
