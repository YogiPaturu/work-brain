from __future__ import annotations

import contextlib
import json
import sqlite3
import subprocess
import shutil
import sysconfig
import threading
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from .database import Database
from .domain import ENTITY_KINDS, SessionEntry, normalize_alias, normalize_domain_tags, validate_session
from .errors import IntegrityError, ValidationError
from .fsutil import (
    append_jsonl,
    atomic_create_bytes,
    atomic_replace_json,
    canonical_json_bytes,
    content_hash,
    ensure_private_dir,
    ensure_private_file,
    read_json,
    read_jsonl_with_recovery,
)
from .ids import new_uuid7, validate_uuid7
from .lock import VaultLock
from .projections import _apply_mutation, journal_text, rebuild_state, render_journal
from .timeutil import date_for_timestamp, parse_timestamp, timestamp_now, validate_calendar_date


_CONTEXT_UNSET = object()


class Vault:
    """Authoritative source store plus rebuildable projections."""

    def __init__(
        self,
        root: str | Path,
        migration_dir: str | Path | None = None,
        *,
        dependency_change_hook: Callable[[str, str], None] | None = None,
        entry_publish_hook: Callable[[str], None] | None = None,
    ):
        self.root = Path(root).expanduser().resolve()
        default_migrations = Path(__file__).resolve().parents[2] / "migrations"
        installed_migrations = Path(sysconfig.get_path("data")) / "share/work-brain/migrations"
        selected_migrations = default_migrations if default_migrations.is_dir() else installed_migrations
        self.migration_dir = Path(migration_dir).resolve() if migration_dir else selected_migrations
        self._thread_lock = threading.RLock()
        self._lock_depth = 0
        self._file_lock: VaultLock | None = None
        self._source_warnings: list[str] = []
        self.dependency_change_hook = dependency_change_hook
        self.entry_publish_hook = entry_publish_hook

    # ----- topology and locking -------------------------------------------------

    def initialize_source_store(self) -> "Vault":
        for relative in (
            "sessions", "amendments", "catalog/entities", "catalog/artifacts", "journal",
            "state", "context", "questions", "career", "artifacts", "index",
        ):
            ensure_private_dir(self.root / relative)
        state_path = self.root / "state/current.json"
        if not state_path.exists():
            atomic_replace_json(state_path, {"items": []})
        return self

    def initialize_projections(self) -> "Vault":
        """Initialize only rebuildable projection storage."""
        self.initialize_source_store()
        conn = self._database().connect()
        conn.close()
        return self

    def initialize(self) -> "Vault":
        """Compatibility alias for source initialization.

        Source capture must not open or migrate SQLite.  Callers that need
        projections must opt into :meth:`initialize_projections`.
        """
        return self.initialize_source_store()

    @contextlib.contextmanager
    def write_lock(self) -> Iterator[None]:
        self.initialize_source_store()
        with self._thread_lock:
            outer = self._lock_depth == 0
            if outer:
                self._file_lock = VaultLock(self.root / ".vault.write.lock")
                self._file_lock.acquire()
            self._lock_depth += 1
            try:
                yield
            finally:
                self._lock_depth -= 1
                if outer and self._file_lock is not None:
                    self._file_lock.release()
                    self._file_lock = None

    def _require_or_lock(self):
        return self.write_lock() if self._lock_depth == 0 else contextlib.nullcontext()

    def consume_source_warnings(self) -> tuple[str, ...]:
        warnings = tuple(self._source_warnings)
        self._source_warnings.clear()
        return warnings

    # ----- sessions and raw turns -----------------------------------------------

    def session_dir(self, session_id: str, local_date: str | None = None) -> Path:
        validate_uuid7(session_id, "session_id")
        if local_date is None:
            for candidate in self.root.glob(f"sessions/*/*/*/{session_id}"):
                return candidate
            raise FileNotFoundError(f"session not found: {session_id}")
        validate_calendar_date(local_date, "local_date")
        year, month, day = local_date.split("-")
        return self.root / "sessions" / year / month / day / session_id

    def create_session(
        self,
        *,
        started_at: str | None = None,
        modes: list[str] | None = None,
        domain_tags: list[str] | None = None,
        runtime: Mapping[str, Any] | None = None,
        session_id: str | None = None,
        entry_id: str | None = None,
    ) -> dict[str, Any]:
        with self._require_or_lock():
            started_at = started_at or timestamp_now()
            parse_timestamp(started_at, "started_at")
            session_id = validate_uuid7(session_id or new_uuid7(), "session_id")
            entry_id = validate_uuid7(entry_id or new_uuid7(), "entry_id")
            local_date = date_for_timestamp(started_at)
            path = self.session_dir(session_id, local_date)
            if path.exists():
                raise IntegrityError(f"session already exists: {session_id}")
            ensure_private_dir(path / "entries")
            metadata = {
                "session_id": session_id,
                "started_at": started_at,
                "ended_at": None,
                "local_date": local_date,
                "entry_id": entry_id,
                "modes": list(modes or []),
                "domain_tags": normalize_domain_tags(list(domain_tags or [])),
                "runtime": dict(runtime or {}),
            }
            validate_session(metadata)
            atomic_replace_json(path / "session.json", metadata)
            turns = path / "turns.jsonl"
            turns.touch(mode=0o600, exist_ok=False)
            ensure_private_file(turns)
            return metadata

    def read_session(self, session_id: str) -> dict[str, Any]:
        value = validate_session(read_json(self.session_dir(session_id) / "session.json"))
        if value["session_id"] != session_id:
            raise IntegrityError(f"session ID mismatch in metadata: {session_id}")
        return value

    def update_session_metadata(self, session_id: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
        """Atomically update the mutable session snapshot after source work succeeds."""
        with self._require_or_lock():
            current = self.read_session(session_id)
            candidate = dict(metadata)
            if candidate.get("session_id") != current["session_id"] or candidate.get("entry_id") != current["entry_id"]:
                raise IntegrityError("session identity cannot change")
            candidate.setdefault("started_at", current["started_at"])
            candidate.setdefault("local_date", current["local_date"])
            candidate.setdefault("ended_at", current.get("ended_at"))
            candidate.setdefault("modes", current.get("modes", []))
            candidate.setdefault("domain_tags", current.get("domain_tags", []))
            candidate.setdefault("runtime", current.get("runtime", {}))
            validate_session(candidate)
            atomic_replace_json(self.session_dir(session_id) / "session.json", candidate)
            return candidate

    def _read_turns(self, session_id: str, *, repair: bool = False) -> list[dict[str, Any]]:
        path = self.session_dir(session_id) / "turns.jsonl"
        records, _ = read_jsonl_with_recovery(path)
        expected = 1
        seen_ids: set[str] = set()
        for record in records:
            validate_uuid7(record.get("turn_id"), "turn_id")
            if record.get("sequence") != expected:
                raise IntegrityError(f"turn sequence gap/non-contiguous sequence in {path}")
            if record.get("role") not in {"user", "assistant"}:
                raise ValidationError("turn.role must be user or assistant")
            if not isinstance(record.get("content"), str):
                raise ValidationError("turn.content must be a string")
            parse_timestamp(record.get("recorded_at"), "turn.recorded_at")
            if record["turn_id"] in seen_ids:
                raise IntegrityError(f"duplicate turn ID in {path}")
            seen_ids.add(record["turn_id"])
            expected += 1
        return records

    def list_turns(self, session_id: str) -> list[dict[str, Any]]:
        return self._read_turns(session_id)

    def append_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        turn_id: str | None = None,
        recorded_at: str | None = None,
        sequence: int | None = None,
    ) -> dict[str, Any]:
        with self._require_or_lock():
            turns = self._read_turns(session_id)
            expected = len(turns) + 1
            candidate = {
                "turn_id": validate_uuid7(turn_id or new_uuid7(), "turn_id"),
                "sequence": sequence or expected,
                "recorded_at": recorded_at or timestamp_now(),
                "role": role,
                "content": content,
            }
            if turns and candidate == turns[-1]:
                return candidate
            if any(turn["turn_id"] == candidate["turn_id"] for turn in turns):
                raise IntegrityError("turn identity was reused for a divergent or non-tail record")
            if candidate["sequence"] != expected:
                raise IntegrityError(f"turn sequence must be exactly {expected}")
            if role not in {"user", "assistant"} or not isinstance(content, str):
                raise ValidationError("role must be user/assistant and content must be a string")
            parse_timestamp(candidate["recorded_at"], "turn.recorded_at")
            append_jsonl(self.session_dir(session_id) / "turns.jsonl", candidate)
            return candidate

    def close_session(self, session_id: str, *, commit_status: str = "no_new_evidence") -> dict[str, Any]:
        """Close a capture boundary when no structured entry will be published."""
        if commit_status not in {"no_new_evidence", "abandoned"}:
            raise ValidationError("unsupported close-session commit status")
        with self._require_or_lock():
            session = self.read_session(session_id)
            if session.get("ended_at") is None:
                session["ended_at"] = timestamp_now()
            runtime = dict(session.get("runtime") or {})
            runtime.update({"capture_status": "closed", "capture_boundary": "closed", "commit_status": commit_status})
            session["runtime"] = runtime
            return self.update_session_metadata(session_id, session)

    # ----- source scans ----------------------------------------------------------

    def _session_paths(self) -> list[Path]:
        return sorted(self.root.glob("sessions/*/*/*/*/session.json"))

    def _domain_tag_migration_paths(self) -> list[Path]:
        return sorted({
            *self.root.glob("sessions/*/*/*/*/session.json"),
            *self.root.glob("sessions/*/*/*/*/entries/*.json"),
            *self.root.glob("quarantine/entries/**/*.json"),
        })

    def migrate_domain_tags(self, *, dry_run: bool = False) -> dict[str, Any]:
        """Rename legacy structured-vault ``domains`` keys in place.

        This is a schema-only migration: evidence values, entry IDs, revisions,
        and commit IDs are unchanged. Derived projections are rebuilt after the
        source JSON migration completes.
        """
        with self._require_or_lock() if not dry_run else contextlib.nullcontext():
            plan: list[tuple[Path, dict[str, Any]]] = []
            for path in self._domain_tag_migration_paths():
                raw = read_json(path)
                if not isinstance(raw, dict) or "domains" not in raw:
                    continue
                if "domain_tags" in raw:
                    raise IntegrityError(f"record contains both domain_tags and legacy domains: {path}")
                migrated = dict(raw)
                migrated["domain_tags"] = normalize_domain_tags(raw["domains"])
                del migrated["domains"]
                plan.append((path, migrated))
            if dry_run:
                return {
                    "dry_run": True,
                    "count": len(plan),
                    "files": [str(path.relative_to(self.root)) for path, _ in plan],
                }
            for path, migrated in plan:
                atomic_replace_json(path, migrated)
            self.rebuild_all()
            return {
                "dry_run": False,
                "count": len(plan),
                "files": [str(path.relative_to(self.root)) for path, _ in plan],
                "status": "migrated",
            }

    def all_sessions(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        sessions = []
        for path in self._session_paths():
            value = validate_session(read_json(path))
            if path.parent.name != value["session_id"]:
                raise IntegrityError(f"session path/ID mismatch: {path}")
            if not include_archived and (value.get("runtime") or {}).get("archive_status") == "session":
                continue
            sessions.append(value)
        return sessions

    def _entry_paths(self, session: Mapping[str, Any]) -> list[Path]:
        return sorted((self.session_dir(session["session_id"]) / "entries").glob("*.json"))

    def all_current_entries(self) -> list[SessionEntry]:
        result = []
        for session in self.all_sessions():
            paths = self._entry_paths(session)
            if not paths:
                continue
            expected = 1
            loaded: list[SessionEntry] = []
            for path in paths:
                try:
                    revision = int(path.stem)
                except ValueError as exc:
                    raise IntegrityError(f"invalid entry revision filename: {path}") from exc
                if revision != expected:
                    raise IntegrityError(f"non-contiguous entry revisions for {session['session_id']}")
                entry = SessionEntry.from_dict(read_json(path))
                if entry.session_id != session["session_id"] or entry.entry_id != session["entry_id"] or entry.revision != revision:
                    raise IntegrityError(f"entry/session identity mismatch: {path}")
                loaded.append(entry)
                expected += 1
            result.append(loaded[-1])
        return result

    def all_entry_revisions(self) -> list[tuple[SessionEntry, Path]]:
        result = []
        for session in self.all_sessions():
            for path in self._entry_paths(session):
                result.append((SessionEntry.from_dict(read_json(path)), path))
        return result

    def get_current_entry(self, entry_id: str) -> SessionEntry:
        validate_uuid7(entry_id, "entry_id")
        for entry in self.all_current_entries():
            if entry.entry_id == entry_id:
                return entry
        raise FileNotFoundError(f"entry not found: {entry_id}")

    # ----- structured entries and amendments ------------------------------------

    def _find_commit(self, commit_id: str) -> tuple[SessionEntry, Path] | None:
        for entry, path in self.all_entry_revisions():
            if entry.commit_id == commit_id:
                return entry, path
        return None

    def _validate_entry_turn_refs(self, entry: SessionEntry, turn_count: int) -> None:
        for statements in entry.sections.values():
            for statement in statements:
                if any(turn > turn_count for turn in statement.source_turns):
                    raise ValidationError(f"statement references missing source turn in entry {entry.entry_id}")
        for mutation in entry.state_mutations:
            if any(turn > turn_count for turn in mutation.source_turns):
                raise ValidationError(f"state mutation references missing source turn in entry {entry.entry_id}")

    def _catalog_exists(self, kind: str, object_id: str) -> bool:
        if kind == "entity":
            return (self.root / "catalog/entities" / f"{object_id}.json").exists()
        if kind == "artifact":
            return (self.root / "catalog/artifacts" / f"{object_id}.json").exists()
        return False

    def _best_effort_source_projections(self, *, affected_date: str | None = None) -> bool:
        """Refresh rebuildable JSON/SQLite projections without changing source status."""
        try:
            self.rebuild_projections(affected_date=affected_date)
            self.reconcile_database()
            return True
        except Exception:
            return False

    def commit_entry(
        self,
        session_id: str,
        payload: Mapping[str, Any],
        *,
        commit_fingerprint: str | None = None,
        refresh_projections: bool = True,
    ) -> SessionEntry:
        """Publish one immutable source revision.

        Source publication is the success boundary. Rebuildable projections
        are refreshed afterward and can be repaired without turning a durable
        commit into an exception.
        """
        with self._require_or_lock():
            session = self.read_session(session_id)
            turns = self._read_turns(session_id)
            current_paths = self._entry_paths(session)
            current_revision = len(current_paths)
            if commit_fingerprint and (session.get("runtime") or {}).get("last_commit_fingerprint") == commit_fingerprint:
                if current_paths:
                    return SessionEntry.from_dict(read_json(current_paths[-1]))
            if commit_fingerprint:
                for existing_path in current_paths:
                    existing_entry = SessionEntry.from_dict(read_json(existing_path))
                    if existing_entry.source_fingerprint == commit_fingerprint:
                        return existing_entry
            raw = dict(payload)
            raw.setdefault("entry_id", session["entry_id"])
            raw.setdefault("session_id", session_id)
            raw.setdefault("revision", current_revision + 1)
            raw.setdefault("commit_id", new_uuid7())
            raw.setdefault("created_at", timestamp_now())
            raw.setdefault("supersedes_revision", current_revision or None)
            raw.setdefault("revision_reason", "initial_commit" if current_revision == 0 else "reextract")
            if commit_fingerprint:
                raw.setdefault("source_fingerprint", commit_fingerprint)
            raw.setdefault("workspace_entity_id", None)
            raw.setdefault("project_entity_id", None)
            if current_revision == 0:
                raw["supersedes_revision"] = None
                raw["revision_reason"] = "initial_commit" if raw["revision_reason"] == "reextract" else raw["revision_reason"]
            commit_id = validate_uuid7(raw["commit_id"], "commit_id")
            existing = self._find_commit(commit_id)
            if existing is not None:
                existing_entry, existing_path = existing
                candidate_hash = content_hash(raw)
                if candidate_hash == content_hash(read_json(existing_path)):
                    return existing_entry
                raise IntegrityError(f"commit_id already exists with different content: {commit_id}")
            entry = SessionEntry.from_dict(raw)
            if entry.session_id != session_id or entry.entry_id != session["entry_id"]:
                raise IntegrityError("entry must use the session's stable entry identity")
            if entry.revision != current_revision + 1:
                raise IntegrityError("entry revision must be the next contiguous revision")
            self._validate_entry_turn_refs(entry, len(turns))
            for ref in entry.entity_refs:
                if not self._catalog_exists("entity", ref["entity_id"]):
                    raise IntegrityError(f"missing entity reference: {ref['entity_id']}")
            if entry.workspace_entity_id is not None:
                workspace_path = self.root / "catalog/entities" / f"{entry.workspace_entity_id}.json"
                if not workspace_path.exists():
                    raise IntegrityError(f"missing workspace reference: {entry.workspace_entity_id}")
                if read_json(workspace_path).get("kind") != "workspace":
                    raise IntegrityError(f"workspace reference is not a workspace entity: {entry.workspace_entity_id}")
            if entry.project_entity_id is not None:
                project_path = self.root / "catalog/entities" / f"{entry.project_entity_id}.json"
                if not project_path.exists():
                    raise IntegrityError(f"missing project reference: {entry.project_entity_id}")
                if read_json(project_path).get("kind") != "project":
                    raise IntegrityError(f"project reference is not a project entity: {entry.project_entity_id}")
            for ref in entry.artifact_refs:
                if not self._catalog_exists("artifact", ref["artifact_id"]):
                    raise IntegrityError(f"missing artifact reference: {ref['artifact_id']}")
            for mutation in entry.state_mutations:
                project_id = mutation.fields.get("project_entity_id")
                if project_id is not None and not self._catalog_exists("entity", project_id):
                    raise IntegrityError(f"missing state project entity: {project_id}")
            target = self.session_dir(session_id) / "entries" / f"{entry.revision:04d}.json"
            atomic_create_bytes(target, canonical_json_bytes(entry.to_dict()))
            session["ended_at"] = timestamp_now()
            runtime = dict(session.get("runtime") or {})
            if commit_fingerprint:
                runtime["last_commit_fingerprint"] = commit_fingerprint
                runtime["commit_status"] = "committed"
            session["runtime"] = runtime
            try:
                atomic_replace_json(self.session_dir(session_id) / "session.json", session)
            except Exception as exc:
                self._source_warnings.append(
                    f"session lifecycle metadata was not refreshed after source publication: {type(exc).__name__}"
                )
        if refresh_projections:
            self._best_effort_source_projections(affected_date=session["local_date"])
        if self.entry_publish_hook is not None:
            try:
                self.entry_publish_hook(entry.entry_id)
            except Exception:
                # Hooks are notifications, never part of the source commit.
                pass
        return entry

    def backfill_entry_context(
        self,
        entry_id: str,
        *,
        workspace: str | Mapping[str, Any] | None | object = _CONTEXT_UNSET,
        project: str | Mapping[str, Any] | None | object = _CONTEXT_UNSET,
    ) -> SessionEntry:
        """Add or correct workspace/project metadata without rewriting a revision.

        Context classification is a structured interpretation, so backfill
        publishes a new immutable revision and retains the prior revision as
        history. Omitted fields are preserved; explicit null clears a field.
        Names create or reuse catalog entities deterministically.
        """
        with self._require_or_lock():
            current = self.get_current_entry(entry_id)
            workspace_id = current.workspace_entity_id
            project_id = current.project_entity_id
            if workspace is not _CONTEXT_UNSET:
                workspace_id = self._resolve_context_entity("workspace", workspace)
            if project is not _CONTEXT_UNSET:
                project_id = self._resolve_context_entity("project", project)
            if workspace_id == current.workspace_entity_id and project_id == current.project_entity_id:
                return current
            raw = current.to_dict()
            raw.update({
                "workspace_entity_id": workspace_id,
                "project_entity_id": project_id,
            })
            return self._publish_metadata_backfill(current, raw)

    def backfill_entry_domain_tags(self, entry_id: str, *, domain_tags: list[str]) -> SessionEntry:
        """Add domain tags as an immutable metadata-only revision."""
        with self._require_or_lock():
            current = self.get_current_entry(entry_id)
            additions = normalize_domain_tags(domain_tags)
            merged = normalize_domain_tags([*current.domain_tags, *additions])
            if merged == current.domain_tags:
                return current
            raw = current.to_dict()
            raw["domain_tags"] = merged
            return self._publish_metadata_backfill(current, raw)

    def _publish_metadata_backfill(
        self,
        current: SessionEntry,
        raw: dict[str, Any],
        *,
        reason: str = "metadata_backfill",
        refresh_projections: bool = True,
    ) -> SessionEntry:
        raw.update({
            "revision": current.revision + 1,
            "commit_id": new_uuid7(),
            "created_at": timestamp_now(),
            "supersedes_revision": current.revision,
            "revision_reason": reason,
        })
        refs = list(raw.get("source_refs", []))
        previous_ref = {"kind": "entry", "id": current.entry_id, "revision": current.revision}
        if previous_ref not in refs:
            refs.append(previous_ref)
        raw["source_refs"] = refs
        return self.commit_entry(current.session_id, raw, refresh_projections=refresh_projections)

    def associate_entry_experience(
        self,
        entry_id: str,
        *,
        experience_id: str | None = None,
        experience_name: str | None = None,
        remove: bool = False,
        move: bool = False,
    ) -> SessionEntry:
        """Publish an immutable metadata revision for an Experience link."""
        with self._require_or_lock():
            current = self.get_current_entry(entry_id)
            existing_ids = [ref["entity_id"] for ref in current.entity_refs if ref["relation"] == "experience"]
            if remove:
                if experience_id is not None or experience_name is not None:
                    raise ValidationError("remove cannot specify an Experience target")
                target_id = None
            else:
                if experience_id and experience_name:
                    raise ValidationError("specify experience_id or experience_name, not both")
                if experience_id is None and not experience_name:
                    raise ValidationError("an Experience target is required unless remove=true")
                target_id = self._resolve_experience_entity(experience_id, experience_name)
                if target_id in existing_ids and len(existing_ids) == 1:
                    return current
                if existing_ids and not move:
                    raise ValidationError("entry already belongs to an Experience; use move=true to replace it")
                self._validate_experience_context(target_id, current)
            refs = [ref for ref in current.entity_refs if ref["relation"] != "experience"]
            if target_id is not None:
                refs.append({"entity_id": target_id, "relation": "experience"})
            if refs == current.entity_refs:
                return current
            raw = current.to_dict()
            raw["entity_refs"] = refs
            # The application service owns post-publication maintenance.  Do
            # not hold the source writer lock while rebuilding/indexing this
            # metadata-only association.
            return self._publish_metadata_backfill(current, raw, refresh_projections=False)

    def _resolve_experience_entity(self, entity_id: str | None, name: str | None) -> str:
        if entity_id is not None:
            entity_id = validate_uuid7(entity_id, "experience_id")
            path = self.root / "catalog/entities" / f"{entity_id}.json"
            if not path.exists():
                raise FileNotFoundError(f"experience not found: {entity_id}")
            if read_json(path).get("kind") != "experience":
                raise ValidationError("entity is not an experience")
            return entity_id
        if not isinstance(name, str) or not name.strip():
            raise ValidationError("experience_name must be a non-empty string")
        return self._resolve_context_entity("experience", name.strip())

    def _validate_experience_context(self, experience_id: str, incoming: SessionEntry) -> None:
        self.validate_experience_context(
            [experience_id], incoming.workspace_entity_id, incoming.project_entity_id,
            excluding_entry_id=incoming.entry_id,
        )

    def validate_experience_context(
        self,
        experience_ids: list[str],
        workspace_entity_id: str | None,
        project_entity_id: str | None,
        *,
        excluding_entry_id: str | None = None,
    ) -> None:
        """Reject mixed workspace/project contexts for an Experience link."""
        incoming_context = (workspace_entity_id, project_entity_id)
        for experience_id in experience_ids:
            linked = [
                entry for entry in self.all_current_entries()
                if entry.entry_id != excluding_entry_id and any(
                    ref["relation"] == "experience" and ref["entity_id"] == experience_id for ref in entry.entity_refs
                )
            ]
            contexts = {(entry.workspace_entity_id, entry.project_entity_id) for entry in linked}
            if len(contexts) > 1:
                raise IntegrityError(f"experience has conflicting workspace/project context: {experience_id}")
            if contexts and next(iter(contexts)) != incoming_context:
                established = next(iter(contexts))
                raise ValidationError(
                    "entry workspace/project does not match the Experience context "
                    f"({established[0]}, {established[1]})"
                )

    def _resolve_context_entity(self, kind: str, value: str | Mapping[str, Any] | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, Mapping):
            entity_id = value.get("entity_id")
            canonical_name = value.get("canonical_name")
            aliases = value.get("aliases", [])
            description = value.get("description")
        elif isinstance(value, str):
            entity_id = value if (self.root / "catalog/entities" / f"{value}.json").exists() else None
            canonical_name = None if entity_id else value
            aliases = []
            description = None
        else:
            raise ValidationError(f"{kind} must be a name, entity object, or null")
        if entity_id is not None:
            entity_id = validate_uuid7(entity_id, f"{kind}.entity_id")
            path = self.root / "catalog/entities" / f"{entity_id}.json"
            if not path.exists():
                raise ValidationError(f"{kind} entity does not exist: {entity_id}")
            entity = read_json(path)
            if entity.get("kind") != kind:
                raise ValidationError(f"entity {entity_id} is not a {kind}")
            return entity_id
        if not isinstance(canonical_name, str) or not canonical_name.strip():
            raise ValidationError(f"{kind} requires a non-empty canonical_name")
        if not isinstance(aliases, list) or any(not isinstance(item, str) or not item.strip() for item in aliases):
            raise ValidationError(f"{kind}.aliases must be a list of non-empty strings")
        key = normalize_alias(canonical_name)
        matches = []
        for path in sorted((self.root / "catalog/entities").glob("*.json")):
            entity = read_json(path)
            if entity.get("kind") != kind:
                continue
            names = [entity.get("canonical_name", ""), *entity.get("aliases", [])]
            if any(normalize_alias(name) == key for name in names):
                matches.append(entity)
        if len(matches) > 1:
            raise IntegrityError(f"ambiguous {kind} entity: {canonical_name}")
        if matches:
            return matches[0]["entity_id"]
        return self.upsert_entity(
            kind=kind,
            canonical_name=canonical_name.strip(),
            aliases=list(aliases),
            description=description,
        )["entity_id"]

    def create_amendment(
        self,
        *,
        target_kind: str,
        target_id: str,
        statement: str,
        source_session_id: str | None = None,
        amendment_id: str | None = None,
        recorded_at: str | None = None,
    ) -> dict[str, Any]:
        with self._require_or_lock():
            if target_kind not in {"entry", "entity", "artifact"}:
                raise ValidationError("amendment target_kind must be entry, entity, or artifact")
            validate_uuid7(target_id, "amendment.target.id")
            if not isinstance(statement, str) or not statement:
                raise ValidationError("amendment.statement must be non-empty")
            if source_session_id is not None:
                validate_uuid7(source_session_id, "source_session_id")
            value = {
                "amendment_id": validate_uuid7(amendment_id or new_uuid7(), "amendment_id"),
                "recorded_at": recorded_at or timestamp_now(),
                "target": {"kind": target_kind, "id": target_id},
                "statement": statement,
                "source_session_id": source_session_id,
            }
            parse_timestamp(value["recorded_at"], "amendment.recorded_at")
            local_date = date_for_timestamp(value["recorded_at"])
            y, m, d = local_date.split("-")
            target = self.root / "amendments" / y / m / d / f"{value['amendment_id']}.json"
            if target.exists():
                existing = read_json(target)
                if existing == value:
                    return existing
                raise IntegrityError("amendment ID already exists with different content")
            atomic_create_bytes(target, canonical_json_bytes(value))
            return value

    def delete_session(self, session_id: str, *, complete_removal: bool = False) -> None:
        """Explicitly delete one session and rebuild all affected projections."""
        if not complete_removal:
            raise ValidationError("session deletion requires complete_removal=True")
        with self._require_or_lock():
            session = self.read_session(session_id)
            entry_ids = {entry.entry_id for entry in self.all_current_entries() if entry.session_id == session_id}
            for amendment_path in (self.root / "amendments").glob("*/*/*/*.json"):
                amendment = read_json(amendment_path)
                if amendment.get("source_session_id") == session_id or amendment.get("target", {}).get("id") in entry_ids:
                    amendment_path.unlink()
            shutil.rmtree(self.session_dir(session_id))
        self._best_effort_source_projections()

    def quarantine_entry(self, session_id: str, *, reason: str) -> None:
        """Hide a bad structured entry while preserving the session's raw turns."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValidationError("quarantine reason must be a non-empty string")
        with self._require_or_lock():
            session = self.read_session(session_id)
            if session.get("ended_at") is None:
                raise ValidationError("cannot quarantine an active session; close it first")
            entries_dir = self.session_dir(session_id) / "entries"
            entry_paths = sorted(entries_dir.glob("*.json"))
            if not entry_paths:
                raise FileNotFoundError(f"structured entry not found for session: {session_id}")
            target = self.root / "quarantine" / "entries" / session["local_date"] / session_id
            if target.exists():
                raise IntegrityError(f"session entry is already quarantined: {session_id}")
            target.parent.mkdir(parents=True, exist_ok=True)
            entries_dir.rename(target)
            runtime = dict(session.get("runtime") or {})
            runtime.update({"quarantine_status": "structured_entry", "quarantine_reason": reason.strip(), "quarantined_at": timestamp_now()})
            session["runtime"] = runtime
            atomic_replace_json(self.session_dir(session_id) / "session.json", session)
        self._best_effort_source_projections(affected_date=session["local_date"])

    def archive_session(self, session_id: str, *, reason: str) -> None:
        """Hide a closed session from active views while preserving all source data."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValidationError("archive reason must be a non-empty string")
        with self._require_or_lock():
            session = self.read_session(session_id)
            if session.get("ended_at") is None:
                raise ValidationError("cannot archive an active session; close it first")
            runtime = dict(session.get("runtime") or {})
            if runtime.get("archive_status") == "session":
                raise IntegrityError(f"session is already archived: {session_id}")
            runtime.update({
                "archive_status": "session",
                "archive_reason": reason.strip(),
                "archived_at": timestamp_now(),
            })
            session["runtime"] = runtime
            atomic_replace_json(self.session_dir(session_id) / "session.json", session)
        self._best_effort_source_projections()

    def apply_amendment(self, amendment_id: str, payload: Mapping[str, Any] | None = None) -> SessionEntry:
        """Publish a new user-correction revision linked to an amendment."""
        with self._require_or_lock():
            validate_uuid7(amendment_id, "amendment_id")
            paths = list((self.root / "amendments").glob("*/*/*/*.json"))
            amendment_path = next((path for path in paths if path.stem == amendment_id), None)
            if amendment_path is None:
                raise FileNotFoundError(f"amendment not found: {amendment_id}")
            amendment = read_json(amendment_path)
            if amendment["target"]["kind"] != "entry":
                raise ValidationError("only entry amendments can create SessionEntry revisions")
            current = self.get_current_entry(amendment["target"]["id"])
            raw = dict(payload or current.to_dict())
            raw.update({
                "entry_id": current.entry_id,
                "session_id": current.session_id,
                "revision": current.revision + 1,
                "commit_id": new_uuid7(),
                "created_at": timestamp_now(),
                "supersedes_revision": current.revision,
                "revision_reason": "user_correction",
            })
            refs = list(raw.get("source_refs", []))
            if not any(ref.get("kind") == "amendment" and ref.get("id") == amendment_id for ref in refs):
                refs.append({"kind": "amendment", "id": amendment_id})
            raw["source_refs"] = refs
            return self.commit_entry(current.session_id, raw)

    # ----- catalogs --------------------------------------------------------------

    def upsert_entity(
        self,
        *,
        kind: str,
        canonical_name: str,
        aliases: list[str] | None = None,
        description: str | None = None,
        entity_id: str | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> dict[str, Any]:
        with self._require_or_lock():
            if kind not in ENTITY_KINDS:
                raise ValidationError("invalid entity kind")
            if not isinstance(canonical_name, str) or not canonical_name:
                raise ValidationError("canonical_name must be non-empty")
            entity_id = validate_uuid7(entity_id or new_uuid7(), "entity_id")
            path = self.root / "catalog/entities" / f"{entity_id}.json"
            previous = read_json(path) if path.exists() else None
            now = updated_at or timestamp_now()
            if created_at is None and previous:
                created_at = previous["created_at"]
            created_at = created_at or now
            parse_timestamp(created_at, "entity.created_at")
            parse_timestamp(now, "entity.updated_at")
            merged_aliases = list(aliases or [])
            if previous and previous.get("canonical_name") != canonical_name:
                merged_aliases.append(previous["canonical_name"])
            deduped: list[str] = []
            seen: set[str] = set()
            for alias in merged_aliases:
                if not isinstance(alias, str) or not alias:
                    raise ValidationError("entity aliases must be non-empty strings")
                key = normalize_alias(alias)
                if key not in seen and key != normalize_alias(canonical_name):
                    seen.add(key)
                    deduped.append(alias)
            value = {"entity_id": entity_id, "kind": kind, "canonical_name": canonical_name, "aliases": deduped,
                     "description": description, "created_at": created_at, "updated_at": now}
            atomic_replace_json(path, value)
            if self.dependency_change_hook is not None:
                self.dependency_change_hook("entity", entity_id)
            return value

    def upsert_artifact(
        self,
        *,
        kind: str,
        label: str,
        locator: str,
        external_id: str | None = None,
        notes: str | None = None,
        artifact_id: str | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> dict[str, Any]:
        with self._require_or_lock():
            artifact_id = validate_uuid7(artifact_id or new_uuid7(), "artifact_id")
            if not all(isinstance(value, str) and value for value in (kind, label, locator)):
                raise ValidationError("artifact kind, label, and locator must be non-empty strings")
            path = self.root / "catalog/artifacts" / f"{artifact_id}.json"
            previous = read_json(path) if path.exists() else None
            now = updated_at or timestamp_now()
            created_at = created_at or (previous["created_at"] if previous else now)
            parse_timestamp(created_at, "artifact.created_at")
            parse_timestamp(now, "artifact.updated_at")
            value = {"artifact_id": artifact_id, "kind": kind.lower(), "label": label, "locator": locator,
                     "external_id": external_id, "notes": notes, "created_at": created_at, "updated_at": now}
            atomic_replace_json(path, value)
            if self.dependency_change_hook is not None:
                self.dependency_change_hook("artifact", artifact_id)
            return value

    # ----- projections -----------------------------------------------------------

    def _entries_and_sessions(self) -> tuple[list[dict[str, Any]], dict[str, SessionEntry]]:
        sessions = self.all_sessions()
        entries = {entry.entry_id: entry for entry in self.all_current_entries()}
        return sessions, entries

    def rebuild_projections(self, *, affected_date: str | None = None) -> None:
        sessions, entries = self._entries_and_sessions()
        state_path = self.root / "state/current.json"
        rebuild_state(entries.values(), state_path)
        dates = {session["local_date"] for session in sessions} if affected_date is None else {affected_date}
        for local_date in dates:
            year, month, _ = local_date.split("-")
            render_journal(local_date, sessions, entries, self.root / "journal" / year / month / f"{local_date}.md")

    def rebuild_all(self) -> None:
        with self._require_or_lock():
            self.initialize_projections()
            self.rebuild_projections()
            self.reconcile_database()

    # ----- SQLite persistence ----------------------------------------------------

    @property
    def database_path(self) -> Path:
        return self.root / "index/work-brain.sqlite"

    @property
    def capture_hook_health_path(self) -> Path:
        return self.root / "context/capture-hook-health.jsonl"

    def capture_hook_health(self, *, limit: int = 5) -> list[dict[str, Any]]:
        if not self.capture_hook_health_path.exists():
            return []
        records, _ = read_jsonl_with_recovery(self.capture_hook_health_path)
        return records[-limit:]

    def _database(self) -> Database:
        return Database(self.database_path, self.migration_dir)

    def reconcile_database(self) -> None:
        self.initialize_projections()
        sessions, current_entries = self._entries_and_sessions()
        revisions = self.all_entry_revisions()
        entities = [read_json(path) for path in sorted((self.root / "catalog/entities").glob("*.json"))]
        artifacts = [read_json(path) for path in sorted((self.root / "catalog/artifacts").glob("*.json"))]
        amendments = [read_json(path) for path in sorted((self.root / "amendments").glob("*/*/*/*.json"))]
        for entity in entities:
            validate_uuid7(entity.get("entity_id"), "entity_id")
        entity_ids = {entity["entity_id"] for entity in entities}
        artifact_ids = {artifact["artifact_id"] for artifact in artifacts}
        for entry in current_entries.values():
            for ref in entry.entity_refs:
                if ref["entity_id"] not in entity_ids:
                    raise IntegrityError(f"missing entity reference during rebuild: {ref['entity_id']}")
            for ref in entry.artifact_refs:
                if ref["artifact_id"] not in artifact_ids:
                    raise IntegrityError(f"missing artifact reference during rebuild: {ref['artifact_id']}")
            if entry.workspace_entity_id is not None:
                workspace = next((item for item in entities if item["entity_id"] == entry.workspace_entity_id), None)
                if workspace is None:
                    raise IntegrityError(f"missing workspace reference during rebuild: {entry.workspace_entity_id}")
                if workspace["kind"] != "workspace":
                    raise IntegrityError(f"workspace reference is not a workspace entity during rebuild: {entry.workspace_entity_id}")
            if entry.project_entity_id is not None:
                project = next((item for item in entities if item["entity_id"] == entry.project_entity_id), None)
                if project is None:
                    raise IntegrityError(f"missing project reference during rebuild: {entry.project_entity_id}")
                if project["kind"] != "project":
                    raise IntegrityError(f"project reference is not a project entity during rebuild: {entry.project_entity_id}")
        # Generate the state source before opening the transaction so a bad
        # mutation cannot partially replace the derived database.
        state = rebuild_state(current_entries.values(), self.root / "state/current.json")
        db = self._database()
        conn = db.connect()
        try:
            with conn:
                db.reset_derived_tables(conn)
                for session in sessions:
                    conn.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
                        session["session_id"], session["started_at"], session.get("ended_at"), session["local_date"],
                        session["entry_id"], str(self.session_dir(session["session_id"])),
                        session.get("runtime", {}).get("model"), session.get("runtime", {}).get("app_revision")))
                for entry in current_entries.values():
                    path = self._entry_paths(self.read_session(entry.session_id))[-1]
                    raw = read_json(path)
                    conn.execute("INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                        entry.entry_id, entry.session_id, entry.revision, entry.title, entry.provenance_kind,
                        entry.occurrence.start, entry.occurrence.end, entry.occurrence.precision, str(path),
                        content_hash(raw), entry.created_at, entry.project_entity_id, entry.workspace_entity_id))
                for entry, path in revisions:
                    conn.execute("INSERT INTO entry_revisions VALUES (?, ?, ?, ?, ?, ?, ?)", (
                        entry.entry_id, entry.revision, entry.commit_id, entry.revision_reason, entry.created_at,
                        str(path), content_hash(read_json(path))))
                for entity in entities:
                    path = self.root / "catalog/entities" / f"{entity['entity_id']}.json"
                    conn.execute("INSERT INTO entities VALUES (?, ?, ?, ?, ?)", (entity["entity_id"], entity["kind"], entity["canonical_name"], str(path), entity["updated_at"]))
                    for alias in entity.get("aliases", []):
                        conn.execute("INSERT INTO entity_aliases VALUES (?, ?, ?)", (entity["entity_id"], alias, normalize_alias(alias)))
                    conn.execute("INSERT OR IGNORE INTO entity_aliases VALUES (?, ?, ?)", (entity["entity_id"], entity["canonical_name"], normalize_alias(entity["canonical_name"])))
                for artifact in artifacts:
                    path = self.root / "catalog/artifacts" / f"{artifact['artifact_id']}.json"
                    conn.execute("INSERT INTO artifacts VALUES (?, ?, ?, ?, ?, ?, ?)", (artifact["artifact_id"], artifact["kind"], artifact["label"], artifact["locator"], artifact.get("external_id"), str(path), artifact["updated_at"]))
                for entry in current_entries.values():
                    for ref in entry.entity_refs:
                        conn.execute("INSERT INTO entry_entities VALUES (?, ?, ?)", (entry.entry_id, ref["entity_id"], ref["relation"]))
                    for ref in entry.artifact_refs:
                        conn.execute("INSERT INTO entry_artifacts VALUES (?, ?, ?)", (entry.entry_id, ref["artifact_id"], ref["relation"]))
                for amendment in amendments:
                    conn.execute("INSERT INTO amendments VALUES (?, ?, ?, ?, ?, ?)", (
                        amendment["amendment_id"], amendment["recorded_at"], amendment["target"]["kind"], amendment["target"]["id"], amendment.get("source_session_id"),
                        str(self.root / "amendments" / amendment["recorded_at"][:4] / amendment["recorded_at"][5:7] / amendment["recorded_at"][8:10] / f"{amendment['amendment_id']}.json")))
                for item in state["items"]:
                    conn.execute("INSERT INTO state_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                        item["state_item_id"], item["kind"], item["title"], item["status"], item.get("project_entity_id"), item.get("details"),
                        item.get("next_action"), item.get("waiting_on"), item.get("due_at"), item["opened_at"], item["updated_at"], item.get("closed_at"), item["last_source_entry_id"]))
        finally:
            conn.close()

    # ----- integrity diagnostics -------------------------------------------------

    def doctor(self) -> list[str]:
        diagnostics: list[str] = []
        sessions: list[dict[str, Any]] = []
        try:
            sessions = self.all_sessions(include_archived=True)
        except Exception as exc:
            diagnostics.append(f"session metadata error: {exc}")
        for session in sessions:
            try:
                self._read_turns(session["session_id"])
            except Exception as exc:
                diagnostics.append(f"turn integrity {session['session_id']}: {exc}")
            try:
                paths = self._entry_paths(session)
                expected = 1
                commits: set[str] = set()
                for path in paths:
                    if path.stem != f"{expected:04d}":
                        diagnostics.append(f"non-contiguous revision: {path}")
                    entry = SessionEntry.from_dict(read_json(path))
                    if entry.commit_id in commits:
                        diagnostics.append(f"duplicate commit ID: {entry.commit_id}")
                    commits.add(entry.commit_id)
                    expected += 1
            except Exception as exc:
                diagnostics.append(f"entry integrity {session['session_id']}: {exc}")
        try:
            current = {entry.entry_id: entry for entry in self.all_current_entries()}
            entity_ids = {p.stem for p in (self.root / "catalog/entities").glob("*.json")}
            artifact_ids = {p.stem for p in (self.root / "catalog/artifacts").glob("*.json")}
            for entry in current.values():
                for ref in entry.entity_refs:
                    if ref["entity_id"] not in entity_ids:
                        diagnostics.append(f"broken entity reference: {entry.entry_id} -> {ref['entity_id']}")
                for ref in entry.artifact_refs:
                    if ref["artifact_id"] not in artifact_ids:
                        diagnostics.append(f"broken artifact reference: {entry.entry_id} -> {ref['artifact_id']}")
            expected_state = {item["state_item_id"]: item for item in rebuild_state_in_memory(current.values())}
            state_path = self.root / "state/current.json"
            if not state_path.exists() or read_json(state_path).get("items") != sorted(expected_state.values(), key=lambda item: item["state_item_id"]):
                diagnostics.append("state projection is stale or missing")
            dates = {session["local_date"] for session in sessions}
            for local_date in dates:
                year, month, _ = local_date.split("-")
                journal_path = self.root / "journal" / year / month / f"{local_date}.md"
                expected_journal = journal_text(local_date, sessions, current)
                if not journal_path.exists() or journal_path.read_text(encoding="utf-8") != expected_journal:
                    diagnostics.append(f"journal projection is stale or missing: {local_date}")
        except Exception as exc:
            diagnostics.append(f"projection integrity error: {exc}")
        hook_failures = self.capture_hook_health()
        if hook_failures:
            diagnostics.append(f"capture hook has {len(hook_failures)} recorded recent failure(s)")
        try:
            conn = self._database().connect()
            try:
                db_rows = {row["entry_id"]: row for row in conn.execute("SELECT * FROM entries")}
                source_entries = {entry.entry_id: entry for entry in self.all_current_entries()}
                for entry_id, row in db_rows.items():
                    if not Path(row["current_path"]).exists():
                        diagnostics.append(f"SQLite current entry path is missing: {entry_id}")
                    elif content_hash(read_json(Path(row["current_path"]))) != row["current_hash"]:
                        diagnostics.append(f"SQLite current entry hash mismatch: {entry_id}")
                for entry_id in source_entries:
                    if entry_id not in db_rows:
                        diagnostics.append(f"source entry missing from SQLite: {entry_id}")
            finally:
                conn.close()
        except Exception as exc:
            diagnostics.append(f"SQLite integrity error: {exc}")
        repo_root = None
        for parent in (self.root, *self.root.parents):
            try:
                if (parent / ".git").exists():
                    repo_root = parent
                    break
            except OSError:
                continue
        if repo_root is not None:
            if repo_root == self.root:
                diagnostics.append("private vault is the Git repository root")
            else:
                relative = str(self.root.relative_to(repo_root))
                ignored = subprocess.run(
                    ["git", "-C", str(repo_root), "check-ignore", "--no-index", "-q", "--", relative],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                ).returncode == 0
                if not ignored:
                    diagnostics.append("private-vault path is inside Git without an effective ignore rule")
        return diagnostics


def rebuild_state_in_memory(entries: Any) -> list[dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for entry in sorted(entries, key=lambda item: (item.created_at, item.entry_id)):
        for mutation in entry.state_mutations:
            _apply_mutation(items, entry, mutation)
    return list(items.values())
