# Feature Specification: Safe Client Deployment Automation

**Feature Branch**: `001-agent-forge-onboarding`  
**Created**: 2026-07-11  
**Status**: Draft  
**Constitution Version**: 1.0.0  
**Input**: User description: "Build Agent Forge, a single-operator system that safely generates, validates, deploys, records, and recovers client voice-agent configurations across the existing business platforms."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Preview a Complete Client Onboarding (Priority: P1)

As the operator, I want to enter a new client's complete business and deployment information and preview the full onboarding sequence before anything changes, so I can catch missing inputs, duplicate deployments, incorrect assumptions, and risky actions early.

**Why this priority**: Safe planning is the minimum valuable capability. It provides immediate value without touching live systems and establishes the data needed by every later workflow.

**Independent Test**: Provide a valid new-client intake, request a preview, and verify that the system returns a complete ordered plan containing dependencies, validations, approval points, expected outputs, and intended external changes while making zero external changes.

**Acceptance Scenarios**:

1. **Given** a valid intake for an organization that has not been deployed, **When** the operator requests a dry run, **Then** the system presents the complete ordered onboarding plan and performs no live write.
2. **Given** an intake with missing or invalid required fields, **When** the operator requests a plan, **Then** the system identifies each issue and does not produce an executable plan.
3. **Given** an organization with a completed deployment, **When** the operator begins onboarding with the same organization identifier, **Then** the system shows the existing deployment summary before collecting further intake and offers proceed, view status, or abort.
4. **Given** an organization with an unresolved partial deployment, **When** a session begins for that organization, **Then** the system presents recovery options before accepting new deployment work.

---

### User Story 2 - Generate and Validate a Deployment Package (Priority: P1)

As the operator, I want the system to generate a complete client-specific deployment package from approved source templates and validate every artifact against the intake and known resources, so I do not have to manually copy and reconcile configurations across platforms.

**Why this priority**: Generation plus deterministic validation delivers the project's core productivity benefit without requiring live deployment.

**Independent Test**: Use a hypothetical client fixture to generate the full package, then verify that every artifact passes structural, referential, security, provenance, and domain-boundary checks without contacting live write endpoints.

**Acceptance Scenarios**:

1. **Given** complete valid intake and approved source material, **When** package generation completes, **Then** the package contains every required client artifact in the required dependency order.
2. **Given** a generated field copied directly from intake, **When** the artifact is reviewed, **Then** the field is traceable to its source.
3. **Given** a generated field that was inferred or defaulted, **When** the artifact is reviewed, **Then** the field is visibly identified with its provenance and reason.
4. **Given** an artifact containing an unknown field, unresolved placeholder, incorrect client identifier, mismatched resource reference, or missing security rule, **When** validation runs, **Then** the artifact is blocked from approval.
5. **Given** an artifact returned by the wrong specialist domain or without trusted source identity, **When** package assembly runs, **Then** the artifact is rejected.

---

### User Story 3 - Deploy Through Per-Action Approval (Priority: P1)

As the operator, I want to approve each proposed external change individually after seeing exactly what it will do, so I retain authority over all live resources.

**Why this priority**: Live deployment is the main operational outcome, and per-action human control is a constitutional safety requirement.

**Independent Test**: Run a staging deployment and verify that each external side effect pauses for a distinct approval, rejected actions do not execute, approved actions produce a receipt, and no approval can authorize later unshown actions.

**Acceptance Scenarios**:

1. **Given** a validated live action, **When** approval is requested, **Then** the operator sees the target, proposed change, inferred values, validation result, and recovery implications before deciding.
2. **Given** a chain containing five live actions, **When** it executes, **Then** five distinct approvals are required and no approval is reused.
3. **Given** the operator rejects an action, **When** the system asks for the next decision, **Then** the operator can abort or describe a revision, and the rejected action does not execute.
4. **Given** the operator requests a revision, **When** a new proposal is generated, **Then** it passes the normal validation and approval flow again.
5. **Given** the live target changed after the original proposal was generated, **When** execution is about to begin, **Then** the stale proposal is discarded, regenerated against current state, revalidated, and shown for fresh approval.

