# Work Brain — LLD-01: Core Domain, Vault, and Persistence Contract

**Document ID:** `WORK-BRAIN-LLD-001`
**Version:** `2`
**Status:** Draft for sibling cross-review
**Date:** `2026-09-30`
**Parent HLD:** `WORK-BRAIN-HLD-001` v2
**Implementation posture:** Prescriptive with bounded local discretion

## 1. Executive Summary

This LLD defines the durable local data contract for the Work Brain. It translates the parent HLD's source-of-truth, journaling, privacy, and rebuildability decisions into concrete filesystem and SQLite persistence semantics.

The central persistence rule is:

```text
Raw session source + explicit user amendments
                    ↓
       Structured entry revisions
                    ↓
     Journal / WorkState projections
                    ↓
       SQLite / FTS / vector indexes
```

Raw conversational source is preserved verbatim and incrementally. Structured interpretations are revisioned rather than silently overwritten. Daily journals and current work state are materialized projections that can be regenerated. SQLite is a local structured projection and integrity/indexing surface; it is never the sole copy of professional evidence.

This LLD deliberately does not define agent probing behavior, model routing, FTS/vector chunking, hybrid search ordering/pagination, interview-question behavior, or CLI command syntax. Those responsibilities belong to LLD-02, LLD-03, LLD-04, or the thin local interface adapter.

## 2. Effective Source Set

This LLD is governed by:

1. `WORK-BRAIN-HLD-001` v2 — Work Brain High-Level Design.
2. The approved design decisions in the discovery conversation that produced that HLD.
3. The Ranq Low-Level Design Discovery and Authoring SOP, used as the authoring discipline for this LLD.

There is no implementation repository yet whose source body changes this LLD. Repository inspection therefore remains an implementation prerequisite rather than design evidence.

## 3. HLD Decisions Implemented Here

This LLD implements the following settled HLD decisions:

- local-first, single-user v1;
- separate public application repository and private professional vault;
- raw conversations preserved verbatim;
- session/conversation is the ingestion and commit unit;
- day is the journal aggregation unit;
- end-of-day closure is optional for durability;
- structured entries are durable interpretations over raw source;
- current work state and daily journals are rebuildable projections;
- explicit user corrections remain distinguishable from original source;
- meaningful belief evolution must not be flattened into hindsight;
- contemporaneous and reconstructed evidence must be distinguishable;
- SQLite metadata is local and rebuildable;
- retrieval-specific FTS/vector indexes are derived, not authoritative;

The source writer and derived maintenance have separate boundaries. Source
capture uses `initialize_source_store()` and `.vault.write.lock`; it does not
open or migrate the rebuildable SQLite projection. Application-level commit
coordination may refresh journals/state/SQLite after source publication, but
the source `Vault` does not invoke retrieval. Retrieval indexing is an
application maintenance concern protected by `.index.write.lock`.
- no background service is required for correctness;
- private user data must not be required in the public repository.

## 4. HLD Decisions Outside This LLD

The following are explicitly outside this LLD:

- session lifecycle states and runtime orchestration — LLD-02;
- Skill/SOP loading and model/tool behavior — LLD-02;
- exact retrieval chunking, FTS5 schema, embeddings, vector backend, and hybrid fusion — LLD-03;
- exact CLI commands, Yap/stdin behavior, and terminal rendering — thin local adapter/implementer discretion;
- interview question-bank behavior, Career practice, and durable career-candidate marks — LLD-04;
- communication sanitization and shareability behavior — LLD-02;
- external GitHub/Google/other connectors — future adapter/LLD when required.

This LLD stores metadata supplied by those components where provenance requires it, but does not define their behavioral semantics.

## 5. Design Decisions, Assumptions, Prerequisites, and Discretion

### 5.1 Resolved design decisions

- Durable source files use UTF-8 JSON/JSONL plus generated Markdown journals.
- Raw conversational turns are append-only within a committed session source.
- Each committed session has one stable `entry_id` and one or more immutable structured entry revisions.
- A new interpretation or correction creates a new entry revision; it never silently rewrites a published revision.
- Explicit user amendments are durable source records separate from model reinterpretation.
- UUIDv7 is the stable identity format for sessions, turns, entries, commits, amendments, entities, artifacts, and state items.
- Current state is represented as a small set of typed state items and is rebuilt from current structured-entry revisions plus explicit amendments.
- Daily journal Markdown is generated from current entry revisions for a calendar day and is not manually authoritative.
- SQLite contains structured metadata and materialized state but is fully rebuildable from vault files.
- Durable source is written before any derived projection/index is updated.
- Derived updates may fail without invalidating a successfully persisted source commit.

### 5.2 Repository assumptions

- The implementation will have access to atomic rename/replace semantics within one filesystem volume.
- SQLite is available locally.
- The implementation can request a filesystem flush/fsync or equivalent durability primitive on the target OS.

### 5.3 Implementation prerequisites

Before coding begins:

- select the implementation language/runtime;
- confirm its UUIDv7 support or select one maintained UUIDv7 library;
- confirm the SQLite build and driver behavior on the target laptop;
- confirm same-directory atomic replacement behavior on the supported OS;
- decide the exact vault-root configuration mechanism in the local interface/configuration adapter;
- cross-review the session/commit fields with LLD-02;
- cross-review the entry identity/source hydration fields with LLD-03.

### 5.4 Implementer discretion

The implementer may choose:

- internal class/module names;
- JSON serialization library;
- JSON pretty-print indentation;
- exact temporary-file suffix;
- private helper decomposition;
- whether SQLite migrations are executed by a small in-house runner or a lightweight migration library, provided the migration contract in this LLD is preserved.

## 6. Core Domain Invariants

### 6.1 Authority hierarchy

The authoritative persistence hierarchy is:

```text
1. Raw conversational turns and explicit user amendments
2. Current structured entry revision derived from those sources
3. Catalog records explicitly created/confirmed by the user or application
4. Generated daily journal and current WorkState
5. SQLite metadata/search indexes and other derived indexes
```

Lower layers MUST NOT silently override higher layers.

### 6.2 Raw source immutability

Once a raw turn has been durably appended, its content MUST NOT be silently edited. If a user later corrects it, the original remains and a correction/amendment is added.

An explicit destructive delete requested by the user is allowed and is not considered a silent rewrite.

### 6.3 Structured interpretation revisions

A structured entry revision is immutable after publication. Re-extraction, improved interpretation, or a user correction creates the next revision for the same stable `entry_id`.

### 6.4 No hindsight overwrite

A later revision may clarify an earlier belief, but MUST preserve the fact that the earlier belief existed when that distinction is materially relevant.

### 6.5 Rebuildability

Deleting the following MUST NOT destroy authoritative professional evidence:

- `journal/`;
- `state/`;
- `index/` including the SQLite database.

The application MUST be able to rebuild them from durable source/catalog records.

