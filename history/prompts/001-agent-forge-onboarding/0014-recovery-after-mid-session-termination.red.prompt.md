---
id: 0014
title: recovery-after-mid-session-termination
stage: red
date: 2026-08-10
surface: agent
model: deepseek-v4-flash-free
feature: 001-agent-forge-onboarding
branch: phase4-update-flow
user: HP
command: continue (ensure recovery so previous org doesn't block new process)
labels: ["recovery", "deployment-lookup", "state-machine", "vapi", "abort", "debugging"]
links:
  spec: specs/001-agent-forge-onboarding/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - orchestrator/deployment_lookup.py (fixed get_latest_deployment ordering)
  - tests/unit/test_deployment_lookup.py (new regression tests)
tests:
  - tests/unit/test_deployment_lookup.py (6 passed)
  - tests/unit/test_state_machine.py (32 passed)
  - tests/integration/test_restart_recovery.py (7 passed)
  - tests/unit full suite (334 passed)
  - ruff check (passed)
---

## Prompt

since the process terminated mid session, make sure recovery is done so previous organization
doesn't block new process

## Response snapshot

Investigated deployment state after the earlier mid-session termination and found:

1. **New stuck deployment**: `8f13b273-5b6a-4d63-ab5c-411bcc46eadf` (`sunrise_dental`, intent
   `new_onboarding`) was created at 2026-08-10T10:32 and left in `recovery_required` when the
   process died mid-run. It had zero `recovery_actions`, `proposed_actions`, and `task_executions`
   rows, and two `external_resources`: the benign Supabase org row (`6b64f6aa-...`) and a Vapi
   assistant (`bdb81d9f-fd00-4d1d-a765-0c996aae53a4`, lifecycle_status `active`).

2. **Bug found**: `DeploymentLookup.get_latest_deployment` (deployment_lookup.py:43) ordered by
   `created_at` ASCENDING, so `limit=1` returned the OLDEST deployment. Live verification showed
   `store.get_latest_deployment` (correct `desc`) returned the stuck `recovery_required`
   deployment while `DeploymentLookup` returned the old `aborted` one — making
   `can_start_new_deployment` report `can_start=True` with reason "terminal state: aborted" even
   though a recovery-required deployment existed. This undermined the org-lock/recovery block check
   in `cli/session.py:132`.

3. **Live-state check**: queried Vapi for the orphaned assistant `bdb81d9f` via
   `VapiAdapter.get_assistant` (with `.env` loaded) -> `HTTP 404: Not found`, i.e. the resource
   does not exist remotely. With no unresolved recovery/proposed/task rows and no live resource,
   the `recovery_required -> aborted` transition was valid (per state_machine.py:71, "only when no
   unresolved live state remains"), matching the earlier `429cb12e` case.

Actions taken:
- Fixed `DeploymentLookup.get_latest_deployment` to order `created_at desc`.
- Added `tests/unit/test_deployment_lookup.py` with 6 regression tests (latest selection,
  descending order call, block-by-latest-recovery, allow-after-latest-aborted,
  has_unresolved_recovery false on terminal latest, state-machine abort transition).
- Marked deployment `8f13b273` `aborted` via `store.update_deployment_status` (completed_at set).

Verification:
- `lookup.get_latest_deployment("sunrise_dental")` -> `8f13b273` (aborted).
- `can_start_new_deployment("sunrise_dental", "new_onboarding")` -> `can_start: True`, reason
  "Existing deployment is in terminal state: aborted", `requires_recovery: False`.
- `has_unresolved_recovery` -> `False`.
- Full unit suite: 334 passed; ruff clean on changed files.

## Outcome

- `sunrise_dental` is unblocked: its latest deployment is now terminal (`aborted`), so a new
  process can start.
- Fixed an ordering bug in `DeploymentLookup.get_latest_deployment` that made the org-lock /
  recovery block check operate on the wrong (oldest) deployment.
- Remaining note: the `external_resources` row for the non-existent Vapi assistant (`bdb81d9f`)
  is stale data; not blocking, but could be reconciled/cleaned later.
- 🔁 Next prompts: wire the CLI recovery-state prompts (`cli/prompts.py`) into onboarding so a
  `recovery_required` deployment is surfaced to the operator instead of hard-failing; optionally
  clean up stale external_resource rows for resources that 404 on the live platform.
- 🧠 Reflection: the ordering bug masked the stuck deployment, so the abort decision required
  manual live-state verification (Vapi 404). Documenting the "no unresolved live state" check in
  the abort path would reduce future manual steps.

## Evaluation notes (flywheel)

- Failure modes observed: ascending `created_at` ordering caused wrong "latest" deployment; caught
  only by cross-checking store vs lookup results against live data.
- Graders run and results (PASS/FAIL): all 334 unit tests PASS; ruff PASS; live Vapi check 404
  (expected, confirmed orphaned resource).
- Prompt variant (if applicable): operational recovery + small code fix.
- Next experiment (smallest change to try): add a unit test asserting
  `DeploymentLookup.get_latest_deployment` order_by string (already covered in
  test_latest_deployment_order_is_descending).
