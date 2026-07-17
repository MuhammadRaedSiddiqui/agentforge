"""
Reconcile deployment state against external platforms.

Implements T139: Read-only reconciliation (compare stored resource IDs and status
against actual external state per adapter, report discrepancies without corrective
writes)

Usage:
    python scripts/reconcile_deployment.py --deployment-id deploy-001
    python scripts/reconcile_deployment.py --organization-id org-001
"""

import argparse
import sys
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.hosting import RenderHostingAdapter
from adapters.make import MakeAdapter
from adapters.supabase_client import SupabaseClientAdapter
from adapters.supabase_internal import SupabaseInternalClient
from adapters.vapi import VapiAdapter


class DeploymentReconciler:
    """
    Reconcile internal records with actual external state.

    READ-ONLY: Reports discrepancies but makes no corrective writes.
    """

    def __init__(self) -> None:
        """Initialize reconciler with adapters."""
        self.internal_store = SupabaseInternalClient()
        self.vapi = VapiAdapter()
        self.make = MakeAdapter()
        self.supabase_client = SupabaseClientAdapter()
        self.hosting = RenderHostingAdapter()

    def reconcile_deployment(
        self,
        deployment_id: str,
    ) -> dict[str, Any]:
        """
        Reconcile a single deployment.

        Args:
            deployment_id: Deployment identifier

        Returns:
            Reconciliation report
        """
        print(f"Reconciling deployment: {deployment_id}\n")

        # Get deployment
        deployment = self.internal_store.get_deployment(deployment_id)
        if not deployment:
            return {
                "error": f"Deployment not found: {deployment_id}",
            }

        # Get all external resources for this deployment
        resources = self.internal_store.get_external_resources(deployment_id)

        print(f"Found {len(resources)} external resources in internal store\n")

        # Reconcile each platform
        vapi_result = self._reconcile_vapi(deployment_id, resources)
        make_result = self._reconcile_make(deployment_id, resources)
        supabase_result = self._reconcile_supabase(deployment_id, resources)
        hosting_result = self._reconcile_hosting(deployment_id, resources)

        # Aggregate results
        total_resources = len(resources)
        total_verified = sum(
            [
                vapi_result["verified"],
                make_result["verified"],
                supabase_result["verified"],
                hosting_result["verified"],
            ]
        )
        total_missing = sum(
            [
                vapi_result["missing"],
                make_result["missing"],
                supabase_result["missing"],
                hosting_result["missing"],
            ]
        )
        total_mismatched = sum(
            [
                vapi_result["mismatched"],
                make_result["mismatched"],
                supabase_result["mismatched"],
                hosting_result["mismatched"],
            ]
        )

        return {
            "deployment_id": deployment_id,
            "organization_id": deployment["organization_id"],
            "total_resources": total_resources,
            "verified": total_verified,
            "missing": total_missing,
            "mismatched": total_mismatched,
            "platforms": {
                "vapi": vapi_result,
                "make": make_result,
                "supabase": supabase_result,
                "hosting": hosting_result,
            },
        }

    def _reconcile_vapi(
        self,
        deployment_id: str,
        all_resources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Reconcile Vapi resources.

        Args:
            deployment_id: Deployment identifier
            all_resources: All external resources

        Returns:
            Reconciliation result
        """
        print("Reconciling Vapi resources...")

        # Filter Vapi resources
        vapi_resources = [r for r in all_resources if r["platform"] == "vapi"]

        if not vapi_resources:
            print("  No Vapi resources to reconcile\n")
            return {
                "verified": 0,
                "missing": 0,
                "mismatched": 0,
                "details": [],
            }

        verified = 0
        missing = 0
        mismatched = 0
        details = []

        for resource in vapi_resources:
            remote_id = resource["remote_id"]
            resource_type = resource["resource_type"]

            try:
                if resource_type == "assistant":
                    # Verify assistant exists
                    result = self.vapi.get_assistant(remote_id)
                    if result["success"]:
                        verified += 1
                        print(f"  ✓ Assistant {remote_id} verified")
                    else:
                        missing += 1
                        print(f"  ✗ Assistant {remote_id} NOT FOUND")
                        details.append(
                            {
                                "resource_type": resource_type,
                                "remote_id": remote_id,
                                "issue": "not_found",
                            }
                        )

                elif resource_type == "tool":
                    # Verify tool exists
                    result = self.vapi.get_tool(remote_id)
                    if result["success"]:
                        verified += 1
                        print(f"  ✓ Tool {remote_id} verified")
                    else:
                        missing += 1
                        print(f"  ✗ Tool {remote_id} NOT FOUND")
                        details.append(
                            {
                                "resource_type": resource_type,
                                "remote_id": remote_id,
                                "issue": "not_found",
                            }
                        )

            except Exception as e:
                print(f"  ✗ Error checking {resource_type} {remote_id}: {e}")
                details.append(
                    {
                        "resource_type": resource_type,
                        "remote_id": remote_id,
                        "issue": "error",
                        "error": str(e),
                    }
                )

        print()
        return {
            "verified": verified,
            "missing": missing,
            "mismatched": mismatched,
            "details": details,
        }

    def _reconcile_make(
        self,
        deployment_id: str,
        all_resources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Reconcile Make resources.

        Args:
            deployment_id: Deployment identifier
            all_resources: All external resources

        Returns:
            Reconciliation result
        """
        print("Reconciling Make resources...")

        # Filter Make resources
        make_resources = [r for r in all_resources if r["platform"] == "make"]

        if not make_resources:
            print("  No Make resources to reconcile\n")
            return {
                "verified": 0,
                "missing": 0,
                "mismatched": 0,
                "details": [],
            }

        verified = 0
        missing = 0
        mismatched = 0
        details = []

        for resource in make_resources:
            remote_id = resource["remote_id"]
            resource_type = resource["resource_type"]

            try:
                if resource_type == "scenario":
                    # Verify scenario exists
                    result = self.make.get_scenario(remote_id)
                    if result["success"]:
                        verified += 1
                        print(f"  ✓ Scenario {remote_id} verified")
                    else:
                        missing += 1
                        print(f"  ✗ Scenario {remote_id} NOT FOUND")
                        details.append(
                            {
                                "resource_type": resource_type,
                                "remote_id": remote_id,
                                "issue": "not_found",
                            }
                        )

                elif resource_type == "hook":
                    # Verify hook exists
                    result = self.make.get_hook(remote_id)
                    if result["success"]:
                        verified += 1
                        print(f"  ✓ Hook {remote_id} verified")
                    else:
                        missing += 1
                        print(f"  ✗ Hook {remote_id} NOT FOUND")
                        details.append(
                            {
                                "resource_type": resource_type,
                                "remote_id": remote_id,
                                "issue": "not_found",
                            }
                        )

            except Exception as e:
                print(f"  ✗ Error checking {resource_type} {remote_id}: {e}")
                details.append(
                    {
                        "resource_type": resource_type,
                        "remote_id": remote_id,
                        "issue": "error",
                        "error": str(e),
                    }
                )

        print()
        return {
            "verified": verified,
            "missing": missing,
            "mismatched": mismatched,
            "details": details,
        }

    def _reconcile_supabase(
        self,
        deployment_id: str,
        all_resources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Reconcile Supabase resources.

        Args:
            deployment_id: Deployment identifier
            all_resources: All external resources

        Returns:
            Reconciliation result
        """
        print("Reconciling Supabase resources...")

        # Filter Supabase resources
        supabase_resources = [r for r in all_resources if r["platform"] == "supabase"]

        if not supabase_resources:
            print("  No Supabase resources to reconcile\n")
            return {
                "verified": 0,
                "missing": 0,
                "mismatched": 0,
                "details": [],
            }

        verified = 0
        missing = 0
        mismatched = 0
        details = []

        for resource in supabase_resources:
            remote_id = resource["remote_id"]
            resource_type = resource["resource_type"]

            try:
                if resource_type == "organization_record":
                    # Verify organization record exists
                    result = self.supabase_client.select_rows(
                        table="organizations",
                        filters={"id": remote_id},
                    )
                    if result["success"] and result["rows"]:
                        verified += 1
                        print(f"  ✓ Organization record {remote_id} verified")
                    else:
                        missing += 1
                        print(f"  ✗ Organization record {remote_id} NOT FOUND")
                        details.append(
                            {
                                "resource_type": resource_type,
                                "remote_id": remote_id,
                                "issue": "not_found",
                            }
                        )

            except Exception as e:
                print(f"  ✗ Error checking {resource_type} {remote_id}: {e}")
                details.append(
                    {
                        "resource_type": resource_type,
                        "remote_id": remote_id,
                        "issue": "error",
                        "error": str(e),
                    }
                )

        print()
        return {
            "verified": verified,
            "missing": missing,
            "mismatched": mismatched,
            "details": details,
        }

    def _reconcile_hosting(
        self,
        deployment_id: str,
        all_resources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Reconcile hosting resources.

        Args:
            deployment_id: Deployment identifier
            all_resources: All external resources

        Returns:
            Reconciliation result
        """
        print("Reconciling hosting resources...")

        # Filter hosting resources
        hosting_resources = [
            r for r in all_resources if r["platform"] == "render" or r["platform"] == "hosting"
        ]

        if not hosting_resources:
            print("  No hosting resources to reconcile\n")
            return {
                "verified": 0,
                "missing": 0,
                "mismatched": 0,
                "details": [],
            }

        verified = 0
        missing = 0
        mismatched = 0
        details = []

        for resource in hosting_resources:
            remote_id = resource["remote_id"]
            resource_type = resource["resource_type"]

            try:
                if resource_type == "deploy":
                    # Verify deploy exists
                    result = self.hosting.get_deploy_status(remote_id)
                    if result["success"]:
                        verified += 1
                        print(f"  ✓ Deploy {remote_id} verified")
                    else:
                        missing += 1
                        print(f"  ✗ Deploy {remote_id} NOT FOUND")
                        details.append(
                            {
                                "resource_type": resource_type,
                                "remote_id": remote_id,
                                "issue": "not_found",
                            }
                        )

            except Exception as e:
                print(f"  ✗ Error checking {resource_type} {remote_id}: {e}")
                details.append(
                    {
                        "resource_type": resource_type,
                        "remote_id": remote_id,
                        "issue": "error",
                        "error": str(e),
                    }
                )

        print()
        return {
            "verified": verified,
            "missing": missing,
            "mismatched": mismatched,
            "details": details,
        }

    def reconcile_organization(
        self,
        organization_id: str,
    ) -> dict[str, Any]:
        """
        Reconcile all deployments for an organization.

        Args:
            organization_id: Organization identifier

        Returns:
            Reconciliation report
        """
        print(f"Reconciling organization: {organization_id}\n")

        # Get all deployments for org
        deployments = self.internal_store.get_deployments_for_organization(organization_id)

        print(f"Found {len(deployments)} deployments\n")

        results = []
        for deployment in deployments:
            # Internal deployment records use ``deployment_id`` as their
            # primary identifier.  Accept ``id`` as a compatibility fallback
            # for older exports, but never assume it is present.
            deployment_id = deployment.get("deployment_id") or deployment.get("id")
            if not deployment_id:
                results.append({"error": "Deployment record missing deployment_id"})
                continue
            result = self.reconcile_deployment(deployment_id)
            results.append(result)

        # Aggregate
        total_verified = sum(int(r.get("verified", 0)) for r in results)
        total_missing = sum(int(r.get("missing", 0)) for r in results)
        total_mismatched = sum(int(r.get("mismatched", 0)) for r in results)

        return {
            "organization_id": organization_id,
            "deployment_count": len(deployments),
            "total_verified": total_verified,
            "total_missing": total_missing,
            "total_mismatched": total_mismatched,
            "deployments": results,
        }


def main() -> None:
    """Main entry point."""
    # Windows consoles can use a legacy code page that cannot render the
    # status symbols used by this script.  Replace unsupported characters
    # rather than failing after reconciliation has already completed.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(
        description="Reconcile Agent Forge deployment state with external platforms"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--deployment-id", type=str, help="Reconcile a single deployment")
    group.add_argument(
        "--organization-id", type=str, help="Reconcile all deployments for an organization"
    )

    args = parser.parse_args()

    # Create reconciler
    reconciler = DeploymentReconciler()

    # Reconcile
    if args.deployment_id:
        result = reconciler.reconcile_deployment(args.deployment_id)
    else:
        result = reconciler.reconcile_organization(args.organization_id)

    # Print summary
    print("\n" + "=" * 60)
    print("RECONCILIATION SUMMARY")
    print("=" * 60)

    if "error" in result:
        print(f"✗ Error: {result['error']}")
        sys.exit(1)

    verified = result.get("verified") or result.get("total_verified", 0)
    missing = result.get("missing") or result.get("total_missing", 0)
    mismatched = result.get("mismatched") or result.get("total_mismatched", 0)

    print(f"Verified:   {verified}")
    print(f"Missing:    {missing}")
    print(f"Mismatched: {mismatched}")

    if missing > 0 or mismatched > 0:
        print("\n⚠️  DISCREPANCIES DETECTED")
        print("   Review details above for specific issues")
        sys.exit(1)
    else:
        print("\n✓ All resources reconciled successfully")
        sys.exit(0)


if __name__ == "__main__":
    main()