### 6.6 One current interpretation

For each `entry_id`, exactly one revision is current. Older revisions remain historical and must be retrievable for audit/debugging but are excluded from normal journal/state/retrieval materialization unless explicitly requested.

### 6.7 Explicit provenance

Every structured entry MUST identify its source session and provenance kind. Historical backfill MUST NOT be indistinguishable from contemporaneous capture.

## 7. Stable Identity and Time Contracts

### 7.1 Identifier format

All durable domain identities use canonical lowercase UUIDv7 strings.

Examples:

```text
0199aa9c-40e1-7b22-8f83-6dc0e6292c2c
0199aa9d-0aa9-7ac2-8b6a-761725ae23cb
```

Separate typed fields identify what the UUID represents; type prefixes are not part of the identifier value.

UUIDv7 is selected because the current requirements need:

- decentralized ID generation;
- extremely low collision risk;
- stable cross-file references;
- chronological locality useful for human-scale local storage and debugging.

### 7.2 Timestamp format

Exact capture timestamps MUST use RFC 3339 with an explicit UTC offset, preserving the local offset at capture time.

Example:

```text
2026-09-30T17:41:23.482+01:00
```

The application MUST NOT persist naive local timestamps.

### 7.3 Calendar-day grouping

A live session belongs to the calendar day containing its `started_at` timestamp's local date.

A session that crosses midnight remains owned by its start date for filesystem/session identity, while individual turns retain their exact timestamps. The local interface may choose to prompt the user to start a new session after midnight, but persistence correctness does not depend on that behavior.

### 7.4 Historical occurrence time

Structured entries support approximate historical occurrence using:

```json
{
  "start": "2023-07-01",
  "end": "2023-09-30",
  "precision": "quarter",
  "label": "2023 Q3"
}
```

Allowed `precision` values are:

```text
instant | day | month | quarter | year | range | unknown
```

`start` and `end` MAY be null only when precision is `unknown`. `label` is optional display text and is not authoritative over `start`/`end`.

## 8. Private Vault Topology

The v1 private vault uses this structure:

```text
career-vault/
├── sessions/
│   └── YYYY/
│       └── MM/
│           └── DD/
│               └── <session_id>/
│                   ├── session.json
│                   ├── turns.jsonl
│                   └── entries/
│                       ├── 0001.json
│                       ├── 0002.json
│                       └── ...
├── amendments/
│   └── YYYY/
│       └── MM/
│           └── DD/
│               └── <amendment_id>.json
├── catalog/
│   ├── entities/
│   │   └── <entity_id>.json
│   └── artifacts/
│       └── <artifact_id>.json
├── journal/
│   └── YYYY/
│       └── MM/
│           └── YYYY-MM-DD.md
├── state/
│   └── current.json
├── context/
├── questions/
├── career/
│   └── marks.jsonl          # LLD-04-owned user preference source
├── artifacts/
└── index/
    └── work-brain.sqlite
```

Authority by directory:

| Path | Authority |
|---|---|
| `sessions/*/turns.jsonl` | durable raw source |
| `sessions/*/entries/*.json` | durable structured interpretation history |
| `amendments/` | durable explicit correction source |
| `catalog/` | durable stable entity/artifact identity metadata |
| `journal/` | rebuildable human-readable projection |
| `state/` | rebuildable operational projection |
| `index/` | rebuildable structured/search projection |
| `context/`, `questions/`, `artifacts/` | user-provided durable private inputs/reference material |
| `career/marks.jsonl` | LLD-04-owned durable user preference metadata; not professional-evidence authority |

No private vault path may be required inside the public Git repository. Sibling features MAY own additional clearly named vault paths when the parent HLD gives them a current durable-user-state requirement; such files MUST NOT silently alter the authority of raw conversations, SessionEntry revisions, or amendments.

## 9. Session Source Contract

### 9.1 `session.json`

Each session directory contains one current metadata snapshot:

```json
{
  "session_id": "0199aa9c-40e1-7b22-8f83-6dc0e6292c2c",
  "started_at": "2026-09-30T10:42:03.122+01:00",
  "ended_at": "2026-09-30T11:08:41.004+01:00",
  "local_date": "2026-09-30",
  "entry_id": "0199aa9d-0aa9-7ac2-8b6a-761725ae23cb",
  "modes": ["think"],
  "domain_tags": ["engineering"],
  "runtime": {
    "model": "<runtime supplied model identifier>",
    "skill": "work-brain",
    "sops": ["core-conversation@1", "think@1", "probe:engineering@1"],
    "app_revision": "<optional git revision>"
  }
}
```

Rules:

- `session_id`, `started_at`, `local_date`, and `entry_id` are required once a session is initialized.
- `ended_at` is null until the structured entry has been durably published; the runtime finalizes the session snapshot after entry publication so a crash cannot leave a closed-looking session with no structured entry.
- `modes` and `domain_tags` are normalized lowercase string tokens, not closed enums. This allows later modes such as `teach` without changing the persistence schema.
- `runtime.sops` stores stable instruction-resource identities in `resource-id@version` form; probe resources MAY use a namespaced identifier such as `probe:engineering@1`.
- LLD-02 owns the meaning and selection of `modes`, `domain_tags`, model identifiers, and SOP references.
- `runtime` fields are provenance/debugging metadata; their absence MUST NOT make professional evidence invalid.
- `session.json` is a mutable snapshot and MUST be updated by atomic replacement.

### 9.2 `turns.jsonl`

`turns.jsonl` is the append-only raw conversational source.

Each line is one JSON object:

```json
{"turn_id":"0199aaa0-3d97-75ef-8566-b58a2ff95468","sequence":1,"recorded_at":"2026-09-30T10:42:11.101+01:00","role":"user","content":"I'm thinking about moving submission generation async."}
{"turn_id":"0199aaa0-f067-716e-aec6-3e526cb5809d","sequence":2,"recorded_at":"2026-09-30T10:42:18.442+01:00","role":"assistant","content":"What problem are you actually trying to solve by making it asynchronous?"}
```

Contract:

- `turn_id` is UUIDv7 and globally unique.
- `sequence` begins at `1` and increments by exactly `1` within a session.
- `role` is `user` or `assistant` in v1.
- `content` is the verbatim textual message. Whitespace MUST NOT be normalized after capture.
- `recorded_at` is the time the application durably accepts the turn.
- A completed turn is appended before the next conversational step is considered durable.
- The implementation MUST flush the appended record to the OS and request durable file synchronization before acknowledging persistence when practical on the platform.
- A duplicate retry with the same `turn_id`, `sequence`, and content is idempotent and MUST NOT create a second record.
- Reuse of a `turn_id` with different content or sequence is corruption and MUST fail.
- A sequence gap or non-tail duplicate is corruption and MUST fail.

### 9.3 Crash recovery for JSONL

