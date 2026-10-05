# Work Brain

Work Brain is a local-first professional thinking and durable work-memory tool.
It helps you reason through decisions, recover current work state, prepare
communication, and practice interviews while preserving the underlying
conversation and structured evidence in a private vault.

## Quick start

For a user install, use `pipx` so the `work-brain` command is available on
your normal `PATH` without requiring an activated virtual environment. Install
`pipx` using your platform's package manager first; on macOS with Homebrew:

```bash
brew install pipx
pipx ensurepath

git clone https://github.com/YogiPaturu/work-brain.git
cd work-brain
pipx install ".[semantic]"
```

On systems where `pipx` is not provided by a package manager, install the
`pipx` tool with Python 3 and then use `pipx` for Work Brain:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
python3 -m pipx install /path/to/work-brain
```

`pip3 install work-brain` is not the recommended application install: plain
`pip3` does not provide pipx's isolated command environment and can leave the
launcher unavailable on the shell `PATH`.

Restart the shell after `pipx ensurepath` if `work-brain` is not immediately
found. The host hook setup records an absolute CLI launcher from the installed
environment, so hook execution does not depend on a shell's `PATH`.

Create a private vault outside the repository, initialize it, and connect your
coding-agent host. For Codex:

```bash
work-brain config set-vault "$HOME/work-brain-vault"
work-brain init
work-brain doctor
work-brain setup codex
work-brain setup codex --check
```

To see the current Work Brain lifecycle in the terminal:

```bash
work-brain status          # one-time human-readable dashboard
work-brain status --watch  # continuously refresh until Ctrl-C
work-brain status --quiet  # one-line prompt-friendly snapshot
```

The dashboard is read-only. It reports whether capture is active, how many
raw turns have been captured, when the last turn was saved, and whether a
structured commit is pending or complete. It never changes raw turns or
entries. To show the one-line snapshot before each zsh prompt, add this to
your `~/.zshrc`:

```zsh
source /path/to/work-brain/examples/work-brain-status.zsh
```

Or copy the small helper from
[`examples/work-brain-status.zsh`](examples/work-brain-status.zsh) into your
shell configuration.

This prompt hook runs when the shell redraws the prompt; it is not a
background daemon. The agent-facing Skill performs its own lifecycle check at
Work Brain boundaries, so the agent does not need to run `status --watch`.

Start a fresh Codex session, then try:

```text
work brain think with me about whether we should move this process async
```

Once Work Brain is active, ordinary follow-up messages are captured without a
prefix. You can also begin a day with `start my day` and finish with
`close my day`. See [Using Work Brain with Codex](#using-work-brain-with-codex)
for the exact capture and lifecycle behavior, or [Install the one canonical
Skill](#install-the-one-canonical-skill) for Claude Code and Cursor.

If you use another supported host, run the matching setup and verification
commands instead:

```bash
# Claude Code
work-brain setup claude
work-brain setup claude --check

