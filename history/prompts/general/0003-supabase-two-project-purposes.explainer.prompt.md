---
id: 0003
title: Supabase Two Project Purposes
stage: explainer
date: 2026-08-10
surface: agent
model: opencode/deepseek-v4-flash-free
feature: none
branch: phase4-update-flow
user: MuhammadRaedSiddiquie
command: this project currently has 2 supabase projects, can you tell what is the purpose of each and why 2 databases and not one
labels: ["supabase", "architecture", "explainer"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - history/prompts/general/0003-supabase-two-project-purposes.explainer.prompt.md
tests:
  - null
---

## Prompt

this project currently has 2 supabase projects, can you tell what is the purpose of each and why 2 databases and not one

## Response snapshot

Explained the two Supabase projects are split by purpose/trust boundary (per knowledge-base/docs/supabase-guide.md:7-9):

1. **Internal project** (SUPABASE_INTERNAL_URL) - platform's own operational store: deployment state, task executions, audit events, recovery actions, receipts. Accessed via adapters/supabase_internal.py (SupabaseInternalClient) and apply_migrations.py. Full service-role access.
2. **Client project** (SUPABASE_CLIENT_URL) - tenant/client-facing business data: organizations (and future appointments). Accessed via adapters/supabase_client.py (SupabaseClientAdapter) with strict table allowlist (ALLOWED_TABLES) and RLS/tenant isolation. Env vars still unset (ENV_VARIABLES_GUIDE.md:96 marks pending setup).

Why two and not one: separation of concerns - security/blast-radius isolation between operational data (audit, state) and client tenant data; different trust/access patterns (internal trusts service role, client enforces allowlist + RLS); lifecycle independence (client project provisioned per deployment, not yet created).

## Outcome

- ✅ Impact: Delivered a clear explanation of each Supabase project's purpose and the rationale for two databases (separation of concerns, security/blast radius, differing trust patterns, lifecycle independence).
- 🧪 Tests: none run (research-only question).
- 📁 Files: no source changes; created this PHR.
- 🔁 Next prompts: set up the client project env vars, deep-dive the internal store schema/migrations, or review RLS policies.
- 🧠 Reflection: The two-database split is a deliberate isolation decision; the client project is still pending setup while the internal store is live.

## Evaluation notes (flywheel)

- Failure modes observed: none
- Graders run and results (PASS/FAIL): N/A
- Prompt variant (if applicable): N/A
- Next experiment (smallest change to try): configure SUPABASE_CLIENT_URL/KEY and verify client adapter against a live project
