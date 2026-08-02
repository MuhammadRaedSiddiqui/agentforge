"""
TaskObject dataclass for Agent Forge.

Represents one deterministic delegation to a specialist domain.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskObject:
    """
    Represents a task delegated to a specialist agent.

    Immutable after creation except for status transitions.
    """

    task_id: str
    deployment_id: str
    agent_target: str
    action_type: str
    context_hash: str
    constraints: list[str]
    dependencies: list[str]
    verification_required: bool
    status: str = "pending"
    attempt_number: int = 1

    # Optional metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate task object after initialization."""
        if not self.task_id:
            raise ValueError("task_id is required")
        if not self.deployment_id:
            raise ValueError("deployment_id is required")
        if not self.agent_target:
            raise ValueError("agent_target is required")
        if not self.action_type:
            raise ValueError("action_type is required")
        if not self.context_hash:
            raise ValueError("context_hash is required")

        # Validate status
        valid_statuses = [
            "pending",
            "running",
            "success",
            "validation_failed",
            "error",
            "blocked",
            "aborted",
        ]
        if self.status not in valid_statuses:
            raise ValueError(f"Invalid status: {self.status}. Must be one of {valid_statuses}")

        # Validate attempt number
        if self.attempt_number < 1:
            raise ValueError("attempt_number must be >= 1")

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation of the task
        """
        return {
            "task_id": self.task_id,
            "deployment_id": self.deployment_id,
            "agent_target": self.agent_target,
            "action_type": self.action_type,
            "context_hash": self.context_hash,
            "constraints": self.constraints,
            "dependencies": self.dependencies,
            "verification_required": self.verification_required,
            "status": self.status,
            "attempt_number": self.attempt_number,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskObject":
        """
        Create TaskObject from dictionary.

        Args:
            data: Dictionary with task data

        Returns:
            TaskObject instance
        """
        return cls(
            task_id=data["task_id"],
            deployment_id=data["deployment_id"],
            agent_target=data["agent_target"],
            action_type=data["action_type"],
            context_hash=data["context_hash"],
            constraints=data.get("constraints", []),
            dependencies=data.get("dependencies", []),
            verification_required=data.get("verification_required", True),
            status=data.get("status", "pending"),
            attempt_number=data.get("attempt_number", 1),
            metadata=data.get("metadata", {}),
        )

    def is_terminal(self) -> bool:
        """
        Check if task is in a terminal state.

        Returns:
            True if task is in a terminal state (success, error, aborted)
        """
        return self.status in ["success", "error", "aborted"]

    def is_blocked(self) -> bool:
        """
        Check if task is blocked.

        Returns:
            True if task status is blocked
        """
        return self.status == "blocked"

    def can_run(self) -> bool:
        """
        Check if task can be run (pending and not blocked).

        Returns:
            True if task can be executed
        """
        return self.status == "pending" and not self.is_blocked()
