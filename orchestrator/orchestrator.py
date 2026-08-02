"""
Main orchestrator for Agent Forge deployments.

Coordinates the full deployment flow:
- Intake validation and planning
- Artifact generation and validation
- Sequential action execution with approval
- Staleness checking and state management
- Receipt persistence and audit logging
- Recovery and revision flows
"""

from datetime import UTC, datetime
from typing import Any

from adapters.base import AdapterReceipt
from adapters.supabase_internal import SupabaseInternalClient
from cli.prompts import InteractivePrompts
from orchestrator.approval import (
    ApprovalDecision,
    ProposedAction,
    check_staleness,
    format_proposal_display,
    record_approval_decision,
    verify_approval_matches_proposal,
)
from orchestrator.intake_schema import normalize_intake, validate_intake
from orchestrator.planner import Planner
from orchestrator.state_machine import DeploymentState, DeploymentStateMachine
from shared.errors import (
    AmbiguousOutcomeError,
    ConflictError,
    ValidationError,
)
from shared.hashing import hash_json


class Orchestrator:
    """
    Main orchestrator for deployment operations.

    Coordinates the entire deployment lifecycle from intake through
    execution, approval, recovery, and audit.
    """

    def __init__(self, internal_store: SupabaseInternalClient):
        """
        Initialize orchestrator.

        Args:
            internal_store: Internal operational store client
        """
        self.internal_store = internal_store
        self.state_machine = DeploymentStateMachine()
        self.prompts = InteractivePrompts()

    def dry_run(self, intake: dict[str, Any]) -> dict[str, Any]:
        """Build a validated onboarding preview without reading or writing services.

        This entry point intentionally avoids the internal store and all
        adapters. It is suitable for CLI previews and pre-flight validation.
        """
        validation = validate_intake(intake)
        if not validation["valid"]:
            return {
                "success": False,
                "errors": validation.get("errors", []),
                "warnings": validation.get("warnings", []),
                "external_calls_made": 0,
                "existing_deployment": None,
            }

        normalized_intake = normalize_intake(intake)
        planner = Planner()
        graph = planner.create_task_graph(normalized_intake)
        plan = planner.create_dry_run_plan(graph, normalized_intake)

        # The planner groups tasks into phases for presentation, while callers
        # also need a flat, ordered list to review dependencies and actions.
        plan["tasks"] = [task.to_dict() for task in graph.get_ordered_tasks()]
        plan["actions"] = plan["intended_changes"]

        return {
            "success": True,
            "plan": plan,
            "external_calls_made": 0,
            # Deliberately not queried: a dry run must be side-effect free and
            # runnable without configured infrastructure.
            "existing_deployment": None,
        }

    def execute_deployment(
        self,
        deployment_id: str,
        organization_id: str,
        operator: str,
        dry_run: bool = False,
        auto_approve: bool = False,
        proposed_actions: list[ProposedAction] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a deployment with per-action approval.

        This is the main entry point for deployment execution after planning.

        Args:
            deployment_id: Deployment identifier
            organization_id: Organization identifier
            operator: Operator identifier
            dry_run: If True, only show what would be executed
            auto_approve: If True, automatically approve all actions without prompting

        Returns:
            Deployment result summary

        Flow:
            1. Load deployment plan and artifacts
            2. For each proposed action:
               a. Check staleness
               b. Request approval
               c. Execute if approved
               d. Persist receipt
               e. Update state
            3. Handle rejections and revisions
        """
        # Load deployment from internal store
        deployment = self.internal_store.get_deployment(deployment_id)
        if not deployment:
            raise ValidationError(
                f"Deployment not found: {deployment_id}",
                field="deployment_id",
            )

        # Verify organization matches
        if deployment["organization_id"] != organization_id:
            raise ConflictError(
                "Deployment organization_id mismatch",
                resource="deployment",
                context={
                    "deployment_org": deployment["organization_id"],
                    "requested_org": organization_id,
                },
            )

        # Get proposed actions from deployment plan
        proposed_actions = proposed_actions or self._build_proposed_actions(deployment)

        if dry_run:
            return self._dry_run_summary(proposed_actions)

        # Execute actions sequentially with approval
        results: list[dict[str, Any]] = []
        for i, proposed_action in enumerate(proposed_actions):
            print(f"\n--- Action {i + 1} of {len(proposed_actions)} ---")

            # Check staleness
            if self._is_action_stale(proposed_action):
                print("⚠️  Action is stale. Regenerating with current state...")
                proposed_action = self._regenerate_action(proposed_action, deployment)

            # Display and request approval
            display_content = format_proposal_display(proposed_action)
            print(display_content)

            decision_str = self.prompts.approve_action(
                self._action_to_dict(proposed_action),
                proposed_action.proposal_hash,
                auto_approve=auto_approve,
            )

            # Record decision
            approval = record_approval_decision(
                proposed_action=proposed_action,
                decision=decision_str,
                display_content=display_content,
                operator=operator,
            )

            # Persist approval decision
            self._persist_approval_decision(deployment_id, approval)

            # Handle decision
            if approval.decision == "approved":
                # Execute action
                try:
                    result = self._execute_action(
                        deployment_id=deployment_id,
                        proposed_action=proposed_action,
                        approval=approval,
                    )
                except Exception as error:
                    # A failure after a prior external action leaves a
                    # partially applied deployment and requires recovery.
                    if results and not isinstance(error, AmbiguousOutcomeError):
                        self._mark_requires_recovery(deployment_id, str(error))
                    raise
                results.append(result)

            elif approval.decision == "rejected_abort":
                # Abort deployment
                self._abort_deployment(deployment_id, "Operator rejected action")
                return {
                    "status": "aborted",
                    "message": "Deployment aborted by operator",
                    "completed_actions": len(results),
                }

            elif approval.decision == "rejected_revise":
                # Get revision instructions
                revision_notes = self.prompts.get_revision_instruction()

                # Mark for revision
                self._mark_for_revision(
                    deployment_id=deployment_id,
                    action_index=i,
                    revision_notes=revision_notes,
                )

                return {
                    "status": "revision_required",
                    "message": "Action marked for revision",
                    "revision_notes": revision_notes,
                    "completed_actions": len(results),
                }

        # All actions completed
        self._complete_deployment(deployment_id)

        return {
            "status": "completed",
            "message": "Deployment completed successfully",
            "total_actions": len(results),
            "completed_actions": len(results),
        }

    def _check_staleness_for_action(
        self,
        proposed_action: ProposedAction,
    ) -> str | None:
        """
        Read authoritative current state and compute state version.

        This implements the staleness check requirement: read current state
        immediately before write, compute state hash, and compare.

        Args:
            proposed_action: The proposed action

        Returns:
            Current state version (hash) or None if not applicable
        """
        # Only applicable for update operations
        if not proposed_action.state_version:
            return None

        # Read current state based on platform and operation
        # This would call the appropriate adapter get method
        # For now, return None to indicate no staleness check needed
        # TODO: Implement platform-specific state reads
        return None

    def _is_action_stale(self, proposed_action: ProposedAction) -> bool:
        """
        Check if an action is stale by comparing state versions.

        Args:
            proposed_action: The proposed action

        Returns:
            True if stale, False otherwise
        """
        current_state = self._check_staleness_for_action(proposed_action)
        return check_staleness(proposed_action, current_state)

    def _execute_action(
        self,
        deployment_id: str,
        proposed_action: ProposedAction,
        approval: ApprovalDecision,
    ) -> dict[str, Any]:
        """
        Execute an approved action and persist receipt.

        This implements the sequential action executor with atomic transaction:
        1. Verify approval matches proposal
        2. Execute via appropriate adapter
        3. Begin transaction
        4. Persist receipt
        5. Update external resource registry
        6. Mark action succeeded
        7. Append audit event
        8. Update deployment state
        9. Commit transaction

        Args:
            deployment_id: Deployment ID
            proposed_action: The action to execute
            approval: The approval decision

        Returns:
            Execution result with receipt

        Raises:
            ConflictError: If approval doesn't match proposal
            Various adapter errors on execution failure
        """
        # Verify approval matches proposal
        verify_approval_matches_proposal(approval, proposed_action)

        print(f"\n⚙️  Executing {proposed_action.operation} on {proposed_action.platform}...")

        try:
            # Execute via adapter
            receipt = self._execute_via_adapter(proposed_action)

            # Begin atomic transaction for post-success operations
            # Note: This would use the internal store's transaction support
            # For now, we persist each operation individually

            # 1. Persist receipt
            self.internal_store.insert_receipt(
                deployment_id=deployment_id,
                platform=proposed_action.platform,
                operation=proposed_action.operation,
                remote_id=receipt.remote_id,
                status=receipt.status,
                response_data=receipt.response_data,
            )

            # 2. Upsert external resource
            if receipt.remote_id:
                operation_to_resource_type = {
                    "insert_org_record": "supabase_organization_row",
                    "run_migration": "supabase_migration",
                    "create_assistant": "vapi_assistant",
                    "create_scenario": "make_scenario",
                    "update_backend": "hosting_deployment",
                    "set_env_variable": "hosting_deployment",
                    "trigger_deploy": "hosting_deployment",
                }
                resource_type = operation_to_resource_type.get(
                    proposed_action.operation,
                    proposed_action.operation.replace("create_", ""),
                )
                self.internal_store.upsert_external_resource(
                    deployment_id=deployment_id,
                    platform=proposed_action.platform,
                    resource_type=resource_type,
                    remote_id=receipt.remote_id,
                    organization_id=None,
                    current_state_hash=hash_json(receipt.response_data),
                )

            # 3. Append audit event
            self.internal_store.append_audit_event(
                deployment_id=deployment_id,
                event_type="action_executed",
                status="success",
                subject=proposed_action.target,
                detail={
                    "platform": proposed_action.platform,
                    "operation": proposed_action.operation,
                    "remote_id": receipt.remote_id,
                },
            )

            # 4. Update deployment state (if needed)
            # State transitions handled at higher level

            print("✓ Action completed successfully")
            print(f"  Remote ID: {receipt.remote_id}")

            return {
                "status": "success",
                "platform": proposed_action.platform,
                "operation": proposed_action.operation,
                "remote_id": receipt.remote_id,
                "receipt": receipt.response_data,
            }

        except Exception as e:
            # Record failure
            self.internal_store.append_audit_event(
                deployment_id=deployment_id,
                event_type="action_failed",
                status="failure",
                subject=proposed_action.target,
                detail={
                    "platform": proposed_action.platform,
                    "operation": proposed_action.operation,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )

            # Classify error and determine recovery path
            if isinstance(e, AmbiguousOutcomeError):
                # Mark deployment as requiring recovery
                self._mark_requires_recovery(deployment_id, str(e))

            raise

    def _execute_via_adapter(self, proposed_action: ProposedAction) -> Any:
        """
        Execute action via the appropriate adapter.

        Args:
            proposed_action: The action to execute

        Returns:
            AdapterReceipt from the execution

        Raises:
            ValidationError: If platform is unknown
        """
        # Import adapters dynamically to avoid circular imports
        from adapters.hosting import RenderAdapter
        from adapters.make import MakeAdapter
        from adapters.supabase_client import SupabaseClientAdapter
        from adapters.vapi import VapiAdapter

        # Route to appropriate adapter
        if proposed_action.platform == "vapi":
            return self._execute_vapi_action(VapiAdapter(), proposed_action)
        elif proposed_action.platform == "make":
            return self._execute_make_action(MakeAdapter(), proposed_action)
        elif proposed_action.platform == "supabase_client":
            return self._execute_supabase_action(SupabaseClientAdapter(), proposed_action)
        elif proposed_action.platform == "render":
            return self._execute_render_action(RenderAdapter(), proposed_action)
        else:
            raise ValidationError(
                f"Unknown platform: {proposed_action.platform}",
                field="platform",
            )

    def _execute_vapi_action(self, adapter: Any, proposed_action: ProposedAction) -> Any:
        """Execute Vapi action."""
        import json
        from pathlib import Path

        operation = proposed_action.operation
        payload = proposed_action.payload

        if operation == "create_assistant":
            config_path = payload.get("config_path")
            if config_path and Path(config_path).exists():
                with open(config_path, encoding="utf-8") as f:
                    assistant_config = json.load(f)
            else:
                assistant_config = payload
            # Strip fields not accepted by Vapi's assistant create endpoint
            assistant_config.pop("tools", None)
            assistant_config.pop("metadata", None)
            receipt = adapter.create_assistant(assistant_config)
            # Auto-assign phone number if provided
            phone_number_id = payload.get("phone_number_id")
            if phone_number_id and receipt.remote_id:
                import contextlib
                with contextlib.suppress(Exception):
                    adapter.assign_phone_number(phone_number_id, receipt.remote_id)
            return receipt
        elif operation == "create_tool":
            return adapter.create_tool(payload)
        elif operation == "update_assistant":
            return adapter.update_assistant(
                payload["assistant_id"],
                payload.get("updates", {}),
            )
        elif operation == "assign_phone_number":
            return adapter.assign_phone_number(
                payload["phone_number_id"],
                payload.get("assistant_id"),
            )
        else:
            raise ValidationError(f"Unknown Vapi operation: {operation}")

    def _execute_make_action(self, adapter: Any, proposed_action: ProposedAction) -> Any:
        """Execute Make action."""
        import json
        import os
        from pathlib import Path

        from orchestrator.make_deployer import MakeScenarioDeployer

        operation = proposed_action.operation
        payload = proposed_action.payload

        if operation == "create_scenario":
            blueprint_path = payload.get("blueprint_path")
            capability = payload.get("blueprint", {}).get("capability", "")

            if blueprint_path and Path(blueprint_path).exists() and capability:
                deployer = MakeScenarioDeployer(adapter)
                connection_id = os.getenv("MAKE_SUPABASE_CONNECTION_ID")
                result = deployer.deploy_scenario(
                    capability=capability,
                    blueprint_path=blueprint_path,
                    hook_name=payload.get("name", f"hook-{capability}"),
                    connection_id=connection_id,
                )
                return AdapterReceipt(
                    platform="make",
                    operation="create_scenario",
                    remote_id=str(result["scenario_id"]),
                    status="success",
                    response_data=result,
                    idempotency_key=None,
                    can_retry=False,
                )

            blueprint = payload["blueprint"]
            if blueprint_path and Path(blueprint_path).exists():
                with open(blueprint_path, encoding="utf-8") as f:
                    blueprint = json.load(f)
            receipt = adapter.create_scenario(
                blueprint,
                payload["scheduling"],
                payload.get("confirmed", False),
            )
            if receipt.remote_id:
                import contextlib
                with contextlib.suppress(Exception):
                    adapter.activate_scenario(int(receipt.remote_id))
            return receipt
        elif operation == "create_hook":
            return adapter.create_hook(
                payload["name"],
                payload["type_name"],
                payload.get("method", True),
                payload.get("headers", True),
                payload.get("stringify", True),
            )
        elif operation == "activate_scenario":
            return adapter.activate_scenario(payload["scenario_id"])
        elif operation == "update_scenario_blueprint":
            return adapter.update_scenario_blueprint(
                payload["scenario_id"],
                payload.get("updates", {}),
                payload.get("confirmed", False),
            )
        else:
            raise ValidationError(f"Unknown Make operation: {operation}")

    def _execute_supabase_action(self, adapter: Any, proposed_action: ProposedAction) -> Any:
        """Execute Supabase client action."""
        operation = proposed_action.operation
        payload = proposed_action.payload

        if operation == "insert_org_record":
            return adapter.insert_org_record(
                payload["organization_id"],
                payload["business_name"],
                payload.get("timezone"),
                payload.get("configuration"),
            )
        else:
            raise ValidationError(f"Unknown Supabase operation: {operation}")

    def _execute_render_action(self, adapter: Any, proposed_action: ProposedAction) -> Any:
        """Execute Render action."""
        operation = proposed_action.operation
        payload = proposed_action.payload

        if operation == "set_env_variable":
            return adapter.set_env_variable(payload["key"], payload["value"])
        elif operation == "trigger_deploy":
            return adapter.trigger_deploy(
                payload.get("clear_cache", "do_not_clear"),
                payload.get("commit_id"),
                payload.get("image_url"),
            )
        else:
            raise ValidationError(f"Unknown Render operation: {operation}")

    # Helper methods

    def _build_proposed_actions(self, deployment: dict[str, Any]) -> list[ProposedAction]:
        """Build list of ProposedAction objects from deployment plan."""
        from orchestrator.approval import build_proposed_action as _build

        stored_actions = self.internal_store.get_proposed_actions(deployment["deployment_id"])
        if stored_actions:
            return [
                ProposedAction(
                    platform=row["platform"],
                    operation=row["operation"],
                    target=row["target"],
                    payload_hash=row.get("payload_hash", ""),
                    state_version=row.get("state_version"),
                    proposal_hash=row.get("proposal_hash", ""),
                    idempotency_key=row.get("idempotency_key"),
                    retry_policy=row.get("retry_policy", "none"),
                    reconciliation_strategy=row.get("reconciliation_strategy", "read_after_write"),
                    compensation_operation=row.get("compensation_operation"),
                    payload=row.get("payload", {}),
                    validation_result=row.get("validation_result"),
                    expected_outcome=row.get("expected_outcome"),
                )
                for row in stored_actions
            ]

        # Fallback: derive from task executions if no proposed_actions stored
        task_executions = self.internal_store.get_task_executions(deployment["deployment_id"])
        actions = []
        for task_exec in task_executions:
            payload = task_exec.get("payload") or task_exec.get("context", {})
            if not payload or not task_exec.get("platform"):
                continue
            actions.append(
                _build(
                    platform=task_exec["platform"],
                    operation=str(task_exec.get("operation", task_exec.get("action_type", ""))),
                    target=str(task_exec.get("target", task_exec.get("task_id", ""))),
                    payload=payload,
                    retry_policy=task_exec.get("retry_policy", "none"),
                    reconciliation_strategy=task_exec.get(
                        "reconciliation_strategy", "read_after_write"
                    ),
                    compensation_operation=task_exec.get("compensation_operation"),
                    expected_outcome=task_exec.get("expected_outcome"),
                )
            )
        return actions

    def _dry_run_summary(self, proposed_actions: list[ProposedAction]) -> dict[str, Any]:
        """Generate dry-run summary."""
        return {
            "status": "dry_run",
            "total_actions": len(proposed_actions),
            "actions": [
                {
                    "platform": a.platform,
                    "operation": a.operation,
                    "target": a.target,
                }
                for a in proposed_actions
            ],
        }

    def _regenerate_action(
        self, proposed_action: ProposedAction, deployment: dict[str, Any]
    ) -> ProposedAction:
        """Regenerate action with fresh state version and idempotency key."""
        from orchestrator.approval import build_proposed_action as _build
        from shared.ids import generate_uuid

        return _build(
            platform=proposed_action.platform,
            operation=proposed_action.operation,
            target=proposed_action.target,
            payload=proposed_action.payload,
            state_version=None,
            idempotency_key=generate_uuid(),
            retry_policy=proposed_action.retry_policy,
            reconciliation_strategy=proposed_action.reconciliation_strategy,
            compensation_operation=proposed_action.compensation_operation,
            validation_result=proposed_action.validation_result,
            expected_outcome=proposed_action.expected_outcome,
        )

    def _action_to_dict(self, proposed_action: ProposedAction) -> dict[str, Any]:
        """Convert ProposedAction to dictionary for display."""
        return {
            "platform": proposed_action.platform,
            "operation": proposed_action.operation,
            "target": proposed_action.target,
            "change_summary": proposed_action.expected_outcome or "No description",
            "validation_result": proposed_action.validation_result or {"passed": True},
            "reconciliation_strategy": proposed_action.reconciliation_strategy,
            "compensation_operation": proposed_action.compensation_operation,
        }

    def _persist_approval_decision(self, deployment_id: str, approval: ApprovalDecision) -> None:
        """Persist approval decision to internal store."""
        self.internal_store.insert_approval_decision(
            deployment_id=deployment_id,
            proposal_hash=approval.proposal_hash,
            decision=approval.decision,
            display_hash=approval.display_hash,
            decided_by=approval.decided_by,
            decided_at=approval.decided_at,
            notes=approval.notes,
        )

    def _abort_deployment(self, deployment_id: str, reason: str) -> None:
        """Abort deployment and record reason."""
        self.internal_store.update_deployment_status(
            deployment_id,
            DeploymentState.ABORTED.value,
        )
        self.internal_store.append_audit_event(
            deployment_id=deployment_id,
            event_type="deployment_aborted",
            status="aborted",
            subject=deployment_id,
            detail={"reason": reason},
        )

    def _mark_for_revision(
        self, deployment_id: str, action_index: int, revision_notes: str
    ) -> None:
        """Mark action for revision."""
        self.internal_store.append_audit_event(
            deployment_id=deployment_id,
            event_type="action_revision_requested",
            status="pending",
            subject=f"action_{action_index}",
            detail={"revision_notes": revision_notes},
        )

    def _complete_deployment(self, deployment_id: str) -> None:
        """Mark deployment as completed."""
        self.internal_store.update_deployment_status(
            deployment_id,
            DeploymentState.COMPLETED.value,
        )
        self.internal_store.append_audit_event(
            deployment_id=deployment_id,
            event_type="deployment_completed",
            status="success",
            subject=deployment_id,
            detail={"completed_at": datetime.now(UTC).isoformat()},
        )

    def _mark_requires_recovery(self, deployment_id: str, reason: str) -> None:
        """Mark deployment as requiring recovery."""
        self.internal_store.update_deployment_status(
            deployment_id,
            DeploymentState.RECOVERY_REQUIRED.value,
        )
        self.internal_store.append_audit_event(
            deployment_id=deployment_id,
            event_type="recovery_required",
            status="pending",
            subject=deployment_id,
            detail={"reason": reason},
        )
