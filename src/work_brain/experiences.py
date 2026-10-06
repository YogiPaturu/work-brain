"""Source-backed professional Experience read models.

Experiences are stable catalog entities.  This module never stores a second
copy of professional facts: cards and hydrated views are derived from linked
SessionEntry revisions and can be rebuilt at any time.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from datetime import timezone
from typing import Any, Iterable, Mapping

from .domain import SessionEntry
from .domain import normalize_alias
from .errors import IntegrityError, ValidationError
from .fsutil import canonical_json_bytes, read_json
from .ids import validate_uuid7
from .retrieval import EvidenceRetriever
from .services import ProjectionMaintenance
from .timeutil import parse_timestamp


MAX_EXPERIENCE_CARD_REFS = 12
MAX_EXPERIENCE_RESULTS = 20
MAX_RELATED_RESULTS = 20
MAX_RELATED_QUERY_CHARS = 1000
MAX_MINING_PAGE_SIZE = 20
MINING_CURSOR_VERSION = 1


@dataclass(frozen=True)
class ExperienceCard:
    experience_id: str
    title: str
    workspace: dict[str, Any] | None
    project: dict[str, Any] | None
    first_occurrence: str | None
    last_occurrence: str | None
    entry_count: int
    domain_tags: list[str]
    supporting_entry_refs: list[dict[str, Any]]
    evidence_signals: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return {
            "experience_id": self.experience_id,
            "title": self.title,
            "workspace": self.workspace,
            "project": self.project,
            "first_occurrence": self.first_occurrence,
            "last_occurrence": self.last_occurrence,
            "entry_count": self.entry_count,
            "domain_tags": list(self.domain_tags),
            "supporting_entry_refs": list(self.supporting_entry_refs),
            "evidence_signals": dict(self.evidence_signals),
        }


class ExperienceService:
    """Deterministic Experience listing, search, and hydration boundary."""

    def __init__(self, vault: Any, *, retriever: EvidenceRetriever | None = None):
        self.vault = vault
        self.retriever = retriever or EvidenceRetriever(vault)

    def list(self, *, limit: int = 8, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if not isinstance(limit, int) or not 1 <= limit <= MAX_EXPERIENCE_RESULTS:
            raise ValidationError(f"limit must be between 1 and {MAX_EXPERIENCE_RESULTS}")
        groups = self._groups(filters=filters)
        cards = [self._card(experience_id, entries).to_dict() for experience_id, entries in groups.items()]
        cards.sort(key=lambda card: (card["last_occurrence"] or "", card["experience_id"]), reverse=True)
        return {"status": "ok", "experiences": cards[:limit]}

    def search(
        self,
        query: str,
        *,
        filters: Mapping[str, Any] | None = None,
        page_size: int = 8,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        evidence = self.retriever.search(query, filters=filters, page_size=page_size, cursor=cursor)
        cards = self.candidates_from_evidence(evidence).get("experiences", [])
        return {
            "status": evidence.get("status", "ok"),
            "degraded_components": evidence.get("degraded_components", []),
            "incomplete": evidence.get("incomplete", False),
            "experiences": cards,
            "next_cursor": evidence.get("next_cursor"),
            "embedding": evidence.get("embedding"),
        }

    def related(self, entry_id: str, *, limit: int = 8) -> dict[str, Any]:
        """Find bounded, source-verified evidence related to one current entry.

        Retrieval supplies the ranking, while source entry records remain
        authoritative for current revisions, context eligibility, and
        Experience links. This operation never publishes an association.
        """
        if not isinstance(limit, int) or not 1 <= limit <= MAX_RELATED_RESULTS:
            raise ValidationError(f"limit must be between 1 and {MAX_RELATED_RESULTS}")
        anchor = self._current_entry_including_archived(entry_id)
        workspace = self._context_descriptor(anchor, "workspace_entity_id", "workspace")
        project = self._context_descriptor(anchor, "project_entity_id", "project")
        experience_ids = self._experience_ids(anchor)

        filters: dict[str, list[str]] = {}
        if anchor.workspace_entity_id is not None:
            filters["workspaces"] = [anchor.workspace_entity_id]
        if anchor.project_entity_id is not None:
            filters["projects"] = [anchor.project_entity_id]
        evidence = self.retriever.search(
            self._related_query(anchor),
            filters=filters,
            page_size=MAX_RELATED_RESULTS,
        )
        current = {
            entry.entry_id: entry
            for entry in self.vault.all_current_entries(include_archived=True)
        }
        candidates: list[dict[str, Any]] = []
        anchor_context = (anchor.workspace_entity_id, anchor.project_entity_id)
        for card in evidence.get("cards", []):
            if not isinstance(card, Mapping):
                continue
            ref = card.get("ref")
            if not isinstance(ref, Mapping) or not isinstance(ref.get("entry_id"), str):
                continue
            candidate = current.get(ref["entry_id"])
            if candidate is None or candidate.entry_id == anchor.entry_id:
                continue
            if (candidate.workspace_entity_id, candidate.project_entity_id) != anchor_context:
                continue
            candidate_experience_ids = self._experience_ids(candidate)
            experience_descriptors = [
                self._experience_descriptor(experience_id)
                for experience_id in candidate_experience_ids
            ]
            candidates.append({
                "candidate_type": "experience_member" if experience_descriptors else "ungrouped_entry",
                "entry_ref": {"entry_id": candidate.entry_id, "revision": candidate.revision},
                "title": candidate.title,
                "when": candidate.occurrence.to_dict(),
                "matched_evidence": dict(card.get("match", {})) if isinstance(card.get("match", {}), Mapping) else {},
                "experience": experience_descriptors[0] if len(experience_descriptors) == 1 else None,
                "experiences": experience_descriptors,
            })
            if len(candidates) >= limit:
                break

        result: dict[str, Any] = {
            "status": evidence.get("status", "ok"),
            "anchor": {
                "entry_id": anchor.entry_id,
                "revision": anchor.revision,
                "title": anchor.title,
                "workspace": workspace,
                "project": project,
                "experience_ids": experience_ids,
            },
            "candidates": candidates,
            "degraded_components": list(evidence.get("degraded_components", [])),
            "incomplete": bool(evidence.get("incomplete", False)),
            "embedding": evidence.get("embedding"),
        }
        if "omitted_stale_entries" in evidence:
            result["omitted_stale_entries"] = evidence["omitted_stale_entries"]
        return result

    def mine(
        self,
        *,
        page_size: int = 5,
        related_limit: int = 6,
        filters: Mapping[str, Any] | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Return a bounded, source-backed page of ungrouped entry anchors.

        Anchor selection is deliberately independent of retrieval.  The
        opaque cursor is a keyset continuation over the source chronology, so
        associations made between requests cannot cause offset drift.
        """
        if not isinstance(page_size, int) or not 1 <= page_size <= MAX_MINING_PAGE_SIZE:
            raise ValidationError(f"page_size must be between 1 and {MAX_MINING_PAGE_SIZE}")
        if not isinstance(related_limit, int) or not 1 <= related_limit <= MAX_RELATED_RESULTS:
            raise ValidationError(f"related_limit must be between 1 and {MAX_RELATED_RESULTS}")
        if filters is not None and not isinstance(filters, Mapping):
            raise ValidationError("filters must be an object")
        normalized_filters = dict(filters or {})
        self._validate_filters(normalized_filters)
        fingerprint = hashlib.sha256(canonical_json_bytes({
            "version": MINING_CURSOR_VERSION,
            "filters": normalized_filters,
        })).hexdigest()

        continuation = self._decode_mining_cursor(cursor) if cursor else None
        if continuation is not None and (
            continuation.get("version") != MINING_CURSOR_VERSION
            or continuation.get("filter_fingerprint") != fingerprint
        ):
            return {
                "status": "cursor_expired",
                "items": [],
                "next_cursor": None,
                "incomplete": False,
                "degraded_components": [],
            }

        anchors = [
            entry for entry in self.vault.all_current_entries()
            if not self._experience_ids(entry) and self._matches(entry, normalized_filters)
        ]
        anchors.sort(key=self._mining_key)
        if continuation is not None:
            last_key = continuation["last_key"]
            last_entry_id = continuation["last_entry_id"]
            anchors = [
                entry for entry in anchors
                if (self._mining_key(entry), entry.entry_id) > (last_key, last_entry_id)
            ]

        page = anchors[:page_size]
        items = [self.related(entry.entry_id, limit=related_limit) for entry in page]
        degraded_components = sorted({
            component
            for item in items
            for component in item.get("degraded_components", [])
        })
        incomplete = any(bool(item.get("incomplete")) or item.get("status") != "ok" for item in items)
        next_cursor = None
        if len(anchors) > len(page) and page:
            last = page[-1]
            next_cursor = self._encode_mining_cursor({
                "version": MINING_CURSOR_VERSION,
                "filter_fingerprint": fingerprint,
                "last_key": self._mining_key(last),
                "last_entry_id": last.entry_id,
            })
        return {
            "status": "degraded" if incomplete else "ok",
            "items": items,
            "next_cursor": next_cursor,
            "incomplete": incomplete,
            "degraded_components": degraded_components,
        }

    def get(self, experience_id: str) -> dict[str, Any]:
        experience_id = validate_uuid7(experience_id, "experience_id")
        groups = self._groups()
        entries = groups.get(experience_id)
        if entries is None:
            raise FileNotFoundError(f"experience not found: {experience_id}")
        return self._card(experience_id, entries).to_dict()

    def hydrate(self, experience_id: str, *, refs: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
        card = self.get(experience_id)
        selected = refs or card["supporting_entry_refs"][:4]
        if not selected:
            return {"experience": card, "evidence": {"items": []}}
        allowed_refs = {
            (item["entry_id"], item["revision"])
            for item in card["supporting_entry_refs"]
        }
        for ref in selected:
            if (ref.get("entry_id"), ref.get("revision")) not in allowed_refs:
                raise ValidationError("experience hydration refs must belong to the experience")
        return {"experience": card, "evidence": self.retriever.hydrate(list(selected)[:4])}

    def associate(
        self,
        entry_id: str,
        *,
        experience_id: str | None = None,
        experience_name: str | None = None,
        remove: bool = False,
        move: bool = False,
        _maintain: bool = True,
    ) -> dict[str, Any]:
        entry = self.vault.associate_entry_experience(
            entry_id,
            experience_id=experience_id,
            experience_name=experience_name,
            remove=remove,
            move=move,
        )
        maintenance = None
        if _maintain:
            maintenance = ProjectionMaintenance(self.vault).after_source_commit(entry)
        result = {"entry_id": entry.entry_id, "revision": entry.revision, "experience_ids": [
            ref["entity_id"] for ref in entry.entity_refs if ref["relation"] == "experience"
        ]}
        result["source_status"] = "committed"
        if maintenance is not None:
            result.update(maintenance.to_dict())
        return result

    def associate_entries(
        self,
        entry_ids: Iterable[str],
        *,
        experience_id: str | None = None,
        experience_name: str | None = None,
        remove: bool = False,
        move: bool = False,
    ) -> dict[str, Any]:
        selected_ids = list(entry_ids)
        if not selected_ids:
            raise ValidationError("at least one entry_id is required")
        entries = [self.vault.get_current_entry(entry_id) for entry_id in selected_ids]
        if not remove:
            existing = [
                ref["entity_id"] for entry in entries for ref in entry.entity_refs
                if ref["relation"] == "experience"
            ]
            if existing and not move:
                raise ValidationError("entry already belongs to an Experience; use move=true to replace it")
            contexts = {(entry.workspace_entity_id, entry.project_entity_id) for entry in entries}
            if len(contexts) > 1:
                raise ValidationError("all entries in one Experience association must share workspace/project context")
            resolved_experience_id = experience_id
            if resolved_experience_id is None and experience_name is not None:
                resolved_experience_id = self.vault._resolve_experience_entity(None, experience_name)
            if resolved_experience_id is not None:
                for entry in entries:
                    self.vault.validate_experience_context(
                        [resolved_experience_id], entry.workspace_entity_id, entry.project_entity_id,
                        excluding_entry_id=entry.entry_id,
                    )
            experience_id = resolved_experience_id
        updated = [self.associate(
            entry_id,
            experience_id=experience_id,
            experience_name=experience_name,
            remove=remove,
            move=move,
            _maintain=False,
        ) for entry_id in selected_ids]
        maintenance = ProjectionMaintenance(self.vault).after_source_commits(
            tuple(self.vault.get_current_entry(item["entry_id"]) for item in updated)
        ) if updated else None
        result: dict[str, Any] = {
            "source_status": "committed",
            "updated": updated,
            "count": len(updated),
        }
        if maintenance is not None:
            result.update(maintenance.to_dict())
        return result

    def candidates_from_evidence(self, evidence: Mapping[str, Any]) -> dict[str, Any]:
        """Aggregate ranked evidence cards without inventing story quality."""
        raw_cards = evidence.get("cards", [])
        if not isinstance(raw_cards, list):
            return {"experiences": [], "ungrouped": []}
        current = {entry.entry_id: entry for entry in self.vault.all_current_entries()}
        grouped: dict[str, dict[str, Any]] = {}
        ungrouped: list[dict[str, Any]] = []
        for rank, card in enumerate(raw_cards, 1):
            if not isinstance(card, Mapping):
                continue
            ref = card.get("ref")
            if not isinstance(ref, Mapping) or not isinstance(ref.get("entry_id"), str):
                continue
            entry = current.get(ref["entry_id"])
            if entry is None:
                continue
            experience_ids = self._experience_ids(entry)
            if not experience_ids:
                ungrouped.append({
                    "candidate_type": "ungrouped_entry",
                    "title": entry.title,
                    "supporting_entry_refs": [{"entry_id": entry.entry_id, "revision": entry.revision}],
                    "matched_evidence": dict(card),
                    "_best_rank": rank,
                })
                continue
            for experience_id in experience_ids:
                item = grouped.setdefault(experience_id, {"best_rank": rank, "matched_refs": [], "matches": []})
                item["best_rank"] = min(item["best_rank"], rank)
                item["matched_refs"].append({"entry_id": entry.entry_id, "revision": entry.revision})
                item["matches"].append(dict(card))
        experiences: list[dict[str, Any]] = []
        all_groups = self._groups()
        for experience_id, item in grouped.items():
            entries = all_groups.get(experience_id, [])
            if not entries:
                continue
            candidate = self._card(experience_id, entries).to_dict()
            candidate["candidate_type"] = "experience"
            candidate["matched_entry_refs"] = item["matched_refs"]
            candidate["matched_evidence"] = item["matches"][:3]
            candidate["_best_rank"] = item["best_rank"]
            experiences.append(candidate)
        experiences.sort(key=lambda item: (item["_best_rank"], item["experience_id"]))
        ungrouped.sort(key=lambda item: (item["_best_rank"], item["supporting_entry_refs"][0]["entry_id"]))
        ordered = sorted(
            [*experiences, *ungrouped],
            key=lambda item: (item["_best_rank"], item.get("experience_id", item["supporting_entry_refs"][0]["entry_id"])),
        )
        public_experiences = [{key: value for key, value in item.items() if key != "_best_rank"} for item in experiences]
        public_ungrouped = [{key: value for key, value in item.items() if key != "_best_rank"} for item in ungrouped]
        return {"experiences": public_experiences, "ungrouped": public_ungrouped, "ordered": ordered}

    def _current_entry_including_archived(self, entry_id: str) -> SessionEntry:
        entry_id = validate_uuid7(entry_id, "entry_id")
        for entry in self.vault.all_current_entries(include_archived=True):
            if entry.entry_id == entry_id:
                return entry
        raise FileNotFoundError(f"entry not found: {entry_id}")

    def _context_descriptor(self, entry: SessionEntry, field: str, kind: str) -> dict[str, str] | None:
        entity_id = getattr(entry, field)
        if entity_id is None:
            return None
        path = self.vault.root / "catalog/entities" / f"{entity_id}.json"
        if not path.exists():
            raise IntegrityError(f"missing {kind} entity: {entity_id}")
        entity = read_json(path)
        if entity.get("kind") != kind:
            raise IntegrityError(f"entry context is not a {kind} entity: {entity_id}")
        return {"entity_id": entity["entity_id"], "name": entity["canonical_name"]}

    def _experience_descriptor(self, experience_id: str) -> dict[str, str]:
        path = self.vault.root / "catalog/entities" / f"{experience_id}.json"
        if not path.exists():
            raise IntegrityError(f"missing experience entity: {experience_id}")
        entity = read_json(path)
        if entity.get("kind") != "experience":
            raise IntegrityError(f"entry relation points to a non-experience entity: {experience_id}")
        return {"experience_id": experience_id, "title": entity["canonical_name"]}

    def _related_query(self, entry: SessionEntry) -> str:
        parts = [entry.title, entry.summary]
        for section in ("context", "reasoning", "contribution", "decisions_actions", "outcomes"):
            statements = entry.sections.get(section, [])
            if statements:
                text = statements[0].text.strip()
                if text:
                    parts.append(text[:240])
        query = " ".join(part.strip() for part in parts if part and part.strip())
        return query[:MAX_RELATED_QUERY_CHARS]

    @staticmethod
    def _mining_key(entry: SessionEntry) -> str:
        value = entry.occurrence.start or entry.created_at
        if entry.occurrence.precision == "instant" or entry.occurrence.start is None:
            return parse_timestamp(value).astimezone(timezone.utc).isoformat()
        return value

    @staticmethod
    def _encode_mining_cursor(payload: Mapping[str, Any]) -> str:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_mining_cursor(value: str) -> dict[str, Any]:
        if not isinstance(value, str) or not value:
            raise ValidationError("cursor must be an opaque mining continuation")
        try:
            padded = value + "=" * (-len(value) % 4)
            decoded = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        except (binascii.Error, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError("cursor must be an opaque mining continuation") from exc
        if not isinstance(decoded, dict):
            raise ValidationError("cursor must be an opaque mining continuation")
        required = ("version", "filter_fingerprint", "last_key", "last_entry_id")
        if (
            not isinstance(decoded.get("version"), int)
            or not isinstance(decoded.get("filter_fingerprint"), str)
            or not isinstance(decoded.get("last_key"), str)
            or not isinstance(decoded.get("last_entry_id"), str)
            or any(key not in decoded for key in required)
        ):
            raise ValidationError("cursor must be an opaque mining continuation")
        return decoded

    def _groups(self, *, filters: Mapping[str, Any] | None = None) -> dict[str, list[SessionEntry]]:
        groups: dict[str, list[SessionEntry]] = {}
        for entry in self.vault.all_current_entries():
            if not self._matches(entry, filters or {}):
                continue
            for experience_id in self._experience_ids(entry):
                groups.setdefault(experience_id, []).append(entry)
        return groups

    def _experience_ids(self, entry: SessionEntry) -> list[str]:
        result: list[str] = []
        for ref in entry.entity_refs:
            if ref["relation"] != "experience":
                continue
            path = self.vault.root / "catalog/entities" / f"{ref['entity_id']}.json"
            if not path.exists():
                raise IntegrityError(f"missing experience entity: {ref['entity_id']}")
            entity = read_json(path)
            if entity.get("kind") != "experience":
                raise IntegrityError(f"entry relation points to a non-experience entity: {ref['entity_id']}")
            if ref["entity_id"] not in result:
                result.append(ref["entity_id"])
        return result

    def _card(self, experience_id: str, entries: Iterable[SessionEntry]) -> ExperienceCard:
        ordered = sorted(entries, key=lambda entry: (entry.created_at, entry.entry_id))
        path = self.vault.root / "catalog/entities" / f"{experience_id}.json"
        if not path.exists():
            raise IntegrityError(f"missing experience entity: {experience_id}")
        entity = read_json(path)
        if entity.get("kind") != "experience":
            raise IntegrityError(f"entity is not an experience: {experience_id}")
        workspace = self._context(ordered, "workspace_entity_id")
        project = self._context(ordered, "project_entity_id")
        tags: list[str] = []
        for entry in ordered:
            for tag in entry.domain_tags:
                if tag not in tags:
                    tags.append(tag)
        starts = [entry.occurrence.start or entry.created_at for entry in ordered]
        ends = [entry.occurrence.end or entry.occurrence.start or entry.created_at for entry in ordered]
        signals = {
            section: any(bool(entry.sections[section]) for entry in ordered)
            for section in ("contribution", "alternatives_tradeoffs", "decisions_actions", "outcomes", "learning", "open_questions")
        }
        refs = [{"entry_id": entry.entry_id, "revision": entry.revision} for entry in ordered]
        return ExperienceCard(
            experience_id=experience_id,
            title=entity["canonical_name"],
            workspace=workspace,
            project=project,
            first_occurrence=min(starts) if starts else None,
            last_occurrence=max(ends) if ends else None,
            entry_count=len(ordered),
            domain_tags=sorted(tags),
            supporting_entry_refs=refs[:MAX_EXPERIENCE_CARD_REFS],
            evidence_signals=signals,
        )

    def _context(self, entries: list[SessionEntry], field: str) -> dict[str, Any] | None:
        ids = {getattr(entry, field) for entry in entries}
        if len(ids) > 1:
            raise IntegrityError(f"experience entries have conflicting {field}")
        entity_id = next(iter(ids), None)
        if entity_id is not None:
            path = self.vault.root / "catalog/entities" / f"{entity_id}.json"
            if not path.exists():
                raise IntegrityError(f"missing context entity: {entity_id}")
            entity = read_json(path)
            return {"entity_id": entity["entity_id"], "kind": entity["kind"], "name": entity["canonical_name"]}
        return None

    def _matches(self, entry: SessionEntry, filters: Mapping[str, Any]) -> bool:
        self._validate_filters(filters)
        for field, entity_id in (("workspaces", entry.workspace_entity_id), ("projects", entry.project_entity_id)):
            values = filters.get(field, [])
            if values:
                if entity_id is None:
                    return False
                path = self.vault.root / "catalog/entities" / f"{entity_id}.json"
                if not path.exists():
                    raise IntegrityError(f"missing context entity: {entity_id}")
                entity = read_json(path)
                names = {entity["entity_id"], normalize_alias(entity["canonical_name"])}
                names.update(normalize_alias(alias) for alias in entity.get("aliases", []))
                if not all(value in names or normalize_alias(value) in names for value in values):
                    return False
        tags = filters.get("domain_tags", [])
        if tags and not set(tags).issubset(set(entry.domain_tags)):
            return False
        value = entry.occurrence.start or entry.created_at
        if filters.get("occurred_after") is not None and value < str(filters["occurred_after"]):
            return False
        if filters.get("occurred_before") is not None and value >= str(filters["occurred_before"]):
            return False
        return True

    @staticmethod
    def _validate_filters(filters: Mapping[str, Any]) -> None:
        allowed = {"workspaces", "projects", "domain_tags", "occurred_after", "occurred_before"}
        unknown = sorted(set(filters) - allowed)
        if unknown:
            raise ValidationError(f"unknown experience filter: {unknown[0]}")
        for field in ("workspaces", "projects", "domain_tags"):
            values = filters.get(field, [])
            if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValidationError(f"{field} must be a list of non-empty strings")
