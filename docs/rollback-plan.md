# Rollback Plan

## Overview

Agent Forge provides controlled rollback through the **cleanup** command and **compensation** flow. There is no "undo button" — each reversal is a deliberate, approved action.

## Rollback Strategy by Stage

### Stage 1: Before any approval (planning/generation)

**Risk**: Zero. No external changes were made.
**Action**: Simply stop. Nothing to roll back.

### Stage 2: Partially deployed (some actions completed)

**Risk**: Orphaned resources on external platforms.
**Action**:

```bash
# See what was created
python -m cli.main history --organization <org>

# Dry-run cleanup to see what would be deleted
python -m cli.main cleanup --organization <org> --dry-run

# Execute cleanup (will prompt for confirmation)
python -m cli.main cleanup --organization <org> --execute
```

### Stage 3: Fully deployed but needs reversal

**Risk**: Live resources serving traffic (if connected to phone numbers).
**Action**:

1. Deactivate the Vapi phone number assignment first (via Vapi dashboard if urgent)
2. Then run cleanup:

```bash
python -m cli.main cleanup --organization <org> --dry-run
python -m cli.main cleanup --organization <org> --execute
```

## Cleanup Command Behavior

The `cleanup` command:

1. Looks up all external resources created for the organization
2. Shows each resource with its platform, type, and remote ID
3. In `--dry-run` mode: lists what would be deleted, makes no changes
4. In `--execute` mode: deletes each resource with confirmation prompts
5. Handles deletion failures gracefully (reports what couldn't be removed)

## Platform-Specific Rollback

| Platform | What gets removed | How |
|----------|-------------------|-----|
| **Vapi** | Assistant, tools, phone assignment | DELETE /assistant/{id} |
| **Make.com** | Scenarios, webhooks | DELETE /scenario/{id}, DELETE /hook/{id} |
| **Supabase (client)** | Organization record, RLS policies | DELETE from organizations WHERE org_id = ... |
| **Hosting (Render)** | Environment variables, client routes | Remove env vars, redeploy |

## Emergency Rollback (Manual)

If Agent Forge is unavailable or the cleanup command fails:

### Vapi
1. Go to https://dashboard.vapi.ai
2. Find the assistant by name (matches `organization_id`)
3. Delete assistant (this also removes tool associations)
4. Remove phone number assignment if applicable

### Make.com
1. Go to https://www.make.com
2. Navigate to team scenarios
3. Find scenarios by name pattern (org_id prefix)
4. Deactivate then delete each scenario
5. Check and remove any webhooks

### Supabase (Client)
1. Go to Supabase Dashboard for the client project
2. SQL Editor: `DELETE FROM organizations WHERE organization_id = '<org_id>';`
3. Remove any RLS policies added for this org

### Render
1. Go to https://dashboard.render.com
2. Find the service environment variables
3. Remove any client-specific variables
4. Trigger a redeploy to apply changes

## Prevention

- Always use `--dry-run` before `--execute`
- Review the approval prompt carefully — abort early if anything looks wrong
- Keep staging and production credentials in separate .env files
- The `AGENT_FORGE_ENV=staging` check blocks production-looking targets

## Post-Rollback Verification

After cleanup, verify nothing was left behind:

```bash
# Check reconciliation against live state
python -m cli.main verify vapi
python -m cli.main verify make
python -m cli.main verify hosting

# Verify no resources remain in internal store
python -m cli.main history --organization <org>

# Health check
python -m cli.main verify health
```
