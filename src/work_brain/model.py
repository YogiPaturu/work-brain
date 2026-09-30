from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class ModelResponse:
    text: str
    tool_calls: tuple[dict[str, Any], ...] = ()


class ConversationModel(Protocol):
    model_id: str
    context_window: int
    output_reserve: int

    def respond(self, messages: Sequence[Mapping[str, Any]], *, instructions: str, tools: Sequence[str]) -> ModelResponse:
        ...

    def emit_commit_draft(self, messages: Sequence[Mapping[str, Any]], *, instructions: str) -> Mapping[str, Any]:
        ...

    def repair_commit_draft(self, draft: Mapping[str, Any], error: str, *, instructions: str) -> Mapping[str, Any]:
        ...


@dataclass
class ScriptedModel:
    """Provider-free model double used by tests and local adapter development."""

    drafts: list[Mapping[str, Any]] = field(default_factory=list)
    responses: list[str | ModelResponse] = field(default_factory=lambda: ["What matters most about this situation?"])
    repairs: list[Mapping[str, Any]] = field(default_factory=list)
    model_id: str = "scripted-work-brain"
    context_window: int = 16_000
    output_reserve: int = 2_000
    calls: list[dict[str, Any]] = field(default_factory=list)

    def respond(self, messages: Sequence[Mapping[str, Any]], *, instructions: str, tools: Sequence[str]) -> ModelResponse:
        self.calls.append({"kind": "respond", "message_count": len(messages), "tools": list(tools)})
        response = self.responses.pop(0) if self.responses else "What would you like to examine next?"
        return response if isinstance(response, ModelResponse) else ModelResponse(response)

    def emit_commit_draft(self, messages: Sequence[Mapping[str, Any]], *, instructions: str) -> Mapping[str, Any]:
        self.calls.append({"kind": "commit_draft", "message_count": len(messages)})
        if not self.drafts:
            raise RuntimeError("scripted model has no commit draft")
        return self.drafts.pop(0)

    def repair_commit_draft(self, draft: Mapping[str, Any], error: str, *, instructions: str) -> Mapping[str, Any]:
        self.calls.append({"kind": "repair_commit_draft", "error": error})
        if not self.repairs:
            return draft
        return self.repairs.pop(0)
