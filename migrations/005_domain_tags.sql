ALTER TABLE retrieval_entry_domains RENAME TO retrieval_entry_domain_tags;
DROP INDEX IF EXISTS retrieval_domains_lookup;
ALTER TABLE retrieval_entry_domain_tags RENAME COLUMN domain TO domain_tag;
CREATE INDEX IF NOT EXISTS retrieval_domain_tags_lookup
    ON retrieval_entry_domain_tags(domain_tag, entry_id);
