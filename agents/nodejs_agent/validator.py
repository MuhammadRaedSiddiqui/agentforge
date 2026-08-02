"""
Node.js artifact validator for server diffs.

Validates generated Node.js diffs for:
- HMAC verification presence
- Embedded secret detection
- Unrelated change detection
- File hash matching
- Diff format validation
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


class NodeJsValidator:
    """Validator for Node.js server diffs."""

    SECRET_PATTERNS = [
        r"sk-[a-zA-Z0-9]{20,}",
        r"Bearer\s+[a-zA-Z0-9_\-]{20,}",
        r'(?:api[_-]?key|secret|token|password)\s*=\s*["\']([^"\']{10,})["\']',
    ]

    def __init__(self) -> None:
        """Initialize the validator."""
        pass

    def validate_diff(
        self, diff: str, expected_org_id: str, file_hash: str, actual_source_hash: str | None = None
    ) -> ValidationResult:
        """
        Validate a Node.js server diff.

        Args:
            diff: Unified diff content
            expected_org_id: Expected organization identifier
            file_hash: Expected source file hash
            actual_source_hash: Actual source file hash (if different from expected)

        Returns:
            ValidationResult with validation status and any errors
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Validate diff format
        if not self._validate_diff_format(diff):
            errors.append("Invalid unified diff format")

        # New webhook routes must be protected. A deletion-only diff does not
        # introduce a route and therefore has no new middleware to validate.
        if self._has_added_webhook_route(diff) and not self._check_hmac_verification(diff):
            errors.append("HMAC verification middleware not found in diff")

        # Check for embedded secrets
        secret_errors = self._check_secrets(diff)
        errors.extend(secret_errors)

        # Check for unrelated changes
        unrelated_errors = self._check_unrelated_changes(diff, expected_org_id)
        errors.extend(unrelated_errors)

        # Validate file hash if provided
        if actual_source_hash and file_hash != actual_source_hash:
            errors.append(
                f"File hash mismatch: expected {file_hash[:16]}..., got {actual_source_hash[:16]}..."
            )

        # Check for placeholders
        placeholder_errors = self._check_placeholders(diff)
        errors.extend(placeholder_errors)

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

    def _validate_diff_format(self, diff: str) -> bool:
        """Validate unified diff format."""
        if not diff.strip():
            return False

        lines = diff.split("\n")

        # Must have --- and +++ headers
        has_from = any(line.startswith("---") for line in lines)
        has_to = any(line.startswith("+++") for line in lines)

        # Must have @@ chunk headers
        has_chunk = any(line.startswith("@@") for line in lines)

        return has_from and has_to and has_chunk

    def _check_hmac_verification(self, diff: str) -> bool:
        """Check for HMAC verification in diff."""
        # Look for HMAC-related code patterns
        hmac_patterns = [
            r"verifyHmac",
            r"createHmac",
            r"hmac\.update",
            r"x-signature",
            r"WEBHOOK_SECRET",
        ]

        matches = sum(1 for pattern in hmac_patterns if re.search(pattern, diff, re.IGNORECASE))

        # A route may use an existing verifyHmac middleware, so its reference
        # is sufficient here. Full middleware implementations naturally match
        # several of the patterns above.
        return matches >= 1

    def _has_added_webhook_route(self, diff: str) -> bool:
        """Return whether the diff introduces a webhook route."""
        return any(
            line.startswith("+") and "/webhook/" in line and "app." in line
            for line in diff.splitlines()
        )

    def _check_secrets(self, diff: str) -> list[str]:
        """Check for embedded secrets in diff."""
        errors = []

        for pattern in self.SECRET_PATTERNS:
            matches = re.finditer(pattern, diff, re.IGNORECASE)
            for match in matches:
                # Check if this is in an added line
                context_start = max(0, match.start() - 100)
                context = diff[context_start : match.end()]

                # Only flag if it's an addition (has + prefix) and not an env var reference
                if "\n+" in context and "process.env" not in context:
                    errors.append(f"Secret pattern detected: {match.group(0)[:30]}...")

        return errors

    def _check_unrelated_changes(self, diff: str, expected_org_id: str) -> list[str]:
        """Check for changes unrelated to the target organization."""
        errors = []

        lines = diff.split("\n")

        for i, line in enumerate(lines):
            # Skip headers
            if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
                continue

            # Only check modified lines (+ or -)
            if not (line.startswith("+") or line.startswith("-")):
                continue

            # Skip comments
            if line.strip().startswith("//") or line.strip().startswith("/*"):
                continue

            # Check for organization ID references
            org_pattern = r"/webhook/([a-z0-9_]+)/"
            matches = re.finditer(org_pattern, line)

            for match in matches:
                found_org_id = match.group(1)
                if found_org_id != expected_org_id:
                    errors.append(
                        f"Line {i + 1}: References different organization '{found_org_id}'"
                    )

            # Check for global middleware changes (app.use without org context)
            if "app.use(" in line and expected_org_id not in line:
                if line.startswith("+") or line.startswith("-"):
                    errors.append(f"Line {i + 1}: Global middleware change detected")

            # Check for changes to routes not belonging to this org
            if re.search(r"app\.(post|get|put|delete)", line):
                if expected_org_id not in line and not line.strip().startswith("//"):
                    # It's a route change not for this org
                    if line.startswith("+") or line.startswith("-"):
                        errors.append(f"Line {i + 1}: Unrelated route modification")

        return errors

    def _check_placeholders(self, diff: str) -> list[str]:
        """Check for unresolved placeholders."""
        errors = []

        # Find placeholders in added lines only
        lines = diff.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("+") and "{{" in line:
                # Extract placeholder
                pattern = r"\{\{([^}]+)\}\}"
                matches = re.finditer(pattern, line)
                for match in matches:
                    placeholder = match.group(1)
                    # Allow certain runtime placeholders
                    if placeholder not in ["WEBHOOK_SECRET"]:
                        errors.append(f"Line {i + 1}: Unresolved placeholder '{{{{placeholder}}}}'")

        return errors

    def validate_route_additions(self, diff: str, expected_org_id: str) -> ValidationResult:
        """
        Validate that route additions follow conventions.

        Args:
            diff: Diff content
            expected_org_id: Expected organization identifier

        Returns:
            ValidationResult
        """
        errors = []
        warnings = []

        # Extract added routes
        added_routes = []
        lines = diff.split("\n")

        for line in lines:
            if line.startswith("+") and "app.post(" in line:
                # Extract route path
                match = re.search(r"app\.post\s*\(\s*['\"]([^'\"]+)['\"]", line)
                if match:
                    added_routes.append(match.group(1))

        # Validate route naming
        expected_prefix = f"/webhook/{expected_org_id}/"

        for route in added_routes:
            if not route.startswith(expected_prefix):
                errors.append(
                    f"Route '{route}' does not follow convention: expected prefix '{expected_prefix}'"
                )

            # Check endpoint name
            parts = route.split("/")
            if len(parts) >= 4:
                endpoint = parts[3]
                valid_endpoints = ["availability", "booking", "cancellation", "rescheduling"]
                if endpoint not in valid_endpoints:
                    warnings.append(f"Route '{route}' uses non-standard endpoint '{endpoint}'")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

    def validate_hmac_implementation(self, diff: str) -> ValidationResult:
        """
        Validate HMAC implementation details.

        Args:
            diff: Diff content

        Returns:
            ValidationResult
        """
        errors = []
        warnings = []

        content = diff

        # Check for proper HMAC function
        if "createHmac" in content:
            # Check algorithm
            if "sha256" not in content.lower():
                warnings.append("HMAC should use SHA-256 algorithm")

            # Check for signature header
            if "x-signature" not in content.lower():
                errors.append("HMAC verification should check x-signature header")

            # Check for error handling
            if "401" not in content and "Unauthorized" not in content:
                warnings.append("HMAC verification should return 401 on failure")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)
