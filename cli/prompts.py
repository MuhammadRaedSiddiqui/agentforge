"""
CLI interactive prompts for Agent Forge.

Provides interactive user prompts for plan confirmation, existing deployment
options, and per-action approval.
"""

import json
from typing import Any


class InteractivePrompts:
    """
    Interactive CLI prompts.

    Handles user interaction for confirmations and approvals.
    """

    @staticmethod
    def confirm_plan(plan: dict[str, Any], auto_approve: bool = False) -> bool:
        """
        Display plan and ask for confirmation.

        Args:
            plan: Dry-run plan dictionary
            auto_approve: Automatically approve without user input

        Returns:
            True if user confirms or auto-approved, False otherwise
        """
        print("\n" + "=" * 70)
        print("DEPLOYMENT PLAN PREVIEW")
        print("=" * 70)

        print(f"\nOrganization: {plan.get('organization_id')}")
        print(f"Intent: {plan.get('intent')}")
        print(f"Capabilities: {', '.join(plan.get('enabled_capabilities', []))}")

        # Show phases
        print("\n--- Phases ---")
        for phase in plan.get("phases", []):
            print(f"  • {phase['name']}: {len(phase['tasks'])} tasks")

        # Show intended changes
        print("\n--- Intended External Changes ---")
        for change in plan.get("intended_changes", []):
            print(f"  • {change['platform']}: {change['operation']}")
            print(f"    {change['description']}")

        # Show approval points
        print("\n--- Approval Points ---")
        for approval in plan.get("approval_points", []):
            print(f"  • {approval['name']}")
            if approval.get("count"):
                print(f"    ({approval['count']})")

        # Show recovery strategy
        print("\n--- Recovery Strategy ---")
        recovery = plan.get("recovery_strategy", {})
        print(f"  • Reconciliation: {recovery.get('reconciliation', 'N/A')}")
        print(f"  • Compensation: {recovery.get('compensation', 'N/A')}")

        print("\n" + "=" * 70)

        # Auto-approve if enabled
        if auto_approve:
            print("\n[AUTO-APPROVED] Plan automatically approved")
            return True

        # Ask for confirmation
        response = input("\nProceed with this plan? (yes/no): ").strip().lower()

        return response in ["yes", "y"]

    @staticmethod
    def handle_existing_deployment(
        existing: dict[str, Any],
        auto_approve: bool = False,
    ) -> str:
        """
        Handle existing deployment situation.

        Args:
            existing: Existing deployment information
            auto_approve: Automatically proceed without user input

        Returns:
            User choice: "proceed", "view", or "abort"
        """
        if auto_approve:
            print("\n[AUTO-APPROVED] Existing deployment detected, proceeding with new deployment")
            return "proceed"

        print("\n" + "!" * 70)
        print("EXISTING DEPLOYMENT DETECTED")
        print("!" * 70)

        print(f"\nOrganization: {existing.get('organization_id')}")
        print(f"Status: {existing.get('status')}")
        print(f"Started: {existing.get('started_at')}")

        if existing.get("requires_recovery"):
            print("\n⚠️  This deployment requires recovery before new work can proceed.")

        print("\nOptions:")
        print("  1. proceed - Continue with new deployment (if allowed)")
        print("  2. view    - View existing deployment details")
        print("  3. abort   - Cancel operation")

        while True:
            response = input("\nChoice (proceed/view/abort): ").strip().lower()

            if response in ["proceed", "view", "abort", "1", "2", "3"]:
                # Map numbers to choices
                if response == "1":
                    return "proceed"
                elif response == "2":
                    return "view"
                elif response == "3":
                    return "abort"
                return response

            print("Invalid choice. Please enter 'proceed', 'view', or 'abort'.")

    @staticmethod
    def display_deployment_details(deployment: dict[str, Any]) -> None:
        """
        Display detailed deployment information.

        Args:
            deployment: Deployment record
        """
        print("\n--- Deployment Details ---")
        print(f"Deployment ID: {deployment.get('deployment_id')}")
        print(f"Organization: {deployment.get('organization_id')}")
        print(f"Intent: {deployment.get('intent')}")
        print(f"Status: {deployment.get('status')}")
        print(f"Started: {deployment.get('started_at')}")

        if deployment.get("completed_at"):
            print(f"Completed: {deployment.get('completed_at')}")

        if deployment.get("failure_summary"):
            print(f"Failure: {deployment.get('failure_summary')}")

    @staticmethod
    def approve_action(
        action: dict[str, Any],
        proposal_hash: str,
        auto_approve: bool = False,
    ) -> str:
        """
        Display action details and request approval.

        Args:
            action: Proposed action details
            proposal_hash: Immutable proposal hash
            auto_approve: Automatically approve without user input

        Returns:
            Decision: "approved", "rejected_abort", or "rejected_revise"
        """
        print("\n" + "=" * 70)
        print("ACTION APPROVAL REQUIRED")
        print("=" * 70)

        print(f"\nPlatform: {action.get('platform')}")
        print(f"Operation: {action.get('operation')}")
        print(f"Target: {json.dumps(action.get('target', {}), indent=2)}")

        # Show change summary
        print("\n--- Change Summary ---")
        print(action.get("change_summary", "N/A"))

        # Show inferred values
        if action.get("inferred_values"):
            print("\n--- Inferred/Default Values ---")
            for key, value in action["inferred_values"].items():
                print(f"  • {key}: {value}")

        # Show validation result
        print("\n--- Validation ---")
        validation = action.get("validation_result", {})
        if validation.get("passed"):
            print("  ✓ All validations passed")
        else:
            print("  ✗ Validation issues detected")
            for issue in validation.get("issues", []):
                print(f"    • {issue}")

        # Show recovery implications
        print("\n--- Recovery Implications ---")
        print(f"  • Reconciliation: {action.get('reconciliation_strategy', 'N/A')}")
        if action.get("compensation_operation"):
            print(f"  • Compensation: {action.get('compensation_operation')}")
        else:
            print("  • Compensation: Not reversible")

        print("\n--- Proposal Hash ---")
        print(f"  {proposal_hash}")

        print("\n" + "=" * 70)

        # Auto-approve if enabled
        if auto_approve:
            print("\n[AUTO-APPROVED] Action automatically approved")
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                f"AUTO-APPROVED: {action.get('platform')} {action.get('operation')} "
                f"(hash: {proposal_hash[:16]}...)"
            )
            return "approved"

        print("\nOptions:")
        print("  1. approve - Execute this action")
        print("  2. abort   - Stop deployment")
        print("  3. revise  - Request changes and regenerate")

        while True:
            response = input("\nDecision (approve/abort/revise): ").strip().lower()

            if response in ["approve", "abort", "revise", "1", "2", "3"]:
                # Map numbers to decisions
                if response == "1":
                    return "approved"
                elif response == "2":
                    return "rejected_abort"
                elif response == "3":
                    return "rejected_revise"

                # Map words to decision types
                if response == "approve":
                    return "approved"
                elif response == "abort":
                    return "rejected_abort"
                elif response == "revise":
                    return "rejected_revise"

            print("Invalid choice. Please enter 'approve', 'abort', or 'revise'.")

    @staticmethod
    def get_revision_instruction() -> str:
        """
        Get revision instruction from user.

        Returns:
            Revision instruction text
        """
        print("\nEnter revision instructions:")
        print("(Describe what should be changed. Press Ctrl+D or Ctrl+Z when done.)\n")

        lines = []
        try:
            while True:
                line = input()
                lines.append(line)
        except EOFError:
            pass

        return "\n".join(lines).strip()

    @staticmethod
    def display_error(message: str) -> None:
        """
        Display error message.

        Args:
            message: Error message
        """
        print("\n" + "!" * 70)
        print("ERROR")
        print("!" * 70)
        print(f"\n{message}\n")

    @staticmethod
    def display_success(message: str) -> None:
        """
        Display success message.

        Args:
            message: Success message
        """
        print("\n" + "=" * 70)
        print("SUCCESS")
        print("=" * 70)
        print(f"\n{message}\n")

    @staticmethod
    def display_warning(message: str) -> None:
        """
        Display warning message.

        Args:
            message: Warning message
        """
        print("\n" + "⚠" * 35)
        print("WARNING")
        print("⚠" * 35)
        print(f"\n{message}\n")

    @staticmethod
    def confirm_action(prompt: str, default: bool = False, auto_approve: bool = False) -> bool:
        """
        Simple yes/no confirmation.

        Args:
            prompt: Confirmation prompt
            default: Default value if user just presses enter
            auto_approve: Automatically approve without user input

        Returns:
            True if confirmed or auto-approved
        """
        if auto_approve:
            print(f"{prompt} [AUTO-APPROVED]")
            return True

        default_str = "Y/n" if default else "y/N"
        response = input(f"{prompt} ({default_str}): ").strip().lower()

        if not response:
            return default

        return response in ["yes", "y"]

    @staticmethod
    def display_recovery_state(recovery_info: dict[str, Any]) -> None:
        """
        Display recovery state for unresolved deployment.

        Implements T119: Partial state summary, completed resources,
        available options: retry/compensate/abort/defer.

        Args:
            recovery_info: Recovery information from detect_restart_recovery
        """
        print("\n" + "!" * 70)
        print("RECOVERY REQUIRED")
        print("!" * 70)

        print(f"\n{recovery_info.get('message', 'Unresolved deployment detected')}")

        print("\n--- Deployment Summary ---")
        print(f"  Deployment ID: {recovery_info.get('deployment_id')}")
        print(f"  Status: {recovery_info.get('deployment_status')}")
        print(f"  Intent: {recovery_info.get('intent')}")
        print(f"  Started: {recovery_info.get('started_at')}")

        # Show completed resources
        completed = recovery_info.get("completed_resources", [])
        if completed:
            print("\n--- Completed Resources ---")
            for resource in completed:
                print(f"  ✓ {resource.get('platform')}: {resource.get('resource_type')}")
                print(f"    ID: {resource.get('remote_resource_id')}")
        else:
            print("\n--- Completed Resources ---")
            print("  None")

        # Show pending recovery actions
        pending = recovery_info.get("recovery_actions", [])
        if pending:
            print("\n--- Pending Recovery Actions ---")
            for action in pending:
                kind = action.get("kind", "unknown")
                operation = action.get("operation", "N/A")
                status = action.get("status", "unknown")
                print(f"  • {kind.upper()}: {operation} ({status})")
        else:
            print("\n--- Pending Recovery Actions ---")
            print("  None")

        print("\n" + "!" * 70)

    @staticmethod
    def choose_recovery_option(available_options: list[str]) -> str:
        """
        Prompt user to choose recovery action.

        Args:
            available_options: List of available option strings

        Returns:
            Chosen option
        """
        print("\n--- Recovery Options ---")

        option_descriptions = {
            "reconcile": "Check remote state to determine if operation succeeded",
            "retry": "Retry the failed operation with fresh approval",
            "compensate": "Undo completed operations (requires approval)",
            "defer": "Mark for later resolution and allow new work",
            "abort": "Abandon this deployment permanently",
        }

        # Display available options
        for i, option in enumerate(available_options, 1):
            description = option_descriptions.get(option, "")
            print(f"  {i}. {option} - {description}")

        print("\n" + "=" * 70)

        while True:
            response = input(f"\nChoice (1-{len(available_options)} or name): ").strip().lower()

            # Try as number
            try:
                choice_num = int(response)
                if 1 <= choice_num <= len(available_options):
                    return available_options[choice_num - 1]
            except ValueError:
                pass

            # Try as name
            if response in available_options:
                return response

            print(f"Invalid choice. Please enter 1-{len(available_options)} or an option name.")

    @staticmethod
    def display_reconciliation_result(result: dict[str, Any]) -> None:
        """
        Display reconciliation result.

        Args:
            result: ReconciliationResult dictionary
        """
        print("\n--- Reconciliation Result ---")
        print(f"Platform: {result.get('platform')}")
        print(f"Operation: {result.get('operation')}")

        if result.get("resource_found"):
            print("\n✓ Resource found remotely")
            print(f"  Remote ID: {result.get('remote_id')}")

            if result.get("matches_expected"):
                print("  State: Matches expected configuration")
            else:
                print("  State: Differs from expected")

        else:
            print("\n✗ Resource not found remotely")

        print(f"\nRecommendation: {result.get('recommendation', 'N/A')}")

        if result.get("can_proceed"):
            print("Status: Can proceed")
        else:
            print("Status: Manual review required")

    @staticmethod
    def display_compensation_ready(compensation: dict[str, Any]) -> None:
        """
        Display compensation action ready for approval.

        Args:
            compensation: Compensation details
        """
        print("\n" + "=" * 70)
        print("COMPENSATION ACTION")
        print("=" * 70)

        print(f"\n{compensation.get('description', 'Compensation operation')}")

        print(f"\nOperation: {compensation.get('compensation_operation')}")

        print("\n⚠️  Warning:")
        print("  This will attempt to undo the completed action.")
        print("  Compensation may not be fully reversible.")
        print("  This requires separate approval.")

        print("\n" + "=" * 70)

    @staticmethod
    def display_retry_ready(retry_info: dict[str, Any]) -> None:
        """
        Display retry information.

        Args:
            retry_info: Retry details
        """
        print("\n--- Retry Information ---")
        print(f"Status: {retry_info.get('status')}")
        print(f"Message: {retry_info.get('message')}")

        if retry_info.get("retry_count"):
            print(f"Retry count: {retry_info.get('retry_count')}")

        if retry_info.get("requires_approval"):
            print("\n⚠️  Fresh approval required for retry")

    @staticmethod
    def display_recovery_failure(failure_info: dict[str, Any]) -> None:
        """
        Display recovery or compensation failure.

        Args:
            failure_info: Failure details
        """
        print("\n" + "!" * 70)
        print("RECOVERY FAILED")
        print("!" * 70)

        print(f"\nStatus: {failure_info.get('status')}")
        print(f"Error: {failure_info.get('error')}")
        print(f"Error Class: {failure_info.get('error_class')}")

        print(f"\nDeployment Status: {failure_info.get('deployment_status')}")

        # Show existing resources
        existing = failure_info.get("existing_resources", [])
        if existing:
            print("\n--- Existing Resources ---")
            for resource in existing:
                print(f"  • {resource.get('platform')}: {resource.get('resource_type')}")
                print(f"    ID: {resource.get('remote_resource_id', 'N/A')}")

        # Show next actions
        next_actions = failure_info.get("next_actions", [])
        if next_actions:
            print("\n--- Next Actions ---")
            for action in next_actions:
                print(f"  • {action}")

        print(f"\nRecommendation: {failure_info.get('recommendation', 'Contact support')}")

        print("\n" + "!" * 70)
