WORK-BRAIN-TOOLS v3

The host agent uses intent-level application operations only. In the
harness-hosted v1 path, these are executed as documented `work-brain` CLI
commands through the harness's existing shell capability:

- `get_current_state`
- `get_recent_work`
- `get_close_day_record` for target-day committed entries, committed entries
  missing from their journal projection, and every uncommitted raw session
- `resolve_context` for read-only resolution of existing workspace/project
  identities from a name, alias, or bounded historical evidence search
- `search_evidence`
- `select_evidence` for bounded filter-only selection without a text query
- `hydrate_evidence`
- `search_experiences`
- `get_experience`
- `hydrate_experience`
- `find_related_experience_entries` for bounded read-only discovery of current
  entries that may continue an anchor entry's Experience
- `get_experience_mining_batch` for one bounded, read-only page of ungrouped
  historical anchors plus related-entry candidate recall; use only from
  historical mining/backfill
- `search_questions`
- `get_question`
- `choose_question`
- `mark_interview_candidate` only after explicit user confirmation
- `unmark_interview_candidate` only after explicit user confirmation
- `list_interview_candidates`
- `associate_entry_experience` for explicit post-hoc Experience association
- `commit-draft` through stdin or a bounded file during the committing phase
- `schema commit-draft` for the canonical machine-readable draft structure,
  retrieved only at the commit boundary
- `session status` for read-only capture health and lifecycle inspection
- `status` for the auto-detected lifecycle dashboard at Work Brain boundaries

The host capture mapping, not a newly created `session-start`, identifies the
conversation being handled. `session-start` is an application/setup operation
used when opening a real Work Brain boundary; it is not a way to obtain a
session for an already-running host conversation. Do not select a session by
recency when more than one recoverable session exists.

At every Work Brain start, resume, workflow boundary, or commit boundary, use
the read-only `work-brain status --json` dashboard first. It auto-detects the
active host mapping and prevents choosing a session merely because it is the
newest recoverable one. For a selected session, use `session status` to verify
the exact session ID before reading turns or committing. The runtime/hook owns
routine lifecycle display; do not duplicate its banner. Inspect capture and
commit independently using `capture_active`, `lifecycle`, `turn_count`,
`last_captured_at`, `commit_status`, and `message`, and explain exceptional or
ambiguous conditions when they matter. An empty `work recent` result does not
mean that no raw session exists.

An ordinary `commit-draft` closes only the current bounded logical session and
keeps the host capture envelope active. `close-day` and explicit stop commands
close the envelope as well. At a live workflow boundary, meaningful evidence
is committed automatically; if the host/model is gone, raw turns are preserved
for the next start-of-day rollover.

Tools return compact typed results and stable references. Work Brain never
exposes raw SQL, vector primitives, arbitrary vault filesystem mutation, or
internal persistence operations as part of its supported application
interface. Retrieval implementation belongs behind the application adapter
and retrieval contract.

`search_evidence` returns EvidenceCards that include existing Experience
identities with stable entity IDs. In live `think` or `operate`, relevant cards
may support a bounded continuity decision before commit; see
`references/experience-review.md` for its limits.

For context classification, the model calls `resolve_context`; it never
constructs SQL. The application may use SQLite entity and retrieval indexes
internally, but source catalog entities remain authoritative and resolution is
read-only. Use a canonical result when it is deterministic, ask one concise
clarification question when candidates remain ambiguous, and do not invent a
durable workspace or project name when no candidate is supported.

The host agent can read other files that its own permissions allow. A Skill is
not a security boundary; the documented CLI is the supported Work Brain
interface and the private vault remains local.

The CLI accepts structured arguments and emits deterministic JSON. A provider
may internally map a logical operation to a tool call, but that is host-agent
behavior rather than a Work Brain model/tool loop. Work Brain v1 does not make
a second LLM call behind the host.

For example, the host may execute:

```sh
work-brain state current
work-brain work recent --limit 5
work-brain evidence search --query "import reliability" --page-size 10
work-brain evidence select --filters '{"occurred_after":"2026-10-01","projects":["Auth"]}'
work-brain experience search --query "influenced a decision" --page-size 8
work-brain experience list --limit 8
work-brain career questions search --tag-all conflict
work-brain career prepare --question-text "Tell me about a difficult decision"
work-brain career mock --question-text "Tell me about a difficult decision"
```

At a commit boundary, first verify the exact target session and inspect its
persisted turns, then run `work-brain schema commit-draft --json`. Populate that
returned template without adding, removing, renaming, pluralizing, or moving
structural keys, and publish it with `work-brain commit-draft`. Do not retrieve
the schema during ordinary conversation turns. Structured input MAY be supplied
on stdin or in a JSON file. The application validates the request, applies the
active workflow contract, and returns a compact JSON result. Unknown, malformed,
or failed calls become stable structured errors; they MUST NOT mutate the vault.
Tool payloads and host shell details are not appended to the raw visible-turn
transcript.

When `resolve_context` returns a deterministic existing workspace or project,
the model may copy its `entity_id` as `workspace_ref` or `project_ref` while
also emitting the returned canonical name. These refs are validated against
the authoritative source catalog; the model must never invent them. The
persisted fields `workspace_entity_id` and `project_entity_id` are not
CommitDraft inputs.

Raw-turn append is not exposed as a normal CLI operation. The internal append
API is reserved for adapters, fixtures, and explicit integration tests. A
hosted agent MUST NOT use it to append its own summary or manufacture missing
conversation history. If a CommitDraft fails, classify the error. For
structural/schema failures, retrieve the canonical schema again and make one
repair attempt against the same session; if it still fails, preserve the raw
session and surface the error. For provenance/source-turn failures, inspect
that exact session's persisted turns and repair the references. For
semantic/context ambiguity, follow the normal clarification rules. Never
create a replacement session or combine unrelated sessions.

`session quarantine` is a narrowly scoped maintenance command requiring an
explicit session ID and reason; it hides a known bad structured entry while
preserving the raw turns. It is not for ordinary workflow completion.

Career question lookup is deterministic and does not require a model call.
Question banks are separate from professional evidence. `prepare` aggregates
ranked EvidenceCards into bounded source-backed Experience candidates and also
preserves relevant ungrouped entries as single-entry candidates. `mock` asks
the question first and does not reveal evidence suggestions before the answer.
The user chooses the story/angle. Candidate marks are private preference events
over either a stable Experience or an individual entry and require explicit
confirmation; a model suggestion alone must never persist one. Experience
association is optional and can be added later with `experience associate`; it
publishes metadata revisions without rewriting older evidence.

When deciding whether an entry may continue an existing Experience, use
`experience related --entry-id ENTRY_ID --limit 8` first. Treat its entries as
candidates only, then load `references/experience-review.md` and inspect or
hydrate bounded evidence as needed. Use explicit association only when the
grouping is sufficiently clear and the user has approved the post-hoc change.
If uncertain, leave the entry unassigned so its evidence remains searchable
and durable. The review reference defines the same-Experience criteria; it does
not add an automatic grouping operation.

The existing `ToolRegistry` and bounded standalone model/tool loop remain
available for provider-free tests and future standalone mode. They are not a
production v1 dependency and do not define the harness-hosted architecture.
