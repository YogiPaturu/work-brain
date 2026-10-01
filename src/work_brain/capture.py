from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from .errors import ValidationError
from .fsutil import atomic_replace_json, ensure_private_file, read_json
from .orchestrator import PromptRoute, route_prompt, select_workflow
from .timeutil import timestamp_now


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

    def handle(self, event: CaptureEvent) -> dict[str, Any]:
        with self.vault.write_lock():
            mappings = self._read_mappings()
            key = f"{event.host}:{event.host_session_id}"
            mapping = mappings.get(key)
            if event.kind == "session_start":
                return {"captured": False, "status": "ready", "host": event.host, "host_session_id": event.host_session_id}
            if event.kind == "user_prompt":
                if mapping is None and not event.explicit_activation:
                    return {"captured": False, "status": "inactive", "host": event.host, "host_session_id": event.host_session_id}
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
                return {"captured": True, "status": "active", "session_id": session_id, "role": "user", "workflow": requested_workflow or workflow}
            if mapping is None:
                return {"captured": False, "status": "inactive", "host": event.host, "host_session_id": event.host_session_id}
            session_id = mapping["session_id"]
            if event.kind == "assistant_message":
                self.vault.append_turn(session_id, "assistant", event.text or "", recorded_at=event.recorded_at)
                if mapping.get("workflow") == "close-day" or mapping.get("lifecycle") == "deactivate":
                    self._deactivate_mapping(mappings, key, session_id, status="closed")
                    return {"captured": True, "status": "closed", "deactivated": True, "session_id": session_id, "role": "assistant", "workflow": "close-day"}
                return {"captured": True, "status": "active", "session_id": session_id, "role": "assistant"}
            if event.kind in {"session_end", "interrupt"}:
                self._deactivate_mapping(mappings, key, session_id, status="recoverable")
                return {"captured": False, "status": "recoverable", "session_id": session_id, "event": event.kind}
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
            runtime.update({
                "capture_status": "active",
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
            session.setdefault("runtime", {}).update({"capture_status": status})
            if status == "closed" and session.get("ended_at") is None:
                session["ended_at"] = timestamp_now()
            self.vault.update_session_metadata(session_id, session)
        finally:
            mappings.pop(key, None)
            self._write_mappings(mappings)