---

### User Story 4 - Recover From Partial or Ambiguous Failure (Priority: P1)

As the operator, I want the system to preserve and explain partial deployment state and guide me through retry or compensation, so failed sessions do not leave forgotten or duplicate resources.

**Why this priority**: A deployment tool that handles only success is unsafe. Recovery is part of the core product, not later hardening.

**Independent Test**: Inject a failure after each possible side effect in a staging sequence and verify that the system records completed work, prevents blind retries, offers accurate recovery choices, and resumes recovery after restart.

**Acceptance Scenarios**:

1. **Given** one or more live actions succeeded and a later action failed, **When** failure is detected, **Then** the deployment is marked partial and completed resources are listed with their available compensating actions.
2. **Given** a partial deployment, **When** the operator chooses retry, **Then** only the failed or unresolved step is attempted after remote-state reconciliation and approval.
3. **Given** a partial deployment, **When** the operator chooses compensation, **Then** each compensating action is individually described, approved, executed, and recorded.
4. **Given** a request timed out with an unknown remote outcome, **When** recovery begins, **Then** the system checks remote state before deciding whether another create or update request is safe.
5. **Given** the application stops during a partial deployment, **When** it starts again for the same organization, **Then** recovery is presented before new work.
6. **Given** compensation fails, **When** the outcome is recorded, **Then** the deployment remains unresolved and the operator receives the exact remaining state and next safe action.

---

### User Story 5 - Diagnose Problems Using Verified Knowledge (Priority: P2)

As the operator, I want failures explained using verified project knowledge first and current external information only when necessary, so recurring issues are resolved consistently without turning guesses into ground truth.

**Why this priority**: Diagnosis reduces manual debugging time, but the system can still perform its primary generation and deployment flows without accumulated knowledge.

**Independent Test**: Ask known troubleshooting questions and verify that answers cite matching verified knowledge; test an unknown issue and verify that fallback research is clearly distinguished from verified internal knowledge.

**Acceptance Scenarios**:

1. **Given** a question matching verified internal knowledge, **When** diagnosis runs, **Then** the answer uses that knowledge and identifies its source and verification status.
2. **Given** no sufficiently relevant internal result, **When** diagnosis runs, **Then** current external research may be used and is labeled as unverified until confirmed.
3. **Given** a retry succeeds because of a diagnosed resolution, **When** the resolution is proposed for reuse, **Then** duplicate or contradictory knowledge is shown and human approval is required before storage.
4. **Given** an unresolved diagnosis, **When** the session ends, **Then** it is not stored as verified guidance.

---

### User Story 6 - Audit, Reconcile, and Export Deployment History (Priority: P2)

As the operator, I want a durable record of what was proposed, validated, approved, changed, retried, and delivered, so I can answer what happened for any client and reconcile records with actual external state.

**Why this priority**: Auditability is mandatory for trustworthy operation, though a minimal deployment can be demonstrated before advanced reporting is added.

**Independent Test**: Complete a staging deployment, retrieve its history, and verify that every task and external action is connected to a session, sanitized, tamper-evident through artifact references or hashes, and exportable for restoration testing.

**Acceptance Scenarios**:

1. **Given** a completed or failed session, **When** its history is opened, **Then** every delegated task, validation, approval, external request, correction, retry, state transition, and artifact is traceable in order.
2. **Given** audit data, **When** it is reviewed or exported, **Then** no secret or unnecessary sensitive client content appears.
3. **Given** a recorded deployment, **When** reconciliation is requested, **Then** stored resource identifiers and status are compared with actual external state and discrepancies are reported without automatic destructive correction.
4. **Given** an export is produced, **When** a restoration test is run in an isolated environment, **Then** deployment and recovery records can be reconstructed successfully.

---

### User Story 7 - Safely Modify an Existing Deployment (Priority: P3)

As the operator, I want to update an existing client deployment through the same read, validate, approve, and recover controls, so ongoing changes do not bypass the protections used during onboarding.

**Why this priority**: Updates are operationally important, but successful first-time onboarding is the initial release goal.

