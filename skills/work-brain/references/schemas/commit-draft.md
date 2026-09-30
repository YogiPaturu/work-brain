WORK-BRAIN-SCHEMA-COMMIT-DRAFT v1

# CommitDraft

The model emits only semantic fields:

- `title`: non-empty string, at most 240 characters.
- `summary`: string, at most 4000 characters.
- `historical_occurrence`: `null` for normal sessions; an LLD1 occurrence for
  `backfill`.
- `domains`: lowercase tokens.
- `sections`: exactly the LLD1 entry section names; each statement has `text`,
  `basis` (`stated` or `inferred`), and existing `source_turns`.
- `state_changes`, `entity_candidates`, `artifact_candidates`, and
  `source_entry_refs`.

The runtime supplies IDs, timestamps, revisions, provenance, and persistence
metadata. The model must not emit those authoritative fields.