# Cursor Agent
work-brain setup cursor
work-brain setup cursor --check
```

### Optional voice input with Yap

On macOS, Yap can provide dictation and read-aloud around the active host. It
does not connect directly to the Work Brain vault and does not replace Codex,
Claude Code, or Cursor:

```bash
brew install --cask latent-variable/tap/yap
open -a Yap
```

On first launch, download Yap's voice model and grant the requested
microphone/accessibility permissions. Focus the host terminal, use Yap's
configured dictate shortcut, and speak the same activation prompt shown above.
After activation, ordinary follow-up speech is captured without repeating the
`work brain` prefix. Yap's read-aloud shortcut can read the visible host
response back to you.

## Architecture overview

Work Brain is a local extension around an existing coding-agent host—Codex,
Claude Code, or the local Cursor Agent. The host owns the model, conversation,
context, agent loop, and shell. Work Brain owns the private evidence vault,
workflow instructions, retrieval, and deterministic persistence operations.
This keeps the tool lightweight: it does not start a second language-model
conversation and does not require an MCP server.

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

The important boundaries are:

- **Host agent:** owns the conversation and decides when to use Work Brain’s
  documented operations.
- **Skill and SOPs:** provide workflow guidance, focused probes, and the
  explicit activation boundary for durable capture.
- **CLI and application:** validate requests, manage bounded sessions, and
  expose state, evidence, retrieval, career, and commit operations.
- **Private vault:** remains the source of truth for exact turns and
  structured evidence; it is kept outside the public repository.
- **Projections:** journals, current work state, SQLite, retrieval indexes,
  and career views are rebuildable from the authoritative source.

Lifecycle hooks are passive during ordinary coding chats. They observe host
events and begin exact capture only after an explicit Work Brain activation
such as `work brain ...`, `start my day`, or `open my work journal`.

There is no second Work Brain LLM call and no MCP server in v1.

## What it is useful for

- **Think:** challenge assumptions, explore alternatives, and preserve why a
  decision was made.
- **Operate:** orient around current work state, recover tasks, blockers, open
  loops, commitments, and next actions, and manage the start/close-day
  lifecycle including clean capture deactivation.
- **Communicate:** turn private context into a concise audience-appropriate
  draft without exposing unrelated private evidence.
- **Career:** retrieve multiple plausible experiences for interview practice and
  let the human choose the story or angle.
- **Backfill:** reconstruct an older experience while marking it as
  `reconstructed`, not contemporaneous capture.

It is not a hosted SaaS product, team project-management system, CRM, meeting
transcriber, or generic personal-life knowledge base.

## What is implemented

The release includes one source-first evidence model with rebuildable journals,
current work state, and retrieval projections. It also includes:

- a local vault for exact conversation turns, structured evidence, revisions,
  amendments, entities, artifacts, and open work state;
- a host-integrated Skill, SOPs, bounded capture sessions, lifecycle aliases,
  CommitDraft validation, recovery, and setup for Codex, Claude Code, and
  Cursor;
- deterministic lexical search, optional local semantic embeddings, hybrid
  retrieval, pagination, hydration, and reindexing;
- deterministic question-bank lookup, interview preparation, mock practice,
  evidence retrieval, and explicit candidate marks.

The raw conversation and structured source entries remain authoritative.
Journals, WorkState, SQLite, retrieval indexes, and career views are
rebuildable projections.

## Install

Work Brain requires Python 3.11+ and SQLite. The base install has no runtime
dependencies and uses a deterministic local hash fallback for semantic
retrieval. Install the optional `semantic` extra to use FastEmbed/BGE locally.
The recommended user installation is:

```bash
brew install pipx                 # macOS/Homebrew; otherwise install pipx with Python 3 below
pipx ensurepath
pipx install "/path/to/work-brain[semantic]"
```

For development from a checkout, use an editable virtual environment instead:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[semantic]"
```

The editable virtualenv keeps the current source tree importable for tests and
development. It is not required for a normal user installation.

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
work-brain skills --workflow think --domain-tag engineering
work-brain migrate-domain-tags --dry-run
work-brain migrate-domain-tags

# Compact application operations for a host agent.
work-brain state current
work-brain work recent --limit 8
work-brain work loops --limit 20
work-brain evidence get --entry-id ENTRY_ID
work-brain recoverable
work-brain status --json
work-brain session turns --session-id SESSION_ID
work-brain session status --session-id SESSION_ID

