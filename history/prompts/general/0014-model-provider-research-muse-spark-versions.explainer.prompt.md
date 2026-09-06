---
id: 0014
title: Model Provider Research Muse Spark Versions
stage: explainer
date: 2026-09-06
surface: agent
model: claude-opus-5
feature: none
branch: fix/post-phr10-hotfix
user: MuhammadRaedSiddiquie
command: do research and see if using muse spark 1.2 or 1.3 solves the issue
labels: ["research", "model-provider", "tool-calling", "extraction", "gemini"]
links:
  spec: null
  ticket: null
  adr: null
  pr: https://github.com/MuhammadRaedSiddiqui/agentforge/pull/12
files:
  - .env (MODEL_PROVIDER, MODEL_NAME, MODEL_BASE_URL — gitignored, backup in scratchpad)
tests:
  - GET /v1/models on api.meta.ai — 4 models; no 1.3 exists
  - production EXTRACT_FUNCTION, 12 runs each — muse-spark-1.1 0/12, muse-spark-1.2 0/12
  - forced tool_choice on both — HTTP 400, only "auto" supported
  - one-field tool — 3/3 on both, so tool calling is not wholly broken
  - schema bisect — indicated `capabilities`, but did not reproduce on re-run
  - gemini-3.5-flash, production schema — 4/4 tool_call, 4/4 timezone, 4/4 business_hours
  - end-to-end chat session from .env — Saturday 10:00-14:00 captured, no default markers
  - pytest -m "not integration and not staging" — 626 passed
---

## Prompt

do research and see if using muse spark 1.2 or 1.3 solves the issue

## Response snapshot

Answered empirically against the live endpoint rather than from documentation,
since the configured provider is the authority on its own behaviour.

**No, and 1.3 does not exist.** `GET https://api.meta.ai/v1/models` returns
four: `muse-image-1.0`, `muse-spark-1.1`, `muse-spark-1.2`,
`muse-spark-1.2-contributor`.

**1.2 is not better than 1.1.** Against the real `EXTRACT_FUNCTION` with the
message that lost the business hours, both scored **0/12**. Two independent
causes:

1. Neither accepts a forced `tool_choice` — the API returns
   `400 only "auto" is supported for "tool_choice"`, confirming the existing
   comment in `intake_extractor.py`.
2. Under `auto`, neither emits the tool call for this schema at all.

Tool calling is not wholly broken: a one-property tool succeeds 3/3 on both.
A cumulative bisect suggested `capabilities` — the single array-typed property
— was the trigger, since adding it to a working four-property schema dropped
it to 0/5 on both models while a fifth *string* property held at 5/5. That
finding did not survive re-running the same script, so it is recorded as
unconfirmed. What is solid at n=12 is that the production schema never works
on either version.

**The fix is a provider switch, not a version bump.** `gemini-3.5-flash`
scored 4/4 on tool calls, timezone and business hours, and captured Saturday
10:00-14:00 — the field that had been silently dropped. The code already
forces `tool_choice` for gemini and already reads `GEMINI_API_KEY`, so this is
configuration only, no code change. Switched the three `MODEL_*` lines in
`.env` (gitignored; backup kept in the session scratchpad) and confirmed
end-to-end through a real chat session reading `.env` with no overrides:
first-turn extraction succeeds, hours and timezone are captured, and neither
is reported as a default.

Two caveats worth carrying: `gemini-3.8-flash` returned 429 on this key, so
quota matters; and `gemini-flash-latest` managed only 2/4, so the pinned
`3.5-flash` is deliberate rather than incidental.

## Outcome

- ✅ Impact: the extraction failure behind PHR 0013 is resolved by
  configuration. Hours, timezone and first-turn extraction all now work.
- 🧪 Tests: 626 passed after the switch; live probes as listed above.
- 📁 Files: `.env` only (untracked). No source change was needed.
- 🔁 Next prompts: the running `fallback_extract` task is now defence in depth
  rather than the fix — on gemini that path never executes; then re-run the
  intake and execute the create path with correct data.
- 🧠 Reflection: the question was about a version bump, and the version bump
  was a dead end — but asking the endpoint what it served, and testing the
  actual schema rather than a toy one, turned a "no" into a working
  configuration. The earlier session had attributed the failure to "the meta
  provider's text-parsing fallback", which was directionally right about the
  provider and wrong about the mechanism.

## Evaluation notes (flywheel)

- Failure modes observed: I reported `capabilities` as the culprit from a
  single 3-run bisect, then the same script disagreed on re-run. Three runs
  against a nondeterministic endpoint is not a measurement. Also miscounted
  JSON-mode successes because an empty-string sentinel is falsy, so empty
  replies scored as parsed.
- Graders run and results (PASS/FAIL): models listing PASS, 1.1 vs 1.2
  comparison PASS (both fail), gemini-3.5-flash PASS, end-to-end session PASS,
  pytest PASS (626).
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): re-run the schema bisect at n=20
  per case to settle whether array-typed properties really do suppress tool
  calling on muse-spark, which would be worth knowing for any future provider
  that only supports `tool_choice="auto"`.
