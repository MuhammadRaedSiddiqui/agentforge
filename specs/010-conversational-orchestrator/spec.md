# Feature Specification: Conversational Intake Orchestrator

**Feature Branch**: `010-conversational-orchestrator`
**Created**: 2026-07-23
**Status**: Draft
**Constitution Version**: 1.1.0
**Input**: Transform Agent Forge's intake layer from JSON-file-only to a conversational AI system where the operator speaks naturally and the Orchestrator Agent extracts intent, gathers requirements, and hands off to the existing execution pipeline.

## Scope

**In scope**: Conversational intake session, structured field extraction via Gemini function calling, gap detection and question generation, plan confirmation flow, CLI chat entry point, backward-compatible JSON intake path.

**Out of scope**: Execution pipeline changes, specialist agent modifications, adapter changes, database schema changes, approval gate modifications, recovery system changes.

## Constitution Check

- [x] Principle I: Specification governs — this spec defines the conversational layer
- [x] Principle II: Model output is untrusted — extraction uses typed function schemas, not free-form parsing
- [x] Principle III: Human authority — user must explicitly confirm plan before execution begins
- [x] Principle IV: Read before write — no writes occur until user confirms
- [x] Principle IX: Natural language is the interface — this feature implements that principle

---

## User Story 1 — Describe a Client in Natural Language (Priority: P1)

As an operator, I want to describe a client in plain English so that I do not need to write a JSON file to start a deployment.

**Why this priority**: This is the core value proposition of the conversational layer — reducing onboarding friction from JSON authoring to natural dialogue.

**Independent Test**: Start a chat session, describe a client across multiple turns, and verify that the system extracts all required fields, asks for missing information one question at a time, and transitions to plan presentation when complete.

**Acceptance Scenarios**:

1. **Given** the user provides all required fields in a single message, **When** extraction runs, **Then** all fields are captured and the plan is presented immediately.
2. **Given** the user provides partial information, **When** the turn completes, **Then** the system asks for exactly one missing field (the highest priority one).
3. **Given** the user uses non-standard terminology for capabilities (e.g., "add bookings"), **When** extraction runs, **Then** the system maps to canonical capability names and confirms the mapping.
4. **Given** the user corrects a previously stated field, **When** extraction runs, **Then** the corrected value replaces the old value.
5. **Given** the user asks for voice suggestions, **When** the request is detected, **Then** common voice options are presented without requiring a specific voice ID yet.

---

## User Story 2 — Confirm Deployment Plan in Plain Language (Priority: P1)

As an operator, I want to see a plain-language summary of what will be built before any deployment begins, so I can catch errors without reading JSON.

**Why this priority**: Confirmation is a constitutional requirement (Principle III) and the bridge between conversational intake and deterministic execution.

**Independent Test**: Complete the intake conversation, verify the plan summary uses plain language (no JSON field names), and confirm that typing "yes" transitions to execution while "no" or change requests return to gathering.

**Acceptance Scenarios**:

1. **Given** all required fields are present, **When** the plan is presented, **Then** it uses human-readable descriptions (not field names like `org_id` or `voice_id`).
2. **Given** the plan is presented, **When** the user types "yes" (or equivalent affirmative), **Then** the session transitions to execution with a validated IntakeData object.
3. **Given** the plan is presented, **When** the user types "cancel" (or equivalent negative), **Then** the session is aborted and nothing is deployed.
4. **Given** the plan is presented, **When** the user describes a change, **Then** the session returns to gathering, updates the field, and re-presents the plan.

---

## User Story 3 — Hand Off to Execution Pipeline (Priority: P1)

As an operator, I want the confirmed intake to flow seamlessly into the existing deployment pipeline with per-action approval, so the conversational layer does not bypass any safety mechanisms.

**Why this priority**: The handoff is where the two halves connect — conversational intake must produce output identical to what JSON intake produces.

**Independent Test**: Complete a full conversation, confirm the plan, and verify that `IntakeData` validation passes, `planner.py` receives a valid object, and execution begins with approval gates firing per action.

**Acceptance Scenarios**:

1. **Given** the user confirms the plan, **When** handoff occurs, **Then** `IntakeData(**confirmed_plan)` passes all existing validation rules.
2. **Given** a confirmed plan with all required and optional fields, **When** execution starts, **Then** the task graph is identical to one produced from equivalent JSON intake.
3. **Given** a confirmed plan, **When** execution begins, **Then** per-action approval gates fire exactly as they do with JSON intake.
4. **Given** a validation error in the confirmed plan, **When** handoff is attempted, **Then** errors are shown and the user is asked to correct via conversation.

---

## Functional Requirements

### FR-001: Conversation State Management

The system MUST maintain a `ConversationState` object tracking: session phase (gathering, confirming, executing, complete, aborted), partial intake data, message history, confirmed plan, and session ID. Phase transitions MUST be explicit and validated.

### FR-002: Structured Field Extraction

The system MUST use Gemini function calling (not text parsing) to extract structured fields from conversation history. The extraction function schema MUST define all intake fields with descriptions. Extraction MUST only populate fields the model is confident about — never guess. Extraction MUST never overwrite confirmed values unless the user explicitly corrects them.

### FR-003: Gap Detection and Prioritized Questioning

The system MUST detect missing required fields and ask for them one at a time in priority order: capabilities → phone_number → voice_id → timezone → business_hours. The system MUST NOT present multiple questions simultaneously.

### FR-004: Plan Presentation

When all required fields are present, the system MUST present a plain-language deployment summary. The summary MUST NOT contain JSON field names, raw IDs without context, or technical schema terminology. The summary MUST list: business name, voice and phone assignment, capabilities in plain language, database record, and backend routes.

### FR-005: Confirmation and Phase Transitions

The system MUST accept affirmative responses (yes, y, yep, yeah, correct, proceed, go ahead, looks good, confirmed, ok, okay) as confirmation. Negative responses (no, n, cancel, stop, abort, quit, exit) MUST abort. Any other response during confirmation MUST return to gathering phase.

### FR-006: CLI Chat Entry Point

The system MUST provide an `agent-forge chat` CLI command that starts an interactive conversational session. The existing `agent-forge --intake file.json` path MUST continue to work unchanged. Running `agent-forge` without arguments SHOULD default to the chat session.

---

## Success Criteria

- SC-001: All 6 test scenarios (complete upfront, incremental, ambiguous capabilities, correction, voice suggestion, plan rejection) pass
- SC-002: `agent-forge chat` starts and completes a full intake → confirm → execute flow
- SC-003: `agent-forge --intake file.json` continues to work with no regressions
- SC-004: All existing tests pass unchanged
- SC-005: New unit and integration tests pass
- SC-006: The conversational agent never asks for two fields at once
- SC-007: Plan summary contains zero JSON field names
