# APPLY THIS SCHEMA TO YOUR SUPABASE DATABASE

## Quick Start (Recommended)

1. **Open Supabase Dashboard**
   - Go to: https://app.supabase.com
   - Select your internal Supabase project

2. **Navigate to SQL Editor**
   - Click "SQL Editor" in the left sidebar
   - Click "New Query"

3. **Copy and Execute**
   - Open: `supabase/migrations/consolidated_schema.sql`
   - Copy ALL 820 lines
   - Paste into the SQL Editor
   - Click "Run" (or press Ctrl+Enter)

4. **Verify Success**
   - You should see: "Success. No rows returned"
   - Run: `python verify_supabase_setup.py`
   - All 11 tables should show [OK]

---

## What Was Fixed

Two migration files had errors where they tried to comment on "constraints" that were actually "indexes":

- Fixed `002_deployments.sql` line 113-114
- Fixed `007_resources.sql` line 60-61

The consolidated schema has been regenerated with these corrections.

---

## Tables That Will Be Created

1. `organizations` - Client identities
2. `organization_intakes` - Versioned intake records  
3. `deployments` - Deployment tracking with state machine
4. `deployment_sessions` - Session records
5. `task_executions` - Task execution logs
6. `artifacts` - Generated artifacts (specs, plans, code)
7. `proposed_actions` - Planned external actions
8. `approval_decisions` - Action approvals
9. `external_request_attempts` - API call attempts
10. `external_receipts` - API response receipts
11. `external_resources` - Live resource registry
12. `recovery_checkpoints` - Recovery points
13. `audit_logs` - Audit trail
14. `templates` - Template records

---

## After Applying

Run the verification script:

```bash
python verify_supabase_setup.py
```

Expected output:
```
[OK] Connected successfully
[OK] organizations
[OK] organization_intakes
[OK] deployments
... (all 11 tables)
[SUCCESS] All 11 tables exist!
[SUCCESS] Your Supabase database is fully configured and working!
```

---

## Troubleshooting

If you still get errors:
1. Make sure you're using the NEW `consolidated_schema.sql` (regenerated with fixes)
2. Try applying migrations individually instead of consolidated
3. Check if you have permissions to create types/tables in your Supabase project

For help: Share the exact error message you receive.
