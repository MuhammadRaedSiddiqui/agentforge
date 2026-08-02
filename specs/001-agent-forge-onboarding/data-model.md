# Data Model: Safe Client Deployment Automation

**Feature**: `001-agent-forge-onboarding`  
**Date**: 2026-07-11  
**Status**: Draft for implementation  
**Spec**: [spec.md](./spec.md)  
**Plan**: [plan.md](./plan.md)  
**Research**: [research.md](./research.md)

## Design Goals

The operational model MUST:

1. separate Agent Forge records from client-facing business data;
2. preserve one normalized organization identity across every platform;
3. represent deployment progress and partial failure durably;
4. record each proposed and executed side effect independently;
5. bind approvals to immutable proposed actions;
6. distinguish generated artifacts from live external resources;
7. support remote reconciliation before retry;
8. reconstruct every deployment decision without storing secrets;
9. support export, restoration, and schema evolution;
10. reject invalid lifecycle transitions through constraints and application rules.

## Conventions

- Primary keys are UUID unless the entity has a natural text key.
- Timestamps are `TIMESTAMPTZ` in UTC.
- JSON fields use `JSONB` only for bounded, versioned payloads that do not need relational joins.
- Secrets, raw authorization headers, complete sensitive vendor responses, and unnecessary client data are never persisted.
- External identifiers are strings because vendor formats vary.
- Every mutable row includes `created_at` and `updated_at`; append-only rows include only `created_at`.
- Enumerations are enforced with PostgreSQL enum types or check constraints.
- Artifact bodies live in gitignored local output files for v1; the database stores hashes, paths, summaries, and versions.
- `organization_id` refers to Agent Forge's normalized organization key, not a vendor-specific identifier.

## Entity Relationship Overview

```text
Organization 1 â”€â”€â”€ * OrganizationIntake
Organization 1 â”€â”€â”€ * Deployment
Deployment   1 â”€â”€â”€ * TaskExecution
Deployment   1 â”€â”€â”€ * ProposedAction
Deployment   1 â”€â”€â”€ * ExternalResource
Deployment   1 â”€â”€â”€ * Artifact
Deployment   1 â”€â”€â”€ * RecoveryAction
Deployment   1 â”€â”€â”€ * AuditEvent

TaskExecution 1 â”€â”€â”€ * Artifact
TaskExecution 1 â”€â”€â”€ * ValidationReport
TaskExecution 1 â”€â”€â”€ * ProposedAction

ProposedAction 1 â”€â”€â”€ 0..1 ApprovalDecision
ProposedAction 1 â”€â”€â”€ * ExternalRequestAttempt
ProposedAction 1 â”€â”€â”€ 0..1 ExternalReceipt
ProposedAction 1 â”€â”€â”€ 0..1 RecoveryAction

SourceTemplate 1 â”€â”€â”€ * Artifact
KnowledgeEntry 0..* â”€â”€â”€ retrieval only, never deployment authority
```

## Enumerations

### DeploymentIntent

- `new_onboarding`
- `update_assistant`
- `update_scenario`
- `update_schema`
- `update_backend`
- `status_only`
- `recovery_only`

### DeploymentStatus

- `planning`
- `awaiting_plan_approval`
- `generating`
- `awaiting_action_approval`
- `executing`
- `verifying`
- `partial`
- `recovery_required`
- `compensating`
- `complete`
- `failed`
- `aborted`

### TaskStatus

- `pending`
- `running`
- `success`
- `validation_failed`
- `error`
- `blocked`
- `aborted`

### ActionStatus

- `proposed`
- `validated`
- `awaiting_approval`
- `approved`
- `rejected`
- `executing`
- `succeeded`
- `failed`
- `ambiguous`
- `reconciliation_required`
- `compensation_pending`
- `compensated`
- `compensation_failed`
- `cancelled`

### ApprovalDecisionType

- `approved`
- `rejected_abort`
- `rejected_revise`

### ArtifactType

