from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping
import json

from .domain import ENTRY_SECTIONS, ENTITY_KINDS, STATE_KINDS, MUTATION_OPS, Occurrence, Statement, normalize_domain_tags
from .errors import IntegrityError, ValidationError
from .fsutil import canonical_json_bytes, read_json
from .ids import new_uuid7, validate_uuid7
from .instructions import SkillLoader
from .timeutil import timestamp_now


FORBIDDEN_DRAFT_FIELDS = {
    "session_id", "entry_id", "revision", "commit_id", "created_at", "supersedes_revision",
    "revision_reason", "provenance_kind", "runtime", "model_id", "sops", "occurrence", "source_fingerprint",
}


@dataclass(frozen=True)
class ValidatedDraft:
    title: str
    summary: str
    historical_occurrence: dict[str, Any] | None
    domain_tags: list[str]
    workspace_name: str
    project_name: str
    sections: dict[str, list[dict[str, Any]]]
    state_changes: list[dict[str, Any]]
    entity_candidates: list[dict[str, Any]]
    artifact_candidates: list[dict[str, Any]]
    source_entry_refs: list[dict[str, Any]]


@dataclass(frozen=True)
class EntityCreation:
    entity_id: str
    kind: str
    canonical_name: str
    aliases: list[str]
    description: str | None


@dataclass(frozen=True)
class ArtifactCreation:
    artifact_id: str
    kind: str
    label: str
    locator: str
    external_id: str | None
    notes: str | None


@dataclass(frozen=True)
class CommitPlan:
    payload: dict[str, Any]
    entity_creations: tuple[EntityCreation, ...]
    artifact_creations: tuple[ArtifactCreation, ...]
    fingerprint: str


