from __future__ import annotations

"""Local, rebuildable evidence retrieval.

The module deliberately keeps the public surface small. SQLite owns lexical
and metadata indexes; the embedding provider is a replaceable local adapter.
FastEmbed/BGE is the normal installed profile; the deterministic hash adapter
remains an explicit offline fallback. Providers can be injected without
changing chunking, filtering, fusion, or CLI contracts.
"""

import base64
import contextlib
import hashlib
import importlib
import importlib.util
import json
import math
import os
import re
import struct
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Protocol

from .domain import ENTRY_SECTIONS, SessionEntry, normalize_alias
from .errors import FeatureUnavailable, IntegrityError, PersistenceError, ValidationError
from .fsutil import canonical_json_bytes, content_hash, read_json
from .ids import validate_uuid7
from .lock import VaultLock
from .timeutil import parse_timestamp, timestamp_now, validate_calendar_date


RECIPE_ID = "WORK-BRAIN-RETRIEVAL-RECIPE@1"
FTS_RECIPE = "unicode61-remove-diacritics-2@1"
DEFAULT_PAGE_SIZE = 8
MAX_PAGE_SIZE = 20
MAX_QUERY_CHARS = 1000
MAX_CHUNK_CHARS = 1600
MAX_CARD_SNIPPET_CHARS = 220
MAX_HYDRATE_REFS = 4


class EmbeddingProvider(Protocol):
    model_id: str
    adapter_recipe: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class AmbiguousFilter(ValidationError):
    def __init__(self, value: str, candidates: list[str]):
        super().__init__(f"entity filter is ambiguous: {value}")
        self.value = value
        self.candidates = candidates


class LocalHashEmbeddingProvider:
    """A deterministic local vector adapter with no third-party dependency.

    This is intentionally a baseline, not a claim that hashed vectors equal a
    transformer model. It gives deterministic tests and an offline fallback
    without changing the index contract.
    """

    model_id = "work-brain-hash-embedding-v1"
    adapter_recipe = "WORK-BRAIN-HASH-EMBEDDING@1"
    dimensions = 384

    def __init__(self, *, selection_reason: str = "explicit") -> None:
        self.selection_reason = selection_reason

    def _vector(self, text: str) -> list[float]:
        values = [0.0] * self.dimensions
        normalized = _normalize_text(text).casefold()
        tokens = _tokens(normalized)
        features = tokens + [f"char:{normalized[i:i + 3]}" for i in range(max(0, len(normalized) - 2))]
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:4], "little") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            values[index] += sign
        norm = math.sqrt(sum(value * value for value in values))
        if norm == 0:
            values[0] = 1.0
            return values
        return [value / norm for value in values]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class FastEmbedEmbeddingProvider:
    """Local BGE adapter for production-quality semantic recall.

    FastEmbed is deliberately imported lazily so the hash fallback remains
    usable in minimal or offline environments without changing the retrieval
    schema or search API.

    The model is loaded on the first embedding call. FastEmbed caches its
    model files locally; the first call may therefore download the model.
    """

    model_id = "BAAI/bge-small-en-v1.5"
    adapter_recipe = "WORK-BRAIN-FASTEMBED-BGE@1"
    dimensions = 384

    def __init__(self, *, cache_dir: str | None = None, selection_reason: str = "explicit") -> None:
        self.cache_dir = cache_dir
        self.selection_reason = selection_reason
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            module = importlib.import_module("fastembed")
            text_embedding = module.TextEmbedding
        except (ImportError, AttributeError) as exc:
            raise FeatureUnavailable(
                "FastEmbed is not installed; reinstall Work Brain with its runtime dependencies or use the hash fallback"
            ) from exc
        kwargs: dict[str, Any] = {"model_name": self.model_id}
        if self.cache_dir:
            kwargs["cache_dir"] = self.cache_dir
        self._model = text_embedding(**kwargs)
        size = getattr(self._model, "embedding_size", self.dimensions)
        if size != self.dimensions:
            raise IntegrityError(
                f"{self.model_id} returned {size} dimensions; expected {self.dimensions}"
            )
        return self._model

    @staticmethod
    def _as_normalized_vector(value: Any) -> list[float]:
        values = value.tolist() if hasattr(value, "tolist") else list(value)
        norm = math.sqrt(sum(float(item) * float(item) for item in values))
        if not norm:
            raise IntegrityError("FastEmbed returned a zero vector")
        return [float(item) / norm for item in values]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        return [self._as_normalized_vector(vector) for vector in model.embed([f"passage: {text}" for text in texts])]

    def embed_query(self, text: str) -> list[float]:
        model = self._load()
        return self._as_normalized_vector(next(iter(model.embed([f"query: {text}"]))))


def default_embedding_provider() -> EmbeddingProvider:
    """Select the normal local profile without breaking offline fallback.

    FastEmbed/BGE is the normal provider. ``WORK_BRAIN_EMBEDDING=hash``
    explicitly selects the deterministic fallback for tests, demos, and
    offline environments.
    """

    if os.environ.get("WORK_BRAIN_EMBEDDING", "").casefold() == "hash":
        return LocalHashEmbeddingProvider(selection_reason="explicit-hash")
    if importlib.util.find_spec("fastembed") is not None:
        return FastEmbedEmbeddingProvider(selection_reason="default-fastembed")
    return LocalHashEmbeddingProvider(selection_reason="fastembed-unavailable")


