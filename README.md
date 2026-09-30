# Work Brain

Work Brain is a local-first professional thinking and durable work-memory tool.
It helps you reason through decisions, recover current work state, prepare
communication, and practice interviews while preserving the underlying
conversation and structured evidence in a private vault.

Work Brain v1 is hosted by an existing local coding-agent harness—Codex,
Claude Code, or the local Cursor Agent. The harness owns the model,
conversation, context, agent loop, and shell. Work Brain owns the private
vault, evidence, retrieval, Skill/SOPs, deterministic CLI, and projections.
There is no second Work Brain LLM call and no MCP server in v1.

```text
User
  |
  v
Codex / Claude Code / Cursor
  |
  +---- Work Brain Skill ------> SOPs / probes
  |
  +---- existing shell --------> work-brain CLI
  |                                  |
  |                                  v
  |                          Work Brain application
  |                            /      |       \
  |                         vault    state   retrieval
  |
  +---- lifecycle hooks ------> capture adapter
                                  |
                                  v
                               raw turns
```

## What it is useful for

- **Think:** challenge assumptions, explore alternatives, and preserve why a
  decision was made.
- **Operate:** recover tasks, blockers, open loops, commitments, and next
  actions from current work state.
- **Communicate:** turn private context into a concise audience-appropriate
  draft without exposing unrelated private evidence.
- **Career:** retrieve multiple plausible experiences for interview practice and
  let the human choose the story or angle.
- **Open/close day:** orient around current state and close a bounded day with
  durable reflection.
- **Backfill:** reconstruct an older experience while marking it as
  `reconstructed`, not contemporaneous capture.

It is not a hosted SaaS product, team project-management system, CRM, meeting
transcriber, or generic personal-life knowledge base.

## Implementation status

| Layer | Responsibility | Status |
|---|---|---|
| HLD-001 v3 | Harness-hosted local architecture, trust boundaries, capture, and future decisions | Implemented as design contract |
| LLD-01 | Vault, raw turns, revisions, amendments, entities, artifacts, WorkState, journals, SQLite, rebuilds, locking | Implemented |
| LLD-02 v3 | Portable Skill/SOPs, workflow contracts, CommitDraft validation/recovery, CLI boundary, harness capture, setup | Implemented |
| LLD-03 v3 | FTS5, local embeddings, vector search, hybrid retrieval, pagination, hydration, index lifecycle | Implemented as a rebuildable local projection; optional BGE semantic profile |
| LLD-04 | Question-bank normalization, interview practice, career retrieval, candidate marks | Contract documented; deferred |

The four LLDs consume one LLD-01 evidence model. Journals, WorkState, SQLite,
FTS, vectors, and career views are projections; raw turns and structured source
entries remain authoritative.

## Install

Work Brain requires Python 3.11+ and SQLite and has no runtime dependencies.
From a checkout:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

Choose a private vault outside this public repository. You can configure it
once for future commands:

```bash
work-brain config set-vault "$HOME/work-brain-vault"
work-brain init
work-brain doctor
```

The CLI resolves the vault in this order:

1. explicit `--vault PATH`;
2. `WORK_BRAIN_VAULT`;
3. local user configuration from `work-brain config set-vault PATH`;
4. a clear error.

The private path is never stored in this repository. A vault has one active
writer; do not run Codex, Claude Code, and Cursor against the same vault
simultaneously.

Run the tests from the checkout:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m compileall -q src examples
```

## Use the CLI directly

Agent-facing commands emit deterministic JSON. For legacy maintenance commands
use `--json` when a machine-readable response is needed.

```bash
# Vault and Skill diagnostics.
work-brain --json doctor
work-brain skills --workflow think --domain engineering

# Compact application operations for a host agent.
work-brain state current
work-brain work recent --limit 8
work-brain work loops --limit 20
work-brain evidence get --entry-id ENTRY_ID
work-brain recoverable

# CommitDraft may be read from stdin, avoiding shell quoting problems.
work-brain commit-draft --session-id SESSION_ID --workflow think < commit-draft.json
```

`evidence search` is the stable LLD-03 operation surface. It searches current
structured entries with deterministic chunks, SQLite FTS5, a local vector
adapter, and entry-level hybrid fusion:

```bash
work-brain evidence search --query "import reliability" --page-size 10
work-brain evidence search --query "changed direction after new evidence" \
  --filters '{"domains":["engineering"],"has_outcome":true}'
