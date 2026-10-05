"""Typed lifecycle state and compatibility transitions.

The JSON runtime snapshot is a compatibility boundary.  New code should use
the small records below rather than inferring state from unrelated keys.
Legacy flat keys are retained when serializing so old vaults and callers keep
their existing CLI-visible contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class CaptureLifecycle(str, Enum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    RECOVERABLE = "recoverable"
    CLOSED = "closed"


class CommitLifecycle(str, Enum):
    NONE = "none"
    PENDING = "pending"
    COMMITTED = "committed"
    FAILED = "failed"
    NO_NEW_EVIDENCE = "no_new_evidence"


class ProjectionLifecycle(str, Enum):
    CURRENT = "current"
    DIRTY = "dirty"
    REBUILDING = "rebuilding"
    FAILED = "failed"


@dataclass(frozen=True)
class LifecycleState:
    capture: CaptureLifecycle
    commit: CommitLifecycle
    projection: ProjectionLifecycle

    def to_dict(self) -> dict[str, str]:
        return {
            "capture": self.capture.value,
            "commit": self.commit.value,
            "projection": self.projection.value,
        }


def _capture_value(runtime: Mapping[str, Any], *, ended_at: str | None) -> CaptureLifecycle:
    value = runtime.get("capture_status")
    if value == "active":
        return CaptureLifecycle.ACTIVE
    if value in {"recoverable", "rolled_over"}:
        return CaptureLifecycle.RECOVERABLE
    if value in {"closed", "committed", "imported"}:
        return CaptureLifecycle.CLOSED
    if ended_at is not None:
        return CaptureLifecycle.CLOSED
    return CaptureLifecycle.INACTIVE


def _commit_value(runtime: Mapping[str, Any], *, has_entry: bool) -> CommitLifecycle:
    value = runtime.get("commit_status")
    if has_entry or value == "committed":
        return CommitLifecycle.COMMITTED
    if value in {"pending_auto_commit", "pending"}:
        return CommitLifecycle.PENDING
    if value in {"auto_commit_failed", "failed"}:
        return CommitLifecycle.FAILED
    if value in {"no_new_evidence", "abandoned"}:
        return CommitLifecycle.NO_NEW_EVIDENCE
    return CommitLifecycle.NONE


def normalize_runtime(
    runtime: Mapping[str, Any] | None,
    *,
    ended_at: str | None = None,
    has_entry: bool = False,
) -> tuple[dict[str, Any], LifecycleState]:
    """Read legacy runtime keys and return a canonical nested lifecycle state."""
    normalized = dict(runtime or {})
    existing = normalized.get("lifecycle")
    if isinstance(existing, Mapping):
        capture = CaptureLifecycle(existing.get("capture", _capture_value(normalized, ended_at=ended_at).value))
        commit = CommitLifecycle(existing.get("commit", _commit_value(normalized, has_entry=has_entry).value))
        projection = ProjectionLifecycle(existing.get("projection", "current"))
    else:
        capture = _capture_value(normalized, ended_at=ended_at)
        commit = _commit_value(normalized, has_entry=has_entry)
        projection = ProjectionLifecycle.CURRENT
    state = LifecycleState(capture, commit, projection)
    normalized["lifecycle"] = state.to_dict()
    return normalized, state


def transition(
    runtime: Mapping[str, Any] | None,
    *,
    capture: CaptureLifecycle | None = None,
    commit: CommitLifecycle | None = None,
    projection: ProjectionLifecycle | None = None,
    ended_at: str | None = None,
    has_entry: bool = False,
) -> tuple[dict[str, Any], LifecycleState]:
    """Apply one legal lifecycle transition and retain legacy flat aliases."""
    normalized, current = normalize_runtime(runtime, ended_at=ended_at, has_entry=has_entry)
    next_state = LifecycleState(capture or current.capture, commit or current.commit, projection or current.projection)
    legal_capture = {
        (CaptureLifecycle.INACTIVE, CaptureLifecycle.ACTIVE),
        (CaptureLifecycle.ACTIVE, CaptureLifecycle.RECOVERABLE),
        (CaptureLifecycle.ACTIVE, CaptureLifecycle.CLOSED),
        (CaptureLifecycle.RECOVERABLE, CaptureLifecycle.ACTIVE),
        (CaptureLifecycle.RECOVERABLE, CaptureLifecycle.CLOSED),
        (CaptureLifecycle.INACTIVE, CaptureLifecycle.CLOSED),
        (CaptureLifecycle.CLOSED, CaptureLifecycle.ACTIVE),
    }
    legal_commit = {
        (CommitLifecycle.NONE, CommitLifecycle.PENDING),
        (CommitLifecycle.PENDING, CommitLifecycle.COMMITTED),
        (CommitLifecycle.PENDING, CommitLifecycle.FAILED),
        (CommitLifecycle.PENDING, CommitLifecycle.NO_NEW_EVIDENCE),
        (CommitLifecycle.FAILED, CommitLifecycle.PENDING),
        (CommitLifecycle.NONE, CommitLifecycle.COMMITTED),
        (CommitLifecycle.NO_NEW_EVIDENCE, CommitLifecycle.COMMITTED),
        (CommitLifecycle.COMMITTED, CommitLifecycle.COMMITTED),
    }
    if capture is not None and capture != current.capture and (current.capture, capture) not in legal_capture:
        raise ValueError(f"illegal capture lifecycle transition: {current.capture.value} -> {capture.value}")
    if commit is not None and commit != current.commit and (current.commit, commit) not in legal_commit:
        raise ValueError(f"illegal commit lifecycle transition: {current.commit.value} -> {commit.value}")
    normalized["lifecycle"] = next_state.to_dict()
    normalized["capture_status"] = next_state.capture.value
    normalized["commit_status"] = next_state.commit.value if next_state.commit != CommitLifecycle.NONE else None
    normalized["projection_status"] = next_state.projection.value
    if normalized["commit_status"] is None:
        normalized.pop("commit_status", None)
    return normalized, next_state


def runtime_for_capture(
    runtime: Mapping[str, Any] | None,
    *,
    capture: CaptureLifecycle,
    commit: CommitLifecycle | None = None,
    projection: ProjectionLifecycle | None = None,
    ended_at: str | None = None,
    has_entry: bool = False,
) -> dict[str, Any]:
    return transition(
        runtime,
        capture=capture,
        commit=commit,
        projection=projection,
        ended_at=ended_at,
        has_entry=has_entry,
    )[0]
