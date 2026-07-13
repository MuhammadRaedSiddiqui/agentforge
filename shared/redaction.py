"""
Secret redaction utilities for Agent Forge.

Scans content for secret patterns and masks them before logging,
displaying, or persisting.
"""

import re
from typing import Any, Dict, List, Optional, Union


# Secret patterns to detect
SECRET_PATTERNS = [
    # API keys (match 10+ chars to catch most real keys)
    (r"sk-[a-zA-Z0-9]{10,}", "sk-***"),
    (r"pk-[a-zA-Z0-9]{10,}", "pk-***"),
    (r"Bearer\s+[a-zA-Z0-9\-._~+/]+=*", "Bearer ***"),

    # Generic API keys and tokens (match 10+ chars)
    (r"api[_-]?key['\"]?\s*[:=]\s*['\"]?([a-zA-Z0-9\-._~+/]{10,})['\"]?", "api_key=***"),
    (r"token['\"]?\s*[:=]\s*['\"]?([a-zA-Z0-9\-._~+/]{10,})['\"]?", "token=***"),
    (r"secret['\"]?\s*[:=]\s*['\"]?([a-zA-Z0-9\-._~+/]{10,})['\"]?", "secret=***"),
    (r"password['\"]?\s*[:=]\s*['\"]?([^\s'\"]{8,})['\"]?", "password=***"),

    # Authorization headers
    (r"Authorization:\s*[^\r\n]+", "Authorization: ***"),

    # AWS-style keys
    (r"AKIA[0-9A-Z]{16}", "AKIA***"),
    (r"(?:aws_access_key_id|aws_secret_access_key)['\"]?\s*[:=]\s*['\"]?([a-zA-Z0-9/+=]{20,})['\"]?", "aws_***=***"),

    # Google API keys
    (r"AIza[0-9A-Za-z\-_]{35}", "AIza***"),

    # Supabase keys (service role keys are especially sensitive)
    (r"eyJ[a-zA-Z0-9\-_]+\.eyJ[a-zA-Z0-9\-_]+\.[a-zA-Z0-9\-_]+", "eyJ***"),

    # Generic base64 encoded secrets (20+ chars)
    (r"['\"]([A-Za-z0-9+/]{40,}={0,2})['\"]", "***"),
]


def scan_for_secrets(content: str) -> List[Dict[str, Any]]:
    """
    Scan content for potential secrets.

    Args:
        content: Text content to scan

    Returns:
        List of findings with pattern, match, and position information
    """
    findings = []

    for pattern, _replacement in SECRET_PATTERNS:
        matches = re.finditer(pattern, content, re.IGNORECASE)
        for match in matches:
            findings.append({
                "pattern": pattern,
                "matched_text": match.group(0),
                "start": match.start(),
                "end": match.end(),
                "line": content[:match.start()].count("\n") + 1,
            })

    return findings


def redact_secrets(content: str) -> str:
    """
    Redact secrets from content.

    Args:
        content: Text content to redact

    Returns:
        Content with secrets replaced by masked placeholders
    """
    redacted = content

    for pattern, replacement in SECRET_PATTERNS:
        redacted = re.sub(pattern, replacement, redacted, flags=re.IGNORECASE)

    return redacted


def redact_dict(data: Dict[str, Any], sensitive_keys: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Redact sensitive values from a dictionary.

    Args:
        data: Dictionary to redact
        sensitive_keys: Additional keys to treat as sensitive (case-insensitive)

    Returns:
        New dictionary with sensitive values redacted
    """
    if sensitive_keys is None:
        sensitive_keys = []

    # Default sensitive key patterns
    default_sensitive = [
        "api_key", "apikey", "api-key",
        "secret", "token", "password", "passwd",
        "authorization", "auth",
        "key", "private_key", "privatekey",
        "credential", "credentials",
        "service_role_key", "anon_key",
    ]

    all_sensitive = set(k.lower() for k in default_sensitive + sensitive_keys)

    redacted = {}
    for key, value in data.items():
        key_lower = key.lower()

        # Check if this key should be redacted
        if any(sensitive in key_lower for sensitive in all_sensitive):
            if isinstance(value, str) and value:
                # Show first 4 chars if long enough
                redacted[key] = f"{value[:4]}***" if len(value) > 4 else "***"
            else:
                redacted[key] = "***"
        elif isinstance(value, dict):
            # Recursively redact nested dictionaries
            redacted[key] = redact_dict(value, sensitive_keys)
        elif isinstance(value, list):
            # Redact list items if they're dictionaries
            redacted[key] = [
                redact_dict(item, sensitive_keys) if isinstance(item, dict) else item
                for item in value
            ]
        elif isinstance(value, str):
            # Scan string values for secret patterns
            redacted[key] = redact_secrets(value)
        else:
            redacted[key] = value

    return redacted


def mask_value(value: str, visible_chars: int = 4) -> str:
    """
    Mask a value, showing only the first few characters.

    Args:
        value: Value to mask
        visible_chars: Number of characters to keep visible

    Returns:
        Masked string like "abcd***"
    """
    if not value or len(value) <= visible_chars:
        return "***"

    return f"{value[:visible_chars]}***"


def validate_no_secrets(content: Union[str, Dict[str, Any]]) -> bool:
    """
    Validate that content contains no detectable secrets.

    Args:
        content: Content to validate (string or dictionary)

    Returns:
        True if no secrets detected, False otherwise
    """
    if isinstance(content, dict):
        # Convert dict to JSON string for scanning
        import json
        content_str = json.dumps(content, indent=2)
    else:
        content_str = content

    findings = scan_for_secrets(content_str)
    return len(findings) == 0


def sanitize_error_message(error: Exception) -> str:
    """
    Sanitize an error message, removing any potential secrets.

    Args:
        error: Exception to sanitize

    Returns:
        Sanitized error message safe for logging and display
    """
    error_str = str(error)
    return redact_secrets(error_str)


def sanitize_url(url: str) -> str:
    """
    Sanitize a URL, removing any embedded credentials.

    Args:
        url: URL to sanitize

    Returns:
        URL with credentials removed
    """
    # Remove basic auth credentials from URLs
    # https://user:pass@example.com -> https://***@example.com
    sanitized = re.sub(
        r"(https?://)([^:]+):([^@]+)@",
        r"\1***:***@",
        url
    )

    # Remove query string parameters that look like secrets
    sanitized = re.sub(
        r"([?&])(api_?key|token|secret|password|key)=[^&]+",
        r"\1\2=***",
        sanitized,
        flags=re.IGNORECASE
    )

    return sanitized


def create_redacted_summary(content: str, max_length: int = 200) -> str:
    """
    Create a redacted summary of content suitable for logging.

    Args:
        content: Content to summarize
        max_length: Maximum length of summary

    Returns:
        Redacted and truncated summary
    """
    # First redact secrets
    redacted = redact_secrets(content)

    # Then truncate if needed
    if len(redacted) > max_length:
        return redacted[:max_length] + "..."

    return redacted