```

Results are bounded EvidenceCards with stable `{entry_id, revision}` refs and
an opaque continuation cursor. Hydrate at most four selected refs from the
authoritative source entry:

```bash
printf '%s\n' '{"refs":[{"entry_id":"ENTRY_ID","revision":1}]}' \
  | work-brain evidence hydrate
```

Use `work-brain reindex` after changing retrieval code or embedding settings.
`work-brain rebuild` also rebuilds the retrieval projection. Search excludes
superseded revisions and reports degraded or incomplete state instead of
presenting a false empty result.

### Semantic retrieval profile

The base install has a deterministic hash-vector fallback so it remains
offline-friendly and dependency-free. That fallback is useful for tests and
small demos, but it is not a production-quality semantic model. Its hit count
is only a diagnostic baseline because it changes with the exact smoke wording.
For normal semantic use, install the optional local BGE profile:

```bash
python3 -m pip install -e '.[semantic]'
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The profile uses FastEmbed with `BAAI/bge-small-en-v1.5`; its first embedding
operation downloads and locally caches the model. When FastEmbed is installed,
it is selected automatically. Set `WORK_BRAIN_EMBEDDING=hash` to force the
deterministic fallback for offline tests or demos. The retrieval schema and
`evidence search` CLI contract are the same for both providers.

The semantic smoke cases use natural paraphrases and check only whether the
expected experience appears in the first three cards. FastEmbed is expected to
reach at least 5/6; that is a cheap regression signal, not evidence that
retrieval is production-ready. The six-item fixture is intentionally too small
and permissive to tune the model against. Run the smoke cases directly with:

```bash
PYTHONPATH=src python3 -m unittest tests.test_retrieval_quality -v
```

The FastEmbed case is skipped when the optional package is absent. Run cold
process and cache-warm timings against a private or synthetic vault with:

```bash
PYTHONPATH=src python3 examples/benchmark_retrieval.py \
  --vault /tmp/work-brain-synthetic --embedding hash
# Build the temporary vault's index with the real provider before benchmarking it.
WORK_BRAIN_EMBEDDING=fastembed work-brain \
  --vault /tmp/work-brain-synthetic reindex
PYTHONPATH=src python3 examples/benchmark_retrieval.py \
  --vault /tmp/work-brain-synthetic --embedding fastembed
```

The benchmark is diagnostic only. A resident daemon is intentionally not part
of LLD-03; model startup should be justified by measured user-facing latency.

For a broader, report-only evaluation, use the checked-in synthetic fixture:

```bash
PYTHONPATH=src python3 examples/evaluate_retrieval.py --embedding hash
WORK_BRAIN_FASTEMBED_CACHE=/tmp/work-brain-fastembed-model \
  PYTHONPATH=src python3 examples/evaluate_retrieval.py --embedding fastembed
```

That fixture contains 24 plausible evidence entries, overlapping distractors,
and natural queries whose `relevant_titles` may contain multiple acceptable
answers. It reports mean recall@3 and recall@5 plus each query's retrieved
titles. It is deliberately not a pass/fail benchmark: its purpose is to make
retrieval behavior inspectable before deciding whether a larger evaluation
corpus or a quality threshold is warranted.

For low-level/manual integration, the CLI also supports `init`, `rebuild`,
`reindex`, `session-start`, `turn`, `commit`, `commit-draft`, `recoverable`,
and `capture-hook`. Use `work-brain --help` for the complete syntax.

## Install the one canonical Skill

There is one authored Skill in `skills/work-brain`. Do not maintain separate
Codex, Claude, and Cursor copies. The setup helper exposes the canonical
directory and adds capture hooks without replacing unrelated settings:

```bash
work-brain setup codex
work-brain setup claude
work-brain setup cursor
```

Pass `--vault PATH` before `setup` if setup should also select the default
private vault in local user configuration:

```bash
work-brain --vault "$HOME/work-brain-vault" setup codex
```

Each command is idempotent. Use `--check` to inspect setup without changing it:

```bash
work-brain setup codex --check
```

The setup targets are:

```text
Codex + local Cursor Skill: ~/.agents/skills/work-brain
Claude Code Skill:         ~/.claude/skills/work-brain
Codex hooks:               ~/.codex/hooks.json
Claude Code hooks:         ~/.claude/settings.json
Cursor local hooks:        ~/.cursor/hooks.json
```

If an existing Skill path or settings file conflicts, setup refuses to
overwrite it. Review the reported warning and resolve it manually.

