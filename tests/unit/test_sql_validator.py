"""
Unit tests for SQL migration validator.

Tests cover:
- Destructive pattern detection (DROP, TRUNCATE, DELETE without WHERE)
- Policy dependency validation
- Foreign-client identifier detection
- Required RLS policy presence
- Safe migration patterns
"""

import pytest

from agents.supabase_agent.validator import SqlValidator

pytestmark = pytest.mark.unit


class TestSqlMigrationValidator:
    """Test suite for SQL migration validation."""

    def test_valid_migration(self) -> None:
        """Test that a valid SQL migration passes validation."""
        sql = """
        -- Create organization table
        CREATE TABLE IF NOT EXISTS organizations (
            organization_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        -- Create RLS policy
        ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;

        CREATE POLICY "org_isolation_policy"
        ON organizations
        FOR ALL
        USING (organization_id = current_setting('app.current_org_id', true));
        """

        validator = SqlValidator()
        result = validator.validate_migration(sql, expected_org_id="test_org")

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_destructive_drop_table_detected(self) -> None:
        """Test that DROP TABLE is detected as destructive."""
        sql = """
        DROP TABLE organizations;
        """

        validator = SqlValidator()
        result = validator.validate_migration(sql, expected_org_id="test_org")

        assert result.is_valid is False
        assert any(
            "drop" in error.lower() and "destructive" in error.lower() for error in result.errors
        )

    def test_destructive_truncate_detected(self) -> None:
        """Test that TRUNCATE is detected as destructive."""
        sql = """
        TRUNCATE TABLE organizations;
        """

        validator = SqlValidator()
        result = validator.validate_migration(sql, expected_org_id="test_org")

        assert result.is_valid is False
        assert any(
            "truncate" in error.lower() and "destructive" in error.lower()
            for error in result.errors
        )

    def test_delete_without_where_detected(self) -> None:
        """Test that DELETE without WHERE clause is detected."""
        sql = """
        DELETE FROM organizations;
        """

        validator = SqlValidator()
        result = validator.validate_migration(sql, expected_org_id="test_org")

        assert result.is_valid is False
        assert any(
            "delete" in error.lower() and "where" in error.lower() for error in result.errors
        )

    def test_delete_with_where_allowed(self) -> None:
        """Test that DELETE with WHERE clause is allowed."""
        sql = """
        DELETE FROM organizations WHERE organization_id = 'test_org';
        """

        validator = SqlValidator()
        result = validator.validate_migration(sql, expected_org_id="test_org")

        # Should not trigger destructive delete error
        destructive_errors = [
            e for e in result.errors if "delete" in e.lower() and "where" in e.lower()
        ]
        assert len(destructive_errors) == 0

    def test_foreign_client_identifier_detected(self) -> None:
        """Test that foreign organization identifiers are detected."""
        sql = """
        INSERT INTO organizations (organization_id, display_name)
        VALUES ('other_client_org', 'Other Client');
        """

        validator = SqlValidator()
        result = validator.validate_migration(sql, expected_org_id="test_org")

        assert result.is_valid is False
        assert any(
            "foreign" in error.lower() or "cross-client" in error.lower() for error in result.errors
        )

    def test_correct_organization_id_passes(self) -> None:
        """Test that correct organization ID passes validation."""
        sql = """
        INSERT INTO organizations (organization_id, display_name)
        VALUES ('test_org', 'Test Organization');
        """

        validator = SqlValidator()
        result = validator.validate_migration(sql, expected_org_id="test_org")

        # Should not trigger foreign client error
        foreign_errors = [
            e for e in result.errors if "foreign" in e.lower() or "cross-client" in e.lower()
        ]
        assert len(foreign_errors) == 0

    def test_rls_policy_dependency_validation(self) -> None:
        """Test that RLS policy is checked before INSERT operations."""
        sql = """
        -- Missing: ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
        -- Missing: CREATE POLICY

        INSERT INTO organizations (organization_id, display_name)
        VALUES ('test_org', 'Test Organization');
        """

        validator = SqlValidator()
        result = validator.validate_migration(sql, expected_org_id="test_org")

        assert result.is_valid is False
        assert any("rls" in error.lower() or "policy" in error.lower() for error in result.errors)

    def test_rls_enabled_before_policy_creation(self) -> None:
        """Test that RLS is enabled before creating policies."""
        sql = """
        CREATE TABLE organizations (
            organization_id TEXT PRIMARY KEY
        );

        -- RLS not enabled before policy creation
        CREATE POLICY "org_policy"
        ON organizations
        FOR ALL
        USING (organization_id = current_setting('app.current_org_id', true));
        """

        validator = SqlValidator()
        result = validator.validate_migration(sql, expected_org_id="test_org")

        assert result.is_valid is False
        assert any("enable row level security" in error.lower() for error in result.errors)

    def test_complete_safe_migration(self) -> None:
        """Test that a complete safe migration passes all checks."""
        sql = """
        -- Create table
        CREATE TABLE IF NOT EXISTS organizations (
            organization_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            industry TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );

        -- Enable RLS
        ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;

        -- Create isolation policy
        CREATE POLICY "org_isolation_policy"
        ON organizations
        FOR ALL
        USING (organization_id = current_setting('app.current_org_id', true));

        -- Insert organization record
        INSERT INTO organizations (organization_id, display_name, phone, email, industry)
        VALUES ('test_org', 'Test Organization', '+1234567890', 'test@example.com', 'technology')
        ON CONFLICT (organization_id) DO NOTHING;

        -- Create index
        CREATE INDEX IF NOT EXISTS idx_organizations_created_at ON organizations(created_at);
        """

        validator = SqlValidator()
        result = validator.validate_migration(sql, expected_org_id="test_org")

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_sql_injection_patterns_detected(self) -> None:
        """Test that potential SQL injection patterns are flagged."""
        sql = """
        INSERT INTO organizations (organization_id, display_name)
        VALUES ('test_org', 'Test'); DROP TABLE users; --');
        """

        validator = SqlValidator()
        result = validator.validate_migration(sql, expected_org_id="test_org")

        assert result.is_valid is False
        assert any("drop" in error.lower() for error in result.errors)

    def test_multiple_organization_ids_detected(self) -> None:
        """Test that multiple different organization IDs are detected."""
        sql = """
        INSERT INTO organizations (organization_id, display_name)
        VALUES ('test_org', 'Test Org');

        INSERT INTO organizations (organization_id, display_name)
        VALUES ('another_org', 'Another Org');
        """

        validator = SqlValidator()
        result = validator.validate_migration(sql, expected_org_id="test_org")

        assert result.is_valid is False
        assert any(
            "foreign" in error.lower() or "another_org" in error.lower() for error in result.errors
        )

    def test_placeholder_detection(self) -> None:
        """Test that unresolved placeholders are detected."""
        sql = """
        INSERT INTO organizations (organization_id, display_name)
        VALUES ('{{ORG_ID}}', '{{ORG_NAME}}');
        """

        validator = SqlValidator()
        result = validator.validate_migration(sql, expected_org_id="test_org")

        assert result.is_valid is False
        assert any("placeholder" in error.lower() for error in result.errors)
