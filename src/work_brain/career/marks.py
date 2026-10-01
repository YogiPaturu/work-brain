from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..errors import IntegrityError, ValidationError
from ..fsutil import append_jsonl, read_jsonl_with_recovery, ensure_private_file
from ..ids import new_uuid7, validate_uuid7
from ..timeutil import parse_timestamp, timestamp_now
from .questions import QuestionRef


@dataclass(frozen=True)
class CareerCandidateMarkEvent:
    event_id: str
    occurred_at: str
    entry_id: str
    entry_revision_at_event: int
    action: str
    note: str | None = None
    question_refs: tuple[dict[str, str], ...] = ()

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "CareerCandidateMarkEvent":
        event_id = validate_uuid7(raw.get("event_id"), "event_id")
        occurred_at = raw.get("occurred_at")
        parse_timestamp(occurred_at, "occurred_at")
        entry_id = validate_uuid7(raw.get("entry_id"), "entry_id")
        revision = raw.get("entry_revision_at_event")
        if not isinstance(revision, int) or revision < 1:
            raise ValidationError("entry_revision_at_event must be a positive integer")
        action = raw.get("action")
        if action not in {"mark", "unmark"}:
            raise ValidationError("mark action must be mark or unmark")
        note = raw.get("note")
        if note is not None and (not isinstance(note, str) or not note.strip()):
            raise ValidationError("mark note must be a non-empty string or null")
        refs = raw.get("question_refs", [])
        if not isinstance(refs, list):
            raise ValidationError("question_refs must be a list")
        normalized_refs: list[dict[str, str]] = []
        for ref in refs:
            if not isinstance(ref, Mapping) or not isinstance(ref.get("bank_id"), str) or not isinstance(ref.get("question_id"), str):
                raise ValidationError("question_refs must contain bank_id and question_id")
            QuestionRef.from_value(ref)
            normalized_refs.append({"bank_id": ref["bank_id"], "question_id": ref["question_id"]})
        if action == "unmark" and (note is not None or normalized_refs):
            raise ValidationError("unmark events cannot include note or question_refs")
        return cls(event_id, occurred_at, entry_id, revision, action, note.strip() if note else None, tuple(normalized_refs))

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id, "occurred_at": self.occurred_at, "entry_id": self.entry_id,
            "entry_revision_at_event": self.entry_revision_at_event, "action": self.action,
            "note": self.note, "question_refs": [dict(ref) for ref in self.question_refs],
        }


class CareerCandidateMarkStore:
    """Append-only private preference events; current state is a fold of the log."""

    def __init__(self, vault: Any):
        self.vault = vault
        self.path = vault.root / "career/marks.jsonl"

    def _events(self) -> list[CareerCandidateMarkEvent]:
        records, _ = read_jsonl_with_recovery(self.path)
        events = [CareerCandidateMarkEvent.from_dict(record) for record in records]
        if len({event.event_id for event in events}) != len(events):
            raise IntegrityError("duplicate candidate mark event ID")
        return events

    def current(self) -> dict[str, CareerCandidateMarkEvent]:
        current: dict[str, CareerCandidateMarkEvent] = {}
        for event in self._events():
            current[event.entry_id] = event
        return {entry_id: event for entry_id, event in current.items() if event.action == "mark"}

    def get(self, entry_id: str) -> CareerCandidateMarkEvent | None:
        entry_id = validate_uuid7(entry_id, "entry_id")
        return self.current().get(entry_id)

    def list(self, *, include_orphans: bool = True) -> list[dict[str, Any]]:
        entries = {entry.entry_id: entry for entry in self.vault.all_current_entries()}
        result = []
        for event in sorted(self.current().values(), key=lambda item: (item.occurred_at, item.entry_id)):
            value = event.to_dict()
            value["orphaned"] = event.entry_id not in entries
            if include_orphans or not value["orphaned"]:
                result.append(value)
        return result

    def _append(self, event: CareerCandidateMarkEvent) -> dict[str, Any]:
        with self.vault.write_lock():
            append_jsonl(self.path, event.to_dict())
        return event.to_dict()

    def mark(self, entry_id: str, *, note: str | None = None, question_refs: list[Mapping[str, str]] | None = None) -> dict[str, Any]:
        entry = self.vault.get_current_entry(validate_uuid7(entry_id, "entry_id"))
        existing = self.get(entry.entry_id)
        refs = []
        for ref in question_refs or []:
            refs.append(QuestionRef.from_value(ref).to_dict())
        if existing is not None and existing.note == (note.strip() if note else None) and list(existing.question_refs) == refs:
            value = existing.to_dict()
            value["idempotent"] = True
            return value
        event = CareerCandidateMarkEvent(new_uuid7(), timestamp_now(), entry.entry_id, entry.revision, "mark", note.strip() if note else None, tuple(refs))
        value = self._append(event)
        value["idempotent"] = False
        return value

    def unmark(self, entry_id: str) -> dict[str, Any]:
        entry_id = validate_uuid7(entry_id, "entry_id")
        existing = self.get(entry_id)
        if existing is None:
            self.vault.get_current_entry(entry_id)
            return {"entry_id": entry_id, "action": "unmark", "idempotent": True}
        try:
            revision = self.vault.get_current_entry(entry_id).revision
        except FileNotFoundError:
            revision = existing.entry_revision_at_event
        event = CareerCandidateMarkEvent(new_uuid7(), timestamp_now(), entry_id, revision, "unmark")
        value = self._append(event)
        value["idempotent"] = False
        return value
