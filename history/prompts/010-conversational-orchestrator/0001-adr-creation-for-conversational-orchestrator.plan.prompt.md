---
id: "0001"
title: ADR creation for conversational orchestrator
stage: plan
date: 2026-07-23
surface: agent
model: claude-opus-4-6
feature: 010-conversational-orchestrator
branch: 001-agent-forge-onboarding
user: MuhammadRaedSiddiquie
command: /sp.adr
labels: ["adr", "architecture", "conversational-intake"]
links:
  spec: specs/010-conversational-orchestrator/spec.md
  ticket: null
  adr: history/adr/004-deterministic-execution-pipeline-over-autonomous-agents.md, history/adr/005-conversational-interface-over-json-intake.md
  pr: null
files:
  - history/adr/004-deterministic-execution-pipeline-over-autonomous-agents.md
  - history/adr/005-conversational-interface-over-json-intake.md
  - .specify/memory/constitution.md
  - CLAUDE.md
  - specs/010-conversational-orchestrator/spec.md
  - specs/010-conversational-orchestrator/tasks.md
tests:
  - null
---

## Prompt

/sp.adr Execution layer is deterministic pipeline, not autonomous agents

## Response snapshot

Created two ADRs documenting architectural decisions for the conversational orchestrator feature:
- ADR-004: Deterministic Execution Pipeline Over Autonomous Agents — the execution layer uses a code-controlled state machine rather than an autonomous agent loop, ensuring approval gates cannot be bypassed.
- ADR-005: Conversational Interface Over JSON Intake — the primary interface is natural language conversation, with JSON intake preserved as an automation path.

Also updated CLAUDE.md with two-half architecture, added Principle IX to constitution, and created specs/010-conversational-orchestrator/ with spec.md and tasks.md.

## Outcome

- Impact: Two ADRs created, constitution amended (v1.1.0), CLAUDE.md updated, feature spec and tasks created
- Tests: N/A (documentation artifacts)
- Files: 6 files created/modified
- Next prompts: /sp.implement against tasks.md
- Reflection: Clustered decisions appropriately — execution model and interface choice are independent architectural axes

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run and results (PASS/FAIL): Significance test PASS (both ADRs cross-cutting, have alternatives, will be revisited)
- Prompt variant (if applicable): N/A
- Next experiment (smallest change to try): N/A