A crash may leave one incomplete trailing JSON record. Recovery MUST:

1. parse records from the start;
2. accept every complete valid record in sequence;
3. discard/truncate only an incomplete final record;
4. fail integrity validation if malformed JSON or sequencing occurs before the final record.

The application MUST NOT silently skip arbitrary malformed middle records.

### 9.4 Raw transcript scope

The raw transcript contract guarantees verbatim user/assistant conversational turns. It does not require preservation of hidden model reasoning or full tool payloads.

Stable references to retrieved prior evidence or artifacts that materially support the committed structured entry belong in the entry's `source_refs`/entity/artifact relationships. LLD-02 may persist additional runtime traces, but they are not required for LLD-01 correctness.

## 10. Structured Session Entry Contract

### 10.1 Entry identity and revision model

Each session has one stable `entry_id`. The first structured commit creates revision `1`. Later reinterpretation or explicit correction creates revision `2`, `3`, and so on.

Each revision is stored as:

```text
sessions/YYYY/MM/DD/<session_id>/entries/<revision padded to 4 digits>.json
```

Examples:

```text
entries/0001.json
entries/0002.json
```

Published revision files are immutable.

### 10.2 SessionEntry shape

A structured entry revision has this v1 shape:

```json
{
  "entry_id": "0199aa9d-0aa9-7ac2-8b6a-761725ae23cb",
  "session_id": "0199aa9c-40e1-7b22-8f83-6dc0e6292c2c",
  "revision": 1,
  "commit_id": "0199aae0-e6e9-711c-8924-c0eaee75bdb4",
  "created_at": "2026-09-30T11:08:43.100+01:00",
  "supersedes_revision": null,
  "revision_reason": "initial_commit",
  "provenance_kind": "contemporaneous",
  "title": "Thinking through asynchronous submission generation",
  "summary": "Considered moving submission generation async; clarified that failure isolation, not latency alone, is the primary concern and deferred the change pending more evidence.",
  "occurrence": {
    "start": "2026-09-30T10:42:03.122+01:00",
    "end": "2026-09-30T11:08:41.004+01:00",
    "precision": "instant",
    "label": null
  },
  "modes": ["think", "operate"],
  "domain_tags": ["engineering"],
  "workspace_entity_id": "0199aaf1-c215-75ec-b2df-76f43ef7ae34",
  "project_entity_id": "0199aaf1-c215-75ec-b2df-76f43ef7ae33",
  "sections": {
    "context": [],
    "observations": [],
    "significance": [],
    "contribution": [],
    "reasoning": [],
    "evidence": [],
    "alternatives_tradeoffs": [],
    "decisions_actions": [],
    "expectations": [],
    "outcomes": [],
    "learning": [],
    "open_questions": []
  },
  "state_mutations": [],
  "entity_refs": [],
  "artifact_refs": [],
  "source_refs": []
}
```

### 10.3 Revision reasons

Allowed `revision_reason` values in v1 are:

```text
initial_commit
reextract
user_correction
metadata_backfill
```

These values are required now because the application must distinguish model reinterpretation from user-supplied factual correction.

### 10.4 Provenance kinds

Allowed `provenance_kind` values are:

```text
contemporaneous
reconstructed
```

A historical backfill session MUST use `reconstructed` even when captured today.

If one conversation genuinely mixes unrelated contemporaneous and reconstructed experiences, LLD-02 SHOULD split the durable commit rather than weaken this provenance distinction. LLD-02 and LLD-01 MUST cross-review this constraint before implementation.

### 10.5 Statement shape

Every element inside `sections.*` is a `Statement`:

```json
{
  "text": "The primary concern is isolating failures between processing stages, not request latency alone.",
  "basis": "stated",
  "source_turns": [5, 6]
}
```

Allowed `basis` values are:

```text
stated
inferred
```

Rules:

- `stated` means the statement is directly supported by the user's raw turns or a supplied artifact represented by an artifact reference.
- `inferred` means the agent synthesized an interpretation not directly stated as fact by the user.
- `source_turns` contains one or more turn sequence numbers when the support is in the transcript.
- An artifact-supported statement MAY have an empty `source_turns` only when a corresponding `artifact_ref` is present and the statement is traceable to that artifact by the runtime.
- Inferred statements MUST remain visibly distinguishable and MUST NOT silently become user-confirmed facts in later Career or communication outputs.
- The model SHOULD prefer omission over manufacturing a fact that is unsupported by transcript or artifacts.

This statement-level provenance is intentionally small: it provides enough evidence traceability to audit weak-model extraction without requiring the model to emit a large citation graph.

### 10.6 Meaning of structured sections

| Section | Meaning |
|---|---|
| `context` | problem/situation and relevant background |
| `observations` | concrete events, facts, measurements, or user-reported observations |
| `significance` | why the situation matters, including stakes/goals/consequences |
| `contribution` | what the user personally did, owned, influenced, or produced |
| `reasoning` | beliefs, assumptions, hypotheses, uncertainty, or interpretation |
| `evidence` | evidence that supports/challenges the user's reasoning |
| `alternatives_tradeoffs` | credible alternatives and material trade-offs |
| `decisions_actions` | decisions/actions plus rationale where known |
| `expectations` | predictions or expected consequences made before the outcome is known |
| `outcomes` | actual results, impact, metrics, or explicitly unknown/pending results |
| `learning` | surprise, changed belief, mistake, lesson, or broader learning |
| `open_questions` | unresolved uncertainty that remains worth carrying forward |

No section is required to be non-empty. The schema's breadth is capacity, not a form-completion requirement.

### 10.7 Belief evolution

When the conversation includes a meaningful change of mind, the entry SHOULD contain separate statements that preserve chronology rather than rewriting the final view as if it was always held.

Example:

```json
{
  "reasoning": [
    {"text":"Initially believed latency was the main reason to move processing async.","basis":"stated","source_turns":[1,3]},
    {"text":"After discussion, concluded failure isolation is the stronger reason.","basis":"stated","source_turns":[5,6]}
  ],
  "learning": [
    {"text":"The original framing over-weighted latency and under-weighted partial-failure behavior.","basis":"inferred","source_turns":[3,5,6]}
  ]
}
```

### 10.8 Source references

`source_refs` records durable non-transcript source relationships used to interpret the entry.

V1 supports:

```json
{"kind":"amendment","id":"<amendment_id>"}
{"kind":"entry","id":"<entry_id>","revision":2}
```

Artifact evidence uses `artifact_refs`, not a generic source reference.

## 11. Entity Catalog

### 11.1 Entity purpose

Entities provide stable identity and aliases for recurring professional concepts whose names may vary across sessions.

V1 entity kinds are:

```text
workspace
project
person
organization
customer
system
topic
```

The entity-kind set is an application vocabulary rather than a persistence-version boundary. Adding a future kind requires validator/test updates but not a source-file migration if no existing semantics change.

