from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .errors import ValidationError
from .ids import validate_uuid7
from .timeutil import date_for_timestamp, parse_timestamp, validate_calendar_date

ENTRY_SECTIONS = (
    "context", "observations", "significance", "contribution", "reasoning",
    "evidence", "alternatives_tradeoffs", "decisions_actions", "expectations",
    "outcomes", "learning", "open_questions",
)
REVISION_REASONS = {"initial_commit", "reextract", "user_correction"}
PROVENANCE_KINDS = {"contemporaneous", "reconstructed"}
OCCURRENCE_PRECISIONS = {"instant", "day", "month", "quarter", "year", "range", "unknown"}
STATE_KINDS = {"task", "open_loop", "commitment", "project_state"}
STATE_STATUSES = {"active", "waiting", "done", "dropped"}
MUTATION_OPS = {"create", "update", "close", "reopen"}
ENTITY_KINDS = {"project", "person", "organization", "customer", "system", "topic"}


def _required(obj: Mapping[str, Any], key: str) -> Any:
    if key not in obj:
        raise ValidationError(f"missing required field: {key}")
    return obj[key]


def _token(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or any(ch.isspace() for ch in value):
        raise ValidationError(f"{field} must be a non-empty token")
    return value.lower()


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x for x in value):
        raise ValidationError(f"{field} must be a list of non-empty strings")
    return value


@dataclass(frozen=True)
class Statement:
    text: str
    basis: str
    source_turns: list[int] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Statement":
        text = _required(raw, "text")
        basis = _required(raw, "basis")
        turns = raw.get("source_turns", [])
        if not isinstance(text, str) or not text:
            raise ValidationError("statement.text must be non-empty")
        if basis not in {"stated", "inferred"}:
            raise ValidationError("statement.basis must be stated or inferred")
        if not isinstance(turns, list) or any(not isinstance(x, int) or x < 1 for x in turns):
            raise ValidationError("statement.source_turns must contain positive integers")
        if basis == "inferred" and not turns:
            raise ValidationError("inferred statements require source_turns or artifact support")
        return cls(text, basis, turns)

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "basis": self.basis, "source_turns": list(self.source_turns)}


@dataclass(frozen=True)
class Occurrence:
    start: str | None
    end: str | None
    precision: str
    label: str | None = None

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Occurrence":
        precision = _required(raw, "precision")
        if precision not in OCCURRENCE_PRECISIONS:
            raise ValidationError("invalid occurrence.precision")
        start, end = raw.get("start"), raw.get("end")
        if precision == "unknown":
            if start is not None or end is not None:
                raise ValidationError("unknown occurrence cannot have start/end")
        elif start is None:
            raise ValidationError("known occurrence precision requires start")
        else:
            if precision == "instant":
                parse_timestamp(start, "occurrence.start")
                if end is not None:
                    parse_timestamp(end, "occurrence.end")
            else:
                validate_calendar_date(start, "occurrence.start")
                if end is not None:
                    validate_calendar_date(end, "occurrence.end")
        if end is not None and start is not None and end < start:
            raise ValidationError("occurrence.end must not precede start")
        if raw.get("label") is not None and not isinstance(raw["label"], str):
            raise ValidationError("occurrence.label must be a string or null")
        return cls(start, end, precision, raw.get("label"))

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end, "precision": self.precision, "label": self.label}


@dataclass(frozen=True)
class StateMutation:
    mutation_id: str
    operation: str
    state_item_id: str
    kind: str | None
    fields: dict[str, Any]
    source_turns: list[int] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "StateMutation":
        mutation_id = validate_uuid7(_required(raw, "mutation_id"), "mutation_id")
        operation = _required(raw, "operation")
        if operation not in MUTATION_OPS:
            raise ValidationError("invalid state mutation operation")
        state_item_id = validate_uuid7(_required(raw, "state_item_id"), "state_item_id")
        kind = raw.get("kind")
        if kind is not None and kind not in STATE_KINDS:
            raise ValidationError("invalid state mutation kind")
        fields = raw.get("fields", {})
        if not isinstance(fields, dict):
            raise ValidationError("state mutation fields must be an object")
        turns = raw.get("source_turns", [])
        if not isinstance(turns, list) or any(not isinstance(x, int) or x < 1 for x in turns):
            raise ValidationError("state mutation source_turns must contain positive integers")
        if operation == "create" and (kind is None or not isinstance(fields.get("title"), str) or not fields["title"]):
            raise ValidationError("create mutation requires kind and fields.title")
        return cls(mutation_id, operation, state_item_id, kind, fields, turns)

    def to_dict(self) -> dict[str, Any]:
        return {"mutation_id": self.mutation_id, "operation": self.operation, "state_item_id": self.state_item_id,
                "kind": self.kind, "fields": self.fields, "source_turns": list(self.source_turns)}


