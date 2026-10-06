WORK-BRAIN-SCHEMA-COMMIT-DRAFT v1

# CommitDraft

The model emits only semantic fields:

- `title`: non-empty string, at most 240 characters.
- `summary`: string, at most 4000 characters.
- `historical_occurrence`: `null` for normal sessions; a historical occurrence for
  `backfill`.
- `domain_tags`: optional list of lowercase hyphenated tags. There is no upper
  limit; include every materially useful subject area or capability supported
  by the conversation.
- `workspace`: required non-empty string naming the broad working context, such
  as `Ranq`, `Health Tech`, or `Work Brain`.
- `workspace_ref`: optional existing workspace entity ID returned by the
  read-only `resolve_context` operation. Never invent this ID.
- `project`: required non-empty string naming the specific effort, such as
  `Auth implementation` or `Billing Right Code`.
- `project_ref`: optional existing project entity ID returned by the
  read-only `resolve_context` operation. Never invent this ID.
- `sections`: exactly the supported entry section names; each statement has `text`,
  `basis` (`stated` or `inferred`), and one or more exact `source_turns` from the
  persisted raw conversation. Every statement must identify the raw turn numbers
  that support it; do not leave this list empty. Each statement must include at
  least one user-authored source turn; assistant-only or synthetic turns do not
  qualify as durable evidence.
- `state_changes`, `entity_candidates`, `artifact_candidates`, and
  `source_entry_refs`.

When a bounded conversation clearly continues an existing professional
Experience, `entity_candidates` may include its stable entity ID or an alias
resolved by the application. A new Experience may be proposed with
`{"kind":"experience","canonical_name":"..."}`; its relation defaults to
`experience`. Experience association is optional. If the relationship is
uncertain, omit the candidate and commit the SessionEntry normally. Never copy
an Experience summary into the entry as a substitute for supporting evidence.
For an existing Experience, prefer the explicit shape
`{"entity_id":"...","kind":"experience","relation":"experience"}`.
An Experience candidate must always use `relation: "experience"`; the
application rejects unrelated relations and rejects ambiguous catalog matches.

The context fields retain required plain names. When `resolve_context`
deterministically identifies an existing identity, preserve both its returned
canonical name and its returned entity ID:

```json
{
  "workspace": "Ranq",
  "workspace_ref": "WORKSPACE_ENTITY_ID",
  "project": "Authentication",
  "project_ref": "PROJECT_ENTITY_ID"
}
```

For historical candidates, emit a ref only after the conversation makes the
selection unambiguous; otherwise ask one concise clarification question. For
unresolved or genuinely new context, omit the ref and keep the existing
name-only behavior. The application validates refs against the authoritative
source catalog, checks their kind, and checks that each supplied name matches
the entity's canonical name or an existing alias. A project ref with workspace
ownership must also belong to the selected workspace; legacy unparented project
refs remain compatible without being mutated. A mismatch or unknown ref is
invalid; the application does not silently prefer the name or ID. When no ref
is supplied, project lookup is scoped to the selected workspace when possible;
projects owned by another workspace are not reused, and a new project is
created with that workspace owner when no eligible project exists.

Detailed assignment guidance and the extensible starter vocabulary are in
`WORK-BRAIN-DOMAIN-TAGS@1`, loaded alongside this schema during commit
generation.

Each state change must also identify at least one supporting `source_turns` value,
including at least one user-authored turn.

Source turns must belong to the session being committed. Do not use source turns
from another session to manufacture a revision. If the evidence comes from a
different session, create a separate entry and use `source_entry_refs` only to
link the related prior entry.

The runtime supplies session, entry, commit, revision, timestamp, provenance,
and persistence metadata. The model must not emit those runtime-owned or
persisted fields, including `workspace_entity_id` and `project_entity_id`.
`workspace_ref` and `project_ref` are the narrow exception: they may copy an
already-existing entity ID returned by Work Brain; they are not IDs invented or
allocated by the model.

## Context classification before emission

Before emitting a CommitDraft, classify the evidence:

1. Prefer an explicit workspace or project name stated by the user.
2. Otherwise infer it from the bounded conversation, the current work item,
   an active communication profile, or supplied retrieved context.
3. Reuse the same classification when the session is clearly continuing one
   work item; do not create a new near-duplicate name.
4. If the workspace or project is materially ambiguous, ask one concise
   clarification question before committing. Do not guess a catalog name.
5. When a deterministic existing identity was returned by `resolve_context`,
   emit its canonical name and matching `workspace_ref` or `project_ref`.
   Otherwise omit the ref. Always emit both name keys as non-empty strings;
   missing, empty, or null values are invalid; ask for the missing
   classification before committing.

The application may create or reuse internal catalog entities from these names.
Except for the narrow trusted `workspace_ref`/`project_ref` references above,
the model does not emit entity IDs, kinds, relations, or catalog metadata.
