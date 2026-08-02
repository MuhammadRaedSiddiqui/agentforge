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
