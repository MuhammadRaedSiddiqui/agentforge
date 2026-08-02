-- Ground Truth Database Schema Template for Client Organizations
-- Template Version: 1.0.0
-- Purpose: Create organization table and RLS policies for tenant isolation

-- ============================================================================
-- ORGANIZATION TABLE
-- ============================================================================

-- Create the organizations table for storing client information
CREATE TABLE IF NOT EXISTS organizations (
    organization_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL CHECK (LENGTH(display_name) > 0),
    phone TEXT CHECK (phone ~ '^\+[1-9]\d{1,14}$'),
    email TEXT CHECK (email ~ '^[^@]+@[^@]+\.[^@]+$'),
    industry TEXT,
    business_hours JSONB DEFAULT '{
        "monday": {"open": "09:00", "close": "17:00"},
        "tuesday": {"open": "09:00", "close": "17:00"},
        "wednesday": {"open": "09:00", "close": "17:00"},
        "thursday": {"open": "09:00", "close": "17:00"},
        "friday": {"open": "09:00", "close": "17:00"},
        "saturday": {"open": null, "close": null},
        "sunday": {"open": null, "close": null}
    }'::jsonb,
    timezone TEXT DEFAULT 'UTC',
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'suspended')),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Add comment describing the table
COMMENT ON TABLE organizations IS 'Stores client organization information with tenant isolation';

-- Add comments for important columns
COMMENT ON COLUMN organizations.organization_id IS 'Unique identifier (lowercase slug format)';
COMMENT ON COLUMN organizations.phone IS 'Contact phone in E.164 format';
COMMENT ON COLUMN organizations.business_hours IS 'Weekly business hours in JSON format';

-- ============================================================================
-- APPOINTMENTS TABLE
-- ============================================================================

-- Create the appointments table for storing booking information
CREATE TABLE IF NOT EXISTS appointments (
    id BIGSERIAL PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
    appointment_id TEXT NOT NULL UNIQUE,
    date DATE NOT NULL,
    time TIME NOT NULL,
    service_type TEXT NOT NULL,
    client_name TEXT NOT NULL CHECK (LENGTH(client_name) > 0),
    client_phone TEXT NOT NULL CHECK (client_phone ~ '^\+[1-9]\d{1,14}$'),
    client_email TEXT CHECK (client_email IS NULL OR client_email ~ '^[^@]+@[^@]+\.[^@]+$'),
    notes TEXT,
    status TEXT DEFAULT 'confirmed' CHECK (status IN ('confirmed', 'rescheduled', 'cancelled', 'completed', 'no-show')),
    cancellation_reason TEXT,
    cancelled_at TIMESTAMPTZ,
    rescheduling_reason TEXT,
    rescheduled_at TIMESTAMPTZ,
    previous_date DATE,
    previous_time TIME,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    CONSTRAINT unique_org_appointment UNIQUE (organization_id, appointment_id)
);

-- Add comment describing the table
COMMENT ON TABLE appointments IS 'Stores appointment bookings with full audit trail';

-- ============================================================================
-- AVAILABILITY SLOTS TABLE
-- ============================================================================

-- Create the availability_slots table for managing available time slots
CREATE TABLE IF NOT EXISTS availability_slots (
    id BIGSERIAL PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
    date DATE NOT NULL,
    time_slot TIME NOT NULL,
    duration_minutes INTEGER DEFAULT 60 CHECK (duration_minutes > 0),
    is_available BOOLEAN DEFAULT TRUE NOT NULL,
    appointment_id TEXT REFERENCES appointments(appointment_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    CONSTRAINT unique_org_slot UNIQUE (organization_id, date, time_slot)
);

-- Add comment describing the table
COMMENT ON TABLE availability_slots IS 'Manages available time slots for appointments';

-- ============================================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================================================

-- Enable Row Level Security on all tables
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE availability_slots ENABLE ROW LEVEL SECURITY;

-- Create RLS policy for organizations table
-- Policy: Users can only access their own organization's data
CREATE POLICY "org_isolation_policy"
ON organizations
FOR ALL
USING (organization_id = current_setting('app.current_org_id', true));

COMMENT ON POLICY "org_isolation_policy" ON organizations IS
'Tenant isolation: restricts access to organization''s own data';

-- Create RLS policy for appointments table
CREATE POLICY "appointments_isolation_policy"
ON appointments
FOR ALL
USING (organization_id = current_setting('app.current_org_id', true));

COMMENT ON POLICY "appointments_isolation_policy" ON appointments IS
'Tenant isolation: restricts access to organization''s appointments';

-- Create RLS policy for availability_slots table
CREATE POLICY "availability_isolation_policy"
ON availability_slots
FOR ALL
USING (organization_id = current_setting('app.current_org_id', true));

COMMENT ON POLICY "availability_isolation_policy" ON availability_slots IS
'Tenant isolation: restricts access to organization''s availability slots';

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- Organizations indexes
CREATE INDEX IF NOT EXISTS idx_organizations_status ON organizations(status);
CREATE INDEX IF NOT EXISTS idx_organizations_created_at ON organizations(created_at);

-- Appointments indexes
CREATE INDEX IF NOT EXISTS idx_appointments_org_id ON appointments(organization_id);
CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(date);
CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(status);
CREATE INDEX IF NOT EXISTS idx_appointments_client_phone ON appointments(client_phone);
CREATE INDEX IF NOT EXISTS idx_appointments_org_date ON appointments(organization_id, date);

-- Availability slots indexes
CREATE INDEX IF NOT EXISTS idx_availability_org_id ON availability_slots(organization_id);
CREATE INDEX IF NOT EXISTS idx_availability_date ON availability_slots(date);
CREATE INDEX IF NOT EXISTS idx_availability_available ON availability_slots(is_available);
CREATE INDEX IF NOT EXISTS idx_availability_org_date ON availability_slots(organization_id, date);
CREATE INDEX IF NOT EXISTS idx_availability_appointment ON availability_slots(appointment_id) WHERE appointment_id IS NOT NULL;

-- ============================================================================
-- UPDATED_AT TRIGGER FUNCTION
-- ============================================================================

-- Create function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for automatic updated_at updates
CREATE TRIGGER update_organizations_updated_at
    BEFORE UPDATE ON organizations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_appointments_updated_at
    BEFORE UPDATE ON appointments
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_availability_slots_updated_at
    BEFORE UPDATE ON availability_slots
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- ORGANIZATION RECORD INSERT TEMPLATE
-- ============================================================================
-- This section is populated by the Supabase agent during generation
-- Template variables: {{organization_id}}, {{display_name}}, {{phone}}, {{email}}, {{industry}}

-- INSERT INTO organizations (organization_id, display_name, phone, email, industry)
-- VALUES ('{{organization_id}}', '{{display_name}}', '{{phone}}', '{{email}}', '{{industry}}')
-- ON CONFLICT (organization_id) DO NOTHING;

-- ============================================================================
-- METADATA
-- ============================================================================

COMMENT ON SCHEMA public IS
'Schema version 1.0.0 - Ground truth template for Agent Forge client onboarding';
