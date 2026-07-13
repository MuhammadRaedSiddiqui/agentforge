-- Migration: 010_templates_records.sql
-- Create SourceTemplate and DeploymentRecord tables

-- SourceTemplate table: human-approved exact generation sources
CREATE TABLE source_templates (
    source_template_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_key TEXT NOT NULL,
    platform TEXT NOT NULL,
    capability TEXT,
    version TEXT NOT NULL,
    file_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    approved_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'superseded', 'revoked')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Unique constraint: template_key + version
CREATE UNIQUE INDEX source_templates_key_version
    ON source_templates(template_key, version);

-- Indexes
CREATE INDEX source_templates_platform_idx ON source_templates(platform, capability);
CREATE INDEX source_templates_status_idx ON source_templates(status);

-- DeploymentRecord table: operator-facing summary after terminal state
CREATE TABLE deployment_records (
    deployment_record_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deployment_id UUID NOT NULL UNIQUE REFERENCES deployments(deployment_id),
    organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
    summary TEXT NOT NULL CHECK (summary <> ''),
    capabilities JSONB NOT NULL,
    artifact_manifest JSONB NOT NULL,
    resource_manifest JSONB NOT NULL,
    verification_summary JSONB NOT NULL,
    package_hash TEXT NOT NULL,
    package_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX deployment_records_organization_id_idx ON deployment_records(organization_id, created_at DESC);
CREATE INDEX deployment_records_deployment_id_idx ON deployment_records(deployment_id);

-- Comments
COMMENT ON TABLE source_templates IS 'Human-approved exact generation source templates';
COMMENT ON TABLE deployment_records IS 'Operator-facing summaries produced after terminal deployment states';
COMMENT ON COLUMN source_templates.template_key IS 'Stable logical key for the template';
COMMENT ON COLUMN source_templates.version IS 'Semantic or reviewed version';
COMMENT ON COLUMN source_templates.file_path IS 'Git-tracked repository path';
COMMENT ON COLUMN source_templates.content_hash IS 'Exact file hash';
COMMENT ON COLUMN source_templates.status IS 'Template status: active, superseded, or revoked';
COMMENT ON COLUMN deployment_records.artifact_manifest IS 'Artifact IDs, hashes, and relative paths';
COMMENT ON COLUMN deployment_records.resource_manifest IS 'Resource IDs and final statuses';
COMMENT ON COLUMN deployment_records.verification_summary IS 'Health and isolation evidence';
COMMENT ON COLUMN deployment_records.package_hash IS 'Hash of package manifest';
COMMENT ON COLUMN deployment_records.package_path IS 'Gitignored local output path';