**Independent Test**: Select an existing staging client, propose one configuration change, and verify current state is read, the exact diff is shown, unchanged resources are preserved, the change requires approval, and rollback or retry remains available.

**Acceptance Scenarios**:

1. **Given** an existing complete deployment, **When** the operator requests a supported modification, **Then** current state is read and only the affected artifacts and actions are planned.
2. **Given** no effective difference between requested and current state, **When** validation completes, **Then** the system reports no change and performs no write.
3. **Given** an update fails after a live change, **When** recovery begins, **Then** the same partial-state and compensation rules used for onboarding apply.

### Edge Cases

- The organization identifier differs only by case or surrounding whitespace from an existing record.
- Two local sessions attempt work for the same organization at the same time.
- An external operation succeeds remotely but its response is lost or times out.
- An external service returns a rate limit, temporary outage, malformed response, or changed contract.
- A referenced resource was deleted or changed outside Agent Forge.
- A generated artifact contains a value belonging to another client.
- Intake changes after planning but before approval.
- Source templates or verified knowledge change during an active session.
- A validator corrects the same field repeatedly, suggesting a systematic generation defect.
- The operator leaves an approval prompt open and resumes after the live target has changed.
- A compensating action is unavailable, incomplete, or itself fails.
- A migration can restore schema shape but cannot restore deleted data.
- Audit or backup storage is unavailable during a live sequence.
- The application terminates immediately after a remote success but before local state is persisted.
- A secret appears in model output, an error response, or an artifact proposed for logging.

## Requirements *(mandatory)*

### Functional Requirements

#### Intake and Planning

- **FR-001**: The system MUST support a single authenticated local operator for the first release.
- **FR-002**: The system MUST collect and validate all information required by the selected deployment capabilities before generating an executable plan.
- **FR-003**: Required onboarding information MUST include a unique organization identifier, business name, client contact context, phone assignment, voice selection, timezone, business hours, offered services, scheduling resource identifiers, booking rules, cancellation and rescheduling rules, transfer destination, enabled capabilities, and required client-specific external identifiers.
- **FR-004**: The system MUST normalize identifiers and check for complete and partial deployments before accepting new onboarding work.
- **FR-005**: The system MUST provide an executable plan and a side-effect-free dry-run view containing ordered steps, dependencies, validators, approvals, expected artifacts, and intended external changes.
- **FR-006**: The operator MUST explicitly confirm the complete execution plan before generation or deployment proceeds beyond read-only preparation.
- **FR-007**: The system MUST prevent concurrent local sessions from modifying the same organization.

#### Generation and Validation

- **FR-008**: The system MUST generate only artifacts required for capabilities selected in the validated intake.
- **FR-009**: Generated artifacts MUST be based on versioned, human-approved source material appropriate to the artifact domain.
- **FR-010**: Every generated artifact MUST identify its originating task, responsible specialist domain, source-material version, and validation status.
- **FR-011**: Values copied from intake and values inferred or defaulted during generation MUST be distinguishable through mechanically produced provenance.
- **FR-012**: The system MUST validate artifact structure, required values, allowed fields, unresolved placeholders, client references, external resource references, authorization constraints, security controls, and specialist-domain boundaries before approval.
- **FR-013**: A deterministic mismatch with one authoritative correct value MAY be corrected automatically, but the original value, corrected value, source, and correction event MUST be recorded.
- **FR-014**: Repeated correction of the same field within one task MUST be escalated as a systematic defect rather than corrected indefinitely.
- **FR-015**: The package assembler MUST reject artifacts with missing, untrusted, or mismatched specialist provenance.

#### Live Action Control

- **FR-016**: Every external side effect MUST require a separate human approval after validation and immediately before execution.
- **FR-017**: An approval request MUST show the target, operation, material change, inferred values, validation result, expected outcome, and recovery implications.
- **FR-018**: Approval for one action MUST NOT authorize any later action.
- **FR-019**: Rejection MUST offer abort or revise; revision MUST return through normal generation, validation, and approval.
- **FR-020**: Every live write MUST be preceded in the same task by a read of authoritative current state and a final staleness comparison.
- **FR-021**: If current state changed, the system MUST discard the stale proposal, regenerate against current state, revalidate, and request fresh approval.
- **FR-022**: The system MUST block destructive data operations unless the task contains explicit operator authorization for the exact destructive intent.
- **FR-023**: The system MUST not claim a destructive action is reversible unless required data can actually be restored.

