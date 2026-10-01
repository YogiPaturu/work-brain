WORK-BRAIN-TOOLS v3

The host agent uses intent-level application operations only. In the
harness-hosted v1 path, these are executed as documented `work-brain` CLI
commands through the harness's existing shell capability:

- `get_current_state`
- `get_recent_work`
- `search_evidence`
- `hydrate_evidence`
- `search_questions`
- `get_question`
- `choose_question`
- `mark_interview_candidate` only after explicit user confirmation
- `unmark_interview_candidate` only after explicit user confirmation
- `list_interview_candidates`
- `commit-draft` through stdin or a bounded file during the committing phase
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
the exact session ID before reading turns or committing. Report capture and
commit independently: `capture_active`, `lifecycle`, `turn_count`,
`last_captured_at`, `commit_status`, and `message`. An empty `work recent`
result does not mean that no raw session exists.

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
work-brain career questions search --tag-all conflict
work-brain career prepare --question-text "Tell me about a difficult decision"
work-brain career mock --question-text "Tell me about a difficult decision"
```

Structured CommitDraft input MAY be an object on stdin or a JSON file. The
application validates the request, applies the active workflow contract, and
returns a compact JSON result. Unknown, malformed, or failed calls become
stable structured errors; they MUST NOT mutate the vault. Tool payloads and
host shell details are not appended to the raw visible-turn transcript.

Raw-turn append is not exposed as a normal CLI operation. The internal append
API is reserved for adapters, fixtures, and explicit integration tests. A
hosted agent MUST NOT use it to append its own summary or manufacture missing
conversation history. If a CommitDraft fails because of provenance, inspect
`session turns` and repair the draft; do not create a replacement session or
combine unrelated sessions.

`session quarantine` is a narrowly scoped maintenance command requiring an
explicit session ID and reason; it hides a known bad structured entry while
preserving the raw turns. It is not for ordinary workflow completion.

Career question lookup is deterministic and does not require a model call.
Question banks are separate from professional evidence. `prepare` may show a
bounded page of plausible EvidenceCards and an opaque continuation cursor;
`mock` asks the question first and does not reveal evidence suggestions before
the answer. The user chooses the story/angle. Candidate marks are private
preference events and require explicit confirmation; a model suggestion alone
must never persist one.

The existing `ToolRegistry` and bounded standalone model/tool loop remain
available for provider-free tests and future standalone mode. They are not a
production v1 dependency and do not define the harness-hosted architecture.
