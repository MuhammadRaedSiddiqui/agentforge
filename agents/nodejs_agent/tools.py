"""
Tools for Node.js agent operations.

Provides utilities for:
- Diff generation
- Route extraction
- HMAC verification checking
"""

import difflib
import re


def generate_diff(current_content: str, new_routes: str, organization_id: str) -> str:
    """
    Generate unified diff for adding new routes to server.js.

    Args:
        current_content: Current server.js content
        new_routes: New route handlers to add
        organization_id: Organization identifier

    Returns:
        Unified diff string
    """
    # Find insertion point (after existing routes, before health check or at end)
    lines = current_content.split("\n")

    # Find the best insertion point
    insertion_index = _find_insertion_point(lines, organization_id)

    # Split new routes into lines
    new_route_lines = new_routes.split("\n")

    # Create modified content
    modified_lines = lines[:insertion_index] + new_route_lines + lines[insertion_index:]
    modified_content = "\n".join(modified_lines)

    # Generate unified diff
    diff = difflib.unified_diff(
        current_content.splitlines(),
        modified_content.splitlines(),
        fromfile="server.js",
        tofile="server.js",
        lineterm="\n",
    )

    return "".join(diff)


def _find_insertion_point(lines: list[str], organization_id: str) -> int:
    """
    Find the best insertion point for new routes.

    Args:
        lines: Lines of current server.js
        organization_id: Organization identifier

    Returns:
        Line index for insertion
    """
    # Strategy: Insert after last app.post/app.get but before health check or module.exports

    last_route_index = -1
    health_check_index = -1
    exports_index = -1

    for i, line in enumerate(lines):
        if re.search(r"app\.(post|get|put|delete|patch)\s*\(", line):
            last_route_index = i
        if "health" in line.lower() and "app.get" in line:
            health_check_index = i
        if "module.exports" in line or "export default" in line:
            exports_index = i

    # Insert after last route but before health check
    if health_check_index > 0:
        return health_check_index
    elif last_route_index > 0:
        return last_route_index + 1
    elif exports_index > 0:
        return exports_index
    else:
        # Insert near end if no clear insertion point
        return len(lines) - 5 if len(lines) > 5 else len(lines)


def extract_routes(server_content: str) -> list[dict[str, str]]:
    """
    Extract all route definitions from server.js.

    Args:
        server_content: Content of server.js

    Returns:
        List of route definitions with method, path, handler
    """
    routes = []

    # Pattern to match route definitions
    # Matches: app.post('/path', handler, ...)
    pattern = r"app\.(post|get|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]"

    matches = re.finditer(pattern, server_content)

    for match in matches:
        method = match.group(1).upper()
        path = match.group(2)

        # Extract handler name if possible
        handler_pattern = f"{re.escape(match.group(0))}[^)]*"
        handler_match = re.search(handler_pattern, server_content)
        handler = handler_match.group(0) if handler_match else ""

        routes.append({"method": method, "path": path, "handler": handler})

    return routes


def verify_hmac_presence(content: str) -> bool:
    """
    Check if HMAC verification is present in the content.

    Args:
        content: Code or diff content to check

    Returns:
        True if HMAC verification found
    """
    # Look for HMAC verification patterns
    hmac_patterns = [
        r"verifyHmac",
        r"createHmac",
        r"hmac\.update",
        r"x-signature",
        r"WEBHOOK_SECRET",
    ]

    # Must have at least 2 patterns to consider it a proper HMAC implementation
    matches = sum(1 for pattern in hmac_patterns if re.search(pattern, content, re.IGNORECASE))

    return matches >= 2


def extract_organization_routes(server_content: str, organization_id: str) -> list[str]:
    """
    Extract routes specific to an organization.

    Args:
        server_content: Content of server.js
        organization_id: Organization identifier

    Returns:
        List of route paths for this organization
    """
    routes = extract_routes(server_content)

    org_routes = [route["path"] for route in routes if organization_id in route["path"]]

    return org_routes


def detect_unrelated_changes(diff: str, organization_id: str) -> list[str]:
    """
    Detect changes to routes or code unrelated to the target organization.

    Args:
        diff: Unified diff content
        organization_id: Target organization identifier

    Returns:
        List of unrelated changes detected
    """
    unrelated = []

    # Parse diff to extract changed lines
    lines = diff.split("\n")

    for i, line in enumerate(lines):
        # Skip diff headers
        if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
            continue

        # Look for changes (lines starting with + or -)
        if line.startswith("+") or line.startswith("-"):
            # Check if this line references a different organization
            # Extract potential org IDs (common patterns)
            org_pattern = r"/webhook/([a-z0-9_]+)/"
            matches = re.finditer(org_pattern, line)

            for match in matches:
                found_org_id = match.group(1)
                if found_org_id != organization_id:
                    unrelated.append(
                        f"Line {i + 1}: References different organization '{found_org_id}'"
                    )

            # Check for global middleware changes
            if "app.use(" in line and organization_id not in line:
                unrelated.append(f"Line {i + 1}: Global middleware change detected")

            # Check for changes to other routes
            if (
                ("app.post(" in line or "app.get(" in line)
                and organization_id not in line
                and not line.strip().startswith("//")
            ):
                unrelated.append(f"Line {i + 1}: Change to unrelated route")

    return unrelated


