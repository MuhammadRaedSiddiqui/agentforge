-- Migration: 007_resources.sql
-- Create ExternalResource table for live resource registry

-- Create resource type enum
CREATE TYPE resource_type AS ENUM (
    'vapi_assistant',
    'vapi_tool',
    'vapi_phone_number',
    'make_scenario',
    'make_hook',
    'supabase_organization_row',
    'supabase_migration',
    'supabase_policy',
    'hosting_service',
    'hosting_deployment',
    'backend_file_revision'
);

-- ExternalResource table: registry of known live resources
CREATE TABLE external_resources (
    external_resource_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
    created_by_deployment_id UUID NOT NULL REFERENCES deployments(deployment_id),
    platform resource_platform NOT NULL,
    resource_type resource_type NOT NULL,
    capability TEXT,
    remote_resource_id TEXT NOT NULL,
    parent_external_resource_id UUID REFERENCES external_resources(external_resource_id),
    remote_url TEXT,
    lifecycle_status TEXT NOT NULL DEFAULT 'active' CHECK (lifecycle_status IN ('active', 'inactive', 'deleted', 'unknown')),
    last_observed_hash TEXT,
    last_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trigger to update updated_at
CREATE TRIGGER external_resources_updated_at
    BEFORE UPDATE ON external_resources
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Unique constraint: platform + resource_type + remote_resource_id
CREATE UNIQUE INDEX external_resources_platform_type_remote_id
    ON external_resources(platform, resource_type, remote_resource_id);

-- Indexes for queries
CREATE INDEX external_resources_organization_id_idx ON external_resources(organization_id, platform, resource_type);
CREATE INDEX external_resources_deployment_id_idx ON external_resources(created_by_deployment_id);
CREATE INDEX external_resources_lifecycle_status_idx ON external_resources(lifecycle_status);
CREATE INDEX external_resources_parent_id_idx ON external_resources(parent_external_resource_id);

-- Comments
COMMENT ON TABLE external_resources IS 'Current registry of known live resources';
COMMENT ON COLUMN external_resources.remote_resource_id IS 'Vendor identifier';
COMMENT ON COLUMN external_resources.parent_external_resource_id IS 'Parent resource if this is a child resource';
COMMENT ON COLUMN external_resources.lifecycle_status IS 'Current status: active, inactive, deleted, or unknown';
COMMENT ON COLUMN external_resources.last_observed_hash IS 'Sanitized remote-state hash';
COMMENT ON COLUMN external_resources.last_verified_at IS 'Last reconciliation timestamp';
COMMENT ON CONSTRAINT external_resources_platform_type_remote_id
    ON external_resources IS 'Prevents duplicate resource registration';
