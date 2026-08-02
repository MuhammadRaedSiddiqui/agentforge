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