### 11.2 Entity shape

`catalog/entities/<entity_id>.json`:

```json
{
  "entity_id": "0199aaf1-c215-75ec-b2df-76f43ef7ae33",
  "kind": "project",
  "canonical_name": "Ranq",
  "aliases": ["ranq"],
  "description": "Current founder venture",
  "created_at": "2026-09-30T09:00:00+01:00",
  "updated_at": "2026-09-30T09:00:00+01:00"
}
```

Rules:

- `entity_id`, `kind`, `canonical_name`, `created_at`, and `updated_at` are required.
- Aliases are case-insensitive for lookup but original display casing is preserved. The application computes `alias_norm` using Unicode NFKC normalization followed by Unicode case-folding; SQLite's built-in ASCII-oriented `NOCASE` collation is not the identity rule.
- Renaming an entity keeps the same `entity_id`; the previous canonical name SHOULD be retained as an alias unless the user explicitly says it was incorrect rather than renamed.
- Two semantically distinct entities MUST NOT be merged merely because their names are similar.
- Entity files are current durable identity metadata and are atomically replaced on update.

### 11.3 Entry entity reference

```json
{
  "entity_id": "0199aaf1-c215-75ec-b2df-76f43ef7ae33",
  "relation": "project"
}
```

`relation` is a normalized lowercase token and is not a closed enum so future projections can add useful relationship labels without source migrations.

An entry may carry one first-class `workspace_entity_id` and one
`project_entity_id`. A workspace is a broad working context such as `Ranq` or
`Brother-in-law health tech`; a project is a specific effort such as `Auth
implementation` or `Billing Right Code`. `domain_tags` remain a multi-valued tag
set for cross-cutting concerns such as `auth`, `architecture`, and `billing`.
Workspace and project scope are indexed separately from ordinary entity
references so communication profiles can retrieve experiences across multiple
dates without relying on a daily window.

## 12. Artifact Reference Catalog

### 12.1 Purpose

An `ArtifactReference` points from professional evidence to durable external or local work artifacts without copying their entire contents into the journal.

### 12.2 Artifact shape

`catalog/artifacts/<artifact_id>.json`:

```json
{
  "artifact_id": "0199aaf9-fb09-738f-bb50-97883d0374ea",
  "kind": "github_pr",
  "label": "Submission parsing refactor",
  "locator": "https://github.com/example/repo/pull/123",
  "external_id": "123",
  "notes": null,
  "created_at": "2026-09-30T11:05:00+01:00",
  "updated_at": "2026-09-30T11:05:00+01:00"
}
```

Rules:

- `kind` is an open normalized token such as `github_pr`, `git_commit`, `document`, `sheet`, `issue`, `url`, or `local_file`.
- `locator` is opaque to the domain. Connector-specific interpretation belongs to future connector adapters/LLDs when those integrations become current requirements.
- Credentials or secrets MUST NOT be embedded in `locator`.
- Artifact content is not assumed durable merely because the reference is durable; future connectors may snapshot artifacts separately when required.

### 12.3 Entry artifact reference

```json
{
  "artifact_id": "0199aaf9-fb09-738f-bb50-97883d0374ea",
  "relation": "supports"
}
```

## 13. Explicit User Amendments

### 13.1 Why amendments exist

A raw transcript can be faithfully preserved and still contain a factual mistake, transcription error, or later correction. An explicit user amendment records that new source evidence without rewriting the original transcript.

### 13.2 Amendment shape

`amendments/YYYY/MM/DD/<amendment_id>.json`:

```json
{
  "amendment_id": "0199ab0e-fd62-79e8-aa49-0952936b595e",
  "recorded_at": "2026-10-02T09:12:00+01:00",
  "target": {
    "kind": "entry",
    "id": "0199aa9d-0aa9-7ac2-8b6a-761725ae23cb"
  },
  "statement": "The improvement was 12%, not 20%.",
  "source_session_id": "0199ab0d-341a-75dd-bb0d-cf1432539281"
}
```

Rules:

- The amendment preserves the user's correction verbatim enough to understand the change.
- The amendment is immutable after creation.
- Applying an amendment to a structured entry creates a new entry revision with `revision_reason = user_correction` and an `amendment` source reference.
- The prior structured revision remains historical.
- An amendment MAY target an `entry`, `entity`, or `artifact` in v1.
- Work-state changes are corrected through a new session/entry/state mutation rather than mutating old state history.

## 14. WorkState and State Mutation Contract

### 14.1 Purpose

`WorkState` is a lightweight personal operational projection, not a full project-management database.

It exists to answer questions such as:

- what is active;
- what is blocked or waiting;
- what did I commit to;
- what remains unresolved;
- what is the next action;
- what project state should I resume from.

### 14.2 State item kinds

V1 state-item kinds are:

```text
task
open_loop
commitment
project_state
```

### 14.3 State status

V1 status values are:

```text
active
waiting
done
dropped
```

`done` means resolved/completed for any state-item kind.

### 14.4 StateItem shape

The materialized current-state shape is:

```json
{
  "state_item_id": "0199ab1a-09b6-76f5-9576-44ca7ac2bc55",
  "kind": "task",
  "title": "Run representative-query ranking experiment",
  "status": "active",
  "project_entity_id": "0199aaf1-c215-75ec-b2df-76f43ef7ae33",
  "details": null,
  "next_action": "Run the evaluation against the representative query set",
  "waiting_on": null,
  "due_at": null,
  "opened_at": "2026-09-30T09:12:00+01:00",
  "updated_at": "2026-09-30T11:10:00+01:00",
  "closed_at": null,
  "last_source_entry_id": "0199aa9d-0aa9-7ac2-8b6a-761725ae23cb"
}
```

No priority score, story points, sprint, assignee, or other project-management fields exist in v1 because no current requirement needs them.

### 14.5 StateMutation shape

A persisted entry contains resolved state mutations:

```json
{
  "mutation_id": "0199ab1a-1ee2-7daf-952a-84473cc6f725",
  "operation": "create",
  "state_item_id": "0199ab1a-09b6-76f5-9576-44ca7ac2bc55",
  "kind": "task",
  "fields": {
    "title": "Run representative-query ranking experiment",
    "status": "active",
    "project_entity_id": "0199aaf1-c215-75ec-b2df-76f43ef7ae33",
    "next_action": "Run the evaluation against the representative query set"
  },
  "source_turns": [7, 8]
}
```

Allowed operations are:

```text
create
update
close
reopen
```

Rules:

- Persisted mutations MUST already contain the final stable `state_item_id`; temporary model-local identifiers MUST NOT leak into durable storage.
- `create` fails if the item already exists unless the operation is an idempotent retry of the same commit.
- `update` fails if the item does not exist.
- `close` sets status to `done` unless an explicit `dropped` status is supplied.
- `reopen` sets status to `active` unless an explicit `waiting` status is supplied.
- Fields not supplied by an update remain unchanged.
- `mutation_id` is stable for the committed revision and allows diagnostics/audit; normal state rebuild is driven by current entry revisions, not by a separate mutable mutation log.

