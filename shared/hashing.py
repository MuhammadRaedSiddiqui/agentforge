"""
SHA-256 content hashing with canonical serialization for Agent Forge.

Provides deterministic hashing for artifacts, proposals, and audit chains.
"""

import hashlib
import json
from typing import Any


def hash_content(content: str | bytes) -> str:
    """
    Compute SHA-256 hash of content.

    Args:
        content: String or bytes to hash

    Returns:
        Hex-encoded SHA-256 hash (64 characters)
    """
    content_bytes = content.encode("utf-8") if isinstance(content, str) else content

    return hashlib.sha256(content_bytes).hexdigest()


def hash_json(data: dict[str, Any]) -> str:
    """
    Compute SHA-256 hash of JSON data with canonical serialization.

    Uses sorted keys and consistent formatting to ensure deterministic hashing.

    Args:
        data: Dictionary to hash

    Returns:
        Hex-encoded SHA-256 hash of canonicalized JSON
    """
    # Serialize with sorted keys, no whitespace, consistent formatting
    canonical_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hash_content(canonical_json)


def hash_file(file_path: str) -> str:
    """
    Compute SHA-256 hash of a file's content.

    Args:
        file_path: Path to file to hash

    Returns:
        Hex-encoded SHA-256 hash

    Raises:
        FileNotFoundError: If file doesn't exist
        IOError: If file can't be read
    """
    hasher = hashlib.sha256()

    with open(file_path, "rb") as f:
        # Read in chunks to handle large files efficiently
        while chunk := f.read(8192):
            hasher.update(chunk)

    return hasher.hexdigest()


def compute_proposal_hash(
    platform: str,
    operation: str,
    target: dict[str, Any],
    payload_hash: str,
    state_version: str,
    dependencies: list[str],
) -> str:
    """
    Compute a proposal hash binding all immutable proposal components.

    Used to bind approval to an exact proposed action.

    Args:
        platform: Target platform (e.g., "vapi", "make")
        operation: Operation name (e.g., "create_assistant")
        target: Target reference dictionary
        payload_hash: Hash of the request payload
        state_version: Current state version/hash
        dependencies: List of dependency task IDs

    Returns:
        SHA-256 hash binding all components
    """
    proposal_components = {
        "platform": platform,
        "operation": operation,
        "target": target,
        "payload_hash": payload_hash,
        "state_version": state_version,
        "dependencies": sorted(dependencies),  # Sort for consistency
    }

    return hash_json(proposal_components)


def compute_display_hash(display_content: str) -> str:
    """
    Compute hash of the exact approval display content shown to operator.

    Args:
        display_content: The text shown in the approval prompt

    Returns:
        SHA-256 hash of display content
    """
    return hash_content(display_content)


def compute_audit_hash(
    event_type: str,
    actor_id: str,
    subject_id: str,
    status: str,
    detail: dict[str, Any],
    timestamp: str,
    previous_hash: str,
) -> str:
    """
    Compute hash for audit event with chain linkage.

    Args:
        event_type: Type of audit event
        actor_id: Actor performing the event
        subject_id: Subject of the event
        status: Event status
        detail: Event detail dictionary
        timestamp: ISO timestamp of event
        previous_hash: Hash of previous event in chain (empty for first)

    Returns:
        SHA-256 hash linking to previous event
    """
    event_components = {
        "event_type": event_type,
        "actor_id": actor_id,
        "subject_id": subject_id,
        "status": status,
        "detail": detail,
        "timestamp": timestamp,
        "previous_hash": previous_hash,
    }

    return hash_json(event_components)


def verify_hash(content: str | bytes, expected_hash: str) -> bool:
    """
    Verify that content matches expected hash.

    Args:
        content: Content to verify
        expected_hash: Expected SHA-256 hash

    Returns:
        True if hash matches, False otherwise
    """
    actual_hash = hash_content(content)
    return actual_hash == expected_hash


def compute_intake_hash(intake: dict[str, Any]) -> str:
    """
    Compute hash of sanitized intake data.

    Excludes volatile fields and ensures consistent ordering.

    Args:
        intake: Intake dictionary

    Returns:
        SHA-256 hash of canonical intake
    """
    # Create a copy and remove any volatile metadata fields
    sanitized = {
        k: v for k, v in intake.items() if k not in ["metadata", "created_at", "updated_at"]
    }

    return hash_json(sanitized)


def compute_state_version(state: dict[str, Any]) -> str:
    """
    Compute a state version hash from current external state.

    Used for staleness detection before writes.

    Args:
        state: Dictionary representing current state

    Returns:
        SHA-256 hash of canonical state representation
    """
    return hash_json(state)


def compute_content_hash(content: str | bytes | dict[str, Any]) -> str:
    """
    Compute SHA-256 hash of content.

    Convenience function that handles strings, bytes, or dictionaries.

    Args:
        content: String, bytes, or dictionary to hash

    Returns:
        Hex-encoded SHA-256 hash
    """
    if isinstance(content, dict):
        return hash_json(content)
    else:
        return hash_content(content)