def validate_no_hardcoded_secrets(content: str) -> list[str]:
    """
    Check for hardcoded secrets in content.

    Args:
        content: Code content to check

    Returns:
        List of detected secret patterns
    """
    secrets_found = []

    # Patterns that indicate hardcoded secrets
    secret_patterns = [
        (r'(?:api[_-]?key|apikey)\s*=\s*["\']([^"\']{10,})["\']', "API key"),
        (r'(?:secret|password|token)\s*=\s*["\']([^"\']{10,})["\']', "Secret/password"),
        (r"Bearer\s+([a-zA-Z0-9_\-]{20,})", "Bearer token"),
        (r"sk-[a-zA-Z0-9]{20,}", "OpenAI-style key"),
        (r'(?:aws|s3)[_-](?:access|secret)[_-]key["\']?\s*[:=]\s*["\']([^"\']+)', "AWS key"),
    ]

    for pattern, description in secret_patterns:
        matches = re.finditer(pattern, content, re.IGNORECASE)
        for match in matches:
            # Exclude environment variable references
            context = content[max(0, match.start() - 50) : match.end() + 50]
            if (
                "process.env" not in context
                and "process.env" not in content[max(0, match.start() - 100) : match.start()]
            ):
                secrets_found.append(f"{description} detected: {match.group(0)[:30]}...")

    return secrets_found


def compute_file_hash(content: str) -> str:
    """
    Compute SHA-256 hash of file content.

    Args:
        content: File content

    Returns:
        Hexadecimal hash string
    """
    import hashlib

    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def parse_diff_stats(diff: str) -> dict[str, int]:
    """
    Parse diff to extract statistics.

    Args:
        diff: Unified diff content

    Returns:
        Dictionary with additions, deletions, and affected files
    """
    lines = diff.split("\n")

    additions = 0
    deletions = 0
    files = set()

    for line in lines:
        if line.startswith("+++"):
            # Extract filename
            match = re.search(r"\+\+\+ (.+?)(?:\t|$)", line)
            if match:
                files.add(match.group(1))
        elif line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1

    return {
        "additions": additions,
        "deletions": deletions,
        "files_changed": len(files),
        "net_change": additions - deletions,
    }


def validate_diff_format(diff: str) -> bool:
    """
    Validate that content is a proper unified diff format.

    Args:
        diff: Content to validate

    Returns:
        True if valid unified diff format
    """
    if not diff.strip():
        return False

    lines = diff.split("\n")

    # Must have --- and +++ headers
    has_from_header = any(line.startswith("---") for line in lines)
    has_to_header = any(line.startswith("+++") for line in lines)

    # Must have @@ chunk headers
    has_chunk_header = any(line.startswith("@@") for line in lines)

    return has_from_header and has_to_header and has_chunk_header


def extract_added_routes(diff: str) -> list[str]:
    """
    Extract route paths that are being added in the diff.

    Args:
        diff: Unified diff content

    Returns:
        List of added route paths
    """
    added_routes = []

    lines = diff.split("\n")

    for line in lines:
        # Look for added lines with route definitions
        if line.startswith("+") and not line.startswith("+++"):
            # Extract route path
            route_match = re.search(r"app\.\w+\s*\(\s*['\"]([^'\"]+)['\"]", line)
            if route_match:
                added_routes.append(route_match.group(1))

    return added_routes


def validate_route_naming_convention(routes: list[str], organization_id: str) -> list[str]:
    """
    Validate that routes follow naming conventions.

    Args:
        routes: List of route paths
        organization_id: Expected organization identifier

    Returns:
        List of validation errors
    """
    errors = []

    expected_prefix = f"/webhook/{organization_id}/"

    for route in routes:
        if not route.startswith(expected_prefix):
            errors.append(
                f"Route '{route}' does not follow convention: expected prefix '{expected_prefix}'"
            )

        # Check for valid endpoint name after org ID
        parts = route.split("/")
        if len(parts) >= 4:
            endpoint = parts[3]
            valid_endpoints = ["availability", "booking", "cancellation", "rescheduling"]
            if endpoint not in valid_endpoints:
                errors.append(f"Route '{route}' uses non-standard endpoint '{endpoint}'")

    return errors