@dataclass(frozen=True)
class EvidenceRef:
    entry_id: str
    revision: int

    def to_dict(self) -> dict[str, Any]:
        return {"entry_id": self.entry_id, "revision": self.revision}


@dataclass(frozen=True)
class RetrievalHealth:
    index_state: str
    stale_entries: int
    lexical_available: bool
    semantic_available: bool
    generation: str


class StaleIndexWork(IntegrityError):
    """Embedding work was based on a source revision that is no longer current."""


def embedding_profile(provider: EmbeddingProvider) -> dict[str, Any]:
    """Return a safe, user-facing description of the selected vector provider."""

    if isinstance(provider, FastEmbedEmbeddingProvider):
        return {
            "provider": "fastembed",
            "model": provider.model_id,
            "semantic_quality": "bge",
            "fallback": False,
            "selection_reason": getattr(provider, "selection_reason", "explicit"),
            "dimensions": provider.dimensions,
        }
    if isinstance(provider, LocalHashEmbeddingProvider):
        return {
            "provider": "hash",
            "model": provider.model_id,
            "semantic_quality": "hash-fallback",
            "fallback": True,
            "selection_reason": getattr(provider, "selection_reason", "explicit"),
            "dimensions": provider.dimensions,
        }
    return {
        "provider": "custom",
        "model": provider.model_id,
        "semantic_quality": "custom",
        "fallback": False,
        "selection_reason": "injected",
        "dimensions": provider.dimensions,
    }


def _normalize_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).replace("\r\n", "\n").replace("\r", "\n")


def _tokens(value: str) -> list[str]:
    return re.findall(r"[\w][\w'_-]*", value, flags=re.UNICODE)


def _safe_query(value: str) -> str:
    tokens = _tokens(_normalize_text(value).casefold())
    return " OR ".join(f'"{token.replace(chr(34), "")}"' for token in tokens)


def _epoch_ms(value: str | None, *, end_of_day: bool = False) -> int | None:
    if value is None:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        validate_calendar_date(value)
        parsed = datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
        if end_of_day:
            return int(parsed.timestamp() * 1000) + 24 * 60 * 60 * 1000
        return int(parsed.timestamp() * 1000)
    return int(parse_timestamp(value).astimezone(timezone.utc).timestamp() * 1000)


def _clip(value: str, limit: int = MAX_CARD_SNIPPET_CHARS) -> str:
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    return value[: max(1, limit - 1)].rstrip() + "…"


