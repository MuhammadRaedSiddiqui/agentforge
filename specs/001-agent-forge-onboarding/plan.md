# Implementation Plan: Safe Client Deployment Automation

**Branch**: `001-agent-forge-onboarding` | **Date**: 2026-07-11 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/001-agent-forge-onboarding/spec.md`  
**Constitution**: `/memory/constitution.md`, version 1.0.0

## Summary

Build Agent Forge as a local-first Python command-line application for one operator. The application collects and validates client intake, previews a dependency-aware deployment graph, generates artifacts through five specialist agents, validates all deterministic constraints in code, requests separate human approval for every live side effect, and persists enough state to reconcile, retry, compensate, audit, and resume interrupted deployments.

The implementation uses the stack selected in the project documents: Python 3.11+, OpenAI Agents SDK with Google Gemini 2.5 Pro through Google's OpenAI-compatible endpoint, embedded Chroma for verified operational knowledge, a separate Supabase project for internal operational records, the Supabase Python client for data access, REST calls for Vapi, Make.com, Brave Search, and the hosting provider, and pytest for automated verification. Runtime remains local and sequential; the interface remains a CLI.

## Technical Context

**Language/Version**: Python 3.11 or later; Node.js only for validating and testing the existing `server.js` target, not for Agent Forge orchestration  
**Primary Dependencies**: `openai-agents>=0.0.4`, `openai>=1.60.0`, `chromadb>=0.5.0`, `supabase>=2.0.0`, `python-dotenv>=1.0.0`, `requests>=2.31.0`, `pytest>=8.0.0`  
**Model Provider**: Google Gemini 2.5 Pro through `https://generativelanguage.googleapis.com/v1beta/openai/`, wrapped once in `adapters/gemini.py`  
**Storage**: Separate internal Supabase project for deployment state and audit records; embedded persistent Chroma for derived search indexes; Git-tracked Markdown and JSON source material; local gitignored deployment packages and backups  
**Testing**: pytest unit, contract, integration, failure-injection, snapshot, security, restoration, and staging smoke tests; Node.js smoke/regression command required before backend writes are enabled  
**Target Platform**: Single operator's local Linux, macOS, or Windows machine with network access to configured external platforms  
**Project Type**: Single Python CLI project with domain-isolated specialist packages  
**Interaction Model**: Interactive terminal prompts plus non-mutating `--dry-run` planning  
**Execution Model**: Sequential specialist delegation; no parallel live actions  
**External Systems**: Vapi, Make.com, client-facing Supabase project, isolated internal Supabase project, hosting provider, Brave Search, and the deployed Node.js backend  
**Performance Goals**: Produce a valid dry-run plan within 5 minutes of completed intake; local validation feedback within 2 seconds for ordinary artifacts; persist each confirmed side effect before the next action begins  
**Constraints**: Local-only runtime, one operator, per-action approval, no secrets in model context or logs, no live write without current-state read and staleness check, no blind retry after ambiguous outcomes, no backend write while tests are placeholders  
**Scale/Scope**: First real client plus reusable fixtures; approximately five specialist domains, nine implementation phases, four automation capabilities plus native transfer, and one active modifying session per organization  
**Dependency Policy**: Minimum versions from the implementation document are bootstrap bounds only; exact versions and external API contract versions MUST be locked after Phase 0 smoke tests pass

## Canonical Technology Decisions

| Area | Decision | Boundary |
|---|---|---|
| Runtime | Python 3.11+ | Agent Forge application only |
| Agent orchestration | OpenAI Agents SDK | Delegation and tool invocation, not safety enforcement |
| Reasoning model | Gemini 2.5 Pro through OpenAI compatibility | All model output remains untrusted proposed data |
| Knowledge retrieval | Embedded Chroma | Derived index only; Git-tracked source files remain canonical |
| Internal records | Isolated Supabase project | Never mixed with client-facing business data |
| Client database access | Supabase Python client and reviewed server-side operations | No arbitrary model-generated database credentials or direct secret exposure |
| Vendor integrations | Deterministic REST adapters using `requests` | One adapter per vendor, pinned request and response contracts |
| User interface | Python CLI | No web UI in v1 |
| Hosting | Local machine | No daemon, remote trigger, or multi-user service in v1 |
| Secrets | Environment variables loaded through `python-dotenv` | Read only by deterministic adapters; always redacted |
| Tests | pytest plus existing Node.js project test command | Live writes stay disabled until their required tests exist |

