from __future__ import annotations

from dataclasses import dataclass
import json
from enum import Enum
from typing import Any, Mapping

from .commit import CommitResolver
from .errors import PersistenceError, ValidationError
from .instructions import LoadedInstructions, SkillLoader, WORKFLOWS
from .lifecycle import CaptureLifecycle, CommitLifecycle, transition
from .model import ConversationModel, ModelResponse
from .routing import ALIASES, PromptRoute, WORKFLOW_ALIASES, normalize_routing_text, route_prompt, select_workflow
from .timeutil import timestamp_now
from .tools import ToolRegistry, ToolResult


class RuntimeState(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    COMMITTING = "committing"
    COMMITTED = "committed"
    RECOVERABLE = "recoverable"


@dataclass(frozen=True)
class ContextPlan:
    estimated_input_tokens: int
    usable_input_tokens: int
    rollover: bool


class ContextPlanner:
    def plan(self, messages: list[Mapping[str, Any]], instructions: str, model: ConversationModel) -> ContextPlan:
        estimated = (len(instructions) + sum(len(message.get("content", "")) for message in messages)) // 4
        usable = max(model.context_window - model.output_reserve, 1)
        # Keep enough headroom for the next model response without making the
        # bounded-session threshold overly sensitive to compact SOP wording.
        return ContextPlan(estimated, usable, estimated >= int(usable * 0.85))


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
        self._domain_tags: list[str] = []
        self.profile_id: str | None = None
        self.last_rollover_commits: list[dict[str, Any]] = []

    def start(self, user_text: str | None = None, *, workflow: str | None = None,
              domain_tags: list[str] | None = None, started_at: str | None = None,
              profile_id: str | None = None) -> dict[str, Any]:
        if self.state not in {RuntimeState.IDLE, RuntimeState.COMMITTED, RuntimeState.RECOVERABLE}:
            raise ValidationError("a session is already active")
        self.workflow = select_workflow(workflow or user_text, None)
        if profile_id is not None and self.workflow != "communicate":
            raise ValidationError("profile_id can only be used with workflow=communicate")
        self.profile_id = profile_id
        self.tools.activate_profile(profile_id)
        self._domain_tags = list(domain_tags or [])
        self.instructions = self.loader.load(self.workflow, self._domain_tags)
        self._modes = [self.workflow]
        # Host capture closes raw boundaries even when the host/model exits
        # before it can emit a CommitDraft.  Resolve stale boundaries before
        # opening the next logical session so a live start is the durable
        # recovery point rather than another source of duplicates.
        from .capture import HarnessCaptureService
        HarnessCaptureService(self.vault).rollover_stale_sessions(reference_at=started_at)
        self.last_rollover_commits = self._commit_pending_rollovers()
        session = self.vault.create_session(
            started_at=started_at, modes=self._modes, domain_tags=self._domain_tags,
            runtime={"model": self.model.model_id, "app_revision": "runtime-v1", "workflow": self.workflow,
                     "sops": self.instructions.identities, "missing_resources": list(self.instructions.missing),
                     "profile_id": self.profile_id},
        )
        self.session_id = session["session_id"]
        self._messages = []
        self.state = RuntimeState.ACTIVE
        if user_text:
            self.turn(user_text)
        return session

    def _commit_pending_rollovers(self) -> list[dict[str, Any]]:
        """Commit stale capture sessions before opening a new live session.

        The capture layer marks only inactive sessions older than the strict
        calendar-day threshold. This method is the model-aware half of the
        handoff; failures leave the raw session in place for another attempt.
        """
        results: list[dict[str, Any]] = []
        pending = []
        committed_session_ids = {entry.session_id for entry in self.vault.all_current_entries()}
        for session in self.vault.all_sessions():
            if session["session_id"] in committed_session_ids:
                continue
            runtime = session.get("runtime") or {}
            explicitly_pending = (
                runtime.get("commit_status") == "pending_auto_commit"
                and runtime.get("capture_boundary") == "closed"
            )
            legacy_recoverable = (
                session.get("ended_at") is None
                and runtime.get("capture_status") in {"recoverable", "rolled_over"}
                and runtime.get("commit_status") is None
            )
            if explicitly_pending or legacy_recoverable:
                pending.append(session)
        for session in pending:
            session_id = session["session_id"]
            runtime = dict(session.get("runtime") or {})
            chosen = select_workflow(runtime.get("workflow"), (session.get("modes") or [None])[0])
            domain_tags = list(session.get("domain_tags", []))
            instructions = self.loader.load(chosen, domain_tags, include_commit_schema=True)
            messages = [{"role": turn["role"], "content": turn["content"]} for turn in self.vault.list_turns(session_id)]
            if not messages:
                self.vault.close_session(session_id, commit_status="no_new_evidence")
                results.append({"session_id": session_id, "status": "no_new_evidence"})
                continue
            try:
                draft = self.model.emit_commit_draft(messages, instructions=instructions.text)
                for attempt in range(3):
                    try:
                        entry = self.resolver.publish(session_id, draft, workflow=chosen, revision_reason="initial_commit")
                        current = self.vault.read_session(session_id)
                        runtime, _ = transition(
                            current.get("runtime"),
                            capture=CaptureLifecycle.CLOSED,
                            commit=CommitLifecycle.COMMITTED,
                            ended_at=current.get("ended_at"),
                            has_entry=True,
                        )
                        runtime.update({
                            "model": self.model.model_id,
                            "sops": instructions.identities,
                            "workflow": chosen,
                            "commit_attempts": attempt + 1,
                            "commit_status": "committed",
                            "capture_status": "closed",
                            "capture_boundary": "closed",
                        })
                        current["runtime"] = runtime
                        self.vault.update_session_metadata(session_id, current)
                        results.append({"session_id": session_id, "entry_id": entry.entry_id, "status": "committed"})
                        break
                    except ValidationError as exc:
                        if attempt == 2:
                            raise
                        draft = self.model.repair_commit_draft(draft, str(exc), instructions=instructions.text)
            except Exception as exc:
                current = self.vault.read_session(session_id)
                runtime, _ = transition(
                    current.get("runtime"),
                    commit=CommitLifecycle.FAILED,
                    ended_at=current.get("ended_at"),
                )
                runtime.update({
                    "commit_status": "auto_commit_failed",
                    "auto_commit_error": str(exc),
                })
                current["runtime"] = runtime
                self.vault.update_session_metadata(session_id, current)
                results.append({"session_id": session_id, "status": "recoverable", "error": str(exc)})
        return results

    def turn(self, user_text: str) -> ModelResponse:
        if self.state != RuntimeState.ACTIVE or self.session_id is None or self.instructions is None or self.workflow is None:
            raise ValidationError("session is not active")
        if not isinstance(user_text, str) or not user_text.strip():
            raise ValidationError("user_text must be non-empty")
        route = route_prompt(user_text, self.workflow)
        if route.recognized and route.workflow != self.workflow:
            self.workflow = route.workflow
            if self.workflow != "communicate":
                self.profile_id = None
                self.tools.activate_profile(None)
            self.instructions = self.loader.load(self.workflow, self._domain_tags)
            self._modes = self._merge(self._modes, [self.workflow])
            session = self.vault.read_session(self.session_id)
            session["modes"] = self._merge(session.get("modes", []), [self.workflow])
            session.setdefault("runtime", {}).update({
                "workflow": self.workflow,
                "sops": self.instructions.identities,
                "missing_resources": list(self.instructions.missing),
                "profile_id": self.profile_id,
            })
            self.vault.update_session_metadata(self.session_id, session)
        # Rollover happens before this user turn is appended so the new turn is
        # never split between the old and new bounded contexts.
        candidate_messages = self._messages + [{"role": "user", "content": user_text}]
        plan = self.context_planner.plan(candidate_messages, self.instructions.text, self.model)
        if plan.rollover and self._messages:
            self.close()
            self.start(workflow=self.workflow, domain_tags=self._domain_tags)
            return self.turn(user_text)
        # This append is deliberately before any model invocation.
        self.vault.append_turn(self.session_id, "user", user_text)
        self._messages.append({"role": "user", "content": user_text})
        # A soft rollover threshold is useful once context exists, but a new
        # session must be allowed to accept its first bounded user turn when
        # the instructions alone put it near that threshold. Only a hard
        # context overflow is rejected here.
        # A freshly rolled session must be allowed to accept its first bounded
        # user turn even when the instructions plus that turn are near the
        # provider limit. Subsequent turns still fail fast on hard overflow.
        if plan.estimated_input_tokens > plan.usable_input_tokens and len(self._messages) > 1:
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
            if plan.estimated_input_tokens > plan.usable_input_tokens and len(self._messages) > 1:
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
            commit_instructions = self.loader.load(self.workflow, self._domain_tags, include_commit_schema=True)
            draft = self.model.emit_commit_draft(self._messages, instructions=commit_instructions.text)
            last_error = ""
            for attempt in range(3):
                try:
                    entry = self.resolver.publish(self.session_id, draft, workflow=self.workflow)
                    session = self.vault.read_session(self.session_id)
                    session["modes"] = self._merge(session.get("modes", []), self._modes)
                    session["domain_tags"] = self._merge(session.get("domain_tags", []), self._domain_tags)
                    session.setdefault("runtime", {}).update({"model": self.model.model_id, "sops": commit_instructions.identities,
                                                               "workflow": self.workflow, "commit_attempts": attempt + 1,
                                                               "commit_status": "committed"})
                    self.vault.update_session_metadata(self.session_id, session)
                    self.state = RuntimeState.COMMITTED
                    return entry
                except ValidationError as exc:
                    last_error = str(exc)
                    if attempt == 2:
                        raise
                    draft = self.model.repair_commit_draft(draft, last_error, instructions=commit_instructions.text)
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
        runtime, _ = transition(
            session.get("runtime"),
            capture=CaptureLifecycle.CLOSED,
            commit=CommitLifecycle.NO_NEW_EVIDENCE,
            ended_at=session.get("ended_at"),
        )
        runtime.update({"workflow": "close-day", "commit_status": "no_new_evidence", "capture_status": "closed"})
        session["runtime"] = runtime
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
        self.profile_id = (session.get("runtime") or {}).get("profile_id")
        if self.profile_id is not None and self.workflow != "communicate":
            raise ValidationError("session profile_id requires workflow=communicate")
        self.tools.activate_profile(self.profile_id)
        self._modes = list(session.get("modes", [])) or [self.workflow]
        self._domain_tags = list(session.get("domain_tags", []))
        self.instructions = self.loader.load(self.workflow, self._domain_tags)
        self._messages = [{"role": turn["role"], "content": turn["content"]} for turn in self.vault.list_turns(session_id)]
        self.state = RuntimeState.ACTIVE
        return session

    def reextract(self, session_id: str, *, workflow: str | None = None) -> Any:
        """Explicitly create a new revision from immutable raw turns."""
        session = self.vault.read_session(session_id)
        chosen = select_workflow(workflow, (session.get("runtime") or {}).get("workflow"))
        instructions = self.loader.load(chosen, session.get("domain_tags", []), include_commit_schema=True)
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
