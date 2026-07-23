
# Agent Forge Constitution

## Core Principles

### I. Specification Is the Source of Truth

Agent Forge MUST be built from versioned, mutually consistent specifications before implementation begins. The constitution defines non-negotiable governance; the feature specification defines required behavior and acceptance outcomes; the implementation plan defines architecture and technology; and tasks define executable work. If code, prompts, schemas, examples, or implementation notes conflict with an approved specification, the approved specification governs until it is formally amended.

Every externally visible behavior, live side effect, data contract, agent boundary, and failure path MUST be traceable to a requirement and an acceptance test. Placeholder assumptions, unresolved tool names, and contradictory contracts MUST be resolved before the affected phase can pass its entry gate.

**Rationale:** AI-assisted implementation magnifies ambiguity quickly. A single, versioned chain from intent to evidence prevents competing documents and generated code from becoming accidental sources of truth.

### II. Deterministic Controls Over Model Judgment

Language-model output MUST be treated as untrusted proposed data, never as authority. Rules with a single correct answer MUST be enforced in deterministic code, schemas, parsers, allowlists, hashes, or cross-reference checks. The model MUST NOT approve its own output, assert that its own validation passed, choose its own privilege level, or invent missing production identifiers.

Agent identity and artifact origin MUST be assigned by trusted application code. Validators MUST reject unknown fields, unresolved placeholders, malformed references, unauthorized destructive statements, and domain-inappropriate artifacts. Inferred or defaulted artifact fields MUST be recorded mechanically and highlighted for review.

**Rationale:** Prompts improve behavior but do not create enforceable safety boundaries. Critical invariants belong in code that can be tested and audited.

### III. Human Authority Over Live State

A human operator MUST explicitly approve every operation that creates, changes, activates, deploys, deactivates, deletes, or otherwise affects an external or live resource. Approval MUST be requested per individual side effect after the exact target, proposed change, inferred values, validation result, and rollback implications are visible. Approval MUST NOT be bundled across a chain of live operations.

Rejection MUST produce an explicit abort-or-revise choice. Revision MUST return through the normal generation and validation path. No agent may weaken, bypass, pre-answer, or reinterpret an approval gate. Read-only discovery, local generation, deterministic validation, and dry-run planning do not require live-write approval.

**Rationale:** Agent Forge is an operator-controlled deployment system, not an autonomous production administrator.

### IV. Read, Validate, Then Write

Every live write MUST be preceded in the same task by a read of the authoritative current state. The read MUST capture a stable version marker or content hash. Immediately before execution, the target MUST be read again and compared with the captured state. If it changed, the stale proposal MUST be discarded, regenerated against current state, revalidated, and presented for approval again.

Generated artifacts MUST pass deterministic structural, referential, authorization, and safety validation before they can reach an approval gate. Database changes MUST be checked for destructive patterns, object existence, tenant-isolation coverage, and policy dependencies. Backend changes MUST be shown as a diff and validated for required authentication controls.

**Rationale:** Approval of a correct proposal is meaningless if the target changed after the proposal was created.

### V. Recoverable and Idempotent Operations

Every live-write tool MUST define its idempotency strategy, remote reconciliation behavior, success receipt, timeout handling, retry policy, and compensating action before implementation. The system MUST record external resource identifiers immediately after confirmed creation. A timeout or ambiguous response MUST trigger remote-state reconciliation before retry, never blind repetition.

Multi-step live sequences MUST persist progress after each side effect. If a later step fails, the system MUST mark the deployment partial, identify existing resources, and offer the operator an informed choice between retry and approved compensation. Recovery MUST survive process termination and resume before new work for the affected organization. Destructive changes that cannot restore lost data MUST NOT be described as reversible merely because inverse schema SQL exists.

**Rationale:** Retries, crashes, and partial success are normal distributed-system conditions, not exceptional edge cases.

### VI. Isolation, Least Privilege, and Secret Safety

Internal operational data MUST remain isolated from client-facing data. Credentials MUST be scoped to the minimum resources and actions required. Broad service-role credentials MUST NOT be exposed to model context, generated artifacts, logs, snapshots, source control, or approval output. Secrets MUST be loaded only by deterministic tool code and MUST be redacted from all persisted events.

Tenant isolation MUST be enforced by authenticated identity claims and verified with positive and negative tests. Client identifiers MUST NOT be hardcoded into reusable policies. Local secret storage is permitted for the single-operator MVP only when files are excluded from version control, filesystem access is restricted, secret scanning is enabled, and a documented rotation procedure exists. Any move to shared or hosted operation requires a dedicated secrets manager and revised threat model.

**Rationale:** The system coordinates privileged actions across several vendors, so one leaked credential or cross-client reference can have disproportionate impact.

### VII. Evidence-Based Testing

No milestone is complete because generated output looks plausible. Each requirement MUST have independent acceptance evidence. Pure logic, schemas, validators, planners, state transitions, and assemblers MUST have automated unit tests. Vendor integrations MUST have mocked contract tests and staging smoke tests. Every live sequence MUST have failure-injection tests at each side-effect boundary, including timeout-after-success and rollback failure.

Human-approved snapshots MAY detect output drift, but they MUST NOT substitute for semantic validators, runtime tests, or integration contracts. Database migrations MUST be exercised against a disposable or staging schema before production use. Backend writes MUST NOT be enabled while `run_tests` is a no-op placeholder. A failing mandatory test or unresolved validator error blocks release.