# CommitDraft may be read from stdin, avoiding shell quoting problems.
work-brain commit-draft --session-id SESSION_ID < commit-draft.json
```

`session turns` is a read-only view of the append-only raw conversation for a
session. Use `--offset` and `--limit` to page through long sessions.
`session status` is a read-only health view showing lifecycle, turn count, last
captured turn, capture/commit status, and host-session mappings.
`status --json` is the auto-detected lifecycle view for the active host mapping;
the human-facing forms are `status`, `status --quiet`, and `status --watch`.
`session import --file transcript.json` is the explicit recovery path for a
user-supplied transcript whose original host capture was missed; it preserves
the supplied raw turns in a separately marked imported session.

`evidence search` is the stable retrieval operation. It searches current
structured entries with deterministic chunks, SQLite FTS5, a local vector
adapter, and entry-level hybrid fusion:

```bash
work-brain evidence search --query "import reliability" --page-size 10
work-brain evidence search --query "changed direction after new evidence" \
  --filters '{"domain_tags":["engineering"],"has_outcome":true}'
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

The optional `semantic` extra includes FastEmbed with the local BGE profile
`BAAI/bge-small-en-v1.5`. Install it when you want production-quality local
semantic retrieval; the first embedding operation downloads and locally caches
the model. The base install uses the deterministic hash-vector adapter, which
remains useful for tests, small demos, and offline environments.

```bash
work-brain reindex
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Set `WORK_BRAIN_EMBEDDING=hash` to force the deterministic fallback. The
retrieval schema and `evidence search` CLI contract are the same for both
providers.

Provider diagnostics are included in `work-brain --json doctor`, `reindex`,
and `evidence search` results under `embedding`. A normal installation reports
`provider: "fastembed"` and `status: "available"`. If FastEmbed is missing,
the result reports `provider: "hash"`, `status: "fallback"`, and a warning.
If the selected provider does not match the stored vectors, the result reports
`status: "degraded"` and `reason: "reindex-required"`.

The semantic smoke cases use natural paraphrases and check only whether the
expected experience appears in the first three cards. FastEmbed is expected to
reach at least 5/6; that is a cheap regression signal, not evidence that
retrieval is production-ready. The six-item fixture is intentionally too small
and permissive to tune the model against. Run the smoke cases directly with:

```bash
PYTHONPATH=src python3 -m unittest tests.test_retrieval_quality -v
```

The FastEmbed case is skipped when the optional extra has not been installed.
Run cold-process and
cache-warm timings against a private or synthetic vault with:

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
of the local runtime; model startup should be justified by measured
user-facing latency.

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

### Interview practice and Career retrieval

Career retrieval keeps two corpora separate: question banks answer “what might I be
asked?”, while committed Work Brain evidence answers “what actually happened?”
Question lookup is deterministic and never calls an LLM. The repository's
synthetic bank is safe for public smoke tests; private banks belong in the
vault's `questions/` directory or can be supplied with `--bank BANK_ID=PATH`.

```bash
work-brain --vault "$HOME/work-brain-vault" career \
  --bank synthetic=resources/questions/synthetic.md \
  questions search --tag-all conflict

work-brain --vault "$HOME/work-brain-vault" career \
  questions choose --tag-all ambiguity --seed 7
```

`career prepare` retrieves a bounded first page of plausible evidence and
returns an opaque continuation cursor. The user chooses the story and angle;
the system does not declare a “best story” or persist a story-quality score.
`career mock` asks the question first and does not reveal evidence suggestions
before the answer.

```bash
work-brain --vault "$HOME/work-brain-vault" career prepare \
  --question-text "Tell me about a difficult technical problem" --page-size 5
work-brain --vault "$HOME/work-brain-vault" career mock \
  --question-text "Tell me about a difficult technical problem"
```

Candidate marks are explicit private preferences, not evidence or model
judgments. The Skill may suggest one, but the application requires explicit
user intent before saving it; marks follow the stable entry ID across later
revisions:

```bash
work-brain --vault "$HOME/work-brain-vault" career candidates mark \
  --entry-id ENTRY_ID --note "Use the trade-off angle"