### 14.6 WorkState rebuild

`state/current.json` is generated by:

1. selecting the current revision of every structured entry;
2. ordering entries by `created_at`, then `entry_id` as a deterministic tie-breaker;
3. applying each entry's state mutations in stored order;
4. applying no historical superseded revision;
5. writing the resulting current item set atomically.

For a normal new entry, the implementation MAY apply mutations incrementally.

Whenever an older entry becomes superseded by a new revision whose state mutations differ, the implementation MUST rebuild WorkState from current entry revisions rather than attempting an unsafe inverse patch.

At expected personal scale, a full state rebuild is intentionally preferred over complex incremental reconciliation.

## 15. Daily Journal Materialization

### 15.1 Journal authority

`journal/YYYY/MM/YYYY-MM-DD.md` is a human-readable projection. It is not authoritative and SHOULD NOT be manually edited.

User-visible corrections MUST go through a new session/amendment and then regenerate the journal.

### 15.2 Journal source set

A day's journal is rendered from the current revisions of entries whose owning session `local_date` matches the journal date.

Entries are ordered by session `started_at`, then `entry_id`.

### 15.3 Journal rendering contract

The journal uses this stable high-level shape:

```markdown
# 2026-09-30

## 09:10 — Morning planning
<!-- entry_id: <uuid>; revision: 1 -->

### Summary
...

### Context
...

### Decisions / actions
...

### Current state / next
...

## 10:42 — Thinking through asynchronous submission generation
<!-- entry_id: <uuid>; revision: 2 -->

### Summary
...

### Reasoning
...

### Alternatives / trade-offs
...

### Decisions / actions
...

### Learning
...
```

Rules:

- Only non-empty sections render.
- `Summary` renders when present.
- Statement lists render as Markdown bullets.
- Inferred statements SHOULD be visibly marked, for example `[inferred]`, so the journal does not present them as equivalent to user-stated facts.
- Entity and artifact links/labels MAY render where useful.
- State mutations SHOULD be rendered in plain language rather than raw JSON.
- Runtime/model metadata does not render by default.
- A close-day conversation is simply another session entry ordered chronologically; it does not own or finalize the journal file.

### 15.4 Incremental updates

After each successful session commit, the application SHOULD regenerate only the affected calendar day's journal.

If an older revision/amendment changes a different day's entry, only that historical day's journal needs regeneration.

## 16. Commit and Durability Ordering

### 16.1 Commit idempotency

Every structured commit has a `commit_id` generated before durable publication.

`commit_id` is unique across the vault.

A retry using the same `commit_id` MUST return the already-created entry revision and MUST NOT create another revision.

A re-extraction or corrected interpretation is a new logical commit and MUST use a new `commit_id`.

Resolver-published entries may also carry an optional `source_fingerprint`.
This is a runtime-owned idempotency marker derived from the bounded draft and
workflow; it is persisted on the immutable entry so a retry remains safe even
if the mutable session lifecycle snapshot could not be updated. It is not a
CommitDraft field and agents MUST NOT supply it.

### 16.2 Source-first ordering

The required publication order is:

```text
1. Ensure all raw turns are durable.
2. Validate the structured entry payload.
3. Resolve stable IDs for new entities/artifacts/state items.
4. Write the immutable entry revision to a temp file.
5. fsync the temp file.
6. Atomically rename the revision into place.
7. fsync the parent directory where supported.
8. Update persistence-owned SQLite metadata in one transaction.
9. Regenerate affected WorkState if required.
10. Regenerate affected daily journal.
11. Invoke retrieval/index updates owned by LLD-03.
```

If steps 8-11 fail after step 7, the structured source commit remains valid. Repair/reindex MUST reconcile derived state from source files.

### 16.3 Atomic replacement

Mutable snapshots (`session.json`, catalog files, `state/current.json`, daily journal files) MUST be written by:

```text
write same-directory temp file
→ flush/fsync
→ atomic replace/rename target
→ fsync containing directory where supported
```

In-place truncation/rewrite is not permitted for these files.

## 17. SQLite Persistence-Owned Schema

SQLite is rebuildable. The source files above remain authoritative.

LLD-01 owns only the tables required to locate domain objects, preserve current-revision metadata, support exact domain relationships, materialize WorkState, and record applied DB migrations.

LLD-03 owns FTS, vector, chunk, and retrieval-specific denormalized tables/indexes.

### 17.1 `sessions`

```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    local_date TEXT NOT NULL,
    entry_id TEXT NOT NULL UNIQUE,
    source_path TEXT NOT NULL UNIQUE,
    model_ref TEXT,
    app_revision TEXT
);

CREATE INDEX sessions_by_local_date
    ON sessions(local_date, started_at);
```

`modes`, `domain_tags`, and SOP refs remain in `session.json`; LLD-03 MAY index them for retrieval if required.

### 17.2 `entries`

```sql
CREATE TABLE entries (
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
    updated_at TEXT NOT NULL,
    project_entity_id TEXT,
    workspace_entity_id TEXT
);
```

### 17.3 `entry_revisions`

```sql
CREATE TABLE entry_revisions (
    entry_id TEXT NOT NULL REFERENCES entries(entry_id),
    revision INTEGER NOT NULL,
    commit_id TEXT NOT NULL UNIQUE,
    revision_reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    content_hash TEXT NOT NULL,
    PRIMARY KEY (entry_id, revision)
);
```

### 17.4 `entities`

```sql
CREATE TABLE entities (
    entity_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL
);

CREATE TABLE entity_aliases (
    entity_id TEXT NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    alias_norm TEXT NOT NULL,
    PRIMARY KEY (entity_id, alias_norm)
);

CREATE INDEX entity_alias_lookup
    ON entity_aliases(alias_norm);
```

### 17.5 `artifacts`

```sql
CREATE TABLE artifacts (
    artifact_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    label TEXT NOT NULL,
    locator TEXT NOT NULL,
    external_id TEXT,
    path TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL
);

CREATE INDEX artifacts_by_locator
    ON artifacts(locator);
```

The locator index supports deduplication lookup; locator uniqueness is NOT globally enforced because distinct logical artifact records may intentionally point at the same broader document with different semantics later.

### 17.6 Entry relationships

```sql
CREATE TABLE entry_entities (
    entry_id TEXT NOT NULL REFERENCES entries(entry_id) ON DELETE CASCADE,
    entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    relation TEXT NOT NULL,
    PRIMARY KEY (entry_id, entity_id, relation)
);

CREATE TABLE entry_artifacts (
    entry_id TEXT NOT NULL REFERENCES entries(entry_id) ON DELETE CASCADE,
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    relation TEXT NOT NULL,
    PRIMARY KEY (entry_id, artifact_id, relation)
);
```

