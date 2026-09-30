---
name: work-brain
description: Use for bounded professional thinking, daily work state, communication, career evidence, interview practice, and related Work Brain workflows.
---

WORK-BRAIN-SKILL v2

# Work Brain

Use this Skill for bounded professional-thinking sessions over a private Work
Brain vault. The application selects one workflow and loads only the core SOP,
that workflow SOP, and up to two relevant domain probes.

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

Work Brain v1 is hosted by the active local agent harness. The harness owns the
conversation, model, context, and agent loop; Work Brain owns the private vault,
evidence, projections, retrieval, and deterministic CLI. There is no second
Work Brain LLM call and no MCP server in v1. At close, emit only the CommitDraft
shape and let the application supply IDs, timestamps, revisions, provenance,
and persistence.

Resources:

- `references/sops/core-conversation.sop.md`
- the selected file under `references/sops/`
- zero, one, or two files under `references/probes/`
- `references/schemas/commit-draft.md` when producing a commit
- `references/tools/agent-tools.md` when using application tools
- `references/tools/work-brain-cli.md` when executing Work Brain operations
