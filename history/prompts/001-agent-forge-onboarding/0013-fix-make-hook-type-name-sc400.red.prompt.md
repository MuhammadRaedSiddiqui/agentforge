---
id: 0013
title: fix-make-hook-type-name-sc400
stage: red
date: 2026-08-10
surface: agent
model: deepseek-v4-flash-free
feature: 001-agent-forge-onboarding
branch: phase4-update-flow
user: HP
command: continue (debugging make hook creation failure)
labels: ["make", "hooks", "sc400", "debugging", "adapter", "deployment"]
links:
  spec: specs/001-agent-forge-onboarding/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - orchestrator/make_deployer.py (type_name "web" -> "gateway-webhook")
  - tests/unit/test_make_deployer.py (assert updated to gateway-webhook)
  - specs/001-agent-forge-onboarding/contracts/tool-contracts.yaml (documented valid typeName values)
tests:
  - tests/unit/test_make_deployer.py (8 passed)
  - tests/contract/test_make_contract.py (27 passed)
  - tests/unit/test_update_execution.py (8 passed)
  - tests/regression/test_blueprint_stability.py (45 passed)
  - ruff check orchestrator/make_deployer.py tests/unit/test_make_deployer.py (passed)
---

## Prompt

Continue if you have next steps, or stop and ask for clarification if you are unsure how to proceed.

(Continuation of a debugging session for the `sunrise_dental` Make.com deployment failing with
`HTTP 400 SC400: Failed to load manifest.json file for hook 'web'` raised from `adapters/make.py:128`
via `orchestrator/make_deployer.py:62`.)

## Response snapshot

Root cause identified: `MakeScenarioDeployer.deploy_scenario` passed `type_name="web"` to
`MakeAdapter.create_hook`, but Make requires the hook `typeName` to be a registered native hook type.
Make's official API docs state the two native hook types are `gateway-webhook` and `gateway-mailhook`
and that `typeName` is "the hook type strictly related to the app for which the hook was created".
`web` and `CustomWebHook` are blueprint *module* names (`webhook:CustomWebHook` /
`gateway:CustomWebHook`), not hook types, so Make cannot load a manifest and rejects with SC400.

Confirmed via Make docs Q&A: creating a custom webhook with `POST /hooks` requires
`typeName: "gateway-webhook"`.

Changes applied:
1. `orchestrator/make_deployer.py:64` — `type_name="web"` -> `type_name="gateway-webhook"`.
2. `tests/unit/test_make_deployer.py:96` — assertion updated to match.
3. `specs/001-agent-forge-onboarding/contracts/tool-contracts.yaml` — `MakeHookCreateRequest.typeName`
   now documents that native values are `gateway-webhook` / `gateway-mailhook` and that `web` /
   `CustomWebHook` are module names rejected with SC400 (schema otherwise unchanged).

Verified the other `create_hook` callers pass `type_name` through from action payloads
(`orchestrator/orchestrator.py:529`, `orchestrator/full_orchestrator.py:786`,
`orchestrator/recovery.py:325`) — no other hardcoded `"web"` values exist.

## Outcome

- Root cause: wrong hook `typeName` value (`"web"` instead of `"gateway-webhook"`).
- 🧪 Tests: 35 tests in the make deployer + contract suites pass; 53 across the update-execution and
  blueprint-stability suites pass; changed files ruff-clean; contract YAML still parses.
- 📁 Files: 2 code/test files changed + 1 contract doc update.
- 🔁 Next prompts: re-run the `sunrise_dental` deployment end-to-end to confirm hook creation now
  succeeds; optionally wire the CLI recovery-state prompts (`cli/prompts.py`) into onboarding so a
  `recovery_required` deployment doesn't hard-fail.
- 🧠 Reflection: The contract's loose `typeName` (plain string) let an invalid value slip through;
  documenting valid native values reduces recurrence. Deployment execution is still pending user
  approval to run against live Make resources.

## Evaluation notes (flywheel)

- Failure modes observed: SC400 manifest load error was only reproducible via live API; unit tests
  used mocked adapters so could not catch the invalid literal.
- Graders run and results (PASS/FAIL): unit/contract/regression suites PASS; ruff PASS; YAML parse PASS.
- Prompt variant (if applicable): manual debugging of a live deployment failure.
- Next experiment (smallest change to try): execute the `sunrise_dental` deployment to validate the fix
  against the real Make API.
