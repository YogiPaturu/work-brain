# Work Brain — HLD-001 v3

**Status:** v1 architecture baseline with LLD-03 implementation
**Supersedes:** [`archive/architecture-v2.md`](archive/architecture-v2.md)  
**Scope:** local Work Brain hosted by an existing coding-agent harness

## 1. Decision summary

Work Brain v1 is a local-first application hosted by an existing local agent
harness: Codex, Claude Code, or the local Cursor Agent. The harness owns the
conversational model, model selection, conversation context, agent loop, and
its built-in shell/terminal capability. Work Brain owns the private vault,
raw Work Brain evidence, structured entries, projections, retrieval, Skills,
SOPs, probes, deterministic CLI operations, and harness capture adapters.

The normal v1 path is:

```text
Codex / Claude Code / Cursor
            |
      Work Brain Skill
            |
    existing shell/terminal
            |
       work-brain CLI
            |
      Work Brain application
       /       |        \
    vault    state    retrieval
```

There is no second Work Brain LLM call behind the host agent. Work Brain is
model-provider agnostic in production. A standalone direct-LLM runtime may be
retained for tests and future experiments, but it is not a v1 dependency.

### Source and derived boundaries

Authoritative source consists of session metadata, append-only raw turns,
immutable `SessionEntry` revisions, amendments, and source catalog records.
Stable Experience identity is a catalog record; an Experience contains no
second copy of professional facts. Its membership is derived from explicit
`SessionEntry.entity_refs` with `relation=experience`. Journals,
ExperienceCards, `state/current.json`, SQLite, FTS, chunks, and embeddings are
rebuildable projections. Source publication is the success boundary: a
projection or retrieval failure is reported independently and never makes a
durably published entry look like an ordinary failed commit.

The application commit path is:

```text
validate -> plan catalog dependencies -> short source lock
         -> publish catalogs and immutable entry -> release source lock
         -> best-effort JSON/SQLite refresh -> best-effort retrieval indexing
```

The `.vault.write.lock` protects source mutations only. Embedding/model work
and derived index publication use `.index.write.lock`; index publication
rechecks source revision and hashes captured before embedding so stale work
cannot replace newer evidence. Raw session creation and turn append initialize
only the source store and do not open or migrate SQLite.

Search is read-only with respect to maintenance: it returns explicit
degraded/incomplete metadata and does not silently start a full reindex.

The product model is longitudinal rather than calendar-owned:

```text
raw conversation -> SessionEntry evidence -> Experience aggregation -> generated views
                                                   /        |        \
                                           communication  career   journal/time views
```

Calendar day and week are retrieval filters. Daily journals and open/close-day
workflows remain useful projections and compatibility conveniences, but no
evidence durability, recovery, or Experience construction depends on them.

Runtime lifecycle is represented as orthogonal capture, commit, and projection
states. Legacy flat runtime keys remain readable, but lifecycle writes use
centralized transition helpers.

MCP is not part of v1. It remains a possible future adapter only if Work Brain
becomes remote/hosted, a supported harness cannot execute the CLI, native
structured tools become materially preferable, or remote authentication and
authorization require a service boundary.

## 2. Goals and non-goals

### Goals

- preserve exact Work Brain conversation evidence in a private local vault;
- turn captured conversations into validated `CommitDraft` and LLD-01 entries;
- expose deterministic, high-level local operations through the CLI;
- provide one portable Skill with progressive SOP/probe loading;
- capture Codex, Claude Code, and local Cursor lifecycle events through one
  shared application service;
- keep ordinary coding conversations inactive unless the user explicitly
  activates Work Brain capture;
- preserve recoverability when a host session ends unexpectedly;
- keep all derived state and retrieval data rebuildable from source evidence.

### Non-goals for v1

- an LLM provider, model router, or model fallback owned by Work Brain;
- an MCP server;
- a Work Brain daemon or hot embedding process;
- cloud-hosted agents accessing a local vault;
- automatic capture of every coding-agent conversation;
- cloud sync, remote vault access, or separate host-specific evidence stores;
- LLD-04 implementation.

## 3. Ownership and boundaries

The host harness owns:

- the model and its selection;
- the host conversation context and visible response lifecycle;
- the agent loop and normal shell/terminal tool;
- host-specific lifecycle hooks.

Work Brain owns:

- private-vault source files and the single-writer lock;
- exact captured Work Brain turns;
- structured `SessionEntry` evidence, revisions, amendments, and provenance;
- WorkState, journals, and rebuildable SQLite projections;
- retrieval application operations and retrieval indexes;
- the canonical Skill, SOPs, probes, and commit schema;
- deterministic CLI validation, persistence, recovery, and diagnostics;
- thin host normalizers that translate hook payloads to the shared capture port.

