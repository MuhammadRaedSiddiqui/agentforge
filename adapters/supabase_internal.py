"""
Supabase internal client wrapper for Agent Forge operational store.

Provides connection management and typed access to the internal
Supabase project that stores deployment state and audit records.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from cli.config import AgentForgeConfig, load_config
from shared.hashing import hash_json
from supabase import Client, create_client

Row = dict[str, Any]


class SupabaseInternalClient:
    """
    Wrapper for Supabase internal operational store.

    Manages connection to the separate internal Supabase project
    used for Agent Forge operational records.
    """

    def __init__(self, config: AgentForgeConfig | None = None):
        """
        Initialize Supabase internal client.

        Args:
            config: Agent Forge configuration with internal Supabase credentials
        """
        self.config = config or load_config()
        self._client: Client | None = None

    @property
    def client(self) -> Client:
        """
        Get or create Supabase client.

        Returns:
            Initialized Supabase client

        Raises:
            ConnectionError: If client cannot be created
        """
        if self._client is None:
            try:
                self._client = create_client(
                    self.config.supabase_internal_url,
                    self.config.supabase_internal_service_role_key,
                )
            except Exception as e:
                raise ConnectionError(f"Failed to create Supabase internal client: {e}") from e

        return self._client

    @property
    def supabase(self) -> Client:
        """Backward-compatible alias used by older scripts."""
        return self.client

    @staticmethod
    def _normalize_row(value: Any) -> Row:
        """Normalize Supabase SDK values to a row dictionary."""
        if not isinstance(value, Mapping):
            raise TypeError(f"Expected mapping row, got {type(value).__name__}")
        return dict(value)

    def _normalize_rows(self, value: Any) -> list[Row]:
        """Normalize Supabase SDK values to a list of row dictionaries."""
        if value is None:
            return []
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            raise TypeError(f"Expected sequence of rows, got {type(value).__name__}")
        return [self._normalize_row(row) for row in value]

    def health_check(self) -> bool:
        """
        Check if connection to internal Supabase is healthy.

        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            # Try a simple query to verify connection
            result = self.client.table("organizations").select("count").limit(1).execute()
            return result is not None
        except Exception:
            return False

    def insert(self, table: str, data: dict[str, Any]) -> Row:
        """
        Insert a row into a table.

        Args:
            table: Table name
            data: Row data to insert

        Returns:
            Inserted row data

        Raises:
            Exception: If insert fails
        """
        result = self.client.table(table).insert(data).execute()
        if result.data:
            rows = self._normalize_rows(result.data)
            if rows:
                return rows[0]
        raise Exception(f"Insert failed for table {table}")

    def select(
        self,
        table: str,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[Row]:
        """
        Select rows from a table.

        Args:
            table: Table name
            columns: Columns to select (default "*")
            filters: Filter conditions (e.g., {"status": "active"})
            order_by: Column to order by
            limit: Maximum number of rows to return

        Returns:
            List of matching rows
        """
        query = self.client.table(table).select(columns)

        if filters:
            for key, value in filters.items():
                query = query.eq(key, value)

        if order_by:
            parts = order_by.strip().split()
            column = parts[0]
            desc = len(parts) > 1 and parts[1].lower() == "desc"
            query = query.order(column, desc=desc)

        if limit:
            query = query.limit(limit)

        result = query.execute()
        return self._normalize_rows(result.data)

    def update(self, table: str, filters: dict[str, Any], data: dict[str, Any]) -> list[Row]:
        """
        Update rows in a table.

        Args:
            table: Table name
            filters: Filter conditions to identify rows to update
            data: Data to update

        Returns:
            List of updated rows
        """
        query = self.client.table(table).update(data)

        for key, value in filters.items():
            query = query.eq(key, value)

        result = query.execute()
        return self._normalize_rows(result.data)

    def delete(self, table: str, filters: dict[str, Any]) -> list[Row]:
        """
        Delete rows from a table.

        Args:
            table: Table name
            filters: Filter conditions to identify rows to delete

        Returns:
            List of deleted rows
        """
        query = self.client.table(table).delete()

        for key, value in filters.items():
            query = query.eq(key, value)

        result = query.execute()
        return self._normalize_rows(result.data)

    def get_by_id(self, table: str, id_column: str, id_value: str) -> Row | None:
        """
        Get a single row by ID.

        Args:
            table: Table name
            id_column: Name of ID column
            id_value: ID value to search for

        Returns:
            Row data if found, None otherwise
        """
        result = self.client.table(table).select("*").eq(id_column, id_value).execute()

        if result.data and len(result.data) > 0:
            rows = self._normalize_rows(result.data)
            if rows:
                return rows[0]
        return None

    def close(self) -> None:
        """
        Close the Supabase client connection.

        Note: The Supabase Python client doesn't require explicit closing,
        but this method is provided for consistency.
        """
        self._client = None

    # Domain-specific methods for deployment orchestration

    def get_deployment(self, deployment_id: str) -> Row | None:
        """
        Get a deployment by ID.

        Args:
            deployment_id: Deployment identifier

        Returns:
            Deployment record if found, None otherwise
        """
        return self.get_by_id("deployments", "deployment_id", deployment_id)

    def insert_receipt(
        self,
        deployment_id: str,
        platform: str,
        operation: str,
        remote_id: str,
        status: str,
        response_data: dict[str, Any],
        proposed_action_id: str | None = None,
    ) -> Row:
        """
        Insert a receipt record.

        If proposed_action_id is provided, writes to external_request_attempts
        and external_receipts tables. Otherwise logs only (legacy path).
        """
        import logging
        from datetime import datetime

        logger = logging.getLogger(__name__)
        logger.info(f"Receipt: {platform}/{operation} -> {remote_id} ({status})")

        if not proposed_action_id:
            return {
                "deployment_id": deployment_id,
                "platform": platform,
                "operation": operation,
                "remote_id": remote_id,
                "status": status,
            }

        now = datetime.now(UTC).isoformat()
        outcome = "success" if status == "success" else "failure"

        try:
            attempt = self.insert(
                "external_request_attempts",
                {
                    "proposed_action_id": proposed_action_id,
                    "attempt_number": 1,
                    "request_hash": hash_json({"platform": platform, "operation": operation}),
                    "started_at": now,
                    "finished_at": now,
                    "outcome": outcome,
                    "failure_class": None if outcome == "success" else "permanent",
                },
            )

            if outcome == "success" and attempt.get("attempt_id"):
                self.insert(
                    "external_receipts",
                    {
                        "proposed_action_id": proposed_action_id,
                        "attempt_id": attempt["attempt_id"],
                        "platform": platform,
                        "operation": operation,
                        "remote_resource_id": remote_id,
                        "receipt_hash": hash_json(response_data or {}),
                    },
                )

            return attempt
        except Exception as e:
            logger.warning(f"Failed to persist receipt to DB: {e}")
            return {
                "deployment_id": deployment_id,
                "platform": platform,
                "operation": operation,
                "remote_id": remote_id,
                "status": status,
            }

    def upsert_external_resource(
        self,
        deployment_id: str,
        platform: str,
        resource_type: str,
        remote_id: str,
        organization_id: str | None,
        current_state_hash: str,
    ) -> Row:
        """
        Upsert an external resource record.

        Args:
            platform: Platform name
            resource_type: Resource type
            remote_id: Remote resource ID
            organization_id: Organization identifier
            current_state_hash: Hash of current state

        Returns:
            Upserted resource record
        """
        deployment = self.get_deployment(deployment_id)
        resolved_organization_id = organization_id or (
            deployment.get("organization_id") if deployment else None
        )
        if not resolved_organization_id:
            raise ValueError("organization_id is required to register an external resource")

        platform_map = {"render": "hosting"}
        resource_type_map = {
            "assistant": "vapi_assistant",
            "tool": "vapi_tool",
            "phone_number": "vapi_phone_number",
            "scenario": "make_scenario",
            "hook": "make_hook",
            "org_record": "supabase_organization_row",
            "migration": "supabase_migration",
            "service": "hosting_service",
            "deploy": "hosting_deployment",
        }
        mapped_resource_type = resource_type_map.get(resource_type, resource_type)
        data = {
            "organization_id": resolved_organization_id,
            "created_by_deployment_id": deployment_id,
            "platform": platform_map.get(platform, platform),
            "resource_type": mapped_resource_type,
            "remote_resource_id": remote_id,
            "last_observed_hash": current_state_hash,
        }

        # Use upsert if available, otherwise try update then insert
        try:
            result = (
                self.client.table("external_resources")
                .upsert(data, on_conflict="platform,resource_type,remote_resource_id")
                .execute()
            )
            if result.data:
                rows = self._normalize_rows(result.data)
                if rows:
                    return rows[0]
        except Exception:
            pass

        # Fallback: try insert
        return self.insert("external_resources", data)

    def append_audit_event(
        self,
        deployment_id: str,
        event_type: str,
        status: str,
        subject: str,
        detail: dict[str, Any],
        session_id: str | None = None,
    ) -> Row:
        """
        Append an audit event.

        If session_id is provided, writes to the audit_events table.
        Otherwise logs only (legacy path).
        """
        import logging

        logger = logging.getLogger(__name__)
        logger.info(f"Audit: {event_type} {status} subject={subject}")

        if not session_id:
            return {
                "deployment_id": deployment_id,
                "event_type": event_type,
                "status": status,
                "subject": str(subject),
            }

        event_hash = hash_json(
            {
                "deployment_id": deployment_id,
                "event_type": event_type,
                "status": status,
                "subject": str(subject),
                "detail": detail,
            }
        )

        try:
            return self.insert(
                "audit_events",
                {
                    "deployment_id": deployment_id,
                    "session_id": session_id,
                    "event_type": event_type,
                    "actor_type": "orchestrator",
                    "actor_id": "system",
                    "subject_type": "deployment",
                    "subject_id": str(subject),
                    "status": status,
                    "summary": f"{event_type}: {status}",
                    "detail": detail if isinstance(detail, dict) else {"info": str(detail)},
                    "event_hash": event_hash,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to persist audit event to DB: {e}")
            return {
                "deployment_id": deployment_id,
                "event_type": event_type,
                "status": status,
                "subject": str(subject),
            }

    def update_deployment_status(self, deployment_id: str, status: str) -> list[Row]:
        """
        Update deployment status.

        Automatically sets completed_at timestamp for terminal states
        (complete, failed, aborted) to satisfy the database constraint.

        Args:
            deployment_id: Deployment identifier
            status: New status

        Returns:
            Updated deployment record
        """
        from datetime import UTC, datetime

        # Terminal states require completed_at to be set
        terminal_states = ["complete", "failed", "aborted"]

        update_data = {"status": status}
        if status in terminal_states:
            update_data["completed_at"] = datetime.now(UTC).isoformat()

        return self.update(
            "deployments",
            {"deployment_id": deployment_id},
            update_data,
        )

    def terminate_preplan_deployment(self, deployment_id: str, failure_summary: str) -> list[Row]:
        """Terminate an orphaned deployment that never persisted a plan.

        This is intentionally limited to the ``planning`` state with no plan
        hash, so it cannot be used to bypass normal recovery for deployments
        that reached plan approval or external execution.
        """
        deployment = self.get_deployment(deployment_id)
        if not deployment:
            raise ValueError(f"Deployment not found: {deployment_id}")
        if deployment.get("status") != "planning" or deployment.get("plan_hash"):
            raise ValueError(
                "Only planning deployments without a plan_hash may use pre-plan termination"
            )

        return self.update(
            "deployments",
            {"deployment_id": deployment_id},
            {
                "status": "failed",
                "failure_class": "local_persistence_failure",
                "failure_summary": failure_summary,
                "completed_at": datetime.now().astimezone().isoformat(),
            },
        )

    def terminate_stale_planning_deployment(
        self, deployment_id: str, failure_summary: str
    ) -> list[Row]:
        """Terminate a planning deployment that made no external changes."""
        deployment = self.get_deployment(deployment_id)
        if not deployment:
            raise ValueError(f"Deployment not found: {deployment_id}")
        if deployment.get("status") != "planning":
            raise ValueError("Only planning deployments may use stale-planning termination")

        resources = self.select(
            "external_resources",
            filters={"created_by_deployment_id": deployment_id},
        )
        if resources:
            raise ValueError("Planning deployment has external resources and requires recovery")

        return self.update(
            "deployments",
            {"deployment_id": deployment_id},
            {
                "status": "failed",
                "failure_class": "local_persistence_failure",
                "failure_summary": failure_summary,
                "completed_at": datetime.now().astimezone().isoformat(),
            },
        )

    def insert_approval_decision(
        self,
        deployment_id: str,
        proposal_hash: str,
        decision: str,
        display_hash: str,
        decided_by: str,
        decided_at: str | datetime,
        notes: str | None = None,
    ) -> Row:
        """
        Insert an approval decision.

        Args:
            deployment_id: Deployment identifier
            proposal_hash: Hash of the proposal
            decision: Decision made
            display_hash: Hash of the display content
            decided_by: Operator who made the decision
            decided_at: Timestamp of decision
            notes: Optional notes

        Returns:
            Inserted approval decision record
        """
        return self.insert(
            "approval_decisions",
            {
                "deployment_id": deployment_id,
                "proposal_hash": proposal_hash,
                "decision": decision,
                "display_hash": display_hash,
                "decided_by": decided_by,
                # Keep the canonical schema fields populated as well as the
                # deployment-scoped compatibility fields used by the
                # orchestrator's approval audit trail.
                "operator_id": decided_by,
                "decided_at": decided_at.isoformat()
                if isinstance(decided_at, datetime)
                else decided_at,
                "notes": notes,
                "revision_instruction": notes,
            },
        )

    def create_deployment(
        self,
        deployment: dict[str, Any] | None = None,
        **fields: Any,
    ) -> Row:
        """Create a deployment record from either a mapping or keyword fields."""
        payload = dict(deployment or {})
        payload.update(fields)
        return self.insert("deployments", payload)

    def get_latest_deployment(self, organization_id: str) -> Row | None:
        """Get the most recently created deployment for an organization."""
        deployments = self.select(
            "deployments",
            filters={"organization_id": organization_id},
            order_by="created_at desc",
            limit=1,
        )
        return deployments[0] if deployments else None

    def get_active_deployments(self, organization_id: str) -> list[Row]:
        """Get non-terminal deployments for an organization."""
        terminal_states = {"complete", "completed", "failed", "aborted"}
        deployments = self.select(
            "deployments",
            filters={"organization_id": organization_id},
            order_by="created_at desc",
        )
        return [
            row for row in deployments if str(row.get("status", "")).lower() not in terminal_states
        ]

    def get_deployments_for_organization(self, organization_id: str) -> list[Row]:
        """Get all deployments for an organization."""
        return self.select(
            "deployments",
            filters={"organization_id": organization_id},
            order_by="created_at desc",
        )

    def get_external_resources(self, deployment_or_organization_id: str) -> list[Row]:
        """Get external resources by deployment ID first, then by organization ID."""
        by_deployment = self.select(
            "external_resources",
            filters={"created_by_deployment_id": deployment_or_organization_id},
        )
        if by_deployment:
            return by_deployment
        return self.select(
            "external_resources",
            filters={"organization_id": deployment_or_organization_id},
        )

    def get_task_executions(self, deployment_id: str) -> list[Row]:
        return self.select(
            "task_executions", filters={"deployment_id": deployment_id}, order_by="created_at"
        )

    def get_proposed_actions(self, deployment_id: str) -> list[Row]:
        return self.select(
            "proposed_actions", filters={"deployment_id": deployment_id}, order_by="created_at"
        )

    def get_approval_decisions(self, deployment_id: str) -> list[Row]:
        """Get approval decisions for a deployment by joining through proposed_actions."""
        # First get all proposed_action_ids for this deployment
        actions = self.select("proposed_actions", filters={"deployment_id": deployment_id})
        if not actions:
            return []

        action_ids = [action["proposed_action_id"] for action in actions]

        # Then get approval decisions for those actions
        all_decisions = []
        for action_id in action_ids:
            decisions = self.select("approval_decisions", filters={"proposed_action_id": action_id})
            all_decisions.extend(decisions)

        # Sort by decided_at
        all_decisions.sort(key=lambda x: x.get("decided_at", ""))
        return all_decisions

    def get_external_attempts(self, deployment_id: str) -> list[Row]:
        """Get external request attempts for a deployment by joining through proposed_actions."""
        actions = self.select("proposed_actions", filters={"deployment_id": deployment_id})
        if not actions:
            return []

        action_ids = [action["proposed_action_id"] for action in actions]
        all_attempts = []
        for action_id in action_ids:
            attempts = self.select(
                "external_request_attempts", filters={"proposed_action_id": action_id}
            )
            all_attempts.extend(attempts)

        all_attempts.sort(key=lambda x: x.get("created_at", ""))
        return all_attempts

    def get_external_receipts(self, deployment_id: str) -> list[Row]:
        """Get external receipts for a deployment by joining through proposed_actions."""
        actions = self.select("proposed_actions", filters={"deployment_id": deployment_id})
        if not actions:
            return []

        action_ids = [action["proposed_action_id"] for action in actions]
        all_receipts = []
        for action_id in action_ids:
            receipts = self.select("external_receipts", filters={"proposed_action_id": action_id})
            all_receipts.extend(receipts)

        all_receipts.sort(key=lambda x: x.get("created_at", ""))
        return all_receipts

    def get_recovery_actions(self, deployment_id: str) -> list[Row]:
        return self.select(
            "recovery_actions", filters={"deployment_id": deployment_id}, order_by="created_at"
        )

    def get_audit_events(self, deployment_id: str) -> list[Row]:
        return self.select(
            "audit_events", filters={"deployment_id": deployment_id}, order_by="created_at"
        )

    def get_last_audit_event(self, deployment_id: str) -> Row | None:
        events = self.select(
            "audit_events",
            filters={"deployment_id": deployment_id},
            order_by="created_at desc",
            limit=1,
        )
        return events[0] if events else None

    def insert_audit_event(self, event: dict[str, Any]) -> str:
        inserted = self.insert("audit_events", event)
        event_id = inserted.get("id") or inserted.get("event_id")
        return str(event_id) if event_id is not None else ""

    def insert_intake(
        self,
        organization_id: str,
        intake_data: dict[str, Any],
        intake_hash: str,
        approved_by: str,
        version: int = 1,
    ) -> Row:
        """
        Insert an organization intake record.

        Args:
            organization_id: Organization identifier
            intake_data: Validated intake dictionary
            intake_hash: SHA-256 hash of intake
            approved_by: Operator who approved the intake
            version: Intake version number (default 1)

        Returns:
            Inserted intake record with intake_id
        """
        from datetime import datetime

        record = {
            "organization_id": organization_id,
            "version": version,
            "business_name": intake_data["business_name"],
            "phone_number": intake_data["phone_number"],
            "voice_id": intake_data["voice_id"],
            "timezone": intake_data["timezone"],
            "business_hours": intake_data["business_hours"],
            "services_offered": intake_data["services_offered"],
            "enabled_capabilities": intake_data["enabled_capabilities"],
            "external_identifiers": intake_data.get("external_identifiers", {}),
            "intake_hash": intake_hash,
            "approved_by": approved_by,
            "approved_at": datetime.now(UTC).isoformat(),
        }

        # Optional fields
        if "booking_calendar_id" in intake_data:
            record["booking_calendar_id"] = intake_data["booking_calendar_id"]
        if "cancellation_window_hours" in intake_data:
            record["cancellation_window_hours"] = intake_data["cancellation_window_hours"]
        if "rescheduling_policy" in intake_data:
            record["rescheduling_policy"] = intake_data["rescheduling_policy"]
        if "transfer_destination" in intake_data:
            record["transfer_destination"] = intake_data["transfer_destination"]

        return self.insert("organization_intakes", record)