## Using Work Brain with Codex

1. Install Work Brain, configure/init the private vault, and run
   `work-brain setup codex`.
2. The canonical Skill is exposed at `~/.agents/skills/work-brain` and hook
   entries are added to `~/.codex/hooks.json`.
3. Start Codex normally from any project.
4. Verify that `work-brain` appears in Codex's available Skills UI/command.
5. Invoke it explicitly through the Skill, or let the Skill description match
   a request such as “help me think through this migration decision”.
6. For guaranteed exact Work Brain transcript capture, begin with:

   ```text
   work brain: think with me about whether we should move this process async
   ```

   Natural lifecycle aliases also activate the boundary when they are the
   first relevant prompt: `start my day` and `open my work journal` select
   `open-day`; `start work brain` starts a general Work Brain session. The
   explicit mid-conversation aliases `capture this` and `journal this` also
   activate capture without requiring a colon. Speech
   input may omit punctuation or change capitalization: `Work Brain, start my
   day` routes exactly like `work brain: start my day`.
8. During an active Work Brain session, ordinary follow-up prompts are captured
   without a prefix. `close my day` routes to `close-day`; after its visible
   response the host mapping is deactivated even when no new evidence needs a
   CommitDraft.
9. Codex executes sanctioned `work-brain ...` commands through its existing
   shell. Work Brain does not use MCP or start another LLM.

Codex lifecycle hooks observe `SessionStart`, `UserPromptSubmit.prompt`,
`Stop.last_assistant_message`, `SessionEnd`, and optional `Interrupt` events.
Hooks do not make model calls.

## Using Work Brain with Claude Code

1. Install Work Brain, configure/init the private vault, and run
   `work-brain setup claude`.
2. The same canonical Skill is exposed at `~/.claude/skills/work-brain` and
   hooks are added to `~/.claude/settings.json`.
3. Start Claude Code with `claude`.
4. Verify the Skill is visible. Claude may select it from its description, or
   invoke it explicitly with `/work-brain`.
5. For guaranteed exact capture, begin the durable conversation with the
   documented `work brain` activation prompt (punctuation is optional), or use
   `start my day` / `open my work journal` for the narrow open-day aliases.
6. Claude Code runs Work Brain operations through its normal Bash/shell
   capability; there is no MCP server in this v1 path.

Claude Code uses the same normalized start, user-prompt, assistant-stop, and
session-end contract. The SOPs and probes are not duplicated for Claude.

## Using Work Brain with Cursor

Work Brain v1 supports the **local Cursor Agent**. It does not support Cursor
cloud agents using a local `~/work-brain-vault`; remote vault access is a future
architecture decision.

1. Install Work Brain, configure/init the private vault, and run
   `work-brain setup cursor`.
2. Cursor reuses the canonical Skill at `~/.agents/skills/work-brain`.
3. Hooks are added to `~/.cursor/hooks.json`.
4. Open any project in Cursor Agent and verify Work Brain appears in the
   available Skills.
5. Let Cursor select it from the description or invoke it through the `/`
   Skill UI.
6. For guaranteed exact capture, begin with the explicit `work brain` prompt,
   `start my day`, or `open my work journal`.
7. Cursor executes Work Brain through its existing shell tool.

Cursor capture uses `sessionStart`, `beforeSubmitPrompt.prompt`,
`afterAgentResponse.text`, and `sessionEnd`. It intentionally does not use a
`stop` event for assistant text.

## How discovery, execution, and capture work

**Skill discovery.** A harness finds `SKILL.md` in its configured user Skill
directory. It initially sees the Skill name and description, then loads the
main instructions and relevant SOP/probe references progressively.

**Tool execution.** The Skill tells the agent which sanctioned logical Work
Brain operation to use. The harness already owns shell/terminal execution, so
the agent calls `work-brain state ...`, `work-brain evidence ...`, or
`work-brain commit-draft ...`. The agent never needs to understand SQLite,
FTS5, embeddings, journals, or vault internals.

**Capture.** Host lifecycle hooks send visible Work Brain turns to one shared
capture adapter. Ordinary coding chats remain inactive. Exact durable capture
starts only after `work brain`, an explicitly observed Work Brain Skill
invocation, or one of the exact activation aliases (`start my day`, `open my
work journal`, `start work brain`, `capture this`, `journal this`) at the
activation boundary. Ambiguous
phrases such as `think about this` remain inactive. Implicit behavior that a
hook did not observe is never labeled verbatim source.

