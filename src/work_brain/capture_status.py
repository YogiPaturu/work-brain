"""Source-only lifecycle status helpers for hooks and the CLI status view."""

from __future__ import annotations

from typing import Any

from .capture import HarnessCaptureService
from .fsutil import read_json
from .lifecycle import normalize_runtime


def session_status(vault: Any, session_id: str) -> dict[str, Any]:
    session = vault.read_session(session_id)
    turns = vault.list_turns(session_id)
    mappings_path = vault.root / HarnessCaptureService.MAP_RELATIVE
    mappings = read_json(mappings_path) if mappings_path.exists() else {}
    host_mappings = [
        {
            "host": value.get("host"),
            "host_session_id": value.get("host_session_id"),
            "workflow": value.get("workflow"),
            "active": value.get("session_id") == session_id,
        }
        for value in mappings.values()
        if isinstance(value, dict) and value.get("session_id") == session_id
    ]
    entries = [entry for entry in vault.all_current_entries() if entry.session_id == session_id]
    runtime, lifecycle_state = normalize_runtime(
        session.get("runtime"), ended_at=session.get("ended_at"), has_entry=bool(entries)
    )
    if runtime.get("archive_status") == "session":
        lifecycle = "archived"
    elif host_mappings:
        lifecycle = "active_capture"
    elif entries or lifecycle_state.commit.value == "committed":
        lifecycle = "committed"
    elif lifecycle_state.commit.value == "pending" or lifecycle_state.capture.value == "recoverable":
        lifecycle = "recoverable_raw"
    elif runtime.get("commit_status") == "no_new_evidence":
        lifecycle = "closed_no_new_evidence"
    else:
        lifecycle = "closed_uncommitted"
    last = turns[-1] if turns else None
    if lifecycle == "archived":
        message = "Session is archived from active views; all raw turns are preserved and readable."
    elif lifecycle == "active_capture":
        message = "Capture is active; raw turns are being saved."
    elif lifecycle == "recoverable_raw":
        message = "Capture is inactive; raw turns are preserved and the structured commit is pending."
    elif lifecycle == "closed_no_new_evidence":
        message = "Capture is closed; no new structured evidence was committed."
    elif lifecycle == "committed":
        message = "Structured entry is committed; raw turns remain preserved."
    elif runtime.get("capture_status") == "imported":
        lifecycle = "imported"
        message = "Imported raw transcript is preserved; no structured entry has been committed."
    else:
        message = "Capture is closed; raw turns are preserved but no structured entry is committed."
    active_mapping = host_mappings[0] if host_mappings else None
    return {
        "session_id": session["session_id"],
        "entry_id": session["entry_id"],
        "local_date": session["local_date"],
        "started_at": session["started_at"],
        "ended_at": session.get("ended_at"),
        "lifecycle": lifecycle,
        "message": message,
        "capture_status": runtime.get("capture_status", "not_captured"),
        "commit_status": "committed" if entries else runtime.get("commit_status"),
        "lifecycle_state": lifecycle_state.to_dict(),
        "capture_active": bool(host_mappings),
        "turn_count": len(turns),
        "last_captured_turn": None if last is None else {
            "sequence": last["sequence"], "role": last["role"], "recorded_at": last["recorded_at"],
        },
        "last_captured_at": last["recorded_at"] if last else None,
        "host_session_id": active_mapping["host_session_id"] if active_mapping else runtime.get("host_session_id"),
        "host_mappings": host_mappings,
        "has_committed_entry": bool(entries),
        "current_revision": max((entry.revision for entry in entries), default=None),
    }


def live_status(vault: Any) -> dict[str, Any]:
    """Build a read-only status snapshot without opening projections."""
    mappings_path = vault.root / HarnessCaptureService.MAP_RELATIVE
    mappings = read_json(mappings_path) if mappings_path.exists() else {}
    if not isinstance(mappings, dict):
        raise ValueError("capture mapping state must be a JSON object")

    active_ids: list[str] = []
    for mapping in mappings.values():
        if not isinstance(mapping, dict) or not isinstance(mapping.get("session_id"), str):
            continue
        if mapping["session_id"] not in active_ids:
            active_ids.append(mapping["session_id"])
    active_sessions = [session_status(vault, session_id) for session_id in active_ids]
    entry_session_ids = {entry.session_id for entry in vault.all_current_entries()}
    recoverable_sessions = []
    for session in vault.all_sessions():
        runtime = session.get("runtime") or {}
        if session["session_id"] not in entry_session_ids and (
            session.get("ended_at") is None
            or runtime.get("commit_status") in {"pending_auto_commit", "auto_commit_failed"}
        ) and session["session_id"] not in active_ids:
            recoverable_sessions.append(session_status(vault, session["session_id"]))

    primary = active_sessions[0] if active_sessions else (recoverable_sessions[0] if recoverable_sessions else None)
    if active_sessions:
        lifecycle, message = primary["lifecycle"], primary["message"]
    elif recoverable_sessions:
        lifecycle, message = "recoverable_raw", "No active capture; raw turns are preserved and a structured commit is pending."
    else:
        lifecycle, message = "inactive", "No active Work Brain capture or recoverable raw session."
    return {
        "lifecycle": lifecycle,
        "message": message,
        "capture_active": bool(active_sessions),
        "active_sessions": active_sessions,
        "recoverable_sessions": recoverable_sessions,
        "active_count": len(active_sessions),
        "recoverable_count": len(recoverable_sessions),
        "primary": primary,
        "capture_hook_health": vault.capture_hook_health(),
    }


def status_text(snapshot: dict[str, Any], *, quiet: bool = False) -> str:
    primary = snapshot.get("primary")
    if quiet:
        if not primary:
            return "[Work Brain: inactive]"
        capture = "ACTIVE" if primary.get("capture_active") else primary.get("lifecycle", "inactive").upper()
        commit = primary.get("commit_status") or "not_started"
        return f"[Work Brain: {capture} · {primary.get('turn_count', 0)} turns · commit {commit}]"
    lines = ["WORK BRAIN LIVE", "────────────────────────────────────────"]
    if primary:
        lines.extend([
            f"Capture     {'ACTIVE' if primary.get('capture_active') else primary.get('lifecycle', 'INACTIVE').upper()}",
            f"Session     {primary.get('session_id', '—')}",
            f"Turns       {primary.get('turn_count', 0)}",
            f"Last turn   {primary.get('last_captured_at') or '—'}",
            f"Commit      {primary.get('commit_status') or 'not_started'}",
            f"Lifecycle   {primary.get('lifecycle', 'unknown')}",
            f"Message     {primary.get('message', '—')}",
        ])
    else:
        lines.extend([
            "Capture     INACTIVE", "Session     —", "Turns       0", "Last turn   —", "Commit      —",
            f"Lifecycle   {snapshot.get('lifecycle', 'inactive')}",
            f"Message     {snapshot.get('message', '—')}",
        ])
    if snapshot.get("active_count", 0) > 1:
        lines.append(f"Active      {snapshot['active_count']} host sessions")
    if snapshot.get("recoverable_count", 0):
        lines.append(f"Recoverable  {snapshot['recoverable_count']} raw session(s)")
    return "\n".join(lines)
