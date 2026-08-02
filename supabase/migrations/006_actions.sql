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
