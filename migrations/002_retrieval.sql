CREATE TABLE IF NOT EXISTS retrieval_entries (
    entry_id TEXT PRIMARY KEY REFERENCES entries(entry_id) ON DELETE CASCADE,
    source_revision INTEGER NOT NULL,
    source_hash TEXT NOT NULL,
    dependency_hash TEXT NOT NULL,
    recipe_id TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    provenance_kind TEXT NOT NULL,
    occurrence_start_ms INTEGER,
    occurrence_end_ms INTEGER,
    occurrence_precision TEXT NOT NULL,
    occurrence_label TEXT,
    has_outcome INTEGER NOT NULL,
    has_open_questions INTEGER NOT NULL,
    indexed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS retrieval_entries_by_occurrence
    ON retrieval_entries(occurrence_start_ms, entry_id);
CREATE INDEX IF NOT EXISTS retrieval_entries_by_provenance
    ON retrieval_entries(provenance_kind, occurrence_start_ms);

CREATE TABLE IF NOT EXISTS retrieval_entry_modes (
    entry_id TEXT NOT NULL REFERENCES retrieval_entries(entry_id) ON DELETE CASCADE,
    mode TEXT NOT NULL,
    PRIMARY KEY (entry_id, mode)
);
CREATE INDEX IF NOT EXISTS retrieval_modes_lookup
    ON retrieval_entry_modes(mode, entry_id);

CREATE TABLE IF NOT EXISTS retrieval_entry_domains (
    entry_id TEXT NOT NULL REFERENCES retrieval_entries(entry_id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    PRIMARY KEY (entry_id, domain)
);
CREATE INDEX IF NOT EXISTS retrieval_domains_lookup
    ON retrieval_entry_domains(domain, entry_id);

CREATE TABLE IF NOT EXISTS retrieval_chunks (
    chunk_id TEXT PRIMARY KEY,
    entry_id TEXT NOT NULL REFERENCES retrieval_entries(entry_id) ON DELETE CASCADE,
    source_revision INTEGER NOT NULL,
    chunk_kind TEXT NOT NULL,
    section_key TEXT,
    ordinal INTEGER NOT NULL,
    text TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    UNIQUE (entry_id, source_revision, chunk_kind, section_key, ordinal)
);
CREATE INDEX IF NOT EXISTS retrieval_chunks_by_entry
    ON retrieval_chunks(entry_id, ordinal);

CREATE VIRTUAL TABLE IF NOT EXISTS retrieval_fts USING fts5(
    chunk_id UNINDEXED,
    entry_id UNINDEXED,
    title,
    body,
    metadata,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS retrieval_embeddings (
    chunk_id TEXT PRIMARY KEY REFERENCES retrieval_chunks(chunk_id) ON DELETE CASCADE,
    model_id TEXT NOT NULL,
    adapter_recipe TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    text_hash TEXT NOT NULL,
    vector BLOB NOT NULL,
    embedded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS retrieval_embeddings_by_model
    ON retrieval_embeddings(model_id, adapter_recipe);

CREATE TABLE IF NOT EXISTS retrieval_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