**Storage and retrieval.** The CLI delegates to application/domain services.
LLD-03 keeps the same chunk corpus in FTS5 and local vectors, applies explicit
filters, fuses lexical and semantic candidates deterministically, and hydrates
only from authoritative source files. Harnesses and Skills do not choose FTS
versus vectors or receive raw scores, SQL, vectors, or internal paths.

## Optional voice interface: Yap

[Yap](https://github.com/latent-variable/Yap) is optional dictation and
read-aloud around whichever local harness you use. Work Brain itself does not
own the conversational model; Yap simply makes the host terminal easier to
use by voice.

Install on macOS with Homebrew:

```bash
# Install Homebrew first if needed: https://brew.sh
brew install --cask latent-variable/tap/yap
```

On first launch, download Yap's voice model and grant microphone/accessibility
permissions when macOS asks. Use Yap's configured dictate shortcut to enter the
initial `work brain:` activation prompt into Codex, Claude Code, or Cursor.
Use its read-aloud shortcut on the visible host response. Yap does not receive
direct access to the private vault and is not a Work Brain evidence store.

## Private vault and durability

```text
work-brain-vault/
  sessions/YYYY/MM/DD/<session-id>/
    session.json              # metadata and host/capture provenance
    turns.jsonl                # append-only visible Work Brain source
    entries/0001.json          # immutable structured revisions
  amendments/YYYY/MM/DD/<amendment-id>.json
  catalog/entities/<entity-id>.json
  catalog/artifacts/<artifact-id>.json
  journal/YYYY/MM/YYYY-MM-DD.md       # generated projection
  state/current.json                   # generated WorkState projection
  context/capture-mappings.json       # private operational host mapping
  questions/                            # private question banks
  career/marks.jsonl                   # future LLD-04 preference metadata
  index/work-brain.sqlite              # rebuildable private index
```

Turns are flushed before the next step is acknowledged. A failed CommitDraft
does not discard the raw transcript. Re-extraction and user correction create
immutable revisions. Journals, state, SQLite, and future retrieval indexes can
be rebuilt from source. A hook failure returns a structured error and does not
fabricate an assistant turn.

## Recovery and maintenance

```bash
work-brain recoverable
work-brain rebuild
work-brain doctor
```

An interrupted host session remains recoverable. A session is not committed
merely because the host process ended. The user or agent must explicitly resume,
repair, or close it through the supported Work Brain workflow.

## Testing and manual smoke checklist

Automated tests cover LLD-01 durability, LLD-02 v3 contracts, and LLD-03
retrieval: deterministic chunk/index generation, FTS/vector corpus alignment,
current-revision search, filters, pagination, hydration, degraded behavior,
reindexing, and no-score EvidenceCards. The default vector adapter is a
dependency-free deterministic local baseline; a higher-quality local embedding
provider can be injected behind the same adapter contract.

Manual checks should be run separately for each available local harness:

1. start a normal coding chat and confirm no Work Brain session is created;
2. start with `work brain:` and confirm the exact prompt is the first turn;
3. start a fresh host session with `start my day` and confirm it selects
   `open-day` while preserving the exact first prompt;
4. confirm a visible assistant response is appended exactly once;
5. send an ordinary follow-up without a prefix and confirm it is captured;
6. send `close my day` with no durable evidence and confirm the mapping closes
   while existing evidence remains unchanged;
7. complete a CommitDraft and confirm the session is committed/deactivated;
8. terminate the host and confirm the session is recoverable without a fake
   assistant response;
9. run `work-brain setup HOST` twice and confirm no duplicate hook entries;
10. run `work-brain setup HOST --check` and inspect reported paths.

Fixture-based support for Claude Code or Cursor is not a claim of runtime
testing on a machine where those hosts were not available.

## Design references

- [HLD-001 v3: Harness-hosted architecture](work-brain-hld-v3.md)
- [LLD-01: Core domain, vault, and persistence](work-brain-lld-01-core-domain-vault-persistence-v2.md)
- [LLD-002 v3: Runtime, Skill, capture, and CLI](work-brain-lld-02-agent-runtime-skills-session-orchestration-v3.md)
- [LLD-003 v3: Retrieval and index lifecycle](work-brain-lld-03-retrieval-fts-embeddings-index-lifecycle-v3.md)
- [LLD-04: Interview practice and career retrieval](work-brain-lld-04-interview-practice-career-retrieval-v1.md)
- [Future considerations](work-brain-future-considerations.md)
