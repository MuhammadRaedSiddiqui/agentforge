---
id: 0004
title: Fix Conversation Loop in Intake
stage: red
date: 2026-08-10
surface: agent
model: opencode/deepseek-v4-flash-free
feature: none
branch: phase4-update-flow
user: MuhammadRaedSiddiquie
command: why is the agent stuck in a loop
labels: ["bug", "conversation", "intake", "extraction"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - orchestrator/intake_extractor.py
  - tests/unit/test_intake_extractor.py
tests:
  - python -m pytest tests/unit/ (327 passed)
  - python -m pytest tests/unit/test_intake_extractor.py (25 passed)
  - ruff check orchestrator/intake_extractor.py (clean)
---

## Prompt

why is the agent stuck in a loop: [full transcript of conversational onboarding showing agent repeatedly asking "What should the assistant be able to do?" despite the user answering]

## Response snapshot

Root cause diagnosed: the conversational intake loop was stuck because `extract_from_conversation` silently returned `{}`.

Why: with the meta/muse-spark-1.1 provider, the extraction tool call failed. The Meta API rejects named `tool_choice` (400: `only "auto" is supported for tool_choice`), so `intake_extractor.py` never forces the call for meta. The model frequently replied with text ("Got it, onboarding Sunrise Dental Studio...") instead of emitting an `update_intake` tool call. When no tool call is returned, extraction returned `{}`, `apply_extraction` filled nothing, `required_fields_present()` stayed false, and the dialogue engine re-asked the first missing field (capabilities) forever.

Reproduced live against api.meta.ai: short prompts sometimes returned tool calls, but the full-length first message returned text-only in 6/6 runs at temperature 0.

Fixes in `orchestrator/intake_extractor.py`:
1. Added a retry for providers without forced tool_choice: after a text-only response, re-send with an explicit instruction to call `update_intake` (verified: retry produced a valid tool call with all fields).
2. Added `fallback_extract()` — a deterministic regex extractor for org_id, business_name, phone_number (E.164), capabilities (keyword map), timezone (IANA), and known voice IDs. Used as last resort for any provider so the conversation always makes progress.
3. Refactored tool-call parsing into `_extract_tool_call()`.

Verified end-to-end against the live meta endpoint with the exact transcript: turn 1 extracts all fields (org_id, business_name, phone, capabilities, timezone), turn 2 adds voice_id. Added 6 new unit tests for the fallback.

## Outcome

- ✅ Impact: Conversation no longer loops — extraction now always fills state via tool-call → retry → deterministic fallback.
- 🧪 Tests: 327 unit tests pass (25 in intake_extractor, including 6 new fallback tests); ruff clean.
- 📁 Files: orchestrator/intake_extractor.py, tests/unit/test_intake_extractor.py.
- 🔁 Next prompts: run the full `agent-forge chat` session live to confirm the onboarding completes and produces a confirmed plan; then push the fix.
- 🧠 Reflection: The meta provider's tool-calling is unreliable and cannot be forced (API limitation), so resilience must come from the code path, not the model. This is a provider-class bug that will recur for any model without forced tool_choice support.

## Evaluation notes (flywheel)

- Failure modes observed: provider rejects named tool_choice; model returns text instead of tool call; extraction silently swallowed the failure returning {}.
- Graders run and results (PASS/FAIL): unit tests PASS; live meta extraction PASS; ruff PASS.
- Prompt variant (if applicable): N/A
- Next experiment (smallest change to try): full live chat session + review whether business_hours/services should also get fallback patterns