**Rationale:** Snapshots show change, not correctness. Live automation needs executable evidence that both success and recovery paths work.

### VIII. Complete Operational Traceability

Every delegated task, model-assisted proposal, deterministic correction, validation result, approval decision, external request, resource identifier, state transition, retry, compensation, and final artifact MUST be traceable by session and task. Audit events MUST include timestamps, actor, operation type, target, status, artifact hash or reference, prompt/template/model version where applicable, validator version, external request ID, and sanitized error detail.

Logs MUST be append-oriented and must never contain secrets or unnecessary client data. The assembler MUST reject results with missing or mismatched trusted agent provenance. Deployment records MUST be reconcilable with actual vendor state, and backups MUST be verifiably restorable rather than merely exported.

**Rationale:** When automation changes multiple systems, debugging and accountability depend on a durable chain of evidence.

### IX. Natural Language Is the Interface

The system's primary interface is conversation, not configuration files. The user MUST NOT be required to write JSON, YAML, or structured input to initiate a deployment. Structured data is an internal representation derived from conversation, not a user-facing format. The JSON intake path MAY exist for automation and scripting but MUST NOT be the only path.

The conversational layer MUST extract structured requirements from natural dialogue using deterministic function-calling schemas, present a plain-language plan summary for confirmation, and hand off a validated IntakeData object to the execution pipeline. The operator MUST see a human-readable summary of what will be built — never raw JSON field names — before confirming deployment.

**Rationale:** Operators deploying client configurations should not need to learn an internal schema format. Natural language reduces onboarding friction, prevents field-name errors, and allows the system to ask targeted clarifying questions rather than rejecting malformed input.

## Architectural Constraints

Agent Forge v1 is a single-operator, local-first Python CLI. It MUST optimize for correctness, inspectability, and a safe path to the first real deployment rather than always-on availability or premature distribution. Specialists MUST execute sequentially unless a future amendment proves concurrency safe and necessary.

Specialist agents MUST have exclusive, documented domains. The orchestrator may identify intent, validate intake completeness, construct dependency-aware plans, delegate work, manage state, and assemble verified results; it MUST NOT generate specialist technical artifacts. Agent registration and capability routing MUST be configuration-driven and validated at startup.

The project MUST maintain one canonical definition for each of the following: repository layout, environment-variable names, intake schema, task/result contracts, internal database schema, tool registry, capability map, deployment-state machine, and vendor-operation mapping. Duplicate definitions in explanatory documents are informative only and MUST be generated from or checked against the canonical contract.

The first production scope is new-client onboarding and controlled updates for the documented Vapi, Make.com, Supabase, and Node.js integrations. Kubernetes, Dapr, Ray, hosted multi-user operation, and other distributed infrastructure are out of scope until measured requirements justify them through an Architecture Decision Record.

## Delivery Workflow and Quality Gates

Work MUST follow this order: constitution, specification, clarification, implementation plan, tasks, cross-artifact analysis, implementation, validation, and deployment. Each artifact MUST identify its version and the versions of upstream artifacts it implements.

A phase may begin only when its entry dependencies are resolved and the previous phase has objective exit evidence. At minimum, every phase gate MUST verify:

1. Requirements and acceptance criteria are complete and internally consistent.
2. Canonical contracts contain no unresolved placeholders or contradictory definitions.
3. Security, failure, retry, compensation, and observability requirements are represented.
4. Tests exist or are explicitly scheduled before the code they protect can perform live writes.
5. Generated and hand-written artifacts pass formatting, static analysis, and relevant automated tests.
6. Vendor assumptions are checked against current official APIs and pinned to a reviewed contract.
7. Any constitutional exception is documented and approved before implementation proceeds.

The permanent `--dry-run` mode MUST expose the complete task graph, dependencies, intended live operations, approval points, and validation steps without executing side effects. The first real deployment MUST use staging-proven artifacts, per-action approvals, live reconciliation, and a post-deployment backup and health check.

Complex architectural choices, security exceptions, vendor substitutions, and changes to canonical contracts MUST produce an Architecture Decision Record. Significant AI-assisted work sessions MUST produce a Prompt History Record when required by the project workflow, capturing intent and outcome without secrets or raw sensitive data.

## Governance

This constitution supersedes conflicting process guidance, implementation documents, generated prompts, and code comments. Specifications, plans, and tasks MUST include a Constitution Check and MUST not be approved while violating a non-negotiable principle.

Amendments require a written proposal that states the motivation, affected artifacts, migration impact, and validation plan. The amendment MUST update this file, prepend a Sync Impact Report, propagate changes to dependent templates and active specifications, and receive explicit owner approval before it takes effect.

Versioning follows semantic versioning:

- **MAJOR:** Removes or materially weakens a principle, changes governance incompatibly, or permits behavior previously forbidden.
- **MINOR:** Adds a principle or materially expands mandatory governance.
- **PATCH:** Clarifies wording without changing obligations.

Every pull request and release MUST verify constitutional compliance. Any temporary exception MUST name the violated rule, scope, owner, expiry date, risk mitigation, and removal task. Exceptions MUST NOT bypass secret protection, tenant isolation, auditability, or human approval of live side effects.

A governance review is required before the first real deployment and after any security incident, rollback failure, cross-tenant defect, or expansion from single-operator local use. The project owner is responsible for ratifying amendments and ensuring unresolved compliance failures block release.

**Version**: 1.1.0 | **Ratified**: 2026-07-11 | **Last Amended**: 2026-07-23