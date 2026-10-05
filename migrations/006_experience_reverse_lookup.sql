CREATE INDEX IF NOT EXISTS entry_entities_by_entity_relation
    ON entry_entities(entity_id, relation, entry_id);
