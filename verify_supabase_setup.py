"""
Verify Supabase database setup after applying migrations.

Tests that all required tables exist and basic operations work.
"""

import contextlib
import os

from dotenv import load_dotenv

from supabase import Client, create_client

EXPECTED_TABLES = [
    "organizations",
    "organization_intakes",
    "deployments",
    "sessions",  # NOT deployment_sessions
    "task_executions",
    "artifacts",
    "proposed_actions",
    "approval_decisions",
    "external_request_attempts",
    "external_receipts",
    "external_resources",
    "recovery_actions",
    "audit_events",
    "source_templates",
    "deployment_records",
    "validation_reports",
]


def check_table_exists(supabase: Client, table_name: str) -> bool:
    """Check if a table exists by attempting a simple query."""
    try:
        supabase.table(table_name).select("*").limit(0).execute()
        return True
    except Exception as e:
        error_msg = str(e)
        if "PGRST205" in error_msg or "not find the table" in error_msg:
            return False
        # Other errors might indicate the table exists but there's a different issue
        print(f"    [WARN] Unexpected error for {table_name}: {e}")
        return False


def test_basic_operations(supabase: Client) -> bool:
    """Test basic CRUD operations on organizations table."""
    test_org_id = "test_verification_org"

    try:
        print("\n[TEST] Basic operations on 'organizations' table...")

        # Clean up any existing test data
        with contextlib.suppress(Exception):
            supabase.table("organizations").delete().eq("organization_id", test_org_id).execute()

        # Insert
        print("  - INSERT test organization...")
        insert_result = (
            supabase.table("organizations")
            .insert(
                {
                    "organization_id": test_org_id,
                    "display_name": "Test Verification Org",
                    "status": "active",
                }
            )
            .execute()
        )

        if not insert_result.data:
            print("    [FAIL] Insert returned no data")
            return False
        print("    [OK] Insert successful")

        # Select
        print("  - SELECT test organization...")
        select_result = (
            supabase.table("organizations").select("*").eq("organization_id", test_org_id).execute()
        )

        if not select_result.data or len(select_result.data) != 1:
            print("    [FAIL] Select returned unexpected data")
            return False
        print("    [OK] Select successful")

        # Update
        print("  - UPDATE test organization...")
        update_result = (
            supabase.table("organizations")
            .update({"display_name": "Updated Test Org"})
            .eq("organization_id", test_org_id)
            .execute()
        )

        if not update_result.data:
            print("    [FAIL] Update returned no data")
            return False
        print("    [OK] Update successful")

        # Delete
        print("  - DELETE test organization...")
        supabase.table("organizations").delete().eq("organization_id", test_org_id).execute()
        print("    [OK] Delete successful")

        return True

    except Exception as e:
        print(f"    [FAIL] Operation failed: {e}")
        # Clean up
        with contextlib.suppress(Exception):
            supabase.table("organizations").delete().eq("organization_id", test_org_id).execute()
        return False


def main():
    print("=" * 70)
    print("Supabase Database Verification")
    print("=" * 70)

    # Load environment
    load_dotenv()
    url = os.getenv("SUPABASE_INTERNAL_URL")
    key = os.getenv("SUPABASE_INTERNAL_SERVICE_ROLE_KEY")

    if not url or not key:
        print("\n[FAIL] Environment variables not set")
        print(
            "       Please check SUPABASE_INTERNAL_URL and SUPABASE_INTERNAL_SERVICE_ROLE_KEY in .env"
        )
        return

    print(f"\n[INFO] Connecting to: {url[:30]}...")

    try:
        supabase: Client = create_client(url, key)
        print("[OK] Connected successfully")
    except Exception as e:
        print(f"[FAIL] Connection failed: {e}")
        return

    # Check all expected tables
    print(f"\n[CHECK] Verifying {len(EXPECTED_TABLES)} expected tables...")
    print()

    missing_tables = []
    existing_tables = []

    for table_name in EXPECTED_TABLES:
        exists = check_table_exists(supabase, table_name)
        status = "[OK]" if exists else "[MISSING]"
        print(f"  {status} {table_name}")

        if exists:
            existing_tables.append(table_name)
        else:
            missing_tables.append(table_name)

    print()
    print("-" * 70)

    if missing_tables:
        print(f"\n[INCOMPLETE] {len(missing_tables)} table(s) missing:")
        for table in missing_tables:
            print(f"  - {table}")
        print()
        print("ACTION REQUIRED:")
        print("  Please apply the database migrations via Supabase Dashboard")
        print("  See SUPABASE_SETUP.md for instructions")
        return

    print(f"\n[SUCCESS] All {len(EXPECTED_TABLES)} tables exist!")

    # Test basic operations
    operations_ok = test_basic_operations(supabase)

    print()
    print("=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)
    print()
    print("  Connection:        [OK]")
    print(f"  Tables Created:    [OK] {len(existing_tables)}/{len(EXPECTED_TABLES)}")
    print(f"  Basic Operations:  {'[OK]' if operations_ok else '[FAIL]'}")
    print()

    if operations_ok:
        print("[SUCCESS] Your Supabase database is fully configured and working!")
        print()
        print("Next steps:")
        print(
            "  - Run integration tests: pytest tests/integration/test_internal_store.py -m integration -v"
        )
        print("  - Complete remaining environment variables in .env")
    else:
        print("[WARNING] Tables exist but operations failed")
        print("          Check permissions and table constraints")

    print()


if __name__ == "__main__":
    main()