## Canonical Environment Contract

The earlier documents use conflicting variable names. This plan establishes the following names as canonical for implementation. Compatibility aliases MUST NOT be added silently.

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Gemini model calls |
| `VAPI_API_KEY` | Vapi REST operations |
| `MAKE_API_TOKEN` | Make.com REST operations |
| `MAKE_TEAM_ID` | Make.com team scope |
| `SUPABASE_CLIENT_URL` | Client-facing Supabase project |
| `SUPABASE_CLIENT_SERVICE_ROLE_KEY` | Restricted client-project server operations for the MVP |
| `SUPABASE_INTERNAL_URL` | Isolated Agent Forge operational project |
| `SUPABASE_INTERNAL_SERVICE_ROLE_KEY` | Internal registry and audit operations |
| `HOSTING_API_TOKEN` | Hosting provider deployment operations |
| `HOSTING_SERVICE_ID` | Target backend service |
| `BRAVE_SEARCH_API_KEY` | External research fallback |
| `CHROMA_PERSIST_DIR` | Local Chroma index path |
| `SERVER_SOURCE_PATH` | Local reviewed path to the target `server.js` copy or checkout |
| `SERVER_TEST_COMMAND` | Real backend test command; absence disables writes |
| `MAKE_ZONE` | Make.com API region (eu1, eu2, us1, us2) |
| `HOSTING_HEALTH_URL` | Project-owned health endpoint URL (HTTPS required) |
| `AGENT_FORGE_ENV` | Runtime environment (staging or production) |

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Constitutional Rule | Plan Evidence | Status |
|---|---|---|
| Specification is source of truth | One canonical spec, plan, contracts, schemas, and environment contract | PASS |
| Deterministic controls over model judgment | Validators, provenance, trusted source identity, schema parsing, and allowlists live outside model prompts | PASS |
| Human authority over live state | Every external side effect is a separate proposed action and approval | PASS |
| Read, validate, then write | State hash or version captured on read and checked immediately before write | PASS |
| Recoverable and idempotent operations | Each live adapter declares reconciliation, retry class, receipt, and compensation metadata | PASS |
| Isolation and secret safety | Separate internal project; secrets stay in adapters; redaction required in all persistence paths | PASS |
| Evidence-based testing | Unit, contract, staging, failure-injection, cross-tenant, restoration, and backend tests are release gates | PASS |
| Complete traceability | Append-oriented event model with task, artifact, approval, external request, and transition references | PASS |
| Local-first and sequential | CLI-only process; fixed specialist execution order; one modifying session per organization | PASS |
| No premature distributed infrastructure | No Kubernetes, Dapr, Ray, web service, or concurrent orchestration | PASS |

**Pre-research gate result**: PASS. No constitutional exception is required.

## Project Structure

### Documentation (this feature)

```text
specs/001-agent-forge-onboarding/
â”œâ”€â”€ spec.md
â”œâ”€â”€ plan.md
â”œâ”€â”€ research.md
â”œâ”€â”€ data-model.md
â”œâ”€â”€ quickstart.md
â”œâ”€â”€ contracts/
â”‚   â””â”€â”€ tool-contracts.yaml
â”œâ”€â”€ checklists/
â”‚   â””â”€â”€ requirements.md
â””â”€â”€ tasks.md
```

### Source Code (repository root)