#### Reliability and Recovery

- **FR-024**: Every live action MUST define a success receipt, external request identifier where available, timeout behavior, retry classification, reconciliation method, idempotency strategy, and compensating action or an explicit statement that safe compensation is unavailable.
- **FR-025**: The system MUST persist confirmed external resource identifiers and deployment state immediately after each side effect.
- **FR-026**: Ambiguous outcomes MUST trigger remote-state reconciliation before retry.
- **FR-027**: The system MUST distinguish retryable, non-retryable, validation, authorization, conflict, and ambiguous-outcome failures.
- **FR-028**: Automatic retries MUST be limited to explicitly retryable read-only or idempotent operations and MUST use bounded delay.
- **FR-029**: After partial success, the system MUST pause and offer retry or compensation with an exact account of current external state.
- **FR-030**: Compensation MUST require the same per-action approval as any other live side effect.
- **FR-031**: Partial deployment state MUST survive application termination and MUST be resolved or deliberately deferred before new work for that organization.
- **FR-032**: Failed compensation MUST leave the deployment unresolved with the remaining resources and next safe action clearly identified.

#### Knowledge and Diagnosis

- **FR-033**: The system MUST consult verified internal knowledge before external research when diagnosing supported issues.
- **FR-034**: Diagnostic answers MUST identify their source and verification status.
- **FR-035**: The system MUST use external research only when internal evidence is absent or insufficient and MUST not present externally discovered guidance as verified internal truth.
- **FR-036**: New reusable knowledge MUST be checked for likely duplicates or contradictions and MUST require human approval before becoming verified.
- **FR-037**: Unresolved diagnoses MUST NOT be stored as verified knowledge.

#### Audit, Security, and Records

- **FR-038**: The system MUST maintain a durable deployment registry with organization identity, external resource references, current deployment status, verification time, and unresolved recovery actions.
- **FR-039**: The system MUST maintain an append-oriented audit history for tasks, artifacts, validations, corrections, approvals, external calls, retries, failures, compensations, and state transitions.
- **FR-040**: Audit events MUST include session and task identifiers, timestamp, actor, operation, target, status, sanitized detail, artifact reference or hash, relevant version information, and external request identifier where available.
- **FR-041**: Secrets MUST NOT be included in model context, generated artifacts, approval displays, audit records, snapshots, exports, or source control.
- **FR-042**: Internal operational records MUST remain isolated from client-facing business data.
- **FR-043**: Reusable access policies MUST derive organization identity from authenticated claims and MUST NOT hardcode client identifiers.
- **FR-044**: Tenant isolation MUST be verified with both allowed-access and denied-cross-tenant tests before a database change is considered complete.
- **FR-045**: The system MUST export its operational records in a restorable format and support a documented restoration verification.
- **FR-046**: The system MUST support reconciliation of recorded deployment resources against actual external state without making unapproved corrective writes.

#### Testing and Release Gates

- **FR-047**: Each milestone MUST have objective exit evidence linked to its requirements and tests.
- **FR-048**: Validation logic, planning, state transitions, provenance checks, assembly, and recovery behavior MUST be covered by automated tests.
- **FR-049**: External integration behavior MUST be covered by contract tests and staging smoke tests before production use.
- **FR-050**: Every multi-action live sequence MUST be tested with failure injection at each side-effect boundary, including timeout-after-success and compensation failure.
- **FR-051**: Database changes MUST be exercised against an isolated non-production schema before production approval.
- **FR-052**: Backend file writes MUST remain disabled until a real automated smoke or regression suite can run after the write.
- **FR-053**: A failing mandatory test, unresolved validation error, unresolved constitutional violation, or unreconciled partial deployment MUST block production release.

