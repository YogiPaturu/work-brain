from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .domain import SessionEntry
from .errors import ValidationError
from .profiles import CommunicationProfileStore
from .timeutil import date_for_timestamp, timestamp_now, validate_calendar_date


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
    "think": ("resolve_context", "search_evidence", "select_evidence", "hydrate_evidence", "search_experiences", "get_experience", "hydrate_experience", "find_related_experience_entries", "get_current_state"),
    "operate": ("resolve_context", "get_current_state", "get_recent_work", "search_evidence", "select_evidence", "hydrate_evidence", "list_work_item_communication_profiles"),
    "communicate": ("resolve_context", "get_current_state", "get_recent_work", "search_evidence", "select_evidence", "search_profile_evidence", "hydrate_evidence", "search_experiences", "get_experience", "hydrate_experience", "get_communication_profile"),
    "career": (
        "resolve_context", "search_questions", "get_question", "choose_question",
        "search_evidence", "select_evidence", "hydrate_evidence", "search_experiences", "get_experience", "hydrate_experience", "find_related_experience_entries",
        "mark_interview_candidate", "unmark_interview_candidate", "list_interview_candidates", "associate_entry_experience",
    ),
    "open-day": ("resolve_context", "get_current_state", "get_recent_work"),
    "close-day": ("resolve_context", "get_current_state", "get_close_day_record", "list_post_close_communication_profiles"),
    "backfill": ("resolve_context", "search_evidence", "select_evidence", "hydrate_evidence", "search_experiences", "get_experience", "hydrate_experience", "find_related_experience_entries", "associate_entry_experience"),
}


