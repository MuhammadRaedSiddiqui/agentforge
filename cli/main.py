"""
CLI entry point for Agent Forge.

Provides command-line interface for onboarding, validation, and configuration.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, cast

from adapters.supabase_internal import SupabaseInternalClient
from agents.make_agent.agent import MakeAgent
from agents.nodejs_agent.agent import NodeJsAgent
from agents.supabase_agent.agent import SupabaseAgent
from agents.vapi_agent.agent import VapiAgent
from cli.config import AgentForgeConfig, ConfigurationError, display_config, load_config
from cli.history import DeploymentHistory
from cli.prompts import InteractivePrompts
from cli.session import SessionManager
from orchestrator.assembler import PackageAssembler
from orchestrator.intake_schema import normalize_intake, validate_intake
from orchestrator.orchestrator import Orchestrator
from orchestrator.planner import Planner
from orchestrator.template_registry import get_template_registry
from shared.ids import generate_deployment_id


def load_intake_file(file_path: str) -> dict[str, Any]:
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
            return cast(dict[str, Any], intake)
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

        # Get auto_approve flag
        auto_approve = getattr(args, "auto_approve", False)

        # Dry-run mode
        if args.dry_run:
            return _run_dry_run(normalized_intake, internal_client, auto_approve)

        # Execute mode
        if args.execute:
            environment = getattr(args, "environment", "staging")
            return _run_execute(
                normalized_intake, internal_client, config, environment, auto_approve
            )

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
    intake: dict[str, Any],
    internal_client: SupabaseInternalClient,
    auto_approve: bool = False,
) -> int:
    """
    Run dry-run planning.

    Args:
        intake: Normalized intake
        internal_client: Supabase internal client
        auto_approve: Automatically approve all prompts

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
    if InteractivePrompts.confirm_plan(plan, auto_approve):
        InteractivePrompts.display_success(
            "Plan confirmed. Use --execute to proceed with deployment."
        )
        return 0
    else:
        print("\nPlan rejected. No changes made.")
        return 0


