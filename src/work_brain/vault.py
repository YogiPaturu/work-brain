from __future__ import annotations

import contextlib
import json
import sqlite3
import subprocess
import shutil
import threading
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from .database import Database
from .domain import SessionEntry, normalize_alias, validate_session
from .errors import IntegrityError, PersistenceError, ValidationError
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
        self.migration_dir = Path(migration_dir).resolve() if migration_dir else default_migrations
        self._thread_lock = threading.RLock()
        self._lock_depth = 0
        self._file_lock: VaultLock | None = None
        self.dependency_change_hook = dependency_change_hook
        self.entry_publish_hook = entry_publish_hook

    # ----- topology and locking -------------------------------------------------

    def initialize(self) -> "Vault":
        for relative in (
            "sessions", "amendments", "catalog/entities", "catalog/artifacts", "journal",
            "state", "context", "questions", "career", "artifacts", "index",
        ):
            ensure_private_dir(self.root / relative)
        state_path = self.root / "state/current.json"
        if not state_path.exists():
            atomic_replace_json(state_path, {"items": []})
        # Creating the SQLite file and applying checked-in migrations is part
        # of initialization; its contents remain a rebuildable projection.
        conn = self._database().connect()
        conn.close()
        return self

    @contextlib.contextmanager
    def write_lock(self) -> Iterator[None]:
        self.initialize()
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
        domains: list[str] | None = None,
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
                "domains": list(domains or []),
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
            candidate.setdefault("domains", current.get("domains", []))
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

    def all_sessions(self) -> list[dict[str, Any]]:
        sessions = []
        for path in self._session_paths():
            value = validate_session(read_json(path))
            if path.parent.name != value["session_id"]:
                raise IntegrityError(f"session path/ID mismatch: {path}")
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

    def commit_entry(self, session_id: str, payload: Mapping[str, Any]) -> SessionEntry:
        with self._require_or_lock():
            session = self.read_session(session_id)
            turns = self._read_turns(session_id)
            current_paths = self._entry_paths(session)
            current_revision = len(current_paths)
            raw = dict(payload)
            raw.setdefault("entry_id", session["entry_id"])
            raw.setdefault("session_id", session_id)
            raw.setdefault("revision", current_revision + 1)
            raw.setdefault("commit_id", new_uuid7())
            raw.setdefault("created_at", timestamp_now())
            raw.setdefault("supersedes_revision", current_revision or None)
            raw.setdefault("revision_reason", "initial_commit" if current_revision == 0 else "reextract")
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
            atomic_replace_json(self.session_dir(session_id) / "session.json", session)
            try:
                self.rebuild_projections(affected_date=session["local_date"])
                self.reconcile_database()
                # Source publication remains authoritative; retrieval is a
                # rebuildable sibling projection.  Indexing happens only
                # after the source and derived projections are durable.
                from .retrieval import EvidenceRetriever
                EvidenceRetriever(self).index_entry(entry.entry_id)
                if self.entry_publish_hook is not None:
                    self.entry_publish_hook(entry.entry_id)
            except Exception as exc:
                raise PersistenceError(f"source commit published but derived state is stale: {exc}") from exc
            return entry

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
            try:
                self.rebuild_projections()
                self.reconcile_database()
                from .retrieval import EvidenceRetriever
                EvidenceRetriever(self).reindex()
            except Exception as exc:
                raise PersistenceError(f"session deleted but derived state is stale: {exc}") from exc

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
            try:
                self.rebuild_projections(affected_date=session["local_date"])
                self.reconcile_database()
                from .retrieval import EvidenceRetriever
                EvidenceRetriever(self).reindex()
            except Exception as exc:
                raise PersistenceError(f"entry quarantined but derived state is stale: {exc}") from exc

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
            if kind not in {"project", "person", "organization", "customer", "system", "topic"}:
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
            try:
                self.reconcile_database()
                from .retrieval import EvidenceRetriever
                EvidenceRetriever(self).reindex()
                if self.dependency_change_hook is not None:
                    self.dependency_change_hook("entity", entity_id)
            except Exception as exc:
                raise PersistenceError(f"entity published but SQLite is stale: {exc}") from exc
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
            try:
                self.reconcile_database()
                from .retrieval import EvidenceRetriever
                EvidenceRetriever(self).reindex()
                if self.dependency_change_hook is not None:
                    self.dependency_change_hook("artifact", artifact_id)
            except Exception as exc:
                raise PersistenceError(f"artifact published but SQLite is stale: {exc}") from exc
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
            self.initialize()
            self.rebuild_projections()
            self.reconcile_database()
            # Retrieval is a derived sibling projection.  Rebuild it only
            # after source projections and the SQLite projection are
            # complete, so a failed index never mutates authoritative files.
            from .retrieval import EvidenceRetriever
            EvidenceRetriever(self).reindex()

    # ----- SQLite persistence ----------------------------------------------------

    @property
    def database_path(self) -> Path:
        return self.root / "index/work-brain.sqlite"

    def _database(self) -> Database:
        return Database(self.database_path, self.migration_dir)

    def reconcile_database(self) -> None:
        self.initialize()
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
                    conn.execute("INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                        entry.entry_id, entry.session_id, entry.revision, entry.title, entry.provenance_kind,
                        entry.occurrence.start, entry.occurrence.end, entry.occurrence.precision, str(path),
                        content_hash(raw), entry.created_at))
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
            sessions = self.all_sessions()
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
        try:
            from .retrieval import EvidenceRetriever
            diagnostics.extend(EvidenceRetriever(self).doctor())
        except Exception as exc:
            diagnostics.append(f"retrieval integrity error: {exc}")
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