@dataclass(frozen=True)
class SessionEntry:
    entry_id: str
    session_id: str
    revision: int
    commit_id: str
    created_at: str
    supersedes_revision: int | None
    revision_reason: str
    provenance_kind: str
    title: str
    summary: str
    occurrence: Occurrence
    modes: list[str]
    domains: list[str]
    sections: dict[str, list[Statement]]
    state_mutations: list[StateMutation]
    entity_refs: list[dict[str, str]]
    artifact_refs: list[dict[str, str]]
    source_refs: list[dict[str, Any]]

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "SessionEntry":
        entry_id = validate_uuid7(_required(raw, "entry_id"), "entry_id")
        session_id = validate_uuid7(_required(raw, "session_id"), "session_id")
        commit_id = validate_uuid7(_required(raw, "commit_id"), "commit_id")
        revision = _required(raw, "revision")
        if not isinstance(revision, int) or revision < 1:
            raise ValidationError("revision must be a positive integer")
        created_at = _required(raw, "created_at")
        parse_timestamp(created_at, "created_at")
        supersedes = raw.get("supersedes_revision")
        if supersedes is not None and (not isinstance(supersedes, int) or supersedes != revision - 1):
            raise ValidationError("supersedes_revision must be the immediately preceding revision")
        reason = _required(raw, "revision_reason")
        if reason not in REVISION_REASONS:
            raise ValidationError("invalid revision_reason")
        if revision == 1 and supersedes is not None:
            raise ValidationError("revision 1 cannot supersede another revision")
        if revision > 1 and supersedes is None:
            raise ValidationError("later revisions must name supersedes_revision")
        provenance = _required(raw, "provenance_kind")
        if provenance not in PROVENANCE_KINDS:
            raise ValidationError("invalid provenance_kind")
        title, summary = _required(raw, "title"), _required(raw, "summary")
        if not isinstance(title, str) or not title or not isinstance(summary, str):
            raise ValidationError("title and summary must be strings; title cannot be empty")
        occurrence = Occurrence.from_dict(_required(raw, "occurrence"))
        modes, domains = _string_list(_required(raw, "modes"), "modes"), _string_list(_required(raw, "domains"), "domains")
        sections_raw = _required(raw, "sections")
        if not isinstance(sections_raw, dict) or set(sections_raw) != set(ENTRY_SECTIONS):
            raise ValidationError("sections must contain exactly the LLD1 section names")
        sections = {}
        for name in ENTRY_SECTIONS:
            if not isinstance(sections_raw[name], list):
                raise ValidationError(f"sections.{name} must be a list")
            sections[name] = [Statement.from_dict(item) for item in sections_raw[name]]
        mutations = [StateMutation.from_dict(item) for item in raw.get("state_mutations", [])]
        for field_name in ("entity_refs", "artifact_refs", "source_refs"):
            if not isinstance(raw.get(field_name, []), list):
                raise ValidationError(f"{field_name} must be a list")
        entities = []
        for ref in raw.get("entity_refs", []):
            entities.append({"entity_id": validate_uuid7(_required(ref, "entity_id"), "entity_id"), "relation": _token(_required(ref, "relation"), "relation")})
        artifacts = []
        for ref in raw.get("artifact_refs", []):
            artifacts.append({"artifact_id": validate_uuid7(_required(ref, "artifact_id"), "artifact_id"), "relation": _token(_required(ref, "relation"), "relation")})
        sources = []
        for ref in raw.get("source_refs", []):
            if not isinstance(ref, dict) or ref.get("kind") not in {"amendment", "entry"}:
                raise ValidationError("source_refs must contain amendment or entry references")
            if ref["kind"] == "amendment":
                sources.append({"kind": "amendment", "id": validate_uuid7(_required(ref, "id"), "source_ref.id")})
            else:
                sources.append({"kind": "entry", "id": validate_uuid7(_required(ref, "id"), "source_ref.id"), "revision": _required(ref, "revision")})
        if any(statement.basis == "inferred" and not statement.source_turns for statements in sections.values() for statement in statements) and not artifacts:
            raise ValidationError("inferred statements without source_turns require an artifact reference")
        return cls(entry_id, session_id, revision, commit_id, created_at, supersedes, reason, provenance, title, summary,
                   occurrence, modes, domains, sections, mutations, entities, artifacts, sources)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id, "session_id": self.session_id, "revision": self.revision,
            "commit_id": self.commit_id, "created_at": self.created_at, "supersedes_revision": self.supersedes_revision,
            "revision_reason": self.revision_reason, "provenance_kind": self.provenance_kind, "title": self.title,
            "summary": self.summary, "occurrence": self.occurrence.to_dict(), "modes": self.modes,
            "domains": self.domains, "sections": {k: [s.to_dict() for s in v] for k, v in self.sections.items()},
            "state_mutations": [m.to_dict() for m in self.state_mutations], "entity_refs": self.entity_refs,
            "artifact_refs": self.artifact_refs, "source_refs": self.source_refs,
        }


def validate_session(raw: Mapping[str, Any]) -> dict[str, Any]:
    session_id = validate_uuid7(_required(raw, "session_id"), "session_id")
    started_at = _required(raw, "started_at")
    parse_timestamp(started_at, "started_at")
    local_date = validate_calendar_date(_required(raw, "local_date"), "local_date")
    if local_date != date_for_timestamp(started_at):
        raise ValidationError("local_date must be the local calendar date of started_at")
    entry_id = validate_uuid7(_required(raw, "entry_id"), "entry_id")
    ended_at = raw.get("ended_at")
    if ended_at is not None:
        parse_timestamp(ended_at, "ended_at")
        if parse_timestamp(ended_at) < parse_timestamp(started_at):
            raise ValidationError("ended_at must not precede started_at")
    if not isinstance(raw.get("modes", []), list) or not isinstance(raw.get("domains", []), list):
        raise ValidationError("modes and domains must be lists")
    return dict(raw)


def normalize_alias(value: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKC", value).casefold()