work-brain --vault "$HOME/work-brain-vault" career candidates list
work-brain --vault "$HOME/work-brain-vault" career candidates unmark --entry-id ENTRY_ID
```

For advanced/manual integration, the CLI also supports `init`, `rebuild`,
`reindex`, `session-start`, `commit`, `commit-draft`, `recoverable`,
`status`, `session status`, `session close`, `session quarantine`, and
`capture-hook`.
Raw-turn append is intentionally not exposed as a normal CLI operation. Use `work-brain --help`
for the complete syntax.

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
   activate capture without requiring a colon; their remaining text is routed
   normally rather than being forced into THINK. Speech
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

The canonical repository directory is also the installed development Skill
when setup creates a symlink. That makes edits immediately available to future
loads, but an already-running agent may still hold older instructions in its
context. After substantial Skill/SOP or routing changes, validate in a fresh
Codex/host session.

Skill discovery/loading is not capture activation. Editing, testing,
documenting, packaging, or installing Work Brain remains ordinary development
work and does not create a durable Work Brain session merely because the
repository or Skill is mentioned. Only an observed activation boundary starts
capture.

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

Capture activation is separate from bounded-session completion. A normal
`commit-draft` closes the current logical session and advances the host mapping
to a fresh bounded session, so one `start my day` activation can cover several
conversations. `finish this`, `that's enough`, and `save this` are completion
signals that keep capture active. `close my day` and `stop work brain` close the
current lifecycle and deactivate the host mapping, even when the close-day gap
check finds no new evidence.

**Probing and behavioral reminders.** Every session receives the core
conversation SOP plus one workflow SOP. The host may select zero, one, or two
domain probes based on the actual target and replace them when the topic
materially changes. Probes are compact conditional guides, not questionnaires;
the core SOP supplies cross-cutting reminders for decisions, outcomes,
ownership, open loops, changed beliefs, and useful artifacts. The repository
also includes transcript-style behavioral fixtures for architecture thinking,
explicit work-state updates, scoped communication drafts, multi-candidate
interview practice, uncertain backfill, and no-op close-day behavior. These are
contract/eval fixtures for a host model, not a claim that a fixed script is an
LLM benchmark.

**Storage and retrieval.** The CLI delegates to application/domain services.
The retrieval layer keeps the same chunk corpus in FTS5 and local vectors, applies explicit
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
  career/marks.jsonl                   # append-only user-authored career marks
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

Automated tests cover vault durability, runtime contracts, retrieval, and
Career behavior: deterministic chunk/index generation, FTS/vector
corpus alignment, current-revision search, filters, pagination, hydration,
degraded behavior, reindexing, no-score EvidenceCards, tagged question parsing,
explicit candidate marks, revision-stable preferences, and prepare/mock
boundaries. Transcript-style behavioral contract fixtures cover bounded
thinking, explicit state updates, scoped communication, career selection,
uncertain backfill, and no-op close-day behavior. The optional vector adapter
is the local FastEmbed/BGE provider; the base install uses a deterministic hash
baseline behind the same adapter contract for offline tests and minimal
environments.

Manual checks should be run separately for each available local harness:

1. start a normal coding chat and confirm no Work Brain session is created;
2. start with `work brain:` and confirm the exact prompt is the first turn;
3. start a fresh host session with `start my day` and confirm it selects
   `open-day` while preserving the exact first prompt;
4. confirm a visible assistant response is appended exactly once;
5. send an ordinary follow-up without a prefix and confirm it is captured;
6. send `close my day` with no durable evidence and confirm the mapping closes
   while existing evidence remains unchanged;
7. complete an ordinary CommitDraft and confirm the bounded session rotates
   while capture remains active; use `close my day` or `stop work brain` to
   confirm explicit deactivation;
8. terminate the host and confirm the session is recoverable without a fake
   assistant response;
9. run `work-brain setup HOST` twice and confirm no duplicate hook entries;
10. run `work-brain setup HOST --check` and inspect reported paths.

Fixture-based support for Claude Code or Cursor is not a claim of runtime
testing on a machine where those hosts were not available.

## Maintainer documentation

Design notes, implementation history, and future considerations live in
[`docs/`](docs/). They are optional reading for users who only want to install
and use Work Brain.
