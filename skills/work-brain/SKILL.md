WORK-BRAIN-SKILL v1

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

Explicit workflow selection bypasses model classification. Private evidence is
retrieved through high-level tools; never ask the model to generate SQL,
filesystem writes, shell commands, or vector-index operations. At close, emit
only the CommitDraft shape and let the application supply IDs, timestamps,
revisions, provenance, and persistence.

Resources:

- `references/sops/core-conversation.sop.md`
- the selected file under `references/sops/`
- zero, one, or two files under `references/probes/`
- `references/schemas/commit-draft.md` when producing a commit
- `references/tools/agent-tools.md` when using application tools
