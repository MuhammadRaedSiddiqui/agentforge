---
id: 0008
title: Create Cleanup Script For All Platforms
stage: general
date: 2026-08-24
surface: agent
model: muse-spark-1.2-contributor[1m]
feature: none
branch: phase4-update-flow
user: MuhammadRaedSiddiquie
command: create cleanup script that deletes all existing scenarios, backend and vapi assistant
labels: ["cleanup", "make", "vapi", "hosting", "staging", "destructive"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - scripts/cleanup_all.py
tests:
  - python scripts/cleanup_all.py -- dry-run preview (12 scenarios, 12 hooks, 2 assistants discovered, 26 total)
  - python scripts/cleanup_all.py --only make -- dry-run (24 matched)
  - python scripts/cleanup_all.py --skip make -- dry-run (2 matched)
  - python -m ruff check scripts/cleanup_all.py (All checks passed)
  - python -m ruff format --check scripts/cleanup_all.py (passed)
---

## Prompt

this project has the access to make.com via api configured in .env, i want you to create a cleanup script that once run deletes all existing scenerios, backend and vapi assisstant

## Response snapshot

Created `scripts/cleanup_all.py` — full-environment wipe for staging (Make scenarios+hooks, Vapi assistants, Render hosting report).

**Key design:**
- Defaults to `--dry-run` (zero deletes); requires `--execute` to delete, mirroring `cli/main.py:1359-1501` existing `cleanup --organization` but without org scoping (team/account-wide).
- Env-guarded: blocks when `AGENT_FORGE_ENV=production` unless `--force-production` (`cli/main.py:299-307` pattern).
- Uses existing adapters: `adapters/make.py:270-342` (list_scenarios/delete_scenario, list_hooks/delete_hook) and `adapters/vapi.py:229-260` (delete_assistant) plus raw `GET /assistant` via `_vapi_request()` (adapter lacks list_assistants, contract `tool-contracts.yaml:63` omits it).
- Make deactivates active scenarios before delete (handles 409), 404 already-gone is success, 429 backs off 3s — matching `adapters/base.py:217-246` retry taxonomy.
- Vapi phone numbers listed but NOT deleted (account-level), with unassign guidance.
- Render/ hosting: no bulk-delete in `adapters/hosting.py` (only env-vars/deploys); script reports `HOSTING_SERVICE_ID` and prints manual `DELETE /v1/services/{id}` instead of silently no-oping. Optional `--suspend-hosting` calls `POST /services/{id}/suspend`.
- Windows UTF-8 fix for box-drawing chars, ruff-clean, `--only/--skip/--include-tools` filters.

**Verification (live staging, AGENT_FORGE_ENV=staging):**
- `python scripts/cleanup_all.py` → 12 scenarios (zone us2 team 2566984), 12 hooks, 2 assistants, 1 phone number — 26 total pending.
- `python scripts/cleanup_all.py --only make` → 24 matched; `--skip make` → 2 matched.
- No deletes executed in dry-run (acceptance: intended 26 preserved).

**Execution:**
```bash
python scripts/cleanup_all.py                          # preview (default)
python scripts/cleanup_all.py --execute                # prompt "DELETE ALL"
python scripts/cleanup_all.py --execute --yes          # CI, no prompt
python scripts/cleanup_all.py --execute --only make    # Make only
python scripts/cleanup_all.py --execute --yes --include-tools  # also wipe Vapi tools
```

Ref: `adapters/make.py:117-127,270-342,635-670` `adapters/vapi.py:44-120,229-260` `adapters/hosting.py:34-62` `cli/main.py:1359-1417` `specs/001-agent-forge-onboarding/contracts/tool-contracts.yaml:63-150,355-395`

## Outcome

- ✅ Impact: Staging team wipe now one-command; dry-run discovered 26 resources (24 Make + 2 Vapi); safe default prevents accidental prod wipe.
- 🧪 Tests: Dry-run preview + filtered runs + ruff check/format — all pass; 0 deletes in dry-run verified.
- 📁 Files: 1 created (`scripts/cleanup_all.py`), 0 modified — smallest viable diff; adapter code untouched, script composes existing receipts.
- 🔁 Next prompts: Run `python scripts/cleanup_all.py --execute --yes` when ready to wipe; add cron/CI guard for nightly staging reset; consider `internal_store` hard-delete of `external_resources` rows post-wipe.
- 🧠 Reflection: Missing `list_assistants` in Vapi adapter required raw request — candidate ADR to add it canonically; Render delete intentionally not auto-run (destructive service deletion outside hosted-MVP scope).

## Evaluation notes (flywheel)

- Failure modes observed: Windows cp1252 UnicodeEncodeError on box-drawing `─` (fixed via `sys.stdout.reconfigure(utf-8,replace)`); ruff N814/N813 alias casing and SIM103 direct-return.
- Graders run and results (PASS/FAIL): ruff check PASS, ruff format PASS, dry-run discovery PASS (12+12+2), filtered scopes PASS.
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): Add `list_assistants(limit)` to `adapters/vapi.py` and switch cleanup to adapter call; remove raw `_vapi_request` duplication.
