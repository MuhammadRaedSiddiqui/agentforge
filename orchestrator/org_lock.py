"""
Organization lock for Agent Forge.

File-based locking to prevent concurrent modifications of the same organization.
"""

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from shared.errors import OrganizationLockError


@dataclass
class LockInfo:
    """Information about an active lock."""

    organization_id: str
    session_id: str
    process_id: int
    host_fingerprint: str
    acquired_at: float
    lock_file_path: str


class OrganizationLock:
    """
    File-based organization lock.

    Prevents concurrent modifying deployments for the same organization.
    Supports staleness detection and takeover validation.
    """

    # Default staleness threshold (1 hour)
    DEFAULT_STALENESS_THRESHOLD = 3600.0

    def __init__(
        self,
        lock_dir: str = ".locks",
        staleness_threshold: float = DEFAULT_STALENESS_THRESHOLD,
    ):
        """
        Initialize organization lock manager.

        Args:
            lock_dir: Directory to store lock files
            staleness_threshold: Time in seconds before lock is considered stale
        """
        self.lock_dir = Path(lock_dir)
        self.staleness_threshold = staleness_threshold

        # Ensure lock directory exists
        self.lock_dir.mkdir(parents=True, exist_ok=True)

    def _get_lock_file_path(self, organization_id: str) -> Path:
        """
        Get lock file path for organization.

        Args:
            organization_id: Normalized organization identifier

        Returns:
            Path to lock file
        """
        return self.lock_dir / f"{organization_id}.lock"

    def _get_process_id(self) -> int:
        """Get current process ID."""
        return os.getpid()

    def _get_host_fingerprint(self) -> str:
        """
        Get host fingerprint (non-secret identifier).

        Returns:
            Host fingerprint string
        """
        import hashlib
        import socket

        try:
            hostname = socket.gethostname()
            # Hash to avoid exposing actual hostname
            fingerprint = hashlib.sha256(hostname.encode()).hexdigest()[:16]
            return fingerprint
        except Exception:
            return "unknown"

    def _read_lock_file(self, lock_file: Path) -> Optional[dict]:
        """
        Read lock file contents.

        Args:
            lock_file: Path to lock file

        Returns:
            Lock data dictionary or None if read fails
        """
        try:
            with lock_file.open("r") as f:
                return json.load(f)
        except Exception:
            return None

    def _write_lock_file(
        self, lock_file: Path, session_id: str, organization_id: str
    ) -> None:
        """
        Write lock file.

        Args:
            lock_file: Path to lock file
            session_id: Session identifier
            organization_id: Organization identifier
        """
        lock_data = {
            "organization_id": organization_id,
            "session_id": session_id,
            "process_id": self._get_process_id(),
            "host_fingerprint": self._get_host_fingerprint(),
            "acquired_at": time.time(),
        }

        with lock_file.open("w") as f:
            json.dump(lock_data, f, indent=2)

    def _is_stale(self, lock_data: dict) -> bool:
        """
        Check if lock is stale.

        Args:
            lock_data: Lock data dictionary

        Returns:
            True if lock is stale
        """
        acquired_at = lock_data.get("acquired_at", 0)
        age = time.time() - acquired_at

        return age > self.staleness_threshold

    def acquire(
        self,
        organization_id: str,
        session_id: str,
        force_takeover: bool = False,
    ) -> LockInfo:
        """
        Acquire lock for organization.

        Args:
            organization_id: Normalized organization identifier
            session_id: Session identifier
            force_takeover: If True, take over stale locks

        Returns:
            LockInfo with lock details

        Raises:
            OrganizationLockError: If lock cannot be acquired
        """
        lock_file = self._get_lock_file_path(organization_id)

        # Check if lock file exists
        if lock_file.exists():
            lock_data = self._read_lock_file(lock_file)

            if lock_data:
                # Check if it's our own lock (same session)
                if lock_data.get("session_id") == session_id:
                    # Already have the lock
                    return LockInfo(
                        organization_id=organization_id,
                        session_id=session_id,
                        process_id=lock_data.get("process_id", 0),
                        host_fingerprint=lock_data.get("host_fingerprint", "unknown"),
                        acquired_at=lock_data.get("acquired_at", time.time()),
                        lock_file_path=str(lock_file),
                    )

                # Check staleness
                is_stale = self._is_stale(lock_data)

                if is_stale and force_takeover:
                    # Take over stale lock
                    self._write_lock_file(lock_file, session_id, organization_id)

                    return LockInfo(
                        organization_id=organization_id,
                        session_id=session_id,
                        process_id=self._get_process_id(),
                        host_fingerprint=self._get_host_fingerprint(),
                        acquired_at=time.time(),
                        lock_file_path=str(lock_file),
                    )

                # Lock is held by another session
                age = time.time() - lock_data.get("acquired_at", 0)
                raise OrganizationLockError(
                    f"Organization '{organization_id}' is locked by session "
                    f"{lock_data.get('session_id')} "
                    f"(acquired {int(age)}s ago, "
                    f"{'STALE' if is_stale else 'ACTIVE'}). "
                    f"Use force_takeover=True to take over stale locks."
                )

        # No existing lock, acquire it
        self._write_lock_file(lock_file, session_id, organization_id)

        return LockInfo(
            organization_id=organization_id,
            session_id=session_id,
            process_id=self._get_process_id(),
            host_fingerprint=self._get_host_fingerprint(),
            acquired_at=time.time(),
            lock_file_path=str(lock_file),
        )

    def release(self, organization_id: str, session_id: str) -> bool:
        """
        Release lock for organization.

        Args:
            organization_id: Normalized organization identifier
            session_id: Session identifier (must match lock owner)

        Returns:
            True if lock was released, False if no lock or wrong session

        Raises:
            OrganizationLockError: If lock is held by different session
        """
        lock_file = self._get_lock_file_path(organization_id)

        if not lock_file.exists():
            # No lock to release
            return False

        # Read lock data
        lock_data = self._read_lock_file(lock_file)

        if not lock_data:
            # Invalid lock file, remove it
            lock_file.unlink()
            return False

        # Check if this session owns the lock
        if lock_data.get("session_id") != session_id:
            raise OrganizationLockError(
                f"Cannot release lock: organization '{organization_id}' "
                f"is locked by session {lock_data.get('session_id')}, "
                f"not {session_id}"
            )

        # Remove lock file
        lock_file.unlink()
        return True

    def check_lock(self, organization_id: str) -> Optional[LockInfo]:
        """
        Check if organization is locked.

        Args:
            organization_id: Normalized organization identifier

        Returns:
            LockInfo if locked, None if not locked
        """
        lock_file = self._get_lock_file_path(organization_id)

        if not lock_file.exists():
            return None

        lock_data = self._read_lock_file(lock_file)

        if not lock_data:
            return None

        return LockInfo(
            organization_id=organization_id,
            session_id=lock_data.get("session_id", "unknown"),
            process_id=lock_data.get("process_id", 0),
            host_fingerprint=lock_data.get("host_fingerprint", "unknown"),
            acquired_at=lock_data.get("acquired_at", 0),
            lock_file_path=str(lock_file),
        )

    def is_locked(self, organization_id: str) -> bool:
        """
        Check if organization is currently locked.

        Args:
            organization_id: Normalized organization identifier

        Returns:
            True if locked
        """
        return self.check_lock(organization_id) is not None

    def cleanup_stale_locks(self) -> int:
        """
        Clean up all stale locks.

        Returns:
            Number of stale locks removed
        """
        count = 0

        for lock_file in self.lock_dir.glob("*.lock"):
            lock_data = self._read_lock_file(lock_file)

            if lock_data and self._is_stale(lock_data):
                try:
                    lock_file.unlink()
                    count += 1
                except Exception:
                    pass

        return count
