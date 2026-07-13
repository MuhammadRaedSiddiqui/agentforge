# Supabase Database Setup Instructions

## Your Supabase Connection Status
✅ **Connection Verified**: Your `SUPABASE_INTERNAL_URL` and `SUPABASE_INTERNAL_SERVICE_ROLE_KEY` are correctly configured in `.env` and the connection is working.

❌ **Schema Missing**: The database tables don't exist yet. You need to apply the migrations.

---

## Step 1: Apply Database Migrations

### Option A: Via Supabase Dashboard (Easiest)

1. **Open your Supabase project dashboard**
   - Go to: https://app.supabase.com
   - Select your internal project

2. **Navigate to SQL Editor**
   - Click on "SQL Editor" in the left sidebar

3. **Apply the consolidated schema**
   - Click "New Query"
   - Open the file: `supabase/migrations/consolidated_schema.sql`
   - Copy the entire contents (820 lines)
   - Paste into the SQL Editor
   - Click "Run" (or press Ctrl+Enter)

4. **Verify success**
   - You should see "Success. No rows returned"
   - Check the "Database" → "Tables" section
   - You should see 11 new tables created

### Option B: Via Supabase CLI (If you have npm)

```bash
# Install Supabase CLI
npm install -g supabase

# Initialize Supabase in the project (if not done)
cd C:\Users\HP\OneDrive\Desktop\agent-forge\agentforge
supabase init

# Link to your project
supabase link --project-ref YOUR_PROJECT_REF

# Push migrations
supabase db push
```

---

## Step 2: Verify Setup

After applying the migrations, run:

```bash
python verify_supabase_setup.py
```

This will test that all tables were created successfully.

---

## What Tables Will Be Created

1. **organizations** - Client identities
2. **organization_intakes** - Versioned intake records
3. **deployments** - Deployment tracking
4. **deployment_sessions** - Session records
5. **task_executions** - Task execution logs
6. **artifacts** - Generated artifacts (specs, plans, code)
7. **actions** - Deployment actions
8. **resource_references** - External resource links
9. **recovery_checkpoints** - Recovery points
10. **audit_logs** - Audit trail
11. **templates** - Template records

---

## Files Location

- **All migrations**: `supabase/migrations/*.sql`
- **Consolidated schema**: `supabase/migrations/consolidated_schema.sql`

---

## Next Steps

1. Apply the migrations using one of the methods above
2. Run `python verify_supabase_setup.py` to confirm success
3. Run the integration tests: `pytest tests/integration/test_internal_store.py -m integration -v`
