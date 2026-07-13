"""
Quick test to verify Supabase internal connection.
Tests only the Supabase variables without requiring full config.
"""

import os
from dotenv import load_dotenv
from supabase import create_client, Client


def main():
    print("Loading environment variables...")
    load_dotenv()

    url = os.getenv("SUPABASE_INTERNAL_URL")
    key = os.getenv("SUPABASE_INTERNAL_SERVICE_ROLE_KEY")

    if not url:
        print("[FAIL] SUPABASE_INTERNAL_URL not set in .env")
        return

    if not key:
        print("[FAIL] SUPABASE_INTERNAL_SERVICE_ROLE_KEY not set in .env")
        return

    print(f"[OK] Environment variables loaded")
    print(f"     URL: {url[:30]}...")
    print(f"     Key: {key[:4]}***")

    try:
        print("\nCreating Supabase client...")
        supabase: Client = create_client(url, key)
        print("[OK] Client created")

        print("\nTesting connection (simple query)...")
        # Try to query the organizations table
        response = supabase.table("organizations").select("organization_id").limit(1).execute()

        print("[SUCCESS] Supabase internal connection is working!")
        print(f"          Query returned {len(response.data)} row(s)")

    except Exception as e:
        print(f"[FAIL] Connection test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
