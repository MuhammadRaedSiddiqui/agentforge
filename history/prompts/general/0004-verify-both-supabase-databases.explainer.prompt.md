---
id: 0004
title: Verify Both Supabase Databases
stage: explainer
date: 2026-08-10
surface: agent
model: opencode/deepseek-v4-flash-free
feature: none
branch: phase4-update-flow
user: MuhammadRaedSiddiquie
command: can you verify status of both databases?
labels: ["supabase", "verification", "connectivity"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - history/prompts/general/0004-verify-both-supabase-databases.explainer.prompt.md
tests:
  - "python verify_supabase_setup.py (internal DB, 16 tables, CRUD)"
  - "python -c ... SupabaseClientAdapter.select_rows(table='organizations') (client DB, 4 rows)"
---

## Prompt

can you verify status of both databases?

## Response snapshot

Verified both Supabase databases are live and configured:

1. **Internal** (SUPABASE_INTERNAL_URL, project dxemxhfpiwsubfmzykzp): ran verify_supabase_setup.py - connection OK, all 16/16 expected tables present (organizations, organization_intakes, deployments, sessions, task_executions, artifacts, proposed_actions, approval_decisions, external_request_attempts, external_receipts, external_resources, recovery_actions, audit_events, source_templates, deployment_records, validation_reports); INSERT/SELECT/UPDATE/DELETE on organizations all pass.
2. **Client** (SUPABASE_CLIENT_URL, project myxtuxdgllckqnffdxgw): SupabaseClientAdapter connected and select_rows(table='organizations') returned 4 rows; allowlist enforcement working.

Also noted: SUPABASE_CLIENT_URL/KEY are now set in .env (docs like ENV_VARIABLES_GUIDE.md previously marked client project as pending setup - that is now outdated).

## Outcome

- ✅ Impact: Confirmed operational status of both databases (internal fully provisioned with schema; client reachable with live data).
- 🧪 Tests: verify_supabase_setup.py (internal) PASS; client adapter select_rows PASS (4 rows).
- 📁 Files: no source changes; created this PHR.
- 🔁 Next prompts: reconcile outdated docs (ENV_VARIABLES_GUIDE.md, NEXT_STEPS.md) that still mark client project as pending; run full integration tests; inspect client organizations rows.
- 🧠 Reflection: Both projects share the same organizations table concept - internal keeps full schema, client is tenant-facing with strict allowlist.

## Evaluation notes (flywheel)

- Failure modes observed: none; both connections succeeded on first attempt
- Graders run and results (PASS/FAIL): PASS (internal verify, client adapter query)
- Prompt variant (if applicable): N/A
- Next experiment (smallest change to try): run pytest tests/integration/test_internal_store.py against the live internal DB
