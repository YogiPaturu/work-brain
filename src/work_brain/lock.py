from __future__ import annotations

import os
from pathlib import Path

from .errors import LockError


class VaultLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, "a+b")
        try:
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            self.handle = None
            raise LockError(f"vault writer lock is already held: {self.path}") from exc
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

    def __enter__(self) -> "VaultLock":
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()

