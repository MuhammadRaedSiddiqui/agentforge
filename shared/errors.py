"""
Custom error hierarchy for Agent Forge.

Provides typed exceptions for different failure scenarios to enable
proper routing, retry logic, and recovery strategies.
"""


class AgentForgeError(Exception):
    """Base exception for all Agent Forge errors."""

    pass


class ValidationError(AgentForgeError):
    """
    Validation failed for intake, artifact, or proposed action.

    This is a permanent error - retry will not help without changes.
    """

    pass


class AuthorizationError(AgentForgeError):
    """
    Authorization failed for an external platform operation.

    May indicate expired credentials, insufficient permissions, or invalid tokens.
    """

    pass


class ConflictError(AgentForgeError):
    """
    Resource conflict detected (e.g., duplicate resource, concurrent modification).

    May be resolvable through reconciliation or regeneration with updated state.
    """

    pass


class TransientError(AgentForgeError):
    """
    Transient failure that may succeed on retry.

    Examples: network timeout, rate limiting, temporary service unavailability.
    """

    pass


class PermanentError(AgentForgeError):
    """
    Permanent failure that will not succeed on retry.

    Examples: invalid request format, unsupported operation, resource not found.
    """

    pass


class AmbiguousOutcomeError(AgentForgeError):
    """
    Outcome is ambiguous - unknown if operation succeeded remotely.

    Examples: timeout after request sent, connection lost during response.
    Requires remote reconciliation before retry.
    """

    pass


class CompensationError(AgentForgeError):
    """
    Compensation operation failed during recovery.

    The deployment remains in an unresolved state requiring manual intervention.
    """

    pass


class PersistenceError(AgentForgeError):
    """
    Local persistence operation failed.

    May occur after successful remote operation, requiring reconciliation.
    """

    pass


class StateTransitionError(AgentForgeError):
    """
    Illegal state transition attempted.

    Indicates a logic error in orchestration or state management.
    """

    pass


class OrganizationLockError(AgentForgeError):
    """
    Failed to acquire organization lock.

    Another session is actively modifying this organization.
    """

    pass


class RecoveryRequiredError(AgentForgeError):
    """
    Deployment requires recovery before new work can proceed.

    Operator must resolve partial or ambiguous state.
    """

    pass


def classify_error(error: Exception) -> str:
    """
    Classify an exception into a FailureClass for data model.

    Args:
        error: The exception to classify

    Returns:
        String matching FailureClass enum: validation, authorization, conflict,
        transient, permanent, ambiguous_outcome, compensation_failure, or
        local_persistence_failure
    """
    if isinstance(error, ValidationError):
        return "validation"
    elif isinstance(error, AuthorizationError):
        return "authorization"
    elif isinstance(error, ConflictError):
        return "conflict"
    elif isinstance(error, TransientError):
        return "transient"
    elif isinstance(error, PermanentError):
        return "permanent"
    elif isinstance(error, AmbiguousOutcomeError):
        return "ambiguous_outcome"
    elif isinstance(error, CompensationError):
        return "compensation_failure"
    elif isinstance(error, PersistenceError):
        return "local_persistence_failure"
    else:
        # Unknown errors are treated as permanent by default
        return "permanent"