def _split_text(text: str, limit: int = MAX_CHUNK_CHARS) -> list[str]:
    text = _normalize_text(text).strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    result: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind(" ", 0, limit + 1)
        if cut < max(1, limit // 2):
            cut = limit
        result.append(remaining[:cut].strip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        result.append(remaining)
    return result


def _statement_texts(entry: SessionEntry, section: str) -> list[str]:
    return [statement.text for statement in entry.sections[section]]


def _chunk_id(entry: SessionEntry, kind: str, section: str | None, ordinal: int) -> str:
    material = "\0".join((RECIPE_ID, entry.entry_id, str(entry.revision), kind, section or "-", str(ordinal)))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _chunks(entry: SessionEntry, metadata: str) -> list[dict[str, Any]]:
    overview_lines = [f"Title: {entry.title}", f"Summary: {entry.summary}"]
    if entry.domain_tags:
        overview_lines.append("Domain tags: " + ", ".join(entry.domain_tags))
    if entry.modes:
        overview_lines.append("Modes: " + ", ".join(entry.modes))
    overview = "\n".join(overview_lines)
    result: list[dict[str, Any]] = []
    ordinal = 0

    def add(kind: str, section: str | None, text: str) -> None:
        nonlocal ordinal
        for part in _split_text(text):
            chunk_id = _chunk_id(entry, kind, section, ordinal)
            result.append({
                "chunk_id": chunk_id, "entry_id": entry.entry_id, "source_revision": entry.revision,
                "chunk_kind": kind, "section_key": section, "ordinal": ordinal,
                "text": part, "text_hash": hashlib.sha256(_normalize_text(part).encode("utf-8")).hexdigest(),
                "title": entry.title, "metadata": metadata,
            })
            ordinal += 1

    add("overview", None, overview)
    for section in ENTRY_SECTIONS:
        statements = _statement_texts(entry, section)
        if statements:
            add("section", section, f"{section.replace('_', ' ').title()}\n" + "\n".join(f"- {text}" for text in statements))
    for mutation in entry.state_mutations:
        fields = mutation.fields
        lines = [f"{mutation.kind or 'state'}: {fields.get('title', mutation.state_item_id)}"]
        for label, key in (("status", "status"), ("next", "next_action"), ("waiting on", "waiting_on"), ("details", "details")):
            if fields.get(key):
                lines.append(f"{label}: {fields[key]}")
        add("state", None, "\n".join(lines))
    return result


def _cursor_encode(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _cursor_decode(value: str) -> dict[str, Any]:
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("cursor must be an opaque continuation returned by search_evidence") from exc
    if not isinstance(decoded, dict):
        raise ValidationError("cursor must be an opaque continuation returned by search_evidence")
    return decoded


class EvidenceRetriever:
    """Hybrid evidence retrieval over one private vault."""

    def __init__(self, vault: Any, embedding_provider: EmbeddingProvider | None = None):
        self.vault = vault
        self.embedding_provider = embedding_provider or default_embedding_provider()

    def embedding_status(
        self,
        health: RetrievalHealth | None = None,
        *,
        runtime_failure: bool = False,
    ) -> dict[str, Any]:
        """Describe the selected provider and whether its index is usable."""

        status = embedding_profile(self.embedding_provider)
        if health is None:
            status["status"] = "fallback" if status["fallback"] else "selected"
            return status
        status.update({
            "index_available": health.semantic_available,
            "index_state": health.index_state,
            "stale_entries": health.stale_entries,
        })
        if runtime_failure:
            status["status"] = "degraded"
            status["reason"] = "provider-error"
        elif not health.semantic_available:
            status["status"] = "degraded"
            status["reason"] = "reindex-required"
            status["warning"] = "The selected embedding provider does not match the indexed vectors; run work-brain reindex."
        elif status["fallback"]:
            status["status"] = "fallback"
            if status["selection_reason"] == "fastembed-unavailable":
                status["warning"] = "FastEmbed is unavailable; deterministic hash embeddings are active."
        else:
            status["status"] = "available"
        return status

    def _db(self):
        return self.vault._database()

    @contextlib.contextmanager
    def _index_lock(self):
        with VaultLock(self.vault.root / ".index.write.lock"):
            yield

    def _dependency_hash(self, entry: SessionEntry) -> str:
        dependencies: list[Any] = []
        if entry.workspace_entity_id is not None:
            path = self.vault.root / "catalog/entities" / f"{entry.workspace_entity_id}.json"
            dependencies.append({"kind": "workspace", "relation": "workspace", "value": read_json(path)})
        if entry.project_entity_id is not None:
            path = self.vault.root / "catalog/entities" / f"{entry.project_entity_id}.json"
            dependencies.append({"kind": "project", "relation": "project", "value": read_json(path)})
        for ref in sorted(entry.entity_refs, key=lambda item: (item["entity_id"], item["relation"])):
            path = self.vault.root / "catalog/entities" / f"{ref['entity_id']}.json"
            dependencies.append({"kind": "entity", "relation": ref["relation"], "value": read_json(path)})
        for ref in sorted(entry.artifact_refs, key=lambda item: (item["artifact_id"], item["relation"])):
            path = self.vault.root / "catalog/artifacts" / f"{ref['artifact_id']}.json"
            dependencies.append({"kind": "artifact", "relation": ref["relation"], "value": read_json(path)})
        return hashlib.sha256(canonical_json_bytes(dependencies)).hexdigest()

    def _metadata(self, entry: SessionEntry) -> str:
        values = list(entry.domain_tags) + list(entry.modes)
        if entry.workspace_entity_id is not None:
            value = read_json(self.vault.root / "catalog/entities" / f"{entry.workspace_entity_id}.json")
            values.extend([value["canonical_name"], *value.get("aliases", [])])
        if entry.project_entity_id is not None:
            value = read_json(self.vault.root / "catalog/entities" / f"{entry.project_entity_id}.json")
            values.extend([value["canonical_name"], *value.get("aliases", [])])
        for ref in entry.entity_refs:
            value = read_json(self.vault.root / "catalog/entities" / f"{ref['entity_id']}.json")
            values.extend([value["canonical_name"], *value.get("aliases", [])])
        for ref in entry.artifact_refs:
            value = read_json(self.vault.root / "catalog/artifacts" / f"{ref['artifact_id']}.json")
            values.extend([value["kind"], value["label"]])
        if entry.occurrence.label:
            values.append(entry.occurrence.label)
        return " ".join(values)

    def _source_hash(self, entry: SessionEntry) -> str:
        session = self.vault.read_session(entry.session_id)
        path = self.vault._entry_paths(session)[-1]
        return content_hash(read_json(path))

    def _set_meta(self, conn: Any, key: str, value: str) -> None:
        conn.execute(
            "INSERT INTO retrieval_meta(key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, timestamp_now()),
        )

    def _meta(self, conn: Any) -> dict[str, str]:
        return {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM retrieval_meta")}

    def _vectors(self, chunks: list[dict[str, Any]]) -> list[list[float]]:
        vectors = self.embedding_provider.embed_documents([chunk["text"] for chunk in chunks])
        if len(vectors) != len(chunks):
            raise IntegrityError("embedding provider returned the wrong number of vectors")
        for vector in vectors:
            self._validate_vector(vector)
        return vectors

    def _validate_vector(self, vector: Any) -> None:
        if not isinstance(vector, (list, tuple)) or len(vector) != self.embedding_provider.dimensions:
            raise ValidationError(f"embedding vector must have exactly {self.embedding_provider.dimensions} dimensions")
        norm = 0.0
        for value in vector:
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValidationError("embedding vector must contain finite numbers")
            norm += float(value) * float(value)
        if not 0.99 <= math.sqrt(norm) <= 1.01:
            raise ValidationError("embedding vector must be L2-normalized")

    def _vector_bytes(self, vector: Iterable[float]) -> bytes:
        return struct.pack("<" + "f" * self.embedding_provider.dimensions, *(float(value) for value in vector))

    def _prepare_entry_index(self, entry_id: str) -> dict[str, Any]:
        entry = self.vault.get_current_entry(entry_id)
        source_hash = self._source_hash(entry)
        dependency_hash = self._dependency_hash(entry)
        metadata = self._metadata(entry)
        chunks = _chunks(entry, metadata)
        vectors = self._vectors(chunks)
        return {
            "entry": entry,
            "source_hash": source_hash,
            "dependency_hash": dependency_hash,
            "chunks": chunks,
            "vectors": vectors,
        }

    def _index_entry_locked(self, prepared: Mapping[str, Any], conn: Any) -> dict[str, Any]:
        entry = prepared["entry"]
        source_hash = prepared["source_hash"]
        dependency_hash = prepared["dependency_hash"]
        chunks = prepared["chunks"]
        vectors = prepared["vectors"]
        current = self.vault.get_current_entry(entry.entry_id)
        if current.revision != entry.revision or self._source_hash(current) != source_hash or self._dependency_hash(current) != dependency_hash:
            raise StaleIndexWork(f"source changed while preparing index work: {entry.entry_id}")
        occurrence_start = _epoch_ms(entry.occurrence.start) if entry.occurrence.start and entry.occurrence.precision == "instant" else _epoch_ms(entry.occurrence.start)
        occurrence_end = _epoch_ms(entry.occurrence.end) if entry.occurrence.end and entry.occurrence.precision == "instant" else _epoch_ms(entry.occurrence.end)
        conn.execute("DELETE FROM retrieval_fts WHERE entry_id = ?", (entry.entry_id,))
        conn.execute("DELETE FROM retrieval_entries WHERE entry_id = ?", (entry.entry_id,))
        conn.execute(
            "INSERT INTO retrieval_entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entry.entry_id, entry.revision, source_hash, dependency_hash, RECIPE_ID, entry.title, entry.summary,
             entry.provenance_kind, occurrence_start, occurrence_end, entry.occurrence.precision, entry.occurrence.label,
             int(bool(entry.sections["outcomes"])), int(bool(entry.sections["open_questions"])), timestamp_now(),
             entry.project_entity_id, entry.workspace_entity_id),
        )
        for mode in entry.modes:
            conn.execute("INSERT INTO retrieval_entry_modes VALUES (?, ?)", (entry.entry_id, normalize_alias(mode)))
        for domain_tag in entry.domain_tags:
            conn.execute("INSERT INTO retrieval_entry_domain_tags VALUES (?, ?)", (entry.entry_id, normalize_alias(domain_tag)))
        for chunk, vector in zip(chunks, vectors):
            conn.execute(
                "INSERT INTO retrieval_chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (chunk["chunk_id"], entry.entry_id, entry.revision, chunk["chunk_kind"], chunk["section_key"],
                 chunk["ordinal"], chunk["text"], chunk["text_hash"]),
            )
            conn.execute("INSERT INTO retrieval_fts(chunk_id, entry_id, title, body, metadata) VALUES (?, ?, ?, ?, ?)",
                         (chunk["chunk_id"], entry.entry_id, chunk["title"], chunk["text"], chunk["metadata"]))
            conn.execute(
                "INSERT INTO retrieval_embeddings VALUES (?, ?, ?, ?, ?, ?, ?)",
                (chunk["chunk_id"], self.embedding_provider.model_id, self.embedding_provider.adapter_recipe,
                 self.embedding_provider.dimensions, chunk["text_hash"], self._vector_bytes(vector), timestamp_now()),
            )
        return {"entry_id": entry.entry_id, "source_revision": entry.revision, "source_hash": source_hash,
                "dependency_hash": dependency_hash, "status": "indexed", "chunk_count": len(chunks),
                "recipe_id": RECIPE_ID, "embedding_model_id": self.embedding_provider.model_id,
                "embedding": embedding_profile(self.embedding_provider),
                "indexed_at": timestamp_now()}

    def index_entry(self, entry_id: str) -> dict[str, Any]:
        validate_uuid7(entry_id, "entry_id")
        self.vault.initialize_projections()
        prepared = self._prepare_entry_index(entry_id)
        with self._index_lock():
            conn = self._db().connect()
            try:
                with conn:
                    self._set_meta(conn, "index_state", "building")
                    result = self._index_entry_locked(prepared, conn)
                    self._set_meta(conn, "index_state", "current")
                    self._set_meta(conn, "generation", hashlib.sha256(f"{timestamp_now()}:{entry_id}".encode()).hexdigest())
                return result
            finally:
                conn.close()

    def reindex(self) -> dict[str, Any]:
        self.vault.initialize_projections()
        prepared_entries = [self._prepare_entry_index(entry.entry_id) for entry in self.vault.all_current_entries()]
        with self._index_lock():
            conn = self._db().connect()
            try:
                with conn:
                    self._set_meta(conn, "index_state", "building")
                    self._set_meta(conn, "full_reindex_started_at", timestamp_now())
                    conn.execute("DELETE FROM retrieval_fts")
                    conn.execute("DELETE FROM retrieval_embeddings")
                    conn.execute("DELETE FROM retrieval_chunks")
                    conn.execute("DELETE FROM retrieval_entry_modes")
                    conn.execute("DELETE FROM retrieval_entry_domain_tags")
                    conn.execute("DELETE FROM retrieval_entries")
                indexed = []
                for prepared in prepared_entries:
                    with conn:
                        indexed.append(self._index_entry_locked(prepared, conn))
                with conn:
                    self._set_meta(conn, "recipe_id", RECIPE_ID)
                    self._set_meta(conn, "embedding_model_id", self.embedding_provider.model_id)
                    self._set_meta(conn, "embedding_adapter_recipe", self.embedding_provider.adapter_recipe)
                    self._set_meta(conn, "embedding_dimensions", str(self.embedding_provider.dimensions))
                    self._set_meta(conn, "fts_recipe", FTS_RECIPE)
                    self._set_meta(conn, "index_state", "current")
                    self._set_meta(conn, "full_reindex_completed_at", timestamp_now())
                    self._set_meta(conn, "generation", hashlib.sha256(f"{timestamp_now()}:full".encode()).hexdigest())
                result = {
                    "status": "current",
                    "indexed_entries": len(indexed),
                    "indexed_chunks": sum(item["chunk_count"] for item in indexed),
                    "embedding": self.embedding_status(),
                }
                return result
            except Exception:
                with conn:
                    self._set_meta(conn, "index_state", "stale")
                raise
            finally:
                conn.close()

    def remove_entry(self, entry_id: str) -> None:
        validate_uuid7(entry_id, "entry_id")
        conn = self._db().connect()
        try:
            with conn:
                conn.execute("DELETE FROM retrieval_fts WHERE entry_id = ?", (entry_id,))
                conn.execute("DELETE FROM retrieval_entries WHERE entry_id = ?", (entry_id,))
                self._set_meta(conn, "index_state", "current")
        finally:
            conn.close()

    def _source_rows(self, conn: Any) -> dict[str, SessionEntry]:
        return {entry.entry_id: entry for entry in self.vault.all_current_entries()}

    def health(self) -> RetrievalHealth:
        conn = self._db().connect()
        try:
            meta = self._meta(conn)
            current = self._source_rows(conn)
            stale = 0
            valid_ids: set[str] = set()
            for entry in current.values():
                row = conn.execute("SELECT * FROM retrieval_entries WHERE entry_id = ?", (entry.entry_id,)).fetchone()
                if row is None or row["source_revision"] != entry.revision or row["recipe_id"] != RECIPE_ID:
                    stale += 1
                    continue
                if row["source_hash"] != self._source_hash(entry) or row["dependency_hash"] != self._dependency_hash(entry):
                    stale += 1
                    continue
                valid_ids.add(entry.entry_id)
            chunks = {row["chunk_id"] for row in conn.execute("SELECT chunk_id FROM retrieval_chunks WHERE entry_id IN ({})".format(",".join("?" * len(valid_ids)) if valid_ids else "NULL"), tuple(valid_ids))} if valid_ids else set()
            fts = {row["chunk_id"] for row in conn.execute("SELECT chunk_id FROM retrieval_fts")}
            embeddings = {row["chunk_id"] for row in conn.execute(
                "SELECT chunk_id FROM retrieval_embeddings WHERE model_id = ? AND adapter_recipe = ? AND dimensions = ?",
                (self.embedding_provider.model_id, self.embedding_provider.adapter_recipe, self.embedding_provider.dimensions),
            )}
            lexical = bool(valid_ids) and chunks == fts and all(row["chunk_id"] in chunks for row in conn.execute("SELECT chunk_id FROM retrieval_chunks WHERE entry_id IN ({})".format(",".join("?" * len(valid_ids)) if valid_ids else "NULL"), tuple(valid_ids))) if valid_ids else True
            semantic = bool(valid_ids) and chunks == embeddings
            return RetrievalHealth(meta.get("index_state", "stale"), stale, lexical, semantic, meta.get("generation", ""))
        finally:
            conn.close()

    def _ensure_current(self) -> RetrievalHealth:
        """Read index health without mutating or rebuilding the index."""
        try:
            return self.health()
        except Exception:
            return RetrievalHealth("failed", 0, False, False, "")

    def _eligible(self, conn: Any, filters: Mapping[str, Any]) -> set[str]:
        allowed = {"occurred_after", "occurred_before", "entities", "workspaces", "projects", "domain_tags", "modes", "provenance_kind", "has_outcome"}
        unknown = sorted(set(filters) - allowed)
        if unknown:
            raise ValidationError(f"unknown evidence filter: {unknown[0]}")
        params: list[Any] = []
        clauses = ["1=1"]
        after = _epoch_ms(filters.get("occurred_after")) if filters.get("occurred_after") is not None else None
        before = _epoch_ms(filters.get("occurred_before")) if filters.get("occurred_before") is not None else None
        if after is not None:
            clauses.append("r.occurrence_start_ms >= ?")
            params.append(after)
        if before is not None:
            clauses.append("r.occurrence_start_ms < ?")
            params.append(before)
        if filters.get("provenance_kind") is not None:
            if filters["provenance_kind"] not in {"contemporaneous", "reconstructed"}:
                raise ValidationError("provenance_kind must be contemporaneous or reconstructed")
            clauses.append("r.provenance_kind = ?")
            params.append(filters["provenance_kind"])
        if filters.get("has_outcome") is not None:
            if not isinstance(filters["has_outcome"], bool):
                raise ValidationError("has_outcome must be a boolean")
            clauses.append("r.has_outcome = ?")
            params.append(int(filters["has_outcome"]))
        ids = None
        for field, table in (("domain_tags", "retrieval_entry_domain_tags"), ("modes", "retrieval_entry_modes")):
            values = filters.get(field, [])
            if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValidationError(f"{field} must be a list of non-empty strings")
            if values:
                normalized = [normalize_alias(value.strip()) for value in values]
                placeholders = ",".join("?" * len(normalized))
                rows = conn.execute(f"SELECT DISTINCT entry_id FROM {table} WHERE {field[:-1]} IN ({placeholders})", normalized).fetchall()
                match_ids = {row["entry_id"] for row in rows}
                ids = match_ids if ids is None else ids & match_ids
        entity_values = filters.get("entities", [])
        if not isinstance(entity_values, list) or any(not isinstance(value, str) or not value.strip() for value in entity_values):
            raise ValidationError("entities must be a list of non-empty strings")
        if entity_values:
            entity_ids: set[str] = set()
            for value in entity_values:
                normalized = normalize_alias(value.strip())
                rows = conn.execute(
                    "SELECT entity_id FROM entities WHERE entity_id = ? "
                    "UNION SELECT DISTINCT entity_id FROM entity_aliases WHERE alias_norm = ?",
                    (value.strip(), normalized),
                ).fetchall()
                if not rows:
                    continue
                if len(rows) > 1:
                    raise AmbiguousFilter(value, sorted(row["entity_id"] for row in rows))
                entity_ids.add(rows[0]["entity_id"])
            if entity_ids:
                placeholders = ",".join("?" * len(entity_ids))
                rows = conn.execute(f"SELECT DISTINCT entry_id FROM entry_entities WHERE entity_id IN ({placeholders})", tuple(entity_ids)).fetchall()
                match_ids = {row["entry_id"] for row in rows}
                ids = match_ids if ids is None else ids & match_ids
            else:
                ids = set()
        workspace_values = filters.get("workspaces", [])
        if not isinstance(workspace_values, list) or any(not isinstance(value, str) or not value.strip() for value in workspace_values):
            raise ValidationError("workspaces must be a list of non-empty strings")
        if workspace_values:
            workspace_ids: set[str] = set()
            for value in workspace_values:
                normalized = normalize_alias(value.strip())
                rows = conn.execute(
                    "SELECT entity_id FROM entities WHERE kind = 'workspace' AND entity_id = ? "
                    "UNION SELECT DISTINCT ea.entity_id FROM entity_aliases ea "
                    "JOIN entities e ON e.entity_id = ea.entity_id "
                    "WHERE e.kind = 'workspace' AND ea.alias_norm = ?",
                    (value.strip(), normalized),
                ).fetchall()
                if not rows:
                    continue
                if len(rows) > 1:
                    raise AmbiguousFilter(value, sorted(row["entity_id"] for row in rows))
                workspace_ids.add(rows[0]["entity_id"])
            if workspace_ids:
                placeholders = ",".join("?" * len(workspace_ids))
                rows = conn.execute(
                    f"SELECT DISTINCT entry_id FROM retrieval_entries WHERE workspace_entity_id IN ({placeholders})",
                    tuple(workspace_ids),
                ).fetchall()
                match_ids = {row["entry_id"] for row in rows}
                ids = match_ids if ids is None else ids & match_ids
            else:
                ids = set()
        project_values = filters.get("projects", [])
        if not isinstance(project_values, list) or any(not isinstance(value, str) or not value.strip() for value in project_values):
            raise ValidationError("projects must be a list of non-empty strings")
        if project_values:
            project_ids: set[str] = set()
            for value in project_values:
                normalized = normalize_alias(value.strip())
                rows = conn.execute(
                    "SELECT entity_id FROM entities WHERE kind = 'project' AND entity_id = ? "
                    "UNION SELECT DISTINCT ea.entity_id FROM entity_aliases ea "
                    "JOIN entities e ON e.entity_id = ea.entity_id "
                    "WHERE e.kind = 'project' AND ea.alias_norm = ?",
                    (value.strip(), normalized),
                ).fetchall()
                if not rows:
                    continue
                if len(rows) > 1:
                    raise AmbiguousFilter(value, sorted(row["entity_id"] for row in rows))
                project_ids.add(rows[0]["entity_id"])
            if project_ids:
                placeholders = ",".join("?" * len(project_ids))
                rows = conn.execute(
                    f"SELECT DISTINCT entry_id FROM retrieval_entries WHERE project_entity_id IN ({placeholders})",
                    tuple(project_ids),
                ).fetchall()
                match_ids = {row["entry_id"] for row in rows}
                ids = match_ids if ids is None else ids & match_ids
            else:
                ids = set()
        base = "SELECT r.entry_id FROM retrieval_entries r WHERE " + " AND ".join(clauses)
        rows = conn.execute(base, params).fetchall()
        result = {row["entry_id"] for row in rows}
        return result if ids is None else result & ids

    def _branch_lexical(self, conn: Any, query: str, eligible: set[str]) -> dict[str, dict[str, Any]]:
        expression = _safe_query(query)
        if not expression or not eligible:
            return {}
        placeholders = ",".join("?" * len(eligible))
        rows = conn.execute(
            f"SELECT retrieval_fts.entry_id, retrieval_fts.body, c.section_key, bm25(retrieval_fts, 0.0, 0.0, 3.0, 1.0, 1.5) AS rank "
            f"FROM retrieval_fts JOIN retrieval_chunks c ON c.chunk_id = retrieval_fts.chunk_id WHERE retrieval_fts MATCH ? AND retrieval_fts.entry_id IN ({placeholders}) ORDER BY rank ASC, retrieval_fts.entry_id ASC",
            (expression, *sorted(eligible)),
        ).fetchall()
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = result.setdefault(row["entry_id"], {"snippets": [], "sections": []})
            if len(item["snippets"]) < 2:
                item["snippets"].append(_clip(row["body"]))
            if row["section_key"] and row["section_key"] not in item["sections"] and len(item["sections"]) < 3:
                item["sections"].append(row["section_key"])
        return result

    def _branch_semantic(self, conn: Any, query: str, eligible: set[str]) -> dict[str, dict[str, Any]]:
        if not eligible:
            return {}
        query_vector = self.embedding_provider.embed_query(query)
        self._validate_vector(query_vector)
        placeholders = ",".join("?" * len(eligible))
        rows = conn.execute(
            f"SELECT c.entry_id, e.chunk_id, e.vector FROM retrieval_embeddings e JOIN retrieval_chunks c ON c.chunk_id = e.chunk_id "
            f"WHERE e.model_id = ? AND e.adapter_recipe = ? AND e.dimensions = ? AND c.entry_id IN ({placeholders})",
            (self.embedding_provider.model_id, self.embedding_provider.adapter_recipe, self.embedding_provider.dimensions, *sorted(eligible)),
        ).fetchall()
        scored: list[tuple[float, str, str]] = []
        for row in rows:
            values = struct.unpack("<" + "f" * self.embedding_provider.dimensions, row["vector"])
            scored.append((sum(a * b for a, b in zip(query_vector, values)), row["entry_id"], row["chunk_id"]))
        scored.sort(key=lambda item: (-item[0], item[1]))
        result: dict[str, dict[str, Any]] = {}
        for score, entry_id, chunk_id in scored:
            item = result.setdefault(entry_id, {"snippets": [], "sections": []})
            if len(item["snippets"]) < 2:
                chunk = conn.execute("SELECT text, section_key FROM retrieval_chunks WHERE chunk_id = ?", (chunk_id,)).fetchone()
                if chunk:
                    item["snippets"].append(_clip(chunk["text"]))
                    if chunk["section_key"] and chunk["section_key"] not in item["sections"]:
                        item["sections"].append(chunk["section_key"])
        return result

    def search(self, query: str, *, filters: Mapping[str, Any] | None = None, page_size: int = DEFAULT_PAGE_SIZE, cursor: str | None = None) -> dict[str, Any]:
        if not isinstance(query, str) or not 1 <= len(_normalize_text(query).strip()) <= MAX_QUERY_CHARS:
            raise ValidationError("query must be between 1 and 1000 characters")
        if not isinstance(page_size, int) or not 1 <= page_size <= MAX_PAGE_SIZE:
            raise ValidationError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")
        normalized_filters = dict(filters or {})
        health = self._ensure_current()
        embedding = self.embedding_status(health)
        if not health.lexical_available and not health.semantic_available:
            return {"status": "retrieval_unavailable", "degraded_components": ["index"], "incomplete": True, "omitted_stale_entries": health.stale_entries, "cards": [], "next_cursor": None, "embedding": embedding}
        conn = self._db().connect()
        try:
            try:
                eligible = self._eligible(conn, normalized_filters)
            except AmbiguousFilter as exc:
                return {"status": "ambiguous_filter", "degraded_components": [], "incomplete": health.stale_entries > 0, "omitted_stale_entries": health.stale_entries, "cards": [], "next_cursor": None, "error": {"value": exc.value, "candidates": exc.candidates}, "embedding": embedding}
            generation = health.generation
            fingerprint = hashlib.sha256(canonical_json_bytes({"query": _normalize_text(query).strip(), "filters": normalized_filters, "page_size": page_size})).hexdigest()
            offset = 0
            if cursor:
                decoded = _cursor_decode(cursor)
                if decoded.get("fingerprint") != fingerprint or decoded.get("generation") != generation:
                    return {"status": "cursor_expired", "degraded_components": [], "incomplete": health.stale_entries > 0, "omitted_stale_entries": health.stale_entries, "cards": [], "next_cursor": None, "embedding": embedding}
                offset = int(decoded.get("offset", 0))
            lexical: dict[str, dict[str, Any]] = {}
            semantic: dict[str, dict[str, Any]] = {}
            degraded: list[str] = []
            if health.index_state != "current" or health.stale_entries:
                degraded.append("index")
            if health.lexical_available:
                try:
                    lexical = self._branch_lexical(conn, query, eligible)
                except Exception:
                    degraded.append("fts")
            else:
                degraded.append("fts")
            if health.semantic_available:
                try:
                    semantic = self._branch_semantic(conn, query, eligible)
                except Exception:
                    degraded.append("semantic")
                    embedding = self.embedding_status(health, runtime_failure=True)
            else:
                degraded.append("semantic")
            if not lexical and not semantic and len(degraded) == 2:
                return {"status": "retrieval_unavailable", "degraded_components": degraded, "incomplete": True, "omitted_stale_entries": health.stale_entries, "cards": [], "next_cursor": None, "embedding": embedding}
            lexical_rank = {entry_id: rank for rank, entry_id in enumerate(lexical, 1)}
            semantic_rank = {entry_id: rank for rank, entry_id in enumerate(semantic, 1)}
            candidates = set(lexical) | set(semantic)
            def sort_key(entry_id: str) -> tuple[Any, ...]:
                rrf = (1 / (60 + lexical_rank[entry_id]) if entry_id in lexical_rank else 0) + (1 / (60 + semantic_rank[entry_id]) if entry_id in semantic_rank else 0)
                return (-rrf, -(1 if entry_id in lexical_rank and entry_id in semantic_rank else 0), min(lexical_rank.get(entry_id, 10**9), semantic_rank.get(entry_id, 10**9)), entry_id)
            ordered = sorted(candidates, key=sort_key)
            page_ids = ordered[offset:offset + page_size]
            rows = {row["entry_id"]: row for row in conn.execute("SELECT * FROM retrieval_entries")}
            cards = []
            for entry_id in page_ids:
                row = rows[entry_id]
                match = {
                    "snippets": list(lexical.get(entry_id, {}).get("snippets", [])) + list(semantic.get(entry_id, {}).get("snippets", [])),
                    "sections": list(lexical.get(entry_id, {}).get("sections", [])) + list(semantic.get(entry_id, {}).get("sections", [])),
                }
                signals = [signal for signal, branch in (("lexical", lexical), ("semantic", semantic)) if entry_id in branch]
                snippets = []
                for value in match.get("snippets", []):
                    if value not in snippets:
                        snippets.append(value)
                entry = self.vault.get_current_entry(entry_id)
                workspace = None
                if entry.workspace_entity_id is not None:
                    workspace_value = read_json(self.vault.root / "catalog/entities" / f"{entry.workspace_entity_id}.json")
                    workspace = {"entity_id": workspace_value["entity_id"], "kind": workspace_value["kind"], "name": workspace_value["canonical_name"]}
                entities = []
                for ref in entry.entity_refs:
                    entity = read_json(self.vault.root / "catalog/entities" / f"{ref['entity_id']}.json")
                    entities.append({"entity_id": entity["entity_id"], "kind": entity["kind"], "name": entity["canonical_name"]})
                project = None
                if entry.project_entity_id is not None:
                    project_value = read_json(self.vault.root / "catalog/entities" / f"{entry.project_entity_id}.json")
                    project = {"entity_id": project_value["entity_id"], "kind": project_value["kind"], "name": project_value["canonical_name"]}
                cards.append({"ref": {"entry_id": entry_id, "revision": row["source_revision"]}, "title": row["title"], "when": entry.occurrence.to_dict(), "summary": row["summary"], "provenance_kind": row["provenance_kind"], "modes": entry.modes, "domain_tags": entry.domain_tags, "workspace": workspace, "project": project, "entities": entities, "match": {"signals": signals, "sections": list(dict.fromkeys(match["sections"]))[:3], "snippets": snippets[:2]}, "flags": {"has_outcome": bool(row["has_outcome"]), "has_open_questions": bool(row["has_open_questions"])}})
            next_cursor = None
            if offset + page_size < len(ordered):
                next_cursor = _cursor_encode({"fingerprint": fingerprint, "generation": generation, "offset": offset + page_size})
            status = "degraded" if degraded else "ok"
            return {"status": status, "degraded_components": sorted(set(degraded)), "incomplete": health.stale_entries > 0, "omitted_stale_entries": health.stale_entries, "cards": cards, "next_cursor": next_cursor, "embedding": embedding}
        finally:
            conn.close()

    def hydrate(self, refs: list[Mapping[str, Any]]) -> dict[str, Any]:
        if not isinstance(refs, list) or not 1 <= len(refs) <= MAX_HYDRATE_REFS:
            raise ValidationError(f"refs must contain between 1 and {MAX_HYDRATE_REFS} items")
        items = []
        current = {entry.entry_id: entry for entry in self.vault.all_current_entries()}
        revisions = {}
        for entry, _ in self.vault.all_entry_revisions():
            revisions[(entry.entry_id, entry.revision)] = entry
        for raw in refs:
            if not isinstance(raw, Mapping):
                raise ValidationError("each evidence ref must be an object")
            entry_id = validate_uuid7(raw.get("entry_id"), "ref.entry_id")
            revision = raw.get("revision")
            if not isinstance(revision, int) or revision < 1:
                raise ValidationError("ref.revision must be a positive integer")
            entry = revisions.get((entry_id, revision))
            if entry is None:
                items.append({"ref": {"entry_id": entry_id, "revision": revision}, "status": "not_found"})
                continue
            current_entry = current.get(entry_id)
            catalog_entities = [read_json(self.vault.root / "catalog/entities" / f"{ref['entity_id']}.json") for ref in entry.entity_refs]
            catalog_artifacts = [read_json(self.vault.root / "catalog/artifacts" / f"{ref['artifact_id']}.json") for ref in entry.artifact_refs]
            items.append({"ref": {"entry_id": entry_id, "revision": revision}, "status": "current" if current_entry and current_entry.revision == revision else "historical", "current_revision": current_entry.revision if current_entry else None, "entry": entry.to_dict(), "entities": catalog_entities, "artifacts": catalog_artifacts})
        return {"items": items}

    def doctor(self) -> list[str]:
        diagnostics: list[str] = []
        try:
            health = self.health()
            conn = self._db().connect()
            try:
                meta = self._meta(conn)
                if not meta and not self.vault.all_current_entries():
                    return []
                if meta.get("index_state") in {"building", "stale"}:
                    diagnostics.append(f"retrieval index state is {meta['index_state']}")
                if health.stale_entries:
                    diagnostics.append(f"retrieval index has {health.stale_entries} stale current entries")
                chunks = {row["chunk_id"] for row in conn.execute("SELECT chunk_id FROM retrieval_chunks")}
                fts = {row["chunk_id"] for row in conn.execute("SELECT chunk_id FROM retrieval_fts")}
                if chunks != fts:
                    diagnostics.append("retrieval FTS/chunk corpus mismatch")
                vectors = {row["chunk_id"] for row in conn.execute("SELECT chunk_id FROM retrieval_embeddings")}
                if health.semantic_available and chunks != vectors:
                    diagnostics.append("retrieval embedding/chunk corpus mismatch")
            finally:
                conn.close()
        except Exception as exc:
            diagnostics.append(f"retrieval integrity error: {exc}")
        return diagnostics
