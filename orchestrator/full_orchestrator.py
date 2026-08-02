"""
Full orchestrator onboard flow connecting US1→US2→US3→US4.

Implements T155: Complete deployment orchestration from intake through
execution, with state transitions and recovery.
"""

from datetime import UTC, datetime
from typing import Any

from adapters.supabase_internal import SupabaseInternalClient
from agents.make_agent.agent import MakeAgent
from agents.nodejs_agent.agent import NodeJsAgent
from agents.supabase_agent.agent import SupabaseAgent
from agents.vapi_agent.agent import VapiAgent
from cli.prompts import InteractivePrompts
from orchestrator.approval import (
    ProposedAction,
    build_proposed_action,
    check_staleness,
    format_proposal_display,
    record_approval_decision,
)
from orchestrator.assembler import DeploymentPackage, PackageAssembler
from orchestrator.audit import (
    AuditEventType,
    AuditEventWriter,
    record_action_execution,
    record_deployment_created,
    record_state_transition,
)
from orchestrator.audit import (
    record_approval_decision as record_audit_approval,
)
from orchestrator.intake_schema import normalize_intake, validate_intake
from orchestrator.planner import Planner, TaskGraph
from orchestrator.recovery import RecoveryOrchestrator
from orchestrator.state_machine import DeploymentState, DeploymentStateMachine
from shared.errors import (
    AmbiguousOutcomeError,
    ConflictError,
    ValidationError,
)
from shared.hashing import hash_json
from shared.ids import generate_deployment_id, generate_uuid
from shared.result_object import ResultObject


