from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
from typing import Any, Mapping

from .errors import ValidationError
from .fsutil import atomic_replace_json, ensure_private_file, read_json
from .orchestrator import PromptRoute, route_prompt, select_workflow
from .timeutil import date_for_timestamp, parse_timestamp, timestamp_now


HOSTS = {"codex", "claude-code", "cursor"}
_ACTIVATION_RE = re.compile(r"^\s*work\s+brain\s*:", re.IGNORECASE)


@dataclass(frozen=True)
class CaptureEvent:
    host: str
    kind: str
    host_session_id: str
    text: str | None = None
    host_model: str | None = None
    recorded_at: str | None = None
    explicit_activation: bool = False
    workflow_hint: str | None = None
    routed_content: str | None = None
    lifecycle: str | None = None


def _value(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    return None


def _host_session_id(payload: Mapping[str, Any]) -> str:
    value = _value(payload, "session_id", "sessionId", "conversation_id", "conversationId")
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("capture hook payload requires a host session ID")
    return value.strip()


def _event_name(payload: Mapping[str, Any]) -> str:
    value = _value(payload, "event", "event_name", "hook_event_name", "hookEventName", "type")
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("capture hook payload requires an event name")
    return value.strip()


def _model(payload: Mapping[str, Any]) -> str | None:
    value = _value(payload, "model", "model_id", "modelId", "host_model")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _timestamp(payload: Mapping[str, Any]) -> str:
    value = _value(payload, "recorded_at", "timestamp", "time")
    return value if isinstance(value, str) and value.strip() else timestamp_now()


def _explicit_skill(payload: Mapping[str, Any]) -> bool:
    # Skill discovery/loading is not activation. A host must provide an
    # explicit user-invocation marker; merely reporting the loaded Skill name
    # or a generic `skill_invoked` flag is insufficient.
    if payload.get("work_brain_explicit_activation") is True:
        return True
    explicit_marker = payload.get("skill_invocation_explicit") is True or payload.get("skillInvocationExplicit") is True
    if not explicit_marker:
        return False
    for key in ("skill", "skill_name", "skillName", "invoked_skill", "invokedSkill"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip().casefold().lstrip("/$") == "work-brain":
            return True
    return False


def _text(payload: Mapping[str, Any], *keys: str) -> str | None:
    value = _value(payload, *keys)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"capture event text field must be a string: {keys[0]}")
    return value


def _route_prompt(text: str | None) -> PromptRoute:
    return route_prompt(text or "")


def _normalize(host: str, payload: Mapping[str, Any], event_map: Mapping[str, str]) -> CaptureEvent:
    if host not in HOSTS:
        raise ValidationError(f"unsupported capture host: {host}")
    name = _event_name(payload)
    kind = event_map.get(name.casefold())
    if kind is None:
        raise ValidationError(f"unsupported {host} capture event: {name}")
    text = None
    if kind == "user_prompt":
        text = _text(payload, "prompt", "text", "content")
        if text is None or not text:
            raise ValidationError("user prompt capture event requires prompt text")
    elif kind == "assistant_message":
        text = _text(payload, "last_assistant_message", "lastAssistantMessage", "text", "content")
        if text is None or not text:
            raise ValidationError("assistant capture event requires visible response text")
    route = _route_prompt(text) if kind == "user_prompt" else None
    return CaptureEvent(
        host=host,
        kind=kind,
        host_session_id=_host_session_id(payload),
        text=text,
        host_model=_model(payload),
        recorded_at=_timestamp(payload),
        explicit_activation=_explicit_skill(payload) or bool(route and (route.activation or _ACTIVATION_RE.match(text or "") or re.match(r"^\s*(?:/|\$)work-brain(?:\s|$)", text or "", re.IGNORECASE))),
        workflow_hint=route.workflow if route and (route.recognized or route.activation) else None,
        routed_content=route.routed_content if route else None,
        lifecycle=route.lifecycle if route else None,
    )


class CodexCaptureAdapter:
    EVENTS = {
        "sessionstart": "session_start", "userpromptsubmit": "user_prompt",
        "stop": "assistant_message", "sessionend": "session_end", "interrupt": "interrupt",
    }

    def normalize(self, payload: Mapping[str, Any]) -> CaptureEvent:
        return _normalize("codex", payload, self.EVENTS)


class ClaudeCodeCaptureAdapter:
    EVENTS = {
        "sessionstart": "session_start", "userpromptsubmit": "user_prompt",
        "stop": "assistant_message", "sessionend": "session_end", "interrupt": "interrupt",
    }

    def normalize(self, payload: Mapping[str, Any]) -> CaptureEvent:
        return _normalize("claude-code", payload, self.EVENTS)


class CursorCaptureAdapter:
    EVENTS = {
        "sessionstart": "session_start", "beforesubmitprompt": "user_prompt",
        "afteragentresponse": "assistant_message", "sessionend": "session_end",
    }

    def normalize(self, payload: Mapping[str, Any]) -> CaptureEvent:
        return _normalize("cursor", payload, self.EVENTS)


def normalize_capture_event(host: str, payload: Mapping[str, Any]) -> CaptureEvent:
    if not isinstance(payload, Mapping):
        raise ValidationError("capture hook input must be a JSON object")
    adapters = {
        "codex": CodexCaptureAdapter(),
        "claude-code": ClaudeCodeCaptureAdapter(),
        "cursor": CursorCaptureAdapter(),
    }
    try:
        adapter = adapters[host]
    except KeyError as exc:
        raise ValidationError(f"unsupported capture host: {host}") from exc
    return adapter.normalize(payload)


class HarnessCaptureService:
    """Normalizes host lifecycle events into the vault persistence API."""

    MAP_RELATIVE = "context/capture-mappings.json"

    def __init__(self, vault: Any):
        self.vault = vault
        self.vault.initialize()
        self.mapping_path = self.vault.root / self.MAP_RELATIVE
        if not self.mapping_path.exists():
            atomic_replace_json(self.mapping_path, {})
        ensure_private_file(self.mapping_path)

    def _read_mappings(self) -> dict[str, dict[str, Any]]:
        value = read_json(self.mapping_path)
        if not isinstance(value, dict):
            raise ValidationError("capture mapping state must be a JSON object")
        mappings: dict[str, dict[str, Any]] = {}
        for key, item in value.items():
            if not isinstance(item, Mapping) or not isinstance(item.get("session_id"), str):
                raise ValidationError("capture mapping entries must contain a session_id object")
            mappings[str(key)] = dict(item)
        return mappings

    def _write_mappings(self, value: Mapping[str, Any]) -> None:
        atomic_replace_json(self.mapping_path, dict(value))

    def _lifecycle_snapshot(self, session_id: str, *, host: str | None = None, host_session_id: str | None = None) -> dict[str, Any]:
        session = self.vault.read_session(session_id)
        turns = self.vault.list_turns(session_id)
        runtime = dict(session.get("runtime") or {})
        if host_session_id is None:
            host_session_id = runtime.get("host_session_id")
        if host is None:
            host = runtime.get("host")
        entries = [entry for entry in self.vault.all_current_entries() if entry.session_id == session_id]
        if runtime.get("capture_status") == "active":
            lifecycle = "active_capture"
            message = "Capture is active; raw turns are being saved."
        elif entries:
            lifecycle = "committed"
            message = "Structured entry is committed; raw turns remain preserved."
        elif runtime.get("commit_status") == "pending_auto_commit" or (
            session.get("ended_at") is None and runtime.get("capture_status") in {"recoverable", "rolled_over"}
        ):
            lifecycle = "recoverable_raw"
            message = "Capture is inactive; raw turns are preserved and the structured commit is pending."
        elif runtime.get("capture_status") == "imported":
            lifecycle = "imported"
            message = "Imported raw transcript is preserved; no structured entry has been committed."
        elif runtime.get("commit_status") == "no_new_evidence":
            lifecycle = "closed_no_new_evidence"
            message = "Capture is closed; no new structured evidence was committed."
        elif runtime.get("commit_status") in {"auto_commit_failed", "pending_auto_commit"}:
            lifecycle = "recoverable_raw"
            message = "Raw turns are safe; the structured commit still needs attention."
        elif session.get("ended_at") is not None:
            lifecycle = "closed_uncommitted"
            message = "Capture is closed; raw turns are preserved but no structured entry is committed."
        else:
            lifecycle = "inactive"
            message = "Work Brain capture is inactive for this host session; no raw turns are being saved."
        last = turns[-1] if turns else None
        return {
            "lifecycle": lifecycle,
            "capture_status": runtime.get("capture_status", "not_captured"),
            "commit_status": "committed" if entries else runtime.get("commit_status"),
            "turn_count": len(turns),
            "last_captured_at": last.get("recorded_at") if last else None,
            "host": host,
            "host_session_id": host_session_id,
            "message": message,
        }

    def rollover_stale_sessions(self, *, reference_at: str | None = None) -> list[dict[str, Any]]:
        """Close stale host capture boundaries without discarding raw turns.

        A session is eligible only when its host explicitly reported a
        recoverable/end condition and its mapping is no longer active.  The
        strict ``> 1`` calendar-day threshold deliberately leaves yesterday's
        session alone around midnight, where a user may simply be continuing
        work across the date boundary.
        """
        reference_at = reference_at or timestamp_now()
        reference_date = date.fromisoformat(date_for_timestamp(reference_at))
        with self.vault.write_lock():
            mappings = self._read_mappings()
            mapped_ids = {mapping["session_id"] for mapping in mappings.values()}
            rolled: list[dict[str, Any]] = []
            for session in self.vault.all_sessions():
                if session["session_id"] in mapped_ids:
                    continue
                runtime = dict(session.get("runtime") or {})
                if runtime.get("commit_status") not in {"pending_auto_commit", "auto_commit_failed"}:
                    continue
                age_days = (reference_date - date.fromisoformat(session["local_date"])).days
                if age_days <= 1:
                    continue
                if runtime.get("capture_status") != "rolled_over":
                    turns = self.vault.list_turns(session["session_id"])
                    runtime.update({
                        "capture_status": "rolled_over",
                        "capture_boundary": "closed",
                        "rollover_reason": "stale_prior_day",
                        "rollover_at": reference_at,
                        "commit_status": "pending_auto_commit" if turns else "no_new_evidence",
                    })
                    session["runtime"] = runtime
                    session["ended_at"] = session.get("ended_at") or reference_at
                    self.vault.update_session_metadata(session["session_id"], session)
                turns = self.vault.list_turns(session["session_id"])
                rolled.append({
                    "session_id": session["session_id"],
                    "entry_id": session["entry_id"],
                    "local_date": session["local_date"],
                    "age_days": age_days,
                    "turn_count": len(turns),
                    "status": "pending_auto_commit" if turns else "no_new_evidence",
                })
            return rolled

    def handle(self, event: CaptureEvent) -> dict[str, Any]:
        with self.vault.write_lock():
            mappings = self._read_mappings()
            key = f"{event.host}:{event.host_session_id}"
            mapping = mappings.get(key)
            if event.kind == "session_start":
                return {
                    "captured": False,
                    "status": "ready",
                    "lifecycle": "inactive",
                    "message": "Work Brain is available but capture is inactive until explicitly activated.",
                    "host": event.host,
                    "host_session_id": event.host_session_id,
                }
            if event.kind == "user_prompt":
                if mapping is None and not event.explicit_activation:
                    return {
                        "captured": False,
                        "status": "inactive",
                        "lifecycle": "inactive",
                        "message": "Work Brain capture is inactive for this host session; no raw turns are being saved. Say ‘capture this’ to resume.",
                        "host": event.host,
                        "host_session_id": event.host_session_id,
                    }
                rollover = self.rollover_stale_sessions(reference_at=event.recorded_at) if mapping is None else []
                if mapping is None:
                    workflow = event.workflow_hint or select_workflow(event.text)
                    session = self.vault.create_session(
                        started_at=event.recorded_at,
                        modes=[workflow],
                        runtime={
                            "host": event.host,
                            "host_session_id": event.host_session_id,
                            "host_model": event.host_model,
                            "capture_fidelity": "verbatim",
                            "capture_activation": "explicit",
                            "activation_trigger": event.text,
                            "capture_status": "active",
                            "workflow": workflow,
                            "lifecycle_action": event.lifecycle,
                        },
                    )
                    session_id = session["session_id"]
                    mappings[key] = {"session_id": session_id, "host": event.host, "host_session_id": event.host_session_id, "workflow": workflow}
                    mapping = mappings[key]
                else:
                    session_id = mapping["session_id"]
                    workflow = mapping.get("workflow") or (self.vault.read_session(session_id).get("runtime") or {}).get("workflow")
                self.vault.append_turn(session_id, "user", event.text or "", recorded_at=event.recorded_at)
                requested_workflow = event.workflow_hint
                if requested_workflow:
                    session = self.vault.read_session(session_id)
                    session.setdefault("runtime", {}).update({"workflow": requested_workflow, "lifecycle_request": event.text})
                    self.vault.update_session_metadata(session_id, session)
                    mapping["workflow"] = requested_workflow
                if event.lifecycle:
                    session = self.vault.read_session(session_id)
                    session.setdefault("runtime", {}).update({
                        "lifecycle_request": event.text,
                        "lifecycle_action": event.lifecycle,
                    })
                    self.vault.update_session_metadata(session_id, session)
                    mapping["lifecycle"] = event.lifecycle
                self._write_mappings(mappings)
                result = {
                    "captured": True,
                    "status": "active",
                    "session_id": session_id,
                    "role": "user",
                    "workflow": requested_workflow or workflow,
                    **self._lifecycle_snapshot(session_id, host=event.host, host_session_id=event.host_session_id),
                }
                if rollover:
                    result["rolled_over"] = rollover
                return result
            if mapping is None:
                return {"captured": False, "status": "inactive", "host": event.host, "host_session_id": event.host_session_id}
            session_id = mapping["session_id"]
            if event.kind == "assistant_message":
                self.vault.append_turn(session_id, "assistant", event.text or "", recorded_at=event.recorded_at)
                if mapping.get("workflow") == "close-day" or mapping.get("lifecycle") == "deactivate":
                    self._deactivate_mapping(mappings, key, session_id, status="closed")
                    return {
                        "captured": True,
                        "status": "closed",
                        "deactivated": True,
                        "session_id": session_id,
                        "role": "assistant",
                        "workflow": "close-day",
                        **self._lifecycle_snapshot(session_id, host=event.host, host_session_id=event.host_session_id),
                    }
                return {
                    "captured": True,
                    "status": "active",
                    "session_id": session_id,
                    "role": "assistant",
                    **self._lifecycle_snapshot(session_id, host=event.host, host_session_id=event.host_session_id),
                }
            if event.kind in {"session_end", "interrupt"}:
                self._deactivate_mapping(mappings, key, session_id, status="recoverable")
                return {
                    "captured": False,
                    "status": "recoverable",
                    "session_id": session_id,
                    "event": event.kind,
                    **self._lifecycle_snapshot(session_id, host=event.host, host_session_id=event.host_session_id),
                }
            raise ValidationError(f"unsupported normalized capture event: {event.kind}")

    def stop(self, *, host: str, host_session_id: str, session_id: str | None = None) -> dict[str, Any]:
        with self.vault.write_lock():
            mappings = self._read_mappings()
            key = f"{host}:{host_session_id}"
            mapping = mappings.get(key)
            if mapping is None:
                return {"deactivated": False, "status": "inactive", "host": host, "host_session_id": host_session_id}
            actual_session = mapping["session_id"]
            if session_id is not None and session_id != actual_session:
                raise ValidationError("session_id does not match active host capture mapping")
            self._deactivate_mapping(mappings, key, actual_session, status="closed")
            return {"deactivated": True, "status": "closed", "session_id": actual_session}

    def stop_session(self, session_id: str) -> dict[str, Any]:
        """Deactivate any host mapping for a session on an explicit stop."""
        with self.vault.write_lock():
            mappings = self._read_mappings()
            matches = [key for key, mapping in mappings.items() if mapping.get("session_id") == session_id]
            for key in matches:
                self._deactivate_mapping(mappings, key, session_id, status="closed")
            return {"deactivated": bool(matches), "status": "closed", "session_id": session_id}

    def import_transcript(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Import an explicitly supplied transcript without merging it into a live session."""
        if not isinstance(payload, Mapping):
            raise ValidationError("transcript import must be a JSON object")
        raw_turns = payload.get("turns")
        if not isinstance(raw_turns, list) or not raw_turns:
            raise ValidationError("transcript import requires a non-empty turns list")
        turns: list[dict[str, Any]] = []
        for index, raw in enumerate(raw_turns, start=1):
            if not isinstance(raw, Mapping):
                raise ValidationError(f"transcript turn {index} must be an object")
            role = raw.get("role")
            content = raw.get("content")
            if role not in {"user", "assistant"}:
                raise ValidationError(f"transcript turn {index} role must be user or assistant")
            if not isinstance(content, str) or not content:
                raise ValidationError(f"transcript turn {index} content must be a non-empty string")
            recorded_at = raw.get("recorded_at")
            if recorded_at is not None:
                parse_timestamp(recorded_at, f"transcript turn {index}.recorded_at")
            turns.append({"role": role, "content": content, "recorded_at": recorded_at})
        if not any(turn["role"] == "user" for turn in turns):
            raise ValidationError("transcript import requires at least one user-authored turn")

        started_at = payload.get("started_at") or next((turn["recorded_at"] for turn in turns if turn["recorded_at"]), None) or timestamp_now()
        parse_timestamp(started_at, "transcript.started_at")
        modes = payload.get("modes", ["think"])
        domains = payload.get("domains", [])
        source = payload.get("source", "user-supplied transcript")
        if not isinstance(modes, list) or any(not isinstance(item, str) or not item.strip() for item in modes):
            raise ValidationError("transcript.modes must be a list of non-empty strings")
        if not isinstance(domains, list) or any(not isinstance(item, str) or not item.strip() for item in domains):
            raise ValidationError("transcript.domains must be a list of non-empty strings")
        if not isinstance(source, str) or not source.strip():
            raise ValidationError("transcript.source must be a non-empty string")
        workflow = payload.get("workflow", modes[0] if modes else "think")
        if not isinstance(workflow, str) or not workflow.strip():
            raise ValidationError("transcript.workflow must be a non-empty string")

        with self.vault.write_lock():
            imported_at = timestamp_now()
            session = self.vault.create_session(
                started_at=started_at,
                modes=modes,
                domains=domains,
                runtime={
                    "capture_status": "imported",
                    "capture_boundary": "closed",
                    "capture_fidelity": "imported",
                    "workflow": workflow,
                    "import_source": source.strip(),
                    "imported_at": imported_at,
                },
            )
            session_id = session["session_id"]
            for turn in turns:
                self.vault.append_turn(session_id, turn["role"], turn["content"], recorded_at=turn["recorded_at"] or imported_at)
            session["ended_at"] = imported_at
            self.vault.update_session_metadata(session_id, session)
            return {
                "session_id": session_id,
                "entry_id": session["entry_id"],
                "status": "imported",
                "capture_fidelity": "imported",
                "turn_count": len(turns),
                "raw_turns_preserved": True,
            }

    def rotate_session(self, session_id: str) -> dict[str, Any]:
        """Start the next bounded session while keeping the host capture active.

        A CommitDraft ends the logical session, but ordinary Work Brain commits
        must not force the user to repeat the activation phrase. The mapping is
        therefore advanced to a new source session with fresh entry identity.
        """
        with self.vault.write_lock():
            mappings = self._read_mappings()
            matches = [(key, mapping) for key, mapping in mappings.items()
                       if mapping.get("session_id") == session_id]
            if not matches:
                return {"rotated": False, "status": "inactive", "session_id": session_id}
            key, mapping = matches[0]
            previous = self.vault.read_session(session_id)
            runtime = dict(previous.get("runtime") or {})
            runtime.pop("commit_status", None)
            runtime.pop("capture_boundary", None)
            runtime.update({
                "capture_status": "active",
                "capture_boundary": "open",
                "capture_continuation": True,
                "previous_session_id": session_id,
                "capture_activation": "continued",
            })
            next_session = self.vault.create_session(
                modes=list(previous.get("modes", [])),
                domains=list(previous.get("domains", [])),
                runtime=runtime,
            )
            previous_runtime = dict(previous.get("runtime") or {})
            previous_runtime.update({
                "capture_status": "committed",
                "capture_boundary": "closed",
                "capture_continuation_to": next_session["session_id"],
            })
            previous["runtime"] = previous_runtime
            self.vault.update_session_metadata(session_id, previous)
            mappings[key] = {
                **mapping,
                "session_id": next_session["session_id"],
                "workflow": runtime.get("workflow") or mapping.get("workflow"),
                "previous_session_id": session_id,
            }
            self._write_mappings(mappings)
            return {
                "rotated": True,
                "status": "active",
                "previous_session_id": session_id,
                "session_id": next_session["session_id"],
                "host": mapping.get("host"),
                "host_session_id": mapping.get("host_session_id"),
            }

    def _deactivate_mapping(self, mappings: dict[str, dict[str, Any]], key: str, session_id: str, *, status: str) -> None:
        try:
            session = self.vault.read_session(session_id)
            runtime = session.setdefault("runtime", {})
            runtime.update({"capture_status": status, "capture_boundary": "closed"})
            turns = self.vault.list_turns(session_id)
            if turns:
                runtime.setdefault("commit_status", "pending_auto_commit")
            else:
                runtime["commit_status"] = "no_new_evidence"
            if session.get("ended_at") is None:
                session["ended_at"] = timestamp_now()
            self.vault.update_session_metadata(session_id, session)
        finally:
            mappings.pop(key, None)
            self._write_mappings(mappings)