These tables represent the current entry revision only and are rebuilt/replaced when the current revision changes.

### 17.7 Materialized `state_items`

```sql
CREATE TABLE state_items (
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

CREATE INDEX state_items_by_status
    ON state_items(status, kind);

CREATE INDEX state_items_by_project
    ON state_items(project_entity_id, status);
```

This table is a projection and may be dropped/rebuilt.

### 17.8 `amendments`

```sql
CREATE TABLE amendments (
    amendment_id TEXT PRIMARY KEY,
    recorded_at TEXT NOT NULL,
    target_kind TEXT NOT NULL,
    target_id TEXT NOT NULL,
    source_session_id TEXT,
    path TEXT NOT NULL UNIQUE
);
```

### 17.9 `schema_migrations`

```sql
CREATE TABLE schema_migrations (
    migration_id TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
```

Migration IDs correspond to checked-in ordered migration files, for example:

```text
001_initial_domain.sql
002_add_<real_requirement>.sql
```

No source JSON `schemaVersion` field exists in v1. A file-format version discriminator MUST be introduced only when actual compatibility/migration behavior requires one.

## 17.10 Derived-index dependency invalidation hook

Entity/artifact catalog metadata such as canonical name, alias, label, or searchable locator text may be denormalized into LLD-03 retrieval chunks/cards. When a catalog mutation changes searchable metadata, the persistence/application layer MUST emit or invoke a deterministic dependency-change hook identifying the changed stable entity/artifact ID.

The hook is not durable professional evidence. Its purpose is to let LLD-03 mark dependent entries retrieval-stale and reindex them synchronously or during explicit reconciliation. If the hook is missed because of a crash, startup/`doctor` dependency-hash reconciliation MUST detect the mismatch before the retrieval subsystem claims completeness.

## 18. SQLite Rebuild Contract

A full SQLite rebuild MUST be possible from an empty database using only the vault source/catalog files.

Rebuild order:

```text
1. initialize persistence-owned schema migrations
2. scan session metadata
3. validate raw transcript presence/integrity
4. resolve each entry's highest/current published revision
5. scan entity catalog
6. scan artifact catalog
7. scan amendments
8. populate sessions / entries / revisions / relationships
9. rebuild WorkState from current revisions
10. hand current entries to LLD-03 for retrieval-index rebuild
```

If an entry revision references a missing entity/artifact, rebuild MUST fail that relationship visibly and `doctor` MUST report it; the system MUST NOT silently fabricate the missing object.

## 19. Access Patterns Owned by This LLD

Persistence must support these exact current access patterns without scanning all source files during normal operation:

| Access pattern | Storage path |
|---|---|
| Load session by ID | `sessions` table -> `source_path` |
| Load current entry by entry/session ID | `entries` -> `current_path` |
| Load historical entry revisions | `entry_revisions` ordered by revision |
| List sessions for a day | `sessions_by_local_date` |
| Resolve entity by ID | `entities` |
| Resolve entity by known alias | `entity_alias_lookup` |
| List current open/waiting work | `state_items_by_status` |
| List current project work | `state_items_by_project` |
| Resolve artifacts linked to entry | `entry_artifacts` + `artifacts` |
| Resolve entries linked to entity | `entry_entities` |
| Rebuild a day's journal | sessions/date + current entry paths |

Full-text and semantic access patterns belong to LLD-03.

## 20. Concurrency, Idempotency, Retry, and Partial Failure

### 20.1 Single-writer v1

V1 supports one active application process writing a vault at a time.

The application MUST acquire the vault-level advisory/exclusive source lock
before source mutation. A second source writer MUST fail clearly rather than
proceed concurrently. Derived index publication uses a separate advisory
index lock and MUST NOT hold the source lock while generating embeddings.

Read-only inspection MAY occur without the write lock if the implementation can tolerate observing the last atomically published snapshot.

Multi-device/multi-writer coordination is a future HLD concern.

### 20.2 Turn retries

A retry of the last raw turn with identical `turn_id`, sequence, role, and content is a no-op success.

Any divergent reuse of the same identity is an integrity error.

### 20.3 Commit retries

`commit_id` is the idempotency identity for structured commits.

The same `commit_id` MUST map to exactly one `(entry_id, revision, content_hash)` tuple.

### 20.4 SQLite transaction failure

If the source entry revision has already been atomically published but SQLite
or retrieval fails, the operation reports `source_status=committed` with an
independent derived status. The next `doctor`, `rebuild`, or `reindex` can
reconcile from source.

The implementation MUST NOT delete the successfully published source revision to make SQLite appear consistent.

### 20.5 Journal/state projection failure

Journal or state projection failure after source commit MUST surface as recoverable derived-state staleness. Source remains authoritative.

## 21. Security, Privacy, and Sensitive Data

### 21.1 Default filesystem permissions

Where the OS supports POSIX-style permissions, newly created private-vault directories SHOULD default to owner-only (`0700`) and files to owner-read/write (`0600`).

On platforms with different permission models, use the closest practical user-private default.

### 21.2 Secrets

The vault MUST NOT intentionally persist API keys, passwords, access tokens, or connector credentials in:

- transcripts;
- artifact locators;
- runtime metadata;
- SQLite tables;
- generated journals.

If the user speaks a secret into a conversation, v1 cannot guarantee automatic secret detection. Documentation MUST make this limitation explicit.

### 21.3 Communication boundary

This LLD stores private evidence. It does not mark content safe to share externally. Communication sanitization/shareability is owned by LLD-02.

### 21.4 Git boundary

The public repository MUST include ignore rules/documentation that prevent the configured private vault from being committed accidentally when it lives inside the repository tree.

A public example vault MUST contain synthetic data only.

## 22. Retention, Deletion, and User Control

### 22.1 Default retention

No automatic deletion or retention expiry exists in v1.

### 22.2 Explicit session deletion

A user-requested destructive session deletion MUST:

1. remove the session directory including raw turns and all entry revisions;
2. remove explicit amendments whose sole target/source is that deleted session when the user requests complete removal;
3. rebuild affected journal/state projections;
4. remove/rebuild corresponding SQLite and retrieval-index records;
5. leave unrelated entity/artifact catalog objects intact unless separately deleted.

The local interface MUST make destructive deletion explicit; exact command/UX mechanics are implementer discretion.

### 22.3 Partial raw-turn editing

V1 does not support in-place editing/redaction of individual committed raw turns because that breaks the raw-source invariant.

If a user requires removal of sensitive material from a session, v1 supports deleting the affected session and optionally recapturing a corrected/sanitized replacement.

A future privacy/redaction design may add a stronger mechanism under a new architecture revision.

## 23. Migration and Compatibility

### 23.1 SQLite migrations

Every checked-in SQLite schema change MUST be an ordered, repeatable migration with one unique `migration_id` recorded in `schema_migrations`.