```text
agent-forge/
â”œâ”€â”€ agents/
â”‚   â”œâ”€â”€ information_agent/
â”‚   â”‚   â”œâ”€â”€ __init__.py
â”‚   â”‚   â”œâ”€â”€ agent.py
â”‚   â”‚   â”œâ”€â”€ tools.py
â”‚   â”‚   â””â”€â”€ rag.py
â”‚   â”œâ”€â”€ vapi_agent/
â”‚   â”‚   â”œâ”€â”€ __init__.py
â”‚   â”‚   â”œâ”€â”€ agent.py
â”‚   â”‚   â””â”€â”€ tools.py
â”‚   â”œâ”€â”€ make_agent/
â”‚   â”‚   â”œâ”€â”€ __init__.py
â”‚   â”‚   â”œâ”€â”€ agent.py
â”‚   â”‚   â””â”€â”€ tools.py
â”‚   â”œâ”€â”€ supabase_agent/
â”‚   â”‚   â”œâ”€â”€ __init__.py
â”‚   â”‚   â”œâ”€â”€ agent.py
â”‚   â”‚   â””â”€â”€ tools.py
â”‚   â””â”€â”€ nodejs_agent/
â”‚       â”œâ”€â”€ __init__.py
â”‚       â”œâ”€â”€ agent.py
â”‚       â””â”€â”€ tools.py
â”œâ”€â”€ orchestrator/
â”‚   â”œâ”€â”€ __init__.py
â”‚   â”œâ”€â”€ orchestrator.py
â”‚   â”œâ”€â”€ planner.py
â”‚   â”œâ”€â”€ assembler.py
â”‚   â”œâ”€â”€ intake_schema.py
â”‚   â”œâ”€â”€ recovery.py
â”‚   â””â”€â”€ state_machine.py
â”œâ”€â”€ adapters/
â”‚   â”œâ”€â”€ gemini.py
â”‚   â”œâ”€â”€ vapi.py
â”‚   â”œâ”€â”€ make.py
â”‚   â”œâ”€â”€ supabase_client.py
â”‚   â”œâ”€â”€ supabase_internal.py
â”‚   â”œâ”€â”€ hosting.py
â”‚   â””â”€â”€ brave_search.py
â”œâ”€â”€ shared/
â”‚   â”œâ”€â”€ task_object.py
â”‚   â”œâ”€â”€ result_object.py
â”‚   â”œâ”€â”€ action_contract.py
â”‚   â”œâ”€â”€ errors.py
â”‚   â”œâ”€â”€ hashing.py
â”‚   â”œâ”€â”€ redaction.py
â”‚   â””â”€â”€ ids.py
â”œâ”€â”€ cli/
â”‚   â”œâ”€â”€ __init__.py
â”‚   â”œâ”€â”€ main.py
â”‚   â”œâ”€â”€ prompts.py
â”‚   â””â”€â”€ session.py
â”œâ”€â”€ config/
â”‚   â”œâ”€â”€ agent_registry.json
â”‚   â”œâ”€â”€ capability_map.json
â”‚   â””â”€â”€ vendor_contract_versions.json
â”œâ”€â”€ ground-truth/
â”‚   â”œâ”€â”€ configs/
â”‚   â”œâ”€â”€ schemas/
â”‚   â””â”€â”€ CHANGELOG.md
â”œâ”€â”€ knowledge-base/
â”‚   â”œâ”€â”€ docs/
â”‚   â””â”€â”€ gotchas/
â”œâ”€â”€ scripts/
â”‚   â”œâ”€â”€ embed_knowledge.py
â”‚   â”œâ”€â”€ export_internal_tables.py
â”‚   â”œâ”€â”€ restore_internal_tables.py
â”‚   â””â”€â”€ reconcile_deployment.py
â”œâ”€â”€ tests/
â”‚   â”œâ”€â”€ unit/
â”‚   â”œâ”€â”€ contract/
â”‚   â”œâ”€â”€ integration/
â”‚   â”œâ”€â”€ failure_injection/
â”‚   â”œâ”€â”€ security/
â”‚   â”œâ”€â”€ restoration/
â”‚   â”œâ”€â”€ fixtures/
â”‚   â””â”€â”€ snapshots/
â”œâ”€â”€ backups/                  # gitignored
â”œâ”€â”€ chroma_data/              # gitignored
â”œâ”€â”€ outputs/                  # gitignored
â”œâ”€â”€ .env.example
â”œâ”€â”€ .gitignore
â”œâ”€â”€ pyproject.toml
â”œâ”€â”€ requirements.txt
â””â”€â”€ README.md
```

