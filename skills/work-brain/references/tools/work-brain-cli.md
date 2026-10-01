WORK-BRAIN-CLI v1

# Work Brain CLI

Use the existing harness shell to invoke only the documented `work-brain`
operations. The CLI is the supported application adapter for Work Brain v1;
there is no MCP server and no second Work Brain model call.

## Vault selection

Resolution precedence is:

1. explicit global `--vault PATH`;
2. `WORK_BRAIN_VAULT`;
3. local user configuration written by `work-brain config set-vault PATH`;
4. a clear error.

Never put a private vault path in a repository, prompt, Skill, or committed
configuration file.

## Read operations

Use `--json` for deterministic machine-readable output where it is not already
the default:

```sh
work-brain state current
work-brain work recent --limit 8
work-brain work loops --limit 20
work-brain evidence get --entry-id ENTRY_ID
work-brain evidence search --query "import reliability" --page-size 10
work-brain evidence hydrate < refs.json
work-brain recoverable
```

`evidence search` is the LLD-03 application operation. It returns bounded
EvidenceCards with stable entry/revision refs and an opaque continuation
cursor. Use `evidence hydrate` for selected refs and `reindex` for explicit
retrieval maintenance. Search may report degraded or incomplete state; never
describe an unavailable search as proof that no history exists.

## Capture and mutation

```sh
work-brain capture-hook --host codex < hook.json
work-brain capture-hook --host claude-code < hook.json
work-brain capture-hook --host cursor < hook.json
work-brain commit-draft --session-id SESSION_ID < draft.json
work-brain recoverable
```

Structured CommitDraft input may be supplied on stdin or with `--file PATH`.
The application validates and resolves IDs, revisions, provenance, and
persistence. An ordinary commit rotates to a fresh bounded session while the
host capture mapping stays active. A close-day commit deactivates the mapping.
Do not write `turns.jsonl`, SQLite, journals, state, or vector data directly.

## Capture activation

Hooks are passive for ordinary coding conversations. Exact durable capture is
activated by a user prompt beginning with `work brain`, one of the exact
activation aliases (`start my day`, `open my work journal`, `start work brain`,
`capture this`, `journal this`),
or an explicit Work Brain Skill invocation observed by the hook. Once active,
the adapters append the exact visible user and assistant text. `close my day`
routes an active mapping to close-day and deactivates it after the visible
workflow response, even if no new CommitDraft is needed. Ambiguous phrases such
as `think about this` remain inactive. Implicit Skill behavior that was not
observed by a hook is never relabeled as verbatim capture.

Skill discovery or loading alone is not activation. A hook may observe that
the Skill is available while a user is editing Work Brain source; that event
must remain inactive unless the user also supplies an activation boundary.

`finish this`, `that's enough`, and `save this` are bounded-session completion
signals; they preserve the active host capture boundary. `stop work brain` and
`close my day` explicitly turn that boundary off.