Migrations MUST run transactionally where SQLite permits.

### 23.2 Source-file compatibility

V1 source JSON does not include defensive schema/protocol version fields.

Additive optional fields may be introduced when readers ignore unknown fields and missing fields have safe defaults.

The first incompatible source-format change MUST introduce an explicit migration/compatibility mechanism at that time; it MUST NOT be pre-invented in v1.

### 23.3 Migration authority

A source-format migration MUST NOT discard raw transcript text or explicit amendment evidence merely to fit a newer structured schema.

## 24. Observability and Integrity Evidence

The application SHOULD emit local operational logs containing IDs/paths/status but not transcript payloads by default.

`doctor` MUST be able to report at least:

- malformed/truncated non-tail JSONL records;
- session metadata/entry ID mismatches;
- missing current entry revisions;
- non-contiguous revision numbers;
- duplicate commit IDs;
- broken entity/artifact references;
- invalid state mutations;
- journal/state projection staleness;
- SQLite rows whose source paths are missing;
- source entry files missing from SQLite;
- hash mismatches for current structured entries;
- private-vault path accidentally located inside a Git repository without an effective ignore rule, when detectable.

`doctor` MAY repair derived projections/indexes after reporting the discrepancy, but MUST NOT silently repair or rewrite raw source evidence.

## 25. Cross-LLD Contract Register

### 25.1 Contracts owned by LLD-01

| Contract | Consumers |
|---|---|
| UUIDv7 stable identity convention | LLD-02, LLD-03, LLD-04 |
| Raw `turns.jsonl` persistence contract | LLD-02 |
| SessionEntry revision/section/provenance contract | LLD-02, LLD-03, LLD-04 |
| Statement basis/source-turn contract | LLD-02, LLD-03, LLD-04 |
| Entity/ArtifactReference identity contract | LLD-02, LLD-03, LLD-04, future connectors |
| Amendment semantics | LLD-02, LLD-04 |
| WorkState/StateMutation semantics | LLD-02 |
| Daily-journal materialization semantics | LLD-02/local interface |
| source-first commit ordering | LLD-02, LLD-03 |
| catalog dependency-change hook | LLD-03 |
| public-repo/private-vault persistence boundary | all LLDs |

### 25.2 Contracts consumed from sibling LLDs

| Contract | Authoritative owner | LLD-01 usage |
|---|---|---|
| Session lifecycle states/finalization order | LLD-02 | determines when `ended_at`/commit operations occur |
| Mode/domain selection | LLD-02 | persisted as open string tokens |
| instruction resource identity | LLD-02 | persisted in `session.json.runtime.sops` |
| Structured commit tool request | LLD-02 | validated/published using LLD-01 data rules |
| Search chunk identity/source hydration | LLD-03 | resolves to LLD-01 entry/session IDs |
| retrieval dependency hash/invalidation | LLD-03 | catalog changes notify or are reconciled against retrieval state |
| Career candidate-mark file contract | LLD-04 | sibling-owned preference state under vault; never alters SessionEntry authority |
| Communication shareability policy | LLD-02 | consumes evidence without changing source authority |

### 25.3 Thin local interface boundary

Exact command syntax, terminal presentation, Yap/stdin capture, and vault-root configuration do not currently create a separate architectural contract. The local adapter MUST use the application/persistence ports defined here and in LLD-02 rather than bypassing them.

## 26. Alternatives Considered

### 26.1 One Markdown file as the only source of truth

**Rejected.** It is human-readable but poor for incremental raw-turn durability, exact provenance, structured corrections, and deterministic rebuilds.

### 26.2 SQLite as the canonical source

**Rejected.** It weakens portability, auditability, Git-free backup simplicity, and recovery from index/schema mistakes. The HLD explicitly requires rebuildable derived indexes.

### 26.3 One mutable `entry.json` per session

**Rejected.** Re-extraction or correction would destroy prior interpretations and make it difficult to distinguish model improvement from factual correction.

### 26.4 Separate permanent event objects instead of one session entry

**Deferred/rejected for v1.** A session is already the ingestion/commit unit. Retrieval LLD-03 may chunk a session entry into smaller searchable units without introducing another authoritative source model.

### 26.5 Per-turn files instead of JSONL

**Rejected.** JSONL provides simpler ordered append, fewer filesystem objects, and straightforward streaming/recovery. The accepted trade-off is explicit handling of one incomplete trailing line after a crash.

### 26.6 Generic JSON Patch amendment format

**Rejected.** It tightly couples corrections to the current structured schema. Durable user amendments preserve the human correction; a new structured revision applies that correction under the current schema.

### 26.7 Full event-sourcing framework

**Rejected.** The corpus scale and single-user requirements do not justify a generalized event-store runtime. The design retains the useful event-sourcing properties—immutable raw evidence, explicit amendments, rebuildable projections—without a service/framework.

## 27. Requirement-to-Evidence Traceability

| Requirement / invariant | Required test or evidence |
|---|---|
| Raw turns survive process failure | integration test kills process after appended turns and successfully recovers complete records |
| Only incomplete trailing JSONL may be truncated | adversarial fixture with malformed middle line fails integrity check |
| Raw turn retry is idempotent | append same `turn_id` twice; one durable record remains |
| Divergent duplicate turn fails | same `turn_id`/sequence with different content produces integrity error |
| Structured revision immutable | attempt to publish over existing revision path fails |
| Commit retry idempotent | same `commit_id` twice returns same revision |
| Re-extraction preserves history | second revision exists and first remains readable |
| User correction is distinguishable | amendment + `user_correction` revision can be traced to original entry and source session |
| Reconstructed evidence distinguishable | backfill fixture persists `provenance_kind=reconstructed` |
| Journal is rebuildable | delete journal file and reproduce equivalent content from source entries |
| WorkState is rebuildable | delete `state/current.json` and SQLite state table, rebuild same active items |
| Superseded state mutations do not leak | revise an old entry, rebuild state, verify only current revision semantics apply |
| SQLite is rebuildable | delete DB and reconstruct persistence-owned tables from vault files |
| Source-first failure safety | force SQLite/index failure after entry-file publication; source remains recoverable |
| Broken references are visible | missing entity/artifact fixture is reported by `doctor` |
| Private/public boundary | clean public checkout runs with synthetic vault and contains no real private data |

## 28. Ordered Implementation Plan

### Step 1 — Implement IDs, timestamp parsing, and source data validators

Create language-native value objects/validators for UUIDv7, RFC3339 timestamps, occurrence precision, SessionEntry, Statement, StateMutation, Entity, ArtifactReference, and Amendment.

**Gate:** fixture tests accept every normative example in this LLD and reject invalid identities, timestamps, state statuses, revision sequences, and unsupported provenance values.

### Step 2 — Implement vault path/layout and atomic I/O primitives

