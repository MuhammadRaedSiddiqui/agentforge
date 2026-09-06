"""
Capability-driven task graph planner for Agent Forge.

Generates ordered task graphs with dependencies, validations, approvals,
expected artifacts, and intended changes based on enabled capabilities.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from orchestrator.intake_schema import needs_database
from shared.ids import generate_task_id, generate_uuid
from shared.task_object import TaskObject


@dataclass
class TaskNode:
    """A node in the task graph."""

    task: TaskObject
    dependencies: list[str] = field(default_factory=list)
    expected_output: str = ""
    validation_required: bool = True


class TaskGraph:
    """
    Task graph with dependencies and ordering.

    Provides topological sorting and query methods.
    """

    def __init__(self) -> None:
        """Initialize empty task graph."""
        self.tasks: dict[str, TaskNode] = {}

    def __iter__(self) -> Iterator[Any]:
        """Iterate over tasks in topological order."""
        return iter(self.get_ordered_tasks())

    def __len__(self) -> int:
        """Return the number of tasks in the graph."""
        return len(self.tasks)

    def add_task(
        self,
        task: TaskObject,
        dependencies: list[str] | None = None,
        expected_output: str = "",
    ) -> None:
        """
        Add task to graph.

        Args:
            task: TaskObject to add
            dependencies: List of task IDs this task depends on
            expected_output: Description of expected output
        """
        node = TaskNode(
            task=task,
            dependencies=dependencies or [],
            expected_output=expected_output,
            validation_required=task.verification_required,
        )
        self.tasks[task.task_id] = node

    def get_ordered_tasks(self) -> list[TaskObject]:
        """
        Get tasks in topological order.

        Returns:
            List of TaskObjects in execution order

        Raises:
            ValueError: If circular dependency detected
        """
        # Kahn's algorithm for topological sort
        in_degree = dict.fromkeys(self.tasks, 0)

        # Calculate in-degree: count how many dependencies each task has
        for task_id, node in self.tasks.items():
            for dep_id in node.dependencies:
                if dep_id in in_degree:
                    in_degree[task_id] += 1

        # Find nodes with no incoming edges (no dependencies)
        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            task_id = queue.pop(0)
            result.append(self.tasks[task_id].task)

            # Reduce in-degree for tasks that depend on this task
            for other_id, node in self.tasks.items():
                if task_id in node.dependencies:
                    in_degree[other_id] -= 1
                    if in_degree[other_id] == 0:
                        queue.append(other_id)

        if len(result) != len(self.tasks):
            raise ValueError("Circular dependency detected in task graph")

        return result

    def get_all_tasks(self) -> list[TaskObject]:
        """Get all tasks (unordered)."""
        return [node.task for node in self.tasks.values()]

    def has_agent_tasks(self, agent_target: str) -> bool:
        """Check if graph has tasks for specific agent."""
        return any(node.task.agent_target == agent_target for node in self.tasks.values())

    def get_approval_tasks(self) -> list[TaskObject]:
        """Get all approval tasks."""
        return [
            node.task for node in self.tasks.values() if "approve" in node.task.action_type.lower()
        ]


class Planner:
    """
    Capability-driven task graph planner.

    Generates task graphs based on enabled capabilities and dependencies.
    """

    def __init__(self) -> None:
        """Initialize planner."""
        pass

    def create_task_graph(
        self, intake: dict[str, Any], deployment_intent: str | None = None
    ) -> TaskGraph:
        """
        Create task graph from intake.

        Args:
            intake: Validated intake dictionary
            deployment_intent: Optional deployment intent (e.g., "new_onboarding")

        Returns:
            TaskGraph with ordered dependencies
        """
        graph = TaskGraph()
        deployment_id = generate_uuid()
        capabilities = intake.get("enabled_capabilities", [])

        # Sequence counter for task IDs
        sequence = 0

        # Phase 1: Database generation (if needed)
        supabase_task_id = None
        if self._needs_database(capabilities):
            sequence += 1
            supabase_task_id = generate_task_id(deployment_id, "supabase_agent", sequence, 1)

            supabase_task = TaskObject(
                task_id=supabase_task_id,
                deployment_id=deployment_id,
                agent_target="supabase_agent",
                action_type="generate_database_schema",
                context_hash="supabase_context_hash",
                constraints=["no_destructive_operations", "tenant_isolation_required"],
                dependencies=[],
                verification_required=True,
            )

            graph.add_task(
                supabase_task,
                dependencies=[],
                expected_output="Database migration SQL with RLS policies",
            )

        # Phase 2: Vapi, Make, Node.js generation (parallel)
        vapi_task_id = None
        make_task_ids: list[str] = []
        nodejs_task_id = None

        # Vapi agent
        sequence += 1
        vapi_task_id = generate_task_id(deployment_id, "vapi_agent", sequence, 1)

        vapi_task = TaskObject(
            task_id=vapi_task_id,
            deployment_id=deployment_id,
            agent_target="vapi_agent",
            action_type="generate_assistant_config",
            context_hash="vapi_context_hash",
            constraints=["no_secrets_in_config", "valid_tool_references"],
            dependencies=[supabase_task_id] if supabase_task_id else [],
            verification_required=True,
        )

        graph.add_task(
            vapi_task,
            dependencies=[supabase_task_id] if supabase_task_id else [],
            expected_output="Vapi assistant configuration JSON and tool schemas",
        )

        # Make uses one blueprint per enabled capability.  A single generic
        # task could not tell the Make agent which template to render and
        # caused live generation to fail before any external write.
        make_capabilities = [
            capability
            for capability in capabilities
            if capability in ["availability", "booking", "cancellation", "rescheduling"]
        ]
        for capability in make_capabilities:
            sequence += 1
            make_task_id = generate_task_id(deployment_id, "make_agent", sequence, 1)
            make_task_ids.append(make_task_id)
            make_task = TaskObject(
                task_id=make_task_id,
                deployment_id=deployment_id,
                agent_target="make_agent",
                action_type=f"generate_{capability}_blueprint",
                context_hash="make_context_hash",
                constraints=["valid_webhook_urls", "no_secrets_in_blueprints"],
                dependencies=[supabase_task_id] if supabase_task_id else [],
                verification_required=True,
            )
            graph.add_task(
                make_task,
                dependencies=[supabase_task_id] if supabase_task_id else [],
                expected_output=f"Make.com {capability} scenario blueprint",
            )

        # Node.js agent
        sequence += 1
        nodejs_task_id = generate_task_id(deployment_id, "nodejs_agent", sequence, 1)

        nodejs_task = TaskObject(
            task_id=nodejs_task_id,
            deployment_id=deployment_id,
            agent_target="nodejs_agent",
            action_type="generate_backend_diff",
            context_hash="nodejs_context_hash",
            constraints=["hmac_validation_required", "no_unrelated_changes"],
            dependencies=[supabase_task_id] if supabase_task_id else [],
            verification_required=True,
        )

        graph.add_task(
            nodejs_task,
            dependencies=[supabase_task_id] if supabase_task_id else [],
            expected_output="Unified diff for backend route additions",
        )

        # Phase 3: Validation tasks for each generation
        validation_tasks = {}

        if supabase_task_id:
            sequence += 1
            val_id = generate_task_id(deployment_id, "supabase_agent", sequence, 1)
            val_task = TaskObject(
                task_id=val_id,
                deployment_id=deployment_id,
                agent_target="supabase_agent",
                action_type="validate_database_schema",
                context_hash="supabase_validation_hash",
                constraints=["schema_conformance", "no_cross_client_refs"],
                dependencies=[supabase_task_id],
                verification_required=True,
            )
            graph.add_task(
                val_task,
                dependencies=[supabase_task_id],
                expected_output="Schema validation report",
            )
            validation_tasks["supabase"] = val_id

        sequence += 1
        vapi_val_id = generate_task_id(deployment_id, "vapi_agent", sequence, 1)
        vapi_val_task = TaskObject(
            task_id=vapi_val_id,
            deployment_id=deployment_id,
            agent_target="vapi_agent",
            action_type="validate_assistant_config",
            context_hash="vapi_validation_hash",
            constraints=["no_secrets", "valid_references"],
            dependencies=[vapi_task_id],
            verification_required=True,
        )
        graph.add_task(
            vapi_val_task,
            dependencies=[vapi_task_id],
            expected_output="Vapi config validation report",
        )
        validation_tasks["vapi"] = vapi_val_id

        if make_task_ids:
            sequence += 1
            make_val_id = generate_task_id(deployment_id, "make_agent", sequence, 1)
            make_val_task = TaskObject(
                task_id=make_val_id,
                deployment_id=deployment_id,
                agent_target="make_agent",
                action_type="validate_scenario_blueprints",
                context_hash="make_validation_hash",
                constraints=["valid_webhooks", "no_secrets"],
                dependencies=make_task_ids,
                verification_required=True,
            )
            graph.add_task(
                make_val_task,
                dependencies=make_task_ids,
                expected_output="Make.com blueprint validation report",
            )
            validation_tasks["make"] = make_val_id

        sequence += 1
        nodejs_val_id = generate_task_id(deployment_id, "nodejs_agent", sequence, 1)
        nodejs_val_task = TaskObject(
            task_id=nodejs_val_id,
            deployment_id=deployment_id,
            agent_target="nodejs_agent",
            action_type="validate_backend_diff",
            context_hash="nodejs_validation_hash",
            constraints=["hmac_present", "no_unrelated_changes"],
            dependencies=[nodejs_task_id],
            verification_required=True,
        )
        graph.add_task(
            nodejs_val_task,
            dependencies=[nodejs_task_id],
            expected_output="Backend diff validation report",
        )
        validation_tasks["nodejs"] = nodejs_val_id

        # Phase 4: Approval tasks for each external action
        if supabase_task_id and "supabase" in validation_tasks:
            sequence += 1
            approval_id = generate_task_id(deployment_id, "operator", sequence, 1)
            approval_task = TaskObject(
                task_id=approval_id,
                deployment_id=deployment_id,
                agent_target="operator",
                action_type="approve_database_migration",
                context_hash="approval_hash",
                constraints=["human_review_required"],
                dependencies=[validation_tasks["supabase"]],
                verification_required=False,
            )
            graph.add_task(
                approval_task,
                dependencies=[validation_tasks["supabase"]],
                expected_output="Approval decision",
            )

        sequence += 1
        vapi_approval_id = generate_task_id(deployment_id, "operator", sequence, 1)
        vapi_approval_task = TaskObject(
            task_id=vapi_approval_id,
            deployment_id=deployment_id,
            agent_target="operator",
            action_type="approve_vapi_assistant",
            context_hash="approval_hash",
            constraints=["human_review_required"],
            dependencies=[validation_tasks["vapi"]],
            verification_required=False,
        )
        graph.add_task(
            vapi_approval_task,
            dependencies=[validation_tasks["vapi"]],
            expected_output="Approval decision",
        )

        if "make" in validation_tasks:
            sequence += 1
            make_approval_id = generate_task_id(deployment_id, "operator", sequence, 1)
            make_approval_task = TaskObject(
                task_id=make_approval_id,
                deployment_id=deployment_id,
                agent_target="operator",
                action_type="approve_make_scenarios",
                context_hash="approval_hash",
                constraints=["human_review_required"],
                dependencies=[validation_tasks["make"]],
                verification_required=False,
            )
            graph.add_task(
                make_approval_task,
                dependencies=[validation_tasks["make"]],
                expected_output="Approval decision",
            )

        sequence += 1
        nodejs_approval_id = generate_task_id(deployment_id, "operator", sequence, 1)
        nodejs_approval_task = TaskObject(
            task_id=nodejs_approval_id,
            deployment_id=deployment_id,
            agent_target="operator",
            action_type="approve_backend_deployment",
            context_hash="approval_hash",
            constraints=["human_review_required"],
            dependencies=[validation_tasks["nodejs"]],
            verification_required=False,
        )
        graph.add_task(
            nodejs_approval_task,
            dependencies=[validation_tasks["nodejs"]],
            expected_output="Approval decision",
        )

        return graph

    def _needs_database(self, capabilities: list[str]) -> bool:
        """
        Check if capabilities require database setup.

        Args:
            capabilities: List of enabled capabilities

        Returns:
            True if database setup needed
        """
        return needs_database(capabilities)

    def create_dry_run_plan(self, graph: TaskGraph, intake: dict[str, Any]) -> dict[str, Any]:
        """
        Create dry-run plan from task graph.

        Args:
            graph: Task graph
            intake: Intake data

        Returns:
            Dry-run plan dictionary
        """
        ordered_tasks = graph.get_ordered_tasks()

        plan = {
            "organization_id": intake.get("organization_id"),
            "intent": "new_onboarding",
            "dry_run": True,
            "enabled_capabilities": intake.get("enabled_capabilities", []),
            "phases": self._create_phases(ordered_tasks),
            "validations": self._create_validation_list(graph),
            "approval_points": self._create_approval_points(graph),
            "expected_outputs": self._create_expected_outputs(graph),
            "intended_changes": self._create_intended_changes(intake),
            "inferred_fields": self._identify_inferred_fields(intake),
            "recovery_strategy": {
                "reconciliation": "Per-platform resource lookup after ambiguous outcomes",
                "compensation": "Delete resources in reverse order with approval",
                "restart": "Resume from last completed action",
            },
        }

        return plan

    def _create_phases(self, tasks: list[TaskObject]) -> list[dict[str, Any]]:
        """Create phase breakdown."""
        phases = [
            {
                "name": "Database Setup",
                "tasks": [t.task_id for t in tasks if t.agent_target == "supabase_agent"],
            },
            {
                "name": "Configuration Generation",
                "tasks": [
                    t.task_id
                    for t in tasks
                    if t.agent_target in ["vapi_agent", "make_agent", "nodejs_agent"]
                ],
            },
            {
                "name": "Validation",
                "tasks": [],  # Would be populated with validation tasks
            },
            {
                "name": "Deployment",
                "tasks": [],  # Would be populated with action tasks
            },
        ]

        return [p for p in phases if p["tasks"]]

    def _create_validation_list(self, graph: TaskGraph) -> list[str]:
        """Create list of validations."""
        return [
            "Schema conformance",
            "Secret absence verification",
            "Cross-client reference detection",
            "Field provenance tracking",
            "Destructive operation blocking",
        ]

    def _create_approval_points(self, graph: TaskGraph) -> list[dict[str, Any]]:
        """Create approval point list."""
        return [
            {
                "name": "Plan Approval",
                "description": "Review complete deployment plan before generation",
                "required": True,
            },
            {
                "name": "Per-Action Approval",
                "description": "Approve each external side effect individually",
                "required": True,
                "count": "One per external operation",
            },
        ]

    def _create_expected_outputs(self, graph: TaskGraph) -> list[dict[str, Any]]:
        """Create expected outputs list."""
        outputs = []

        for _task_id, node in graph.tasks.items():
            if node.expected_output:
                outputs.append(
                    {
                        "task": node.task.agent_target,
                        "artifact": node.expected_output,
                    }
                )

        return outputs

    def _create_intended_changes(self, intake: dict[str, Any]) -> list[dict[str, Any]]:
        """Create intended external changes list."""
        changes = []
        capabilities = intake.get("enabled_capabilities", [])

        # Vapi changes
        changes.append(
            {
                "platform": "vapi",
                "operation": "create_assistant",
                "description": "Create voice assistant with configured tools",
            }
        )

        # Make changes (one per capability requiring Make)
        make_capabilities = [
            c
            for c in capabilities
            if c in ["availability", "booking", "cancellation", "rescheduling"]
        ]
        for cap in make_capabilities:
            changes.append(
                {
                    "platform": "make",
                    "operation": "create_scenario",
                    "description": f"Create {cap} automation scenario",
                }
            )

        # Backend changes
        changes.append(
            {
                "platform": "hosting",
                "operation": "update_backend",
                "description": "Add routes for new client",
            }
        )

        # Database changes (if needed)
        if needs_database(capabilities):
            changes.append(
                {
                    "platform": "supabase_client",
                    "operation": "run_migration",
                    "description": "Create organization record and RLS policies",
                }
            )

        return changes

    def _identify_inferred_fields(self, intake: dict[str, Any]) -> list[str]:
        """Identify fields that will be inferred or defaulted."""
        inferred = []

        # Example inferred fields
        if not intake.get("voice_id"):
            inferred.append("voice_id (default will be used)")

        return inferred
