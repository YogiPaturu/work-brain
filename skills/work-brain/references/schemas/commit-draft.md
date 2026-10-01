WORK-BRAIN-SCHEMA-COMMIT-DRAFT v1

# CommitDraft

The model emits only semantic fields:

- `title`: non-empty string, at most 240 characters.
- `summary`: string, at most 4000 characters.
- `historical_occurrence`: `null` for normal sessions; a historical occurrence for
  `backfill`.
- `domains`: lowercase tokens.
- `sections`: exactly the supported entry section names; each statement has `text`,
  `basis` (`stated` or `inferred`), and one or more exact `source_turns` from the
  persisted raw conversation. Every statement must identify the raw turn numbers
  that support it; do not leave this list empty. Each statement must include at
  least one user-authored source turn; assistant-only or synthetic turns do not
  qualify as durable evidence.
- `state_changes`, `entity_candidates`, `artifact_candidates`, and
  `source_entry_refs`.

Each state change must also identify at least one supporting `source_turns` value,
including at least one user-authored turn.

Source turns must belong to the session being committed. Do not use source turns
from another session to manufacture a revision. If the evidence comes from a
different session, create a separate entry and use `source_entry_refs` only to
link the related prior entry.

The runtime supplies IDs, timestamps, revisions, provenance, and persistence
metadata. The model must not emit those authoritative fields.
