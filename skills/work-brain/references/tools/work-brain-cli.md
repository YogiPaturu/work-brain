WORK-BRAIN-CLI v1

# Work Brain CLI

Use the existing harness shell to invoke only the documented `work-brain`
operations. The CLI is the supported application adapter for Work Brain v1;
there is no MCP server and no second Work Brain model call.

## CLI resolution

Prefer `work-brain` when it is on `PATH`. A host may not inherit the shell
that activated the repository virtualenv, so if the command is unavailable,
resolve the checkout-local launcher before giving up:

```sh
WORK_BRAIN_CLI="$(command -v work-brain || true)"
if [ -z "$WORK_BRAIN_CLI" ] && [ -x "$(pwd)/.venv/bin/work-brain" ]; then
  WORK_BRAIN_CLI="$(pwd)/.venv/bin/work-brain"
fi
```

Use the resolved absolute launcher for the rest of the operation. If the
current directory is not the checkout, use the repository's absolute
`.venv/bin/work-brain` path. Do not read the private vault directly as a
fallback.

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
work-brain session turns --session-id SESSION_ID
work-brain session turns --session-id SESSION_ID --offset 0 --limit 100
work-brain session status --session-id SESSION_ID
work-brain session import --file transcript.json
```

`evidence search` is the retrieval application operation. It returns bounded
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

Starting a new Work Brain session automatically rolls over inactive recoverable
sessions more than one calendar day old. It preserves their raw turns and marks
them `pending_auto_commit`; the live start-of-day workflow publishes a summary
when meaningful evidence exists, or closes them as `no_new_evidence`. A session
from exactly yesterday is left alone for the midnight edge case, and an active
host mapping is never silently closed.

`session status` is read-only and reports lifecycle state, turn count, last
captured turn, capture/commit status, and host-session mappings. `session close`
is the explicit no-new-evidence/abandoned boundary when no structured entry is
being published.

`session quarantine --session-id SESSION_ID --reason REASON` is a maintenance
operation for an explicitly identified closed session with a known bad
structured entry. It removes that entry from active projections while
preserving the session metadata and raw turns for audit. It is not a normal
recovery step and MUST NOT be used to hide an uncertain or merely unwanted work
item; use `session close` or a user correction instead.

### Choosing the target session

For an active hosted conversation, use the session ID supplied by the active
host mapping and verify it with `session status`. If several sessions are
recoverable, inspect their host mappings and bounded turns; never assume the
newest session is the current conversation. `session-start` creates a new
application session and must not be used as a fallback for a missing mapping.

`session turns` is for auditing captured evidence. It is not a source for
copying or rewriting a transcript. The host hooks already persist the visible
user and assistant turns continuously.

`session import --file transcript.json` is the explicit recovery path for a
user-supplied transcript whose original host capture was missed. The JSON
object must contain a non-empty `turns` list of `{role, content}` objects and
may include `started_at`, `workflow`, `modes`, `domains`, and `source`. The
application validates the entire input before creating a closed imported
session. It preserves the supplied turn text exactly, marks the capture as
`imported`, and never merges it into an existing session or entry. Missing
per-turn timestamps are recorded at import time rather than fabricated as
historical event times.

If `commit-draft` returns a validation error, do not append a turn to add a
summary. Correct the draft's exact `source_turns` for the selected session, or
leave that session recoverable for a later workflow boundary. A same-session
follow-up may create a revision; evidence from a different session creates a
new entry and may use `source_entry_refs` to link the earlier entry.

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
