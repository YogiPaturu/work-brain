from __future__ import annotations

import os
import errno
from pathlib import Path

from .errors import LockError, PersistenceError, VaultAccessError


class VaultLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def acquire(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.handle = open(self.path, "a+b")
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._close_after_failure()
            raise LockError(f"vault writer lock is already held: {self.path}") from exc
        except OSError as exc:
            self._close_after_failure()
            if exc.errno in {errno.EACCES, errno.EPERM, errno.EROFS}:
                raise VaultAccessError(f"Work Brain cannot write the vault at {self.path.parent}: {exc}") from exc
            raise PersistenceError(f"cannot acquire vault writer lock at {self.path}: {exc}") from exc
        except ImportError:
            # The v1 target is POSIX. On platforms without fcntl, retain a
            # process-local lock file and fail closed if it already contains a
            # live marker.
            self.handle.seek(0)
            if self.handle.read():
                self.handle.close()
                self.handle = None
                raise LockError(f"vault writer lock is already held: {self.path}")
            self.handle.write(str(os.getpid()).encode())
            self.handle.flush()

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            try:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            except ImportError:
                self.handle.seek(0)
                self.handle.truncate()
                self.handle.flush()
        finally:
            self.handle.close()
            self.handle = None

    def _close_after_failure(self) -> None:
        if self.handle is not None:
            self.handle.close()
            self.handle = None

    def __enter__(self) -> "VaultLock":
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()