- `vapi_assistant_config`
- `vapi_tool_schema`
- `make_scenario_blueprint`
- `database_migration`
- `database_recovery_plan`
- `rls_policy`
- `organization_record`
- `server_candidate`
- `server_diff`
- `validation_report`
- `deployment_summary`
- `dry_run_plan`
- `diagnostic_report`

### ResourcePlatform

- `vapi`
- `make`
- `supabase_client`
- `hosting`

### ResourceType

- `vapi_assistant`
- `vapi_tool`
- `vapi_phone_number`
- `make_scenario`
- `make_hook`
- `supabase_organization_row`
- `supabase_migration`
- `supabase_policy`
- `hosting_service`
- `hosting_deployment`
- `backend_file_revision`

### FailureClass

- `validation`
- `authorization`
- `conflict`
- `transient`
- `permanent`
- `ambiguous_outcome`
- `compensation_failure`
- `local_persistence_failure`

### VerificationStatus

- `unverified`
- `verified`
- `stale`
- `failed`

## Entity: Organization

Represents one client identity inside Agent Forge.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `organization_id` | text | yes | Primary key; normalized lowercase slug; `[a-z0-9_]+` |
| `display_name` | text | yes | Non-empty; operator-facing business name |
| `status` | text | yes | `active`, `inactive`, or `blocked` |
| `created_at` | timestamptz | yes | Server default |
| `updated_at` | timestamptz | yes | Updated on mutation |

**Invariants**:

- Normalized identity is unique and case-insensitive.
- An organization with unresolved recovery MUST NOT start another modifying deployment.
- Display name changes do not change the primary identity.

## Entity: OrganizationIntake

Versioned operator-approved business and deployment inputs.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `intake_id` | uuid | yes | Primary key |
| `organization_id` | text | yes | FK to Organization |
| `version` | integer | yes | Starts at 1; unique per organization |
| `business_name` | text | yes | Non-empty |
| `phone_number` | text | yes | E.164 format |
| `voice_id` | text | yes | Validated against reviewed Vapi choices |
| `timezone` | text | yes | Valid IANA timezone |
| `business_hours` | jsonb | yes | Day-to-ranges mapping; validated structure |
| `services_offered` | jsonb | yes | Non-empty array of normalized service objects |
| `booking_calendar_id` | text | conditional | Required for scheduling capabilities |
| `cancellation_window_hours` | integer | conditional | Non-negative |
| `rescheduling_policy` | jsonb | conditional | Required when rescheduling is enabled |
| `transfer_destination` | text | conditional | Valid destination when transfer is enabled |
| `enabled_capabilities` | jsonb | yes | Non-empty array from capability registry |
| `external_identifiers` | jsonb | yes | Sanitized references only, no credentials |
| `intake_hash` | text | yes | SHA-256 of canonical sanitized intake |
| `approved_by` | text | yes | Local operator identity |
| `approved_at` | timestamptz | yes | Approval time |
| `created_at` | timestamptz | yes | Server default |

**Invariants**:

- Intake is immutable after approval. Changes create a new version.
- Capability-specific required fields MUST be present before planning.
- Secrets MUST NOT appear in `external_identifiers`.
- A deployment references one exact intake version and hash.

## Entity: Deployment

One onboarding, update, status, or recovery lifecycle.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `deployment_id` | uuid | yes | Primary key |
| `organization_id` | text | yes | FK to Organization |
| `intake_id` | uuid | conditional | Required for generating or modifying intent |
| `intent` | DeploymentIntent | yes | Immutable |
| `status` | DeploymentStatus | yes | Controlled state transitions only |
| `plan_hash` | text | conditional | Required after planning |
| `plan_version` | text | conditional | Required after planning |
| `constitution_version` | text | yes | Exact governing version |
| `spec_version` | text | yes | Exact feature spec version or commit |
| `started_by` | text | yes | Operator identity |
| `lock_owner` | text | conditional | Active local session identifier |
| `started_at` | timestamptz | yes | Server default |
| `completed_at` | timestamptz | no | Set only for terminal success/abort/failure |
| `last_verified_at` | timestamptz | no | Latest complete health verification |
| `failure_class` | FailureClass | no | Present for failed or recovery state |
| `failure_summary` | text | no | Sanitized concise description |
| `created_at` | timestamptz | yes | Server default |
| `updated_at` | timestamptz | yes | Updated on transition |

