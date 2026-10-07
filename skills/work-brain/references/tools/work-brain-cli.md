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
work-brain context resolve --workspace "Ranq" --project "token refresh work" --limit 5
work-brain work loops --limit 20
work-brain evidence get --entry-id ENTRY_ID
work-brain evidence search --query "import reliability" --page-size 10
work-brain evidence select --filters '{"occurred_after":"2026-10-01","projects":["Auth"]}'
work-brain evidence hydrate < refs.json
work-brain experience list --limit 8
work-brain experience search --query "influenced the API decision" --page-size 8
work-brain experience get --experience-id EXPERIENCE_ID
work-brain experience related --entry-id ENTRY_ID --limit 8
work-brain experience mine --page-size 5 --related-limit 6
work-brain experience hydrate --experience-id EXPERIENCE_ID
work-brain recoverable
work-brain status
work-brain status --quiet
work-brain status --watch
work-brain session turns --session-id SESSION_ID
work-brain session turns --session-id SESSION_ID --offset 0 --limit 100
work-brain session status --session-id SESSION_ID
work-brain session import --file transcript.json
work-brain schema commit-draft --json
```

`schema commit-draft --json` is read-only, does not require an initialized
vault, and returns the canonical CommitDraft structure and template. Its section
names are generated from the same `ENTRY_SECTIONS` constant used by validation.

`context resolve` is the read-only application operation for resolving existing
workspace/project identities from canonical names, aliases, or bounded
historical evidence. The model calls this operation rather than constructing
SQL or inspecting SQLite. SQLite is a fast lookup/retrieval projection;
source catalog entities remain authoritative. A deterministic exact match may
be used for CommitDraft's plain-string `workspace` and `project` fields;
historical matches are candidates and should be clarified if ambiguous.

`evidence search` is the retrieval application operation. It returns bounded
EvidenceCards with stable entry/revision refs and an opaque continuation
cursor. Use `evidence hydrate` for selected refs and `reindex` for explicit
retrieval maintenance. Search may report degraded or incomplete state; never
describe an unavailable search as proof that no history exists.

`evidence select` is the filter-only companion for date, workspace, project,
Experience, domain-tag, provenance, and outcome scopes. It does not require a
query string and uses the same bounded cards and pagination contract.

`experience list/search/get/hydrate` are bounded read operations over stable
Experience entities and their linked SessionEntry revisions. An Experience is
optional; unassigned entries remain available through `evidence search` and
career preparation. Use `experiences` in evidence filters to scope a project,
communication request, or interview search to one or more Experience IDs or
aliases.

`experience related` is a read-only candidate-discovery operation. It uses the
anchor entry's deterministic structured text with existing hybrid retrieval,
then revalidates candidates against the anchor's exact current
workspace/project tuple. It does not create or associate Experiences. Use it
before `experience associate` when an entry may continue an existing
Experience, and load `references/experience-review.md` for the bounded
include/exclude/uncertain review. Candidate recall is not a grouping decision;
leave the entry unassigned when the evidence remains uncertain.

`experience mine` is a read-only, cursor-paginated historical-mining operation.
It selects visible current entries with no Experience ref from authoritative
source data, then delegates bounded related discovery for only that page. Use
the returned cursor for the next batch after reviewing and explicitly
associating any approved entries. It does not cluster, associate, create an
Experience, or load the whole vault; retrieval degradation keeps anchors in the
response and is not evidence that no related history exists.

## Capture and mutation

```sh
work-brain capture-hook --host codex < hook.json
work-brain capture-hook --host claude-code < hook.json
work-brain capture-hook --host cursor < hook.json
work-brain commit-draft --session-id SESSION_ID < draft.json
work-brain migrate-domain-tags --dry-run
work-brain migrate-domain-tags
work-brain backfill-tags --file domain-tags.json --dry-run
work-brain backfill-tags --file domain-tags.json
work-brain experience associate --entry-id ENTRY_ID --experience-id EXPERIENCE_ID
work-brain experience associate --entry-id ENTRY_ID --experience-name "Migration recovery"
work-brain recoverable
```

Structured CommitDraft input may be supplied on stdin or with `--file PATH`.
The application validates and resolves IDs, revisions, provenance, and
persistence. An ordinary commit rotates to a fresh bounded session while the
host capture mapping stays active. A close-day commit deactivates the mapping.
Do not write `turns.jsonl`, SQLite, journals, state, or vector data directly.
When `context resolve` deterministically identifies an existing workspace or
project, preserve its canonical name in `workspace`/`project` and its returned
ID in `workspace_ref`/`project_ref`; the application verifies the ref against
the source catalog. Do not invent refs or emit persisted fields such as
`workspace_entity_id` or `project_entity_id` in a CommitDraft.

At a commit boundary, verify the exact target session and persisted turns, then
retrieve `work-brain schema commit-draft --json` and fill its template. Keep
every structural key exactly as returned. The existing
`work-brain commit-draft --session-id ... --workflow ... [--file ...]`
invocation is unchanged.

An `error.code` of `vault_access_denied` means the current host process cannot
write the configured vault. It is not a CommitDraft/schema failure: do not
retrieve the schema to repair it, rewrite the draft, alter workspace/project
classification, create a replacement session, append synthetic turns, or move
the vault under the repository. Preserve raw turns, explain the access problem,
and after host access is repaired and restarted if needed, verify and retry the
same session. The single schema repair retry is only for structural/schema
`invalid_request` errors.

`backfill-tags` is the documented historical-maintenance operation for adding
domain tags to existing current entries. Its JSON input is an explicit mapping
with optional `defaults.domain_tags` and per-entry `entries[ENTRY_ID].domain_tags`
lists. The lists are additive, have no upper bound, and are normalized to
lowercase hyphenated tokens while preserving existing tags. Run `--dry-run`
first; an applied change publishes a new immutable `metadata_backfill` revision
and retains the prior revision and source reference.

`migrate-domain-tags` is the one-time schema migration for older private vaults
that stored the same metadata under `domains`. It renames the key to
`domain_tags` in session and structured-entry JSON, preserves IDs/revisions and
evidence values, rebuilds all derived projections, and supports `--dry-run`.
Run it before using the renamed filters or profile scopes on an older vault.

`work-brain backfill-project-workspaces --dry-run` and
`work-brain backfill-project-workspaces` are explicit maintenance commands for legacy
unparented projects. They derive ownership only from stable project/workspace
IDs on authoritative current entries, apply only projects with exactly one
known workspace, and never guess conflicts or projects with no workspace
evidence. Run the dry run first. Applying the plan changes only project source
metadata; it does not rewrite historical entries and refreshes rebuildable
projections afterward.

Starting any new activated Work Brain workflow automatically rolls over inactive recoverable
sessions more than one calendar day old. It preserves their raw turns and marks
them `pending_auto_commit`; the live workflow boundary publishes a summary
when meaningful evidence exists, or closes them as `no_new_evidence`. A session
from exactly yesterday is left alone for the midnight edge case, and an active
host mapping is never silently closed.

`session status` is read-only and reports lifecycle state, turn count, last
captured turn, capture/commit status, and host-session mappings. `session close`
is the explicit no-new-evidence/abandoned boundary when no structured entry is
being published.

`status` is the human-facing lifecycle dashboard. It automatically discovers
the active host mapping and prints capture state, turn count, last captured
time, commit state, and recoverable-session count. `status --quiet` prints a
single prompt-friendly line; `status --watch` refreshes the dashboard until
interrupted. These are read-only views and never modify raw turns or entries.

For Codex, the installed capture hook owns and emits the compact lifecycle
banner through Codex's valid `SessionStart`, `UserPromptSubmit`, and `Stop`
hook output once Work Brain is active or recoverable. The agent does not need
to remember to run `status` for routine display and must not duplicate the
banner. It must still verify the exact session with `session status` before
reading turns or committing, and explain exceptional or ambiguous lifecycle
conditions when relevant.

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
may include `started_at`, `workflow`, `modes`, `domain_tags`, and `source`. The
application validates the entire input before creating a closed imported
session. It preserves the supplied turn text exactly, marks the capture as
`imported`, and never merges it into an existing session or entry. Missing
per-turn timestamps are recorded at import time rather than fabricated as
historical event times.

If `commit-draft` returns a validation error, classify it. For structural/schema
errors, retrieve the canonical schema again and repair against that structure,
then retry at most once on the same session. For provenance/source-turn errors,
inspect the exact persisted turns and repair references. For semantic/context
ambiguity, follow the normal clarification rules. If the deterministic repair
still fails, leave raw turns preserved and surface the error. Do not append a
turn to repair a draft or create a replacement session. A same-session
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