The public repository contains code, publication-safe instructions, schemas,
fixtures, and synthetic examples only. User-specific professional data,
private questions, journals, raw turns, indexes, and artifacts remain in the
private vault outside the public repository.

## 4. Trust and security contract

The private vault is the authority and the trust boundary. Work Brain never
exposes raw SQL, vector primitives, arbitrary vault filesystem mutation, or
internal persistence operations as supported application commands. Agent
workflows MUST use documented `work-brain` CLI operations for Work Brain state,
evidence, retrieval, and maintenance.

This is an application-interface rule, not a sandbox guarantee. A fully
trusted Codex, Claude Code, or Cursor process may independently read or write
files permitted by the host. A Skill cannot prevent that. Stronger isolation
would require a real sandbox or service/MCP boundary and is deferred.

Only one Work Brain source writer may operate on a vault at a time. Running Codex,
Claude Code, and Cursor against the same vault simultaneously does not bypass
the existing LLD-01 lock or make concurrent writes safe.

## 5. Capture contract

Hooks are passive for ordinary coding conversations. A host conversation is
durably activated only when the initial user-prompt hook observes an explicit
activation boundary: a normalized leading `work brain` prompt, a narrow natural
activation alias, or an explicitly marked user Skill invocation. Skill
discovery/loading alone is not activation. Development prompts such as “edit
the Work Brain capture tests” remain ordinary coding work.

Activation happens before the host model responds, so the triggering prompt is
captured exactly. While active, user-prompt and visible-assistant hooks append
the exact observed text to the Work Brain session. Internal reasoning, shell
tool payloads, and reconstructed text are not labeled verbatim source.

The active mapping stores only operational host/session linkage in the private
vault. The Work Brain session's `runtime` metadata records:

```json
{
  "host": "codex",
  "host_session_id": "host-session-id",
  "host_model": "model-if-supplied",
  "capture_fidelity": "verbatim",
  "capture_activation": "explicit",
  "capture_status": "active"
}
```

`SessionEnd` and `Interrupt` remove the active mapping without fabricating an
assistant turn and leave the Work Brain session recoverable. An explicit close
or commit deactivates the mapping. Hooks perform no LLM calls and contain no
professional-evidence logic.

Host event mappings are:

| Host | Lifecycle events used |
|---|---|
| Codex | `SessionStart`, `UserPromptSubmit.prompt`, `Stop.last_assistant_message`, `SessionEnd`, optional `Interrupt` |
| Claude Code | `SessionStart`, `UserPromptSubmit.prompt`, `Stop.last_assistant_message`, `SessionEnd` |
| local Cursor Agent | `sessionStart`, `beforeSubmitPrompt.prompt`, `afterAgentResponse.text`, `sessionEnd` |

The adapters use documented host event payloads rather than scraping terminal
output. Host transcript files are optional debugging/recovery inputs, never a
canonical capture API without an explicit host guarantee.

## 6. Skill and CLI distribution

There is exactly one authored Skill:

```text
skills/work-brain/
  SKILL.md
  agents/openai.yaml
  references/sops/
  references/probes/
  references/schemas/
  references/tools/
```

`SKILL.md` uses portable Agent Skill frontmatter and retains a Work Brain
resource identity immediately after it. `agents/openai.yaml` contains only
OpenAI presentation metadata. SOPs and probes remain provider-neutral.

The harness discovers the Skill from user-level locations. During local
development, setup exposes the same canonical repository directory through:

- `~/.agents/skills/work-brain` for Codex and local Cursor;
- `~/.claude/skills/work-brain` for Claude Code.

`work-brain setup codex|claude|cursor` creates idempotent links and additive
hook entries, preserves unrelated settings, refuses unsafe overwrites, and
supports `--check`. Absolute executable paths are used in hook commands. The
installed hook command uses the dependency-light `python -m work_brain.hook`
entrypoint; `work-brain capture-hook` remains a compatible CLI adapter.

The CLI resolves a vault by explicit `--vault`, `WORK_BRAIN_VAULT`, optional
local user configuration, then a clear error. A private path is never stored
in the public repository.

## 7. Runtime and application operations

The host model selects or is explicitly given one bounded workflow. It reads
the Skill and relevant SOP/probe references, uses the CLI through the host
shell, and produces a `CommitDraft`. Work Brain validates and repairs the
draft, supplies runtime-owned IDs/timestamps/revisions/provenance, publishes
through the LLD-01 source-first protocol, and leaves failures recoverable.