class FullOrchestrator:
    """
    Full deployment orchestrator connecting all user stories.

    Orchestrates complete deployment lifecycle:
    - US1: Intake validation and planning (preview)
    - US2: Artifact generation and validation (package)
    - US3: Sequential execution with approval (deploy)
    - US4: Recovery from partial/ambiguous failures (recover)
    """

    def __init__(
        self,
        internal_store: SupabaseInternalClient,
        adapters: dict[str, Any] | None = None,
    ):
        self.internal_store = internal_store
        self.state_machine = DeploymentStateMachine()
        self.planner = Planner()
        self.assembler = PackageAssembler()
        self.audit_writer = AuditEventWriter(internal_store)
        self.prompts = InteractivePrompts()
        self.adapters = adapters or {}
        self.recovery = RecoveryOrchestrator(internal_store, self.adapters)

    def onboard(
        self,
        intake: dict[str, Any],
        operator: str,
        session_id: str,
        dry_run: bool = False,
        environment: str = "staging",
    ) -> dict[str, Any]:
        """
        Complete onboarding flow from intake to deployment.

        Args:
            intake: Raw intake dictionary
            operator: Operator identifier
            session_id: Session identifier
            dry_run: If True, stop after planning (US1 only)
            environment: Target environment (staging/production)

        Returns:
            Onboarding result with deployment_id and status

        Flow:
            1. US1: Validate intake and create plan
            2. US2: Generate and validate artifacts
            3. US3: Execute actions with per-action approval
            4. US4: Handle failures and recovery
        """
        # Check for existing recovery state before starting new work
        organization_id_check = intake.get("organization_id") or intake.get("organization", {}).get(
            "slug"
        )
        if organization_id_check:
            recovery_info = self.recovery.detect_restart_recovery(organization_id_check)
            if recovery_info:
                return {
                    "status": "recovery_pending",
                    "message": "Existing deployment requires recovery before new work",
                    "recovery_info": self.recovery.format_recovery_options(recovery_info),
                }

        # ============================================================
        # US1: INTAKE VALIDATION AND PLANNING
        # ============================================================

        validation_result = validate_intake(intake)
        if not validation_result["valid"]:
            return {
                "status": "validation_failed",
                "errors": validation_result["errors"],
            }

        normalized_intake = normalize_intake(intake)
        organization_id = normalized_intake["organization_id"]

        deployment_id = generate_deployment_id()

        deployment = {
            "deployment_id": deployment_id,
            "organization_id": organization_id,
            "intent": "new_onboarding",
            "status": DeploymentState.PLANNING.value,
            "operator": operator,
            "session_id": session_id,
            "environment": environment,
            "created_at": datetime.now(UTC).isoformat(),
        }

        self.internal_store.create_deployment(deployment)

        record_deployment_created(
            audit_writer=self.audit_writer,
            deployment_id=deployment_id,
            organization_id=organization_id,
            operator=operator,
            intent="new_onboarding",
            session_id=session_id,
        )

        task_graph = self.planner.create_task_graph(normalized_intake)

        self._transition_state(
            deployment_id=deployment_id,
            from_state=DeploymentState.PLANNING.value,
            to_state=DeploymentState.AWAITING_PLAN_APPROVAL.value,
            operator=operator,
            session_id=session_id,
        )

        if dry_run:
            plan = self.planner.create_dry_run_plan(task_graph, normalized_intake)
            return {
                "status": "plan_ready",
                "deployment_id": deployment_id,
                "organization_id": organization_id,
                "task_count": len(task_graph),
                "plan": plan,
                "message": "Dry run complete. Review plan and run with execute=True to proceed.",
            }

        # ============================================================
        # US2: ARTIFACT GENERATION AND VALIDATION
        # ============================================================

        self._transition_state(
            deployment_id=deployment_id,
            from_state=DeploymentState.AWAITING_PLAN_APPROVAL.value,
            to_state=DeploymentState.GENERATING.value,
            operator=operator,
            session_id=session_id,
            reason="Plan approved by operator",
        )

        generation_results = self._generate_artifacts(
            deployment_id=deployment_id,
            task_graph=task_graph,
            intake=normalized_intake,
            session_id=session_id,
        )

        package = self.assembler.assemble_package(
            deployment_id=deployment_id,
            organization_id=organization_id,
            results=generation_results,
        )

        if not package.validation_passed:
            self._transition_state(
                deployment_id=deployment_id,
                from_state=DeploymentState.GENERATING.value,
                to_state=DeploymentState.FAILED.value,
                operator="system",
                session_id=session_id,
                reason=f"Package validation failed: {package.errors}",
            )

            return {
                "status": "generation_failed",
                "deployment_id": deployment_id,
                "errors": package.errors,
            }

        # ============================================================
        # US3: SEQUENTIAL EXECUTION WITH APPROVAL
        # ============================================================

        self._transition_state(
            deployment_id=deployment_id,
            from_state=DeploymentState.GENERATING.value,
            to_state=DeploymentState.AWAITING_ACTION_APPROVAL.value,
            operator="system",
            session_id=session_id,
            reason="Package validated, ready for deployment",
        )

        proposed_actions = self._build_proposed_actions(
            package=package,
            intake=normalized_intake,
            deployment_id=deployment_id,
        )

        if not proposed_actions:
            self._transition_state(
                deployment_id=deployment_id,
                from_state=DeploymentState.AWAITING_ACTION_APPROVAL.value,
                to_state=DeploymentState.VERIFYING.value,
                operator="system",
                session_id=session_id,
                reason="No external actions required",
            )
            self._transition_state(
                deployment_id=deployment_id,
                from_state=DeploymentState.VERIFYING.value,
                to_state=DeploymentState.COMPLETED.value,
                operator="system",
                session_id=session_id,
            )
            return {
                "status": "completed",
                "deployment_id": deployment_id,
                "organization_id": organization_id,
                "message": "Deployment completed (no external actions).",
            }

        execution_result = self._execute_with_approval(
            deployment_id=deployment_id,
            organization_id=organization_id,
            proposed_actions=proposed_actions,
            operator=operator,
            session_id=session_id,
        )

        return execution_result

    # ------------------------------------------------------------------
    # US2: Artifact Generation
    # ------------------------------------------------------------------

    def _generate_artifacts(
        self,
        deployment_id: str,
        task_graph: TaskGraph,
        intake: dict[str, Any],
        session_id: str,
    ) -> list[ResultObject]:
        """
        Generate artifacts by delegating to specialist agents.

        Routes each generation task to the correct agent based on agent_target.
        """
        results: list[ResultObject] = []
        ordered_tasks = task_graph.get_ordered_tasks()

        agent_map: dict[str, Any] = {
            "vapi_agent": VapiAgent(),
            "make_agent": MakeAgent(),
            "supabase_agent": SupabaseAgent(),
            "nodejs_agent": NodeJsAgent(),
        }

        for task in ordered_tasks:
            if task.agent_target == "operator":
                continue

            if "validate" in task.action_type:
                continue

            agent = agent_map.get(task.agent_target)
            if not agent:
                continue

            self.audit_writer.record_event(
                deployment_id=deployment_id,
                event_type=AuditEventType.TASK_STARTED,
                actor=task.agent_target,
                subject=task.task_id,
                status="started",
                detail={"action_type": task.action_type},
                session_id=session_id,
            )

            try:
                result = agent.execute(task, intake)
                results.append(result)

                self.audit_writer.record_event(
                    deployment_id=deployment_id,
                    event_type=AuditEventType.TASK_COMPLETED,
                    actor=task.agent_target,
                    subject=task.task_id,
                    status="success",
                    detail={
                        "content_hash": result.content_hash,
                        "storage_path": result.storage_path,
                    },
                    session_id=session_id,
                )
            except Exception as e:
                self.audit_writer.record_event(
                    deployment_id=deployment_id,
                    event_type=AuditEventType.TASK_FAILED,
                    actor=task.agent_target,
                    subject=task.task_id,
                    status="failed",
                    detail={"error": str(e)},
                    session_id=session_id,
                )
                raise

        return results

    # ------------------------------------------------------------------
    # US3: Build Proposed Actions from Package
    # ------------------------------------------------------------------

    def _build_proposed_actions(
        self,
        package: DeploymentPackage,
        intake: dict[str, Any],
        deployment_id: str,
    ) -> list[ProposedAction]:
        """
        Build ProposedAction list from validated package and intake.

        Maps each artifact/capability to the external operations required.
        """
        actions: list[ProposedAction] = []
        organization_id = intake["organization_id"]
        capabilities = intake.get("enabled_capabilities", [])

        # Supabase: insert organization record (if booking capability)
        if "booking" in capabilities:
            actions.append(
                build_proposed_action(
                    platform="supabase_client",
                    operation="insert_org_record",
                    target=f"organizations/{organization_id}",
                    payload={
                        "organization_id": organization_id,
                        "business_name": intake.get("business_name", ""),
                        "timezone": intake.get("timezone"),
                        "configuration": {
                            "capabilities": capabilities,
                        },
                    },
                    retry_policy="proven_idempotent",
                    reconciliation_strategy="select_by_org_id",
                    compensation_operation="delete_org_record",
                    expected_outcome=f"Insert organization record for {organization_id}",
                )
            )

        # Vapi: create assistant
        vapi_artifact = next((a for a in package.artifacts if a.agent_source == "vapi_agent"), None)
        if vapi_artifact:
            actions.append(
                build_proposed_action(
                    platform="vapi",
                    operation="create_assistant",
                    target=f"assistant/{organization_id}",
                    payload={
                        "name": f"{intake.get('business_name', organization_id)}-assistant",
                        "config_path": vapi_artifact.storage_path,
                        "content_hash": vapi_artifact.content_hash,
                    },
                    retry_policy="none",
                    reconciliation_strategy="list_by_name",
                    compensation_operation="delete_assistant",
                    expected_outcome=f"Create Vapi assistant for {organization_id}",
                )
            )

        # Make: create scenarios for each capability
        make_capabilities = [
            c
            for c in capabilities
            if c in ["availability", "booking", "cancellation", "rescheduling"]
        ]
        for cap in make_capabilities:
            blueprint_path = f"outputs/{organization_id}/make/blueprints/{cap}.json"
            actions.append(
                build_proposed_action(
                    platform="make",
                    operation="create_scenario",
                    target=f"scenario/{organization_id}/{cap}",
                    payload={
                        "name": f"{organization_id}-{cap}",
                        "blueprint": {"capability": cap},
                        "blueprint_path": blueprint_path,
                        "scheduling": {"type": "immediately"},
                        "confirmed": False,
                    },
                    retry_policy="none",
                    reconciliation_strategy="list_by_team_name",
                    compensation_operation="delete_scenario",
                    expected_outcome=f"Create Make scenario for {cap}",
                )
            )

        # Render: set env variables and trigger deploy
        webhook_base = intake.get("hosting", {}).get("webhook_base_url", "")
        if webhook_base:
            actions.append(
                build_proposed_action(
                    platform="render",
                    operation="set_env_variable",
                    target=f"env/{organization_id}",
                    payload={
                        "key": f"CLIENT_{organization_id.upper().replace('-', '_')}_ENABLED",
                        "value": "true",
                    },
                    retry_policy="proven_idempotent",
                    reconciliation_strategy="get_env_variable",
                    compensation_operation="delete_env_variable",
                    expected_outcome=f"Enable client routes for {organization_id}",
                )
            )

            actions.append(
                build_proposed_action(
                    platform="render",
                    operation="trigger_deploy",
                    target=f"deploy/{organization_id}",
                    payload={
                        "clear_cache": "do_not_clear",
                    },
                    retry_policy="read_only",
                    reconciliation_strategy="get_deploy_status",
                    compensation_operation=None,
                    expected_outcome="Trigger backend deployment with new routes",
                )
            )

        return actions

    # ------------------------------------------------------------------
    # US3: Sequential Execution with Per-Action Approval
    # ------------------------------------------------------------------

    def _execute_with_approval(
        self,
        deployment_id: str,
        organization_id: str,
        proposed_actions: list[ProposedAction],
        operator: str,
        session_id: str,
    ) -> dict[str, Any]:
        """
        Execute proposed actions sequentially with per-action approval.

        Each action: display → approve → execute → persist receipt.
        On failure, transitions to US4 recovery.
        """
        completed: list[dict[str, Any]] = []

        for i, proposed_action in enumerate(proposed_actions):
            action_label = f"{i + 1}/{len(proposed_actions)}"

            # Check staleness before presenting
            current_state = self._read_current_state(proposed_action)
            if check_staleness(proposed_action, current_state):
                self.audit_writer.record_event(
                    deployment_id=deployment_id,
                    event_type=AuditEventType.ACTION_EXECUTING,
                    actor="system",
                    subject=proposed_action.target,
                    status="stale_detected",
                    detail={
                        "platform": proposed_action.platform,
                        "operation": proposed_action.operation,
                    },
                    session_id=session_id,
                )
                proposed_action = self._regenerate_action(
                    proposed_action, deployment_id, organization_id
                )

            # Transition to awaiting approval for this action
            if i == 0:
                self._transition_state(
                    deployment_id=deployment_id,
                    from_state=DeploymentState.AWAITING_ACTION_APPROVAL.value,
                    to_state=DeploymentState.EXECUTING.value,
                    operator=operator,
                    session_id=session_id,
                    reason=f"Starting action execution ({action_label})",
                )

            # Display proposal and get approval
            display_content = format_proposal_display(proposed_action)
            decision_str = self.prompts.approve_action(
                {
                    "platform": proposed_action.platform,
                    "operation": proposed_action.operation,
                    "target": proposed_action.target,
                    "change_summary": proposed_action.expected_outcome or "",
                    "validation_result": proposed_action.validation_result or {"passed": True},
                    "reconciliation_strategy": proposed_action.reconciliation_strategy,
                    "compensation_operation": proposed_action.compensation_operation,
                },
                proposed_action.proposal_hash,
            )

            # Record approval
            approval = record_approval_decision(
                proposed_action=proposed_action,
                decision=decision_str,
                display_content=display_content,
                operator=operator,
            )

            self.internal_store.insert_approval_decision(
                deployment_id=deployment_id,
                proposal_hash=approval.proposal_hash,
                decision=approval.decision,
                display_hash=approval.display_hash,
                decided_by=operator,
                decided_at=approval.decided_at,
                notes=approval.notes,
            )

            record_audit_approval(
                audit_writer=self.audit_writer,
                deployment_id=deployment_id,
                action_id=proposed_action.target,
                operator=operator,
                decision=approval.decision,
                proposal_hash=approval.proposal_hash,
                display_hash=approval.display_hash,
                session_id=session_id,
            )

            # Handle decision
            if approval.decision == "approved":
                result = self._execute_single_action(
                    deployment_id=deployment_id,
                    organization_id=organization_id,
                    proposed_action=proposed_action,
                    session_id=session_id,
                )

                if result["status"] == "success":
                    completed.append(result)
                elif result["status"] == "ambiguous":
                    # US4: Enter recovery
                    return self._enter_recovery(
                        deployment_id=deployment_id,
                        proposed_action=proposed_action,
                        error_message=result.get("error", "Ambiguous outcome"),
                        completed=completed,
                        session_id=session_id,
                    )
                else:
                    # US4: Action failed
                    return self._handle_action_failure(
                        deployment_id=deployment_id,
                        proposed_action=proposed_action,
                        error_message=result.get("error", "Action failed"),
                        completed=completed,
                        session_id=session_id,
                        operator=operator,
                    )

            elif approval.decision == "rejected_abort":
                self._transition_state(
                    deployment_id=deployment_id,
                    from_state=DeploymentState.EXECUTING.value,
                    to_state=DeploymentState.ABORTED.value,
                    operator=operator,
                    session_id=session_id,
                    reason="Operator rejected action and aborted",
                )
                return {
                    "status": "aborted",
                    "deployment_id": deployment_id,
                    "completed_actions": len(completed),
                    "message": "Deployment aborted by operator",
                }

            elif approval.decision == "rejected_revise":
                # Go back to generating for revision
                self._transition_state(
                    deployment_id=deployment_id,
                    from_state=DeploymentState.EXECUTING.value,
                    to_state=DeploymentState.AWAITING_ACTION_APPROVAL.value,
                    operator=operator,
                    session_id=session_id,
                    reason="Operator requested revision",
                )
                return {
                    "status": "revision_required",
                    "deployment_id": deployment_id,
                    "action_index": i,
                    "completed_actions": len(completed),
                    "message": "Action revision requested. Re-run after addressing feedback.",
                }

        # All actions completed successfully
        self._transition_state(
            deployment_id=deployment_id,
            from_state=DeploymentState.EXECUTING.value,
            to_state=DeploymentState.VERIFYING.value,
            operator="system",
            session_id=session_id,
        )

        self._transition_state(
            deployment_id=deployment_id,
            from_state=DeploymentState.VERIFYING.value,
            to_state=DeploymentState.COMPLETED.value,
            operator="system",
            session_id=session_id,
        )

        return {
            "status": "completed",
            "deployment_id": deployment_id,
            "organization_id": organization_id,
            "total_actions": len(proposed_actions),
            "completed_actions": len(completed),
            "receipts": completed,
            "message": "Deployment completed successfully",
        }

    # ------------------------------------------------------------------
    # US3: Single Action Execution
    # ------------------------------------------------------------------

    def _execute_single_action(
        self,
        deployment_id: str,
        organization_id: str,
        proposed_action: ProposedAction,
        session_id: str,
    ) -> dict[str, Any]:
        """Execute a single approved action via the appropriate adapter."""
        record_action_execution(
            audit_writer=self.audit_writer,
            deployment_id=deployment_id,
            action_id=proposed_action.target,
            platform=proposed_action.platform,
            operation=proposed_action.operation,
            status="executing",
            session_id=session_id,
        )

        try:
            receipt = self._call_adapter(proposed_action)

            self.internal_store.insert_receipt(
                deployment_id=deployment_id,
                platform=proposed_action.platform,
                operation=proposed_action.operation,
                remote_id=receipt.get("remote_id", ""),
                status="success",
                response_data=receipt,
            )

            if receipt.get("remote_id"):
                self.internal_store.upsert_external_resource(
                    deployment_id=deployment_id,
                    platform=proposed_action.platform,
                    resource_type=proposed_action.operation.replace("create_", ""),
                    remote_id=receipt["remote_id"],
                    organization_id=organization_id,
                    current_state_hash=hash_json(receipt),
                )

            record_action_execution(
                audit_writer=self.audit_writer,
                deployment_id=deployment_id,
                action_id=proposed_action.target,
                platform=proposed_action.platform,
                operation=proposed_action.operation,
                status="succeeded",
                receipt_id=receipt.get("remote_id"),
                session_id=session_id,
            )

            return {
                "status": "success",
                "platform": proposed_action.platform,
                "operation": proposed_action.operation,
                "remote_id": receipt.get("remote_id"),
            }

        except AmbiguousOutcomeError as e:
            record_action_execution(
                audit_writer=self.audit_writer,
                deployment_id=deployment_id,
                action_id=proposed_action.target,
                platform=proposed_action.platform,
                operation=proposed_action.operation,
                status="ambiguous",
                error_message=str(e),
                session_id=session_id,
            )
            return {
                "status": "ambiguous",
                "error": str(e),
                "platform": proposed_action.platform,
                "operation": proposed_action.operation,
            }

        except Exception as e:
            record_action_execution(
                audit_writer=self.audit_writer,
                deployment_id=deployment_id,
                action_id=proposed_action.target,
                platform=proposed_action.platform,
                operation=proposed_action.operation,
                status="failed",
                error_message=str(e),
                session_id=session_id,
            )
            return {
                "status": "failed",
                "error": str(e),
                "platform": proposed_action.platform,
                "operation": proposed_action.operation,
            }

    def _call_adapter(self, proposed_action: ProposedAction) -> Any:
        """Route action to the correct platform adapter and return receipt."""
        from adapters.hosting import RenderAdapter
        from adapters.make import MakeAdapter
        from adapters.supabase_client import SupabaseClientAdapter
        from adapters.vapi import VapiAdapter

        platform = proposed_action.platform
        operation = proposed_action.operation
        payload = proposed_action.payload

        if platform == "vapi":
            adapter = self.adapters.get("vapi") or VapiAdapter()
            if operation == "create_assistant":
                return adapter.create_assistant(payload)
            elif operation == "create_tool":
                return adapter.create_tool(payload)
            elif operation == "assign_phone_number":
                return adapter.assign_phone_number(
                    payload["phone_number_id"], payload.get("assistant_id")
                )

        elif platform == "make":
            adapter = self.adapters.get("make") or MakeAdapter()
            if operation == "create_scenario":
                return adapter.create_scenario(
                    payload["blueprint"], payload["scheduling"], payload.get("confirmed", False)
                )
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

        elif platform == "supabase_client":
            adapter = self.adapters.get("supabase_client") or SupabaseClientAdapter()
            if operation == "insert_org_record":
                return adapter.insert_org_record(
                    payload["organization_id"],
                    payload["business_name"],
                    payload.get("timezone"),
                    payload.get("configuration"),
                )

        elif platform == "render":
            adapter = self.adapters.get("render") or RenderAdapter()
            if operation == "set_env_variable":
                return adapter.set_env_variable(payload["key"], payload["value"])
            elif operation == "trigger_deploy":
                return adapter.trigger_deploy(
                    payload.get("clear_cache", "do_not_clear"),
                    payload.get("commit_id"),
                    payload.get("image_url"),
                )

        raise ValidationError(
            f"Unknown platform/operation: {platform}/{operation}",
            field="platform",
        )

    # ------------------------------------------------------------------
    # US4: Recovery Handling
    # ------------------------------------------------------------------

    def _enter_recovery(
        self,
        deployment_id: str,
        proposed_action: ProposedAction,
        error_message: str,
        completed: list[dict[str, Any]],
        session_id: str,
    ) -> dict[str, Any]:
        """Transition to recovery state after ambiguous outcome."""
        self._transition_state(
            deployment_id=deployment_id,
            from_state=DeploymentState.EXECUTING.value,
            to_state=DeploymentState.PARTIAL.value,
            operator="system",
            session_id=session_id,
            reason=f"Ambiguous outcome: {error_message}",
        )
        self._transition_state(
            deployment_id=deployment_id,
            from_state=DeploymentState.PARTIAL.value,
            to_state=DeploymentState.RECOVERY_REQUIRED.value,
            operator="system",
            session_id=session_id,
            reason="Reconciliation needed",
        )

        return {
            "status": "recovery_required",
            "deployment_id": deployment_id,
            "completed_actions": len(completed),
            "failed_action": {
                "platform": proposed_action.platform,
                "operation": proposed_action.operation,
                "target": proposed_action.target,
                "error": error_message,
            },
            "recovery_options": ["reconcile", "retry", "compensate", "defer", "abort"],
            "message": "Ambiguous outcome detected. Recovery required before proceeding.",
        }

    def _handle_action_failure(
        self,
        deployment_id: str,
        proposed_action: ProposedAction,
        error_message: str,
        completed: list[dict[str, Any]],
        session_id: str,
        operator: str,
    ) -> dict[str, Any]:
        """Handle definitive action failure (not ambiguous)."""
        if completed:
            self._transition_state(
                deployment_id=deployment_id,
                from_state=DeploymentState.EXECUTING.value,
                to_state=DeploymentState.PARTIAL.value,
                operator="system",
                session_id=session_id,
                reason=f"Action failed: {error_message}",
            )
            self._transition_state(
                deployment_id=deployment_id,
                from_state=DeploymentState.PARTIAL.value,
                to_state=DeploymentState.RECOVERY_REQUIRED.value,
                operator="system",
                session_id=session_id,
            )
            return {
                "status": "recovery_required",
                "deployment_id": deployment_id,
                "completed_actions": len(completed),
                "failed_action": {
                    "platform": proposed_action.platform,
                    "operation": proposed_action.operation,
                    "target": proposed_action.target,
                    "error": error_message,
                },
                "recovery_options": ["retry", "compensate", "defer", "abort"],
                "message": "Action failed after partial completion. Recovery required.",
            }
        else:
            self._transition_state(
                deployment_id=deployment_id,
                from_state=DeploymentState.EXECUTING.value,
                to_state=DeploymentState.FAILED.value,
                operator="system",
                session_id=session_id,
                reason=f"First action failed: {error_message}",
            )
            return {
                "status": "failed",
                "deployment_id": deployment_id,
                "failed_action": {
                    "platform": proposed_action.platform,
                    "operation": proposed_action.operation,
                    "target": proposed_action.target,
                    "error": error_message,
                },
                "message": "Deployment failed (no resources created).",
            }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _transition_state(
        self,
        deployment_id: str,
        from_state: str,
        to_state: str,
        operator: str,
        session_id: str,
        reason: str | None = None,
    ) -> None:
        """Validate and execute state transition with audit logging."""
        if not self.state_machine.is_valid_transition(from_state, to_state):
            raise ConflictError(
                f"Invalid state transition: {from_state} → {to_state}",
                resource="deployment",
                context={
                    "deployment_id": deployment_id,
                    "from_state": from_state,
                    "to_state": to_state,
                },
            )

        self.internal_store.update_deployment_status(deployment_id, to_state)

        record_state_transition(
            audit_writer=self.audit_writer,
            deployment_id=deployment_id,
            actor=operator,
            from_state=from_state,
            to_state=to_state,
            reason=reason,
            session_id=session_id,
        )

    def _read_current_state(self, proposed_action: ProposedAction) -> str | None:
        """Read authoritative current state for staleness check."""
        if not proposed_action.state_version:
            return None
        return None

    def _regenerate_action(
        self,
        proposed_action: ProposedAction,
        deployment_id: str,
        organization_id: str,
    ) -> ProposedAction:
        """Regenerate a stale action with fresh state."""
        return build_proposed_action(
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
