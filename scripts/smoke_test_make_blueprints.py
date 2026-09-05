"""Standalone smoke test: deploy all Make blueprints to catch schema errors.

Loads .env, creates a hook per capability, deploys the blueprint, and
reports any errors. Does NOT trigger the full onboarding process.

Run: python scripts/smoke_test_make_blueprints.py
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))

from shared.errors import PermanentError  # noqa: E402

CAPABILITIES = ["availability", "booking", "cancellation", "rescheduling"]
BLUEPRINT_DIR = ROOT / "ground-truth" / "configs" / "make_blueprints"


def main() -> int:
    from adapters.make import MakeAdapter
    from orchestrator.make_deployer import MakeScenarioDeployer

    adapter = MakeAdapter()
    deployer = MakeScenarioDeployer(adapter)
    connection_id = os.getenv("MAKE_SUPABASE_CONNECTION_ID")

    failures = 0
    results = []
    for capability in CAPABILITIES:
        blueprint_path = BLUEPRINT_DIR / f"{capability}.json"
        print(f"=== Deploying {capability} ===")
        try:
            result = deployer.deploy_scenario(
                capability=capability,
                blueprint_path=str(blueprint_path),
                hook_name=f"smoke-{capability}",
                connection_id=connection_id,
            )
            print(
                f"  OK: scenario_id={result['scenario_id']} "
                f"hook_id={result['hook_id']} "
                f"module_count={result['module_count']} "
                f"activated={result['activated']} "
                f"fallback={result['used_fallback']}"
            )
            results.append(result)
        except PermanentError as e:
            failures += 1
            print(f"  PERMANENT ERROR: {e}")
        except Exception as e:
            failures += 1
            print(f"  ERROR: {type(e).__name__}: {e}")

    # Clean up: delete created scenarios and hooks
    print("\n=== Cleanup ===")
    for result in results:
        if result.get("scenario_id"):
            try:
                adapter.delete_scenario(int(result["scenario_id"]))
                print(f"  Deleted scenario {result['scenario_id']}")
            except Exception as e:
                print(f"  Cleanup scenario failed: {e}")
        if result.get("hook_id"):
            try:
                adapter.delete_hook(int(result["hook_id"]), confirmed=True)
                print(f"  Deleted hook {result['hook_id']}")
            except Exception as e:
                print(f"  Cleanup hook failed: {e}")

    print(f"\n=== {len(CAPABILITIES) - failures}/{len(CAPABILITIES)} deployed ===")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