**Unique constraints**:

- At most one deployment in a modifying nonterminal state per organization.

**State transitions**:

```text
planning
  -> awaiting_plan_approval
  -> aborted

awaiting_plan_approval
  -> generating
  -> aborted

generating
  -> awaiting_action_approval
  -> failed
  -> aborted

awaiting_action_approval
  -> executing
  -> generating          # revision requested
  -> aborted

executing
  -> awaiting_action_approval
  -> verifying
  -> partial
  -> recovery_required
  -> failed

partial
  -> recovery_required

recovery_required
  -> executing           # targeted retry
  -> compensating
  -> aborted             # only when no unresolved live state remains

compensating
  -> failed              # compensation completed, original deployment failed
  -> recovery_required   # compensation failed or state remains

verifying
  -> complete
  -> recovery_required
  -> failed
```

Illegal transitions MUST be rejected and recorded as an application error, not silently corrected.

## Entity: Session

One local CLI process context.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `session_id` | uuid | yes | Primary key |
| `deployment_id` | uuid | no | Set when a deployment exists |
| `operator_id` | text | yes | Local operator identity |
| `host_fingerprint` | text | yes | Non-secret machine identifier hash |
| `process_id` | integer | yes | Local process ID |
| `started_at` | timestamptz | yes | Server default |
| `ended_at` | timestamptz | no | Set on graceful end |
| `end_reason` | text | no | `complete`, `aborted`, `crash_detected`, or `unknown` |

**Invariants**:

- A session does not grant authority; approvals remain separate.
- Process identity is diagnostic and MUST NOT be used as authentication.

## Entity: TaskExecution

One deterministic delegation to one specialist domain.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `task_id` | text | yes | Primary key; generated by application |
| `deployment_id` | uuid | yes | FK to Deployment |
| `session_id` | uuid | yes | FK to Session |
| `agent_target` | text | yes | Must exist in agent registry |
| `action_type` | text | yes | Registry-allowed action type |
| `context_hash` | text | yes | Hash of sanitized immutable context |
| `constraints` | jsonb | yes | Array of explicit rules |
| `dependency_task_ids` | jsonb | yes | Array of prior task IDs |
| `verification_required` | boolean | yes | Defaults true for generated artifacts |
| `status` | TaskStatus | yes | Controlled transition |
| `attempt_number` | integer | yes | Starts at 1 |
| `started_at` | timestamptz | no | Set on running |
| `completed_at` | timestamptz | no | Set on terminal state |
| `error_class` | FailureClass | no | Sanitized category |
| `error_detail` | text | no | Sanitized detail |
| `created_at` | timestamptz | yes | Server default |

**Invariants**:

- `agent_target` cannot change after creation.
- Dependencies must belong to the same deployment and be satisfied before running.
- A re-delegation creates a new attempt record or incremented attempt with a linked audit event; history is never overwritten.

## Entity: Artifact

Generated content or report associated with a task.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `artifact_id` | uuid | yes | Primary key |
| `deployment_id` | uuid | yes | FK to Deployment |
| `task_id` | text | yes | FK to TaskExecution |
| `artifact_type` | ArtifactType | yes | Domain-specific type |
| `agent_source` | text | yes | Assigned by trusted code |
| `source_template_id` | uuid | no | FK to SourceTemplate |
| `content_hash` | text | yes | SHA-256 of exact content |
| `storage_path` | text | yes | Relative path under gitignored output package |
| `summary` | text | yes | Sanitized human-readable summary |
| `field_provenance` | jsonb | no | Map of inferred/defaulted fields to reason and source |
| `model_id` | text | no | Exact model used if AI-assisted |
| `prompt_version` | text | no | Exact prompt version |
| `validator_version` | text | yes | Exact validator version |
| `validation_status` | VerificationStatus | yes | Must be verified before action proposal |
| `created_at` | timestamptz | yes | Server default |

**Invariants**:

- `agent_source` must match the originating task target.
- Content cannot change after hashing; revisions create a new artifact.
- Secret scanner must pass before metadata is persisted or content is displayed.
- Unverified artifacts cannot produce executable live actions.

## Entity: ValidationReport

Deterministic evidence for one artifact or proposed action.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `validation_report_id` | uuid | yes | Primary key |
| `task_id` | text | yes | FK to TaskExecution |
| `artifact_id` | uuid | no | FK to Artifact |
| `proposed_action_id` | uuid | no | FK to ProposedAction |
| `validator_name` | text | yes | Stable validator identifier |
| `validator_version` | text | yes | Exact version |
| `passed` | boolean | yes | Overall result |
| `checks` | jsonb | yes | Bounded array of check results |
| `corrections` | jsonb | yes | Deterministic corrections with old/new hashes, never secrets |
| `created_at` | timestamptz | yes | Append-only |

**Invariants**:

- At least one of `artifact_id` or `proposed_action_id` is required.
- Failed mandatory validation blocks approval.
- A third repeated correction for the same field in one task is represented as failure, not another correction.

## Entity: ProposedAction

One immutable candidate external side effect.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `proposed_action_id` | uuid | yes | Primary key |
| `deployment_id` | uuid | yes | FK to Deployment |
| `task_id` | text | yes | FK to TaskExecution |
| `sequence_number` | integer | yes | Unique within deployment |
| `platform` | ResourcePlatform | yes | Target platform |
| `operation` | text | yes | Allowlisted adapter operation |
| `target_reference` | jsonb | yes | Sanitized target identity |
| `payload_hash` | text | yes | Hash of validated request payload |
| `payload_storage_path` | text | yes | Local encrypted or protected proposal file |
| `state_version_before` | text | conditional | Hash/version from authoritative read |
| `proposal_hash` | text | yes | Hash binding operation, target, payload, dependencies, and state version |
| `idempotency_key` | text | no | Used when vendor supports or project can safely derive one |
| `retry_policy` | jsonb | yes | Bounded reviewed policy |
| `reconciliation_strategy` | text | yes | Named adapter strategy |
| `compensation_operation` | text | no | Named operation if safe compensation exists |
| `status` | ActionStatus | yes | Controlled lifecycle |
| `created_at` | timestamptz | yes | Server default |
| `updated_at` | timestamptz | yes | Updated on transition |

**Invariants**:

- Proposal fields are immutable. Regeneration creates a new proposal and cancels the stale one.
- Approval is valid only for the exact `proposal_hash`.
- A write proposal requires passing validation and a current-state version.
- Secret values are not stored in target or payload metadata.

## Entity: ApprovalDecision

One operator decision for one immutable proposal.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `approval_id` | uuid | yes | Primary key |
| `proposed_action_id` | uuid | yes | Unique FK to ProposedAction |
| `proposal_hash` | text | yes | Must match proposal at decision time |
| `decision` | ApprovalDecisionType | yes | Approved, abort, or revise |
| `operator_id` | text | yes | Decision actor |
| `display_hash` | text | yes | Hash of the exact rendered approval content |
| `revision_instruction` | text | conditional | Sanitized; required for revise |
| `decided_at` | timestamptz | yes | Server default |

**Invariants**:

- One proposal has at most one terminal decision.
- An approved proposal cannot be edited or reused for another action.
- Revision creates a new task attempt and proposal after validation.

## Entity: ExternalRequestAttempt

One actual vendor request attempt.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `attempt_id` | uuid | yes | Primary key |
| `proposed_action_id` | uuid | yes | FK to ProposedAction |
| `attempt_number` | integer | yes | Starts at 1; unique per proposal |
| `request_hash` | text | yes | Hash of sanitized canonical request |
| `vendor_request_id` | text | no | Vendor-provided identifier |
| `started_at` | timestamptz | yes | Request start |
| `finished_at` | timestamptz | no | Response or timeout time |
| `http_status` | integer | no | If available |
| `outcome` | text | yes | `success`, `failure`, `timeout`, `connection_error`, `ambiguous` |
| `failure_class` | FailureClass | no | Required for non-success |
| `response_summary` | text | no | Sanitized bounded summary |
| `created_at` | timestamptz | yes | Append-only |