Implement directory creation, owner-private permissions where available, append+sync, atomic replace, and vault write lock.

**Gate:** crash/failure tests demonstrate no half-replaced mutable snapshot and correct single-writer behavior.

### Step 3 — Implement raw session store

Implement `session.json`, `turns.jsonl`, sequence checks, duplicate-tail idempotency, and trailing-record recovery.

**Gate:** raw-turn durability and corruption tests pass.

### Step 4 — Implement structured entry revision store

Implement immutable revision publication, `commit_id` uniqueness, revision lookup, and current-revision resolution.

**Gate:** initial commit/retry/reextract/user-correction revision tests pass without rewriting prior revisions.

### Step 5 — Implement entity/artifact/amendment catalogs

Implement atomic current-record updates, alias lookup inputs, artifact-reference persistence, and immutable amendment creation.

**Gate:** rename/alias, amendment traceability, and broken-reference tests pass.

### Step 6 — Implement WorkState projector

Implement state-mutation validation, incremental new-entry application, and deterministic full rebuild on supersession/correction.

**Gate:** full rebuild equals incremental state for the same current entry set.

### Step 7 — Implement daily-journal renderer

Render one day's current entries using the contract in §15.

**Gate:** regenerated journal is deterministic for a fixed source set and excludes superseded revisions.

### Step 8 — Implement SQLite persistence schema and migration runner

Add the persistence-owned tables and source-to-SQLite reconciliation.

**Gate:** delete/rebuild DB test reproduces all current metadata and WorkState.

### Step 9 — Implement `doctor` integrity checks required by this LLD

Do not include LLD-03 FTS/vector checks until that sibling is implemented.

**Gate:** every integrity fixture produces the expected diagnostic and no raw source is silently modified.

### Step 10 — Cross-review with LLD-02, LLD-03, and LLD-04

Reconcile session lifecycle/commit payloads, search source-hydration/dependency invalidation, and the LLD-04 career-mark vault boundary before freezing implementation.

**Gate:** sibling review reports no genuine conflicts in shared contracts.

## 29. Objective Acceptance Criteria

LLD-01 is implementation-ready when all of the following are true:

- a session can be created with a stable UUIDv7 identity;
- user and assistant turns are durably appended and recoverable after a simulated crash;
- one malformed final partial record can be safely recovered while malformed middle data fails visibly;
- a structured commit creates immutable revision `1` with traceable statements;
- retrying the same `commit_id` is idempotent;
- a re-extraction creates revision `2` without changing revision `1`;
- an explicit correction produces a durable amendment and a new `user_correction` revision;
- contemporaneous and reconstructed entries are queryably distinct;
- entity and artifact references resolve through stable IDs;
- state mutations produce current lightweight WorkState and can be fully rebuilt;
- deleting `journal/`, `state/`, and `index/work-brain.sqlite` does not destroy source evidence and all can be rebuilt;
- the affected day's journal updates after a new session without requiring close-day;
- SQLite domain tables can be reconstructed from the vault;
- failed SQLite/journal/index updates after a source commit leave the source valid and detectable as stale;
- one process holds the vault write lock and a second writer fails safely;
- a synthetic example vault can be used from a public checkout with no private user material;
- LLD-02 and LLD-03 have cross-reviewed the shared core contracts before substantial implementation begins; LLD-04 confirms its career-mark files do not alter professional-evidence authority.
- changing an entity/artifact searchable name/alias makes dependent retrieval data stale or is detected by `doctor` reconciliation.

## 30. Decision Register

| Decision | Status | Rationale |
|---|---|---|
| JSONL for raw conversational turns | Resolved | appendable, ordered, simple, recoverable with explicit trailing-record rule |
| JSON revision files for structured entries | Resolved | deterministic structured contract and immutable history |
| Markdown for daily journal projection | Resolved | human-readable and easy to inspect/share locally |
| UUIDv7 for durable IDs | Resolved | decentralized, sortable, cross-platform stable identity |
| One stable entry per session with revision history | Resolved | preserves ingestion-unit simplicity while supporting redrive/correction |
| Explicit Amendment records | Resolved | corrections remain source evidence independent of current schema |
| Statement-level `basis` + turn references | Resolved | limits silent inference and supports weak-model auditability |
| Current WorkState as rebuildable projection | Resolved | immediate operational utility without second source of truth |
| Single-writer vault | Resolved | matches v1 local single-user scope and avoids needless distributed locking |
| No source JSON schema version in v1 | Resolved | no active compatibility branch currently requires one |
| SQLite migration ledger | Resolved | application upgrades need deterministic DB migration history |
| Full state rebuild on superseded mutation history | Resolved | personal scale makes correctness simpler than inverse-patch logic |
| Stable `resource-id@version` SOP provenance | Resolved | enables reproducible session provenance without coupling to filenames |
| Session `ended_at` finalized after entry publication | Resolved | prevents a closed-looking session from lacking its structured entry after crash |
| Catalog dependency-change hook for retrieval | Resolved | keeps denormalized search metadata rebuildable/current |
| LLD-04 career marks stored outside SessionEntry authority | Resolved | user preference is durable but does not become a professional fact |
| Exact implementation language | Implementer discretion / sibling decision | persistence contract does not require one language |

## 31. Documentation Drift / Consolidated Sibling Refinements

Version 2 consolidates the sibling refinements discovered while drafting LLD-02 and LLD-03: stable versioned instruction-resource identity, session finalization after entry publication, and retrieval invalidation when denormalized entity/artifact metadata changes.

The representative vault layout in the parent HLD omitted a dedicated structured-entry directory. This LLD does not conflict with the HLD: structured entries were explicitly a durable L1 layer and exact filesystem layout was delegated here. LLD-01 co-locates revisions under their source session to keep provenance explicit.

## 32. Consult and Blocker

### Consult

None.

### Blocker

None for LLD authoring.

Implementation MUST NOT freeze until the LLD-02/LLD-03 sibling cross-review confirms the shared session-commit, source-hydration, pagination, and dependency-invalidation contracts. LLD-04 must confirm that its durable career marks remain preference metadata rather than evidence authority.

## 33. Final Coding-Agent Readiness Gate

A coding agent implementing this LLD should not need to invent:

- which files are authoritative;
- how raw turns are durably represented;
- how IDs/timestamps work;
- how structured interpretations are revisioned;
- how user corrections differ from model reinterpretation;
- how contemporaneous/backfilled evidence differs;
- how state mutations rebuild current work state;
- how daily journals are materialized;
- how durable source publication is ordered relative to SQLite/derived updates;
- what SQLite domain tables LLD-01 owns;
- how retries, partial failure, and single-writer concurrency behave;
- which private data must stay outside the public repository.

Remaining implementation choices are intentionally local mechanics or sibling-owned contracts. After LLD-02/03/04 cross-review, this LLD can be frozen as the persistence baseline.
