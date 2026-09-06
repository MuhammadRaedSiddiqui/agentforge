"""
Export operational data from the internal Supabase store.

Implements T141: Operational data export (all 14 tables to JSON, manifest with
schema version, row counts, file hashes, final audit hash per deployment)

Usage:
    python scripts/export_internal_tables.py --output exports/backup-001
"""

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.supabase_internal import SupabaseInternalClient
from shared.console import enable_utf8_output

# All operational tables in dependency order
TABLES = [
    "organizations",
    "organization_intakes",
    "source_templates",
    "deployments",
    "sessions",
    "task_executions",
    "artifacts",
    "validation_reports",
    "proposed_actions",
    "approval_decisions",
    "external_request_attempts",
    "external_receipts",
    "external_resources",
    "recovery_actions",
    "audit_events",
]


def compute_file_hash(file_path: Path) -> str:
    """
    Compute SHA-256 hash of file.

    Args:
        file_path: Path to file

    Returns:
        Hex digest of hash
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def export_table(
    client: SupabaseInternalClient,
    table_name: str,
    output_dir: Path,
) -> dict[str, Any]:
    """
    Export a single table to JSON.

    Args:
        client: Internal store client
        table_name: Name of table to export
        output_dir: Output directory

    Returns:
        Export metadata (row count, file hash)
    """
    print(f"  Exporting {table_name}...")

    # Fetch all rows
    # Note: In production, this should handle pagination for large tables
    response = client.supabase.table(table_name).select("*").execute()

    rows = response.data

    # Write to file
    output_file = output_dir / f"{table_name}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, default=str)

    # Compute file hash
    file_hash = compute_file_hash(output_file)

    print(f"    ✓ Exported {len(rows)} rows")

    return {
        "table": table_name,
        "row_count": len(rows),
        "file": f"{table_name}.json",
        "file_hash": file_hash,
    }


def get_final_audit_hashes(
    client: SupabaseInternalClient,
) -> dict[str, str]:
    """
    Get final audit event hash for each deployment.

    Args:
        client: Internal store client

    Returns:
        Dictionary mapping deployment_id to final audit hash
    """
    # Get all deployments
    deployments = client.supabase.table("deployments").select("id").execute()

    final_hashes: dict[str, str] = {}

    for deployment in deployments.data:
        deployment_dict = cast(dict[str, Any], deployment)
        deployment_id = cast(str, deployment_dict["id"])

        # Get last audit event for this deployment
        last_event = (
            client.supabase.table("audit_events")
            .select("event_hash")
            .eq("deployment_id", deployment_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if last_event.data:
            event_dict = cast(dict[str, Any], last_event.data[0])
            final_hashes[deployment_id] = cast(str, event_dict["event_hash"])

    return final_hashes


def export_operational_data(
    output_dir: Path,
    include_deployment_id: str | None = None,
) -> dict[str, Any] | None:
    """
    Export all operational data.

    Args:
        output_dir: Output directory
        include_deployment_id: Optional deployment ID to export only

    Returns:
        Export manifest
    """
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Connect to internal store
    client = SupabaseInternalClient()

    print(f"Exporting operational data to {output_dir}")

    # Export each table
    table_exports = []

    for table_name in TABLES:
        try:
            export_metadata = export_table(client, table_name, output_dir)
            table_exports.append(export_metadata)
        except Exception as e:
            print(f"    ✗ Error exporting {table_name}: {e}")
            return None

    # Get final audit hashes per deployment
    print("\n  Computing final audit hashes...")
    final_audit_hashes = get_final_audit_hashes(client)
    print(f"    ✓ Computed {len(final_audit_hashes)} deployment hashes")

    # Create manifest
    manifest = {
        "export_version": "1.0.0",
        "schema_version": "1.0.0",
        "exported_at": datetime.now(UTC).isoformat(),
        "table_count": len(table_exports),
        "tables": table_exports,
        "total_rows": sum(t["row_count"] for t in table_exports),
        "final_audit_hashes": final_audit_hashes,
    }

    # Write manifest
    manifest_file = output_dir / "manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print("\n✓ Export complete")
    print(f"  Total tables: {manifest['table_count']}")
    print(f"  Total rows: {manifest['total_rows']}")
    print(f"  Manifest: {manifest_file}")

    return manifest


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Export Agent Forge operational data")
    parser.add_argument("--output", type=Path, required=True, help="Output directory for export")
    parser.add_argument("--deployment-id", type=str, help="Optional: export only this deployment")

    args = parser.parse_args()

    # Validate output doesn't already exist
    if args.output.exists() and any(args.output.iterdir()):
        print(f"Error: Output directory {args.output} already exists and is not empty")
        print("  Use a new directory or remove existing contents")
        sys.exit(1)

    # Export
    manifest = export_operational_data(
        output_dir=args.output,
        include_deployment_id=args.deployment_id,
    )

    if manifest:
        sys.exit(0)
    else:
        print("\n✗ Export failed")
        sys.exit(1)


if __name__ == "__main__":
    enable_utf8_output()
    main()