### Key Entities *(include if feature involves data)*

- **Organization Intake**: The operator-approved facts and capability selections required to plan and generate one client's deployment.
- **Capability**: A supported business behavior selected for a client, including its required inputs, artifacts, specialist domains, validations, and external actions.
- **Deployment**: The lifecycle record for one organization's onboarding or update, including pending, partial, complete, failed, and unresolved states.
- **External Resource Reference**: A sanitized identifier and metadata record for a resource managed on an external platform.
- **Task**: A uniquely identified unit of delegated work with one specialist domain, constraints, dependencies, verification requirement, and execution state.
- **Artifact**: A generated or documented output with trusted origin, provenance, version references, validation evidence, and approval requirement.
- **Validation Report**: Deterministic evidence of checks performed, corrections made, failures found, and release-blocking status.
- **Approval Decision**: The operator's decision for exactly one proposed live action, including what was shown, when it was decided, and whether revision or abort followed.
- **Audit Event**: A sanitized append-oriented record of a task, decision, action, correction, failure, or state transition.
- **Recovery Action**: A retry, reconciliation, or compensating operation associated with a partial or ambiguous deployment state.
- **Verified Knowledge Entry**: Human-approved troubleshooting guidance with source, platform, symptom, root cause, resolution, and verification metadata.
- **Source Template**: Versioned, human-approved reference material used to produce exact domain artifacts.
- **Deployment Package**: The assembled collection of validated artifacts, reports, records, and operator-facing summary for one deployment.

## Scope Boundaries

### In Scope

- Single-operator local use.
- New-client onboarding through a preview, generation, validation, approval, deployment, documentation, and recovery flow.
- Controlled updates to supported existing deployments after onboarding is stable.
- Integration with the existing voice-assistant, automation, client data, and backend-hosting platforms identified by the approved plan.
- Verified internal troubleshooting knowledge with controlled external research fallback.
- Staging verification, deployment records, reconciliation, audit history, and restorable exports.

### Out of Scope

- Multi-user collaboration, role-based workspace administration, or client self-service.
- Always-on hosted operation, remote triggering, mobile or web interface.
- Autonomous approval or autonomous destructive remediation.
- Concurrent specialist execution for one deployment.
- Replacing the existing client-facing dashboard or business systems.
- General-purpose agent creation unrelated to the supported onboarding and update capabilities.
- Distributed infrastructure introduced only for hypothetical future scale.
- Guaranteed restoration of data destroyed without a recoverable backup.

## Assumptions

- One technically competent operator owns all approvals during the first release.
- External vendor accounts, staging environments, and authorized credentials are available before live-integration testing.
- The operator can verify and approve initial source templates and expected fixture outputs.
- Client-specific phone, scheduling, transfer, tenant, and business-policy information is available during intake.
- External platforms expose sufficient read operations to reconcile writes and discover existing resources.
- The first release prioritizes correctness and traceability over throughput and always-on availability.
- Approval prompts may wait indefinitely, but every resumed action still performs a fresh staleness check.
- Retention follows the operator's documented business and legal obligations; secrets are never intentionally retained.

## Dependencies

