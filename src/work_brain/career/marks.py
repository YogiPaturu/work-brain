from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..errors import IntegrityError, ValidationError
from ..fsutil import append_jsonl, read_jsonl_with_recovery, read_json
from ..ids import new_uuid7, validate_uuid7
from ..timeutil import parse_timestamp, timestamp_now
from .questions import QuestionRef


@dataclass(frozen=True)
class CareerCandidateMarkEvent:
    event_id: str
    occurred_at: str
    target_kind: str
    target_id: str
    target_revision_at_event: int | None
    action: str
    note: str | None = None
    question_refs: tuple[dict[str, str], ...] = ()

    @property
    def entry_id(self) -> str | None:
        """Compatibility view for pre-Experience entry marks."""
        return self.target_id if self.target_kind == "entry" else None

    @property
    def entry_revision_at_event(self) -> int | None:
        return self.target_revision_at_event if self.target_kind == "entry" else None

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "CareerCandidateMarkEvent":
        event_id = validate_uuid7(raw.get("event_id"), "event_id")
        occurred_at = raw.get("occurred_at")
        parse_timestamp(occurred_at, "occurred_at")
        target_kind = raw.get("target_kind", "entry")
        if target_kind not in {"entry", "experience"}:
            raise ValidationError("candidate mark target_kind must be entry or experience")
        target_id = validate_uuid7(raw.get("target_id", raw.get("entry_id")), "target_id")
        revision = raw.get("target_revision_at_event", raw.get("entry_revision_at_event"))
        if target_kind == "entry":
            if not isinstance(revision, int) or revision < 1:
                raise ValidationError("entry candidate marks require a positive target revision")
        elif revision is not None:
            raise ValidationError("experience candidate marks cannot include an entry revision")
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
        return cls(event_id, occurred_at, target_kind, target_id, revision, action, note.strip() if note else None, tuple(normalized_refs))

    def to_dict(self) -> dict[str, Any]:
        value = {
            "event_id": self.event_id, "occurred_at": self.occurred_at,
            "target_kind": self.target_kind, "target_id": self.target_id,
            "target_revision_at_event": self.target_revision_at_event,
            "action": self.action, "note": self.note,
            "question_refs": [dict(ref) for ref in self.question_refs],
        }
        # Preserve the old keys in new entry events for older local readers.
        if self.target_kind == "entry":
            value["entry_id"] = self.target_id
            value["entry_revision_at_event"] = self.target_revision_at_event
        return value


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

    def current(self) -> dict[tuple[str, str], CareerCandidateMarkEvent]:
        current: dict[tuple[str, str], CareerCandidateMarkEvent] = {}
        for event in self._events():
            current[(event.target_kind, event.target_id)] = event
        return {target: event for target, event in current.items() if event.action == "mark"}

    def get(self, target_id: str, *, target_kind: str = "entry") -> CareerCandidateMarkEvent | None:
        target_id = validate_uuid7(target_id, "target_id")
        if target_kind not in {"entry", "experience"}:
            raise ValidationError("target_kind must be entry or experience")
        return self.current().get((target_kind, target_id))

    def list(self, *, include_orphans: bool = True) -> list[dict[str, Any]]:
        entries = {entry.entry_id: entry for entry in self.vault.all_current_entries()}
        experiences = {
            path.stem for path in (self.vault.root / "catalog/entities").glob("*.json")
            if self._is_experience(path)
        }
        result = []
        for event in sorted(self.current().values(), key=lambda item: (item.occurred_at, item.target_kind, item.target_id)):
            value = event.to_dict()
            value["orphaned"] = event.target_id not in entries if event.target_kind == "entry" else event.target_id not in experiences
            if include_orphans or not value["orphaned"]:
                result.append(value)
        return result

    @staticmethod
    def _is_experience(path: Any) -> bool:
        try:
            return read_json(path).get("kind") == "experience"
        except (OSError, ValueError, TypeError):
            return False

    def _append(self, event: CareerCandidateMarkEvent) -> dict[str, Any]:
        with self.vault.write_lock():
            append_jsonl(self.path, event.to_dict())
        return event.to_dict()

    def mark(
        self,
        target_id: str,
        *,
        target_kind: str = "entry",
        note: str | None = None,
        question_refs: list[Mapping[str, str]] | None = None,
    ) -> dict[str, Any]:
        target_id = validate_uuid7(target_id, "target_id")
        if target_kind == "entry":
            target = self.vault.get_current_entry(target_id)
            revision = target.revision
        elif target_kind == "experience":
            path = self.vault.root / "catalog/entities" / f"{target_id}.json"
            if not path.exists() or read_json(path).get("kind") != "experience":
                raise FileNotFoundError(f"experience not found: {target_id}")
            revision = None
        else:
            raise ValidationError("target_kind must be entry or experience")
        existing = self.get(target_id, target_kind=target_kind)
        refs = [QuestionRef.from_value(ref).to_dict() for ref in question_refs or []]
        normalized_note = note.strip() if note else None
        if existing is not None and existing.note == normalized_note and list(existing.question_refs) == refs:
            value = existing.to_dict()
            value["idempotent"] = True
            return value
        event = CareerCandidateMarkEvent(new_uuid7(), timestamp_now(), target_kind, target_id, revision, "mark", normalized_note, tuple(refs))
        value = self._append(event)
        value["idempotent"] = False
        return value

    def unmark(self, target_id: str, *, target_kind: str = "entry") -> dict[str, Any]:
        target_id = validate_uuid7(target_id, "target_id")
        existing = self.get(target_id, target_kind=target_kind)
        if existing is None:
            if target_kind == "entry":
                self.vault.get_current_entry(target_id)
            elif target_kind == "experience":
                path = self.vault.root / "catalog/entities" / f"{target_id}.json"
                if not path.exists() or read_json(path).get("kind") != "experience":
                    raise FileNotFoundError(f"experience not found: {target_id}")
            else:
                raise ValidationError("target_kind must be entry or experience")
            return {"target_kind": target_kind, "target_id": target_id, "action": "unmark", "idempotent": True}
        revision = self.vault.get_current_entry(target_id).revision if target_kind == "entry" else None
        event = CareerCandidateMarkEvent(new_uuid7(), timestamp_now(), target_kind, target_id, revision, "unmark")
        value = self._append(event)
        value["idempotent"] = False
        return value
