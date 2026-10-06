ALTER TABLE entities ADD COLUMN workspace_entity_id TEXT;

CREATE INDEX IF NOT EXISTS entities_by_kind_workspace
    ON entities(kind, workspace_entity_id, canonical_name);