- Current, reviewed contracts for every external platform operation used by the deployment flow.
- Approved source templates for each supported configuration and capability.
- A non-production environment for integration, failure-injection, migration, and recovery testing.
- A canonical registry of capabilities, specialist responsibilities, tool operations, and compensating actions.
- Secure credential provisioning and rotation procedures.
- The Agent Forge Constitution v1.0.0.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The operator can produce a complete dry-run plan for a valid new client in under 5 minutes, with zero external side effects.
- **SC-002**: 100% of required intake fields are validated before an executable plan is accepted.
- **SC-003**: 100% of generated artifacts used in a deployment have trusted origin, source version, provenance, and passing validation evidence.
- **SC-004**: 100% of external side effects require a distinct recorded human approval immediately before execution.
- **SC-005**: In failure-injection testing, every completed side effect is reflected in persisted deployment state before the next side effect begins.
- **SC-006**: In timeout-after-success tests, zero duplicate external resources are created by blind retry.
- **SC-007**: After restart, 100% of simulated partial deployments are detected and presented for recovery before new work for the affected organization.
- **SC-008**: Cross-client fixture tests detect and block 100% of deliberately injected foreign resource identifiers and unauthorized access attempts.
- **SC-009**: No seeded secret appears in generated artifacts, model-visible context, approval output, audit records, snapshots, or exports during security testing.
- **SC-010**: 100% of production-bound database changes pass allowed-access, denied-cross-tenant, and isolated-schema tests before approval.
- **SC-011**: 100% of production-bound backend changes pass an automated post-write test suite; writes remain disabled when no suite is configured.
- **SC-012**: The full audit history reconstructs every tested deployment action and decision in correct order with no unexplained gaps.
- **SC-013**: A clean operational-data export can be restored and reconciled successfully in an isolated restoration exercise.
- **SC-014**: All three known troubleshooting fixtures are answered from verified internal knowledge without unsupported guessing.
- **SC-015**: One real client can be onboarded end to end through Agent Forge with a complete deployment package, complete audit history, successful health verification, and no unresolved recovery action.

<!--
Remediation target: specs/001-agent-forge-onboarding/spec.md
Insert this section immediately before `## Success Criteria`.
After merging, remove this comment.
-->

## Constitution Check *(mandatory)*

**Gate**: This specification MUST satisfy Agent Forge Constitution v1.0.0 before planning or implementation. Any failed row blocks progression.

| Constitutional Principle | Specification Evidence | Status |
|---|---|---|
| I. Specification Is the Source of Truth | User stories, FR-001 through FR-053, SC-001 through SC-015, scope boundaries, assumptions, and dependencies define observable behavior and acceptance outcomes. Conflicting implementation documents are subordinate to this specification until formally reconciled. | PASS |
| II. Deterministic Controls Over Model Judgment | FR-010 through FR-015 require trusted artifact origin, mechanical provenance, deterministic validation, cross-reference checks, correction records, and domain-boundary enforcement. Model output is never treated as authority. | PASS |
| III. Human Authority Over Live State | FR-016 through FR-019 require a separate informed approval for every external side effect and route rejection through abort or normal revision. | PASS |
| IV. Read, Validate, Then Write | FR-020 through FR-023 require authoritative reads, final staleness checks, regeneration, validation, and explicit destructive authorization before writes. | PASS |
| V. Recoverable and Idempotent Operations | FR-024 through FR-032 define receipts, reconciliation, bounded retries, durable partial state, approved compensation, restart recovery, and unresolved compensation handling. | PASS |
| VI. Isolation, Least Privilege, and Secret Safety | FR-038 through FR-046 require isolated operational records, secret exclusion, authenticated tenant claims, positive and negative isolation tests, restoration, and read-only reconciliation. | PASS |
| VII. Evidence-Based Testing | FR-047 through FR-053 require objective milestone evidence, automated logic tests, contract and staging tests, failure injection, isolated migrations, real backend tests, and release blocking on failed evidence. | PASS |
| VIII. Complete Operational Traceability | FR-010, FR-011, and FR-038 through FR-046 require task, artifact, version, approval, external request, correction, retry, compensation, and state-transition traceability without secrets. | PASS |
| Local-first and sequential architecture | Scope boundaries limit v1 to one local operator, a CLI interface, sequential execution, supported onboarding and controlled updates, and no premature distributed infrastructure. | PASS |

### Gate Conditions

The specification is constitutionally valid only while all of the following remain true:

1. No implementation artifact weakens per-action approval, secret protection, tenant isolation, trusted provenance, or durable recovery.
2. Every new live action adds deterministic validation, reconciliation behavior, a receipt contract, and an approved compensation classification before implementation.
3. Every new requirement receives measurable acceptance criteria and task coverage before release.
4. Any temporary exception names its owner, scope, mitigation, expiry date, and removal task; exceptions may not bypass the non-waivable safeguards named by the constitution.
5. A change that conflicts with this gate requires an explicit constitution amendment or specification revision before implementation continues.

**Constitution Gate Result**: PASS for specification version 1.0.0.