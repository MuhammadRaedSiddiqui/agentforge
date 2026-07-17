-- Migration: 014_audit_event_compatibility.sql
-- Support deployment-level audit writes that occur outside a CLI session.

ALTER TABLE audit_events
    ALTER COLUMN session_id DROP NOT NULL;

ALTER TABLE audit_events
    ADD COLUMN IF NOT EXISTS subject TEXT;
