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
