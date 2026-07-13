"""
Deterministic ID generation for Agent Forge.

Provides consistent, traceable identifiers for tasks, knowledge entries,
and other entities.
"""

import uuid
from datetime import datetime
from typing import Optional


def generate_uuid() -> str:
    """
    Generate a new UUID v4.

    Returns:
        String representation of UUID (e.g., "550e8400-e29b-41d4-a716-446655440000")
    """
    return str(uuid.uuid4())


def generate_task_id(
    deployment_id: str, agent_target: str, sequence: int, attempt: int = 1
) -> str:
    """
    Generate a deterministic task ID.

    Format: {deployment_id_prefix}-{agent_target}-{sequence:03d}-{attempt}

    Args:
        deployment_id: The parent deployment UUID
        agent_target: The agent name (e.g., "vapi_agent")
        sequence: Sequential task number within deployment
        attempt: Attempt number for this task (default 1)

    Returns:
        Task ID string (e.g., "550e8400-vapi_agent-001-1")
    """
    # Use first 8 chars of deployment UUID for readability
    deployment_prefix = deployment_id.split("-")[0]
    return f"{deployment_prefix}-{agent_target}-{sequence:03d}-{attempt}"


def generate_knowledge_entry_id(source_path: str, content_hash: str) -> str:
    """
    Generate a deterministic knowledge entry ID.

    Combines source path and content hash to ensure uniqueness and
    enable stale detection.

    Args:
        source_path: Git-tracked path to the source file
        content_hash: SHA-256 hash of the content

    Returns:
        Knowledge entry ID (e.g., "knowledge-base-gotchas-vapi-timeout-a1b2c3d4")
    """
    # Normalize path separators and remove extension
    normalized_path = source_path.replace("\\", "/").replace(".md", "").replace("/", "-")

    # Take first 8 chars of hash
    hash_prefix = content_hash[:8]

    return f"{normalized_path}-{hash_prefix}"


def generate_idempotency_key(
    organization_id: str, operation: str, target: str, timestamp: Optional[str] = None
) -> str:
    """
    Generate an idempotency key for external operations.

    Used when vendor supports idempotency keys to prevent duplicate operations.

    Args:
        organization_id: The organization identifier
        operation: Operation name (e.g., "create_assistant")
        target: Target identifier (e.g., "vapi")
        timestamp: Optional ISO timestamp (defaults to current time)

    Returns:
        Idempotency key string
    """
    if timestamp is None:
        timestamp = datetime.utcnow().isoformat()

    # Create a deterministic key from components
    components = [organization_id, operation, target, timestamp]
    return "-".join(components)


def validate_uuid(value: str) -> bool:
    """
    Validate that a string is a valid UUID.

    Args:
        value: String to validate

    Returns:
        True if valid UUID, False otherwise
    """
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def validate_organization_id(org_id: str) -> bool:
    """
    Validate organization ID format.

    Must be lowercase alphanumeric with underscores, matching ^[a-z0-9_]+$

    Args:
        org_id: Organization identifier to validate

    Returns:
        True if valid, False otherwise
    """
    if not org_id:
        return False

    # Check pattern: lowercase letters, numbers, underscores only
    import re

    pattern = r"^[a-z0-9_]+$"
    return bool(re.match(pattern, org_id))


def normalize_organization_id(org_name: str) -> str:
    """
    Normalize an organization name to a valid organization ID.

    Converts to lowercase, replaces spaces and hyphens with underscores,
    removes invalid characters.

    Args:
        org_name: Human-readable organization name

    Returns:
        Normalized organization_id
    """
    # Convert to lowercase
    normalized = org_name.lower()

    # Replace spaces and hyphens with underscores
    normalized = normalized.replace(" ", "_")
    normalized = normalized.replace("-", "_")

    # Remove any character that's not lowercase letter, number, or underscore
    import re

    normalized = re.sub(r"[^a-z0-9_]", "", normalized)

    # Collapse multiple underscores
    normalized = re.sub(r"_+", "_", normalized)

    # Remove leading/trailing underscores
    normalized = normalized.strip("_")

    return normalized
