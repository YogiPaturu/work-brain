from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .domain import SessionEntry
from .errors import ValidationError
from .profiles import CommunicationProfileStore


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
    "operate": ("get_current_state", "get_recent_work", "search_evidence", "hydrate_evidence", "list_work_item_communication_profiles"),
    "communicate": ("get_current_state", "get_recent_work", "search_evidence", "search_profile_evidence", "hydrate_evidence", "get_communication_profile"),
    "career": (
        "search_questions", "get_question", "choose_question",
        "search_evidence", "hydrate_evidence",
        "mark_interview_candidate", "unmark_interview_candidate", "list_interview_candidates",
    ),
    "open-day": ("get_current_state", "get_recent_work"),
    "close-day": ("get_current_state", "get_recent_work", "list_post_close_communication_profiles"),
    "backfill": ("search_evidence", "hydrate_evidence"),
}


class ToolRegistry:
    """High-level read tools; storage and retrieval mechanics stay behind this port."""

    DEFINITIONS = {
        "get_current_state": ToolDefinition("get_current_state", "Read compact active work state."),
        "get_recent_work": ToolDefinition("get_recent_work", "Read compact recent committed work."),
        "search_evidence": ToolDefinition("search_evidence", "Search evidence through the configured retrieval adapter."),
        "search_profile_evidence": ToolDefinition("search_profile_evidence", "Search evidence using a validated communication profile's exact scope."),
        "hydrate_evidence": ToolDefinition("hydrate_evidence", "Hydrate selected stable evidence references."),
        "get_communication_profile": ToolDefinition("get_communication_profile", "Read one validated user-owned communication profile."),
        "list_post_close_communication_profiles": ToolDefinition("list_post_close_communication_profiles", "List user-owned communication profiles configured to be offered after close-day."),
        "list_work_item_communication_profiles": ToolDefinition("list_work_item_communication_profiles", "List user-owned communication profiles configured for meaningful work-item completion."),
        "search_questions": ToolDefinition("search_questions", "Filter configured interview questions without an LLM call."),
        "get_question": ToolDefinition("get_question", "Fetch one exact interview question by stable reference."),
        "choose_question": ToolDefinition("choose_question", "Choose one question from a bounded filtered set."),
        "mark_interview_candidate": ToolDefinition("mark_interview_candidate", "Persist an explicitly user-confirmed interview candidate mark.", mutating=True),
        "unmark_interview_candidate": ToolDefinition("unmark_interview_candidate", "Remove an interview candidate mark.", mutating=True),
        "list_interview_candidates": ToolDefinition("list_interview_candidates", "List current user-authored interview candidate marks."),
        "commit_session": ToolDefinition("commit_session", "Publish a validated session draft.", mutating=True),
        "record_amendment": ToolDefinition("record_amendment", "Record an explicit user correction.", mutating=True),
    }

    def __init__(self, vault: Any, retrieval: Mapping[str, Callable[..., Any]] | None = None,
                 profile_store: CommunicationProfileStore | None = None):
        self.vault = vault
        self.profile_store = profile_store or CommunicationProfileStore.load()
        self.active_profile_id: str | None = None
        if retrieval is None:
            from .retrieval import EvidenceRetriever
            adapter = EvidenceRetriever(vault)
            retrieval = {"search_evidence": adapter.search, "hydrate_evidence": adapter.hydrate}
        self.retrieval = dict(retrieval)

    def definitions(self, workflow: str, *, committing: bool = False) -> tuple[ToolDefinition, ...]:
        if workflow not in PROFILES:
            raise ValidationError(f"unknown workflow: {workflow}")
        names = list(PROFILES[workflow])
        if workflow == "communicate":
            if self.active_profile_id:
                names.remove("search_evidence")
            else:
                names.remove("search_profile_evidence")
        if committing:
            names.append("commit_session")
        return tuple(self.DEFINITIONS[name] for name in names)

    def activate_profile(self, profile_id: str | None) -> None:
        if profile_id is None:
            self.active_profile_id = None
            return
        profile = self.profile_store.get(profile_id)
        if profile.workflow != "communicate":
            raise ValidationError("communication profile must use workflow=communicate")
        self.active_profile_id = profile.profile_id

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
        if name == "search_profile_evidence":
            handler = self.retrieval.get("search_evidence")
            if handler is None:
                return ToolResult(False, error="retrieval adapter is not configured")
            profile_id = arguments.get("profile_id") or self.active_profile_id
            try:
                profile = self.profile_store.get(profile_id)
                filters = profile.retrieval_filters(local_date=arguments.get("local_date"))
                query = arguments.get("query")
                if profile.scope.get("time_window") == "work_item":
                    work_item = arguments.get("work_item")
                    if not isinstance(work_item, str) or not work_item.strip():
                        raise ValidationError("work_item is required for a work-item-scoped communication profile")
                    query = f"{work_item.strip()} {query or ''}".strip()
                page_size = arguments.get("page_size", 8)
                cursor = arguments.get("cursor")
                result = handler(
                    query=query,
                    filters=filters,
                    page_size=page_size,
                    cursor=cursor,
                )
                fallback_used = False
                scope_fields = ("entities", "workspaces", "projects")
                if (
                    not cursor
                    and any(filters.get(field) for field in scope_fields)
                    and isinstance(result, dict)
                    and not result.get("cards")
                ):
                    # Older entries may mention a scoped entity or project
                    # without carrying an explicit catalog reference. Preserve
                    # that boundary as a text anchor for legacy entries.
                    fallback_filters = dict(filters)
                    scope_terms: list[str] = []
                    for field in scope_fields:
                        scope_terms.extend(fallback_filters.pop(field, []))
                    fallback_query = " ".join(scope_terms + [query]).strip()
                    result = handler(
                        query=fallback_query,
                        filters=fallback_filters,
                        page_size=page_size,
                        cursor=None,
                    )
                    fallback_used = True
                if isinstance(result, dict):
                    result = dict(result)
                    result["profile_scope"] = {
                        "profile_id": profile.profile_id,
                        "filters": filters,
                        "retrieval_mode": "text_entity_fallback" if fallback_used else "metadata",
                    }
                return ToolResult(True, result)
            except (ValidationError, ValueError) as exc:
                return ToolResult(False, error=str(exc))
        if name == "get_communication_profile":
            try:
                profile_id = arguments.get("profile_id") or self.active_profile_id
                return ToolResult(True, self.profile_store.get(profile_id).to_dict())
            except ValidationError as exc:
                return ToolResult(False, error=str(exc))
        if name == "list_post_close_communication_profiles":
            return ToolResult(True, [
                {
                    "id": profile.profile_id,
                    "label": profile.label,
                    "channel": profile.channel,
                    "audience": profile.audience,
                    "purpose": profile.purpose,
                }
                for profile in self.profile_store.triggered_after_close_day()
            ])
        if name == "list_work_item_communication_profiles":
            return ToolResult(True, [
                {
                    "id": profile.profile_id,
                    "label": profile.label,
                    "channel": profile.channel,
                    "audience": profile.audience,
                    "purpose": profile.purpose,
                }
                for profile in self.profile_store.triggered_after_work_item()
            ])
        if name in {"search_questions", "get_question", "choose_question", "mark_interview_candidate", "unmark_interview_candidate", "list_interview_candidates"}:
            try:
                from .career import CareerService, QuestionFilters, QuestionRef
                service = CareerService(self.vault)
                if name == "search_questions":
                    raw_filters = arguments.get("filters") or {}
                    if not isinstance(raw_filters, Mapping):
                        raise ValidationError("question filters must be an object")
                    filters = QuestionFilters.from_values(
                        tags_all=raw_filters.get("tags_all", ()), tags_any=raw_filters.get("tags_any", ()),
                        exclude_tags=raw_filters.get("exclude_tags", ()), bank_ids=raw_filters.get("bank_ids", ()),
                    )
                    return ToolResult(True, service.search_questions(filters=filters, text=arguments.get("text"), limit=arguments.get("limit", 20)))
                if name == "get_question":
                    return ToolResult(True, service.get_question(QuestionRef.from_value(arguments.get("question_ref", {}))))
                if name == "choose_question":
                    raw_filters = arguments.get("filters") or {}
                    filters = QuestionFilters.from_values(
                        tags_all=raw_filters.get("tags_all", ()), tags_any=raw_filters.get("tags_any", ()),
                        exclude_tags=raw_filters.get("exclude_tags", ()), bank_ids=raw_filters.get("bank_ids", ()),
                    )
                    return ToolResult(True, service.choose_question(filters=filters, text=arguments.get("text"), seed=arguments.get("seed")))
                if name == "list_interview_candidates":
                    return ToolResult(True, service.marks.list())
                if name == "mark_interview_candidate":
                    if arguments.get("explicit_user_intent") is not True:
                        return ToolResult(False, error="explicit_user_intent=true is required; a model suggestion cannot create a mark")
                    return ToolResult(True, service.marks.mark(arguments["entry_id"], note=arguments.get("note"), question_refs=arguments.get("question_refs")))
                if arguments.get("explicit_user_intent") is not True:
                    return ToolResult(False, error="explicit_user_intent=true is required to change a candidate mark")
                return ToolResult(True, service.marks.unmark(arguments["entry_id"]))
            except (ValidationError, ValueError, KeyError) as exc:
                return ToolResult(False, error=str(exc))
        return ToolResult(False, error=f"tool is not available in the current phase: {name}")
