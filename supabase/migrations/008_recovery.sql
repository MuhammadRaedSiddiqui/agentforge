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
