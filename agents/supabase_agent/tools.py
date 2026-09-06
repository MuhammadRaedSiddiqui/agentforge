"""
Tools for Supabase agent operations.

Provides utilities for:
- SQL generation
- Policy template verification
- Isolation checking
"""

import re
from typing import Any


class GenerateSql:
    """SQL generation utilities."""

    @staticmethod
    def generate_org_insert(
        organization_id: str,
        display_name: str,
        phone: str | None = None,
        email: str | None = None,
        industry: str | None = None,
    ) -> str:
        """
        Generate organization INSERT statement.

        Args:
            organization_id: Organization identifier
            display_name: Organization display name
            phone: Contact phone (optional)
            email: Contact email (optional)
            industry: Industry type (optional)

        Returns:
            SQL INSERT statement
        """
        # Build column list and values
        columns = ["organization_id", "display_name"]
        values = [
            f"'{GenerateSql._escape_sql(organization_id)}'",
            f"'{GenerateSql._escape_sql(display_name)}'",
        ]

        if phone:
            columns.append("phone")
            values.append(f"'{GenerateSql._escape_sql(phone)}'")

        if email:
            columns.append("email")
            values.append(f"'{GenerateSql._escape_sql(email)}'")

        if industry:
            columns.append("industry")
            values.append(f"'{GenerateSql._escape_sql(industry)}'")

        columns_str = ", ".join(columns)
        values_str = ", ".join(values)

        sql = f"""-- Insert organization record
INSERT INTO organizations ({columns_str})
VALUES ({values_str})
ON CONFLICT (organization_id) DO NOTHING;
"""
        return sql

    @staticmethod
    def _escape_sql(value: str) -> str:
        """
        Escape single quotes in SQL string values.

        Args:
            value: String to escape

        Returns:
            Escaped string
        """
        if not value:
            return ""
        return value.replace("'", "''")


class GeneratePolicyTemplate:
    """Policy template utilities."""

    @staticmethod
    def verify_rls_policies(sql: str) -> bool:
        """
        Verify that SQL contains required RLS policies.

        Args:
            sql: SQL script to check

        Returns:
            True if all required policies are present
        """
        required_checks = [
            "ENABLE ROW LEVEL SECURITY",
            "CREATE POLICY",
            "organization_id = current_setting('app.current_org_id'",
        ]

        return all(check in sql for check in required_checks)

    @staticmethod
    def extract_policies(sql: str) -> list[dict[str, str]]:
        """
        Extract all CREATE POLICY statements from SQL.

        Args:
            sql: SQL script

        Returns:
            List of policy definitions
        """
        policies = []

        # Pattern to match CREATE POLICY statements
        pattern = r'CREATE POLICY\s+"([^"]+)"\s+ON\s+(\w+)\s+FOR\s+(\w+)\s+USING\s*\(([^;]+)\)'
        matches = re.finditer(pattern, sql, re.IGNORECASE | re.DOTALL)

        for match in matches:
            policies.append(
                {
                    "name": match.group(1),
                    "table": match.group(2),
                    "for_operation": match.group(3),
                    "using_clause": match.group(4).strip(),
                }
            )

        return policies

    @staticmethod
    def validate_policy_isolation(policy: dict[str, str]) -> bool:
        """
        Validate that a policy enforces organization isolation.

        Args:
            policy: Policy definition

        Returns:
            True if policy enforces isolation
        """
        using_clause = policy.get("using_clause", "").lower()

        # Check for organization_id filtering
        isolation_patterns = [
            "organization_id = current_setting('app.current_org_id'",
            'organization_id = current_setting("app.current_org_id"',
        ]

        return any(pattern.lower() in using_clause for pattern in isolation_patterns)


def check_isolation(sql: str, expected_org_id: str) -> dict[str, Any]:
    """
    Check that SQL enforces proper tenant isolation.

    Args:
        sql: SQL script to check
        expected_org_id: Expected organization identifier

    Returns:
        Dictionary with isolation check results
    """
    issues = []

    # Check 1: RLS must be enabled
    if "ENABLE ROW LEVEL SECURITY" not in sql:
        issues.append("Row Level Security (RLS) not enabled on tables")

    # Check 2: Policies must exist
    policies = GeneratePolicyTemplate.extract_policies(sql)
    if not policies:
        issues.append("No RLS policies defined")

    # Check 3: Each policy must enforce isolation
    for policy in policies:
        if not GeneratePolicyTemplate.validate_policy_isolation(policy):
            issues.append(f"Policy '{policy['name']}' does not enforce organization isolation")

    # Check 4: All organization_id references should match expected ID
    # Look for INSERT statements with organization_id column and check the corresponding value
    insert_pattern = r"INSERT\s+INTO\s+\w+\s*\(((?:[^)]+))\)\s*VALUES\s*\(((?:[^)]+))\)"
    matches = re.finditer(insert_pattern, sql, re.IGNORECASE | re.DOTALL)

    for match in matches:
        columns_str = match.group(1)
        values_str = match.group(2)

        # Parse column names and values
        columns = [col.strip() for col in columns_str.split(",")]

        # Find organization_id column index
        org_id_col_index = None
        for i, col in enumerate(columns):
            if "organization_id" in col.lower():
                org_id_col_index = i
                break

        if org_id_col_index is not None:
            # Extract the corresponding value
            # Simple regex to extract string literals
            value_pattern = r"'([^']*)'"
            values = re.findall(value_pattern, values_str)

            if org_id_col_index < len(values):
                org_id_value = values[org_id_col_index]
                if org_id_value != expected_org_id and "{{" not in org_id_value:
                    issues.append(f"Foreign organization ID found: {org_id_value}")

    return {"is_isolated": len(issues) == 0, "issues": issues, "policies_found": len(policies)}


