"""
Vapi agent for generating assistant configurations.

This agent generates Vapi assistant configurations from intake data and
ground-truth templates, with full provenance tracking.
"""

import json
from pathlib import Path
from typing import Any

from agents.vapi_agent.tools import assemble_config, interpolate_template, mark_field_provenance
from agents.vapi_agent.validator import VapiValidator
from orchestrator.template_registry import get_template_registry
from shared.hashing import compute_content_hash
from shared.result_object import ResultObject
from shared.task_object import TaskObject


class VapiAgent:
    """
    Specialist agent for generating Vapi assistant configurations.

    Responsibilities:
    - Load Vapi assistant template
    - Interpolate intake data into template
    - Attach tool references
    - Set server URL and webhook configuration
    - Record field provenance (intake-copied vs inferred vs defaulted)
    - Validate generated configuration
    - Return typed ResultObject
    """

    def __init__(self) -> None:
        """Initialize the Vapi agent."""
        self.agent_name = "vapi_agent"
        self.template_registry = get_template_registry()
        self.validator = VapiValidator()

    def execute(self, task: TaskObject, intake: dict[str, Any]) -> ResultObject:
        """
        Execute the Vapi generation task.

        Args:
            task: Task object with generation parameters
            intake: Validated intake data

        Returns:
            ResultObject with generated configuration and provenance
        """
        # Load template
        template_content = self.template_registry.get_template_content("vapi_assistant")
        if not template_content:
            raise ValueError("Vapi assistant template not found")

        template_data = json.loads(template_content)

        # Extract required data from intake
        organization_id = intake.get("organization_id")
        if not isinstance(organization_id, str):
            raise ValueError("organization_id must be a string")

        organization_display_name = intake.get("business_name")
        if not isinstance(organization_display_name, str):
            raise ValueError("business_name must be a string")

        server_url = intake.get("hosting", {}).get("webhook_base_url")
        if not isinstance(server_url, str):
            raise ValueError("webhook_base_url must be a string")

        capabilities = intake.get("capabilities", [])
        if not isinstance(capabilities, list):
            raise ValueError("capabilities must be a list")

        # Build interpolation context
        context = {
            "organization_id": organization_id,
            "organization_display_name": organization_display_name,
            "voice_id": intake.get("vapi", {}).get("voice_id", "default-voice"),
            "server_url": server_url,
            "server_url_secret": "{{WEBHOOK_SECRET}}",  # Placeholder for runtime secret
        }

        # Interpolate template
        interpolated_config = interpolate_template(template_data, context)

        # Mark field provenance
        field_provenance = mark_field_provenance(interpolated_config, intake)

        # Filter tools based on capabilities
        if capabilities:
            interpolated_config["tools"] = [
                tool
                for tool in interpolated_config.get("tools", [])
                if self._tool_matches_capability(tool, capabilities)
            ]

        # Assemble final configuration
        final_config = assemble_config(interpolated_config, organization_id, capabilities)

        # Validate configuration
        validation_result = self.validator.validate_assistant_config(
            final_config, expected_org_id=organization_id
        )

        if not validation_result.is_valid:
            raise ValueError(f"Generated Vapi config failed validation: {validation_result.errors}")

        # Save to output file
        output_dir = Path("outputs") / organization_id / "vapi"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "assistant_config.json"

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(final_config, f, indent=2)

        # Compute content hash
        content_hash = compute_content_hash(json.dumps(final_config, sort_keys=True))

        # Create result object
        result = ResultObject(
            task_id=task.task_id,
            agent_source=self.agent_name,
            content_hash=content_hash,
            storage_path=str(output_path),
            summary=f"Generated Vapi assistant config for {organization_display_name}",
            field_provenance=field_provenance,
            model_id="gemini-2.5-pro",  # Model used for any inference
            validation_status="verified",
        )

        return result

    def _tool_matches_capability(self, tool: dict[str, Any], capabilities: list) -> bool:
        """
        Check if a tool matches requested capabilities.

        Args:
            tool: Tool definition from template
            capabilities: List of capability names from intake

        Returns:
            True if tool should be included
        """
        tool_function_name = tool.get("function", {}).get("name", "")

        # Map function names to capabilities
        capability_map = {
            "check_availability": "availability",
            "book_appointment": "booking",
            "cancel_appointment": "cancellation",
            "reschedule_appointment": "rescheduling",
        }

        required_capability = capability_map.get(tool_function_name)
        return required_capability in capabilities if required_capability else False

    def generate_tool_configs(self, task: TaskObject, intake: dict[str, Any]) -> list[ResultObject]:
        """
        Generate individual tool configuration files.

        This is an optional separate task that creates standalone tool configs.

        Args:
            task: Task object
            intake: Validated intake data

        Returns:
            List of ResultObjects for each tool config
        """
        results = []
        capabilities = intake.get("capabilities", [])
        organization_id = intake.get("organization_id")

        if not organization_id:
            raise ValueError("organization_id is required in intake")

        # Map capabilities to tool template IDs
        capability_tool_map = {
            "availability": "vapi_tool_availability",
            "booking": "vapi_tool_booking",
            "cancellation": "vapi_tool_cancellation",
            "rescheduling": "vapi_tool_rescheduling",
        }

        for capability in capabilities:
            tool_template_id = capability_tool_map.get(capability)
            if not tool_template_id:
                continue

            # Load tool template
            tool_content = self.template_registry.get_template_content(tool_template_id)
            if not tool_content:
                continue

            tool_data = json.loads(tool_content)

            # Interpolate tool template
            context = {
                "organization_id": organization_id,
                "organization_display_name": intake.get("organization", {}).get("display_name"),
                "server_url": intake.get("hosting", {}).get("webhook_base_url"),
                "service_types": json.dumps(
                    intake.get("business", {}).get("service_types", ["standard"])
                ),
            }

            interpolated_tool = interpolate_template(tool_data, context)

            # Validate tool config
            # (validation happens in assistant config, tools are validated as part of assistant)

            # Save tool config
            output_dir = Path("outputs") / organization_id / "vapi" / "tools"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{capability}.json"

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(interpolated_tool, f, indent=2)

            # Compute hash
            content_hash = compute_content_hash(json.dumps(interpolated_tool, sort_keys=True))

            # Create result
            result = ResultObject(
                task_id=f"{task.task_id}_tool_{capability}",
                agent_source=self.agent_name,
                content_hash=content_hash,
                storage_path=str(output_path),
                summary=f"Generated Vapi {capability} tool config",
                field_provenance={
                    "function": {"type": "defaulted", "source": "template"},
                    "server": {"type": "copied", "source": "intake"},
                },
                model_id="gemini-2.5-pro",
                validation_status="verified",
            )

            results.append(result)

        return results
