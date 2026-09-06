---
id: 0017
title: Multi User Workflow Testing
stage: green
date: 2026-09-06
surface: agent
model: claude-opus-5
feature: none
branch: fix/post-phr10-hotfix
user: MuhammadRaedSiddiquie
command: test it as different users with different inputs and requirements and capture any errors/bugs and fix them simultaneously
labels: ["testing", "bugs", "encoding", "capabilities", "extraction", "matrix"]
links:
  spec: null
  ticket: null
  adr: null
  pr: https://github.com/MuhammadRaedSiddiqui/agentforge/pull/12
files:
  - cli/main.py (build_generation_intake; UTF-8 intake loading; secret-scan read)
  - orchestrator/intake_schema.py (DATABASE_BACKED_CAPABILITIES, needs_database)
  - orchestrator/planner.py, orchestrator/action_builder.py (use needs_database)
  - orchestrator/intake_extractor.py (normalize_voice_id)
  - orchestrator/org_lock.py, scripts/verify_staging.py (explicit encodings)
  - tests/unit/test_generation_intake.py (new), plus additions to test_action_builder,
    test_planner, test_intake_extractor, test_conversation_agent
  - commits 4a0f6d3, 9c60c5b, 1e1d9a2
tests:
  - 19 synthetic client profiles through validate/normalize, dry-run, and generate
  - 6 live conversational personas through run_chat_session
  - full capability-subset sweep (all 31 non-empty subsets) for deployment coherence
  - pytest -m "not integration and not staging" — 701 passed, 63 deselected
  - ruff / ruff format / mypy (73 files) — clean; PR #12 green on all four checks
---

## Prompt

i want to be 100% syre that there's no issues with the workflow therefore i want you to test it as different users with different inputs and requirements and capture any errors/bugs and fix them simultanously

## Response snapshot

Built an escalation ladder — cheap and broad first, expensive and mutating
last — and fixed each defect as it surfaced.

**19 synthetic profiles** varying what the code branches on: every capability
subset, apostrophes, quotes, non-ASCII names, a 60-character org id, 24/7 and
fully-closed weeks, twelve services and none. **6 live conversations** varying
how a user talks: casual phrasing, requirements spread across five turns, a
mid-conversation correction, a request for voice suggestions, human_transfer
alone, a non-ASCII name.

Five defects found, all fixed.

1. *`agent-forge generate` failed on every input.* The agents read
   `capabilities`, `vapi.voice_id`, `hosting.webhook_base_url` and
   `server_source_path`; that reshaping lived inline in the execute path only.
   Fixing the crash alone would still have produced the default voice and no
   capabilities. Both entry points now share `build_generation_intake`.

2. *Non-ASCII intakes were corrupted at load.* `load_intake_file` opened
   without an encoding, so Windows used cp1252 and "Café München" became
   "CafÃ© MÃ¼nchen" — propagating into the generated assistant name and on
   toward Vapi. Three sibling reads had the same shape; a test now walks the
   source so the next one fails in CI rather than in a client's name.

3. *Clients without booking got scenarios but no tenant.* Every generated Make
   scenario opens with `supabase:searchRows`, yet the database was gated on
   "booking" in three places. An availability-only or cancellation-only client
   deployed scenarios querying an organization nobody created.
   `DATABASE_BACKED_CAPABILITIES` expresses the real condition once.

4. *Extracted voice ids lost their casing.* "use the Savannah voice" yielded
   "savannah", which `is_valid_vapi_voice` rejects — an assistant that deploys
   and cannot speak. `normalize_voice_id` restores canonical casing and drops
   anything unrecognised so the conversation asks again.

5. *Two pre-existing tests encoded bug 3, and two encoded a pre-Vapi voice
   catalogue.* They asserted availability produced no tenant, and that
   "jennifer"/"rachel" were valid voices. Corrected, with the reasoning
   recorded, and paired with tests for what they were really describing.

**Also learned, not a code defect:** the Gemini free tier allows 20 requests
per day per model. `gemini-3.5-flash` was exhausted partway through the
conversational matrix. `gemini-3.5-flash-lite` extracts equally well on the
production schema and draws on a separate quota pool.

## Outcome

- ✅ Impact: five defects closed, three of which broke entire classes of client
  — anyone using `generate`, anyone with an accented name, anyone not buying
  booking.
- 🧪 Tests: 701 passed (from 687), 33 added; ruff, format, mypy clean; PR #12
  green. Verified afterwards that all 19 profiles generate, capability filtering
  is exact, all 146 generated JSON files parse, SQL escapes apostrophes as
  'O''Brien & Associates, P.C.', and all six conversations produce valid intakes.
- 📁 Files: three commits. Test output directories removed from `outputs/`.
- 🔁 Next prompts: consider `gemini-3.5-flash-lite` as the default given the
  quota; the live update/drift path is still untested end to end; rollback
  remains absent from the update path.
- 🧠 Reflection: every one of the 19 profiles exited 0 on `onboard --dry-run`,
  and that told me nothing — dry-run does not write artifacts, so it never
  exercised the generators where the bugs were. The bugs appeared only once I
  ran `generate` and then read the files it produced. Exit codes were the wrong
  instrument twice in one session.

## Evaluation notes (flywheel)

- Failure modes observed: I initially treated `--dry-run` as coverage of the
  generation path and reported 19 passes on that basis. It plans only. Also
  wrote a persona check comparing a business name against the generated
  assistant name, which surfaced the mojibake — a check I nearly dismissed as
  a false positive before looking at the codepoints.
- Graders run and results (PASS/FAIL): validate/normalize PASS (19/19),
  generate PASS (19/19 after fixes), artifact inspection PASS, capability
  coherence PASS (31/31 subsets), conversational matrix PASS (6/6 after fixes),
  pytest PASS (701), ruff PASS, format PASS, mypy PASS, CI PASS.
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): drive the same 19 profiles through
  `onboard --execute` against a mocked adapter layer, so the execution path
  gets the same subset coverage the generation path now has without creating
  live resources.
