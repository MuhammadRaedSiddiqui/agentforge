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
