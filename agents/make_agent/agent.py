"""
Make agent for generating Make.com scenario blueprints.

This agent generates Make.com scenario configurations from intake data and
ground-truth templates, with full provenance tracking.
"""

import json
import os
from pathlib import Path
from typing import Any

from agents.make_agent.tools import configure_scheduling, inject_hook_urls, parameterize_blueprint
from agents.make_agent.validator import MakeValidator
from orchestrator.template_registry import get_template_registry
from shared.hashing import compute_content_hash
from shared.result_object import ResultObject
from shared.task_object import TaskObject


class MakeAgent:
    """
    Specialist agent for generating Make.com scenario blueprints.

    Responsibilities:
    - Load Make.com blueprint templates
    - Parameterize webhook URLs and team settings
    - Configure Supabase connection references
    - Inject hook IDs and scheduling configuration
    - Record field provenance
    - Validate generated blueprints
    - Return typed ResultObject for each scenario
    """

    def __init__(self) -> None:
        """Initialize the Make agent."""
        self.agent_name = "make_agent"
        self.template_registry = get_template_registry()
        self.validator = MakeValidator()

    def execute(self, task: TaskObject, intake: dict[str, Any]) -> ResultObject:
        """
        Execute the Make blueprint generation task.

        Args:
            task: Task object with generation parameters
            intake: Validated intake data

        Returns:
            ResultObject with generated blueprint and provenance
        """
        # Determine which capability to generate
        capability = self._extract_capability_from_task(task)
        if not capability:
            raise ValueError(f"Cannot determine capability from task: {task.task_id}")

        # Check if this capability is enabled
        # Callers outside the CLI (for example package generation and tests)
        # provide normalized intake with ``enabled_capabilities``.  The CLI
        # also supplies the short ``capabilities`` alias, so support both.
        enabled_capabilities = intake.get("capabilities", intake.get("enabled_capabilities", []))
        if capability not in enabled_capabilities:
            raise ValueError(f"Capability '{capability}' not enabled in intake")

        # Load blueprint template
        template_id = f"make_blueprint_{capability}"
        template_content = self.template_registry.get_template_content(template_id)
        if not template_content:
            raise ValueError(f"Make blueprint template not found: {template_id}")

        blueprint_data = json.loads(template_content)

        # Extract required data from intake
        organization_id = intake.get("organization_id")
        if not isinstance(organization_id, str):
            raise ValueError("organization_id must be a string")

        organization_display_name = intake.get("business_name")
        if not isinstance(organization_display_name, str):
            raise ValueError("business_name must be a string")

        make_team_id = intake.get("make", {}).get("team_id") or intake.get(
            "external_identifiers", {}
        ).get("make_team_id")
        if not isinstance(make_team_id, str):
            raise ValueError("make.team_id must be a string")

        # Build parameterization context
        context = {
            "organization_id": organization_id,
            "organization_display_name": organization_display_name,
            "make_team_id": make_team_id,
            f"{capability}_hook_id": f"{{HOOK_{capability.upper()}_ID}}",  # Runtime placeholder
            "supabase_connection_id": os.getenv(
                "MAKE_SUPABASE_CONNECTION_ID", "{{SUPABASE_CONNECTION_ID}}"
            ),
        }

        # Parameterize blueprint
        parameterized_blueprint = parameterize_blueprint(blueprint_data, context)

        # Inject webhook URLs (placeholders for now)
        blueprint_with_hooks = inject_hook_urls(
            parameterized_blueprint, capability, organization_id
        )

        # Configure scheduling
        final_blueprint = configure_scheduling(blueprint_with_hooks, "immediately")

        # Validate blueprint
        validation_result = self.validator.validate_blueprint(final_blueprint)

        if not validation_result.is_valid:
            raise ValueError(
                f"Generated Make blueprint failed validation: {validation_result.errors}"
            )

        # Save to output file
        output_dir = Path("outputs") / organization_id / "make" / "blueprints"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{capability}.json"

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(final_blueprint, f, indent=2)

        # Compute content hash
        content_hash = compute_content_hash(json.dumps(final_blueprint, sort_keys=True))

        # Mark field provenance
        field_provenance = {
            "name": {"type": "derived", "source": "intake.business_name"},
            "teamId": {"type": "copied", "source": "intake.make.team_id"},
            "flow": {"type": "defaulted", "source": "template"},
            "metadata.organization_id": {"type": "copied", "source": "intake.organization_id"},
            "metadata.capability": {"type": "defaulted", "source": "template"},
            "scheduling": {"type": "defaulted", "source": "template"},
        }

        # Create result object
        result = ResultObject(
            task_id=task.task_id,
            agent_source=self.agent_name,
            content_hash=content_hash,
            storage_path=str(output_path),
            summary=f"Generated Make {capability} scenario blueprint for {organization_display_name}",
            field_provenance=field_provenance,
            model_id="gemini-2.5-pro",
            validation_status="verified",
        )

        return result

    def generate_all_scenarios(
        self, task: TaskObject, intake: dict[str, Any]
    ) -> list[ResultObject]:
        """
        Generate all scenario blueprints for enabled capabilities.

        Args:
            task: Base task object
            intake: Validated intake data

        Returns:
            List of ResultObjects for each generated scenario
        """
        results = []
        capabilities = intake.get("capabilities", [])

        for capability in capabilities:
            # Create a sub-task for this capability
            capability_task = TaskObject(
                task_id=f"{task.task_id}_{capability}",
                deployment_id=task.deployment_id,
                agent_target=self.agent_name,
                action_type=f"generate_{capability}_blueprint",
                context_hash=task.context_hash,
                constraints=task.constraints,
                dependencies=task.dependencies,
                verification_required=True,
                status="pending",
            )

            try:
                result = self.execute(capability_task, intake)
                results.append(result)
            except Exception as e:
                # Log error but continue with other scenarios
                print(f"Error generating {capability} scenario: {str(e)}")
                continue

        return results

    def _extract_capability_from_task(self, task: TaskObject) -> str:
        """
        Extract capability name from task action_type or task_id.

        Args:
            task: Task object

        Returns:
            Capability name (e.g., 'availability', 'booking')
        """
        # Try to extract from action_type first
        action_type = task.action_type.lower()

        capabilities = ["availability", "booking", "cancellation", "rescheduling"]
        for cap in capabilities:
            if cap in action_type:
                return cap

        # Try to extract from task_id
        task_id = task.task_id.lower()
        for cap in capabilities:
            if cap in task_id:
                return cap

        return ""
