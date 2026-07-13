"""
CLI entry point for Agent Forge.

Provides command-line interface for onboarding, validation, and configuration.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from cli.config import AgentForgeConfig, load_config, display_config, ConfigurationError
from cli.session import SessionManager
from cli.prompts import InteractivePrompts
from orchestrator.intake_schema import validate_intake, normalize_intake
from orchestrator.planner import Planner
from adapters.supabase_internal import SupabaseInternalClient


def load_intake_file(file_path: str) -> Dict[str, Any]:
    """
    Load intake from JSON file.

    Args:
        file_path: Path to intake JSON file

    Returns:
        Intake dictionary

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If JSON is invalid
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Intake file not found: {file_path}")

    with path.open("r") as f:
        try:
            intake = json.load(f)
            return intake
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in intake file: {e}")


def cmd_config_check(args: argparse.Namespace) -> int:
    """
    Check configuration validity.

    Args:
        args: Command arguments

    Returns:
        Exit code (0 for success)
    """
    try:
        config = load_config()
        print(display_config(config))
        return 0
    except ConfigurationError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


def cmd_intake_validate(args: argparse.Namespace) -> int:
    """
    Validate intake file.

    Args:
        args: Command arguments

    Returns:
        Exit code (0 for success)
    """
    try:
        # Load intake
        intake = load_intake_file(args.file)

        # Validate
        result = validate_intake(intake)

        if result["valid"]:
            print("✓ Intake validation passed")
            print(f"\nNormalized organization ID: {result['normalized_organization_id']}")

            if result.get("warnings"):
                print("\nWarnings:")
                for warning in result["warnings"]:
                    print(f"  ⚠ {warning}")

            return 0
        else:
            print("✗ Intake validation failed", file=sys.stderr)
            print("\nErrors:", file=sys.stderr)
            for error in result["errors"]:
                print(f"  • {error}", file=sys.stderr)

            if result.get("warnings"):
                print("\nWarnings:", file=sys.stderr)
                for warning in result["warnings"]:
                    print(f"  ⚠ {warning}", file=sys.stderr)

            return 1

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


def cmd_onboard(args: argparse.Namespace) -> int:
    """
    Run onboarding command.

    Args:
        args: Command arguments

    Returns:
        Exit code (0 for success)
    """
    try:
        # Load configuration
        config = load_config()

        # Load intake
        intake = load_intake_file(args.intake)

        # Validate intake
        validation_result = validate_intake(intake)

        if not validation_result["valid"]:
            InteractivePrompts.display_error("Intake validation failed")
            print("\nErrors:")
            for error in validation_result["errors"]:
                print(f"  • {error}")
            return 1

        # Normalize intake
        normalized_intake = normalize_intake(intake)

        # Create internal client
        internal_client = SupabaseInternalClient(config)

        # Dry-run mode
        if args.dry_run:
            return _run_dry_run(normalized_intake, internal_client)

        # Execute mode (not implemented in Phase 3)
        if args.execute:
            InteractivePrompts.display_error(
                "Execute mode is not yet implemented. "
                "Phase 3 implements dry-run preview only."
            )
            return 1

        # Default: show help
        print("Please specify --dry-run or --execute mode")
        return 1

    except ConfigurationError as e:
        InteractivePrompts.display_error(f"Configuration error: {e}")
        return 1
    except FileNotFoundError as e:
        InteractivePrompts.display_error(str(e))
        return 1
    except ValueError as e:
        InteractivePrompts.display_error(str(e))
        return 1
    except Exception as e:
        InteractivePrompts.display_error(f"Unexpected error: {e}")
        return 1


def _run_dry_run(
    intake: Dict[str, Any],
    internal_client: SupabaseInternalClient,
) -> int:
    """
    Run dry-run planning.

    Args:
        intake: Normalized intake
        internal_client: Supabase internal client

    Returns:
        Exit code
    """
    organization_id = intake["organization_id"]

    print(f"\nGenerating deployment plan for: {organization_id}")
    print("(Dry-run mode - no external changes will be made)")

    # Create planner
    planner = Planner()

    # Create task graph
    task_graph = planner.create_task_graph(intake)

    # Create dry-run plan
    plan = planner.create_dry_run_plan(task_graph, intake)

    # Display plan and ask for confirmation
    if InteractivePrompts.confirm_plan(plan):
        InteractivePrompts.display_success(
            "Plan confirmed. Use --execute to proceed with deployment."
        )
        return 0
    else:
        print("\nPlan rejected. No changes made.")
        return 0


def main() -> int:
    """
    Main CLI entry point.

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        prog="agent-forge",
        description="Agent Forge - Safe client deployment automation",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # config check command
    config_parser = subparsers.add_parser(
        "config",
        help="Configuration management",
    )
    config_subparsers = config_parser.add_subparsers(dest="config_command")

    config_check_parser = config_subparsers.add_parser(
        "check",
        help="Validate configuration",
    )

    # intake validate command
    intake_parser = subparsers.add_parser(
        "intake",
        help="Intake management",
    )
    intake_subparsers = intake_parser.add_subparsers(dest="intake_command")

    intake_validate_parser = intake_subparsers.add_parser(
        "validate",
        help="Validate intake file",
    )
    intake_validate_parser.add_argument(
        "--file",
        required=True,
        help="Path to intake JSON file",
    )

    # onboard command
    onboard_parser = subparsers.add_parser(
        "onboard",
        help="Run client onboarding",
    )
    onboard_parser.add_argument(
        "--intake",
        required=True,
        help="Path to intake JSON file",
    )
    onboard_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview deployment plan without making changes",
    )
    onboard_parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute deployment with per-action approval",
    )
    onboard_parser.add_argument(
        "--environment",
        choices=["staging", "production"],
        default="staging",
        help="Target environment (default: staging)",
    )

    # Parse arguments
    args = parser.parse_args()

    # Route to command handlers
    if args.command == "config":
        if args.config_command == "check":
            return cmd_config_check(args)
        else:
            config_parser.print_help()
            return 1

    elif args.command == "intake":
        if args.intake_command == "validate":
            return cmd_intake_validate(args)
        else:
            intake_parser.print_help()
            return 1

    elif args.command == "onboard":
        return cmd_onboard(args)

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
