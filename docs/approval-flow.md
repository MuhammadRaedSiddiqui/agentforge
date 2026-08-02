# Approval Flow Guide

## Overview

Every external side effect in Agent Forge requires a separate, explicit human approval. No action can execute without your consent, and no approval authorizes actions you haven't seen.

## How It Works

When Agent Forge is ready to make an external change, you'll see:

```
======================================================================
ACTION APPROVAL REQUIRED
======================================================================

Platform: vapi
Operation: create_assistant
Target: {
  "name": "Agent Forge Staging Salon Assistant"
}

--- Change Summary ---
Create voice assistant with configured tools for availability, booking,
cancellation, rescheduling, and human transfer.

--- Inferred/Default Values ---
  • voice_id: en-US-neural-male-1 (from intake)
  • server_url: https://averon-ztfm.onrender.com (from hosting config)

--- Validation ---
  ✓ All validations passed

--- Recovery Implications ---
  • Reconciliation: List assistants by name, match by configuration hash
  • Compensation: Delete assistant by ID

--- Proposal Hash ---
  a3f7b2c1e8d9...

======================================================================

Options:
  1. approve - Execute this action
  2. abort   - Stop deployment
  3. revise  - Request changes and regenerate

Decision (approve/abort/revise):
```

## Your Options

| Option | What happens |
|--------|-------------|
| **approve** | The action executes immediately. A receipt is persisted before the next action. |
| **abort** | Deployment stops. Completed actions remain (use `cleanup` to undo). |
| **revise** | You provide instructions, the system regenerates the artifact, re-validates, and presents a fresh proposal. |

## Key Rules

1. **One action at a time** — you'll never be asked to approve a batch
2. **Hash-bound** — each approval is cryptographically tied to exactly what was shown
3. **Stale proposals die** — if the remote state changed since the read, the proposal is discarded and regenerated
4. **No blind replay** — approving action #1 doesn't authorize action #2
5. **Receipts before progress** — the result of each action is persisted before the next one starts

## Typical Onboarding Sequence

A new client onboarding shows ~5-7 approval prompts:

1. Supabase: insert organization record + RLS policies
2. Vapi: create assistant
3. Make: create availability scenario
4. Make: create booking scenario
5. Make: create cancellation scenario
6. Make: create rescheduling scenario
7. Hosting: update backend (add client routes)

Each one shows exactly what will be created/modified. You can abort at any point — completed actions are tracked and recoverable.

## Tips

- Read the **Recovery Implications** section — it tells you what happens if this action fails
- Check **Inferred/Default Values** — these are values the system filled in from your intake or configuration
- If something looks wrong, choose **revise** and explain what to fix
- The **Proposal Hash** is your audit proof that you approved exactly this action
