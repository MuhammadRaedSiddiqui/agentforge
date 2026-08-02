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
