"""
CLI interactive prompts for Agent Forge.

Provides interactive user prompts for plan confirmation, existing deployment
options, and per-action approval.
"""

import json
from typing import Any, Dict, List, Optional


class InteractivePrompts:
    """
    Interactive CLI prompts.

    Handles user interaction for confirmations and approvals.
    """

    @staticmethod
    def confirm_plan(plan: Dict[str, Any]) -> bool:
        """
        Display plan and ask for confirmation.

        Args:
            plan: Dry-run plan dictionary

        Returns:
            True if user confirms, False otherwise
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

        # Ask for confirmation
        response = input("\nProceed with this plan? (yes/no): ").strip().lower()

        return response in ["yes", "y"]

    @staticmethod
    def handle_existing_deployment(
        existing: Dict[str, Any]
    ) -> str:
        """
        Handle existing deployment situation.

        Args:
            existing: Existing deployment information

        Returns:
            User choice: "proceed", "view", or "abort"
        """
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
    def display_deployment_details(deployment: Dict[str, Any]) -> None:
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
        action: Dict[str, Any],
        proposal_hash: str,
    ) -> str:
        """
        Display action details and request approval.

        Args:
            action: Proposed action details
            proposal_hash: Immutable proposal hash

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

        print(f"\n--- Proposal Hash ---")
        print(f"  {proposal_hash}")

        print("\n" + "=" * 70)

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
    def confirm_action(prompt: str, default: bool = False) -> bool:
        """
        Simple yes/no confirmation.

        Args:
            prompt: Confirmation prompt
            default: Default value if user just presses enter

        Returns:
            True if confirmed
        """
        default_str = "Y/n" if default else "y/N"
        response = input(f"{prompt} ({default_str}): ").strip().lower()

        if not response:
            return default

        return response in ["yes", "y"]
