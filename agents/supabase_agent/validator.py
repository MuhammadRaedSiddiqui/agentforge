"""
SQL artifact validator for Supabase migrations.

Validates generated SQL for:
- Destructive pattern detection
- Reference checking
- Policy dependency validation
- Foreign-client identifier detection
"""

import re
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """Result of validation check."""

    is_valid: bool
    errors: list[str]
    warnings: list[str] | None = None

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []


class SqlValidator:
    """Validator for SQL migration scripts."""

    DESTRUCTIVE_PATTERNS = [
        (r"\bDROP\s+TABLE\b", "DROP TABLE is destructive"),
        (r"\bDROP\s+DATABASE\b", "DROP DATABASE is destructive"),
        (r"\bTRUNCATE\b", "TRUNCATE is destructive"),
    ]

    def __init__(self) -> None:
        """Initialize the validator."""
        pass

    def validate_migration(self, sql: str, expected_org_id: str) -> ValidationResult:
        """
        Validate a SQL migration script.

        Args:
            sql: SQL script to validate
            expected_org_id: Expected organization identifier

        Returns:
            ValidationResult with validation status and any errors
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Check for destructive patterns
        destructive_errors = self._check_destructive_patterns(sql)
        errors.extend(destructive_errors)

        # Check for DELETE without WHERE
        delete_errors = self._check_delete_without_where(sql)
        errors.extend(delete_errors)

        # Validate RLS policies
        rls_errors = self._validate_rls_policies(sql)
        errors.extend(rls_errors)

        # Check for foreign organization IDs
        foreign_org_errors = self._check_foreign_org_ids(sql, expected_org_id)
        errors.extend(foreign_org_errors)

        # Check for unresolved placeholders
        placeholder_errors = self._check_placeholders(sql)
        errors.extend(placeholder_errors)

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

    def _check_destructive_patterns(self, sql: str) -> list[str]:
        """Check for destructive SQL patterns."""
        errors = []

        # Remove comments first
        sql_no_comments = re.sub(r"--[^\n]*", "", sql)

        for pattern, message in self.DESTRUCTIVE_PATTERNS:
            if re.search(pattern, sql_no_comments, re.IGNORECASE):
                errors.append(message)

        return errors

    def _check_delete_without_where(self, sql: str) -> list[str]:
        """Check for DELETE statements without WHERE clause."""
        errors = []

        # Remove comments
        sql_no_comments = re.sub(r"--[^\n]*", "", sql)

        # Pattern to match DELETE without WHERE
        # DELETE FROM table_name; or DELETE FROM table_name <end-of-string>
        pattern = r"\bDELETE\s+FROM\s+\w+\s*(?:;|$)"

        matches = re.finditer(pattern, sql_no_comments, re.IGNORECASE | re.MULTILINE)

        for match in matches:
            statement = match.group(0)
            # Check if WHERE clause exists
            if not re.search(r"\bWHERE\b", statement, re.IGNORECASE):
                errors.append(f"DELETE without WHERE clause detected: {statement.strip()[:50]}...")

        return errors

    def _validate_rls_policies(self, sql: str) -> list[str]:
        """Validate that RLS policies are properly configured."""
        errors = []
        sql_no_comments = re.sub(r"--[^\n]*", "", sql)

        # Check if there are INSERT operations
        has_insert = bool(re.search(r"\bINSERT\s+INTO\b", sql_no_comments, re.IGNORECASE))

        if has_insert:
            # Must have RLS enabled
            has_rls_enable = bool(
                re.search(r"ENABLE\s+ROW\s+LEVEL\s+SECURITY", sql_no_comments, re.IGNORECASE)
            )

            if not has_rls_enable:
                errors.append("RLS must be enabled before INSERT operations")

            # Must have CREATE POLICY
            has_policy = bool(re.search(r"CREATE\s+POLICY", sql_no_comments, re.IGNORECASE))

            if not has_policy:
                errors.append("RLS policy must be created before INSERT operations")

        # Check if policies are created before RLS is enabled
        policy_positions = [
            m.start() for m in re.finditer(r"CREATE\s+POLICY", sql_no_comments, re.IGNORECASE)
        ]
        rls_positions = [
            m.start()
            for m in re.finditer(r"ENABLE\s+ROW\s+LEVEL\s+SECURITY", sql_no_comments, re.IGNORECASE)
        ]

        for policy_pos in policy_positions:
            # Check if there's an ENABLE RLS before this policy
            rls_before = [pos for pos in rls_positions if pos < policy_pos]
            if not rls_before:
                errors.append("ENABLE ROW LEVEL SECURITY must come before CREATE POLICY")
                break

        return errors

    def _check_foreign_org_ids(self, sql: str, expected_org_id: str) -> list[str]:
        """Check for references to other organization IDs."""
        errors = []

        # Pattern to find organization_id values in INSERT/UPDATE statements
        # Match: VALUES (..., 'org_id', ...)
        # The organization ID is the first literal in the VALUES clause for
        # the generated organization inserts. Use a non-greedy match so later
        # values (for example an industry name) are not mistaken for an ID.
        value_pattern = r"VALUES\s*\([^)]*?'([a-z0-9_]+)'[^)]*\)"

        matches = re.finditer(value_pattern, sql, re.IGNORECASE)

        for match in matches:
            # Get the full context
            context_start = max(0, match.start() - 200)
            context_end = min(len(sql), match.end() + 100)
            context = sql[context_start:context_end]

            # Check if this is an organization_id value
            if "organization_id" in context.lower():
                org_id = match.group(1)
                # Skip placeholders
                if org_id != expected_org_id and "{{" not in org_id:
                    errors.append(f"Foreign organization ID detected: '{org_id}'")

        # Also check for hardcoded org IDs in WHERE clauses
        where_pattern = r"organization_id\s*=\s*'([a-z0-9_]+)'"
        where_matches = re.finditer(where_pattern, sql, re.IGNORECASE)

        for match in where_matches:
            org_id = match.group(1)
            if org_id != expected_org_id and "{{" not in org_id:
                errors.append(f"Foreign organization ID in WHERE clause: '{org_id}'")

        return errors

    def _check_placeholders(self, sql: str) -> list[str]:
        """Check for unresolved placeholders."""
        errors = []

        # Find all placeholders
        pattern = r"\{\{([^}]+)\}\}"
        matches = re.finditer(pattern, sql)

        unresolved = set()
        for match in matches:
            placeholder = match.group(1)
            # All placeholders in SQL should be resolved by the time of validation
            unresolved.add(placeholder)

        if unresolved:
            errors.append(f"Unresolved placeholders found: {', '.join(sorted(unresolved))}")

        return errors

    def validate_table_structure(self, sql: str) -> ValidationResult:
        """
        Validate table structure definitions.

        Args:
            sql: SQL script

        Returns:
            ValidationResult
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Extract CREATE TABLE statements
        create_table_pattern = r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\(([^;]+)\);"
        matches = re.finditer(create_table_pattern, sql, re.IGNORECASE | re.DOTALL)

        for match in matches:
            table_name = match.group(1)
            table_def = match.group(2)

            # Check for primary key
            if "PRIMARY KEY" not in table_def.upper():
                warnings.append(f"Table '{table_name}' has no primary key defined")

            # Check for created_at/updated_at timestamps
            if "created_at" not in table_def.lower():
                warnings.append(f"Table '{table_name}' missing created_at timestamp")

            # Check for organization_id in multi-tenant tables
            if table_name != "organizations" and "organization_id" not in table_def.lower():
                warnings.append(
                    f"Table '{table_name}' may need organization_id for tenant isolation"
                )

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

    def validate_indexes(self, sql: str) -> ValidationResult:
        """
        Validate index definitions.

        Args:
            sql: SQL script

        Returns:
            ValidationResult
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Find all CREATE INDEX statements
        index_pattern = r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+ON\s+(\w+)\s*\(([^)]+)\)"
        matches = re.finditer(index_pattern, sql, re.IGNORECASE)

        indexes = []
        for match in matches:
            indexes.append(
                {"name": match.group(1), "table": match.group(2), "columns": match.group(3)}
            )

        # Check for common performance indexes
        tables_in_sql = self._extract_table_names(sql)

        for table in tables_in_sql:
            if table == "organizations":
                continue

            # Check for organization_id index on multi-tenant tables
            has_org_index = any(
                idx["table"] == table and "organization_id" in idx["columns"] for idx in indexes
            )

            if not has_org_index:
                warnings.append(
                    f"Consider adding index on {table}(organization_id) for tenant isolation"
                )

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

    def _extract_table_names(self, sql: str) -> list[str]:
        """Extract all table names from SQL."""
        tables = set()

        # CREATE TABLE
        create_pattern = r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)"
        for match in re.finditer(create_pattern, sql, re.IGNORECASE):
            tables.add(match.group(1))

        return sorted(tables)