**Invariants**:

- Attempts are append-only.
- A create action with ambiguous outcome cannot receive a new attempt until reconciliation is recorded.
- Raw headers and raw sensitive bodies are never stored.

## Entity: ExternalReceipt

Confirmed evidence of one successful live side effect.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `receipt_id` | uuid | yes | Primary key |
| `proposed_action_id` | uuid | yes | Unique FK to ProposedAction |
| `attempt_id` | uuid | yes | FK to ExternalRequestAttempt |
| `platform` | ResourcePlatform | yes | Platform |
| `operation` | text | yes | Executed operation |
| `remote_resource_id` | text | no | Required for resource creation |
| `remote_version` | text | no | Vendor version/hash if available |
| `observed_state_hash` | text | no | Hash of sanitized verified state |
| `vendor_request_id` | text | no | Request correlation |
| `confirmed_at` | timestamptz | yes | Confirmation time |
| `receipt_hash` | text | yes | Tamper-evident hash |
| `created_at` | timestamptz | yes | Append-only |

**Invariants**:

- Receipt creation and external-resource upsert occur in one local transaction.
- A receipt is not generated from model text.
- A successful receipt transitions its proposal to `succeeded`.

## Entity: ExternalResource

Current registry of known live resources.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `external_resource_id` | uuid | yes | Primary key |
| `organization_id` | text | yes | FK to Organization |
| `created_by_deployment_id` | uuid | yes | FK to Deployment |
| `platform` | ResourcePlatform | yes | Platform |
| `resource_type` | ResourceType | yes | Type |
| `capability` | text | no | Capability registry key |
| `remote_resource_id` | text | yes | Vendor identifier |
| `parent_external_resource_id` | uuid | no | FK to ExternalResource |
| `remote_url` | text | no | Sanitized, non-secret URL |
| `lifecycle_status` | text | yes | `active`, `inactive`, `deleted`, `unknown` |
| `last_observed_hash` | text | no | Sanitized remote-state hash |
| `last_verified_at` | timestamptz | no | Last reconciliation |
| `created_at` | timestamptz | yes | Server default |
| `updated_at` | timestamptz | yes | Updated on reconciliation |

**Unique constraint**: `(platform, resource_type, remote_resource_id)`.

**Invariants**:

- A resource cannot be silently reassigned to another organization.
- Deletion marks lifecycle status; the record remains for audit.
- `unknown` state blocks dependent writes until reconciliation.

## Entity: RecoveryAction

Durable retry, reconciliation, or compensation work.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `recovery_action_id` | uuid | yes | Primary key |
| `deployment_id` | uuid | yes | FK to Deployment |
| `proposed_action_id` | uuid | no | Related failed action |
| `external_resource_id` | uuid | no | Related live resource |
| `kind` | text | yes | `reconcile`, `retry`, `compensate`, `manual_inspection` |
| `operation` | text | yes | Named adapter operation or inspection |
| `sequence_number` | integer | yes | Recovery order |
| `status` | text | yes | `pending`, `approved`, `running`, `succeeded`, `failed`, `deferred` |
| `requires_approval` | boolean | yes | True for every live side effect |
| `failure_summary` | text | no | Sanitized |
| `created_at` | timestamptz | yes | Server default |
| `resolved_at` | timestamptz | no | Resolution time |

**Invariants**:

- A deployment remains recovery-required while any recovery action is pending, failed, or deferred with live state unresolved.
- Compensation is not automatically approved by approval of the original action.
- Recovery execution creates its own proposal, approval, attempts, and receipt when it has side effects.

## Entity: AuditEvent

