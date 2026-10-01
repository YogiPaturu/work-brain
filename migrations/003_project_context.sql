ALTER TABLE entries ADD COLUMN project_entity_id TEXT;
ALTER TABLE retrieval_entries ADD COLUMN project_entity_id TEXT;

CREATE INDEX IF NOT EXISTS entries_by_project
    ON entries(project_entity_id);
CREATE INDEX IF NOT EXISTS retrieval_entries_by_project
    ON retrieval_entries(project_entity_id, occurrence_start_ms);
