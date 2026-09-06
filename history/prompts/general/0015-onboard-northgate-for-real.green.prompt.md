---
id: 0015
title: Onboard Northgate For Real
stage: green
date: 2026-09-06
surface: agent
model: claude-opus-5
feature: none
branch: fix/post-phr10-hotfix
user: MuhammadRaedSiddiquie
command: go ahead and onboard northgate for real
labels: ["deployment", "vapi", "make", "verification", "bug"]
links:
  spec: null
  ticket: null
  adr: null
  pr: https://github.com/MuhammadRaedSiddiqui/agentforge/pull/12
files:
  - (no source changes; live deployment 4cedaad4-0717-4f64-a053-d583f13f6a84)
  - outputs/northgate_dental/vapi/assistant_config.json (generated, 4 tools defined)
tests:
  - onboard --dry-run — 7 intended external changes
  - onboard --execute --auto-approve — exit 0, 8 of 8 actions completed
  - live verification against Vapi, Make and the generated config
---

## Prompt

go ahead and onboard northgate for real

## Response snapshot

Ran the real onboarding after a dry run enumerated the actions, so
`--auto-approve` was informed rather than blind. Deployment
`4cedaad4-0717-4f64-a053-d583f13f6a84` reported **SUCCESS, 8 of 8 actions**,
exit 0.

Created, and independently verified against the platforms:

  - Supabase org record `northgate_dental`
  - Vapi assistant `b2cf9718-f0bf-4d4d-8b85-01b446864182`, voice `Elliot`
    with `provider: vapi` (correct per the built-in-voices gotcha)
  - Make scenarios 6171144/45/46/47, all `isActive: true`
  - Render env var `CLIENT_NORTHGATE_DENTAL_ENABLED`, deploy
    `dep-daeih0lbedkc73ddg200`

**The reported success does not mean the client works.** Verification against
the live platforms found three defects:

1. *The assistant has no tools.* `outputs/northgate_dental/vapi/assistant_config.json`
   defines four, but `orchestrator.py:518` does
   `assistant_config.pop("tools", None)` — correct in itself, since Vapi's
   create endpoint rejects inline tools — and nothing puts them back.
   `action_builder.py` emits five operation types and `create_tool` is not one
   of them, though `VapiAdapter.create_tool` exists and the orchestrator has a
   branch to execute it. Live check: `toolIds`, `model.toolIds` and
   `model.tools` are all None. The assistant can converse and can do nothing.

2. *The phone number was never assigned.* `+19086846982` still points at the
   previous assistant `8d33aa1e`. The action payload carries
   `phone_number_id: None`, so the guard at `orchestrator.py:522` never fired —
   even though the intake carries `external_identifiers.vapi_phone_number_id`.
   Worse, that call sits inside `contextlib.suppress(Exception)`, so had it
   fired and failed the action would still have reported success.

3. *`serverUrl` is the health endpoint*, `https://averon-ztfm.onrender.com/health`.
   Tool webhooks would POST to a health check.

The common thread: an action's success criterion is "the API returned 200",
not "the resource is usable". Eight green receipts and an audit trail all
record a successful deployment of a client that cannot receive a call.

## Outcome

- ✅ Impact: the create path runs end to end against live platforms, and doing
  it for real exposed three defects that no test caught.
- 🧪 Tests: dry run 7 actions; execute 8/8 exit 0; live verification of Vapi
  assistant, phone assignment, four Make scenarios and the generated config.
- 📁 Files: no source changes. Live resources created and left in place.
- 🔁 Next prompts: emit `create_tool` actions after `create_assistant`; put
  `vapi_phone_number_id` into the create payload and stop suppressing the
  assignment failure; point `serverUrl` at the webhook route rather than
  `HOSTING_HEALTH_URL`. Then re-run and verify the assistant can take a call.
  The four Make scenarios are active and will consume operations quota until
  cleaned up.
- 🧠 Reflection: every earlier layer of verification passed — 626 unit tests,
  four CI gates, a dry run, and eight approval receipts — and the deployed
  client is still non-functional. Each gate checked that a step was performed,
  none checked that the result was usable. Post-deployment verification against
  the live platform is the only thing that found this, which is an argument for
  making it part of the deployment rather than something done afterwards by
  hand.

## Evaluation notes (flywheel)

- Failure modes observed: `contextlib.suppress(Exception)` around the phone
  assignment converts a client-breaking failure into a silent one inside an
  action that reports success — the same swallow-and-continue pattern the
  original evaluation flagged elsewhere. Separately, the generator writes four
  tools that the executor is guaranteed to discard, so the two halves disagree
  about the contract and nothing detects it.
- Graders run and results (PASS/FAIL): dry run PASS, execute PASS (8/8),
  assistant exists PASS, scenarios exist PASS, tools attached FAIL, phone
  assigned FAIL, serverUrl correct FAIL.
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): add a post-deployment verification
  step asserting that a created assistant has at least as many tools as its
  generated config defined, and that its phone number resolves to it — turning
  all three defects into deployment failures rather than silent ones.