class ToolRegistry:
    """High-level read tools; storage and retrieval mechanics stay behind this port."""

    DEFINITIONS = {
        "get_current_state": ToolDefinition("get_current_state", "Read compact active work state."),
        "get_recent_work": ToolDefinition("get_recent_work", "Read compact recent committed work."),
        "get_close_day_record": ToolDefinition(
            "get_close_day_record",
            "Read target-day committed entries, committed entries missing from their journal projection, and all uncommitted raw sessions.",
        ),
        "search_evidence": ToolDefinition("search_evidence", "Search evidence through the configured retrieval adapter."),
        "resolve_context": ToolDefinition("resolve_context", "Resolve existing workspace/project identities from names or historical evidence."),
        "select_evidence": ToolDefinition("select_evidence", "Select bounded evidence by deterministic metadata filters without a text query."),
        "search_profile_evidence": ToolDefinition("search_profile_evidence", "Search evidence using a validated communication profile's exact scope."),
        "hydrate_evidence": ToolDefinition("hydrate_evidence", "Hydrate selected stable evidence references."),
        "search_experiences": ToolDefinition("search_experiences", "Search or list source-backed professional Experiences."),
        "get_experience": ToolDefinition("get_experience", "Read one bounded source-backed Experience card."),
        "hydrate_experience": ToolDefinition("hydrate_experience", "Hydrate an Experience and bounded supporting evidence."),
        "find_related_experience_entries": ToolDefinition("find_related_experience_entries", "Find bounded source-backed entries related to an anchor entry without changing Experience associations."),
        "get_communication_profile": ToolDefinition("get_communication_profile", "Read one validated user-owned communication profile."),
        "list_post_close_communication_profiles": ToolDefinition("list_post_close_communication_profiles", "List user-owned communication profiles configured to be offered after close-day."),
        "list_work_item_communication_profiles": ToolDefinition("list_work_item_communication_profiles", "List user-owned communication profiles configured for meaningful work-item completion."),
        "search_questions": ToolDefinition("search_questions", "Filter configured interview questions without an LLM call."),
        "get_question": ToolDefinition("get_question", "Fetch one exact interview question by stable reference."),
        "choose_question": ToolDefinition("choose_question", "Choose one question from a bounded filtered set."),
        "mark_interview_candidate": ToolDefinition("mark_interview_candidate", "Persist an explicitly user-confirmed interview candidate mark.", mutating=True),
        "unmark_interview_candidate": ToolDefinition("unmark_interview_candidate", "Remove an interview candidate mark.", mutating=True),
        "list_interview_candidates": ToolDefinition("list_interview_candidates", "List current user-authored interview candidate marks."),
        "associate_entry_experience": ToolDefinition("associate_entry_experience", "Attach or remove an entry's optional source-backed Experience association.", mutating=True),
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
            retrieval = {"search_evidence": adapter.search, "select_evidence": adapter.select_evidence, "hydrate_evidence": adapter.hydrate}
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
        if name == "resolve_context":
            try:
                from .context_resolver import ContextResolver

                resolver = ContextResolver(self.vault, search_evidence=self.retrieval.get("search_evidence"))
                return ToolResult(True, resolver.resolve_context(
                    workspace_hint=arguments.get("workspace_hint"),
                    project_hint=arguments.get("project_hint"),
                    limit=arguments.get("limit", 5),
                ))
            except (ValidationError, ValueError) as exc:
                return ToolResult(False, error=str(exc))
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
        if name == "get_close_day_record":
            local_date = arguments.get("local_date") or date_for_timestamp(timestamp_now())
            try:
                validate_calendar_date(local_date, "local_date")
            except ValidationError as exc:
                return ToolResult(False, error=str(exc))
            sessions = {session["session_id"]: session for session in self.vault.all_sessions()}
            journal_cache: dict[str, str] = {}

            def journal_contains(entry: SessionEntry, session: Mapping[str, Any]) -> bool:
                entry_date = session["local_date"]
                if entry_date not in journal_cache:
                    year, month, _ = entry_date.split("-")
                    path = self.vault.root / "journal" / year / month / f"{entry_date}.md"
                    journal_cache[entry_date] = path.read_text(encoding="utf-8") if path.exists() else ""
                marker = f"<!-- entry_id: {entry.entry_id}; revision: {entry.revision} -->"
                return marker in journal_cache[entry_date]

            entries = []
            unjournaled_entries = []
            all_entry_session_ids: set[str] = set()
            for entry in sorted(self.vault.all_current_entries(), key=lambda item: (item.created_at, item.entry_id)):
                session = sessions.get(entry.session_id)
                if session is None:
                    continue
                all_entry_session_ids.add(entry.session_id)
                card = {
                    "entry_id": entry.entry_id,
                    "revision": entry.revision,
                    "session_id": entry.session_id,
                    "local_date": session["local_date"],
                    "journal_associated": journal_contains(entry, session),
                    "started_at": session["started_at"],
                    "created_at": entry.created_at,
                    "title": entry.title,
                    "summary": entry.summary,
                    "sections": entry.sections,
                    "state_mutations": [mutation.to_dict() for mutation in entry.state_mutations],
                }
                if session["local_date"] == local_date:
                    entries.append(card)
                elif not card["journal_associated"]:
                    unjournaled_entries.append(card)

            uncommitted_raw = []
            for session in sorted(sessions.values(), key=lambda item: (item["started_at"], item["session_id"])):
                if session["session_id"] in all_entry_session_ids:
                    continue
                turns = self.vault.list_turns(session["session_id"])
                runtime = dict(session.get("runtime") or {})
                pending = runtime.get("commit_status") in {"pending_auto_commit", "auto_commit_failed"}
                recoverable = runtime.get("capture_status") in {"active", "recoverable", "rolled_over"}
                if not turns or not (session.get("ended_at") is None or pending or recoverable):
                    continue
                uncommitted_raw.append({
                    "session_id": session["session_id"],
                    "entry_id": session["entry_id"],
                    "local_date": session["local_date"],
                    "started_at": session["started_at"],
                    "ended_at": session.get("ended_at"),
                    "workflow": runtime.get("workflow"),
                    "capture_status": runtime.get("capture_status"),
                    "commit_status": runtime.get("commit_status"),
                    "turn_count": len(turns),
                    "turns": turns,
                })

            return ToolResult(True, {
                "local_date": local_date,
                "committed_entries": entries,
                "unjournaled_entries": unjournaled_entries,
                "uncommitted_raw_sessions": uncommitted_raw,
            })
        if name in {"search_evidence", "select_evidence", "hydrate_evidence"}:
            handler = self.retrieval.get(name)
            if handler is None:
                return ToolResult(False, error="retrieval adapter is not configured")
            try:
                return ToolResult(True, handler(**arguments))
            except (ValidationError, ValueError) as exc:
                return ToolResult(False, error=str(exc))
        if name in {"search_experiences", "get_experience", "hydrate_experience", "find_related_experience_entries"}:
            try:
                from .experiences import ExperienceService
                service = ExperienceService(self.vault)
                if name == "search_experiences":
                    query = arguments.get("query")
                    if query:
                        return ToolResult(True, service.search(
                            query,
                            filters=arguments.get("filters"),
                            page_size=arguments.get("page_size", 8),
                            cursor=arguments.get("cursor"),
                        ))
                    return ToolResult(True, service.list(
                        limit=arguments.get("limit", 8),
                        filters=arguments.get("filters"),
                    ))
                if name == "get_experience":
                    return ToolResult(True, service.get(arguments["experience_id"]))
                if name == "find_related_experience_entries":
                    return ToolResult(True, service.related(arguments["entry_id"], limit=arguments.get("limit", 8)))
                refs = arguments.get("refs")
                return ToolResult(True, service.hydrate(arguments["experience_id"], refs=refs))
            except (ValidationError, ValueError, FileNotFoundError) as exc:
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
                if query:
                    result = handler(query=query, filters=filters, page_size=page_size, cursor=cursor)
                else:
                    selector = self.retrieval.get("select_evidence")
                    if selector is None:
                        raise ValidationError("retrieval adapter does not support filter-only evidence selection")
                    result = selector(filters=filters, page_size=page_size, cursor=cursor)
                fallback_used = False
                scope_fields = ("entities", "workspaces", "projects", "experiences")
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
                    fallback_query = " ".join(scope_terms + ([query] if query else [])).strip()
                    result = handler(query=fallback_query, filters=fallback_filters, page_size=page_size, cursor=None)
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
        if name in {"search_questions", "get_question", "choose_question", "mark_interview_candidate", "unmark_interview_candidate", "list_interview_candidates", "associate_entry_experience"}:
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
                if name == "associate_entry_experience":
                    if arguments.get("explicit_user_intent") is not True:
                        return ToolResult(False, error="explicit_user_intent=true is required to change an Experience association")
                    return ToolResult(True, service.experiences.associate(
                        arguments["entry_id"],
                        experience_id=arguments.get("experience_id"),
                        experience_name=arguments.get("experience_name"),
                        remove=arguments.get("remove", False),
                        move=arguments.get("move", False),
                    ))
                if name == "mark_interview_candidate":
                    if arguments.get("explicit_user_intent") is not True:
                        return ToolResult(False, error="explicit_user_intent=true is required; a model suggestion cannot create a mark")
                    target_kind = arguments.get("target_kind", "entry")
                    target_id = arguments.get("target_id", arguments.get("entry_id"))
                    return ToolResult(True, service.marks.mark(target_id, target_kind=target_kind, note=arguments.get("note"), question_refs=arguments.get("question_refs")))
                if arguments.get("explicit_user_intent") is not True:
                    return ToolResult(False, error="explicit_user_intent=true is required to change a candidate mark")
                target_kind = arguments.get("target_kind", "entry")
                target_id = arguments.get("target_id", arguments.get("entry_id"))
                return ToolResult(True, service.marks.unmark(target_id, target_kind=target_kind))
            except (ValidationError, ValueError, KeyError) as exc:
                return ToolResult(False, error=str(exc))
        return ToolResult(False, error=f"tool is not available in the current phase: {name}")
