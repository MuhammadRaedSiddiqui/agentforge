# Recovery Procedure

## When Recovery Activates

Recovery triggers automatically when:
- An action fails after sending the request (ambiguous outcome)
- A timeout occurs after a create/update was sent
- The process is killed or crashes mid-deployment
- You restart Agent Forge for the same organization with an unresolved deployment

## What You'll See

On restart with an unresolved deployment:

```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
RECOVERY REQUIRED
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

Unresolved deployment detected for organization: agent_forge_staging

--- Deployment Summary ---
  Deployment ID: ac5e0ff9-5cbb-404d-9068-046d71547ce0
  Status: recovery_required
  Intent: new_onboarding
  Started: 2026-07-17T08:30:00Z

--- Completed Resources ---
  ✓ vapi: assistant
    ID: asst_abc123
  ✓ make: scenario
    ID: scn_def456

--- Pending Recovery Actions ---
  • RECONCILE: create_scenario (pending)

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
```

## Recovery Options

| Option | When to use | What happens |
|--------|-------------|-------------|
| **reconcile** | After timeout/crash — unsure if action succeeded | Reads remote state to check if the resource exists |
| **retry** | After confirmed failure — resource definitely wasn't created | Re-runs the failed action with fresh approval |
| **compensate** | You want to undo everything and start over | Deletes completed resources one by one (each needs approval) |
| **defer** | Can't resolve now, want to do other work | Marks deployment as deferred; you'll be reminded next session |
| **abort** | Permanent failure, give up on this deployment | Marks as abandoned; resources remain (use `cleanup` later) |

## Step-by-Step Recovery

### Scenario: Timeout after create

1. Agent Forge shows "RECOVERY REQUIRED" on restart
2. Choose **reconcile**
3. System queries the remote platform (e.g., lists Vapi assistants)
4. If found: marks as succeeded, continues to next action
5. If not found: marks as failed, offers retry

### Scenario: Confirmed failure (4xx error)

1. Error is classified (validation, authorization, conflict, etc.)
2. System transitions deployment to `recovery_required`
3. On next run, choose **retry**
4. System regenerates the action with current state
5. Fresh approval required — you see the new proposal

### Scenario: Want to undo completed work

1. Choose **compensate**
2. System generates compensation actions (e.g., "delete assistant asst_abc123")
3. Each compensation action requires **separate approval**
4. If compensation fails: deployment stays unresolved, remaining resources listed

### Scenario: Process killed mid-deployment

1. Restart Agent Forge for the same organization
2. System detects unresolved state automatically
3. Shows what completed and what was in progress
4. Follow reconcile → retry flow as above

## Important Rules

- **Never retry blindly** — always reconcile first if the outcome is ambiguous
- **Compensation needs approval** — no automatic rollback
- **Failed compensation is honest** — system reports what it couldn't undo
- **Max 2 auto-retries** — only for read-only/idempotent operations
- **Bounded delay** — retries wait 1s then 2s, never longer

## CLI Commands for Recovery

```bash
# Check for unresolved deployments
python -m cli.main verify health

# View deployment history (see failed/recovery states)
python -m cli.main history --organization <org>

# Reconcile external resources against stored state
python -m cli.main verify vapi
python -m cli.main verify make
python -m cli.main verify hosting

# Clean up all resources for an organization (dry-run first!)
python -m cli.main cleanup --organization <org> --dry-run
python -m cli.main cleanup --organization <org> --execute
```

## Failure Types Reference

| Type | Meaning | Recovery path |
|------|---------|---------------|
| `validation` | Bad input/config | Fix input, retry |
| `authorization` | Bad credentials | Fix .env, retry |
| `conflict` | Resource already exists | Reconcile first |
| `transient` | Temporary network/server issue | Auto-retried (max 2) |
| `permanent` | Unrecoverable API error | Investigate, possibly abort |
| `ambiguous_outcome` | Sent request, no confirmation | Must reconcile |
| `compensation_failure` | Undo action failed | Manual intervention |
| `local_persistence` | Couldn't save receipt locally | Reconcile on restart |
