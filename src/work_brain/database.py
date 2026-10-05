from __future__ import annotations

import sqlite3
from pathlib import Path

from .errors import PersistenceError
from .fsutil import atomic_replace_json, content_hash, read_json
from .timeutil import timestamp_now


class Database:
    def __init__(self, path: Path, migration_dir: Path):
        self.path = path
        self.migration_dir = migration_dir

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        self.migrate(conn)
        return conn

    def migrate(self, conn: sqlite3.Connection) -> None:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (migration_id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        applied = {row[0] for row in conn.execute("SELECT migration_id FROM schema_migrations")}
        for path in sorted(self.migration_dir.glob("*.sql")):
            migration_id = path.name
            if migration_id in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            try:
                with conn:
                    conn.executescript(sql)
                    conn.execute("INSERT INTO schema_migrations(migration_id, applied_at) VALUES (?, ?)", (migration_id, timestamp_now()))
            except sqlite3.Error as exc:
                raise PersistenceError(f"failed migration {migration_id}: {exc}") from exc

    def reset_derived_tables(self, conn: sqlite3.Connection) -> None:
        for table in ("retrieval_fts", "retrieval_embeddings", "retrieval_chunks", "retrieval_entry_modes", "retrieval_entry_domain_tags", "retrieval_entries", "entry_artifacts", "entry_entities", "state_items", "amendments", "entry_revisions", "entries", "sessions", "entity_aliases", "entities", "artifacts"):
            conn.execute(f"DELETE FROM {table}")
