from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .domain import SessionEntry
from .errors import ValidationError


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    data: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "data": self.data, "error": self.error}


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    mutating: bool = False


PROFILES: dict[str, tuple[str, ...]] = {
    "think": ("search_evidence", "hydrate_evidence", "get_current_state"),
    "operate": ("get_current_state", "get_recent_work", "search_evidence", "hydrate_evidence"),
    "communicate": ("get_recent_work", "search_evidence", "hydrate_evidence"),
    "career": ("search_evidence", "hydrate_evidence"),
    "open-day": ("get_current_state", "get_recent_work"),
    "close-day": ("get_current_state", "get_recent_work"),
    "backfill": ("search_evidence", "hydrate_evidence"),
}


class ToolRegistry:
    """High-level read tools; storage and retrieval mechanics stay behind this port."""

    DEFINITIONS = {
        "get_current_state": ToolDefinition("get_current_state", "Read compact active work state."),
        "get_recent_work": ToolDefinition("get_recent_work", "Read compact recent committed work."),
        "search_evidence": ToolDefinition("search_evidence", "Search evidence through the configured retrieval adapter."),
        "hydrate_evidence": ToolDefinition("hydrate_evidence", "Hydrate selected stable evidence references."),
        "commit_session": ToolDefinition("commit_session", "Publish a validated session draft.", mutating=True),
        "record_amendment": ToolDefinition("record_amendment", "Record an explicit user correction.", mutating=True),
    }

    def __init__(self, vault: Any, retrieval: Mapping[str, Callable[..., Any]] | None = None):
        self.vault = vault
        if retrieval is None:
            from .retrieval import EvidenceRetriever
            adapter = EvidenceRetriever(vault)
            retrieval = {"search_evidence": adapter.search, "hydrate_evidence": adapter.hydrate}
        self.retrieval = dict(retrieval)

    def definitions(self, workflow: str, *, committing: bool = False) -> tuple[ToolDefinition, ...]:
        if workflow not in PROFILES:
            raise ValidationError(f"unknown workflow: {workflow}")
        names = list(PROFILES[workflow])
        if committing:
            names.append("commit_session")
        return tuple(self.DEFINITIONS[name] for name in names)

    def call(self, name: str, **arguments: Any) -> ToolResult:
        if name == "get_current_state":
            path = self.vault.root / "state/current.json"
            return ToolResult(True, json.loads(path.read_text(encoding="utf-8")))
        if name == "get_recent_work":
            entries = sorted(self.vault.all_current_entries(), key=lambda item: item.created_at, reverse=True)
            limit = arguments.get("limit", 8)
            if not isinstance(limit, int) or not 0 < limit <= 50:
                return ToolResult(False, error="limit must be an integer between 1 and 50")
            return ToolResult(True, [
                {"entry_id": entry.entry_id, "revision": entry.revision, "title": entry.title, "summary": entry.summary}
                for entry in entries[:limit]
            ])
        if name in {"search_evidence", "hydrate_evidence"}:
            handler = self.retrieval.get(name)
            if handler is None:
                return ToolResult(False, error="retrieval adapter is not configured")
            try:
                return ToolResult(True, handler(**arguments))
            except (ValidationError, ValueError) as exc:
                return ToolResult(False, error=str(exc))
        return ToolResult(False, error=f"tool is not available in the current phase: {name}")
