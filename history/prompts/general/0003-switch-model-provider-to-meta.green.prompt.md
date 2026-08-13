---
id: 0003
title: Switch Model Provider to Meta
stage: green
date: 2026-08-10
surface: agent
model: opencode/deepseek-v4-flash-free
feature: none
branch: phase4-update-flow
user: MuhammadRaedSiddiquie
command: replace bedrock configuration with meta muse-spark-1.1
labels: ["config", "model-provider", "env"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - .env
  - .env.example
tests:
  - python model init check (provider=meta, model_id=muse-spark-1.1)
---

## Prompt

the issue is the project currently uses bedrock configuration, replace it with meta muse-spark-1.1

## Response snapshot

Diagnosis: The `.env` already contained the Meta configuration (`META_API_KEY`, `MODEL_PROVIDER=meta`, `MODEL_NAME=muse-spark-1.1`, `MODEL_BASE_URL=https://api.meta.ai/v1`) but a later block at the bottom of the file set `MODEL_PROVIDER=bedrock` plus AWS credentials. Since python-dotenv applies last-wins, the bedrock override was winning at runtime.

Confirmed code path: `adapters/model_wrapper.py:initialize_model()` reads `MODEL_PROVIDER`, and for `meta` uses `META_API_KEY` / `MODEL_NAME` (default `muse-spark-1.1`) / `MODEL_BASE_URL`. `config/agent_registry.json` "model" fields are metadata only (not consumed for runtime model selection).

Fixes:
1. `.env`: removed the trailing bedrock override block (MODEL_PROVIDER=bedrock, AWS keys, BEDROCK_MODEL_ID) and consolidated the single active Meta provider config; kept META_API_KEY, MODEL_PROVIDER=meta, MODEL_NAME=muse-spark-1.1, MODEL_BASE_URL.
2. `.env.example`: changed default from bedrock to meta (MODEL_PROVIDER=meta, MODEL_NAME=muse-spark-1.1, MODEL_BASE_URL), moved AWS/Bedrock vars behind comments as an optional alternative.

Verification: `initialize_model()` now resolves provider=meta, model_id=muse-spark-1.1 via dotenv load.

## Outcome

- ✅ Impact: Project model provider switched from Bedrock to Meta muse-spark-1.1; no code changes needed since ModelWrapper already supports the meta provider.
- 🧪 Tests: model initialization verified (meta/muse-spark-1.1). Full smoke test would require a live network call to api.meta.ai.
- 📁 Files: .env, .env.example.
- 🔁 Next prompts: run `agent-forge smoke-test meta` to confirm live connectivity, then re-run the conversational onboarding flow.
- 🧠 Reflection: Root cause was a duplicate/overriding env block in .env (last-wins semantics), not code. Keeping one canonical model config section avoids this class of bug.

## Evaluation notes (flywheel)

- Failure modes observed: duplicate MODEL_PROVIDER assignment where the later bedrock value silently overrode meta.
- Graders run and results (PASS/FAIL): provider resolution PASS.
- Prompt variant (if applicable): N/A
- Next experiment (smallest change to try): live `agent-forge smoke-test meta` against api.meta.ai
