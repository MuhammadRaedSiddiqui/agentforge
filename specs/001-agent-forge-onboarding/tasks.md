# Tasks: Safe Client Deployment Automation

**Input**: Design documents from `/specs/001-agent-forge-onboarding/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/tool-contracts.yaml, quickstart.md
**Feature Branch**: `001-agent-forge-onboarding`
**Tests**: Included per FR-047 through FR-053 (explicit spec requirement for automated verification at every layer)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Runtime**: Python 3.11+ single project at repository root
- **Source**: `agents/`, `orchestrator/`, `adapters/`, `shared/`, `cli/`, `config/`, `scripts/`
- **Tests**: `tests/unit/`, `tests/contract/`, `tests/integration/`, `tests/failure_injection/`, `tests/security/`, `tests/restoration/`, `tests/fixtures/`, `tests/snapshots/`
- **Ground Truth**: `ground-truth/configs/`, `ground-truth/schemas/`
- **Knowledge**: `knowledge-base/docs/`, `knowledge-base/gotchas/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Repository scaffold, dependency lock, environment contract, and initial smoke tests

- [X] T001 Create canonical project directory structure per plan.md layout at repository root
- [X] T002 Create pyproject.toml with Python 3.11+ metadata and dependency specifications in pyproject.toml
- [X] T003 Create requirements.txt with pinned minimum versions for openai-agents, openai, chromadb, supabase, python-dotenv, requests, pytest in requirements.txt
- [X] T004 [P] Create .env.example from canonical environment contract (19 variables including MAKE_ZONE, HOSTING_HEALTH_URL, AGENT_FORGE_ENV) in .env.example
- [X] T005 [P] Create .gitignore excluding .env, backups/, chroma_data/, outputs/, __pycache__/, .venv/ in .gitignore
- [X] T006 [P] Create config/agent_registry.json with five specialist agent definitions in config/agent_registry.json
- [X] T007 [P] Create config/capability_map.json mapping capabilities to required inputs, artifacts, and domains in config/capability_map.json
- [X] T008 [P] Create config/vendor_contract_versions.json with placeholder version entries for each external platform in config/vendor_contract_versions.json
- [X] T009 Implement environment loader and configuration validator in cli/config.py
- [X] T010 Implement Gemini compatibility smoke test (model selection, structured output, function tool, multi-turn, sanitized error) in tests/integration/test_gemini_smoke.py
- [X] T011 Implement Chroma persistence smoke test (create collection, insert, retrieve, delete) in tests/integration/test_chroma_smoke.py
- [X] T012 Create pytest configuration with markers (unit, contract, integration, staging, security, restoration, failure_injection) in pyproject.toml
- [X] T013 [P] Configure ruff formatting and linting rules in pyproject.toml
- [X] T014 [P] Configure mypy type checking for all source packages in pyproject.toml

**Exit Gate**: Gemini and Chroma smoke tests pass; environment validates without secrets leaking; vendor contract versions placeholder exists.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core shared modules, internal operational store, and base infrastructure that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

### Shared Modules

- [X] T015 [P] Implement custom error hierarchy (validation, authorization, conflict, transient, permanent, ambiguous, compensation, persistence) in shared/errors.py
- [X] T016 [P] Implement deterministic ID generation (UUID, task ID format, knowledge entry ID) in shared/ids.py
- [X] T017 [P] Implement SHA-256 content hashing with canonical serialization in shared/hashing.py
- [X] T018 [P] Implement secret redaction utilities (scan, mask, validate-absence) in shared/redaction.py
- [X] T019 [P] Implement TaskObject dataclass (task_id, deployment_id, agent_target, action_type, context_hash, constraints, dependencies, verification_required, status) in shared/task_object.py
- [X] T020 [P] Implement ResultObject dataclass (task_id, agent_source, content_hash, storage_path, summary, field_provenance, model_id, validation_status) in shared/result_object.py
- [X] T021 [P] Implement ActionContract dataclass (platform, operation, target, payload_hash, state_version, idempotency_key, retry_policy, reconciliation_strategy, compensation_operation) in shared/action_contract.py

### Internal Operational Store