The stable agent-facing operation surface is:

```text
work-brain state current
work-brain work recent
work-brain work loops
work-brain evidence search ...
work-brain evidence get ...
work-brain commit-draft ...
work-brain recoverable
work-brain capture-hook --host ...
```

All agent-facing operations provide deterministic JSON and stable non-zero
error categories. Application/domain code owns validation and persistence;
CLI handlers remain thin. CommitDraft input may be read from stdin so the
host does not need fragile shell quoting.

## 8. LLD decomposition

### LLD-01 — Core domain, vault, and persistence

LLD-01 remains authoritative for raw turns, sessions, entries, revisions,
amendments, entities, artifacts, WorkState, journals, source-first ordering,
locking, and rebuildable SQLite. Its existing `session.runtime` metadata is
the home for host and capture provenance. No new evidence schema is introduced
for harness integration.

### LLD-02 — Harness-hosted agent runtime and capture

LLD-02 v3 owns portable Skill/SOP/probe loading, workflow selection, bounded
logical sessions, CommitDraft validation/repair, recovery, harness capture,
capture provenance, CLI application contracts, bounded payloads, and
communication privacy. It does not require a production ConversationModel
port, provider adapter, model selection/fallback, provider context-window
accounting, or native model tool calling.

Existing `ConversationModel`, `ScriptedModel`, and standalone orchestrator code
may remain as test/future support. They must not be described as the normal v1
hosting path.

### LLD-03 — Retrieval and index lifecycle

LLD-03 v3 remains harness-agnostic. It owns FTS5, local embeddings, vector
search, fusion, pagination, hydration, staleness, reindexing, and retrieval
tests behind application operations. CLI calls may be separate OS processes;
LLD-03 must not assume an embedding model remains hot in one persistent Work
Brain process. Benchmark cold and OS-cache-warm query latency before considering
a daemon. No daemon is introduced preemptively.

### LLD-04 — Interview practice and career retrieval

LLD-04 remains deferred and consumes the shared LLD-03 evidence operations and
LLD-01 source model. It must not create a second evidence store.

## 9. Cross-review and readiness gate

Before LLD-03 implementation begins, HLD-001 v3, LLD-01, LLD-002 v3, and
LLD-003 v3 must agree on:

- source-first commit and rebuild ordering;
- session runtime host/capture provenance;
- exact-vs-reconstructed capture fidelity;
- the CLI operation and error boundary;
- stable evidence identity, hydration, pagination, and retrieval degradation;
- one-vault/one-writer behavior;
- public Skill/private vault separation;
- no MCP, daemon, standalone provider, or automatic global capture contract.

The readiness evidence must include unit tests for all three normalizers,
explicit/inactive capture, abrupt termination, setup idempotence and safe
settings merge, configured vault precedence, JSON CLI behavior, hook failure
safety, no LLM calls in hooks, and the complete LLD-01/previous LLD-02 suite.

Manual smoke testing of Codex, Claude Code, and local Cursor should be listed
separately from fixture-based contract tests. Unsupported cloud/remote agents
must not be presented as v1-compatible.

### Cross-review result for this checkpoint

| Contract | Decision | Authority / consumers |
|---|---|---|
| raw turns, revisions, source-first publication, one writer | unchanged | LLD-01 / LLD-02, CLI, capture service |
| host and capture provenance | use existing `session.runtime` metadata | LLD-01 / LLD-02, no new evidence schema |
| exact versus reconstructed capture | only hook-observed text may be `verbatim`; implicit/unobserved behavior is not | LLD-02 / capture adapters / README |
| supported Work Brain interface | deterministic CLI operations, not raw persistence primitives | HLD / LLD-02 / Skill / LLD-03 |
| retrieval ownership | host-agnostic application operation; FTS/vector choice stays in LLD-03 | LLD-02 / LLD-03 |
| process lifetime | CLI may be a separate process; no hot-model or daemon assumption | LLD-03 / README |
| future standalone runtime | optional future consideration only | HLD / future-considerations.md |

This matrix remains the cross-review baseline for LLD-03. The repository now
implements the retrieval contract as a foreground local projection; cold and
OS-cache-warm benchmark measurements remain an operational follow-up rather
than a reason to add a daemon or change the v1 process boundary.

The measurement is reproducible without private data:

```bash
PYTHONPATH=src python3 examples/benchmark_retrieval.py \
  --synthetic --embedding hash --query "authentication access control"
```

The command reports cold-process, first-query, and same-process cache-warm
latency. Results are machine-dependent and should be recorded with the host,
Python version, embedding provider, and vault size when used for deployment
decisions.
