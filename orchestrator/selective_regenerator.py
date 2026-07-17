"""
Selective artifact regeneration for updates.

Implements T149: Selective artifact regeneration (generate only affected
artifacts and actions, preserve unchanged resources)
"""

from typing import Any

from orchestrator.planner import Planner
from shared.hashing import compute_content_hash
from shared.task_object import TaskObject


class SelectiveRegenerator:
    """
    Determines which artifacts need regeneration based on changes.

    Only regenerates artifacts affected by the update, preserving unchanged
    resources to minimize side effects.
    """

    def __init__(self) -> None:
        """Initialize selective regenerator."""
        self.planner = Planner()

    def determine_affected_artifacts(
        self,
        intent: str,
        changes: dict[str, dict[str, Any]],
    ) -> set[str]:
        """
        Determine which artifacts are affected by changes.

        Args:
            intent: Deployment intent (update_assistant, update_scenario, etc.)
            changes: Dictionary of field changes

        Returns:
            Set of affected artifact types
        """
        affected = set()

        if intent == "update_assistant":
            # Assistant updates affect:
            # - Vapi assistant config
            affected.add("vapi_assistant")

        elif intent == "update_scenario":
            # Scenario updates affect:
            # - Make scenario blueprints
            # - Make hooks (if webhook URLs changed)
            affected.add("make_scenario")

            if any(field in changes for field in ["webhook_url", "server_url"]):
                affected.add("make_hooks")

        elif intent == "update_schema":
            # Schema updates affect:
            # - Supabase migrations
            affected.add("supabase_migration")

        elif intent == "update_backend":
            # Backend updates affect:
            # - Node.js server diff
            # - Hosting deployment
            affected.add("nodejs_diff")
            affected.add("hosting_deploy")

        return affected

    def generate_update_tasks(
        self,
        deployment_id: str,
        organization_id: str,
        intent: str,
        changes: dict[str, dict[str, Any]],
        current_state: dict[str, Any],
    ) -> list[TaskObject]:
        """
        Generate tasks for selective artifact regeneration.

        Only generates tasks for affected artifacts.

        Args:
            deployment_id: New deployment ID for update
            organization_id: Organization identifier
            intent: Deployment intent
            changes: Dictionary of changes
            current_state: Current external state

        Returns:
            List of tasks to execute
        """
        tasks = []

        # Determine affected artifacts
        affected_artifacts = self.determine_affected_artifacts(intent, changes)

        # Generate tasks only for affected artifacts
        if "vapi_assistant" in affected_artifacts:
            task = TaskObject(
                task_id=f"{deployment_id}_vapi_assistant_update",
                deployment_id=deployment_id,
                agent_target="vapi_agent",
                action_type="update_assistant",
                context_hash=compute_content_hash(str(changes)),
                constraints=["preserve_tools", "preserve_phone"],
                dependencies=[],
                verification_required=True,
                status="pending",
            )
            tasks.append(task)

        if "make_scenario" in affected_artifacts:
            preserve_hooks = "make_hooks" not in affected_artifacts
            constraints = ["preserve_hooks"] if preserve_hooks else []
            task = TaskObject(
                task_id=f"{deployment_id}_make_scenario_update",
                deployment_id=deployment_id,
                agent_target="make_agent",
                action_type="update_scenario",
                context_hash=compute_content_hash(str(changes)),
                constraints=constraints,
                dependencies=[],
                verification_required=True,
                status="pending",
            )
            tasks.append(task)

        if "make_hooks" in affected_artifacts:
            task = TaskObject(
                task_id=f"{deployment_id}_make_hooks_update",
                deployment_id=deployment_id,
                agent_target="make_agent",
                action_type="update_hooks",
                context_hash=compute_content_hash(str(changes)),
                constraints=[],
                dependencies=[],
                verification_required=True,
                status="pending",
            )
            tasks.append(task)

        if "supabase_migration" in affected_artifacts:
            task = TaskObject(
                task_id=f"{deployment_id}_supabase_migration_update",
                deployment_id=deployment_id,
                agent_target="supabase_agent",
                action_type="generate_migration",
                context_hash=compute_content_hash(str(changes)),
                constraints=["migration_type:alter"],
                dependencies=[],
                verification_required=True,
                status="pending",
            )
            tasks.append(task)

        if "nodejs_diff" in affected_artifacts:
            task = TaskObject(
                task_id=f"{deployment_id}_nodejs_diff_update",
                deployment_id=deployment_id,
                agent_target="nodejs_agent",
                action_type="generate_diff",
                context_hash=compute_content_hash(str(changes)),
                constraints=[],
                dependencies=[],
                verification_required=True,
                status="pending",
            )
            tasks.append(task)

        if "hosting_deploy" in affected_artifacts:
            task = TaskObject(
                task_id=f"{deployment_id}_hosting_deploy",
                deployment_id=deployment_id,
                agent_target="hosting_adapter",
                action_type="trigger_deploy",
                context_hash=compute_content_hash(str(changes)),
                constraints=[],
                dependencies=["nodejs_diff"] if "nodejs_diff" in affected_artifacts else [],
                verification_required=True,
                status="pending",
            )
            tasks.append(task)

        return tasks

    def preserve_unchanged_resources(
        self,
        current_state: dict[str, Any],
        affected_artifacts: set[str],
    ) -> dict[str, list[str]]:
        """
        Identify resources to preserve (not regenerate or redeploy).

        Args:
            current_state: Current external state
            affected_artifacts: Set of affected artifact types

        Returns:
            Dictionary of preserved resources by platform
        """
        preserved: dict[str, list[str]] = {
            "vapi": [],
            "make": [],
            "supabase": [],
            "hosting": [],
        }

        # Vapi preservation
        if "vapi_assistant" not in affected_artifacts:
            # Preserve assistant if not affected
            vapi_state = current_state.get("platforms", {}).get("vapi", {})
            for assistant in vapi_state.get("assistants", []):
                preserved["vapi"].append(assistant["id"])

        # Always preserve tools unless explicitly updating
        if "vapi_tools" not in affected_artifacts:
            vapi_state = current_state.get("platforms", {}).get("vapi", {})
            for tool in vapi_state.get("tools", []):
                preserved["vapi"].append(tool["id"])

        # Make preservation
        if "make_scenario" not in affected_artifacts:
            make_state = current_state.get("platforms", {}).get("make", {})
            for scenario in make_state.get("scenarios", []):
                preserved["make"].append(scenario["id"])

        if "make_hooks" not in affected_artifacts:
            make_state = current_state.get("platforms", {}).get("make", {})
            for hook in make_state.get("hooks", []):
                preserved["make"].append(hook["id"])

        # Supabase preservation
        if "supabase_migration" not in affected_artifacts:
            supabase_state = current_state.get("platforms", {}).get("supabase", {})
            if supabase_state.get("organization_record"):
                preserved["supabase"].append("organization_record")

        return preserved