- [X] T022 Implement Supabase internal client wrapper with connection management in adapters/supabase_internal.py
- [X] T023 Create SQL migration for Organization and OrganizationIntake tables with constraints per data-model.md in supabase/migrations/001_organizations.sql
- [X] T024 Create SQL migration for Deployment table with state-transition check constraint and partial unique index in supabase/migrations/002_deployments.sql
- [X] T025 Create SQL migration for Session table in supabase/migrations/003_sessions.sql
- [X] T026 Create SQL migration for TaskExecution table with agent_target immutability and dependency constraints in supabase/migrations/004_task_executions.sql
- [X] T027 Create SQL migration for Artifact and ValidationReport tables with hash and provenance fields in supabase/migrations/005_artifacts.sql
- [X] T028 Create SQL migration for ProposedAction, ApprovalDecision, ExternalRequestAttempt, ExternalReceipt tables with append-only constraints in supabase/migrations/006_actions.sql
- [X] T029 Create SQL migration for ExternalResource table with unique platform+type+remote_id constraint in supabase/migrations/007_resources.sql
- [X] T030 Create SQL migration for RecoveryAction table in supabase/migrations/008_recovery.sql
- [X] T031 Create SQL migration for AuditEvent table with update/delete restriction and hash chain fields in supabase/migrations/009_audit.sql
- [X] T032 Create SQL migration for SourceTemplate and DeploymentRecord tables in supabase/migrations/010_templates_records.sql
- [X] T033 Create SQL migration for all query indexes per data-model.md recommendations in supabase/migrations/011_indexes.sql

### Gemini Model Wrapper

- [X] T034 Implement Gemini OpenAI-compatible model wrapper (OpenAIChatCompletionsModel with explicit provider setup, single construction, API key isolation, model selection validation, startup failure on unavailable model) in adapters/gemini.py

### State Machine and Base Adapter

- [X] T035 Implement deployment state machine with valid transitions and illegal-transition rejection in orchestrator/state_machine.py
- [X] T036 Implement base HTTP adapter class with timeout (10s connect, 30s read), retry classification, redaction, request ID tracking, and typed receipt in adapters/base.py

### Foundational Tests

- [X] T037 [P] Unit tests for shared/errors.py, shared/ids.py, shared/hashing.py, shared/redaction.py in tests/unit/test_shared.py
- [X] T038 [P] Unit tests for deployment state machine transitions (valid, invalid, all paths) in tests/unit/test_state_machine.py
- [X] T039 [P] Unit tests for base adapter timeout, retry classification, redaction, and receipt behavior in tests/unit/test_adapter_base.py
- [X] T040 Integration test for internal store: create org, insert intake, create deployment, transition states in tests/integration/test_internal_store.py
- [X] T041 Security test for redaction: verify no secret patterns in sanitized outputs in tests/security/test_redaction.py

**Checkpoint**: Foundation ready — shared contracts typed, internal store operational, state machine tested, adapter base validated. User story implementation can now begin.

---

## Phase 3: User Story 1 — Preview a Complete Client Onboarding (Priority: P1) MVP

**Goal**: Operator enters new client intake and previews the full onboarding sequence with zero external side effects.

**Independent Test**: Provide a valid new-client intake fixture, request a preview, and verify a complete ordered plan is returned containing dependencies, validations, approval points, expected outputs, and intended changes — while making zero external writes.

### Tests for User Story 1

- [X] T042 [P] [US1] Unit test for intake schema validation (valid, missing fields, invalid formats, capability-specific required fields) in tests/unit/test_intake_schema.py
- [X] T043 [P] [US1] Unit test for planner task graph generation (correct ordering, dependencies, approval points, all capabilities) in tests/unit/test_planner.py
- [X] T044 [P] [US1] Integration test for full dry-run flow (fixture in, plan out, zero writes) in tests/integration/test_dry_run.py

### Implementation for User Story 1

- [X] T045 [US1] Implement intake schema with all required fields from FR-003, capability-conditional validation, and E.164/IANA/slug normalization in orchestrator/intake_schema.py
- [X] T046 [US1] Implement organization identity normalization (lowercase slug, whitespace trim, case-insensitive dedup check) in orchestrator/intake_schema.py
- [X] T047 [US1] Implement organization lock (file-based, session identity, process identity, staleness check, takeover validation) in orchestrator/org_lock.py
- [X] T048 [US1] Implement deployment and partial-deployment lookup for existing organizations in orchestrator/deployment_lookup.py
- [X] T049 [US1] Implement capability-driven task graph planner (ordered steps, dependencies, validators, approvals, expected artifacts, intended changes) in orchestrator/planner.py
- [X] T050 [US1] Implement dry-run plan output formatter (JSON with ordered tasks, dependencies, validations, approval points, expected outputs, intended external changes) in orchestrator/planner.py
- [X] T051 [US1] Implement CLI session management (start, organization scope, lock acquisition, end) in cli/session.py
- [X] T052 [US1] Implement CLI interactive prompts (plan confirmation, existing deployment options: proceed/view/abort) in cli/prompts.py
- [X] T053 [US1] Implement CLI entry point with `onboard --dry-run` and `intake validate` commands in cli/main.py
- [X] T054 [US1] Implement `config check` CLI command (validate env presence, redacted display, staging/production identity check, block production-looking targets) in cli/main.py
- [X] T055 [US1] Create staging intake fixture in tests/fixtures/staging_client.json per quickstart.md template

