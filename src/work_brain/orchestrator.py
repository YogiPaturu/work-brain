from __future__ import annotations

from dataclasses import dataclass
import json
from enum import Enum
import re
import unicodedata
from typing import Any, Mapping

from .commit import CommitResolver
from .errors import PersistenceError, ValidationError
from .instructions import LoadedInstructions, SkillLoader, WORKFLOWS
from .model import ConversationModel, ModelResponse
from .timeutil import timestamp_now
from .tools import ToolRegistry, ToolResult


class RuntimeState(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    COMMITTING = "committing"
    COMMITTED = "committed"
    RECOVERABLE = "recoverable"


@dataclass(frozen=True)
class PromptRoute:
    """Routing metadata derived from a prompt without changing its raw text."""

    raw: str
    activation: bool
    routed_content: str
    normalized_content: str
    workflow: str
    recognized: bool


# Keep this table as the single conversational control vocabulary. Matching is
# anchored at the beginning of normalized content, so ordinary sentences do
# not become commands merely because they contain a related word.
WORKFLOW_ALIASES: tuple[tuple[str, str], ...] = (
    ("open my work journal", "open-day"),
    ("start my day", "open-day"),
    ("start work brain", "think"),
    ("open day", "open-day"),
    ("close my day", "close-day"),
    ("finish my day", "close-day"),
    ("wrap up my day", "close-day"),
    ("close day", "close-day"),
    ("help me think through", "think"),
    ("challenge my thinking", "think"),
    ("think with me", "think"),
    ("capture this", "think"),
    ("journal this", "think"),
    ("think", "think"),
    ("reason", "think"),
    ("where did i leave off", "operate"),
    ("where was i", "operate"),
    ("what should i work on next", "operate"),
    ("what should i work on", "operate"),
    ("what am i working on", "operate"),
    ("catch me up", "operate"),
    ("give me a quick update", "operate"),
    ("quick update", "operate"),
    ("plan my work", "operate"),
    ("what should i do", "operate"),
    ("operate", "operate"),
    ("draft a message", "communicate"),
    ("communicate", "communicate"),
    ("practice this interview question", "career"),
    ("help me prepare for", "career"),
    ("interview me", "career"),
    ("practice interview", "career"),
    ("career", "career"),
    ("remember a past experience", "backfill"),
    ("backfill", "backfill"),
)

# These are deliberately explicit activation aliases. Other recognized
# workflow phrases route only after Work Brain is already active or after an
# explicit `work brain` prefix.
NATURAL_ACTIVATION_ALIASES = frozenset({"start my day", "open my work journal", "start work brain", "capture this", "journal this"})


def normalize_routing_text(value: str) -> str:
    """Normalize only command/routing text; never use this for persistence."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.strip().split())


def _strip_work_brain_prefix(raw: str) -> tuple[bool, str]:
    candidate = raw.strip()
    match = re.match(r"(?:[/\$])?work(?:\s+|-)brain(?=$|[^\w])", candidate, flags=re.IGNORECASE)
    if not match:
        return False, raw
    remainder = candidate[match.end():]
    # Punctuation immediately after the spoken prefix is a delimiter, not
    # content. Preserve all later punctuation and, importantly, preserve raw
    # input separately for L0 evidence.
    remainder = re.sub(r"^[\s,.:;!?/\\|_\-–—]+", "", remainder)
    return True, remainder


def _workflow_for_normalized(normalized: str, current: str | None = None) -> tuple[str, bool]:
    for phrase, workflow in sorted(WORKFLOW_ALIASES, key=lambda item: len(item[0]), reverse=True):
        if normalized == phrase or normalized.startswith(phrase + " "):
            return workflow, True
    if current in WORKFLOWS:
        return current, False
    return "think", False


def route_prompt(intent: str | None, current: str | None = None) -> PromptRoute:
    raw = intent if isinstance(intent, str) else ""
    activation, routed = _strip_work_brain_prefix(raw)
    normalized = normalize_routing_text(routed)
    workflow, recognized = _workflow_for_normalized(normalized, current)
    if not activation and normalized in NATURAL_ACTIVATION_ALIASES:
        activation = True
    return PromptRoute(raw=raw, activation=activation, routed_content=routed, normalized_content=normalized, workflow=workflow, recognized=recognized)


# Backwards-compatible alias mapping for callers that imported the old table.
ALIASES = dict(WORKFLOW_ALIASES)


def select_workflow(intent: str | None, current: str | None = None) -> str:
    return route_prompt(intent, current).workflow


@dataclass(frozen=True)
class ContextPlan:
    estimated_input_tokens: int
    usable_input_tokens: int
    rollover: bool


class ContextPlanner:
    def plan(self, messages: list[Mapping[str, Any]], instructions: str, model: ConversationModel) -> ContextPlan:
        estimated = (len(instructions) + sum(len(message.get("content", "")) for message in messages)) // 4
        usable = max(model.context_window - model.output_reserve, 1)
        return ContextPlan(estimated, usable, estimated >= int(usable * 0.70))


class SessionOrchestrator:
    """Coordinates a bounded session without embedding provider-specific behavior."""

    MAX_TOOL_ROUNDS = 8

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
        self._messages: list[dict[str, Any]] = []
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
        route = route_prompt(user_text, self.workflow)
        if route.recognized and route.workflow != self.workflow:
            self.workflow = route.workflow
            self.instructions = self.loader.load(self.workflow, self._domains)
            self._modes = self._merge(self._modes, [self.workflow])
            session = self.vault.read_session(self.session_id)
            session["modes"] = self._merge(session.get("modes", []), [self.workflow])
            session.setdefault("runtime", {}).update({
                "workflow": self.workflow,
                "sops": self.instructions.identities,
                "missing_resources": list(self.instructions.missing),
            })
            self.vault.update_session_metadata(self.session_id, session)
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
        # A soft rollover threshold is useful once context exists, but a new
        # session must be allowed to accept its first bounded user turn when
        # the instructions alone put it near that threshold. Only a hard
        # context overflow is rejected here.
        if plan.estimated_input_tokens > plan.usable_input_tokens:
            raise PersistenceError("context budget reached; close and roll over before adding another turn")
        try:
            response = self._respond_with_tools()
        except Exception:
            self.state = RuntimeState.RECOVERABLE
            raise
        if response.text:
            self.vault.append_turn(self.session_id, "assistant", response.text)
            self._messages.append({"role": "assistant", "content": response.text})
        return response

    def _respond_with_tools(self) -> ModelResponse:
        """Run the bounded model/tool loop for one persisted user turn."""
        if self.instructions is None or self.workflow is None:
            raise ValidationError("session instructions are not loaded")
        available = tuple(tool.name for tool in self.tools.definitions(self.workflow))
        allowed = set(available)
        for _round in range(self.MAX_TOOL_ROUNDS):
            plan = self.context_planner.plan(self._messages, self.instructions.text, self.model)
            if plan.estimated_input_tokens > plan.usable_input_tokens:
                raise PersistenceError("context budget reached during model/tool loop")
            response = self.model.respond(
                self._messages, instructions=self.instructions.text, tools=available,
            )
            if not response.tool_calls:
                return response

            self._messages.append({
                "role": "assistant", "content": response.text,
                "tool_calls": [dict(call) if isinstance(call, Mapping) else {"raw": str(call)} for call in response.tool_calls],
            })
            for index, raw_call in enumerate(response.tool_calls):
                call_id, name, arguments, validation_error = self._normalize_tool_call(raw_call, _round, index)
                if validation_error:
                    result = ToolResult(False, error=validation_error)
                elif name not in allowed:
                    result = ToolResult(False, error=f"tool is not available in workflow: {name}")
                else:
                    try:
                        result = self.tools.call(name, **arguments)
                    except Exception as exc:
                        result = ToolResult(False, error=f"tool execution failed: {exc}")
                self._messages.append({
                    "role": "tool", "tool_call_id": call_id, "name": name or "unknown",
                    "content": json.dumps(result.to_dict(), ensure_ascii=False, default=str),
                })
        raise ValidationError(f"model/tool loop exceeded {self.MAX_TOOL_ROUNDS} rounds")

    @staticmethod
    def _normalize_tool_call(raw_call: Any, round_number: int, index: int) -> tuple[str, str, dict[str, Any], str | None]:
        """Normalize the provider-neutral tool-call shape used by the model port."""
        if not isinstance(raw_call, Mapping):
            return f"tool-call-{round_number}-{index}", "", {}, "tool call must be an object"
        function = raw_call.get("function")
        source = function if isinstance(function, Mapping) else raw_call
        name = source.get("name")
        arguments = source.get("arguments", {})
        call_id = str(raw_call.get("id") or f"tool-call-{round_number}-{index}")
        if not isinstance(name, str) or not name.strip():
            return call_id, "", {}, "tool call name must be a non-empty string"
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                return call_id, name, {}, "tool call arguments must be valid JSON"
        if not isinstance(arguments, Mapping):
            return call_id, name, {}, "tool call arguments must be an object"
        return call_id, name, dict(arguments), None

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

    def complete_without_commit(self) -> None:
        """Finish close-day when the gap check produced no new evidence.

        Closing a Work Brain workflow and publishing a SessionEntry are
        separate decisions.  The host capture adapter deactivates its mapping
        independently; this method records the completed bounded session
        without manufacturing a CommitDraft.
        """
        if self.state != RuntimeState.ACTIVE or self.session_id is None or self.workflow != "close-day":
            raise ValidationError("only an active close-day session can complete without a commit")
        session = self.vault.read_session(self.session_id)
        session["ended_at"] = timestamp_now()
        session.setdefault("runtime", {}).update({"workflow": "close-day", "commit_status": "no_new_evidence", "capture_status": "closed"})
        self.vault.update_session_metadata(self.session_id, session)
        self.state = RuntimeState.COMMITTED

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
