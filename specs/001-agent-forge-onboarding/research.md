\# Research: Safe Client Deployment Automation

**Feature**: `001-agent-forge-onboarding`  
**Date**: 2026-07-11  
**Status**: Complete  
**Plan**: [plan.md](./plan.md)  
**Constitution**: `/memory/constitution.md`, version 1.0.0

## Purpose

Resolve implementation uncertainties before design and coding. This document records reviewed decisions, their rationale, rejected alternatives, and the validation required before a decision is relied on for live operations.

## Decision 1: Python 3.11+ as the Agent Forge Runtime

**Decision**: Implement Agent Forge as one Python 3.11+ command-line application.

**Rationale**:

- The selected orchestration, Chroma, Supabase, validation, and testing libraries all support Python.
- A single process keeps approval prompts, sequential delegation, task state, and local recovery understandable.
- Python matches the project documents and avoids splitting orchestration between Python and Node.js.
- Node.js remains relevant only as the language of the existing backend target and its test command.

**Alternatives considered**:

- **Node.js for the whole tool**: rejected because it conflicts with the approved stack and adds no MVP advantage.
- **Multiple services**: rejected because a local single-operator tool does not need network boundaries, deployment orchestration, or distributed tracing.
- **Kubernetes, Dapr, or Ray**: rejected until measured scale or availability requirements justify them.

**Validation**: Run supported Python version checks in CI and on each intended operator platform.

## Decision 2: OpenAI Agents SDK With Explicit Gemini Compatibility Wrapper

**Decision**: Use the OpenAI Agents SDK with an explicit `OpenAIChatCompletionsModel` backed by Google's OpenAI-compatible endpoint. Construct this once in `adapters/gemini.py`; pin the exact SDK, OpenAI client, model identifier, and endpoint contract after smoke tests.

**Rationale**:

- The Agents SDK supports non-OpenAI model setups and explicit model selection.
- Google documents OpenAI-compatible Gemini access.
- A central wrapper prevents agents from loading API keys or choosing providers independently.
- The project benefits from typed tools and agent boundaries, while deterministic code still controls validation, approvals, and writes.

**Alternatives considered**:

- **Native Gemini SDK**: technically viable and may become preferable if compatibility defects recur, but it diverges from the approved plan.
- **Direct model HTTP calls**: rejected because it would rebuild orchestration behavior already provided by the SDK.
- **Framework handoffs as the workflow engine**: rejected for live sequencing; the deterministic planner and executor own control flow.

**Risks and mitigations**:

- Compatibility behavior for tools and handoffs has changed across releases. Contract smoke tests MUST cover structured output, function tools, multi-turn tool results, error propagation, and cancellation before dependency versions are locked.
- The model name `gemini-2.5-pro` MUST be verified against the operator's active Google account at implementation time. Startup MUST fail clearly if unavailable.

**Sources**:

