---
id: 0007
title: Fix CI Lint and Secret-Scan Failures
stage: green
date: 2026-08-14
surface: agent
model: opencode/deepseek-v4-flash-free
feature: none
branch: phase4-update-flow
user: MuhammadRaedSiddiquie
command: the pr lint and secret-scan is failing
labels: ["ci", "lint", "ruff", "secret-scan", "trufflehog", "lob", "false-positive"]
links:
  spec: null
  ticket: null
  adr: null
  pr: https://github.com/MuhammadRaedSiddiqui/agentforge/pull/10
files:
  - .trufflehog.exclude
  - .github/workflows/security.yml
  - tests/unit/test_deployment_lookup.py
  - adapters/vapi.py
  - agents/make_agent/validator.py
  - agents/vapi_agent/validator.py
  - orchestrator/dialogue_engine.py
  - tests/contract/test_make_contract.py
  - tests/unit/test_conversation_agent.py
  - tests/unit/test_dialogue_engine.py
tests:
  - ruff check on all 22 changed .py files (All checks passed)
  - python -m pytest tests/unit/test_deployment_lookup.py tests/regression/test_prompt_stability.py (17 passed)
  - trufflehog filesystem/git scans (exclude suppresses Lob false positive)
  - gh pr checks 10 -> lint/test/typecheck/secret-scan all pass
---

## Prompt

the pr lint and secret-scan is failing

## Response snapshot

PR #10 CI had two failing jobs: `lint` (ruff) and `secret-scan` (TruffleHog).

**Lint (13 errors, all in PR-touched files):** fixed via `ruff --fix` for import sorting/unused imports (test_conversation_agent, test_dialogue_engine, dialogue_engine), B904 `raise ... from e` x3 in `adapters/vapi.py:111-115`, SIM102 nested-if flattening in `agents/make_agent/validator.py:87/196`, `agents/vapi_agent/validator.py:245`, and F841 dropped unused `receipt` in `tests/contract/test_make_contract.py:239`. CI lint only checks changed `.py` files vs `origin/master`; full repo shows pre-existing failures (B904 in vapi, SIM102/I001 elsewhere) that CI does not gate on. Verified: all 22 changed .py files pass `ruff check`.

**Secret-scan (TruffleHog):** flagged `tests/unit/test_deployment_lookup.py:59` as a "verified Lob result". Root cause: the Lob detector (DetectorType 490) treats pytest method names like `test_<30+ lowercase chars>` as Lob test API keys. Because TruffleHog's GitHub action scans the PR's git *history* (base..head), the old method name (the 40-char `test_latest_deployment_picks_*` variant) survived in commit `b03387b` even after HEAD renamed it — so renaming in HEAD alone was not enough. Reproduced locally with trufflehog 3.96.0; only 6 tokens actually match the detector; all other 16 long `test_` names in the diff are safe.

Fix (user chose exclude-config over history rewrite): added `.trufflehog.exclude` (regex `^tests/unit/test_deployment_lookup\.py$`) and wired `--exclude-paths=.trufflehog.exclude` into `.github/workflows/security.yml` extra_args. Verified exclude suppresses the finding in git-source scans of a fresh clone. Also kept the `test_latest_picks_newest` rename (harmless, removes the token from HEAD).

Follow-up (PR re-checked after PHR push): the secret-scan re-failed because the PHR's own Response snapshot quoted the full method name, and TruffleHog's git-history scan caught it in the intermediate PHR commit. Fixed by rephrasing the PHR text and adding the PHR file path to `.trufflehog.exclude`. Final `.trufflehog.exclude` excludes both `tests/unit/test_deployment_lookup.py` and the PHR file.

Result: `gh pr checks 10` — lint pass, test pass, typecheck pass, secret-scan pass (all green).

## Outcome

- ✅ Impact: PR #10 checks all green (lint, test, typecheck, secret-scan). No force-push / history rewrite needed.
- 🧪 Tests: ruff on changed files clean; 17 tests in the two touched suites pass; TruffleHog exclude verified on git scan.
- 📁 Files: 9 files across two commits (a370e14 lint+rename, 5d53aa9 exclude+workflow).
- 🔁 Next prompts: consider whether `.trufflehog.exclude` should be tightened to a pattern (it only excludes the one file that triggered); full repo still has pre-existing ruff issues to clean opportunistically.
- 🧠 Reflection: GitHub TruffleHog action scans commit history, so a renamed-in-HEAD token still fails until excluded or history-rewritten. PowerShell quirks: no `xargs`, no heredoc, `file://` URIs mangled — use temp-file clone for git-source scans; `gh` output is on stderr.

## Evaluation notes (flywheel)

- Failure modes observed: Lob detector false-positive on pytest method names; TruffleHog git scan not re-run by rename alone because intermediate commit retained the token; ruff only lints changed files on PRs.
- Graders run and results (PASS/FAIL): ruff PASS; pytest PASS; trufflehog exclude PASS; PR checks PASS.
- Prompt variant (if applicable): N/A
- Next experiment (smallest change to try): none pending; PR is mergeable. Optionally add the `--exclude-detectors=Lob`-style guard only if future test files re-trigger.