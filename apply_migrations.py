"""
Apply database migrations to Supabase internal instance.

Reads migration files in order and executes them.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from supabase import Client, create_client


def main():
    print("=" * 60)
    print("Supabase Migration Runner")
    print("=" * 60)

    # Load environment
    load_dotenv()
    url = os.getenv("SUPABASE_INTERNAL_URL")
    key = os.getenv("SUPABASE_INTERNAL_SERVICE_ROLE_KEY")

    if not url or not key:
        print("[FAIL] SUPABASE_INTERNAL_URL or SUPABASE_INTERNAL_SERVICE_ROLE_KEY not set")
        return

    print(f"\n[INFO] Connecting to: {url[:30]}...")

    try:
        supabase: Client = create_client(url, key)
        print("[OK] Connected to Supabase")
    except Exception as e:
        print(f"[FAIL] Connection failed: {e}")
        return

    # Find migration files
    migrations_dir = Path("supabase/migrations")
    if not migrations_dir.exists():
        print(f"[FAIL] Migrations directory not found: {migrations_dir}")
        return

    migration_files = sorted(migrations_dir.glob("*.sql"))

    if not migration_files:
        print("[FAIL] No migration files found")
        return

    print(f"\n[INFO] Found {len(migration_files)} migration files")
    print()

    # Apply each migration
    success_count = 0
    for migration_file in migration_files:
        print(f"[RUN] {migration_file.name}")

        try:
            # Read SQL
            sql_content = migration_file.read_text(encoding="utf-8")

            # Execute via RPC (raw SQL execution)
            # Note: We need to use the REST API directly since supabase-py
            # doesn't have a direct SQL execution method

            # For now, we'll use psycopg2 if available, or provide instructions
            try:
                import psycopg2  # noqa: F401

                # Extract connection details from Supabase URL
                # Format: https://PROJECT_REF.supabase.co
                project_ref = url.replace("https://", "").split(".")[0]

                # Supabase uses direct postgres connection
                # Connection string format for Supabase
                print("[INFO] Attempting direct postgres connection...")
                print("[WARN] This requires the database password, not the service role key")
                print("[SKIP] Direct SQL execution not supported via service role key")
                print("       Please apply migrations manually via Supabase Dashboard")
                print("       Or use Supabase CLI: supabase db push")
                break

            except ImportError:
                print("[SKIP] psycopg2 not installed")
                print("       Please apply migrations manually via Supabase Dashboard")
                print("       Or install Supabase CLI: npm install -g supabase")
                break

        except Exception as e:
            print(f"[FAIL] Error: {e}")
            break

    print()
    print("=" * 60)
    print("MIGRATION INSTRUCTIONS")
    print("=" * 60)
    print()
    print("To apply these migrations, you have two options:")
    print()
    print("1. Via Supabase Dashboard (Recommended):")
    print("   a. Go to your Supabase project dashboard")
    print("   b. Navigate to: SQL Editor")
    print("   c. Copy and paste each migration file content")
    print("   d. Run them in order (001, 002, 003, ...)")
    print()
    print("2. Via Supabase CLI:")
    print("   a. Install: npm install -g supabase")
    print("   b. Initialize: supabase init")
    print("   c. Link project: supabase link --project-ref YOUR_PROJECT_REF")
    print("   d. Push migrations: supabase db push")
    print()
    print(f"Migration files location: {migrations_dir.absolute()}")
    print()


if __name__ == "__main__":
    main()
