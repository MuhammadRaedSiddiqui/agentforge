-- Migration: 001_organizations.sql
-- Create Organization and OrganizationIntake tables

-- Organization table: client identity within Agent Forge
CREATE TABLE organizations (
    organization_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL CHECK (display_name <> ''),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'blocked')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Check constraint: organization_id must be lowercase alphanumeric with underscores
ALTER TABLE organizations ADD CONSTRAINT organizations_id_format
    CHECK (organization_id ~ '^[a-z0-9_]+$');

-- OrganizationIntake table: versioned intake records
CREATE TABLE organization_intakes (
    intake_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
    version INTEGER NOT NULL CHECK (version > 0),
    business_name TEXT NOT NULL CHECK (business_name <> ''),
    phone_number TEXT NOT NULL,
    voice_id TEXT NOT NULL,
    timezone TEXT NOT NULL,
    business_hours JSONB NOT NULL,
    services_offered JSONB NOT NULL,
    booking_calendar_id TEXT,
    cancellation_window_hours INTEGER CHECK (cancellation_window_hours >= 0),
    rescheduling_policy JSONB,
    transfer_destination TEXT,
    enabled_capabilities JSONB NOT NULL,
    external_identifiers JSONB NOT NULL,
    intake_hash TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    approved_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Unique constraint: one version per organization
CREATE UNIQUE INDEX organization_intakes_org_version
    ON organization_intakes(organization_id, version);

-- Trigger to update updated_at on organizations
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER organizations_updated_at
    BEFORE UPDATE ON organizations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Comments for documentation
COMMENT ON TABLE organizations IS 'Client identities managed by Agent Forge';
COMMENT ON TABLE organization_intakes IS 'Versioned intake records with operator approval';
COMMENT ON COLUMN organizations.organization_id IS 'Normalized lowercase slug, primary identity';
COMMENT ON COLUMN organization_intakes.version IS 'Monotonically increasing version per organization';
COMMENT ON COLUMN organization_intakes.intake_hash IS 'SHA-256 of canonical sanitized intake';
-- Migration: 002_deployments.sql
-- Create Deployment table with state machine enforcement

-- Create deployment status enum
CREATE TYPE deployment_status AS ENUM (
    'planning',
    'awaiting_plan_approval',
    'generating',
    'awaiting_action_approval',
    'executing',
    'verifying',
    'partial',
    'recovery_required',
    'compensating',
    'complete',
    'failed',
    'aborted'
);

-- Create deployment intent enum
CREATE TYPE deployment_intent AS ENUM (
    'new_onboarding',
    'update_assistant',
    'update_scenario',
    'update_schema',
    'update_backend',
    'status_only',
    'recovery_only'
);

-- Create failure class enum
CREATE TYPE failure_class AS ENUM (
    'validation',
    'authorization',
    'conflict',
    'transient',
    'permanent',
    'ambiguous_outcome',
    'compensation_failure',
    'local_persistence_failure'
);

-- Deployment table
CREATE TABLE deployments (
    deployment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
    intake_id UUID REFERENCES organization_intakes(intake_id),
    intent deployment_intent NOT NULL,
    status deployment_status NOT NULL,
    plan_hash TEXT,
    plan_version TEXT,
    constitution_version TEXT NOT NULL,
    spec_version TEXT NOT NULL,
    started_by TEXT NOT NULL,
    lock_owner TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    last_verified_at TIMESTAMPTZ,
    failure_class failure_class,
    failure_summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trigger to update updated_at
CREATE TRIGGER deployments_updated_at
    BEFORE UPDATE ON deployments
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Partial unique index: only one active modifying deployment per organization
CREATE UNIQUE INDEX one_active_modifying_deployment_per_org
    ON deployments (organization_id)
    WHERE status IN (
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
    AND intent <> 'status_only';

-- Check constraint: intake_id required for generating/modifying intents
ALTER TABLE deployments ADD CONSTRAINT deployments_intake_required
    CHECK (
        (intent IN ('status_only', 'recovery_only') AND intake_id IS NULL) OR
        (intent NOT IN ('status_only', 'recovery_only') AND intake_id IS NOT NULL)
    );

-- A plan hash is required after planning. Terminal failed/aborted records
-- without a plan represent failures before plan persistence.
ALTER TABLE deployments ADD CONSTRAINT deployments_plan_hash_required
    CHECK (
        plan_hash IS NOT NULL OR status IN ('planning', 'failed', 'aborted')
    );

-- Check constraint: completed_at only for terminal states
ALTER TABLE deployments ADD CONSTRAINT deployments_completed_at_terminal
    CHECK (
        (status IN ('complete', 'failed', 'aborted') AND completed_at IS NOT NULL) OR
        (status NOT IN ('complete', 'failed', 'aborted') AND completed_at IS NULL)
    );

-- Comments
COMMENT ON TABLE deployments IS 'Deployment lifecycles with state machine enforcement';
COMMENT ON COLUMN deployments.intent IS 'Immutable deployment intent';
COMMENT ON COLUMN deployments.status IS 'Current state in deployment lifecycle';
COMMENT ON COLUMN deployments.lock_owner IS 'Active local session identifier holding the lock';
COMMENT ON INDEX one_active_modifying_deployment_per_org
    IS 'Prevents concurrent modifying deployments for same organization';
-- Migration: 003_sessions.sql
-- Create Session table for CLI process tracking

-- Session table: one local CLI process context
CREATE TABLE sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deployment_id UUID REFERENCES deployments(deployment_id),
    operator_id TEXT NOT NULL,
    host_fingerprint TEXT NOT NULL,
    process_id INTEGER NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    end_reason TEXT CHECK (end_reason IN ('complete', 'aborted', 'crash_detected', 'unknown'))
);

-- Index for looking up active sessions
CREATE INDEX sessions_deployment_id_idx ON sessions(deployment_id);
CREATE INDEX sessions_started_at_idx ON sessions(started_at DESC);

-- Comments
COMMENT ON TABLE sessions IS 'Local CLI process context for diagnostic purposes';
COMMENT ON COLUMN sessions.operator_id IS 'Local operator identity (not authentication)';
COMMENT ON COLUMN sessions.host_fingerprint IS 'Non-secret machine identifier hash';
COMMENT ON COLUMN sessions.process_id IS 'Local process ID (diagnostic only)';
COMMENT ON COLUMN sessions.end_reason IS 'Reason for session termination';
-- Migration: 004_task_executions.sql
-- Create TaskExecution table for specialist delegations

-- Create task status enum
CREATE TYPE task_status AS ENUM (
    'pending',
    'running',
    'success',
    'validation_failed',
    'error',
    'blocked',
    'aborted'
);

-- TaskExecution table: one deterministic delegation to a specialist domain
CREATE TABLE task_executions (
    task_id TEXT PRIMARY KEY,
    deployment_id UUID NOT NULL REFERENCES deployments(deployment_id),
    session_id UUID NOT NULL REFERENCES sessions(session_id),
    agent_target TEXT NOT NULL,
    action_type TEXT NOT NULL,
    context_hash TEXT NOT NULL,
    constraints JSONB NOT NULL DEFAULT '[]',
    dependency_task_ids JSONB NOT NULL DEFAULT '[]',
    verification_required BOOLEAN NOT NULL DEFAULT true,
    status task_status NOT NULL DEFAULT 'pending',
    attempt_number INTEGER NOT NULL DEFAULT 1 CHECK (attempt_number > 0),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_class failure_class,
    error_detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Constraint: agent_target cannot change after creation (enforce in application)
-- This is a logical constraint enforced by application code, not a DB constraint

-- Check constraint: completed_at only for terminal states
ALTER TABLE task_executions ADD CONSTRAINT task_executions_completed_at_terminal
    CHECK (
        (status IN ('success', 'validation_failed', 'error', 'aborted')
         AND completed_at IS NOT NULL) OR
        (status NOT IN ('success', 'validation_failed', 'error', 'aborted')
         AND completed_at IS NULL)
    );

-- Check constraint: error_class only for error states
ALTER TABLE task_executions ADD CONSTRAINT task_executions_error_class_on_error
    CHECK (
        (status IN ('error', 'validation_failed') AND error_class IS NOT NULL) OR
        (status NOT IN ('error', 'validation_failed') AND error_class IS NULL)
    );

-- Indexes for queries
CREATE INDEX task_executions_deployment_id_idx ON task_executions(deployment_id, created_at);
CREATE INDEX task_executions_status_idx ON task_executions(status);
CREATE INDEX task_executions_agent_target_idx ON task_executions(agent_target);

-- Comments
COMMENT ON TABLE task_executions IS 'Specialist agent task delegations with dependencies';
COMMENT ON COLUMN task_executions.task_id IS 'Generated by application, deterministic format';
COMMENT ON COLUMN task_executions.agent_target IS 'Must exist in agent registry, immutable after creation';
COMMENT ON COLUMN task_executions.context_hash IS 'SHA-256 of sanitized immutable context';
COMMENT ON COLUMN task_executions.dependency_task_ids IS 'Array of prior task IDs that must be satisfied';
COMMENT ON COLUMN task_executions.attempt_number IS 'Attempt number for this task (starts at 1)';
-- Migration: 005_artifacts.sql
-- Create Artifact and ValidationReport tables

-- Create artifact type enum
CREATE TYPE artifact_type AS ENUM (
    'vapi_assistant_config',
    'vapi_tool_schema',
    'make_scenario_blueprint',
    'database_migration',
    'database_recovery_plan',
    'rls_policy',
    'organization_record',
    'server_candidate',
    'server_diff',
    'validation_report',
    'deployment_summary',
    'dry_run_plan',
    'diagnostic_report'
);

-- Create verification status enum
CREATE TYPE verification_status AS ENUM (
    'unverified',
    'verified',
    'stale',
    'failed'
);

-- Artifact table: generated content or report
CREATE TABLE artifacts (
    artifact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deployment_id UUID NOT NULL REFERENCES deployments(deployment_id),
    task_id TEXT NOT NULL REFERENCES task_executions(task_id),
    artifact_type artifact_type NOT NULL,
    agent_source TEXT NOT NULL,
    source_template_id UUID,
    content_hash TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    summary TEXT NOT NULL CHECK (summary <> ''),
    field_provenance JSONB,
    model_id TEXT,
    prompt_version TEXT,
    validator_version TEXT NOT NULL,
    validation_status verification_status NOT NULL DEFAULT 'unverified',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ValidationReport table: deterministic evidence for artifacts or actions
CREATE TABLE validation_reports (
    validation_report_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id TEXT NOT NULL REFERENCES task_executions(task_id),
    artifact_id UUID REFERENCES artifacts(artifact_id),
    proposed_action_id UUID,
    validator_name TEXT NOT NULL,
    validator_version TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    checks JSONB NOT NULL DEFAULT '[]',
    corrections JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Check constraint: at least one of artifact_id or proposed_action_id must be set
ALTER TABLE validation_reports ADD CONSTRAINT validation_reports_subject_required
    CHECK (artifact_id IS NOT NULL OR proposed_action_id IS NOT NULL);

-- Constraint: agent_source must match originating task target (enforced in application)
-- Constraint: content cannot change after hashing (revisions create new artifact)

-- Indexes
CREATE INDEX artifacts_deployment_id_idx ON artifacts(deployment_id, artifact_type);
CREATE INDEX artifacts_task_id_idx ON artifacts(task_id);
CREATE INDEX artifacts_validation_status_idx ON artifacts(validation_status);
CREATE INDEX validation_reports_artifact_id_idx ON validation_reports(artifact_id);
CREATE INDEX validation_reports_proposed_action_id_idx ON validation_reports(proposed_action_id);
CREATE INDEX validation_reports_task_id_idx ON validation_reports(task_id);

-- Comments
COMMENT ON TABLE artifacts IS 'Generated content or reports with provenance and validation status';
COMMENT ON TABLE validation_reports IS 'Deterministic validation evidence for artifacts and actions';
COMMENT ON COLUMN artifacts.agent_source IS 'Assigned by trusted code, must match task target';
COMMENT ON COLUMN artifacts.content_hash IS 'SHA-256 of exact content';
COMMENT ON COLUMN artifacts.storage_path IS 'Relative path under gitignored output package';
COMMENT ON COLUMN artifacts.field_provenance IS 'Map of inferred/defaulted fields to reason and source';
COMMENT ON COLUMN validation_reports.checks IS 'Bounded array of check results';
COMMENT ON COLUMN validation_reports.corrections IS 'Deterministic corrections with old/new hashes';
-- Migration: 006_actions.sql
-- Create ProposedAction, ApprovalDecision, ExternalRequestAttempt, and ExternalReceipt tables

-- Create resource platform enum
CREATE TYPE resource_platform AS ENUM (
    'vapi',
    'make',
    'supabase_client',
    'hosting'
);

-- Create action status enum
CREATE TYPE action_status AS ENUM (
    'proposed',
    'validated',
    'awaiting_approval',
    'approved',
    'rejected',
    'executing',
    'succeeded',
    'failed',
    'ambiguous',
    'reconciliation_required',
    'compensation_pending',
    'compensated',
    'compensation_failed',
    'cancelled'
);

-- Create approval decision type enum
CREATE TYPE approval_decision_type AS ENUM (
    'approved',
    'rejected_abort',
    'rejected_revise'
);

-- ProposedAction table: immutable candidate external side effect
CREATE TABLE proposed_actions (
    proposed_action_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deployment_id UUID NOT NULL REFERENCES deployments(deployment_id),
    task_id TEXT NOT NULL REFERENCES task_executions(task_id),
    sequence_number INTEGER NOT NULL CHECK (sequence_number > 0),
    platform resource_platform NOT NULL,
    operation TEXT NOT NULL,
    target_reference JSONB NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_storage_path TEXT NOT NULL,
    state_version_before TEXT,
    proposal_hash TEXT NOT NULL,
    idempotency_key TEXT,
    retry_policy JSONB NOT NULL,
    reconciliation_strategy TEXT NOT NULL,
    compensation_operation TEXT,
    status action_status NOT NULL DEFAULT 'proposed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trigger to update updated_at
CREATE TRIGGER proposed_actions_updated_at
    BEFORE UPDATE ON proposed_actions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Unique constraint: sequence_number per deployment
CREATE UNIQUE INDEX proposed_actions_deployment_sequence
    ON proposed_actions(deployment_id, sequence_number);

-- ApprovalDecision table: one operator decision per proposal
CREATE TABLE approval_decisions (
    approval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposed_action_id UUID NOT NULL UNIQUE REFERENCES proposed_actions(proposed_action_id),
    proposal_hash TEXT NOT NULL,
    decision approval_decision_type NOT NULL,
    operator_id TEXT NOT NULL,
    display_hash TEXT NOT NULL,
    revision_instruction TEXT,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Check constraint: revision_instruction required for rejected_revise
ALTER TABLE approval_decisions ADD CONSTRAINT approval_decisions_revision_required
    CHECK (
        (decision = 'rejected_revise' AND revision_instruction IS NOT NULL) OR
        (decision <> 'rejected_revise')
    );

-- ExternalRequestAttempt table: one actual vendor request attempt
CREATE TABLE external_request_attempts (
    attempt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposed_action_id UUID NOT NULL REFERENCES proposed_actions(proposed_action_id),
    attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
    request_hash TEXT NOT NULL,
    vendor_request_id TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    http_status INTEGER,
    outcome TEXT NOT NULL CHECK (outcome IN ('success', 'failure', 'timeout', 'connection_error', 'ambiguous')),
    failure_class failure_class,
    response_summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Unique constraint: attempt_number per proposed action
CREATE UNIQUE INDEX external_request_attempts_action_attempt
    ON external_request_attempts(proposed_action_id, attempt_number);

-- Check constraint: failure_class required for non-success outcomes
ALTER TABLE external_request_attempts ADD CONSTRAINT external_request_attempts_failure_class_required
    CHECK (
        (outcome = 'success' AND failure_class IS NULL) OR
        (outcome <> 'success' AND failure_class IS NOT NULL)
    );

-- ExternalReceipt table: confirmed evidence of successful side effect
CREATE TABLE external_receipts (
    receipt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposed_action_id UUID NOT NULL UNIQUE REFERENCES proposed_actions(proposed_action_id),
    attempt_id UUID NOT NULL REFERENCES external_request_attempts(attempt_id),
    platform resource_platform NOT NULL,
    operation TEXT NOT NULL,
    remote_resource_id TEXT,
    remote_version TEXT,
    observed_state_hash TEXT,
    vendor_request_id TEXT,
    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    receipt_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX proposed_actions_deployment_id_idx ON proposed_actions(deployment_id, sequence_number);
CREATE INDEX proposed_actions_status_idx ON proposed_actions(status);
CREATE INDEX approval_decisions_proposed_action_id_idx ON approval_decisions(proposed_action_id);
CREATE INDEX external_request_attempts_proposed_action_id_idx ON external_request_attempts(proposed_action_id, attempt_number);
CREATE INDEX external_receipts_proposed_action_id_idx ON external_receipts(proposed_action_id);

-- Comments
COMMENT ON TABLE proposed_actions IS 'Immutable proposed external side effects';
COMMENT ON TABLE approval_decisions IS 'Operator decisions bound to exact proposal hashes';
COMMENT ON TABLE external_request_attempts IS 'Append-only record of vendor request attempts';
COMMENT ON TABLE external_receipts IS 'Confirmed evidence of successful side effects';
COMMENT ON COLUMN proposed_actions.proposal_hash IS 'Hash binding operation, target, payload, dependencies, and state version';
COMMENT ON COLUMN approval_decisions.display_hash IS 'Hash of the exact rendered approval content';
COMMENT ON COLUMN external_request_attempts.outcome IS 'Request outcome: success, failure, timeout, connection_error, or ambiguous';
COMMENT ON COLUMN external_receipts.receipt_hash IS 'Tamper-evident hash of receipt';
-- Migration: 007_resources.sql
-- Create ExternalResource table for live resource registry

-- Create resource type enum
CREATE TYPE resource_type AS ENUM (
    'vapi_assistant',
    'vapi_tool',
    'vapi_phone_number',
    'make_scenario',
    'make_hook',
    'supabase_organization_row',
    'supabase_migration',
    'supabase_policy',
    'hosting_service',
    'hosting_deployment',
    'backend_file_revision'
);

-- ExternalResource table: registry of known live resources
CREATE TABLE external_resources (
    external_resource_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
    created_by_deployment_id UUID NOT NULL REFERENCES deployments(deployment_id),
    platform resource_platform NOT NULL,
    resource_type resource_type NOT NULL,
    capability TEXT,
    remote_resource_id TEXT NOT NULL,
    parent_external_resource_id UUID REFERENCES external_resources(external_resource_id),
    remote_url TEXT,
    lifecycle_status TEXT NOT NULL DEFAULT 'active' CHECK (lifecycle_status IN ('active', 'inactive', 'deleted', 'unknown')),
    last_observed_hash TEXT,
    last_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trigger to update updated_at
CREATE TRIGGER external_resources_updated_at
    BEFORE UPDATE ON external_resources
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Unique constraint: platform + resource_type + remote_resource_id
CREATE UNIQUE INDEX external_resources_platform_type_remote_id
    ON external_resources(platform, resource_type, remote_resource_id);

-- Indexes for queries
CREATE INDEX external_resources_organization_id_idx ON external_resources(organization_id, platform, resource_type);
CREATE INDEX external_resources_deployment_id_idx ON external_resources(created_by_deployment_id);
CREATE INDEX external_resources_lifecycle_status_idx ON external_resources(lifecycle_status);
CREATE INDEX external_resources_parent_id_idx ON external_resources(parent_external_resource_id);

-- Comments
COMMENT ON TABLE external_resources IS 'Current registry of known live resources';
COMMENT ON COLUMN external_resources.remote_resource_id IS 'Vendor identifier';
COMMENT ON COLUMN external_resources.parent_external_resource_id IS 'Parent resource if this is a child resource';
COMMENT ON COLUMN external_resources.lifecycle_status IS 'Current status: active, inactive, deleted, or unknown';
COMMENT ON COLUMN external_resources.last_observed_hash IS 'Sanitized remote-state hash';
COMMENT ON COLUMN external_resources.last_verified_at IS 'Last reconciliation timestamp';
COMMENT ON INDEX external_resources_platform_type_remote_id
    IS 'Prevents duplicate resource registration';
-- Migration: 008_recovery.sql
-- Create RecoveryAction table for durable retry, reconciliation, and compensation

-- RecoveryAction table: durable recovery work
CREATE TABLE recovery_actions (
    recovery_action_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deployment_id UUID NOT NULL REFERENCES deployments(deployment_id),
    proposed_action_id UUID REFERENCES proposed_actions(proposed_action_id),
    external_resource_id UUID REFERENCES external_resources(external_resource_id),
    kind TEXT NOT NULL CHECK (kind IN ('reconcile', 'retry', 'compensate', 'manual_inspection')),
    operation TEXT NOT NULL,
    sequence_number INTEGER NOT NULL CHECK (sequence_number > 0),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'running', 'succeeded', 'failed', 'deferred')),
    requires_approval BOOLEAN NOT NULL DEFAULT true,
    failure_summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

-- Unique constraint: sequence_number per deployment
CREATE UNIQUE INDEX recovery_actions_deployment_sequence
    ON recovery_actions(deployment_id, sequence_number);

-- Check constraint: at least one of proposed_action_id or external_resource_id
ALTER TABLE recovery_actions ADD CONSTRAINT recovery_actions_subject_required
    CHECK (proposed_action_id IS NOT NULL OR external_resource_id IS NOT NULL);

-- Check constraint: resolved_at only for terminal states
ALTER TABLE recovery_actions ADD CONSTRAINT recovery_actions_resolved_at_terminal
    CHECK (
        (status IN ('succeeded', 'failed', 'deferred') AND resolved_at IS NOT NULL) OR
        (status NOT IN ('succeeded', 'failed', 'deferred') AND resolved_at IS NULL)
    );

-- Indexes
CREATE INDEX recovery_actions_deployment_id_idx ON recovery_actions(deployment_id, status, sequence_number);
CREATE INDEX recovery_actions_proposed_action_id_idx ON recovery_actions(proposed_action_id);
CREATE INDEX recovery_actions_external_resource_id_idx ON recovery_actions(external_resource_id);
CREATE INDEX recovery_actions_status_idx ON recovery_actions(status);

-- Comments
COMMENT ON TABLE recovery_actions IS 'Durable retry, reconciliation, or compensation work';
COMMENT ON COLUMN recovery_actions.kind IS 'Type of recovery: reconcile, retry, compensate, or manual_inspection';
COMMENT ON COLUMN recovery_actions.operation IS 'Named adapter operation or inspection task';
COMMENT ON COLUMN recovery_actions.sequence_number IS 'Recovery order within deployment';
COMMENT ON COLUMN recovery_actions.requires_approval IS 'True for every live side effect (compensation not auto-approved)';
COMMENT ON COLUMN recovery_actions.status IS 'Current status: pending, approved, running, succeeded, failed, or deferred';
-- Migration: 009_audit.sql
-- Create AuditEvent table for append-only chronological evidence

-- AuditEvent table: append-only audit trail
CREATE TABLE audit_events (
    audit_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deployment_id UUID REFERENCES deployments(deployment_id),
    session_id UUID NOT NULL REFERENCES sessions(session_id),
    task_id TEXT REFERENCES task_executions(task_id),
    event_type TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('operator', 'orchestrator', 'specialist', 'validator', 'adapter', 'system')),
    actor_id TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT NOT NULL CHECK (summary <> ''),
    detail JSONB NOT NULL,
    event_hash TEXT NOT NULL,
    previous_event_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Prevent updates and deletes on audit_events (append-only enforcement)
-- This will be enforced through application role permissions

-- Indexes for queries
CREATE INDEX audit_events_deployment_id_idx ON audit_events(deployment_id, created_at, audit_event_id);
CREATE INDEX audit_events_session_id_idx ON audit_events(session_id, created_at);
CREATE INDEX audit_events_task_id_idx ON audit_events(task_id);
CREATE INDEX audit_events_event_type_idx ON audit_events(event_type, created_at);
CREATE INDEX audit_events_created_at_idx ON audit_events(created_at DESC);

-- Comments
COMMENT ON TABLE audit_events IS 'Append-only chronological evidence with hash chaining';
COMMENT ON COLUMN audit_events.event_type IS 'Stable event catalog value';
COMMENT ON COLUMN audit_events.actor_type IS 'Type of actor: operator, orchestrator, specialist, validator, adapter, or system';
COMMENT ON COLUMN audit_events.actor_id IS 'Sanitized identity of the actor';
COMMENT ON COLUMN audit_events.subject_type IS 'Entity type the event is about';
COMMENT ON COLUMN audit_events.subject_id IS 'Entity identifier';
COMMENT ON COLUMN audit_events.status IS 'Event result or status';
COMMENT ON COLUMN audit_events.summary IS 'Sanitized, bounded human-readable summary';
COMMENT ON COLUMN audit_events.detail IS 'Sanitized, schema-versioned metadata';
COMMENT ON COLUMN audit_events.event_hash IS 'Hash of canonical event content';
COMMENT ON COLUMN audit_events.previous_event_hash IS 'Prior event hash for deployment chain (null for first event)';

-- Note: Updates and deletes should be forbidden to the application role
-- This will be configured when setting up database roles and permissions
-- Migration: 010_templates_records.sql
-- Create SourceTemplate and DeploymentRecord tables

-- SourceTemplate table: human-approved exact generation sources
CREATE TABLE source_templates (
    source_template_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_key TEXT NOT NULL,
    platform TEXT NOT NULL,
    capability TEXT,
    version TEXT NOT NULL,
    file_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    approved_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'superseded', 'revoked')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Unique constraint: template_key + version
CREATE UNIQUE INDEX source_templates_key_version
    ON source_templates(template_key, version);

-- Indexes
CREATE INDEX source_templates_platform_idx ON source_templates(platform, capability);
CREATE INDEX source_templates_status_idx ON source_templates(status);

-- DeploymentRecord table: operator-facing summary after terminal state
CREATE TABLE deployment_records (
    deployment_record_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deployment_id UUID NOT NULL UNIQUE REFERENCES deployments(deployment_id),
    organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
    summary TEXT NOT NULL CHECK (summary <> ''),
    capabilities JSONB NOT NULL,
    artifact_manifest JSONB NOT NULL,
    resource_manifest JSONB NOT NULL,
    verification_summary JSONB NOT NULL,
    package_hash TEXT NOT NULL,
    package_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX deployment_records_organization_id_idx ON deployment_records(organization_id, created_at DESC);
CREATE INDEX deployment_records_deployment_id_idx ON deployment_records(deployment_id);

-- Comments
COMMENT ON TABLE source_templates IS 'Human-approved exact generation source templates';
COMMENT ON TABLE deployment_records IS 'Operator-facing summaries produced after terminal deployment states';
COMMENT ON COLUMN source_templates.template_key IS 'Stable logical key for the template';
COMMENT ON COLUMN source_templates.version IS 'Semantic or reviewed version';
COMMENT ON COLUMN source_templates.file_path IS 'Git-tracked repository path';
COMMENT ON COLUMN source_templates.content_hash IS 'Exact file hash';
COMMENT ON COLUMN source_templates.status IS 'Template status: active, superseded, or revoked';
COMMENT ON COLUMN deployment_records.artifact_manifest IS 'Artifact IDs, hashes, and relative paths';
COMMENT ON COLUMN deployment_records.resource_manifest IS 'Resource IDs and final statuses';
COMMENT ON COLUMN deployment_records.verification_summary IS 'Health and isolation evidence';
COMMENT ON COLUMN deployment_records.package_hash IS 'Hash of package manifest';
COMMENT ON COLUMN deployment_records.package_path IS 'Gitignored local output path';
-- Migration: 011_indexes.sql
-- Comprehensive query indexes per data-model.md recommendations
-- Note: Many indexes were already created in individual table migrations
-- This migration adds any remaining recommended indexes

-- Additional indexes for deployments (beyond what's already in 002_deployments.sql)
CREATE INDEX IF NOT EXISTS deployments_organization_created_at_idx
    ON deployments(organization_id, created_at DESC);

-- Additional indexes for organizations
CREATE INDEX IF NOT EXISTS organizations_status_idx
    ON organizations(status);
CREATE INDEX IF NOT EXISTS organizations_created_at_idx
    ON organizations(created_at DESC);

-- Additional indexes for organization_intakes
CREATE INDEX IF NOT EXISTS organization_intakes_organization_id_idx
    ON organization_intakes(organization_id, version DESC);
CREATE INDEX IF NOT EXISTS organization_intakes_approved_at_idx
    ON organization_intakes(approved_at DESC);

-- Additional indexes for sessions
CREATE INDEX IF NOT EXISTS sessions_operator_id_idx
    ON sessions(operator_id, started_at DESC);
CREATE INDEX IF NOT EXISTS sessions_ended_at_idx
    ON sessions(ended_at DESC) WHERE ended_at IS NOT NULL;

-- Additional composite indexes for task_executions
CREATE INDEX IF NOT EXISTS task_executions_deployment_status_idx
    ON task_executions(deployment_id, status);

-- Additional indexes for artifacts
CREATE INDEX IF NOT EXISTS artifacts_deployment_type_idx
    ON artifacts(deployment_id, artifact_type);
CREATE INDEX IF NOT EXISTS artifacts_agent_source_idx
    ON artifacts(agent_source);

-- Additional indexes for validation_reports
CREATE INDEX IF NOT EXISTS validation_reports_passed_idx
    ON validation_reports(passed, created_at DESC);

-- Additional indexes for proposed_actions
CREATE INDEX IF NOT EXISTS proposed_actions_task_id_idx
    ON proposed_actions(task_id);
CREATE INDEX IF NOT EXISTS proposed_actions_platform_idx
    ON proposed_actions(platform, status);

-- Additional indexes for approval_decisions
CREATE INDEX IF NOT EXISTS approval_decisions_operator_id_idx
    ON approval_decisions(operator_id, decided_at DESC);
CREATE INDEX IF NOT EXISTS approval_decisions_decision_idx
    ON approval_decisions(decision);

-- Migration: 013_approval_decision_compatibility.sql
ALTER TABLE approval_decisions
    ALTER COLUMN proposed_action_id DROP NOT NULL;

ALTER TABLE approval_decisions
    ADD COLUMN IF NOT EXISTS deployment_id UUID REFERENCES deployments(deployment_id),
    ADD COLUMN IF NOT EXISTS decided_by TEXT,
    ADD COLUMN IF NOT EXISTS notes TEXT;

CREATE INDEX IF NOT EXISTS approval_decisions_deployment_id_idx
    ON approval_decisions(deployment_id, decided_at DESC);

-- Additional indexes for external_request_attempts
CREATE INDEX IF NOT EXISTS external_request_attempts_outcome_idx
    ON external_request_attempts(outcome, created_at DESC);
CREATE INDEX IF NOT EXISTS external_request_attempts_vendor_request_id_idx
    ON external_request_attempts(vendor_request_id) WHERE vendor_request_id IS NOT NULL;

-- Additional indexes for external_receipts
CREATE INDEX IF NOT EXISTS external_receipts_platform_idx
    ON external_receipts(platform, confirmed_at DESC);
CREATE INDEX IF NOT EXISTS external_receipts_remote_resource_id_idx
    ON external_receipts(remote_resource_id) WHERE remote_resource_id IS NOT NULL;

-- Additional indexes for external_resources
CREATE INDEX IF NOT EXISTS external_resources_capability_idx
    ON external_resources(capability) WHERE capability IS NOT NULL;
CREATE INDEX IF NOT EXISTS external_resources_verified_at_idx
    ON external_resources(last_verified_at DESC) WHERE last_verified_at IS NOT NULL;

-- Additional indexes for recovery_actions
CREATE INDEX IF NOT EXISTS recovery_actions_kind_idx
    ON recovery_actions(kind, status);

-- Additional indexes for audit_events
CREATE INDEX IF NOT EXISTS audit_events_actor_id_idx
    ON audit_events(actor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS audit_events_subject_idx
    ON audit_events(subject_type, subject_id);

-- Additional indexes for source_templates
CREATE INDEX IF NOT EXISTS source_templates_file_path_idx
    ON source_templates(file_path);
CREATE INDEX IF NOT EXISTS source_templates_content_hash_idx
    ON source_templates(content_hash);

-- Additional indexes for deployment_records
CREATE INDEX IF NOT EXISTS deployment_records_created_at_idx
    ON deployment_records(created_at DESC);

-- Comments
COMMENT ON INDEX deployments_organization_created_at_idx
    IS 'Efficient lookup of recent deployments by organization';
COMMENT ON INDEX task_executions_deployment_status_idx
    IS 'Find tasks by deployment and status';
COMMENT ON INDEX audit_events_actor_id_idx
    IS 'Trace actions by actor';
COMMENT ON INDEX external_resources_organization_id_idx
    IS 'List all resources for an organization by platform and type';
COMMENT ON INDEX recovery_actions_deployment_id_idx
    IS 'Find pending recovery actions by deployment';

-- Performance note: These indexes support the most common query patterns:
-- 1. Looking up deployments by organization
-- 2. Finding tasks and artifacts by deployment
-- 3. Tracing audit events chronologically
-- 4. Resource reconciliation queries
-- 5. Recovery action status checks
