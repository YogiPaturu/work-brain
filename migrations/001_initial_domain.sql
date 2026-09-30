CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    local_date TEXT NOT NULL,
    entry_id TEXT NOT NULL UNIQUE,
    source_path TEXT NOT NULL UNIQUE,
    model_ref TEXT,
    app_revision TEXT
);

CREATE INDEX IF NOT EXISTS sessions_by_local_date
    ON sessions(local_date, started_at);

CREATE TABLE IF NOT EXISTS entries (
    entry_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL UNIQUE REFERENCES sessions(session_id),
    current_revision INTEGER NOT NULL,
    title TEXT NOT NULL,
    provenance_kind TEXT NOT NULL,
    occurrence_start TEXT,
    occurrence_end TEXT,
    occurrence_precision TEXT NOT NULL,
    current_path TEXT NOT NULL,
    current_hash TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entry_revisions (
    entry_id TEXT NOT NULL REFERENCES entries(entry_id),
    revision INTEGER NOT NULL,
    commit_id TEXT NOT NULL UNIQUE,
    revision_reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    content_hash TEXT NOT NULL,
    PRIMARY KEY (entry_id, revision)
);

CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entity_aliases (
    entity_id TEXT NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    alias_norm TEXT NOT NULL,
    PRIMARY KEY (entity_id, alias_norm)
);

CREATE INDEX IF NOT EXISTS entity_alias_lookup ON entity_aliases(alias_norm);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    label TEXT NOT NULL,
    locator TEXT NOT NULL,
    external_id TEXT,
    path TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS artifacts_by_locator ON artifacts(locator);

CREATE TABLE IF NOT EXISTS entry_entities (
    entry_id TEXT NOT NULL REFERENCES entries(entry_id) ON DELETE CASCADE,
    entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    relation TEXT NOT NULL,
    PRIMARY KEY (entry_id, entity_id, relation)
);

CREATE TABLE IF NOT EXISTS entry_artifacts (
    entry_id TEXT NOT NULL REFERENCES entries(entry_id) ON DELETE CASCADE,
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    relation TEXT NOT NULL,
    PRIMARY KEY (entry_id, artifact_id, relation)
);

CREATE TABLE IF NOT EXISTS state_items (
    state_item_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    project_entity_id TEXT REFERENCES entities(entity_id),
    details TEXT,
    next_action TEXT,
    waiting_on TEXT,
    due_at TEXT,
    opened_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT,
    last_source_entry_id TEXT NOT NULL REFERENCES entries(entry_id)
);

CREATE INDEX IF NOT EXISTS state_items_by_status ON state_items(status, kind);
CREATE INDEX IF NOT EXISTS state_items_by_project ON state_items(project_entity_id, status);

CREATE TABLE IF NOT EXISTS amendments (
    amendment_id TEXT PRIMARY KEY,
    recorded_at TEXT NOT NULL,
    target_kind TEXT NOT NULL,
    target_id TEXT NOT NULL,
    source_session_id TEXT,
    path TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