Append-only chronological evidence.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `audit_event_id` | uuid | yes | Primary key |
| `deployment_id` | uuid | no | FK to Deployment |
| `session_id` | uuid | yes | FK to Session |
| `task_id` | text | no | Related task |
| `event_type` | text | yes | Stable event catalog value |
| `actor_type` | text | yes | `operator`, `orchestrator`, `specialist`, `validator`, `adapter`, `system` |
| `actor_id` | text | yes | Sanitized identity |
| `subject_type` | text | yes | Entity type |
| `subject_id` | text | yes | Entity identifier |
| `status` | text | yes | Event result |
| `summary` | text | yes | Sanitized, bounded text |
| `detail` | jsonb | yes | Sanitized, schema-versioned metadata |
| `event_hash` | text | yes | Hash of canonical event |
| `previous_event_hash` | text | no | Prior event hash for deployment chain |
| `created_at` | timestamptz | yes | Append-only server timestamp |

**Invariants**:

- Updates and deletes are forbidden to the application role.
- Detail is redacted before insertion.
- Hash chaining detects missing or modified exported events; it is not a substitute for database access control.

## Entity: SourceTemplate

Human-approved exact generation source.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `source_template_id` | uuid | yes | Primary key |
| `template_key` | text | yes | Stable logical key |
| `platform` | text | yes | Domain |
| `capability` | text | no | Capability key |
| `version` | text | yes | Semantic or reviewed version |
| `file_path` | text | yes | Git-tracked repository path |
| `content_hash` | text | yes | Exact file hash |
| `approved_by` | text | yes | Human approver |
| `approved_at` | timestamptz | yes | Approval time |
| `status` | text | yes | `active`, `superseded`, `revoked` |
| `created_at` | timestamptz | yes | Server default |

**Unique constraint**: `(template_key, version)`.

**Invariants**:

- Active templates must have a matching changelog entry.
- Existing artifacts keep their original template version even after supersession.
- Agent code cannot approve or modify templates.

## Entity: KnowledgeEntry

Verified or unverified troubleshooting source indexed by Chroma.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `knowledge_entry_id` | text | yes | Deterministic ID from source path and content hash |
| `source_path` | text | yes | Git-tracked Markdown path |
| `platform` | text | yes | Vapi, Make, Supabase, Node.js, Agents SDK, or general |
| `topic` | text | yes | Normalized topic |
| `symptom` | text | yes | Observed problem |
| `root_cause` | text | yes | Explanation |
| `resolution` | text | yes | Reviewed steps |
| `verification_status` | VerificationStatus | yes | Verified only after human approval |
| `content_hash` | text | yes | Source checksum |
| `approved_by` | text | no | Required when verified |
| `approved_at` | timestamptz | no | Required when verified |

**Storage note**: The canonical record is the Git-tracked Markdown file. Chroma stores the document, deterministic ID, and searchable metadata as a derived index.

## Entity: DeploymentRecord

Operator-facing summary produced after a deployment reaches a terminal state.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `deployment_record_id` | uuid | yes | Primary key |
| `deployment_id` | uuid | yes | Unique FK to Deployment |
| `organization_id` | text | yes | FK to Organization |
| `summary` | text | yes | Sanitized human-readable outcome |
| `capabilities` | jsonb | yes | Capability keys |
| `artifact_manifest` | jsonb | yes | Artifact IDs, hashes, and relative paths |
| `resource_manifest` | jsonb | yes | Resource IDs and final statuses |
| `verification_summary` | jsonb | yes | Health and isolation evidence |
| `package_hash` | text | yes | Hash of package manifest |
| `package_path` | text | yes | Gitignored local output path |
| `created_at` | timestamptz | yes | Server default |

**Invariants**:

- Complete deployments require no unresolved recovery action.
- Failed or aborted deployments may still receive a record, clearly labeled with final state.
- The package contains no secrets.

## Recommended PostgreSQL Constraints and Indexes

### Constraints

- Check normalized organization IDs against `^[a-z0-9_]+$`.
- Check intake versions are positive.
- Check attempt and sequence numbers are positive.
- Enforce one approval per proposed action.
- Enforce one receipt per successful proposed action.
- Enforce one deployment record per deployment.
- Enforce unique remote resource identity.
- Reject approval when proposal hash mismatch through application transaction logic.
- Restrict application-role updates and deletes on `audit_event`, `external_request_attempt`, `external_receipt`, and `approval_decision`.

### Partial Unique Index