**Checkpoint**: Operator can validate intake, preview full onboarding plan with zero side effects, see existing deployment state, and confirm or abort. User Story 1 is independently testable.

---

## Phase 4: User Story 2 — Generate and Validate a Deployment Package (Priority: P1)

**Goal**: System generates complete client-specific deployment artifacts from approved source templates and validates every artifact deterministically.

**Independent Test**: Use a hypothetical client fixture to generate the full package, then verify every artifact passes structural, referential, security, provenance, and domain-boundary checks without contacting live write endpoints.

### Tests for User Story 2

- [ ] T056 [P] [US2] Unit test for Vapi assistant config validator (required fields, tool references, server URL HTTPS, no secrets) in tests/unit/test_vapi_validator.py
- [ ] T057 [P] [US2] Unit test for Make blueprint validator (scenario structure, hook references, module allowlist) in tests/unit/test_make_validator.py
- [ ] T058 [P] [US2] Unit test for SQL migration validator (destructive pattern detection, policy dependencies, foreign-client identifiers) in tests/unit/test_sql_validator.py
- [ ] T059 [P] [US2] Unit test for Node.js diff validator (HMAC presence, no embedded secrets, unrelated change detection, file hash match) in tests/unit/test_nodejs_validator.py
- [ ] T060 [P] [US2] Unit test for package assembler (provenance enforcement, source mismatch rejection, completeness check) in tests/unit/test_assembler.py
- [ ] T061 [P] [US2] Integration test for full package generation from fixture (all artifacts, all validators pass, no write endpoints) in tests/integration/test_generation_package.py

### Source Templates and Ground Truth

- [ ] T062 [P] [US2] Create ground-truth Vapi assistant config template in ground-truth/configs/vapi_assistant_template.json
- [ ] T063 [P] [US2] Create ground-truth Vapi tool schemas (availability, booking, cancellation, rescheduling) in ground-truth/configs/vapi_tools/
- [ ] T064 [P] [US2] Create ground-truth Make scenario blueprints (availability, booking, cancellation, rescheduling) in ground-truth/configs/make_blueprints/
- [ ] T065 [P] [US2] Create ground-truth database schema template (organization table, RLS policies) in ground-truth/schemas/
- [ ] T066 [P] [US2] Create ground-truth CHANGELOG.md tracking template versions in ground-truth/CHANGELOG.md
- [ ] T067 [US2] Implement source template registry (load, version lookup, hash verification, active/superseded status) in orchestrator/template_registry.py

### Specialist Agents — Generation

- [ ] T068 [US2] Implement Vapi agent: generate assistant config from intake + template, attach tool references, set server URL, record provenance in agents/vapi_agent/agent.py
- [ ] T069 [P] [US2] Implement Vapi agent tools: template interpolation, field provenance marking, config assembly in agents/vapi_agent/tools.py
- [ ] T070 [US2] Implement Make agent: generate 4 scenario blueprints from templates + intake, parameterize webhook URLs, record provenance in agents/make_agent/agent.py
- [ ] T071 [P] [US2] Implement Make agent tools: blueprint parameterization, hook URL injection, scheduling config in agents/make_agent/tools.py
- [ ] T072 [US2] Implement Supabase agent: generate SQL migration (org record insert, RLS policies), validate against schema in agents/supabase_agent/agent.py
- [ ] T073 [P] [US2] Implement Supabase agent tools: SQL generation, policy template, isolation check in agents/supabase_agent/tools.py
- [ ] T074 [US2] Implement Node.js agent: read current server.js, generate unified diff for new client routes, validate HMAC in agents/nodejs_agent/agent.py
- [ ] T075 [P] [US2] Implement Node.js agent tools: diff generation, route extraction, HMAC verification in agents/nodejs_agent/tools.py

### Validators and Assembler