- [OpenAI Agents SDK model documentation](https://openai.github.io/openai-agents-python/models/)
- [Google Gemini OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai)

## Decision 3: Deterministic Sequential Orchestration

**Decision**: Build the task graph and execute specialists sequentially in application code. Use this order for full onboarding: Supabase generation, Vapi generation, Make generation, Node.js read/diff, then separately approved live actions in dependency order.

**Rationale**:

- External identifiers produced by one step are inputs to later steps.
- Sequential execution produces a simpler audit trail and clearer partial-failure boundary.
- Model-directed handoffs are too loose to enforce production safety invariants.

**Alternatives considered**:

- **Concurrent specialists**: rejected for v1 because saved time is smaller than added tracing, stale-data, and recovery complexity.
- **A graph framework**: rejected for MVP scope. The typed planner and state machine provide the required deterministic graph behavior.

**Validation**: Planner tests MUST assert task ordering, dependencies, validations, and approval points for every capability combination.

## Decision 4: Chroma as a Disposable Local Retrieval Index

**Decision**: Use Chroma `PersistentClient` at `CHROMA_PERSIST_DIR`. Git-tracked Markdown files are canonical; Chroma is derived and rebuildable.

**Rationale**:

- `PersistentClient` stores an embedded index on the operator's machine without a separate server.
- The initial verified knowledge corpus is small.
- Rebuilding from source is safer than treating index files as durable knowledge.

**Alternatives considered**:

- **Hosted vector database**: rejected due to cost, secrets, network dependency, and unnecessary operational scope.
- **Weaviate**: deferred until hybrid keyword and semantic retrieval becomes a measured need.
- **Plain text search only**: insufficient for symptom and explanation similarity, but may later supplement semantic retrieval.

**Distance decision**:

- The PDF's `1.5` fallback threshold is retained only as a configuration default for the originally selected distance behavior.
- Collection distance space, embedding function, model version, and normalization MUST be explicit, because distance values are not portable between configurations.
- Before production reliance, calibrate the threshold against labeled positive and negative fixture queries. Store the chosen configuration and calibration date.

**Sources**:

- [Chroma PersistentClient documentation](https://cookbook.chromadb.dev/core/clients/)
- [Chroma collection configuration](https://docs.trychroma.com/docs/collections/configure)

## Decision 5: Logical, Versioned Knowledge Chunks

**Decision**: Chunk gotchas one file per entry and project documents at the deepest numbered heading. Include deterministic IDs and source checksums.

**Rationale**:

- Troubleshooting entries are already coherent semantic units.
- Deep section chunking avoids returning an entire chapter for a narrow recovery question.
- Checksums allow stale-index detection without relying on Chroma to notice source changes.

**Alternatives considered**:

- **Fixed character windows**: rejected because they split procedures and mix unrelated rules.
- **Automatic embedding on every startup**: rejected because it adds latency and may mutate state unexpectedly.

**Validation**: Unit tests cover nested headings, preamble folding, duplicate IDs, metadata, changed checksums, and complete rebuilds.

## Decision 6: Separate Internal Supabase Project

**Decision**: Store Agent Forge operational records in a separate Supabase project. Keep client business data in the existing client-facing project.

**Rationale**:

- Project-level separation limits accidental mixing of operational and client-facing data.
- PostgreSQL constraints support deployment-state integrity and traceability.
- Supabase provides straightforward local/staging workflows and Python data access.

**Alternatives considered**:

- **Same project with separate schema**: rejected because a wrong credential or query retains a larger blast radius.
- **Local SQLite only**: attractive for a local tool, but rejected to remain aligned with the approved implementation stack and shared recovery record requirements.
- **Chroma as operational storage**: rejected because vector storage is not a transactional system of record.

**Internal RLS decision**: RLS may be disabled for service-role-only internal access in v1, but network exposure, credential scope, and access logs MUST be reviewed. This does not relax RLS requirements on client-facing tenant data.

## Decision 7: Supabase CLI Migrations, Not Arbitrary SQL Through the Python Data Client

**Decision**: Use version-controlled migration files and the Supabase CLI or a narrowly scoped reviewed server-side operation for schema changes. Use the Python client for normal table access, not as an assumed generic DDL executor.

**Rationale**:

- Supabase officially documents CLI-managed local development and versioned migrations.
- Migrations can be tested against a local or isolated staging schema before production.
- The Python data client is appropriate for row operations but does not itself establish a safe general migration mechanism.

**Alternatives considered**:

- **Execute arbitrary generated SQL directly with a service key**: rejected because it creates excessive authority and bypasses reproducible migration workflows.
- **Management API as the default migration executor**: deferred until the exact reviewed operation and account capability are confirmed.
- **Generated inverse SQL as complete rollback**: rejected. It may reverse schema shape but cannot recreate destroyed data.

**Implementation consequence**:

1. Generate a versioned forward migration and a recovery classification.
2. Validate with a parser and explicit safety rules.
3. Apply to local or staging Supabase first.
4. Run positive and negative tenant-isolation tests.
5. Present the production migration and evidence for approval.
6. Apply through the reviewed migration boundary.
7. Verify live schema and policies.

**Sources**:

- [Supabase database migrations](https://supabase.com/docs/guides/deployment/database-migrations)
- [Supabase local development](https://supabase.com/docs/guides/local-development/overview)
- [Supabase environment management](https://supabase.com/docs/guides/deployment/managing-environments)

## Decision 8: Vapi Resources Are Separate and Must Be Reconciled Separately

**Decision**: Model Vapi assistant, tools, and phone-number assignment as distinct resources and operations. The internal action names are project-level wrapper names, not claims about SDK methods.

**Rationale**:

- Vapi exposes a create-assistant REST operation.
- Tools include built-in and custom categories and may exist independently of an assistant.
- Official onboarding guidance treats creating an assistant and attaching a phone number as separate steps.
- Separate resource records enable precise retry and compensation.

**Alternatives considered**:

- **Embed every tool and phone assignment in one assistant-create payload**: rejected because it obscures actual resource lifecycles and rollback boundaries.
- **Depend on an SDK naming convention**: rejected. Use reviewed REST contracts and stable internal adapter methods.

**Required adapter operations**:

- Read, create, update, and delete assistant.
- Read, create, update, and delete custom tool where supported by the reviewed API.
- Read phone number and assign or update assistant association.
- Verify final assistant, tool references, and phone association.

**Sources**:

- [Vapi create assistant](https://docs.vapi.ai/api-reference/assistants/create)
- [Vapi assistants quickstart](https://docs.vapi.ai/assistants/quickstart)
- [Vapi tools](https://docs.vapi.ai/tools)

## Decision 9: Make.com Uses Region-Aware REST Contracts

**Decision**: Implement Make.com integration through a region-aware REST adapter. Record the base region, team ID, scenario ID, blueprint version, hook ID, webhook URL, activation state, and external request evidence.

**Rationale**:

- Make documents REST resources for scenarios, blueprints, and hooks.
- API servers vary by region.
- API access and endpoints can depend on subscription plan and token scopes.
- Scenario import, hook creation, and activation are separate recovery boundaries.

**Alternatives considered**:

- **Browser automation**: rejected as fragile and hard to test.
- **Assume `import_scenario` is a vendor SDK method**: rejected. It remains an internal wrapper over the reviewed blueprint/scenario endpoints.
- **One Make operation for the whole chain**: rejected because it hides partial external state.

**Precondition**: Phase 0 MUST verify that the operator's Make plan and token scopes allow all required scenario, blueprint, and hook operations.

**Sources**:

- [Make API overview](https://developers.make.com/api-documentation)
- [Make scenarios API](https://developers.make.com/api-documentation/api-reference/scenarios)
- [Make blueprints API](https://developers.make.com/api-documentation/api-reference/scenarios/blueprints)
- [Make hooks API](https://developers.make.com/api-documentation/api-reference/hooks)

## Decision 10: Deterministic REST Adapters With Typed Receipts

**Decision**: Use `requests` behind one deterministic adapter per external platform. Agents never call external APIs directly.

**Rationale**:

- Typed adapter inputs and outputs establish a testable safety boundary.
- A common base can enforce timeouts, redaction, retry classification, request IDs, and receipts.
- Vendor-specific behavior remains isolated.

**Alternatives considered**:

- **Agent-owned HTTP tools**: rejected because models could choose targets or payloads outside validated plans.
- **One generic HTTP adapter**: rejected because it cannot enforce domain-specific allowlists and reconciliation.

**Policy**:

- Default connect timeout: 10 seconds.
- Default read timeout: 30 seconds.
- Maximum two automatic retries for read-only or proven-idempotent transient failures.
- No blind retry for ambiguous creates or updates.
- All payloads validated before request and sanitized before logging.
- Every success returns a typed receipt with target, operation, remote identifier, request evidence, and observed state.

## Decision 11: Per-Action Approval Bound to an Immutable Proposal

**Decision**: Bind each approval to the hash of one immutable proposed action and its displayed evidence.

**Rationale**:

- Prevents one confirmation from authorizing later or mutated work.
- Enables audit proof of exactly what was approved.
- Supports stale-state regeneration, which naturally creates a new hash and requires a new approval.

**Alternatives considered**:

- **Approve the whole deployment upfront**: rejected because later actions may differ after earlier writes.
- **Approve by operation name only**: rejected because target and payload matter.

**Validation**: Tests mutate target, payload, dependencies, and state version after approval and verify execution is blocked.

## Decision 12: Durable Recovery State and Remote Reconciliation

**Decision**: Persist a deployment action before execution, then persist its receipt and resulting resource immediately after confirmed success. On ambiguous outcomes, reconcile remotely before retry.

**Rationale**:

- Handles lost responses, process crashes, and local persistence failures.
- Prevents duplicate external resources.
- Makes restart recovery deterministic.

**Alternatives considered**:

- **Automatic rollback**: rejected because compensation is another live side effect and may destroy useful state.
- **Retry the entire chain**: rejected because earlier actions may already have succeeded.
- **Store recovery only in memory**: rejected because process termination would create silent orphans.

## Decision 13: Explicit Organization Locking

**Decision**: Allow one modifying local session per normalized organization identifier. Use an atomic lock file containing session identity, process identity, and creation time; validate staleness before takeover.

**Rationale**:

- Prevents two local runs from generating conflicting partial states.
- Fits the local single-operator scope without distributed locking infrastructure.

**Alternatives considered**:

- **Database advisory lock**: possible, but adds remote dependence before basic intake and planning.
- **No lock because there is one operator**: rejected because accidental duplicate terminals remain possible.

## Decision 14: Real Backend Tests Are a Hard Write Gate

**Decision**: `write_server_file` is disabled unless `SERVER_TEST_COMMAND` is configured and passes against the staged candidate. After an approved write, run the command again and verify service health.

**Rationale**:

- A placeholder test function gives false confidence.
- Backend changes can break every client's tool calls.
- The constitution explicitly forbids enabling writes behind a no-op test.

**Alternatives considered**:

- **Proceed with warning**: rejected for live writes.
- **Manual diff review only**: useful but insufficient for syntax and runtime regressions.

## Decision 15: Canonical Environment and Repository Contracts

**Decision**: The names and layout in `plan.md` supersede conflicting variants in the two PDFs. Code, tests, scripts, and documentation MUST use those canonical definitions.

**Rationale**:

- The PDFs disagree on package names, environment names, and internal table fields.
- Supporting aliases silently would preserve ambiguity.

**Alternatives considered**:

- **Support every previous name**: rejected because it complicates deployment and increases secret-configuration errors.
- **Choose one PDF unchanged**: rejected because both omit required safety and implementation details.

## Decision 16: Testing and Release Evidence

**Decision**: Use pytest for Python tests, vendor contract fixtures for adapters, staging smoke tests for live operations, failure injection at every side-effect boundary, positive and negative tenant-isolation tests, snapshot diffs for reviewed generation drift, and restoration tests for exports.

**Rationale**:

- No single test type proves this system safe.
- Snapshots detect change but do not prove correctness.
- Failure and recovery paths are first-class product behavior.

**Alternatives considered**:

- **Manual verification only**: rejected because it is not repeatable.
- **Snapshots as regression tests**: rejected as the sole method because model output can differ while remaining correct or stay similar while becoming unsafe.

## Resolved Questions

| Question | Resolution |
|---|---|
| Can the Agents SDK call Gemini? | Yes, through an explicit compatible-provider setup, subject to pinned smoke and tool-call tests. |
| Is Chroma durable truth? | No. Git-tracked source is truth; Chroma is a disposable local index. |
| Is distance `1.5` universally meaningful? | No. It is an initial configurable value that must be calibrated for the chosen metric and embedding model. |
| Can the Supabase Python data client be assumed to execute arbitrary DDL safely? | No. Use versioned migrations through the CLI or a narrowly reviewed server-side boundary. |
| Is attaching a Vapi phone number part of assistant creation? | Treat it as a separate reviewed resource operation. |
| Are `create_assistant` and `import_scenario` vendor SDK method names? | Not necessarily. They are internal typed adapter names mapped to reviewed REST contracts. |
| Can failed writes be retried automatically? | Only if read-only or proven idempotent. Ambiguous outcomes require reconciliation first. |
| Is inverse SQL a full rollback? | No. It cannot restore destroyed data without backup. |
| Can backend writes ship with a placeholder test? | No. Writes remain disabled until a real test command exists. |
| Is distributed infrastructure needed? | No, not for the local single-operator first release. |

## Research Exit Gate

- [x] Runtime and orchestration approach selected.
- [x] Model-provider compatibility risks identified and testable.
- [x] Chroma durability, metric, and threshold rules resolved.
- [x] Supabase migration boundary corrected.
- [x] Vapi resource boundaries clarified.
- [x] Make API access, region, and scope prerequisites identified.
- [x] Retry, idempotency, reconciliation, and receipt policy defined.
- [x] Backend test placeholder rejected as a live-write path.
- [x] Canonical contracts selected over conflicting PDF definitions.
- [x] No remaining `NEEDS CLARIFICATION` marker blocks Phase 1 design.