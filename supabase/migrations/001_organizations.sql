-- Migration: 001_organizations.sql
-- Create Organization and OrganizationIntake tables

-- Organization table: client identity within Agent Forge
CREATE TABLE organizations (
    organization_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL CHECK (display_name <> ''),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'blocked')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Check constraint: organization_id must be lowercase alphanumeric with underscores
ALTER TABLE organizations ADD CONSTRAINT organizations_id_format
    CHECK (organization_id ~ '^[a-z0-9_]+$');

-- OrganizationIntake table: versioned intake records
CREATE TABLE organization_intakes (
    intake_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
    version INTEGER NOT NULL CHECK (version > 0),
    business_name TEXT NOT NULL CHECK (business_name <> ''),
    phone_number TEXT NOT NULL,
    voice_id TEXT NOT NULL,
    timezone TEXT NOT NULL,
    business_hours JSONB NOT NULL,
    services_offered JSONB NOT NULL,
    booking_calendar_id TEXT,
    cancellation_window_hours INTEGER CHECK (cancellation_window_hours >= 0),
    rescheduling_policy JSONB,
    transfer_destination TEXT,
    enabled_capabilities JSONB NOT NULL,
    external_identifiers JSONB NOT NULL,
    intake_hash TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    approved_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Unique constraint: one version per organization
CREATE UNIQUE INDEX organization_intakes_org_version
    ON organization_intakes(organization_id, version);

-- Trigger to update updated_at on organizations
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER organizations_updated_at
    BEFORE UPDATE ON organizations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Comments for documentation
COMMENT ON TABLE organizations IS 'Client identities managed by Agent Forge';
COMMENT ON TABLE organization_intakes IS 'Versioned intake records with operator approval';
COMMENT ON COLUMN organizations.organization_id IS 'Normalized lowercase slug, primary identity';
COMMENT ON COLUMN organization_intakes.version IS 'Monotonically increasing version per organization';
COMMENT ON COLUMN organization_intakes.intake_hash IS 'SHA-256 of canonical sanitized intake';
