"""
CLI session management for Agent Forge.

Manages session lifecycle, organization scoping, and lock acquisition.
"""

import uuid
from dataclasses import dataclass
from typing import Optional

from adapters.supabase_internal import SupabaseInternalClient
from cli.config import AgentForgeConfig
from orchestrator.deployment_lookup import DeploymentLookup
from orchestrator.org_lock import OrganizationLock, LockInfo
from shared.errors import OrganizationLockError


@dataclass
class Session:
    """Active CLI session."""

    session_id: str
    operator_id: str
    organization_id: Optional[str]
    lock_info: Optional[LockInfo]
    started_at: float


class SessionManager:
    """
    Manages CLI session lifecycle.

    Handles session creation, organization scoping, lock acquisition,
    and cleanup.
    """

    def __init__(
        self,
        config: AgentForgeConfig,
        internal_client: SupabaseInternalClient,
    ):
        """
        Initialize session manager.

        Args:
            config: Agent Forge configuration
            internal_client: Supabase internal client
        """
        self.config = config
        self.internal_client = internal_client
        self.org_lock = OrganizationLock()
        self.deployment_lookup = DeploymentLookup(internal_client)

        self.active_session: Optional[Session] = None

    def start_session(self, operator_id: str = "operator") -> Session:
        """
        Start a new session.

        Args:
            operator_id: Operator identifier

        Returns:
            Created session

        Raises:
            ValueError: If session already active
        """
        if self.active_session:
            raise ValueError("Session already active. End current session first.")

        import time

        session_id = str(uuid.uuid4())

        # Create session record
        session_record = self.internal_client.insert(
            "sessions",
            {
                "session_id": session_id,
                "operator_id": operator_id,
                "host_fingerprint": self._get_host_fingerprint(),
                "process_id": self._get_process_id(),
            },
        )

        session = Session(
            session_id=session_id,
            operator_id=operator_id,
            organization_id=None,
            lock_info=None,
            started_at=time.time(),
        )

        self.active_session = session

        return session

    def scope_to_organization(
        self,
        organization_id: str,
        force_takeover: bool = False,
    ) -> LockInfo:
        """
        Scope session to organization and acquire lock.

        Args:
            organization_id: Normalized organization identifier
            force_takeover: Allow taking over stale locks

        Returns:
            Lock information

        Raises:
            ValueError: If no active session
            OrganizationLockError: If lock cannot be acquired
        """
        if not self.active_session:
            raise ValueError("No active session. Start session first.")

        # Check for existing/partial deployments
        can_start = self.deployment_lookup.can_start_new_deployment(
            organization_id, "new_onboarding"
        )

        if not can_start["can_start"] and not force_takeover:
            raise OrganizationLockError(
                f"Cannot scope to organization: {can_start['reason']}"
            )

        # Acquire lock
        lock_info = self.org_lock.acquire(
            organization_id,
            self.active_session.session_id,
            force_takeover=force_takeover,
        )

        # Update session
        self.active_session.organization_id = organization_id
        self.active_session.lock_info = lock_info

        return lock_info

    def end_session(self, end_reason: str = "complete") -> None:
        """
        End active session and release locks.

        Args:
            end_reason: Reason for ending session
        """
        if not self.active_session:
            return

        # Release lock if held
        if self.active_session.lock_info:
            try:
                self.org_lock.release(
                    self.active_session.lock_info.organization_id,
                    self.active_session.session_id,
                )
            except Exception:
                pass  # Best effort

        # Update session record
        import time

        try:
            self.internal_client.update(
                "sessions",
                {"session_id": self.active_session.session_id},
                {
                    "ended_at": time.time(),
                    "end_reason": end_reason,
                },
            )
        except Exception:
            pass  # Best effort

        self.active_session = None

    def get_session(self) -> Optional[Session]:
        """Get active session."""
        return self.active_session

    def is_scoped(self) -> bool:
        """Check if session is scoped to an organization."""
        return (
            self.active_session is not None
            and self.active_session.organization_id is not None
        )

    def get_organization_id(self) -> Optional[str]:
        """Get scoped organization ID."""
        if self.active_session:
            return self.active_session.organization_id
        return None

    def check_recovery_required(self, organization_id: str) -> bool:
        """
        Check if organization requires recovery before new work.

        Args:
            organization_id: Organization identifier

        Returns:
            True if recovery required
        """
        return self.deployment_lookup.has_unresolved_recovery(organization_id)

    def _get_process_id(self) -> int:
        """Get current process ID."""
        import os
        return os.getpid()

    def _get_host_fingerprint(self) -> str:
        """Get host fingerprint."""
        import hashlib
        import socket

        try:
            hostname = socket.gethostname()
            fingerprint = hashlib.sha256(hostname.encode()).hexdigest()[:16]
            return fingerprint
        except Exception:
            return "unknown"

    def __enter__(self) -> "SessionManager":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - ensure session cleanup."""
        if exc_type:
            self.end_session(end_reason="error")
        else:
            self.end_session(end_reason="complete")