- [ ] T076 [US2] Implement Vapi artifact validator (schema conformance, tool ID references, server URL HTTPS, no placeholders, no foreign IDs, secret scan) in agents/vapi_agent/validator.py
- [ ] T077 [P] [US2] Implement Make artifact validator (blueprint structure, hook references, module allowlist, no placeholders, secret scan) in agents/make_agent/validator.py
- [ ] T078 [P] [US2] Implement SQL artifact validator (destructive pattern block, reference check, policy dependency, foreign-client detection) in agents/supabase_agent/validator.py
- [ ] T079 [P] [US2] Implement Node.js artifact validator (HMAC present, no secrets, hash match, no unrelated changes) in agents/nodejs_agent/validator.py
- [ ] T080 [US2] Implement cross-client reference detector (scan all artifacts for foreign organization identifiers) in orchestrator/assembler.py
- [ ] T081 [US2] Implement field provenance tracker (intake-copied vs inferred/defaulted, source labeling) in orchestrator/assembler.py
- [ ] T082 [US2] Implement package assembler (collect results, verify agent_source matches task target, verify validation status, reject untrusted provenance, assemble manifest with hashes) in orchestrator/assembler.py
- [ ] T083 [US2] Implement repeated-correction escalation (third correction on same field in one task → failure, not correction) in orchestrator/assembler.py
- [ ] T084 [US2] Implement `generate` and `validate package` CLI commands in cli/main.py

### Snapshot Tests

- [ ] T085 [P] [US2] Create human-reviewed snapshot for a fixture Vapi assistant config in tests/snapshots/vapi_assistant_staging.json
- [ ] T086 [P] [US2] Create human-reviewed snapshot for a fixture Make blueprint in tests/snapshots/make_booking_staging.json

**Checkpoint**: Full deployment package can be generated from intake, all artifacts pass deterministic validation, provenance is traceable, cross-client references are blocked, and no live write endpoint is contacted. User Story 2 is independently testable.

---

## Phase 5: User Story 3 — Deploy Through Per-Action Approval (Priority: P1)

**Goal**: Operator approves each proposed external change individually after seeing exactly what it will do, retaining authority over all live resources.

**Independent Test**: Run a staging deployment and verify each external side effect pauses for a distinct approval, rejected actions do not execute, approved actions produce a receipt, and no approval can authorize later unshown actions.

### Tests for User Story 3

- [ ] T087 [P] [US3] Contract test for Vapi adapter (create/get/update/delete assistant, create/list tools, assign phone) against tool-contracts.yaml in tests/contract/test_vapi_contract.py
- [ ] T088 [P] [US3] Contract test for Make adapter (create/get/delete scenario, get blueprint, start/stop, create/delete hook, ping) in tests/contract/test_make_contract.py
- [ ] T089 [P] [US3] Contract test for Render adapter (get/put env var, trigger/get deploy) in tests/contract/test_render_contract.py
- [ ] T090 [P] [US3] Contract test for Supabase client adapter (select/insert org record) in tests/contract/test_supabase_client_contract.py
- [ ] T091 [P] [US3] Unit test for approval flow (proposal hash binding, display hash, single-use, rejection routing) in tests/unit/test_approval.py
- [ ] T092 [US3] Integration test for sequential deployment with 5 actions requiring 5 approvals in tests/integration/test_deployment_approval.py

### Live Adapters

- [ ] T093 [US3] Implement Vapi live adapter (create_assistant, get_assistant, update_assistant, delete_assistant, create_tool, list_tools, get_tool, assign_phone_number) with contracts from tool-contracts.yaml in adapters/vapi.py
- [ ] T094 [US3] Implement Make live adapter (create_scenario, get_scenario, list_scenarios, delete_scenario, get_blueprint, activate_scenario, deactivate_scenario, create_hook, get_hook, list_hooks, delete_hook, verify_hook) in adapters/make.py
- [ ] T095 [US3] Implement Supabase client adapter (select_rows, insert_org_record) with allowlisted table enforcement in adapters/supabase_client.py
- [ ] T096 [US3] Implement Render hosting adapter (get_env_variable, set_env_variable, trigger_deploy, get_deploy_status) in adapters/hosting.py
- [ ] T097 [P] [US3] Implement Brave Search adapter (web_search with sanitized results) in adapters/brave_search.py

### Approval and Execution Flow