class CommitDraftValidator:
    def validate(self, raw: Mapping[str, Any], *, turn_count: int, workflow: str) -> ValidatedDraft:
        if not isinstance(raw, Mapping):
            raise ValidationError("CommitDraft must be a JSON object")
        forbidden = sorted(FORBIDDEN_DRAFT_FIELDS.intersection(raw))
        if forbidden:
            raise ValidationError(f"CommitDraft contains runtime-owned fields: {', '.join(forbidden)}")
        title, summary = raw.get("title"), raw.get("summary")
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 240:
            raise ValidationError("title must be a non-empty string of at most 240 characters")
        if not isinstance(summary, str) or len(summary) > 4000:
            raise ValidationError("summary must be a string of at most 4000 characters")
        historical = raw.get("historical_occurrence")
        if workflow == "backfill" and historical is None:
            raise ValidationError("backfill CommitDraft requires historical_occurrence")
        if workflow != "backfill" and historical is not None:
            raise ValidationError("historical_occurrence is only allowed for backfill")
        if historical is not None:
            Occurrence.from_dict(historical)
        if "domains" in raw:
            raise ValidationError("CommitDraft uses domain_tags, not domains")
        domain_tags = self._domain_tags(raw.get("domain_tags", []))
        if "workspace" not in raw:
            raise ValidationError("CommitDraft must include workspace; infer it or clarify it before committing")
        if "project" not in raw:
            raise ValidationError("CommitDraft must include project; infer it or clarify it before committing")
        workspace = self._context_name(raw["workspace"], "workspace")
        project = self._context_name(raw["project"], "project")
        sections_raw = raw.get("sections")
        if not isinstance(sections_raw, Mapping) or set(sections_raw) != set(ENTRY_SECTIONS):
            raise ValidationError("sections must contain exactly the supported entry section names")
        sections: dict[str, list[dict[str, Any]]] = {}
        for section in ENTRY_SECTIONS:
            values = sections_raw[section]
            if not isinstance(values, list):
                raise ValidationError(f"sections.{section} must be a list")
            sections[section] = [self._statement(value, turn_count, section) for value in values]
        state_changes = [self._state_change(value, turn_count) for value in self._list_field(raw, "state_changes")]
        entities = [self._entity(value) for value in self._list_field(raw, "entity_candidates")]
        artifacts = [self._artifact(value) for value in self._list_field(raw, "artifact_candidates")]
        source_refs = [self._source_ref(value) for value in self._list_field(raw, "source_entry_refs")]
        return ValidatedDraft(title.strip(), summary.strip(), historical, domain_tags, workspace, project, sections, state_changes, entities, artifacts, source_refs)

    @staticmethod
    def _list_field(raw: Mapping[str, Any], name: str) -> list[Any]:
        value = raw.get(name, [])
        if not isinstance(value, list):
            raise ValidationError(f"{name} must be a list")
        return value

    @staticmethod
    def _statement(value: Any, turn_count: int, section: str) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise ValidationError(f"sections.{section} items must be objects")
        statement = Statement.from_dict(value)
        if not statement.source_turns:
            raise ValidationError(f"sections.{section} statements must reference supporting source_turns")
        if any(turn > turn_count for turn in statement.source_turns):
            raise ValidationError(f"sections.{section} references a missing source turn")
        return statement.to_dict()

    @staticmethod
    def _domain_tags(value: Any) -> list[str]:
        return normalize_domain_tags(value, "domain_tags")

    @staticmethod
    def _turns(value: Any, turn_count: int, field: str) -> list[int]:
        if not isinstance(value, list) or any(not isinstance(item, int) or item < 1 or item > turn_count for item in value):
            raise ValidationError(f"{field} must reference existing positive turn sequences")
        if not value:
            raise ValidationError(f"{field} must reference at least one supporting source turn")
        return value

    def _state_change(self, value: Any, turn_count: int) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise ValidationError("state_changes items must be objects")
        operation = value.get("operation")
        if operation not in MUTATION_OPS:
            raise ValidationError("state_changes.operation is invalid")
        target = value.get("target_state_item_id")
        if operation == "create" and target is not None:
            raise ValidationError("create state changes cannot name a target")
        if target is not None:
            validate_uuid7(target, "target_state_item_id")
        kind = value.get("kind")
        if kind is not None and kind not in STATE_KINDS:
            raise ValidationError("state_changes.kind is invalid")
        fields = value.get("fields", {})
        if not isinstance(fields, dict):
            raise ValidationError("state_changes.fields must be an object")
        if operation == "create" and (kind is None or not isinstance(fields.get("title"), str) or not fields["title"]):
            raise ValidationError("create state changes require kind and fields.title")
        allowed_fields = {"title", "status", "project_entity_id", "details", "next_action", "waiting_on", "due_at", "updated_at", "closed_at"}
        unsupported = sorted(set(fields) - allowed_fields)
        if unsupported:
            raise ValidationError(f"state_changes.fields contains unsupported fields: {', '.join(unsupported)}")
        if "status" in fields and fields["status"] not in {"active", "waiting", "done", "dropped"}:
            raise ValidationError("state_changes.fields.status is invalid")
        if "project_entity_id" in fields and fields["project_entity_id"] is not None:
            validate_uuid7(fields["project_entity_id"], "state_changes.fields.project_entity_id")
        return {"operation": operation, "target_state_item_id": target, "kind": kind, "fields": dict(fields),
                "source_turns": self._turns(value.get("source_turns", []), turn_count, "state_changes.source_turns")}

    @staticmethod
    def _entity(value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise ValidationError("entity_candidates items must be objects")
        entity_id = value.get("entity_id")
        if entity_id is not None:
            validate_uuid7(entity_id, "entity_id")
        kind = value.get("kind")
        if kind is not None and kind not in ENTITY_KINDS:
            raise ValidationError("entity candidate kind is invalid")
        name = value.get("canonical_name")
        if entity_id is None and (kind is None or not isinstance(name, str) or not name.strip()):
            raise ValidationError("new entity candidates require kind and canonical_name")
        aliases = value.get("aliases", [])
        if not isinstance(aliases, list) or any(not isinstance(item, str) or not item for item in aliases):
            raise ValidationError("entity candidate aliases must be strings")
        default_relation = "experience" if kind == "experience" else "subject"
        relation = value.get("relation", default_relation)
        if not isinstance(relation, str) or not relation.strip():
            raise ValidationError("entity candidate relation must be a non-empty token")
        if kind == "experience" and relation.strip().casefold() != "experience":
            raise ValidationError("experience entity candidates must use relation=experience")
        return {"entity_id": entity_id, "kind": kind, "canonical_name": name, "aliases": list(aliases),
                "description": value.get("description"), "relation": relation.strip().casefold()}

    @staticmethod
    def _context_name(value: Any, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"CommitDraft {field} must be a required non-empty string")
        return value.strip()

    @staticmethod
    def _artifact(value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise ValidationError("artifact_candidates items must be objects")
        artifact_id = value.get("artifact_id")
        if artifact_id is not None:
            validate_uuid7(artifact_id, "artifact_id")
        required = (value.get("kind"), value.get("label"), value.get("locator"))
        if artifact_id is None and any(not isinstance(item, str) or not item for item in required):
            raise ValidationError("new artifact candidates require kind, label, and locator")
        if not isinstance(value.get("relation", "supports"), str) or not value.get("relation", "supports").strip():
            raise ValidationError("artifact candidate relation must be a non-empty token")
        return {"artifact_id": artifact_id, "kind": value.get("kind"), "label": value.get("label"),
                "locator": value.get("locator"), "external_id": value.get("external_id"),
                "notes": value.get("notes"), "relation": value.get("relation", "supports")}

    @staticmethod
    def _source_ref(value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise ValidationError("source_entry_refs items must be objects")
        entry_id = validate_uuid7(value.get("entry_id"), "source_entry_refs.entry_id")
        revision = value.get("revision")
        if not isinstance(revision, int) or revision < 1:
            raise ValidationError("source_entry_refs.revision must be a positive integer")
        return {"entry_id": entry_id, "revision": revision}


class CommitResolver:
    def __init__(self, vault: Any, validator: CommitDraftValidator | None = None):
        self.vault = vault
        self.validator = validator or CommitDraftValidator()

    def publish(self, session_id: str, raw_draft: Mapping[str, Any], *, workflow: str, revision_reason: str = "initial_commit"):
        return self._publish_source(session_id, raw_draft, workflow=workflow, revision_reason=revision_reason)

    def publish_result(self, session_id: str, raw_draft: Mapping[str, Any], *, workflow: str, revision_reason: str = "initial_commit"):
        """Publish source evidence and report rebuildable subsystem status."""
        from .services import CommitPublicationResult, ProjectionMaintenance

        entry = self._publish_source(session_id, raw_draft, workflow=workflow, revision_reason=revision_reason)
        maintenance = ProjectionMaintenance(self.vault).after_source_commit(entry)
        return CommitPublicationResult.from_entry(entry, maintenance, self.vault.consume_source_warnings())

    def _publish_source(self, session_id: str, raw_draft: Mapping[str, Any], *, workflow: str, revision_reason: str = "initial_commit"):
        session = self.vault.read_session(session_id)
        turns = self.vault.list_turns(session_id)
        draft = self.validator.validate(raw_draft, turn_count=len(turns), workflow=workflow)
        self._require_user_authored_sources(draft, turns)
        state = self._state_items()
        mutations = []
        for change in draft.state_changes:
            target = change["target_state_item_id"] or new_uuid7()
            if change["operation"] != "create" and target not in state:
                raise ValidationError(f"state target does not exist: {target}")
            mutations.append({"mutation_id": new_uuid7(), "operation": change["operation"], "state_item_id": target,
                              "kind": change["kind"], "fields": change["fields"], "source_turns": change["source_turns"]})
        for mutation in mutations:
            if mutation["operation"] == "create":
                state[mutation["state_item_id"]] = True
            project_id = mutation["fields"].get("project_entity_id")
            if project_id is not None and not (self.vault.root / "catalog/entities" / f"{project_id}.json").exists():
                raise ValidationError(f"state project entity does not exist: {project_id}")
        source_refs = []
        known_revisions = {entry.entry_id: entry.revision for entry in self.vault.all_current_entries()}
        for ref in draft.source_entry_refs:
            if ref["entry_id"] not in known_revisions or known_revisions[ref["entry_id"]] < ref["revision"]:
                raise ValidationError(f"source entry reference is not available: {ref['entry_id']}@{ref['revision']}")
            source_refs.append({"kind": "entry", "id": ref["entry_id"], "revision": ref["revision"]})
        modes = self._merge_tokens(session.get("modes", []), [workflow])
        domain_tags = self._merge_tokens(session.get("domain_tags", []), draft.domain_tags)
        occurrence = draft.historical_occurrence or {
            "start": session["started_at"], "end": timestamp_now(), "precision": "instant", "label": None,
        }
        current_revisions = [entry.revision for entry in self.vault.all_current_entries() if entry.session_id == session_id]
        revision = max(current_revisions, default=0) + 1
        plan = self._plan_catalogs_and_payload(
            session_id=session_id,
            raw_draft=raw_draft,
            session=session,
            draft=draft,
            workflow=workflow,
            revision_reason=revision_reason,
            revision=revision,
            occurrence=occurrence,
            modes=modes,
            domain_tags=domain_tags,
            mutations=mutations,
            source_refs=source_refs,
        )
        with self.vault.write_lock():
            for creation in plan.entity_creations:
                self.vault.upsert_entity(
                    kind=creation.kind,
                    canonical_name=creation.canonical_name,
                    aliases=creation.aliases,
                    description=creation.description,
                    entity_id=creation.entity_id,
                )
            for creation in plan.artifact_creations:
                self.vault.upsert_artifact(
                    kind=creation.kind,
                    label=creation.label,
                    locator=creation.locator,
                    external_id=creation.external_id,
                    notes=creation.notes,
                    artifact_id=creation.artifact_id,
                )
            entry = self.vault.commit_entry(
                session_id,
                plan.payload,
                commit_fingerprint=plan.fingerprint,
                refresh_projections=False,
            )
        self.vault._best_effort_source_projections(affected_date=session["local_date"])
        return entry

    def _plan_catalogs_and_payload(
        self,
        *,
        session_id: str,
        raw_draft: Mapping[str, Any],
        session: Mapping[str, Any],
        draft: ValidatedDraft,
        workflow: str,
        revision_reason: str,
        revision: int,
        occurrence: Mapping[str, Any],
        modes: list[str],
        domain_tags: list[str],
        mutations: list[dict[str, Any]],
        source_refs: list[dict[str, Any]],
    ) -> CommitPlan:
        entity_refs, entity_creations, catalog = self._plan_entities(draft.entity_candidates)
        workspace_entity_id, workspace_creation = self._plan_context_name(draft.workspace_name, "workspace", catalog)
        if workspace_creation is not None:
            entity_creations.append(workspace_creation)
            catalog.append(self._creation_as_catalog(workspace_creation))
        project_entity_id, project_creation = self._plan_context_name(draft.project_name, "project", catalog)
        if project_creation is not None:
            entity_creations.append(project_creation)
            catalog.append(self._creation_as_catalog(project_creation))
        artifact_refs, artifact_creations = self._plan_artifacts(draft.artifact_candidates)
        payload = {
            "entry_id": session["entry_id"], "session_id": session_id, "revision": revision, "commit_id": new_uuid7(),
            "created_at": timestamp_now(), "supersedes_revision": revision - 1 if revision > 1 else None,
            "revision_reason": revision_reason,
            "provenance_kind": "reconstructed" if workflow == "backfill" or (session.get("runtime") or {}).get("capture_fidelity") == "imported" else "contemporaneous",
            "title": draft.title, "summary": draft.summary, "occurrence": occurrence, "modes": modes, "domain_tags": domain_tags,
            "workspace_entity_id": workspace_entity_id,
            "project_entity_id": project_entity_id,
            "sections": draft.sections, "state_mutations": mutations, "entity_refs": entity_refs,
            "artifact_refs": artifact_refs, "source_refs": source_refs,
        }
        fingerprint = hashlib.sha256(canonical_json_bytes({
            "session_id": session_id,
            "workflow": workflow,
            "revision_reason": revision_reason,
            "draft": raw_draft,
        })).hexdigest()
        return CommitPlan(payload, tuple(entity_creations), tuple(artifact_creations), fingerprint)

    @staticmethod
    def _require_user_authored_sources(draft: ValidatedDraft, turns: list[dict[str, Any]]) -> None:
        roles = {turn["sequence"]: turn["role"] for turn in turns}
        for section, statements in draft.sections.items():
            for statement in statements:
                if not any(roles[sequence] == "user" for sequence in statement["source_turns"]):
                    raise ValidationError(
                        f"sections.{section} statements must reference at least one user-authored source turn"
                    )
        for change in draft.state_changes:
            if not any(roles[sequence] == "user" for sequence in change["source_turns"]):
                raise ValidationError(
                    "state_changes.source_turns must reference at least one user-authored source turn"
                )

    def _state_items(self) -> dict[str, bool]:
        path = self.vault.root / "state/current.json"
        if not path.exists():
            return {}
        return {item["state_item_id"]: True for item in json.loads(path.read_text(encoding="utf-8")).get("items", [])}

    @staticmethod
    def _creation_as_catalog(creation: EntityCreation) -> dict[str, Any]:
        return {
            "entity_id": creation.entity_id,
            "kind": creation.kind,
            "canonical_name": creation.canonical_name,
            "aliases": creation.aliases,
            "description": creation.description,
        }

    def _plan_entities(
        self,
        candidates: list[dict[str, Any]],
    ) -> tuple[list[dict[str, str]], list[EntityCreation], list[dict[str, Any]]]:
        catalog = [read_json(path) for path in sorted((self.vault.root / "catalog/entities").glob("*.json"))]
        creations: list[EntityCreation] = []
        refs: list[dict[str, str]] = []
        for candidate in candidates:
            entity_id = candidate["entity_id"]
            if entity_id is not None:
                matches = [item for item in catalog if item["entity_id"] == entity_id]
                if not matches:
                    raise ValidationError(f"entity does not exist: {entity_id}")
                if candidate.get("kind") is not None and matches[0]["kind"] != candidate["kind"]:
                    raise ValidationError(f"entity {entity_id} is not a {candidate['kind']}")
            else:
                key = SkillLoader.normalize_token(candidate["canonical_name"])
                matches = [item for item in catalog if item["kind"] == candidate["kind"] and
                           (SkillLoader.normalize_token(item["canonical_name"]) == key or
                            any(SkillLoader.normalize_token(alias) == key for alias in item.get("aliases", [])))]
                if len(matches) > 1:
                    raise IntegrityError(f"ambiguous entity candidate: {candidate['canonical_name']}")
                if matches:
                    entity_id = matches[0]["entity_id"]
                else:
                    entity_id = new_uuid7()
                    creation = EntityCreation(entity_id, candidate["kind"], candidate["canonical_name"], list(candidate["aliases"]), candidate["description"])
                    creations.append(creation)
                    catalog.append(self._creation_as_catalog(creation))
            refs.append({"entity_id": entity_id, "relation": candidate["relation"]})
        return refs, creations, catalog

    def _plan_context_name(
        self,
        name: str,
        kind: str,
        catalog: list[dict[str, Any]],
    ) -> tuple[str, EntityCreation | None]:
        key = SkillLoader.normalize_token(name)
        matches = [item for item in catalog if item["kind"] == kind and
                   (SkillLoader.normalize_token(item["canonical_name"]) == key or
                    any(SkillLoader.normalize_token(alias) == key for alias in item.get("aliases", [])))]
        if len(matches) > 1:
            raise IntegrityError(f"ambiguous {kind} name: {name}")
        if matches:
            return matches[0]["entity_id"], None
        entity_id = new_uuid7()
        return entity_id, EntityCreation(entity_id, kind, name, [], None)

    def _plan_artifacts(self, candidates: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[ArtifactCreation]]:
        catalog = [read_json(path) for path in sorted((self.vault.root / "catalog/artifacts").glob("*.json"))]
        creations: list[ArtifactCreation] = []
        refs: list[dict[str, str]] = []
        for candidate in candidates:
            artifact_id = candidate["artifact_id"]
            if artifact_id is not None:
                if not any(item["artifact_id"] == artifact_id for item in catalog):
                    raise ValidationError(f"artifact does not exist: {artifact_id}")
            else:
                matches = [item for item in catalog if item["kind"] == candidate["kind"] and item["label"] == candidate["label"] and item["locator"] == candidate["locator"]]
                if len(matches) > 1:
                    raise IntegrityError(f"ambiguous artifact candidate: {candidate['label']}")
                if matches:
                    artifact_id = matches[0]["artifact_id"]
                else:
                    artifact_id = new_uuid7()
                    creation = ArtifactCreation(artifact_id, candidate["kind"], candidate["label"], candidate["locator"], candidate["external_id"], candidate["notes"])
                    creations.append(creation)
                    catalog.append({"artifact_id": artifact_id, "kind": candidate["kind"], "label": candidate["label"], "locator": candidate["locator"]})
            refs.append({"artifact_id": artifact_id, "relation": candidate["relation"]})
        return refs, creations

    def _resolve_entities(self, candidates: list[dict[str, Any]]) -> list[dict[str, str]]:
        catalog = [read_json(path) for path in sorted((self.vault.root / "catalog/entities").glob("*.json"))]
        refs = []
        for candidate in candidates:
            entity_id = candidate["entity_id"]
            if entity_id is not None:
                matches = [item for item in catalog if item["entity_id"] == entity_id]
                if not matches:
                    raise ValidationError(f"entity does not exist: {entity_id}")
                if candidate.get("kind") is not None and matches[0]["kind"] != candidate["kind"]:
                    raise ValidationError(f"entity {entity_id} is not a {candidate['kind']}")
            else:
                key = SkillLoader.normalize_token(candidate["canonical_name"])
                matches = [item for item in catalog if item["kind"] == candidate["kind"] and
                           (SkillLoader.normalize_token(item["canonical_name"]) == key or
                            any(SkillLoader.normalize_token(alias) == key for alias in item.get("aliases", [])))]
                if len(matches) > 1:
                    raise IntegrityError(f"ambiguous entity candidate: {candidate['canonical_name']}")
                entity_id = matches[0]["entity_id"] if matches else self.vault.upsert_entity(
                    kind=candidate["kind"], canonical_name=candidate["canonical_name"], aliases=candidate["aliases"],
                    description=candidate["description"]
                )["entity_id"]
            refs.append({"entity_id": entity_id, "relation": candidate["relation"]})
        return refs

    def _resolve_context_name(self, name: str, kind: str) -> str:
        catalog = [read_json(path) for path in sorted((self.vault.root / "catalog/entities").glob("*.json"))]
        key = SkillLoader.normalize_token(name)
        matches = [item for item in catalog if item["kind"] == kind and
                   (SkillLoader.normalize_token(item["canonical_name"]) == key or
                    any(SkillLoader.normalize_token(alias) == key for alias in item.get("aliases", [])))]
        if len(matches) > 1:
            raise IntegrityError(f"ambiguous {kind} name: {name}")
        return matches[0]["entity_id"] if matches else self.vault.upsert_entity(
            kind=kind, canonical_name=name, aliases=[]
        )["entity_id"]

    def _resolve_artifacts(self, candidates: list[dict[str, Any]]) -> list[dict[str, str]]:
        catalog = [read_json(path) for path in sorted((self.vault.root / "catalog/artifacts").glob("*.json"))]
        refs = []
        for candidate in candidates:
            artifact_id = candidate["artifact_id"]
            if artifact_id is not None:
                if not any(item["artifact_id"] == artifact_id for item in catalog):
                    raise ValidationError(f"artifact does not exist: {artifact_id}")
            else:
                matches = [item for item in catalog if item["kind"] == candidate["kind"] and item["label"] == candidate["label"] and item["locator"] == candidate["locator"]]
                if len(matches) > 1:
                    raise IntegrityError(f"ambiguous artifact candidate: {candidate['label']}")
                artifact_id = matches[0]["artifact_id"] if matches else self.vault.upsert_artifact(
                    kind=candidate["kind"], label=candidate["label"], locator=candidate["locator"],
                    external_id=candidate["external_id"], notes=candidate["notes"]
                )["artifact_id"]
            refs.append({"artifact_id": artifact_id, "relation": candidate["relation"]})
        return refs

    @staticmethod
    def _merge_tokens(*groups: list[str]) -> list[str]:
        result: list[str] = []
        for group in groups:
            for item in group:
                if item not in result:
                    result.append(item)
        return result
