"""
ResultObject dataclass for Agent Forge.

Represents the output from a specialist agent task execution.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ResultObject:
    """
    Represents the result of a task execution by a specialist agent.

    Contains the generated content, provenance, and validation status.
    """

    task_id: str
    agent_source: str
    content_hash: str
    storage_path: str
    summary: str
    field_provenance: Dict[str, Dict[str, str]]
    model_id: Optional[str]
    validation_status: str

    # Optional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate result object after initialization."""
        if not self.task_id:
            raise ValueError("task_id is required")
        if not self.agent_source:
            raise ValueError("agent_source is required")
        if not self.content_hash:
            raise ValueError("content_hash is required")
        if not self.storage_path:
            raise ValueError("storage_path is required")
        if not self.summary:
            raise ValueError("summary is required")

        # Validate validation_status
        valid_statuses = ["unverified", "verified", "stale", "failed"]
        if self.validation_status not in valid_statuses:
            raise ValueError(
                f"Invalid validation_status: {self.validation_status}. "
                f"Must be one of {valid_statuses}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation of the result
        """
        return {
            "task_id": self.task_id,
            "agent_source": self.agent_source,
            "content_hash": self.content_hash,
            "storage_path": self.storage_path,
            "summary": self.summary,
            "field_provenance": self.field_provenance,
            "model_id": self.model_id,
            "validation_status": self.validation_status,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResultObject":
        """
        Create ResultObject from dictionary.

        Args:
            data: Dictionary with result data

        Returns:
            ResultObject instance
        """
        return cls(
            task_id=data["task_id"],
            agent_source=data["agent_source"],
            content_hash=data["content_hash"],
            storage_path=data["storage_path"],
            summary=data["summary"],
            field_provenance=data.get("field_provenance", {}),
            model_id=data.get("model_id"),
            validation_status=data.get("validation_status", "unverified"),
            metadata=data.get("metadata", {}),
        )

    def is_verified(self) -> bool:
        """
        Check if result has been verified.

        Returns:
            True if validation_status is 'verified'
        """
        return self.validation_status == "verified"

    def is_stale(self) -> bool:
        """
        Check if result is stale.

        Returns:
            True if validation_status is 'stale'
        """
        return self.validation_status == "stale"

    def has_model_provenance(self) -> bool:
        """
        Check if result has model provenance information.

        Returns:
            True if model_id is set
        """
        return self.model_id is not None

    def get_inferred_fields(self) -> list[str]:
        """
        Get list of fields that were inferred or defaulted.

        Returns:
            List of field names marked as inferred/defaulted in provenance
        """
        inferred = []
        for field_name, provenance in self.field_provenance.items():
            if provenance.get("type") in ["inferred", "defaulted"]:
                inferred.append(field_name)
        return inferred

    def get_copied_fields(self) -> list[str]:
        """
        Get list of fields copied directly from intake.

        Returns:
            List of field names marked as copied in provenance
        """
        copied = []
        for field_name, provenance in self.field_provenance.items():
            if provenance.get("type") == "copied":
                copied.append(field_name)
        return copied