- [ ] T098 [US3] Implement ProposedAction builder (platform, operation, target, payload hash, state version, proposal hash computation, idempotency key, retry policy, reconciliation strategy, compensation) in orchestrator/approval.py
- [ ] T099 [US3] Implement approval display renderer (target, operation, change summary, inferred values, validation result, recovery implications, proposal hash) in cli/prompts.py
- [ ] T100 [US3] Implement approval decision recorder (approved, rejected_abort, rejected_revise, display hash, proposal hash match enforcement) in orchestrator/approval.py
- [ ] T101 [US3] Implement staleness check: read authoritative current state before write, compute state_version_before, compare at execution time, discard stale and regenerate in orchestrator/orchestrator.py
- [ ] T102 [US3] Implement sequential action executor (one action at a time, persist receipt before next, atomic pre-execution transaction per data-model.md) in orchestrator/orchestrator.py
- [ ] T103 [US3] Implement post-success transaction (finish attempt, insert receipt, upsert external resource, mark action succeeded, append audit event, update deployment state) in orchestrator/orchestrator.py
- [ ] T104 [US3] Implement revision flow (rejection → new task attempt → generation → validation → fresh approval) in orchestrator/orchestrator.py
- [ ] T105 [US3] Implement `onboard --execute --environment staging` CLI command with per-action interactive approval in cli/main.py

**Checkpoint**: Each external side effect requires a separate recorded approval bound to an immutable proposal hash, rejected actions do not execute, approved actions produce receipts, stale proposals are regenerated. User Story 3 is independently testable against staging.

---

## Phase 6: User Story 4 — Recover From Partial or Ambiguous Failure (Priority: P1)

**Goal**: System preserves partial deployment state, explains what happened, guides retry or compensation, and resumes recovery after restart.

**Independent Test**: Inject a failure after each possible side effect in a staging sequence and verify the system records completed work, prevents blind retries, offers accurate recovery choices, and resumes recovery after restart.

### Tests for User Story 4

- [ ] T106 [P] [US4] Failure injection test: timeout-after-success for each adapter (no duplicate resource created) in tests/failure_injection/test_timeout_after_success.py
- [ ] T107 [P] [US4] Failure injection test: failure at each action boundary (correct partial state recorded) in tests/failure_injection/test_action_boundary_failure.py
- [ ] T108 [P] [US4] Failure injection test: local persistence failure after remote success (reconciliation on restart) in tests/failure_injection/test_persistence_failure.py
- [ ] T109 [P] [US4] Failure injection test: compensation failure (deployment remains unresolved, next safe action identified) in tests/failure_injection/test_compensation_failure.py
- [ ] T110 [US4] Integration test for process stop and restart recovery detection in tests/integration/test_restart_recovery.py

### Recovery Implementation

- [ ] T111 [US4] Implement ambiguous-outcome handler (mark proposal reconciliation_required, create pending reconciliation action, transition deployment to recovery_required) in orchestrator/recovery.py
- [ ] T112 [US4] Implement remote-state reconciliation per adapter (Vapi: list/get by ID, Make: list by team/name, Supabase: select by org_id, Render: get deploy) in orchestrator/recovery.py
- [ ] T113 [US4] Implement retry flow (only failed/unresolved step, requires reconciliation first, requires fresh approval, bounded retry count) in orchestrator/recovery.py
- [ ] T114 [US4] Implement compensation flow (individual description, separate approval per compensating action, execution, receipt recording) in orchestrator/recovery.py
- [ ] T115 [US4] Implement failed-compensation handling (deployment remains unresolved, remaining resources listed, next safe action identified) in orchestrator/recovery.py
- [ ] T116 [US4] Implement restart detection (on session start for same org, check for unresolved partial/recovery_required deployments, present recovery before new work) in orchestrator/orchestrator.py
- [ ] T117 [US4] Implement failure classification (validation, authorization, conflict, transient, permanent, ambiguous_outcome, compensation_failure, local_persistence) in adapters/base.py
- [ ] T118 [US4] Implement bounded automatic retry (max 2, read-only or proven-idempotent only, bounded delay, no blind retry for ambiguous creates) in adapters/base.py
- [ ] T119 [US4] Implement recovery CLI display (partial state summary, completed resources, available options: retry/compensate/abort/defer) in cli/prompts.py

**Checkpoint**: Failures at any action boundary produce correct partial state, blind retries are blocked, reconciliation verifies remote state, compensation requires approval, restart detects unresolved state, and failed compensation is honestly reported. User Story 4 is independently testable via failure injection.

---

## Phase 7: User Story 5 — Diagnose Problems Using Verified Knowledge (Priority: P2)

**Goal**: Failures are explained using verified internal knowledge first, with clearly-labeled external research as fallback.

**Independent Test**: Ask known troubleshooting questions and verify answers cite matching verified knowledge; test an unknown issue and verify fallback research is clearly distinguished from verified truth.

### Tests for User Story 5

