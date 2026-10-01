ALTER TABLE entries ADD COLUMN workspace_entity_id TEXT;
ALTER TABLE retrieval_entries ADD COLUMN workspace_entity_id TEXT;

CREATE INDEX IF NOT EXISTS entries_by_workspace
    ON entries(workspace_entity_id);
CREATE INDEX IF NOT EXISTS retrieval_entries_by_workspace
    ON retrieval_entries(workspace_entity_id, occurrence_start_ms);