**Structure Decision**: Use one Python project with five explicit specialist packages, a non-agent orchestrator layer, deterministic vendor adapters, shared contracts, and tests organized by evidence type. `ground-truth/` stores exact approved templates; `knowledge-base/` stores retrievable guidance; Chroma remains a disposable derived index. This layout replaces both conflicting layouts in the PDFs.

## Core Design

### Execution Flow

1. Start session and acquire an organization-scoped local lock.
2. Normalize organization identity and check complete or partial deployment state.
3. Collect capability-driven intake and validate every field.
4. Produce and display the dry-run task graph.
5. Obtain operator confirmation for the plan.
6. Generate and validate client database artifacts.
7. Generate and validate Vapi artifacts.
8. Generate and validate Make.com artifacts.
9. Read backend state, generate and validate the proposed diff.
10. Execute approved actions sequentially, persisting a receipt after every side effect.
11. On ambiguous or partial failure, reconcile remote state and enter recovery before continuing.
12. Verify health and tenant isolation.
13. Assemble the deployment package and deployment record.
14. Export internal records and release the organization lock.

### Agent Boundary

The orchestrator creates typed tasks and may route, retry, recover, and assemble, but it never creates Vapi JSON, Make.com blueprints, SQL, backend code, or diagnosis content. Each specialist returns one typed `ResultObject` with trusted `agent_source` assigned by code. The assembler rejects a result whose source does not match its task target.

### Safety Boundary

Models may propose artifact content and diagnostic text. Models may not execute vendor calls directly. All external operations pass through deterministic adapters that validate typed inputs, redact secrets, apply timeout and retry policy, record request identifiers, reconcile ambiguous outcomes, and return typed receipts.

### State and Recovery Boundary

Deployment state is persisted before and after each live action. A successful remote write is not considered locally complete until its receipt and resource reference are stored. If persistence fails after remote success, the next session reconciles remote state using the operation's idempotency and lookup strategy.

## Implementation Phases

### Phase 0: Environment and Contracts

- Scaffold the canonical repository.
- Create `.env.example` from the canonical environment contract.
- Lock exact dependency versions after Gemini and Chroma smoke tests pass.
- Capture reviewed Vapi, Make.com, Supabase, hosting, and Brave request and response contracts.
- Establish redaction tests and secret scanning before any integration logging exists.

**Exit gate**: Gemini and Chroma smoke tests pass; vendor contracts are versioned; no unresolved environment or repository conflict remains.

### Phase 1: Internal Operational Store

- Create canonical tables from `data-model.md`.
- Implement append-oriented event writes, deployment locking, resource registry, and recovery queries.
- Implement export, restore, and restoration verification.

**Exit gate**: Tables pass constraints and transition tests; export and restore reconstruct a fixture deployment.

### Phase 2: Information Agent

- Implement deterministic chunking and embedded Chroma retrieval.
- Implement verified-knowledge lookup, threshold-configured fallback research, and human-approved gotcha proposals.
- Add the three known diagnostic fixtures.

**Exit gate**: All diagnostic fixtures use verified internal knowledge and provenance is visible.

### Phase 3: Vapi and Make.com Generation

- Populate and version approved ground-truth templates.
- Implement generation and deterministic validators.
- Implement cross-client reference detection and mechanically produced field provenance.
- Save only human-confirmed snapshots.

**Exit gate**: A second-industry fixture produces a complete package and passes all validators.

### Phase 4: Vapi and Make.com Live Adapters

