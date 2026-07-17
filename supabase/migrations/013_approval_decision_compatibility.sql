-- Migration: 013_approval_decision_compatibility.sql
-- Align approval decision persistence with the orchestrator's deployment-
-- scoped approval workflow.  Earlier migrations required a proposed action
-- row, but the executor records decisions before that row is persisted.

ALTER TABLE approval_decisions
    ALTER COLUMN proposed_action_id DROP NOT NULL;

ALTER TABLE approval_decisions
    ADD COLUMN IF NOT EXISTS deployment_id UUID REFERENCES deployments(deployment_id),
    ADD COLUMN IF NOT EXISTS decided_by TEXT,
    ADD COLUMN IF NOT EXISTS notes TEXT;

CREATE INDEX IF NOT EXISTS approval_decisions_deployment_id_idx
    ON approval_decisions(deployment_id, decided_at DESC);

COMMENT ON COLUMN approval_decisions.deployment_id
    IS 'Deployment-scoped approval linkage when a proposed action row is not persisted yet';
COMMENT ON COLUMN approval_decisions.decided_by
    IS 'Operator identity retained for compatibility with the approval audit model';
COMMENT ON COLUMN approval_decisions.notes
    IS 'Optional operator notes retained for compatibility with the approval audit model';
