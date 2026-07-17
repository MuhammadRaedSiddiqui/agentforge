-- Migration: 015_legacy_receipts_compatibility.sql
-- Preserve receipt persistence for the deployment executor, which records a
-- deployment-scoped receipt before proposed-action/attempt rows are available.

CREATE TABLE IF NOT EXISTS receipts (
    receipt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deployment_id UUID NOT NULL REFERENCES deployments(deployment_id),
    platform TEXT NOT NULL,
    operation TEXT NOT NULL,
    remote_id TEXT,
    status TEXT NOT NULL,
    response_data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS receipts_deployment_id_idx
    ON receipts(deployment_id, created_at DESC);
