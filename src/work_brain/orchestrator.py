from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .commit import CommitResolver
from .errors import PersistenceError, ValidationError
from .instructions import LoadedInstructions, SkillLoader, WORKFLOWS
from .model import ConversationModel, ModelResponse
from .timeutil import timestamp_now
from .tools import ToolRegistry


class RuntimeState(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    COMMITTING = "committing"
    COMMITTED = "committed"
    RECOVERABLE = "recoverable"


ALIASES = {
    "think": "think", "think with me": "think", "reason": "think",
    "operate": "operate", "plan my work": "operate", "what should i do": "operate",
    "communicate": "communicate", "draft a message": "communicate",
    "career": "career", "practice interview": "career",
    "open day": "open-day", "start my day": "open-day",
    "close day": "close-day", "close my day": "close-day",
    "backfill": "backfill", "remember a past experience": "backfill",
}


def select_workflow(intent: str | None, current: str | None = None) -> str:
    if intent:
        normalized = " ".join(intent.casefold().strip().split())
        if normalized in ALIASES:
            return ALIASES[normalized]
        for phrase, workflow in sorted(ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
            if phrase in normalized:
                return workflow
    if current in WORKFLOWS:
        return current
    return "think"


@dataclass(frozen=True)
class ContextPlan:
    estimated_input_tokens: int
    usable_input_tokens: int
    rollover: bool


class ContextPlanner:
    def plan(self, messages: list[Mapping[str, str]], instructions: str, model: ConversationModel) -> ContextPlan:
        estimated = (len(instructions) + sum(len(message.get("content", "")) for message in messages)) // 4
        usable = max(model.context_window - model.output_reserve, 1)
        return ContextPlan(estimated, usable, estimated >= int(usable * 0.70))


class SessionOrchestrator:
    """Coordinates a bounded session without embedding provider-specific behavior."""

    def __init__(self, vault: Any, model: ConversationModel, *, loader: SkillLoader | None = None,
                 tools: ToolRegistry | None = None, resolver: CommitResolver | None = None):
        self.vault = vault
        self.model = model
        self.loader = loader or SkillLoader()
        self.tools = tools or ToolRegistry(vault)
        self.resolver = resolver or CommitResolver(vault)
        self.context_planner = ContextPlanner()
        self.state = RuntimeState.IDLE
        self.session_id: str | None = None
        self.workflow: str | None = None
        self.instructions: LoadedInstructions | None = None
        self._messages: list[dict[str, str]] = []
        self._modes: list[str] = []
        self._domains: list[str] = []

    def start(self, user_text: str | None = None, *, workflow: str | None = None,
              domains: list[str] | None = None, started_at: str | None = None) -> dict[str, Any]:
        if self.state not in {RuntimeState.IDLE, RuntimeState.COMMITTED, RuntimeState.RECOVERABLE}:
            raise ValidationError("a session is already active")
        self.workflow = select_workflow(workflow or user_text, None)
        self._domains = list(domains or [])
        self.instructions = self.loader.load(self.workflow, self._domains)
        self._modes = [self.workflow]
        session = self.vault.create_session(
            started_at=started_at, modes=self._modes, domains=self._domains,
            runtime={"model": self.model.model_id, "app_revision": "lld2-v1", "workflow": self.workflow,
                     "sops": self.instructions.identities, "missing_resources": list(self.instructions.missing)},
        )
        self.session_id = session["session_id"]
        self._messages = []
        self.state = RuntimeState.ACTIVE
        if user_text:
            self.turn(user_text)
        return session

    def turn(self, user_text: str) -> ModelResponse:
        if self.state != RuntimeState.ACTIVE or self.session_id is None or self.instructions is None or self.workflow is None:
            raise ValidationError("session is not active")
        if not isinstance(user_text, str) or not user_text.strip():
            raise ValidationError("user_text must be non-empty")
        # Rollover happens before this user turn is appended so the new turn is
        # never split between the old and new bounded contexts.
        candidate_messages = self._messages + [{"role": "user", "content": user_text}]
        plan = self.context_planner.plan(candidate_messages, self.instructions.text, self.model)
        if plan.rollover and self._messages:
            self.close()
            self.start(workflow=self.workflow, domains=self._domains)
            return self.turn(user_text)
        # This append is deliberately before any model invocation.
        self.vault.append_turn(self.session_id, "user", user_text)
        self._messages.append({"role": "user", "content": user_text})
        if plan.rollover:
            raise PersistenceError("context budget reached; close and roll over before adding another turn")
        try:
            response = self.model.respond(
                self._messages, instructions=self.instructions.text,
                tools=[tool.name for tool in self.tools.definitions(self.workflow)],
            )
        except Exception:
            self.state = RuntimeState.RECOVERABLE
            raise
        if response.text:
            self.vault.append_turn(self.session_id, "assistant", response.text)
            self._messages.append({"role": "assistant", "content": response.text})
        return response

    def close(self) -> Any:
        if self.state != RuntimeState.ACTIVE or self.session_id is None or self.instructions is None or self.workflow is None:
            raise ValidationError("session is not active")
        self.state = RuntimeState.COMMITTING
        try:
            draft = self.model.emit_commit_draft(self._messages, instructions=self.instructions.text)
            last_error = ""
            for attempt in range(3):
                try:
                    entry = self.resolver.publish(self.session_id, draft, workflow=self.workflow)
                    session = self.vault.read_session(self.session_id)
                    session["modes"] = self._merge(session.get("modes", []), self._modes)
                    session["domains"] = self._merge(session.get("domains", []), self._domains)
                    session.setdefault("runtime", {}).update({"model": self.model.model_id, "sops": self.instructions.identities,
                                                               "workflow": self.workflow, "commit_attempts": attempt + 1,
                                                               "commit_status": "committed"})
                    self.vault.update_session_metadata(self.session_id, session)
                    self.state = RuntimeState.COMMITTED
                    return entry
                except ValidationError as exc:
                    last_error = str(exc)
                    if attempt == 2:
                        raise
                    draft = self.model.repair_commit_draft(draft, last_error, instructions=self.instructions.text)
            raise ValidationError(last_error or "CommitDraft validation failed")
        except Exception:
            self.state = RuntimeState.RECOVERABLE
            raise

    def recoverable_sessions(self) -> list[dict[str, Any]]:
        return [session for session in self.vault.all_sessions() if session.get("ended_at") is None]

    def resume(self, session_id: str, *, workflow: str | None = None) -> dict[str, Any]:
        """Reconstruct an unfinished session without replaying model calls."""
        if self.state not in {RuntimeState.IDLE, RuntimeState.COMMITTED, RuntimeState.RECOVERABLE}:
            raise ValidationError("a session is already active")
        session = self.vault.read_session(session_id)
        if session.get("ended_at") is not None:
            raise ValidationError("only an unfinished session can be resumed")
        self.session_id = session_id
        self.workflow = select_workflow(workflow, (session.get("runtime") or {}).get("workflow"))
        self._modes = list(session.get("modes", [])) or [self.workflow]
        self._domains = list(session.get("domains", []))
        self.instructions = self.loader.load(self.workflow, self._domains)
        self._messages = [{"role": turn["role"], "content": turn["content"]} for turn in self.vault.list_turns(session_id)]
        self.state = RuntimeState.ACTIVE
        return session

    def reextract(self, session_id: str, *, workflow: str | None = None) -> Any:
        """Explicitly create a new revision from immutable raw turns."""
        session = self.vault.read_session(session_id)
        chosen = select_workflow(workflow, (session.get("runtime") or {}).get("workflow"))
        instructions = self.loader.load(chosen, session.get("domains", []))
        messages = [{"role": turn["role"], "content": turn["content"]} for turn in self.vault.list_turns(session_id)]
        draft = self.model.emit_commit_draft(messages, instructions=instructions.text)
        for attempt in range(3):
            try:
                entry = self.resolver.publish(session_id, draft, workflow=chosen, revision_reason="reextract")
                current = self.vault.read_session(session_id)
                current.setdefault("runtime", {}).update({"model": self.model.model_id, "sops": instructions.identities,
                                                           "workflow": chosen, "commit_attempts": attempt + 1,
                                                           "commit_status": "reextracted"})
                self.vault.update_session_metadata(session_id, current)
                return entry
            except ValidationError as exc:
                if attempt == 2:
                    raise
                draft = self.model.repair_commit_draft(draft, str(exc), instructions=instructions.text)
        raise ValidationError("re-extraction failed")

    def recover(self, session_id: str) -> dict[str, Any]:
        session = self.vault.read_session(session_id)
        if session.get("ended_at") is not None:
            return session
        if any(entry.session_id == session_id for entry in self.vault.all_current_entries()):
            entry = next(entry for entry in self.vault.all_current_entries() if entry.session_id == session_id)
            session["ended_at"] = entry.created_at
            session.setdefault("runtime", {})["recovery"] = "finalized_published_entry"
            self.vault.update_session_metadata(session_id, session)
            return self.vault.read_session(session_id)
        return session

    def _merge(self, *groups: list[str]) -> list[str]:
        result: list[str] = []
        for group in groups:
            for item in group:
                if item not in result:
                    result.append(item)
        return result
