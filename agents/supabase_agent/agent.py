"""
Supabase agent for generating SQL migrations.

This agent generates SQL migration scripts from intake data and
ground-truth database schema templates, with full provenance tracking.
"""

from pathlib import Path
from typing import Any

from agents.supabase_agent.tools import check_isolation, generate_policy_template, generate_sql
from agents.supabase_agent.validator import SqlValidator
from orchestrator.template_registry import get_template_registry
from shared.hashing import compute_content_hash
from shared.result_object import ResultObject
from shared.task_object import TaskObject


class SupabaseAgent:
    """
    Specialist agent for generating Supabase SQL migrations.

    Responsibilities:
    - Load database schema template
    - Generate organization record INSERT statement
    - Generate RLS policies for tenant isolation
    - Validate against schema requirements
    - Ensure no destructive patterns
    - Record field provenance
    - Return typed ResultObject
    """

    def __init__(self) -> None:
        """Initialize the Supabase agent."""
        self.agent_name = "supabase_agent"
        self.template_registry = get_template_registry()
        self.validator = SqlValidator()

    def execute(self, task: TaskObject, intake: dict[str, Any]) -> ResultObject:
        """
        Execute the Supabase SQL generation task.

        Args:
            task: Task object with generation parameters
            intake: Validated intake data

        Returns:
            ResultObject with generated SQL and provenance
        """
        # Load schema template
        template_content = self.template_registry.get_template_content("database_schema")
        if not template_content:
            raise ValueError("Database schema template not found")

        # Extract required data from intake
        organization_id = intake.get("organization_id")
        if not isinstance(organization_id, str):
            raise ValueError("organization_id must be a string")

        display_name = intake.get("business_name")
        if not isinstance(display_name, str):
            raise ValueError("business_name must be a string")

        phone = intake.get("phone_number")
        email = intake.get("email")
        industry = intake.get("industry")

        # Generate SQL components

        # 1. Base schema (from template)
        base_schema = template_content

        # 2. Generate organization INSERT statement
        org_insert = generate_sql.generate_org_insert(
            organization_id=organization_id,
            display_name=display_name,
            phone=phone,
            email=email,
            industry=industry,
        )

        # 3. Generate RLS policies (already in template, but verify)
        policy_check = generate_policy_template.verify_rls_policies(base_schema)
        if not policy_check:
            raise ValueError("Template missing required RLS policies")

        # 4. Combine into final migration
        final_sql = self._assemble_migration(base_schema, org_insert, organization_id)

        # Validate SQL
        validation_result = self.validator.validate_migration(
            final_sql, expected_org_id=organization_id
        )

        if not validation_result.is_valid:
            raise ValueError(f"Generated SQL failed validation: {validation_result.errors}")

        # Check isolation
        isolation_check = check_isolation(final_sql, organization_id)
        if not isolation_check["is_isolated"]:
            raise ValueError(f"SQL failed isolation check: {isolation_check['issues']}")

        # Save to output file
        output_dir = Path("outputs") / organization_id / "supabase"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "migration.sql"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_sql)

        # Compute content hash
        content_hash = compute_content_hash(final_sql)

        # Mark field provenance
        field_provenance = {
            "organization_id": {"type": "copied", "source": "intake.organization_id"},
            "display_name": {"type": "copied", "source": "intake.business_name"},
            "phone": {"type": "copied", "source": "intake.phone_number"},
            "email": {"type": "copied", "source": "intake.email"},
            "industry": {"type": "copied", "source": "intake.industry"},
            "schema": {"type": "defaulted", "source": "template"},
            "rls_policies": {"type": "defaulted", "source": "template"},
            "indexes": {"type": "defaulted", "source": "template"},
        }

        # Create result object
        result = ResultObject(
            task_id=task.task_id,
            agent_source=self.agent_name,
            content_hash=content_hash,
            storage_path=str(output_path),
            summary=f"Generated SQL migration for {display_name}",
            field_provenance=field_provenance,
            model_id="gemini-2.5-pro",
            validation_status="verified",
        )

        return result

    def _assemble_migration(self, base_schema: str, org_insert: str, organization_id: str) -> str:
        """
        Assemble final migration SQL from components.

        Args:
            base_schema: Base schema template
            org_insert: Organization INSERT statement
            organization_id: Organization identifier

        Returns:
            Complete migration SQL
        """
        # Remove the entire commented INSERT-template section. Leaving the
        # example placeholders in generated SQL makes otherwise valid
        # migrations fail the unresolved-placeholder security check.
        lines = base_schema.split("\n")
        filtered_lines = []
        in_insert_template = False

        for line in lines:
            if "ORGANIZATION RECORD INSERT TEMPLATE" in line:
                in_insert_template = True
                continue
            if in_insert_template and "METADATA" in line:
                in_insert_template = False

            if not in_insert_template:
                filtered_lines.append(line)

        base_sql = "\n".join(filtered_lines)

        # Add header
        migration_header = f"""-- Generated Migration for {organization_id}
-- Generated at: {self._get_timestamp()}
-- Agent Forge Version: 1.0.0
-- DO NOT EDIT THIS FILE MANUALLY

"""

        # Combine components
        final_sql = migration_header + base_sql + "\n\n" + org_insert

        return final_sql

    def _get_timestamp(self) -> str:
        """Get current timestamp as ISO string."""
        from datetime import datetime

        return datetime.now().isoformat()