- [ ] T120 [P] [US5] Unit test for knowledge chunking (one-file-per-gotcha, section-level for docs, deterministic IDs, checksums) in tests/unit/test_knowledge_chunking.py
- [ ] T121 [P] [US5] Unit test for Chroma retrieval (threshold behavior, verified-only filter, provenance display) in tests/unit/test_knowledge_retrieval.py
- [ ] T122 [US5] Integration test for three diagnostic fixtures answered from verified knowledge in tests/integration/test_knowledge_search.py

### Knowledge Base and Retrieval

- [ ] T123 [P] [US5] Create verified gotcha entries (3 minimum) for known diagnostic fixtures in knowledge-base/gotchas/
- [ ] T124 [P] [US5] Create knowledge-base docs structure (platform-indexed Markdown files) in knowledge-base/docs/
- [ ] T125 [US5] Implement deterministic chunking (one chunk per gotcha file, deep-heading chunks for docs, metadata with platform/topic/symptom/resolution) in scripts/embed_knowledge.py
- [ ] T126 [US5] Implement Chroma collection management (create/rebuild, explicit distance metric, embedding function, configurable threshold 1.5 default) in agents/information_agent/rag.py
- [ ] T127 [US5] Implement verified knowledge retrieval (search, threshold filter, verification_status check, source citation) in agents/information_agent/rag.py
- [ ] T128 [US5] Implement information agent (verified-first lookup, threshold-configured fallback to Brave search, clear labeling of unverified results) in agents/information_agent/agent.py
- [ ] T129 [P] [US5] Implement information agent tools (search_knowledge, search_web_fallback, propose_new_knowledge) in agents/information_agent/tools.py
- [ ] T130 [US5] Implement knowledge approval flow (duplicate/contradiction check, human approval required before verified status, unresolved diagnoses blocked from storage) in agents/information_agent/agent.py
- [ ] T131 [US5] Implement `--verify` and `--rebuild` flags for embed_knowledge.py (stale checksum detection, full rebuild) in scripts/embed_knowledge.py

**Checkpoint**: Known issues are resolved from verified internal knowledge with provenance, unknown issues use clearly-labeled external fallback, no unresolved diagnosis is stored as verified, and duplicate/contradictory entries require human review. User Story 5 is independently testable.

---

## Phase 8: User Story 6 — Audit, Reconcile, and Export Deployment History (Priority: P2)

**Goal**: Durable record of every proposal, validation, approval, change, retry, and delivery — exportable and restorable.

**Independent Test**: Complete a staging deployment, retrieve its history, and verify every action is connected to a session, sanitized, tamper-evident, and exportable for restoration testing.

### Tests for User Story 6

- [ ] T132 [P] [US6] Unit test for audit event recording (required fields, redaction, hash chain, append-only) in tests/unit/test_audit.py
- [ ] T133 [P] [US6] Security test for secret propagation (no secret in artifacts, audit records, snapshots, exports, model context) in tests/security/test_secret_propagation.py
- [ ] T134 [P] [US6] Restoration test for export/import cycle (manifest hashes, row counts, FK validity, audit hash chains, recovery queries) in tests/restoration/test_operational_restore.py

### Audit and History

- [ ] T135 [US6] Implement audit event writer (event type catalog, actor, subject, status, sanitized detail, hash computation, chain linkage, append-only enforcement) in orchestrator/audit.py
- [ ] T136 [US6] Instrument all orchestrator operations with audit events (task start/end, validation, approval, execution, retry, compensation, state transitions) in orchestrator/orchestrator.py
- [ ] T137 [US6] Implement deployment history renderer (ordered timeline of tasks, actions, approvals, external requests, corrections, retries, compensations, state transitions) in cli/history.py
- [ ] T138 [US6] Implement `history --organization` CLI command with JSON output in cli/main.py

### Reconciliation

- [ ] T139 [US6] Implement read-only reconciliation (compare stored resource IDs and status against actual external state per adapter, report discrepancies without corrective writes) in scripts/reconcile_deployment.py
- [ ] T140 [US6] Implement `verify vapi`, `verify make`, `verify hosting`, `verify health` CLI subcommands in cli/main.py

### Export and Restore

- [ ] T141 [US6] Implement operational data export (all 14 tables to JSON, manifest with schema version, row counts, file hashes, final audit hash per deployment) in scripts/export_internal_tables.py
- [ ] T142 [US6] Implement operational data restore (dry-run default, manifest validation, empty-target requirement, preserve IDs and timestamps, FK validation, hash chain verification) in scripts/restore_internal_tables.py
- [ ] T143 [US6] Implement DeploymentRecord assembly (summary, capabilities, artifact manifest, resource manifest, verification summary, package hash) in orchestrator/assembler.py
- [ ] T144 [US6] Implement `security scan --path` CLI command (secret scanner across output directory) in cli/main.py

