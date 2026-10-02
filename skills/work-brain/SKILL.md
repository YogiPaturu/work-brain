---
name: work-brain
description: Use when recovering work context, reasoning through professional decisions, preserving exact work evidence, starting or closing a work day, updating work state, drafting from relevant private work context, or practising interview and career stories. Work Brain uses explicit activation and bounded sessions; ordinary coding chats remain outside durable capture.
---

WORK-BRAIN-SKILL v2

# Work Brain

Use this Skill for bounded professional-thinking sessions over a private Work
Brain vault. The application selects one workflow and loads only the core SOP,
that workflow SOP, and up to two relevant domain probes. Select probes for the
actual target (not keyword presence), and replace them when the target changes.

## Routing

| Intent | Workflow | SOP |
|---|---|---|
| reason through a decision or problem | `think` | `think.sop.md` |
| current tasks, blockers, or commitments | `operate` | `operate.sop.md` |
| prepare a shareable draft | `communicate` | `communicate.sop.md` |
| interview or career practice | `career` | `career.sop.md` |
| start-of-day orientation | `open-day` | `open-day.sop.md` |
| end-of-day reflection | `close-day` | `close-day.sop.md` |
| reconstruct a past experience | `backfill` | `backfill.sop.md` |

Explicit workflow selection bypasses model classification. Use only the
documented Work Brain CLI operations for Work Brain persistence, state,
retrieval, and maintenance. Do not access Work Brain's SQLite database, vector
data, internal vault files, or generated projections directly. Do not construct
ad-hoc SQL or mutate the vault through arbitrary shell commands. The harness
may use its normal shell to execute sanctioned `work-brain` commands.

## Development / authoring boundary

When the user's task is to inspect, edit, test, document, package, install, or
otherwise develop Work Brain itself, treat it as Work Brain development, not as
a Work Brain professional-memory session. Do not activate durable capture solely
because the task mentions Work Brain. Do not retrieve or mutate the user's
private Work Brain vault unless the task explicitly requires a fixture or
integration test against it. Use repository files, tests, and design documents
as the development context.

An explicit user activation such as “work brain think with me about this
architecture” still overrides this boundary when the user genuinely wants a
Work Brain session. Skill discovery or loading is not activation: the Skill may
be available while repository work remains an ordinary coding task, and hooks
must keep capture inactive until an activation boundary is observed.

Activation is speech-friendly: a leading `work brain` is case-insensitive and
does not require punctuation; the raw prompt remains unchanged. Explicit
natural aliases include `start my day`, `open my work journal`, `start work
brain`, `capture this`, and `journal this`; `close my day` routes active
sessions to `close-day` and may finish without a CommitDraft.

Work Brain v1 is hosted by the active local agent harness. The harness owns the
conversation, model, context, and agent loop; Work Brain owns the private vault,
evidence, projections, retrieval, and deterministic CLI. There is no second
Work Brain LLM call and no MCP server in v1. At a live workflow boundary, emit
only the CommitDraft shape when durable new evidence exists and let the
application validate and publish it automatically. A close-day gap check may
complete without a commit; capture deactivation is a separate lifecycle action.
If the host/model disappears first, raw turns remain durable and the next live
start-of-day boundary rolls them over and commits them when meaningful evidence
exists.
“Finish this,” “that’s enough,” and “save this” may finish one bounded session
while keeping capture active; “stop Work Brain” and “close my day” deactivate it.

## Session and provenance contract

The host capture session is the source of truth for the current conversation.
The agent MUST NOT create a second session to summarize the conversation, and
MUST NOT append a model-written summary with the low-level `turn` command. The
raw-turn append API is an internal integration/testing primitive, not a normal
hosted-agent operation. Raw user and assistant turns are written by host hooks;
the agent only reads them and emits a semantic CommitDraft.

Before committing, the agent MUST identify the exact active `session_id` from
the host mapping or `session status`. It MUST NOT choose a session merely
because it is the newest recoverable session. If the active mapping is absent
or ambiguous, inspect status and leave the raw session recoverable rather than
starting a replacement session.

An entry revision is valid only when it belongs to the same bounded session as
the new evidence. A separate conversation session produces a new linked entry;
it does not become a revision by combining summaries. Use `source_entry_refs`
to relate a new entry to an older entry when appropriate. The runtime owns
entry IDs, revisions, and supersession metadata; the agent never invents them.

Every statement and state change in a CommitDraft MUST cite exact persisted
turn sequences from the target session, including at least one user-authored
turn. Assistant-only or model-generated turns are not durable evidence. If a
claim cannot be supported by the target session, omit it or keep the session
recoverable.

If CommitDraft validation fails, the agent MUST NOT work around the error by
creating a new session, appending synthetic turns, or combining unrelated
entries. Read the target session's bounded turns, correct the draft's
provenance, and retry once; if the evidence is unavailable, report the failure
and defer the commit to the next live workflow boundary.

When the user supplies a transcript whose original host capture was missed, use
the explicit transcript-import operation. Treat the imported session as raw
source evidence with `capture_fidelity: imported`; do not pretend it was
verbatim host capture, do not assign unknown historical timestamps, and do not
merge it into an existing entry before review.

Lifecycle visibility is part of the user contract. Whenever Work Brain starts,
resumes, or reaches a boundary, report capture state and commit state
separately: whether raw turns are actively being saved, whether a recoverable
raw session exists, the turn count and last-captured time, and whether a
structured entry is committed, pending, absent, or imported. If capture is
inactive, say so plainly and tell the user how to reactivate it.

Use the read-only `work-brain status --json` operation as the first lifecycle
check because it discovers the active host mapping. Use `session status` with
the exact returned session ID before reading turns or emitting a CommitDraft.
The human-facing `work-brain status`, `status --quiet`, and `status --watch`
views are optional terminal conveniences; they never replace exact session
verification and never mutate raw turns.

On Codex, the host capture hook supplies the same compact lifecycle banner at
the host's valid session, prompt, and stop hook boundaries. Treat that banner
as runtime-provided state, not as a reason to invent a session or skip exact
provenance checks.

Resources:

- `references/sops/core-conversation.sop.md`
- the selected file under `references/sops/`
- zero, one, or two files under `references/probes/`
- `references/schemas/commit-draft.md` when producing a commit
- `references/domain-tags.md` when producing a commit
- `references/tools/agent-tools.md` when using application tools
- `references/tools/work-brain-cli.md` when executing Work Brain operations
