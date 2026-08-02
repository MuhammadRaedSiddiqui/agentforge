-- Permit a deployment that failed before plan persistence to reach a terminal
-- recovery state. All non-terminal states after planning still require a plan.
ALTER TABLE deployments
    DROP CONSTRAINT IF EXISTS deployments_plan_hash_required;

ALTER TABLE deployments
    ADD CONSTRAINT deployments_plan_hash_required
    CHECK (
        plan_hash IS NOT NULL
        OR status IN ('planning', 'failed', 'aborted')
    );