- Implement typed REST adapters using the reviewed contract names rather than assuming SDK method names.
- Add request timeouts, bounded retry classification, remote reconciliation, idempotency, and compensation metadata.
- Enforce one approval per action.

**Exit gate**: Staging resources can be created, verified, and compensated through separately approved actions; timeout-after-success creates no duplicate.

### Phase 5: Supabase and Node.js Generation

- Implement schema, policy, and backend reads with canonical hashes.
- Generate SQL, isolation policy proposals, backend route changes, and unified diffs.
- Validate destructive patterns, references, policy dependencies, HMAC controls, and foreign-client identifiers.

**Exit gate**: Fixture migration and backend diff pass deterministic checks and isolated tests.

### Phase 6: Supabase and Node.js Live Adapters

- Execute reviewed database operations only through the approved server-side operation boundary.
- Re-read and compare state before database or backend writes.
- Require isolated-schema verification and real backend test command.
- Implement approved compensation without claiming lost data is restorable when it is not.

**Exit gate**: Staging organization and reversible backend change succeed; tenant isolation and backend tests pass; injected failures enter recoverable partial state.

### Phase 7: Orchestrator and Package Assembly

- Implement organization lock, intake, planner, dry run, sequential routing, typed failure policy, recovery, provenance enforcement, and package assembly.
- Implement regression, contract, security, failure-injection, and restoration suites.

**Exit gate**: Full hypothetical onboarding succeeds; deliberately broken tasks recover correctly; every spec success criterion has evidence.

### Phase 8: First Real Deployment

- Run the verified flow for one real client.
- Reconcile all created resources, verify health and tenant isolation, assemble records, and export operational data.

**Exit gate**: Deployment is complete, no recovery action is pending, audit history has no unexplained gap, and the export passes verification.

## Testing Strategy

| Test Layer | Purpose | Release Gate |
|---|---|---|
| Unit | Schemas, validators, hashing, redaction, planner, state transitions | Required on every change |
| Contract | Vendor request/response adapters and error mapping | Required before staging calls |
| Integration | Internal store, Chroma, model wrapper, staging vendor reads | Required per phase |
| Failure injection | Every live boundary, timeout-after-success, persistence failure, compensation failure | Required before first real deployment |
| Security | Secret leakage, cross-client identifiers, tenant allowed/denied access | Required before live database use |
| Snapshot | Human-reviewed generation drift | Advisory diff plus validator pass |
| Restoration | Export integrity and recoverability | Required before first real deployment |
| Backend | Real `SERVER_TEST_COMMAND` after file write | Mandatory; absent command disables write |

## Operational Policies

- Default HTTP connect timeout: 10 seconds; default read timeout: 30 seconds, overridden only in a reviewed vendor contract.
- Automatic retries: maximum two for read-only or proven-idempotent transient failures; no automatic retry for ambiguous creates until reconciliation completes.
- Approval prompts have no expiry, but every resumed action repeats the staleness check.
- Chroma distance threshold begins at 1.5 as documented, lives in configuration, and must be calibrated against real fixtures before production reliance.
- Backups run after every completed real onboarding and are followed by integrity verification.
- External API and model identifiers are pinned in `vendor_contract_versions.json`; upgrades require contract tests and an ADR when behavior changes.

## Post-Design Constitution Check

| Check | Result |
|---|---|
| Canonical contracts replace conflicting PDF definitions | PASS |
| Models are separated from live adapters and authority | PASS |
| Per-action approval is preserved | PASS |
| Staleness, idempotency, reconciliation, and durable recovery are designed | PASS |
| Secrets and tenant isolation have explicit test gates | PASS |
| Backend placeholder test gap is removed by disabling writes without a real command | PASS |
| Local-first sequential scope is preserved | PASS |
| No unexplained constitutional violation remains | PASS |

**Post-design gate result**: PASS.

## Complexity Tracking

No constitutional violation requires justification. The additional `adapters/`, recovery state machine, and evidence-specific test directories are necessary safety boundaries for a privileged multi-platform deployment tool, not speculative architecture.