**Checkpoint**: Every deployment decision is traceable in order, audit records are tamper-evident through hash chains, secrets never appear in persisted data, exports reconstruct successfully in isolation. User Story 6 is independently testable.

---

## Phase 9: User Story 7 — Safely Modify an Existing Deployment (Priority: P3)

**Goal**: Updates to existing client deployments pass through the same read, validate, approve, and recover controls as onboarding.

**Independent Test**: Select an existing staging client, propose one configuration change, and verify current state is read, exact diff is shown, unchanged resources are preserved, the change requires approval, and rollback/retry remains available.

### Tests for User Story 7

- [ ] T145 [P] [US7] Unit test for update-intent intake (existing deployment lookup, change detection, no-op detection) in tests/unit/test_update_intake.py
- [ ] T146 [US7] Integration test for single-field update flow (read current, show diff, approve, write, verify) in tests/integration/test_update_flow.py

### Update Flow

- [ ] T147 [US7] Implement update-intent intake (select existing org, select modification type from DeploymentIntent enum, collect changed fields only) in orchestrator/intake_schema.py
- [ ] T148 [US7] Implement current-state reader (read all relevant external resources for the organization, compute state hashes) in orchestrator/orchestrator.py
- [ ] T149 [US7] Implement selective artifact regeneration (generate only affected artifacts and actions, preserve unchanged resources) in orchestrator/planner.py
- [ ] T150 [US7] Implement no-change detection (if requested state matches current state, report no change, perform no write) in orchestrator/orchestrator.py
- [ ] T151 [US7] Implement update execution reusing US3 approval flow and US4 recovery controls in orchestrator/orchestrator.py
- [ ] T152 [US7] Implement CLI `update --organization` command routing through same approve/recover flow in cli/main.py

**Checkpoint**: Existing deployments can be safely modified through the same controls, no-op changes are detected and reported, partial update failures enter the same recovery flow. User Story 7 is independently testable.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Full integration, first-real-deployment preparation, security hardening, and release gate validation

- [ ] T153 [P] Run complete type checking (mypy) across all source packages and fix issues
- [ ] T154 [P] Run ruff format and lint checks across all source and fix issues
- [ ] T155 Implement full orchestrator onboard flow connecting US1→US2→US3→US4 with all intermediate state transitions in orchestrator/orchestrator.py
- [ ] T156 [P] Security test: cross-client fixture injection (foreign org_id in artifact, foreign resource reference) in tests/security/test_cross_client.py
- [ ] T157 [P] Security test: tenant isolation (allowed-access succeeds, denied-cross-tenant fails, no hardcoded org_id in policies) in tests/security/test_tenant_isolation.py
- [ ] T158 Implement `cleanup --organization --dry-run/--execute` CLI command for staging resource removal in cli/main.py
- [ ] T159 Implement `smoke-test gemini` and `smoke-test chroma` CLI commands in cli/main.py
- [ ] T160 Create staging-readiness checklist in specs/001-agent-forge-onboarding/checklists/staging-readiness.md
- [ ] T161 Run full quickstart.md staging verification end to end and document evidence in outputs/verification/

**Checkpoint**: All release gates pass — type checks, lint, tests, security, tenant isolation, export/restore, reconciliation, audit completeness, backend tests, health verification, and quickstart staging validation.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational (Phase 2)
- **US2 (Phase 4)**: Depends on US1 (needs intake schema and planner)
- **US3 (Phase 5)**: Depends on US2 (needs generated artifacts to deploy)
- **US4 (Phase 6)**: Depends on US3 (needs live deployment state to recover from)
- **US5 (Phase 7)**: Depends on Foundational (Phase 2) only — can start in parallel with US1
- **US6 (Phase 8)**: Depends on Foundational (Phase 2) — audit instrumentation added progressively across US1-US4
- **US7 (Phase 9)**: Depends on US3 and US4 (reuses their approval and recovery flows)
- **Polish (Phase 10)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (P1)**: After Foundational → First independently testable increment (MVP preview)
- **US2 (P1)**: After US1 → Adds generation on top of planning
- **US3 (P1)**: After US2 → Adds live deployment on top of generation
- **US4 (P1)**: After US3 → Adds recovery on top of deployment
- **US5 (P2)**: After Foundational → Independent of US1-US4, can develop in parallel
- **US6 (P2)**: After Foundational → Independent, but richer with data from US3/US4
- **US7 (P3)**: After US4 → Reuses full onboard+deploy+recover flow for updates

