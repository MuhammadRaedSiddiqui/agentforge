# Agent Forge Setup - Next Steps

## Current Status: Supabase Connection Verified ✅

Your Supabase internal connection is working correctly. The credentials in your `.env` are valid and authenticated.

**What's Done:**
- ✅ `.env` file created with `SUPABASE_INTERNAL_URL` and `SUPABASE_INTERNAL_SERVICE_ROLE_KEY`
- ✅ Supabase connection verified (authentication successful)
- ✅ Migration bugs fixed (2 files corrected)
- ✅ Consolidated schema generated (820 lines, error-free)
- ✅ Verification scripts created

**What's Needed:**
- ❌ Database schema not yet applied (11 tables need to be created)
- ❌ Remaining environment variables not configured

---

## Step 1: Apply Database Schema (DO THIS FIRST) 🔴

### Quick Method (5 minutes):

1. **Open Supabase Dashboard**
   ```
   https://app.supabase.com
   ```
   Select your **internal** Supabase project

2. **Open SQL Editor**
   - Left sidebar → "SQL Editor"
   - Click "New Query"

3. **Run the Schema**
   - Open file: `supabase/migrations/consolidated_schema.sql`
   - Copy ALL 820 lines
   - Paste into SQL Editor
   - Click "Run" or press Ctrl+Enter

4. **Expected Result**
   ```
   Success. No rows returned
   ```

5. **Verify It Worked**
   ```bash
   python verify_supabase_setup.py
   ```
   
   You should see:
   ```
   [OK] organizations
   [OK] organization_intakes
   [OK] deployments
   ... (all 11 tables)
   [SUCCESS] Your Supabase database is fully configured and working!
   ```

### Alternative: Apply Migrations Individually

If the consolidated schema fails, apply each file individually in order:

```bash
001_organizations.sql
002_deployments.sql
003_sessions.sql
004_task_executions.sql
005_artifacts.sql
006_actions.sql
007_resources.sql
008_recovery.sql
009_audit.sql
010_templates_records.sql
011_indexes.sql
```

---

## Step 2: Complete Environment Configuration

After database setup, add remaining variables to `.env`. See `ENV_VARIABLES_GUIDE.md` for details.

### Critical Variables (Must Have):

```bash
# Client Supabase (separate from internal)
SUPABASE_CLIENT_URL=https://your-client-project.supabase.co
SUPABASE_CLIENT_SERVICE_ROLE_KEY=eyJ...

# AI Model Provider
GEMINI_API_KEY=AIza...
```

### Full Deployment Capability:

```bash
# Voice Assistant Platform
VAPI_API_KEY=sk-...

# Automation Platform
MAKE_API_TOKEN=...
MAKE_TEAM_ID=...
MAKE_ZONE=us1

# Hosting Provider
HOSTING_API_TOKEN=...
HOSTING_SERVICE_ID=...
HOSTING_HEALTH_URL=https://...

# Search API
BRAVE_SEARCH_API_KEY=BSA...

# Local Paths
SERVER_SOURCE_PATH=./backend/server.js
SERVER_TEST_COMMAND=npm test
```

Test configuration:
```bash
python -c "from cli.config import load_config, display_config; config = load_config(); print(display_config(config))"
```

---

## Step 3: Run Integration Tests

Once database and environment are configured:

```bash
# Run all integration tests
pytest tests/integration/ -m integration -v

# Run specific Supabase tests
pytest tests/integration/test_internal_store.py -m integration -v

# Run smoke tests
pytest tests/smoke/ -v
```

---

## Quick Reference

### Files Created/Updated:
- ✅ `supabase/migrations/002_deployments.sql` (fixed)
- ✅ `supabase/migrations/007_resources.sql` (fixed)
- ✅ `supabase/migrations/consolidated_schema.sql` (regenerated)
- ✅ `test_supabase_connection.py` (simple connection test)
- ✅ `verify_supabase_setup.py` (full database verification)
- ✅ `apply_migrations.py` (migration helper)
- ✅ `APPLY_MIGRATIONS.md` (migration instructions)
- ✅ `ENV_VARIABLES_GUIDE.md` (environment variable reference)
- ✅ `SUPABASE_SETUP.md` (setup overview)
- ✅ `NEXT_STEPS.md` (this file)

### Test Commands:
```bash
# Test Supabase connection only
python test_supabase_connection.py

# Verify full database setup
python verify_supabase_setup.py

# Test configuration loading
python -c "from cli.config import load_config; load_config()"

# Run integration tests
pytest tests/integration/test_internal_store.py -m integration -v
```

---

## Troubleshooting

### Issue: "Could not find the table"
- **Cause:** Database schema not applied yet
- **Fix:** Apply migrations via Supabase Dashboard (Step 1)

### Issue: "Missing required environment variables"
- **Cause:** `.env` file incomplete
- **Fix:** Add missing variables (see ENV_VARIABLES_GUIDE.md)

### Issue: Migration SQL error
- **Cause:** Old consolidated_schema.sql with bugs
- **Fix:** Use the NEW regenerated file (with fixes applied)

### Issue: "COMMENT ON CONSTRAINT does not exist"
- **Cause:** Using old migration files
- **Fix:** We already fixed this - use updated files

---

## Success Criteria

You'll know setup is complete when:

✅ `python verify_supabase_setup.py` shows all tables [OK]
✅ `python -c "from cli.config import load_config; load_config()"` succeeds
✅ `pytest tests/integration/test_internal_store.py -m integration -v` passes

---

## Need Help?

If you encounter errors:
1. Copy the exact error message
2. Note which step you were on
3. Check if you're using the latest files (with fixes)
4. Share the error for assistance

---

**IMMEDIATE ACTION:** Apply the database schema using Step 1 above, then run `python verify_supabase_setup.py`.
