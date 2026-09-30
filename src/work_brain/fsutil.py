from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .errors import IntegrityError, PersistenceError


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass


def ensure_private_file(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        pass


def fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def atomic_replace_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}-{id(data)}")
    try:
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        ensure_private_file(path)
        fsync_directory(path.parent)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def atomic_replace_json(path: Path, value: Any) -> None:
    atomic_replace_bytes(path, canonical_json_bytes(value))


def atomic_create_bytes(path: Path, data: bytes) -> None:
    """Publish a new immutable file without replacing an existing revision."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}-{id(data)}")
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(tmp, flags, 0o600)
        try:
            offset = 0
            while offset < len(data):
                offset += os.write(fd, data[offset:])
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.link(tmp, path)
        except FileExistsError as exc:
            raise IntegrityError(f"immutable file already exists: {path}") from exc
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
        fsync_directory(path.parent)
    except OSError as exc:
        if isinstance(exc, IntegrityError):
            raise
        raise PersistenceError(f"failed to publish immutable file {path}: {exc}") from exc


def read_json(path: Path) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise IntegrityError(f"invalid JSON: {path}: {exc}") from exc


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json_bytes(value)
    with open(path, "ab") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    ensure_private_file(path)


def read_jsonl_with_recovery(path: Path) -> tuple[list[dict[str, Any]], bool]:
    """Read JSONL and truncate only an incomplete final unterminated record."""
    if not path.exists():
        return [], False
    raw = path.read_bytes()
    records: list[dict[str, Any]] = []
    offset = 0
    repaired = False
    for index, line in enumerate(raw.splitlines(keepends=True)):
        is_final = offset + len(line) == len(raw)
        body = line[:-1] if line.endswith(b"\n") else line
        if body.endswith(b"\r"):
            body = body[:-1]
        try:
            value = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            if is_final and not line.endswith(b"\n"):
                with open(path, "r+b") as handle:
                    handle.truncate(offset)
                    handle.flush()
                    os.fsync(handle.fileno())
                repaired = True
                break
            raise IntegrityError(f"malformed JSONL record {index + 1} in {path}") from exc
        if not isinstance(value, dict):
            raise IntegrityError(f"JSONL record {index + 1} in {path} must be an object")
        records.append(value)
        offset += len(line)
    return records, repaired
