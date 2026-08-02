"""
ActionContract dataclass for Agent Forge.

Represents one immutable proposed external side effect with its
reconciliation and compensation metadata.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ActionContract:
    """
    Represents a proposed external action with all metadata needed for
    safe execution, retry, reconciliation, and compensation.

    Immutable after creation - regeneration creates a new instance.
    """

    platform: str
    operation: str
    target: dict[str, Any]
    payload_hash: str
    state_version: str
    idempotency_key: str | None
    retry_policy: dict[str, Any]
    reconciliation_strategy: str
    compensation_operation: str | None

    # Optional metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate action contract after initialization."""
        if not self.platform:
            raise ValueError("platform is required")
        if not self.operation:
            raise ValueError("operation is required")
        if not self.target:
            raise ValueError("target is required")
        if not self.payload_hash:
            raise ValueError("payload_hash is required")
        if not self.state_version:
            raise ValueError("state_version is required")
        if not self.retry_policy:
            raise ValueError("retry_policy is required")
        if not self.reconciliation_strategy:
            raise ValueError("reconciliation_strategy is required")

        # Validate platform
        valid_platforms = ["vapi", "make", "supabase_client", "hosting"]
        if self.platform not in valid_platforms:
            raise ValueError(f"Invalid platform: {self.platform}. Must be one of {valid_platforms}")

        # Validate retry policy structure
        if "max_retries" not in self.retry_policy:
            raise ValueError("retry_policy must contain 'max_retries'")
        if "retry_delay_seconds" not in self.retry_policy:
            raise ValueError("retry_policy must contain 'retry_delay_seconds'")

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation of the action contract
        """
        return {
            "platform": self.platform,
            "operation": self.operation,
            "target": self.target,
            "payload_hash": self.payload_hash,
            "state_version": self.state_version,
            "idempotency_key": self.idempotency_key,
            "retry_policy": self.retry_policy,
            "reconciliation_strategy": self.reconciliation_strategy,
            "compensation_operation": self.compensation_operation,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActionContract":
        """
        Create ActionContract from dictionary.

        Args:
            data: Dictionary with action contract data

        Returns:
            ActionContract instance
        """
        return cls(
            platform=data["platform"],
            operation=data["operation"],
            target=data["target"],
            payload_hash=data["payload_hash"],
            state_version=data["state_version"],
            idempotency_key=data.get("idempotency_key"),
            retry_policy=data["retry_policy"],
            reconciliation_strategy=data["reconciliation_strategy"],
            compensation_operation=data.get("compensation_operation"),
            metadata=data.get("metadata", {}),
        )

    def is_idempotent(self) -> bool:
        """
        Check if action has idempotency support.

        Returns:
            True if idempotency_key is set
        """
        return self.idempotency_key is not None

    def has_compensation(self) -> bool:
        """
        Check if action has a defined compensation operation.

        Returns:
            True if compensation_operation is defined
        """
        return self.compensation_operation is not None

    def is_retryable(self) -> bool:
        """
        Check if action allows retries.

        Returns:
            True if max_retries > 0
        """
        max_retries: int = self.retry_policy.get("max_retries", 0)
        return max_retries > 0

    def is_read_only(self) -> bool:
        """
        Check if operation is read-only (safe to retry without reconciliation).

        Returns:
            True if operation is a read operation
        """
        read_operations = ["get", "list", "read", "select", "query", "verify"]
        return any(op in self.operation.lower() for op in read_operations)

    def is_create_operation(self) -> bool:
        """
        Check if operation creates a new resource.

        Returns:
            True if operation is a create operation
        """
        return "create" in self.operation.lower()

    def is_update_operation(self) -> bool:
        """
        Check if operation updates an existing resource.

        Returns:
            True if operation is an update operation
        """
        update_keywords = ["update", "patch", "modify", "set"]
        return any(keyword in self.operation.lower() for keyword in update_keywords)

    def is_delete_operation(self) -> bool:
        """
        Check if operation deletes a resource.

        Returns:
            True if operation is a delete operation
        """
        return "delete" in self.operation.lower()

    def get_max_retries(self) -> int:
        """
        Get maximum retry count from policy.

        Returns:
            Maximum number of retries allowed
        """
        max_retries: int = self.retry_policy.get("max_retries", 0)
        return max_retries

    def get_retry_delay(self) -> float:
        """
        Get retry delay in seconds.

        Returns:
            Delay between retries in seconds
        """
        delay: float = self.retry_policy.get("retry_delay_seconds", 0.0)
        return delay
