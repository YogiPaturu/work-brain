---
name: work-brain
description: Use only when the user explicitly invokes Work Brain (for example, a prompt beginning with "work brain") or uses a documented Work Brain activation alias such as "start my day", "open my work journal", "start work brain", "capture this", or "journal this". Also use to continue an already-active Work Brain session and to handle its lifecycle commands such as "close my day" or "stop Work Brain". Supports bounded professional reasoning, work-state recovery, communication drafting from private work context, historical backfill, and career/interview practice. Do not use for ordinary coding or professional chats, or for Work Brain development, unless the user explicitly activates Work Brain.
---

WORK-BRAIN-SKILL v2

# Work Brain

Use this Skill for bounded professional-thinking sessions over a private Work
Brain vault. The application selects one workflow and loads only the core SOP,
that workflow SOP, and up to two relevant domain probes. Select probes for the
actual target (not keyword presence), and replace them when the target changes.
The durable product model is conversation evidence grouped optionally into
long-lived source-backed Experiences; calendar-day views are conveniences.

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
Work Brain activation rolls them over and commits them when meaningful evidence
exists. The activation may be `think`, `operate`, `communicate`, `career`, or
another workflow; it does not require `start my day`.
“Finish this,” “that’s enough,” and “save this” may finish one bounded session
while keeping capture active; “stop Work Brain” and “close my day” deactivate it.

## Session and provenance contract

The host-captured Work Brain session is authoritative for the current
conversation. Never manufacture missing evidence by creating a replacement
session, appending synthetic or model-written raw turns, or combining
unrelated sessions.

Before reading bounded turns or committing, identify and verify the exact
active `session_id` from the host mapping/status; never select merely the
newest recoverable session. If the mapping is absent or ambiguous, inspect
status and leave the raw session recoverable rather than starting a replacement.
Every durable CommitDraft statement or state change must cite exact persisted
source turns from that target session, including at least one user-authored
turn. Evidence from another session requires a separate linked entry, not a
revision of the current entry.

If validation fails, repair provenance against the same target session and retry
the canonical workflow; never create a replacement session to work around the
error. Imported transcripts retain imported/reconstructed capture semantics and
must not be presented as verbatim host capture.

Detailed session, revision, CommitDraft, import, recovery, and CLI mechanics
are owned by the referenced core SOP, schema, and tool documentation below.

Lifecycle visibility is part of the user contract. The runtime/hook owns the
routine compact lifecycle banner at valid host boundaries; do not repeat a
banner that the runtime already supplied. Still inspect and distinguish capture
state and commit state separately when required: whether raw turns are actively
being saved, whether a recoverable raw session exists, the turn count and
last-captured time, and whether a structured entry is committed, pending,
absent, or imported. Explain exceptional or ambiguous conditions when they
affect the user's work, including recoverable raw sessions, failed or pending
structured commits, ambiguous or missing active mappings, imported capture, or
capture unexpectedly being inactive. If capture is inactive, say so plainly
when relevant and tell the user how to reactivate it.

Use the read-only `work-brain status --json` operation as the first lifecycle
check because it discovers the active host mapping. Use `session status` with
the exact returned session ID before reading turns or emitting a CommitDraft.
The human-facing `work-brain status`, `status --quiet`, and `status --watch`
views are optional terminal conveniences; they never replace exact session
verification and never mutate raw turns.

On Codex, the host capture hook supplies the compact lifecycle banner at the
host's valid session, prompt, and stop hook boundaries. Treat that banner as
runtime-owned routine status: do not duplicate it, and do not treat it as a
reason to invent a session or skip exact provenance checks. Explain the state
yourself when the banner is absent or an exceptional condition needs context.

Resources:

- `references/sops/core-conversation.sop.md`
- the selected file under `references/sops/`
- zero, one, or two files under `references/probes/`
- `references/schemas/commit-draft.md` when producing a commit
- `references/domain-tags.md` when producing a commit
- `references/tools/agent-tools.md` when using application tools
- `references/tools/work-brain-cli.md` when executing Work Brain operations
