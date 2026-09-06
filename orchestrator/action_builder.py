"""
Onboarding action builder.

Translates a validated deployment package plus intake into the ordered list of
external operations an onboarding requires. Each operation is wrapped in a
ProposedAction so it carries its own approval binding, retry policy,
reconciliation strategy, and compensation operation.

Extracted from the former FullOrchestrator, where this was the only reachable
method: the class's `onboard()` entry point had no callers, so the CLI
constructed a throwaway instance purely to reach this logic. It never used
`self`, so it is a plain function here.
"""

from typing import Any

from orchestrator.approval import ProposedAction, build_proposed_action
from orchestrator.assembler import DeploymentPackage
from orchestrator.intake_schema import needs_database

# Capabilities that map to a Make scenario. Others (e.g. informational-only
# capabilities) produce no Make automation.
MAKE_CAPABILITIES = ("availability", "booking", "cancellation", "rescheduling")


def build_onboarding_actions(
    package: DeploymentPackage,
    intake: dict[str, Any],
) -> list[ProposedAction]:
    """
    Build the ProposedAction list for a new onboarding.

    Args:
        package: Validated deployment package with generated artifacts
        intake: Normalized intake data

    Returns:
        Ordered list of proposed actions, one per required external write
    """
    actions: list[ProposedAction] = []
    organization_id = intake["organization_id"]
    capabilities = intake.get("enabled_capabilities", [])

    # Supabase: insert the organization record. Required by every capability
    # whose Make scenario queries the tenant, not just booking — see
    # DATABASE_BACKED_CAPABILITIES.
    if needs_database(capabilities):
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

    # Vapi: create assistant, its tools, and bind the phone number.
    #
    # These are sub-steps of one action rather than three, because the tool and
    # phone calls both need the assistant id, which does not exist until the
    # create runs — there is nothing to put in a payload at plan time. The
    # expected_outcome therefore has to name all three, so the operator approves
    # what actually happens rather than just the assistant.
    vapi_artifact = next((a for a in package.artifacts if a.agent_source == "vapi_agent"), None)
    if vapi_artifact:
        phone_number_id = intake.get("external_identifiers", {}).get("vapi_phone_number_id")
        outcome = f"Create Vapi assistant and its tools for {organization_id}"
        if phone_number_id:
            outcome += f", and bind phone number {phone_number_id} to it"
        actions.append(
            build_proposed_action(
                platform="vapi",
                operation="create_assistant",
                target=f"assistant/{organization_id}",
                payload={
                    "name": f"{intake.get('business_name', organization_id)}-assistant",
                    "config_path": vapi_artifact.storage_path,
                    "content_hash": vapi_artifact.content_hash,
                    "phone_number_id": phone_number_id,
                },
                retry_policy="none",
                reconciliation_strategy="list_by_name",
                compensation_operation="delete_assistant",
                expected_outcome=outcome,
            )
        )

    # Make: create scenarios for each capability
    for cap in [c for c in capabilities if c in MAKE_CAPABILITIES]:
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
