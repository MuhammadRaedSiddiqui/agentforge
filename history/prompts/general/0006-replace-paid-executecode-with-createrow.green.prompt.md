---
id: 0006
title: Replace Paid ExecuteCode with createARow
stage: green
date: 2026-08-13
surface: agent
model: opencode/deepseek-v4-flash-free
feature: none
branch: phase4-update-flow
user: MuhammadRaedSiddiquie
command: replace code:ExecuteCode with a Supabase createARow so booking activates on a free plan
labels: ["make", "blueprint", "booking", "activation", "free-plan"]
links:
  spec: null
  ticket: null
  adr: null
  pr: https://github.com/MuhammadRaedSiddiqui/agentforge/pull/10
files:
  - ground-truth/configs/make_blueprints/booking.json
  - tests/snapshots/make_booking_staging.json
  - orchestrator/make_deployer.py
  - tests/unit/test_make_deployer.py
  - tests/regression/test_blueprint_stability.py
  - AGENT_FORGE_DOCUMENTATION.md
  - knowledge-base/gotchas/make-module-count-verification.md
  - knowledge-base/gotchas/make-hook-first-deployment.md
tests:
  - python -m pytest tests/unit tests/regression tests/contract tests/security (547 passed)
  - scripts/smoke_test_make_blueprints.py (4/4 deployed, booking activated=True)
  - ruff check (JSON false positives pre-existing, not real)
---

## Prompt

replace code:ExecuteCode with a Supabase createARow so booking activates on a free plan

## Response snapshot

Root cause: the booking scenario used the paid `code:ExecuteCode` module to generate `appointment_id`. The 'code' app is only on paid Make plans, so the scenario could be created but never activated (IM005: "scenario contains an app for paid plans only").

Fix: replaced the standalone code module with a single `supabase:createARow` appointment insert that generates `appointment_id` via Make's free built-in expression `APT-{{formatDate(now; "x")}}` (epoch milliseconds — verified against Make date/format docs, lowercase x = millis). This removed the paid module entirely and dropped booking from 6 to 5 modules.

Changes:
- booking.json: deleted code:ExecuteCode module; createARow (now module 2) generates appointment_id; downstream modules renumbered (3,4,5) referencing {{2.appointment_id}} and {{4.json}}; template_version bumped to 1.1.0.
- tests/snapshots/make_booking_staging.json: regenerated to match.
- EXPECTED_MODULE_COUNTS booking 6 -> 5 (deployer + test_make_deployer).
- test_blueprint_stability: test_booking_has_6_modules -> test_booking_has_5_modules.
- Docs/knowledge-base gotchas updated for booking=5.

Verification: full suite 547 passed; live smoke test 4/4 scenarios deployed with activated=True (booking scenario_id/hook created, module_count=5, no IM005), then cleaned up.

## Outcome

- ✅ Impact: Booking scenario now creates AND activates on a free Make plan — the IM005 blocker is resolved.
- 🧪 Tests: 547 passed; live smoke deploy 4/4 activated=True.
- 📁 Files: booking.json, snapshot, deployer, tests, docs (8 files committed as 3429f16).
- 🔁 Next prompts: PR #10 updated with the fix; run full `agent-forge chat` flow to confirm end-to-end booking.
- 🧠 Reflection: Make has no free random/UUID module, but epoch-ms via formatDate(now; "x") is a free, deterministic unique ID. Replacing a paid module with a native free one is the cleanest way to satisfy plan restrictions. ruff flags JSON files (B018/F821) but this is a false positive — JSON is not Python; confirm by checking an untouched blueprint.

## Evaluation notes (flywheel)

- Failure modes observed: paid-only module (code app) blocked scenario activation (IM005).
- Graders run and results (PASS/FAIL): full suite PASS; live smoke PASS (booking activated=True).
- Prompt variant (if applicable): N/A
- Next experiment (smallest change to try): run the full onboarding + deployment flow live to confirm end-to-end booking works, not just deployment.