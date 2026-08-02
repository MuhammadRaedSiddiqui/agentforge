# Tasks: Conversational Intake Orchestrator

**Input**: Design documents from `/specs/010-conversational-orchestrator/`
**Prerequisites**: spec.md (required), constitution.md v1.1.0 (Principle IX)
**Feature Branch**: `010-conversational-orchestrator`
**Upstream Dependency**: All execution-layer code from `001-agent-forge-onboarding` (complete)

**Organization**: Tasks follow the 8-phase build sequence from the implementation plan. Each phase has an explicit exit gate.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Path Conventions

- **New source**: `orchestrator/conversation_state.py`, `orchestrator/intake_extractor.py`, `orchestrator/dialogue_engine.py`, `orchestrator/conversation_agent.py`, `cli/chat.py`, `memory/orchestrator_system_prompt.md`
- **Updated source**: `cli/main.py`, `orchestrator/intake_schema.py`
- **Tests**: `tests/unit/test_conversation_state.py`, `tests/unit/test_intake_extractor.py`, `tests/unit/test_dialogue_engine.py`, `tests/unit/test_conversation_agent.py`, `tests/integration/test_full_conversation_flow.py`

---

## Phase 1: Conversation State Foundation

**Purpose**: Data structure tracking gathered fields, missing fields, and session phase. No external dependencies.

- [X] T001 [US1] Create `orchestrator/conversation_state.py` with `SessionPhase` enum (gathering, confirming, executing, complete, aborted), `PartialIntakeData` dataclass (org_id, business_name, phone_number, voice_id, capabilities, industry, timezone, business_hours — all Optional), and `ConversationState` dataclass (phase, partial_intake, messages, confirmed_plan, session_id)
- [X] T002 [US1] Implement `PartialIntakeData.required_fields_present()` returning bool and `missing_required_fields()` returning list of field names for the 5 required fields (org_id, business_name, phone_number, voice_id, capabilities)
- [X] T003 [P] [US1] Unit tests for conversation state in `tests/unit/test_conversation_state.py`: instantiation, serialization, phase transitions, required_fields_present returns correct results for all combinations

**Exit Gate**: `ConversationState` can be instantiated and updated. `partial_intake.required_fields_present()` returns correct results for all field combinations.

---

## Phase 2: Intake Extraction Engine

**Purpose**: Use Gemini function calling to extract structured fields from conversation history. Independently testable.

- [X] T004 [US1] Create `orchestrator/intake_extractor.py` with `EXTRACT_FUNCTION` schema defining all intake fields with extraction-guidance descriptions
- [X] T005 [US1] Implement `extract_from_conversation(messages, model)` that sends conversation history to Gemini with the function schema and returns a dict of extracted fields (empty dict on any failure)
- [X] T006 [US1] Implement `apply_extraction(partial_intake, extracted)` that merges new fields into PartialIntakeData without overwriting existing non-None values (unless correction detected)
- [X] T007 [P] [US1] Unit tests for intake extractor in `tests/unit/test_intake_extractor.py`: extracts business_name, derives org_id, maps capability synonyms, does not extract absent fields, does not overwrite existing fields

**Exit Gate**: Given a conversation where the user states business details, `extract_from_conversation` returns the correct structured dict. Missing fields return absent, not empty strings.

---

## Phase 3: Dialogue Engine

**Purpose**: Given current PartialIntakeData, generate the next question. One question at a time, priority-ordered.

- [X] T008 [US1] Create `orchestrator/dialogue_engine.py` with `FIELD_PRIORITY` list (capabilities, phone_number, voice_id, timezone, business_hours) and `FIELD_QUESTIONS` dict mapping each field to a natural-language question
- [X] T009 [US1] Implement `next_question(partial)` returning the question string for the highest-priority missing field, or None when all required fields present
- [X] T010 [US1] Implement `handle_voice_suggestion_request(text)` returning True if user asks for voice suggestions, plus `VOICE_SUGGESTIONS` constant with common Vapi voice options
- [X] T011 [P] [US1] Unit tests for dialogue engine in `tests/unit/test_dialogue_engine.py`: returns None when complete, asks capabilities first, asks phone before voice, detects voice suggestion requests

**Exit Gate**: `next_question` returns None when all 5 required fields present. For each missing field, returns the correct single question. Never asks for two things at once.

---

## Phase 4: Orchestrator System Prompt

**Purpose**: The agent identity, constraints, tone, and phase-transition rules as a first-class artifact.

- [X] T012 [US1] Create `memory/orchestrator_system_prompt.md` defining: role (conversational intake assistant), what it gathers (5 required + 2 optional fields), questioning rules (one at a time, natural language, no JSON field names), plan confirmation format (plain language summary), constraints (never execute without confirmation, never invent IDs, never ask for credentials), and tone (professional, concise, direct)

**Exit Gate**: System prompt covers all constraints from FR-001 through FR-005. Readable by a human operator as the agent's "job description."

---

## Phase 5: Conversation Agent

**Purpose**: Main Gemini-powered agent wiring together state, extractor, dialogue engine, and plan presentation.