```sql
create unique index one_active_modifying_deployment_per_org
on deployment (organization_id)
where status in (
  'planning',
  'awaiting_plan_approval',
  'generating',
  'awaiting_action_approval',
  'executing',
  'verifying',
  'partial',
  'recovery_required',
  'compensating'
)
and intent <> 'status_only';
```

### Query Indexes

- `deployment (organization_id, created_at desc)`
- `task_execution (deployment_id, created_at)`
- `proposed_action (deployment_id, sequence_number)`
- `external_request_attempt (proposed_action_id, attempt_number)`
- `external_resource (organization_id, platform, resource_type)`
- `recovery_action (deployment_id, status, sequence_number)`
- `audit_event (deployment_id, created_at, audit_event_id)`
- `artifact (deployment_id, artifact_type)`

## Transaction Boundaries

### Before External Request

In one local transaction:

1. verify proposal is validated and approved;
2. verify proposal hash equals approval hash;
3. verify current-state version still matches;
4. mark proposal executing;
5. append request-start audit event;
6. insert request-attempt row.

### After Confirmed Success

In one local transaction:

1. finish request attempt as success;
2. insert external receipt;
3. insert or update external resource;
4. mark proposed action succeeded;
5. append success audit event;
6. update deployment to next valid state.

### After Ambiguous Outcome

In one local transaction:

1. finish attempt as ambiguous;
2. mark proposal reconciliation-required;
3. create pending reconciliation action;
4. transition deployment to recovery-required;
5. append ambiguity event.

### After Validation Failure

In one local transaction:

1. insert validation report;
2. mark task validation-failed;
3. block affected proposals;
4. append validation failure event.

## Export and Restore Model

An export bundle contains:

```text
backup-YYYYMMDD-HHMMSS/
â”œâ”€â”€ manifest.json
â”œâ”€â”€ organizations.json
â”œâ”€â”€ organization_intakes.json
â”œâ”€â”€ deployments.json
â”œâ”€â”€ sessions.json
â”œâ”€â”€ task_executions.json
â”œâ”€â”€ artifacts.json
â”œâ”€â”€ validation_reports.json
â”œâ”€â”€ proposed_actions.json
â”œâ”€â”€ approval_decisions.json
â”œâ”€â”€ external_request_attempts.json
â”œâ”€â”€ external_receipts.json
â”œâ”€â”€ external_resources.json
â”œâ”€â”€ recovery_actions.json
â”œâ”€â”€ audit_events.json
â”œâ”€â”€ source_templates.json
â””â”€â”€ deployment_records.json
```

`manifest.json` includes schema version, export time, row counts, file hashes, and the final audit hash per deployment. Artifact bodies are backed up separately from the operational database and verified against `content_hash`.

Restore defaults to dry-run and MUST:

1. validate manifest and file hashes;
2. reject unknown schema versions;
3. load into an empty isolated target;
4. preserve original identifiers and timestamps;
5. validate foreign keys and row counts;
6. validate audit hash chains;
7. verify deployment recovery queries before declaring success.

## Data Retention and Privacy

- Persist only data required for deployment, recovery, verification, and audit.
- Do not persist raw credentials, authorization headers, or complete sensitive vendor responses.
- Sanitize free-text operator revision instructions before storage.
- Do not include call recordings, customer conversations, or appointment data in the internal operational store.
- Retention duration is configured by operator policy and applied only after confirming no active recovery or legal requirement depends on the record.
- Deletion of operational records is an explicit administrative workflow outside the first onboarding feature.

## Model Validation Checklist

- [x] Every spec entity is represented or intentionally derived.
- [x] Deployment and action state transitions are explicit.
- [x] Approval is bound to an immutable proposal hash.
- [x] Ambiguous outcomes require reconciliation before retry.
- [x] External resources are normalized rather than stored in one unstructured registry row.
- [x] Audit history is append-only and secret-free.
- [x] Artifact provenance and version trace are first-class.
- [x] Export and restoration requirements are modeled.
- [x] Client-facing business data remains outside the internal project.
- [x] The model supersedes conflicting table shapes in the earlier PDFs.