def validate_sql_syntax(sql: str) -> dict[str, Any]:
    """
    Perform basic SQL syntax validation.

    Args:
        sql: SQL script to validate

    Returns:
        Dictionary with validation results
    """
    errors = []

    # Check for common syntax errors
    lines = sql.split("\n")

    # Track open/close balance
    paren_balance = 0
    in_string = False
    string_char = None

    for line_num, line in enumerate(lines, 1):
        # Skip comments
        if line.strip().startswith("--"):
            continue

        for char in line:
            if char in ('"', "'") and not in_string:
                in_string = True
                string_char = char
            elif char == string_char and in_string:
                in_string = False
                string_char = None
            elif not in_string:
                if char == "(":
                    paren_balance += 1
                elif char == ")":
                    paren_balance -= 1

        if paren_balance < 0:
            errors.append(f"Line {line_num}: Unbalanced parentheses (too many closing)")

    if paren_balance != 0:
        errors.append(f"Unbalanced parentheses: {paren_balance} unclosed")

    # Check for unterminated statements (missing semicolons at critical points)
    sql_upper = sql.upper()
    statement_keywords = ["CREATE TABLE", "INSERT INTO", "CREATE POLICY", "ALTER TABLE"]

    for keyword in statement_keywords:
        if keyword in sql_upper:
            # Find the keyword and check if there's a semicolon before the next statement
            pattern = f"{keyword}[^;]*?(?:CREATE|INSERT|ALTER|$)"
            matches = re.finditer(pattern, sql_upper, re.DOTALL)
            for match in matches:
                if ";" not in match.group(0) and not match.group(0).strip().endswith("$"):
                    errors.append(f"Possible missing semicolon after {keyword} statement")

    return {"is_valid": len(errors) == 0, "errors": errors}


def detect_destructive_patterns(sql: str) -> list[str]:
    """
    Detect potentially destructive SQL patterns.

    Args:
        sql: SQL script to check

    Returns:
        List of destructive patterns found
    """
    destructive = []

    # Remove comments first
    sql_no_comments = re.sub(r"--[^\n]*", "", sql)

    # Check for DROP statements
    if re.search(r"\bDROP\s+TABLE\b", sql_no_comments, re.IGNORECASE):
        destructive.append("DROP TABLE detected")

    if re.search(r"\bDROP\s+DATABASE\b", sql_no_comments, re.IGNORECASE):
        destructive.append("DROP DATABASE detected")

    # Check for TRUNCATE
    if re.search(r"\bTRUNCATE\b", sql_no_comments, re.IGNORECASE):
        destructive.append("TRUNCATE detected")

    # Check for DELETE without WHERE
    delete_pattern = r"\bDELETE\s+FROM\s+\w+\s*(?:;|$)"
    if re.search(delete_pattern, sql_no_comments, re.IGNORECASE):
        destructive.append("DELETE without WHERE clause detected")

    # Check for UPDATE without WHERE
    update_pattern = r"\bUPDATE\s+\w+\s+SET\s+[^;]*?(?:;|$)"
    matches = re.finditer(update_pattern, sql_no_comments, re.IGNORECASE | re.DOTALL)
    for match in matches:
        if "WHERE" not in match.group(0).upper():
            destructive.append("UPDATE without WHERE clause detected")

    return destructive


def extract_table_names(sql: str) -> list[str]:
    """
    Extract all table names referenced in SQL.

    Args:
        sql: SQL script

    Returns:
        List of table names
    """
    tables = set()

    # CREATE TABLE
    create_pattern = r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)"
    for match in re.finditer(create_pattern, sql, re.IGNORECASE):
        tables.add(match.group(1))

    # INSERT INTO
    insert_pattern = r"INSERT\s+INTO\s+(\w+)"
    for match in re.finditer(insert_pattern, sql, re.IGNORECASE):
        tables.add(match.group(1))

    # UPDATE
    update_pattern = r"UPDATE\s+(\w+)"
    for match in re.finditer(update_pattern, sql, re.IGNORECASE):
        tables.add(match.group(1))

    # FROM clause
    from_pattern = r"FROM\s+(\w+)"
    for match in re.finditer(from_pattern, sql, re.IGNORECASE):
        tables.add(match.group(1))

    # ON clause (for policies)
    on_pattern = r"ON\s+(\w+)\s+FOR"
    for match in re.finditer(on_pattern, sql, re.IGNORECASE):
        tables.add(match.group(1))

    return sorted(tables)


# Export utility instances
generate_sql = GenerateSql()
generate_policy_template = GeneratePolicyTemplate()