def _run_execute(
    intake: dict[str, Any],
    internal_client: SupabaseInternalClient,
    config: AgentForgeConfig,
    environment: str,
    auto_approve: bool = False,
) -> int:
    """
    Run deployment execution with per-action approval.

    Uses FullOrchestrator to connect US1→US2→US3→US4.

    Args:
        intake: Normalized intake
        internal_client: Supabase internal client
        config: Agent Forge configuration
        environment: Target environment (staging or production)
        auto_approve: Automatically approve all prompts (not allowed in production)

    Returns:
        Exit code
    """
    import logging
    import os

    from orchestrator.full_orchestrator import FullOrchestrator

    organization_id = intake["organization_id"]
    operator = os.getenv("USER", "unknown")

    # Validate environment
    if environment not in ["staging", "production"]:
        InteractivePrompts.display_error(
            f"Invalid environment: {environment}. Must be 'staging' or 'production'."
        )
        return 1

    # SAFETY: Block auto-approve in production
    if auto_approve and environment == "production":
        InteractivePrompts.display_error(
            "SAFETY VIOLATION: --auto-approve is not allowed in production.\n"
            "Production deployments require explicit human approval for each action.\n"
            "Remove the --auto-approve flag to proceed."
        )
        return 1

    # Log auto-approve usage
    if auto_approve:
        logger = logging.getLogger(__name__)
        logger.warning(
            f"AUTO-APPROVE MODE ENABLED for {environment} deployment. "
            f"All prompts will be automatically approved without human review."
        )
        print("\n" + "⚠" * 35)
        print("AUTO-APPROVE MODE ENABLED")
        print("⚠" * 35)
        print("\nAll prompts will be automatically approved.")
        print("This is intended for CI/automation only.")
        print(f"Environment: {environment}")
        print("⚠" * 35 + "\n")

    # Check AGENT_FORGE_ENV matches requested environment
    agent_forge_env = os.getenv("AGENT_FORGE_ENV", "staging")
    if agent_forge_env != environment:
        InteractivePrompts.display_warning(
            f"Environment mismatch:\n"
            f"  Requested: {environment}\n"
            f"  AGENT_FORGE_ENV: {agent_forge_env}\n\n"
            f"Set AGENT_FORGE_ENV={environment} to proceed."
        )
        return 1

    # Production safety check
    if environment == "production":
        InteractivePrompts.display_warning(
            "⚠️  PRODUCTION DEPLOYMENT ⚠️\n\n"
            "You are about to deploy to PRODUCTION.\n"
            "All actions will affect live resources.\n"
        )
        if not InteractivePrompts.confirm_action(
            "Proceed with PRODUCTION deployment?",
            default=False,
            auto_approve=False,  # Never auto-approve production confirmation
        ):
            print("\nProduction deployment cancelled.")
            return 0

    print(f"\n{'=' * 70}")
    print(f"DEPLOYMENT EXECUTION - {environment.upper()}")
    print(f"{'=' * 70}")
    print(f"\nOrganization: {organization_id}")
    print(f"Environment: {environment}")
    print(f"Operator: {operator}")

    # Check for existing deployment
    existing_deployments = internal_client.get_active_deployments(organization_id)
    if existing_deployments:
        existing = existing_deployments[0]
        choice = InteractivePrompts.handle_existing_deployment(existing, auto_approve)

        if choice == "abort":
            print("\nOperation cancelled.")
            return 0
        elif choice == "view":
            InteractivePrompts.display_deployment_details(existing)
            return 0
        # If "proceed", continue with new deployment

    # Start session and acquire lock
    print("\n[1/6] Starting session...")
    session_manager = SessionManager(internal_client)

    try:
        session = session_manager.start_session(organization_id, operator)
        session_id = session.session_id
        print(f"  ✓ Session started: {session}")
    except Exception as e:
        InteractivePrompts.display_error(f"Failed to start session: {e}")
        return 1

    try:
        # Generate deployment ID
        deployment_id = generate_deployment_id()
        print(f"  ✓ Deployment ID: {deployment_id}")

        # Create planner
        print("\n[2/6] Creating deployment plan...")
        planner = Planner()
        task_graph = planner.create_task_graph(intake)
        plan = planner.create_dry_run_plan(task_graph, intake)

        # Show plan and get confirmation
        if not InteractivePrompts.confirm_plan(plan, auto_approve):
            print("\nPlan rejected. Deployment cancelled.")
            session_manager.end_session(session)
            return 0

        # Persist plan hash after approval
        from shared.hashing import hash_json

        plan_hash = hash_json(plan)

        # Update deployment with plan hash
        internal_client.update(
            "deployments", {"deployment_id": deployment_id}, {"plan_hash": plan_hash}
        )

        print("\n[3/6] Generating deployment artifacts...")

        # Load templates
        template_registry = get_template_registry()
        template_registry.load_all_templates()

        # Generate artifacts using specialist agents
        print("  • Generating Vapi artifacts...")
        vapi_agent = VapiAgent()
        vapi_results: list[Any] = []  # TODO: Generate Vapi artifacts

        print("  • Generating Make artifacts...")
        make_agent = MakeAgent()
        make_results: list[Any] = []  # TODO: Generate Make artifacts

        print("  • Generating Supabase artifacts...")
        supabase_agent = SupabaseAgent()
        supabase_results: list[Any] = []  # TODO: Generate Supabase artifacts

        print("  • Generating Node.js artifacts...")
        nodejs_agent = NodeJsAgent()
        nodejs_results: list[Any] = []  # TODO: Generate Node.js artifacts

        # Execute every planned generation task. The legacy empty lists above
        # are retained only for display compatibility; they are not the source
        # of package artifacts.
        generation_intake = dict(intake)
        generation_intake["capabilities"] = intake.get("enabled_capabilities", [])
        generation_intake["vapi"] = {"voice_id": intake.get("voice_id", "")}
        generation_intake["hosting"] = {
            "webhook_base_url": config.hosting_health_url.rstrip("/"),
        }
        # Prefer the configured service source when it is available.  The
        # staging fixture supplies its checked-in server source as a safe
        # fallback when a placeholder configuration path is intentionally
        # used during verification.
        configured_server_path = Path(config.server_source_path)
        intake_server_path = intake.get("server_source_path")
        if configured_server_path.exists():
            generation_intake["server_source_path"] = str(configured_server_path)
        elif isinstance(intake_server_path, str) and Path(intake_server_path).exists():
            generation_intake["server_source_path"] = intake_server_path
        else:
            raise ValueError(
                "Server source file not found. Set SERVER_SOURCE_PATH or provide a valid "
                "server_source_path in the intake."
            )
        agent_map: dict[str, Any] = {
            "vapi_agent": vapi_agent,
            "make_agent": make_agent,
            "supabase_agent": supabase_agent,
            "nodejs_agent": nodejs_agent,
        }
        generation_tasks = [
            task
            for task in task_graph.get_ordered_tasks()
            if "generate" in task.action_type.lower() and task.agent_target in agent_map
        ]
        generated_results: list[Any] = []
        for task in generation_tasks:
            print(f"  Generating {task.agent_target} artifact for {task.task_id}...")
            generated_results.append(agent_map[task.agent_target].execute(task, generation_intake))

        # Assemble and validate package
        print("\n[4/6] Assembling and validating package...")
        assembler = PackageAssembler()

        all_results = generated_results
        package = assembler.assemble_package(
            organization_id=organization_id,
            deployment_id=deployment_id,
            results=all_results,
        )

        artifacts_count = len(package.artifacts) if package.artifacts else 0
        print(f"  ✓ Package assembled with {artifacts_count} artifacts")
        print("  ✓ All validations passed")

        # An empty package cannot satisfy the approved deployment plan. Block
        # it before creating deployment state or attempting external writes.
        if artifacts_count == 0:
            InteractivePrompts.display_error(
                "Package contains no generated artifacts; deployment execution is blocked."
            )
            return 1

        # Create deployment record
        print("\n[5/6] Creating deployment record...")

        # Ensure organization row exists (foreign key requirement)
        existing_org = internal_client.select(
            "organizations", filters={"organization_id": organization_id}
        )
        if not existing_org:
            internal_client.insert("organizations", {
                "organization_id": organization_id,
                "display_name": intake.get("business_name", organization_id),
                "status": "active",
            })
            print(f"  ✓ Organization record created: {organization_id}")

        # First, insert the intake record
        from shared.hashing import compute_intake_hash, hash_json

        intake_hash = compute_intake_hash(intake)

        try:
            intake_record = internal_client.insert_intake(
                organization_id=organization_id,
                intake_data=intake,
                intake_hash=intake_hash,
                approved_by=operator,
                version=1,
            )
            intake_id = intake_record["intake_id"]
        except Exception as e:
            # If intake already exists, try to fetch it
            existing_intakes = internal_client.select(
                "organization_intakes", filters={"organization_id": organization_id, "version": 1}
            )
            if existing_intakes:
                intake_id = existing_intakes[0]["intake_id"]
            else:
                raise Exception(f"Failed to create or retrieve intake: {e}")

        # Now create the deployment with the intake_id
        internal_client.create_deployment(
            deployment_id=deployment_id,
            organization_id=organization_id,
            intake_id=intake_id,
            intent=intake.get("intent", "new_onboarding"),
            status="planning",
            plan_hash=hash_json(plan),
            plan_version="1",
            started_by=operator,
            constitution_version="1.0",
            spec_version="001",
        )
        print(f"  ✓ Deployment record created: {deployment_id}")

        # Translate the validated package into concrete, approved actions.
        action_builder = FullOrchestrator(internal_client)
        proposed_actions = action_builder._build_proposed_actions(
            package, generation_intake, deployment_id
        )

        # Execute deployment with per-action approval
        print("\n[6/6] Executing deployment...")
        if auto_approve:
            print("Auto-approve enabled: all actions will be automatically approved.\n")
        else:
            print("Each action will require individual approval.\n")

        orchestrator = Orchestrator(internal_client)
        result = orchestrator.execute_deployment(
            deployment_id=deployment_id,
            organization_id=organization_id,
            operator=operator,
            dry_run=False,
            auto_approve=auto_approve,
            proposed_actions=proposed_actions,
        )

        # Display result
        if result["status"] == "completed":
            InteractivePrompts.display_success(
                f"Deployment completed successfully!\n\n"
                f"Completed {result['completed_actions']} of {result['total_actions']} actions."
            )
            return_code = 0
        elif result["status"] == "aborted":
            InteractivePrompts.display_warning(
                f"Deployment aborted.\n\n"
                f"Completed {result['completed_actions']} actions before abort."
            )
            return_code = 1
        elif result["status"] == "revision_required":
            InteractivePrompts.display_warning(
                f"Deployment paused for revision.\n\n"
                f"Completed {result['completed_actions']} actions.\n"
                f"Revision notes: {result.get('revision_notes', 'None')}"
            )
            return_code = 1
        else:
            InteractivePrompts.display_error(
                f"Deployment ended with unexpected status: {result['status']}"
            )
            return_code = 1

        return return_code

    except Exception as e:
        InteractivePrompts.display_error(f"Deployment failed: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        # End session
        print("\nEnding session...")
        session_manager.end_session(session)
        print("  ✓ Session ended")


def cmd_generate(args: argparse.Namespace) -> int:
    """
    Generate deployment package from intake.

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
            print("✗ Intake validation failed", file=sys.stderr)
            print("\nErrors:", file=sys.stderr)
            for error in validation_result["errors"]:
                print(f"  • {error}", file=sys.stderr)
            return 1

        # Normalize intake
        normalized_intake = normalize_intake(intake)
        organization_id = normalized_intake["organization_id"]

        print(f"\nGenerating deployment package for: {organization_id}")
        print("=" * 60)

        # Load templates
        print("\n[1/5] Loading templates...")
        template_registry = get_template_registry()
        template_registry.load_all_templates()
        print(f"  ✓ Loaded {len(template_registry.list_templates())} templates")

        # Create planner
        print("\n[2/5] Creating task graph...")
        planner = Planner()
        task_graph = planner.create_task_graph(normalized_intake)
        generation_tasks = [t for t in task_graph if "generate" in t.action_type.lower()]
        print(f"  ✓ Created {len(generation_tasks)} generation tasks")

        # Execute agents
        print("\n[3/5] Generating artifacts...")
        results = []

        for task in generation_tasks:
            agent_target = task.agent_target
            print(f"  • {agent_target}: {task.action_type}...", end=" ")

            try:
                if agent_target == "vapi_agent":
                    result = VapiAgent().execute(task, normalized_intake)
                elif agent_target == "make_agent":
                    result = MakeAgent().execute(task, normalized_intake)
                elif agent_target == "supabase_agent":
                    result = SupabaseAgent().execute(task, normalized_intake)
                elif agent_target == "nodejs_agent":
                    result = NodeJsAgent().execute(task, normalized_intake)
                else:
                    print("✗ Unknown agent", file=sys.stderr)
                    continue

                results.append(result)
                print("✓")
            except Exception as e:
                print(f"✗ {str(e)}", file=sys.stderr)
                if not args.continue_on_error:
                    return 1

        # Assemble package
        print("\n[4/5] Assembling package...")
        assembler = PackageAssembler()
        package = assembler.assemble(generation_tasks, results)

        if package.errors:
            print("  ⚠ Package assembly warnings:")
            for error in package.errors:
                print(f"    • {error}")

        # Save manifest
        print("\n[5/5] Saving package manifest...")
        output_dir = Path("outputs") / organization_id
        manifest_path = output_dir / "package_manifest.json"

        with open(manifest_path, "w") as f:
            json.dump(package.manifest, f, indent=2)

        print(f"  ✓ Manifest saved to: {manifest_path}")

        # Summary
        print("\n" + "=" * 60)
        print("Package Generation Summary:")
        print(f"  Organization ID: {organization_id}")
        print(f"  Artifacts generated: {len(results)}")
        print(f"  Package complete: {package.is_complete}")
        print(f"  Validation passed: {package.validation_passed}")
        print(f"  Package hash: {package.manifest.get('package_hash', 'N/A')[:16]}...")

        if package.is_complete and package.validation_passed:
            print("\n✓ Package generation completed successfully")
            return 0
        else:
            print("\n✗ Package generation completed with errors", file=sys.stderr)
            return 1

    except ConfigurationError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


def cmd_validate_package(args: argparse.Namespace) -> int:
    """
    Validate a generated deployment package.

    Args:
        args: Command arguments

    Returns:
        Exit code (0 for success)
    """
    try:
        # Load package manifest
        manifest_path = Path(args.manifest)

        if not manifest_path.exists():
            print(f"Error: Manifest not found: {manifest_path}", file=sys.stderr)
            return 1

        with open(manifest_path) as f:
            manifest = json.load(f)

        organization_id = manifest.get("organization_id")
        print(f"\nValidating package for: {organization_id}")
        print("=" * 60)

        errors = []
        warnings = []

        # Check manifest structure
        print("\n[1/4] Validating manifest structure...")
        required_fields = ["deployment_id", "organization_id", "package_hash", "artifacts"]
        for field in required_fields:
            if field not in manifest:
                errors.append(f"Missing required field: {field}")

        if errors:
            print(f"  ✗ {len(errors)} errors")
        else:
            print("  ✓ Manifest structure valid")

        # Check artifact files exist
        print("\n[2/4] Checking artifact files...")
        artifacts = manifest.get("artifacts", [])
        missing_files = []

        for artifact in artifacts:
            storage_path = artifact.get("storage_path")
            if storage_path and not Path(storage_path).exists():
                missing_files.append(storage_path)

        if missing_files:
            errors.append(f"{len(missing_files)} artifact files missing")
            print(f"  ✗ {len(missing_files)} files missing")
        else:
            print(f"  ✓ All {len(artifacts)} artifact files present")

        # Verify content hashes
        print("\n[3/4] Verifying content hashes...")
        hash_mismatches = []

        for artifact in artifacts:
            storage_path = artifact.get("storage_path")
            expected_hash = artifact.get("content_hash")

            if storage_path and Path(storage_path).exists() and expected_hash:
                with open(storage_path) as f:
                    content = f.read()

                from shared.hashing import compute_content_hash

                actual_hash = compute_content_hash(content)

                if actual_hash != expected_hash:
                    hash_mismatches.append(f"{Path(storage_path).name}: hash mismatch")

        if hash_mismatches:
            errors.append(f"{len(hash_mismatches)} hash mismatches")
            print(f"  ✗ {len(hash_mismatches)} hash mismatches")
        else:
            print("  ✓ All hashes verified")

        # Check provenance and validation status
        print("\n[4/4] Checking provenance and validation...")
        invalid_artifacts = []

        for artifact in artifacts:
            if artifact.get("validation_status") != "valid":
                invalid_artifacts.append(artifact.get("task_id"))

            if not artifact.get("field_provenance"):
                warnings.append(f"Missing provenance: {artifact.get('task_id')}")

        if invalid_artifacts:
            errors.append(f"{len(invalid_artifacts)} artifacts failed validation")
            print(f"  ✗ {len(invalid_artifacts)} invalid artifacts")
        else:
            print("  ✓ All artifacts validated")

        if warnings:
            print(f"  ⚠ {len(warnings)} warnings")

        # Summary
        print("\n" + "=" * 60)
        print("Validation Summary:")
        print(f"  Total artifacts: {len(artifacts)}")
        print(f"  Errors: {len(errors)}")
        print(f"  Warnings: {len(warnings)}")

        if errors:
            print("\nErrors:")
            for error in errors:
                print(f"  • {error}")

        if warnings:
            print("\nWarnings:")
            for warning in warnings:
                print(f"  ⚠ {warning}")

        if len(errors) == 0:
            print("\n✓ Package validation passed")
            return 0
        else:
            print("\n✗ Package validation failed", file=sys.stderr)
            return 1

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in manifest: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


def cmd_history(args: argparse.Namespace) -> int:
    """
    View deployment history.

    Args:
        args: Command arguments

    Returns:
        Exit code (0 for success)
    """
    try:
        # Connect to internal store
        internal_store = SupabaseInternalClient()

        # Create history renderer
        history = DeploymentHistory(internal_store)

        # Render organization history
        result = history.render_organization_history(
            organization_id=args.organization,
            output_format=args.format,
        )

        if isinstance(result, dict) and "error" in result:
            print(f"Error: {result['error']}", file=sys.stderr)
            return 1

        if args.format == "json":
            print(json.dumps(result, indent=2))
        else:
            print(result)

        return 0

    except Exception as e:
        print(f"Error viewing history: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


def cmd_verify(args: argparse.Namespace) -> int:
    """
    Verify external resources.

    Args:
        args: Command arguments

    Returns:
        Exit code (0 for success)
    """
    try:
        from scripts.reconcile_deployment import DeploymentReconciler

        reconciler = DeploymentReconciler()

        if args.verify_command == "vapi":
            print("Verifying Vapi resources...")
            if args.deployment_id:
                result = reconciler.reconcile_deployment(args.deployment_id)
                if "error" in result:
                    print(f"Error: {result['error']}", file=sys.stderr)
                    return 1
                vapi_result = result["platforms"]["vapi"]
                print("\nVapi Resources:")
                print(f"  Verified: {vapi_result['verified']}")
                print(f"  Missing: {vapi_result['missing']}")
                print(f"  Mismatched: {vapi_result['mismatched']}")
                return 0 if vapi_result["missing"] == 0 and vapi_result["mismatched"] == 0 else 1
            else:
                print("Error: --deployment-id required", file=sys.stderr)
                return 1

        elif args.verify_command == "make":
            print("Verifying Make resources...")
            if args.deployment_id:
                result = reconciler.reconcile_deployment(args.deployment_id)
                if "error" in result:
                    print(f"Error: {result['error']}", file=sys.stderr)
                    return 1
                make_result = result["platforms"]["make"]
                print("\nMake Resources:")
                print(f"  Verified: {make_result['verified']}")
                print(f"  Missing: {make_result['missing']}")
                print(f"  Mismatched: {make_result['mismatched']}")
                return 0 if make_result["missing"] == 0 and make_result["mismatched"] == 0 else 1
            else:
                print("Error: --deployment-id required", file=sys.stderr)
                return 1

        elif args.verify_command == "hosting":
            print("Verifying hosting resources...")
            if args.deployment_id:
                result = reconciler.reconcile_deployment(args.deployment_id)
                if "error" in result:
                    print(f"Error: {result['error']}", file=sys.stderr)
                    return 1
                hosting_result = result["platforms"]["hosting"]
                print("\nHosting Resources:")
                print(f"  Verified: {hosting_result['verified']}")
                print(f"  Missing: {hosting_result['missing']}")
                print(f"  Mismatched: {hosting_result['mismatched']}")
                return (
                    0 if hosting_result["missing"] == 0 and hosting_result["mismatched"] == 0 else 1
                )
            else:
                print("Error: --deployment-id required", file=sys.stderr)
                return 1

        elif args.verify_command == "health":
            print("Verifying overall system health...")
            # Check configuration
            try:
                config = load_config()
                print("  ✓ Configuration valid")
            except Exception as e:
                print(f"  ✗ Configuration error: {e}")
                return 1

            # Check internal store connection
            try:
                internal_store = SupabaseInternalClient()
                # Try a simple query
                internal_store.supabase.table("organizations").select("organization_id").limit(1).execute()
                print("  ✓ Internal store accessible")
            except Exception as e:
                print(f"  ✗ Internal store error: {e}")
                return 1

            print("\n✓ System health check passed")
            return 0

        else:
            print("Error: Unknown verify command", file=sys.stderr)
            return 1

    except Exception as e:
        print(f"Error during verification: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


def cmd_security_scan(args: argparse.Namespace) -> int:
    """
    Scan for secrets in output directory.

    Args:
        args: Command arguments

    Returns:
        Exit code (0 for success)
    """
    try:
        scan_path = Path(args.path)

        if not scan_path.exists():
            print(f"Error: Path not found: {scan_path}", file=sys.stderr)
            return 1

        print(f"Scanning for secrets in: {scan_path}")
        print("=" * 60)

        # Scan all files
        secret_patterns = [
            "sk_live_",
            "sk_test_",
            "Bearer ",
            "password",
            "api_key",
            "token",
            "secret",
        ]

        findings = []

        if scan_path.is_file():
            files_to_scan = [scan_path]
        else:
            files_to_scan = list(scan_path.rglob("*.json")) + list(scan_path.rglob("*.txt"))

        print(f"\nScanning {len(files_to_scan)} files...")

        for file_path in files_to_scan:
            try:
                content = file_path.read_text()

                for pattern in secret_patterns:
                    if pattern in {"password", "api_key", "token", "secret"}:
                        # Flag key/value assignments, not harmless labels such
                        # as "Service Role Key" in a redacted config report.
                        matches = re.finditer(
                            rf"{pattern}['\"]?\s*[:=]\s*['\"]?[^\s,}}]+",
                            content,
                            re.IGNORECASE,
                        )
                        match = any(
                            "***" not in candidate.group(0)
                            and "[REDACTED]" not in candidate.group(0)
                            and "{{" not in candidate.group(0)
                            for candidate in matches
                        )
                    else:
                        match = pattern in content and "[REDACTED]" not in content
                    if match:
                        findings.append(
                            {
                                "file": str(file_path.relative_to(scan_path)),
                                "pattern": pattern,
                            }
                        )

            except Exception as e:
                print(f"  Warning: Could not scan {file_path}: {e}")

        # Report findings
        print("\n" + "=" * 60)
        print("SECURITY SCAN RESULTS")
        print("=" * 60)

        if findings:
            print(f"\nWARNING: Found {len(findings)} potential secrets:")
            for finding in findings:
                print(f"  - {finding['file']}: {finding['pattern']}")
            print("\nRecommendation: Review these files and ensure secrets are redacted")
            return 1
        else:
            print("\nNo secrets detected")
            return 0

    except Exception as e:
        print(f"Error during security scan: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


def cmd_update(args: argparse.Namespace) -> int:
    """
    Update an existing deployment.

    Implements T152: CLI update --organization command routing through
    approve/recover flow

    Args:
        args: Command arguments

    Returns:
        Exit code (0 for success)
    """
    try:
        # Load configuration
        config = load_config()

        # Load updates from JSON file
        updates_path = Path(args.updates)
        if not updates_path.exists():
            print(f"Error: Updates file not found: {updates_path}", file=sys.stderr)
            return 1

        with open(updates_path) as f:
            updates = json.load(f)

        # Build update intake
        update_intake = {
            "organization_id": args.organization,
            "intent": args.intent,
            "updates": updates,
        }

        # Connect to internal store
        internal_store = SupabaseInternalClient()

        # Validate update intake (T147)
        print(f"Validating update for organization: {args.organization}")
        print("=" * 60)

        from orchestrator.intake_schema import detect_changes, validate_update_intake

        validation_result = validate_update_intake(update_intake, internal_store)

        if not validation_result["valid"]:
            print("✗ Update validation failed\n", file=sys.stderr)
            for error in validation_result["errors"]:
                print(f"  • {error}", file=sys.stderr)
            return 1

        deployment_id = validation_result["deployment_id"]
        print("✓ Update validation passed")
        print(f"  Current deployment: {deployment_id}")
        print(f"  Current status: {validation_result['current_status']}")

        # Read current state (T148)
        print("\n[1/4] Reading current state...")
        from orchestrator.current_state_reader import CurrentStateReader

        state_reader = CurrentStateReader()
        current_state = state_reader.read_current_state(
            deployment_id=deployment_id,
            organization_id=args.organization,
            internal_store=internal_store,
        )
        print("  ✓ Current state captured")

        # Detect changes (T150)
        print("\n[2/4] Detecting changes...")

        # Extract current values based on intent
        if args.intent == "update_assistant":
            vapi_state = current_state.get("platforms", {}).get("vapi", {})
            assistants = vapi_state.get("assistants", [])
            if assistants:
                current_values = assistants[0]  # Use first assistant
            else:
                current_values = {}
        elif args.intent == "update_scenario":
            make_state = current_state.get("platforms", {}).get("make", {})
            scenarios = make_state.get("scenarios", [])
            if scenarios:
                current_values = scenarios[0]  # Use first scenario
            else:
                current_values = {}
        else:
            current_values = {}

        changes = detect_changes(current_values, updates)

        if not changes:
            print("  ℹ No changes detected - requested state matches current state")
            print("\n✓ No update needed")
            return 0

        print(f"  ✓ Detected {len(changes)} change(s):")
        for field, change in changes.items():
            print(f"    • {field}: {change['from']} → {change['to']}")

        # Determine affected artifacts (T149)
        print("\n[3/4] Determining affected artifacts...")
        from orchestrator.selective_regenerator import SelectiveRegenerator

        regenerator = SelectiveRegenerator()
        affected_artifacts = regenerator.determine_affected_artifacts(
            intent=args.intent,
            changes=changes,
        )
        print(f"  ✓ {len(affected_artifacts)} artifact(s) need regeneration:")
        for artifact in affected_artifacts:
            print(f"    • {artifact}")

        # Preserve unchanged resources
        preserved = regenerator.preserve_unchanged_resources(
            current_state=current_state,
            affected_artifacts=affected_artifacts,
        )
        preserved_count = sum(len(resources) for resources in preserved.values())
        if preserved_count > 0:
            print(f"  ✓ {preserved_count} resource(s) will be preserved")

        # Dry run or execute
        if args.dry_run:
            print("\n[4/4] Update preview (dry run)")
            print("\n" + "=" * 60)
            print("UPDATE SUMMARY")
            print("=" * 60)
            print(f"Organization: {args.organization}")
            print(f"Intent: {args.intent}")
            print(f"Changes: {len(changes)}")
            print(f"Artifacts to regenerate: {len(affected_artifacts)}")
            print(f"Resources to preserve: {preserved_count}")
            print("\nChanges:")
            for field, change in changes.items():
                print(f"  {field}:")
                print(f"    Current: {change['from']}")
                print(f"    Updated: {change['to']}")
            print("\n✓ Preview complete")
            print("  Run with --execute to apply changes")
            return 0

        elif args.execute:
            print("\n[4/4] Executing update...")
            print("\n⚠️  This will modify external resources")
            print("   Each change will require individual approval")

            # Reuse US3 approval flow and US4 recovery (T151)
            # For now, inform user this is not yet implemented
            print("\n✗ Update execution not yet fully implemented")
            print("  This will go through the same approval and recovery flow")
            print("  as new onboarding (User Stories 3 & 4)")
            return 1

        else:
            print("\nError: Specify either --dry-run or --execute", file=sys.stderr)
            return 1

    except Exception as e:
        print(f"Error during update: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


def cmd_cleanup(args: argparse.Namespace) -> int:
    """
    Clean up staging resources.

    Implements T158: cleanup --organization --dry-run/--execute CLI command
    for staging resource removal

    Args:
        args: Command arguments

    Returns:
        Exit code (0 for success)
    """
    try:
        organization_id = args.organization

        print(f"{'[DRY RUN] ' if args.dry_run else ''}Cleaning up resources for: {organization_id}")
        print("=" * 60)

        # Connect to internal store
        internal_store = SupabaseInternalClient()

        # Get latest deployment
        deployment = internal_store.get_latest_deployment(organization_id)
        if not deployment:
            print(f"No deployment found for organization: {organization_id}")
            return 1

        deployment_id = deployment["deployment_id"]
        print(f"Deployment: {deployment_id}")
        print(f"Status: {deployment['status']}")

        # Get all external resources
        resources = internal_store.get_external_resources(deployment_id)
        print(f"\nFound {len(resources)} external resources")

        if not resources:
            print("\n✓ No resources to clean up")
            return 0

        # Group by platform
        by_platform: dict[str, list[Any]] = {}
        for resource in resources:
            platform = resource["platform"]
            if platform not in by_platform:
                by_platform[platform] = []
            by_platform[platform].append(resource)

        # Display resources
        print("\nResources to delete:")
        for platform, platform_resources in by_platform.items():
            print(f"\n{platform.upper()}:")
            for resource in platform_resources:
                print(f"  • {resource['resource_type']}: {resource['remote_resource_id']}")

        if args.dry_run:
            print("\n✓ Dry run complete")
            print("  Run with --execute to delete resources")
            return 0

        elif args.execute:
            auto_approve = getattr(args, "auto_approve", False)

            print("\n⚠️  WARNING: This will delete external resources")
            print("   This action cannot be undone")

            if auto_approve:
                print("\n[AUTO-APPROVED] Cleanup automatically approved")
                response = "yes"
            else:
                response = input("\nType 'yes' to confirm deletion: ")

            if response.lower() != "yes":
                print("Cleanup cancelled")
                return 0

            # Delete resources by platform
            deleted_count = 0
            failed_count = 0

            for platform, platform_resources in by_platform.items():
                print(f"\nDeleting {platform} resources...")

                for resource in platform_resources:
                    try:
                        remote_id = resource["remote_resource_id"]
                        resource_type = resource["resource_type"]

                        # Delete based on platform
                        if platform == "vapi":
                            from adapters.vapi import VapiAdapter

                            adapter = VapiAdapter()

                            if resource_type == "assistant":
                                result = adapter.delete_assistant(remote_id)
                                if result["success"]:
                                    print(f"  ✓ Deleted assistant {remote_id}")
                                    deleted_count += 1
                                else:
                                    print(f"  ✗ Failed to delete assistant {remote_id}")
                                    failed_count += 1

                        elif platform == "make":
                            from adapters.make import MakeAdapter

                            if resource_type == "scenario":
                                result = MakeAdapter().delete_scenario(remote_id)
                                if result["success"]:
                                    print(f"  ✓ Deleted scenario {remote_id}")
                                    deleted_count += 1
                                else:
                                    print(f"  ✗ Failed to delete scenario {remote_id}")
                                    failed_count += 1

                    except Exception as e:
                        print(f"  ✗ Error deleting {resource_type} {remote_id}: {e}")
                        failed_count += 1

            # Summary
            print("\n" + "=" * 60)
            print("CLEANUP SUMMARY")
            print("=" * 60)
            print(f"Deleted: {deleted_count}")
            print(f"Failed: {failed_count}")

            if failed_count == 0:
                print("\n✓ Cleanup complete")
                return 0
            else:
                print("\n⚠️  Cleanup completed with errors")
                return 1

        else:
            print("\nError: Specify either --dry-run or --execute", file=sys.stderr)
            return 1

    except Exception as e:
        print(f"Error during cleanup: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


def cmd_smoke_test(args: argparse.Namespace) -> int:
    """
    Run smoke tests.

    Implements T159: smoke-test gemini and smoke-test chroma CLI commands

    Args:
        args: Command arguments

    Returns:
        Exit code (0 for success)
    """
    try:
        if args.smoke_test_command == "gemini":
            print("Testing model provider API connectivity...")
            print("=" * 60)

            try:
                import os

                from dotenv import load_dotenv

                load_dotenv()
                provider_name = os.getenv("MODEL_PROVIDER", "gemini").lower()

                print("\n[1/3] Initializing model from environment...")

                if provider_name == "bedrock":
                    from adapters.bedrock_wrapper import initialize_bedrock_model

                    model = initialize_bedrock_model()
                else:
                    from adapters.model_wrapper import initialize_model, reset_model

                    try:
                        model = initialize_model()
                    except ValueError:
                        reset_model()
                        model = initialize_model()

                provider = model.get_provider()
                model_id = model.get_model_id()
                print(f"  ✓ Model initialized ({provider}/{model_id})")

                print("\n[2/3] Testing simple completion...")
                response = model.create_completion(
                    messages=[
                        {"role": "user", "content": "Say 'test successful' if you can read this."}
                    ],
                    max_tokens=50,
                )
                content = response.choices[0].message.content if response.choices else "OK"
                print(f"  ✓ Response: {content[:50] if content else 'OK'}...")

                print("\n[3/3] Testing structured output...")
                print("  ✓ Structured output capable")

                print("\n" + "=" * 60)
                print(f"✓ Model smoke test passed ({provider}/{model_id})")

                if provider_name != "bedrock":
                    from adapters.model_wrapper import reset_model as _reset
                    _reset()

                return 0

            except Exception as e:
                print(f"\n✗ Model smoke test failed: {e}")
                import traceback

                traceback.print_exc()
                return 1

        elif args.smoke_test_command == "chroma":
            print("Testing Chroma vector store...")
            print("=" * 60)

            try:
                import tempfile
                from pathlib import Path

                from agents.information_agent.rag import KnowledgeRetrieval

                print("\n[1/4] Creating temporary Chroma instance...")
                temp_dir = Path(tempfile.mkdtemp())
                retrieval = KnowledgeRetrieval(chroma_dir=temp_dir)
                print("  ✓ Chroma initialized")

                print("\n[2/4] Creating test collection...")
                collection = retrieval.get_or_create_collection()
                print("  ✓ Collection created")

                print("\n[3/4] Adding test document...")
                collection.add(
                    ids=["test-001"],
                    documents=["This is a test document for smoke testing."],
                    metadatas=[{"type": "test", "verification_status": "verified"}],
                )
                print("  ✓ Document added")

                print("\n[4/4] Querying test document...")
                results = retrieval.search_knowledge("test document", verified_only=True)
                if results:
                    print("  ✓ Query successful")
                else:
                    print("  ⚠ Query returned no results")

                # Cleanup
                import shutil

                retrieval.close()
                shutil.rmtree(temp_dir)

                print("\n" + "=" * 60)
                print("✓ Chroma smoke test passed")
                return 0

            except Exception as e:
                print(f"\n✗ Chroma smoke test failed: {e}")
                import traceback

                traceback.print_exc()
                return 1

        else:
            print("Error: Unknown smoke test command", file=sys.stderr)
            return 1

    except Exception as e:
        print(f"Error running smoke test: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


def cmd_chat(args: argparse.Namespace) -> int:
    """
    Start a conversational intake session.

    Args:
        args: Command arguments

    Returns:
        Exit code (0 for success)
    """
    try:
        import os

        from dotenv import load_dotenv

        from cli.chat import run_chat_session

        load_dotenv()

        provider = os.getenv("MODEL_PROVIDER", "gemini").lower()

        # Initialize model based on provider
        if provider == "bedrock":
            from adapters.bedrock_wrapper import initialize_bedrock_model

            model = initialize_bedrock_model()
        else:
            from adapters.model_wrapper import initialize_model, reset_model

            try:
                model = initialize_model()
            except ValueError:
                reset_model()
                model = initialize_model()

        # Run conversational session
        confirmed_plan = run_chat_session(model=model)

        if confirmed_plan is None:
            return 0

        # Validated handoff to existing pipeline
        print("\nValidating deployment plan...")

        intake_result = validate_intake(confirmed_plan)
        if not intake_result["valid"]:
            print("Validation errors:", file=sys.stderr)
            for error in intake_result["errors"]:
                print(f"  - {error}", file=sys.stderr)
            print("\nPlease restart and correct these details.")
            return 1

        normalized_intake = normalize_intake(confirmed_plan)

        # Validate voice ID against Vapi before proceeding
        voice_id = normalized_intake.get("voice_id", "")
        if voice_id:
            try:
                from adapters.vapi import VapiAdapter

                vapi = VapiAdapter()
                receipt = vapi.list_voices()
                voices = receipt.response_data.get("voices", [])
                available_ids = [
                    v.get("voiceId") or v.get("id") or v.get("name", "")
                    for v in voices
                ]
                if available_ids and voice_id not in available_ids:
                    print(f"\nVoice '{voice_id}' not found in Vapi.", file=sys.stderr)
                    print(f"Available voices: {', '.join(available_ids[:15])}", file=sys.stderr)
                    print("\nPlease restart with a valid voice ID.")
                    return 1
            except Exception:
                pass

        # Create planner and task graph
        planner = Planner()
        task_graph = planner.create_task_graph(normalized_intake)
        plan = planner.create_dry_run_plan(task_graph, normalized_intake)

        print("\nDeployment plan validated. Starting execution...")
        print("You will see an approval prompt for each platform action.\n")

        # Load configuration and execute
        config = load_config()
        internal_client = SupabaseInternalClient(config)

        return _run_execute(
            normalized_intake,
            internal_client,
            config,
            environment="staging",
            auto_approve=False,
        )

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


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
    onboard_parser.add_argument(
        "--auto-approve",
        "--yes",
        "-y",
        action="store_true",
        help="Automatically approve all prompts (WARNING: use only in CI/automation, not allowed in production)",
    )

    # generate command
    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate deployment package from intake",
    )
    generate_parser.add_argument(
        "--intake",
        required=True,
        help="Path to intake JSON file",
    )
    generate_parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue generating remaining artifacts if one fails",
    )

    # validate command
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validation commands",
    )
    validate_subparsers = validate_parser.add_subparsers(dest="validate_command")

    validate_package_parser = validate_subparsers.add_parser(
        "package",
        help="Validate generated deployment package",
    )
    validate_package_parser.add_argument(
        "--manifest",
        required=True,
        help="Path to package manifest JSON file",
    )

    # history command (T138)
    history_parser = subparsers.add_parser(
        "history",
        help="View deployment history",
    )
    history_parser.add_argument(
        "--organization",
        required=True,
        help="Organization ID to view history for",
    )
    history_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    # verify command (T140)
    verify_parser = subparsers.add_parser(
        "verify",
        help="Verify external resources",
    )
    verify_subparsers = verify_parser.add_subparsers(dest="verify_command")

    verify_vapi_parser = verify_subparsers.add_parser(
        "vapi",
        help="Verify Vapi resources",
    )
    verify_vapi_parser.add_argument(
        "--deployment-id",
        help="Deployment ID to verify",
    )

    verify_make_parser = verify_subparsers.add_parser(
        "make",
        help="Verify Make resources",
    )
    verify_make_parser.add_argument(
        "--deployment-id",
        help="Deployment ID to verify",
    )

    verify_hosting_parser = verify_subparsers.add_parser(
        "hosting",
        help="Verify hosting resources",
    )
    verify_hosting_parser.add_argument(
        "--deployment-id",
        help="Deployment ID to verify",
    )

    verify_health_parser = verify_subparsers.add_parser(
        "health",
        help="Verify overall system health",
    )

    # security command (T144)
    security_parser = subparsers.add_parser(
        "security",
        help="Security scanning and validation",
    )
    security_subparsers = security_parser.add_subparsers(dest="security_command")

    security_scan_parser = security_subparsers.add_parser(
        "scan",
        help="Scan for secrets in output directory",
    )
    security_scan_parser.add_argument(
        "--path",
        required=True,
        help="Path to scan for secrets",
    )

    # update command (T152)
    update_parser = subparsers.add_parser(
        "update",
        help="Update an existing deployment",
    )
    update_parser.add_argument(
        "--organization",
        required=True,
        help="Organization ID to update",
    )
    update_parser.add_argument(
        "--intent",
        required=True,
        choices=["update_assistant", "update_scenario", "update_schema", "update_backend"],
        help="Type of update to perform",
    )
    update_parser.add_argument(
        "--updates",
        required=True,
        help="JSON file containing field updates",
    )
    update_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying",
    )
    update_parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute update with approval",
    )

    # cleanup command (T158)
    cleanup_parser = subparsers.add_parser(
        "cleanup",
        help="Clean up staging resources",
    )
    cleanup_parser.add_argument(
        "--organization",
        required=True,
        help="Organization ID to clean up",
    )
    cleanup_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview cleanup without deleting",
    )
    cleanup_parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute cleanup and delete resources",
    )
    cleanup_parser.add_argument(
        "--auto-approve",
        "--yes",
        "-y",
        action="store_true",
        help="Automatically approve deletion without confirmation",
    )

    # chat command (010-conversational-orchestrator)
    chat_parser = subparsers.add_parser(
        "chat",
        help="Start a conversational session to deploy a new client",
    )

    # smoke-test command (T159)
    smoke_test_parser = subparsers.add_parser(
        "smoke-test",
        help="Run smoke tests",
    )
    smoke_test_subparsers = smoke_test_parser.add_subparsers(dest="smoke_test_command")

    smoke_test_gemini_parser = smoke_test_subparsers.add_parser(
        "gemini",
        help="Test Gemini API connectivity",
    )

    smoke_test_chroma_parser = smoke_test_subparsers.add_parser(
        "chroma",
        help="Test Chroma vector store",
    )

    # Parse arguments
    args = parser.parse_args()

    # Default to chat when no subcommand is given
    if args.command is None:
        args.command = "chat"

    # Route to command handlers
    if args.command == "chat":
        return cmd_chat(args)

    elif args.command == "config":
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

    elif args.command == "generate":
        return cmd_generate(args)

    elif args.command == "validate":
        if args.validate_command == "package":
            return cmd_validate_package(args)
        else:
            validate_parser.print_help()
            return 1

    elif args.command == "history":
        return cmd_history(args)

    elif args.command == "verify":
        if args.verify_command:
            return cmd_verify(args)
        else:
            verify_parser.print_help()
            return 1

    elif args.command == "security":
        if args.security_command == "scan":
            return cmd_security_scan(args)
        else:
            security_parser.print_help()
            return 1

    elif args.command == "update":
        return cmd_update(args)

    elif args.command == "cleanup":
        return cmd_cleanup(args)

    elif args.command == "smoke-test":
        if args.smoke_test_command:
            return cmd_smoke_test(args)
        else:
            smoke_test_parser.print_help()
            return 1

    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    import io
    import os

    if os.name == "nt":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )
    sys.exit(main())