### Within Each User Story

- Tests written first, verified to fail before implementation
- Shared models/schemas before domain-specific services
- Domain services before CLI integration
- Core implementation before edge cases
- Story complete and checkpoint validated before next priority

### Parallel Opportunities

- All [P] tasks within a phase can run in parallel
- US5 can develop in parallel with US1→US4 chain (after Foundational)
- US6 audit infrastructure can develop in parallel (after Foundational), with instrumentation added as US1-US4 complete
- Within US2: all four specialist agents (T067-T074) and their validators (T075-T078) can run in parallel
- Within US3: all four live adapters (T092-T096) can run in parallel
- Within US4: all failure injection tests (T105-T108) can run in parallel

---

## Parallel Example: User Story 2 (Generation)

```bash
# Launch all source templates in parallel:
Task: T061 "Create ground-truth Vapi assistant config template"
Task: T062 "Create ground-truth Vapi tool schemas"
Task: T063 "Create ground-truth Make scenario blueprints"
Task: T064 "Create ground-truth database schema template"

# Launch all specialist agents in parallel (after templates):
Task: T067 "Implement Vapi agent generation"
Task: T069 "Implement Make agent generation"
Task: T071 "Implement Supabase agent generation"
Task: T073 "Implement Node.js agent generation"

# Launch all validators in parallel (after agents):
Task: T075 "Implement Vapi artifact validator"
Task: T076 "Implement Make artifact validator"
Task: T077 "Implement SQL artifact validator"
Task: T078 "Implement Node.js artifact validator"
```

---

## Parallel Example: User Story 3 (Live Adapters)

```bash
# Launch all contract tests in parallel:
Task: T086 "Contract test for Vapi adapter"
Task: T087 "Contract test for Make adapter"
Task: T088 "Contract test for Render adapter"
Task: T089 "Contract test for Supabase client adapter"

# Launch all adapters in parallel:
Task: T092 "Implement Vapi live adapter"
Task: T093 "Implement Make live adapter"
Task: T094 "Implement Supabase client adapter"
Task: T095 "Implement Render hosting adapter"
Task: T096 "Implement Brave Search adapter"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1 (Preview)
4. **STOP and VALIDATE**: Run `python -m cli.main onboard --dry-run` with fixture
5. Operator can preview complete onboarding plans with zero side effects

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 (Preview) → Test independently → First safe demo (MVP!)
3. Add US2 (Generate) → Test independently → Full packages without deployment
4. Add US3 (Deploy) → Test independently → Staging deployments with approval
5. Add US4 (Recover) → Test independently → Production-safe deployment tool
6. Add US5 (Diagnose) → Test independently → Self-service troubleshooting
7. Add US6 (Audit) → Test independently → Complete operational traceability
8. Add US7 (Update) → Test independently → Full lifecycle management
9. Each story adds value without breaking previous stories

### First Real Deployment

After US1-US4 pass staging verification and all release gates (US6 audit, US5 diagnosis):
1. Run verified flow for one real client
2. Reconcile all created resources
3. Verify health and tenant isolation
4. Assemble records and export operational data
5. Confirm no recovery action pending, audit history complete, export passes verification

---

## Summary

| Metric | Value |
|---|---|
| **Total tasks** | 161 |
| **Phase 1 (Setup)** | 14 tasks |
| **Phase 2 (Foundational)** | 27 tasks |
| **Phase 3 (US1 — Preview)** | 14 tasks |
| **Phase 4 (US2 — Generate)** | 31 tasks |
| **Phase 5 (US3 — Deploy)** | 19 tasks |
| **Phase 6 (US4 — Recover)** | 14 tasks |
| **Phase 7 (US5 — Diagnose)** | 12 tasks |
| **Phase 8 (US6 — Audit)** | 13 tasks |
| **Phase 9 (US7 — Update)** | 8 tasks |
| **Phase 10 (Polish)** | 9 tasks |
| **Parallel opportunities** | 68 tasks marked [P] |
| **Suggested MVP scope** | Phase 1 + Phase 2 + Phase 3 (US1 only) = 55 tasks |
| **Independently testable stories** | All 7 user stories have independent test criteria |

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks in the same phase
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable at its checkpoint
- Tests are included per FR-047 through FR-053 (spec-mandated automated verification)
- Commit after each task or logical group
- Stop at any checkpoint to validate the story independently
- Backend writes (T074, T079) remain disabled until SERVER_TEST_COMMAND is real and passes
- All format validated: checkbox + ID + optional [P] + optional [Story] + description with file path
