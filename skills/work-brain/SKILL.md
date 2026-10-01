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

Resources:

- `references/sops/core-conversation.sop.md`
- the selected file under `references/sops/`
- zero, one, or two files under `references/probes/`
- `references/schemas/commit-draft.md` when producing a commit
- `references/tools/agent-tools.md` when using application tools
- `references/tools/work-brain-cli.md` when executing Work Brain operations
