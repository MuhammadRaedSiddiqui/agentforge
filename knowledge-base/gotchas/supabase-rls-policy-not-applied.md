# Gotcha: Supabase RLS Policy Not Applied After Migration

**Platform:** Supabase  
**Topic:** Row Level Security  
**Symptom:** RLS policies defined in migration but queries bypass them or fail with permission denied  
**Verification Status:** Verified  
**Approved By:** system  
**Approved At:** 2026-07-14

## Root Cause

Supabase Row Level Security (RLS) policies can fail to apply correctly after migration due to:

1. **Policy order matters** - Multiple policies on same table can conflict
2. **Role permissions** - Policy requires explicit role grants
3. **Policy dependencies** - Policy references functions/tables that don't exist yet
4. **Enable RLS flag** - Table has policies but RLS not enabled on table

## Resolution

1. **Verify RLS is enabled on table:**
   ```sql
   ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
   ```

2. **Check policy order and conflicts:**
   ```sql
   -- List all policies on table
   SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual
   FROM pg_policies
   WHERE tablename = 'organizations'
   ORDER BY policyname;
   ```

3. **Grant necessary permissions:**
   ```sql
   -- Ensure authenticated role has access
   GRANT SELECT, INSERT, UPDATE ON organizations TO authenticated;
   ```

4. **Test policies after migration:**
   ```python
   # Positive test - should succeed
   result = supabase_client.select_rows(
       table="organizations",
       filters={"organization_id": "allowed_org"}
   )
   assert len(result) > 0
   
   # Negative test - should fail or return empty
   result = supabase_client.select_rows(
       table="organizations", 
       filters={"organization_id": "foreign_org"}
   )
   assert len(result) == 0
   ```

5. **Run tenant isolation tests:**
   ```bash
   pytest tests/security/test_tenant_isolation.py -m staging
   ```

## Detection

```python
# After migration, verify RLS is working
test_cases = [
    {
        "org_id": "test_org_1",
        "should_access": True,
        "expected_count": 1,
    },
    {
        "org_id": "test_org_2",  # Cross-tenant
        "should_access": False,
        "expected_count": 0,
    },
]

for test in test_cases:
    result = query_with_context(test["org_id"])
    actual_count = len(result)
    
    if actual_count != test["expected_count"]:
        raise SecurityError(
            f"RLS policy not working: "
            f"expected {test['expected_count']}, got {actual_count}"
        )
```

## Prevention

- **Enable RLS explicitly in migration:**
  ```sql
  ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
  ```

- **Use policy templates with proven patterns:**
  ```sql
  -- Tenant isolation policy template
  CREATE POLICY "tenant_isolation_select"
  ON organizations FOR SELECT
  USING (organization_id = current_setting('app.current_org_id')::text);
  ```

- **Always run isolation tests after migration:**
  ```bash
  # Automated in CI
  supabase db push --linked
  pytest tests/security/test_tenant_isolation.py
  ```

- **Avoid hardcoded organization IDs in policies**
- **Document policy dependencies in migration comments**

## Common Mistakes

1. Creating policy before enabling RLS on table
2. Missing role grants for authenticated users
3. Policy uses function that doesn't exist yet
4. Multiple conflicting policies (first one wins)
5. Policy references current_user but should reference custom setting

## Related Issues

- Postgres function permissions can also block RLS
- Service role bypasses RLS (be careful with service key operations)
- Local Supabase vs staging can have different policy behavior

## References

- Supabase RLS Guide: https://supabase.com/docs/guides/auth/row-level-security
- Agent Forge Tenant Isolation: tests/security/test_tenant_isolation.py
- Data Model: specs/001-agent-forge-onboarding/data-model.md
- Research Date: 2026-07-14
