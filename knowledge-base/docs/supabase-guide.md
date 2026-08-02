# Supabase Platform Guide

## Overview

Supabase provides hosted PostgreSQL with REST API, authentication, and row-level security.

Agent Forge uses two Supabase projects:
1. **Internal project** - Operational records (deployments, tasks, audit)
2. **Client project** - Client-facing business data (organizations, appointments)

## Row Level Security (RLS)

### Enabling RLS

RLS must be explicitly enabled on tables:

```sql
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
```

### Creating Policies

Policies control row-level access:

```sql
CREATE POLICY "tenant_isolation_select"
ON organizations FOR SELECT
USING (organization_id = current_setting('app.current_org_id')::text);
```

**Important:** Policy order matters. See gotcha: supabase-rls-policy-not-applied.md

### Testing Policies

Always test positive and negative cases:

```python
# Positive: Should access own org
result = client.select_rows("organizations", {"organization_id": "own_org"})
assert len(result) > 0

# Negative: Should NOT access foreign org
result = client.select_rows("organizations", {"organization_id": "foreign_org"})
assert len(result) == 0
```

## Migrations

### CLI-Based Migrations

Use Supabase CLI for migrations:

```bash
# Create migration
supabase migration new add_organizations_table

# Apply to local
supabase db reset

# Apply to staging
supabase db push --linked --project-ref $SUPABASE_PROJECT_REF_STAGING
```

### Migration Structure

```sql
-- Migration: 001_add_organizations.sql

-- Create table
CREATE TABLE organizations (
    organization_id TEXT PRIMARY KEY,
    business_name TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;

-- Create policy
CREATE POLICY "tenant_select" ON organizations FOR SELECT
USING (organization_id = current_setting('app.current_org_id', true)::text);

-- Grant permissions
GRANT SELECT, INSERT, UPDATE ON organizations TO authenticated;
```

## Python Client

### Initialization

```python
from adapters.supabase_client import SupabaseClientAdapter

client = SupabaseClientAdapter(
    url=os.getenv("SUPABASE_CLIENT_URL"),
    key=os.getenv("SUPABASE_CLIENT_SERVICE_ROLE_KEY")
)
```

### Operations

```python
# Select
rows = client.select_rows(
    table="organizations",
    filters={"organization_id": "test_org"}
)

# Insert
client.insert_org_record(
    organization_id="test_org",
    business_name="Test Business",
    timezone="America/New_York"
)
```

## Service Role vs Authenticated

### Service Role

- **Bypasses RLS** - Has superuser-like access
- **Use carefully** - Only for admin operations
- **Never expose** - Keep service role key secret

### Authenticated Role

- **Respects RLS** - Policies apply
- **Safer for operations** - Can't bypass tenant isolation
- **Set context** - Use `current_setting('app.current_org_id')`

## Common Issues

### Policy Not Applied

**Symptoms:**
- Cross-tenant data visible
- Permission denied on valid queries

**Resolution:** See gotcha: supabase-rls-policy-not-applied.md

### Migration Conflicts

**Symptom:** Migration fails with "already exists" error

**Cause:** Migration applied partially or manually

**Resolution:**
```bash
# Check applied migrations
supabase migration list --linked

# Reset local and reapply
supabase db reset
```

### Connection Pool Exhausted

**Symptom:** "too many connections" error

**Cause:** Not closing connections or too many concurrent operations

**Resolution:**
```python
# Use context manager (if available)
with client.get_connection() as conn:
    # Operations

# Or explicit close
client.close()
```

## Best Practices

- **Enable RLS on all tables** - Defense in depth
- **Test policies thoroughly** - Positive and negative cases
- **Use migrations for schema** - Never manual DDL in production
- **Minimize service role use** - Prefer authenticated with policies
- **Monitor connection count** - Stay under pool limits

## Local Development

```bash
# Start local Supabase
supabase start

# Get local connection info
supabase status

# Reset database
supabase db reset
```

## References

- Official Docs: https://supabase.com/docs
- RLS Guide: https://supabase.com/docs/guides/auth/row-level-security
- Agent Forge Internal Store: adapters/supabase_internal.py
- Agent Forge Client Store: adapters/supabase_client.py