- [X] T013 [US1] Create `orchestrator/conversation_agent.py` with `ConversationAgent` class accepting a Gemini model instance and loading the system prompt from `memory/orchestrator_system_prompt.md`
- [X] T014 [US1] Implement `new_session()` returning a fresh ConversationState with UUID session_id, and `greet()` returning the opening message
- [X] T015 [US1] Implement `turn(user_message, state)` main loop: append message → handle special requests → extract fields → check completeness → generate response or transition phase → return (response, updated_state)
- [X] T016 [US2] Implement `_build_plan_summary(state)` producing a plain-language deployment summary with no JSON field names, listing business name, voice assignment, capabilities in plain English, Supabase record, and backend routes
- [X] T017 [US2] Implement `_is_confirmation(text)` and `_is_cancellation(text)` for phase transition detection during confirming phase
- [X] T018 [US3] Implement `_build_confirmed_intake(state)` converting PartialIntakeData to a dict suitable for `IntakeData` validation and planner handoff
- [X] T019 [US1] Implement `_conversational_response(user_message, state)` that generates a natural Gemini response acknowledging what was provided and asking the single next question via internal guidance injection
- [X] T020 [P] [US1,US2,US3] Unit tests for conversation agent in `tests/unit/test_conversation_agent.py`: phase transitions gathering→confirming, confirming→executing on yes, confirming→aborted on no, return to gathering on change request, plan summary contains no JSON field names

**Exit Gate**: Full turn loop works. Given all 5 fields provided across turns, state transitions correctly through gathering → confirming → executing. Plan summary is human-readable.

---

## Phase 6: CLI Entry Point

**Purpose**: Terminal session entry point and main.py integration.

- [X] T021 [US1] Create `cli/chat.py` with `run_chat_session()` function: initializes Gemini model, creates ConversationAgent, runs conversation loop with Rich console output, handles exit/quit/Ctrl+C gracefully
- [X] T022 [US3] Implement execution handoff in `cli/chat.py`: on SessionPhase.EXECUTING, validate confirmed_plan through IntakeData, build task graph via existing planner, call existing run_deployment with per-action approval
- [X] T023 [US3] Update `cli/main.py` to add `chat` subcommand and make it the default when no subcommand is given (preserving all existing commands unchanged)
- [X] T024 [US1] Add `PartialIntakeData` awareness to `orchestrator/intake_schema.py` — add a `from_partial()` class method on IntakeData that validates a partial dict and returns either IntakeData or a list of validation errors

**Exit Gate**: `agent-forge chat` starts a terminal session. `agent-forge --intake file.json` still works. The user can type naturally and see approval prompts before any platform action.

---

## Phase 7: System Prompt Tuning

**Purpose**: Test the conversational agent against real scenarios and refine until quality is correct.

- [X] T025 [US1] Test Scenario A — Complete upfront: user provides all fields in one message, plan presented immediately
- [X] T026 [US1] Test Scenario B — Incremental disclosure: user provides info across 3-5 turns, system asks one question per turn
- [X] T027 [US1] Test Scenario C — Ambiguous capabilities: user says "add, change and cancel bookings", system maps to ["booking", "rescheduling", "cancellation"] and confirms
- [X] T028 [US1] Test Scenario D — User corrects a field: system updates to new value, does not retain old
- [X] T029 [US1] Test Scenario E — Voice suggestion request: system returns voice options, waits for selection
- [X] T030 [US2] Test Scenario F — User says no to plan: system returns to gathering, updates field, re-presents plan
- [X] T031 [US1,US2] Refine system prompt based on test results until: never asks two fields at once, never uses JSON field names, confirms capability mapping, does not hallucinate voice IDs

**Exit Gate**: All 6 scenarios produce expected behavior. Agent never asks for two fields at once, never uses JSON field names in responses, confirms capability mapping before proceeding.

---

## Phase 8: Automated Tests

**Purpose**: Unit and integration tests ensuring correctness and preventing regression.

- [X] T032 [P] [US1] Integration test `tests/integration/test_full_conversation_flow.py`: test_complete_intake_in_one_turn (mock Gemini)
- [X] T033 [P] [US1] Integration test: test_incremental_intake_across_five_turns (mock Gemini responses per turn)
- [X] T034 [P] [US1] Integration test: test_correction_mid_conversation_updates_field
- [X] T035 [P] [US3] Integration test: test_handoff_produces_valid_intake_data (confirmed plan passes IntakeData validation)
- [X] T036 [US3] Verify all existing tests pass with no regressions: `pytest tests/ -v`
- [X] T037 [US3] Verify backward compatibility: `agent-forge --intake tests/fixtures/staging_client.json` produces same output as before

**Exit Gate**: All new tests pass. `pytest tests/ -v` shows zero regressions. JSON intake path works identically.

---

## Completion Criteria

The conversational intake transformation is complete when:

1. `agent-forge chat` starts a session and the user can type naturally
2. All 6 test scenarios in Phase 7 pass with correct behavior
3. A full conversation → deployment runs end-to-end with approval gates firing per action
4. `agent-forge --intake file.json` still works (backward compatibility)
5. All existing tests pass with no regressions
6. New unit and integration tests pass
7. This spec file is matched by implementation
8. CLAUDE.md and constitution.md are updated (done)
9. Two ADR records created for architectural decisions
