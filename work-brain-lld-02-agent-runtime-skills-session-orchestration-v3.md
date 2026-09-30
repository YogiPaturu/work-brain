# Work Brain — LLD-002 v3: Harness Runtime, Skills, Capture, and CLI

**Status:** implementation contract before LLD-03  
**Supersedes:** `work-brain-lld-02-agent-runtime-skills-session-orchestration-v2.md`  
**Parent:** [`work-brain-hld-v3.md`](work-brain-hld-v3.md)  
**Sibling contracts:** LLD-01 remains source authority; LLD-03 v3 consumes the
  application retrieval boundary; LLD-04 remains deferred.

## 1. Purpose

LLD-002 v3 defines the Work Brain behavior hosted by an existing local coding
agent. Codex, Claude Code, and the local Cursor Agent provide the model,
conversation, context, shell, and agent loop. Work Brain provides a portable
Skill, deterministic local application operations, evidence persistence, and
thin capture adapters.

The normal v1 path is:

```text
host agent -> Work Brain Skill -> existing shell -> work-brain CLI -> application -> private vault
```

Work Brain MUST NOT make a second conversational LLM call in this path. MCP,
provider-specific adapters, model selection/fallback, and a Work Brain daemon
are not v1 dependencies.

## 2. Ownership

LLD-002 owns:

- Skill/SOP/probe loading and resource provenance;
- deterministic workflow selection;
- bounded logical Work Brain sessions;
- CommitDraft schema use, validation, repair, and recovery;
- host capture normalization and capture provenance;
- the documented agent-facing CLI operation contract;
- context/retrieval payload limits independent of a provider context window;
- communication privacy behavior;
- setup/linking and safe, additive hook installation.

LLD-002 does not own:

- raw source, entry, amendment, or projection schemas (LLD-01);
- retrieval internals, FTS, embeddings, vectors, or pagination (LLD-03);
- question-bank and candidate-mark persistence (LLD-04);
- a production conversational model port.

The existing `ConversationModel`, `ScriptedModel`, and standalone
`SessionOrchestrator` may remain for provider-free tests and future standalone
mode. They are not required for harness-hosted production v1.

## 3. Portable Skill package

There is one authored package:

```text
skills/work-brain/
  SKILL.md
  agents/openai.yaml
  references/sops/
  references/probes/
  references/schemas/
  references/tools/
```

`SKILL.md` MUST begin with standard `name` and `description` frontmatter and
MUST retain the Work Brain resource identity immediately after the frontmatter.
The loader scans the first few lines for the internal identity and therefore
supports both metadata layers. `agents/openai.yaml` is OpenAI-specific UI
metadata under `interface:`; the Skill and references remain provider-neutral.

The loader progressively loads exactly the core Skill, core conversation SOP,
one workflow SOP, and at most two normalized domain probes. Each resource has
a stable `WORK-BRAIN-* vN` identity recorded in `session.runtime.sops`.

SOPs use the selected Agent-SOP-compatible structure:

```text
Overview
Parameters
Steps
Examples
Troubleshooting
```

Parameters stay concise. SOPs describe logical workflows and constraints;
`references/tools/work-brain-cli.md` owns concrete command syntax.

## 4. Trust and CLI boundary

The supported Work Brain application interface is the CLI. The host may use
its normal shell to execute sanctioned commands, but the Skill MUST instruct
the agent not to access Work Brain SQLite, vector data, internal vault files,
generated projections, or ad-hoc SQL directly.

This is not a security boundary against a host that is already trusted to read
arbitrary permitted files. The Skill MUST NOT claim otherwise.

Agent-facing operations are deterministic JSON operations:

```text
state current
work recent
work loops
evidence search
evidence get
commit-draft
recoverable
capture-hook
```

The CLI resolves the private vault in this order: explicit `--vault`,
`WORK_BRAIN_VAULT`, optional user configuration, then a clear error. Agent
operations have stable non-zero error categories and do not mix prose into
JSON output. Structured CommitDraft input can be read from stdin.

Application services own validation, locks, and persistence; CLI handlers are
thin. Retrieval commands do not expose SQL or vector primitives. `evidence
search` delegates to LLD-03 once implemented and may report a stable
`unavailable` result before then.

## 5. Logical session lifecycle

The host agent may begin an explicit Work Brain conversation by invoking the
Skill or by sending a prompt beginning with `work brain:`. The capture adapter
activates before the model responds and appends the exact initial user prompt.
Subsequent visible user and assistant turns are captured by host lifecycle
hooks. The model does not need to call a Work Brain model adapter.

The logical state machine remains:

```text
IDLE -> ACTIVE -> COMMITTING -> COMMITTED
             \-> RECOVERABLE
```

An ordinary coding-agent conversation with no explicit activation MUST remain
outside Work Brain. `SessionEnd` or `Interrupt` removes the active mapping,
does not fabricate an assistant turn, and leaves an unfinished session
recoverable. Commit/close explicitly deactivates the host mapping.

Only one Work Brain writer may operate on a vault at a time. Existing LLD-01
lock and source-first semantics remain authoritative.

## 6. Capture port

All hosts normalize into one event shape:

```python
CaptureEvent(
    host: str,
    kind: "session_start" | "user_prompt" | "assistant_message" | "session_end" | "interrupt",
    host_session_id: str,
    text: str | None,
    host_model: str | None,
    recorded_at: str,
    explicit_activation: bool,
)
```

The shared `HarnessCaptureService` owns mapping, activation, exact turn
append, lifecycle cleanup, and runtime provenance. Host normalizers contain no
professional-evidence or persistence logic.

### Host mappings

| Host event | Normalized operation |
|---|---|
| Codex `SessionStart` | bookkeeping readiness |
| Codex `UserPromptSubmit.prompt` | exact user turn if active/activation |
| Codex `Stop.last_assistant_message` | exact assistant turn if active |
| Codex `SessionEnd` / `Interrupt` | deactivate and leave recoverable |
| Claude Code corresponding events | same normalized operations |
| Cursor `sessionStart` | bookkeeping readiness |
| Cursor `beforeSubmitPrompt.prompt` | exact user turn if active/activation |
| Cursor `afterAgentResponse.text` | exact assistant turn if active |
| Cursor `sessionEnd` | deactivate and leave recoverable |

Cursor MUST use `afterAgentResponse.text`; `stop` is not its assistant-text
source. Host transcript files are optional recovery aids, not canonical APIs.

Runtime provenance is stored in the existing LLD-01 session metadata:

```json
{
  "host": "cursor",
  "host_session_id": "...",
  "host_model": "...",
  "capture_fidelity": "verbatim",
  "capture_activation": "explicit",
  "capture_status": "active"
}
```

Operational host-to-Work-Brain mappings are private runtime state and are not
a second evidence schema.

## 7. CommitDraft and recovery

The host agent produces only the public CommitDraft shape. Work Brain supplies
entry/session IDs, UUIDv7 identity, timestamps, revisions, provenance, source
relationships, catalog IDs, and persistence. Validation rejects runtime-owned
fields, invalid source-turn references, unsafe communication output, and
workflow-incompatible payloads.

The raw transcript is durable before extraction. A failed or malformed draft
leaves the session recoverable. Repair attempts are bounded. Re-extraction
creates a revision without rewriting immutable raw turns. Communication
workflows MUST keep private evidence and internal retrieval mechanics out of a
shareable draft unless the user explicitly asks for them.

## 8. Context and retrieval payload limits

LLD-002 controls bounded logical session and payload size, but it MUST NOT
require a configured provider context window in the harness-hosted path. The
host owns its context window. Work Brain MUST:

- load instructions progressively;
- request bounded state/recent-work/search pages;
- hydrate only selected stable evidence references;
- avoid preloading the entire vault;
- preserve stable evidence references whenever retrieval influences a commit.

The retrieval tool contract remains harness-agnostic:

```text
get_current_state
get_recent_work
get_open_loops
search_evidence
hydrate_evidence
```

The host invokes these through CLI commands. No FTS, vector, or embedding
choice belongs in the Skill or a harness hook.

## 9. Setup contract

`work-brain setup codex|claude|cursor` MUST:

- expose the one canonical Skill using an idempotent link or equivalent copy;
- install additive host hooks without destroying unrelated settings;
- avoid duplicate hook entries on rerun;
- use absolute executable paths;
- report changes and warnings;
- support `--check`;
- refuse invalid or conflicting existing configuration rather than overwrite
  it wholesale.

User-level targets are:

```text
Codex + local Cursor: ~/.agents/skills/work-brain
Claude Code:         ~/.claude/skills/work-brain
Codex hooks:         ~/.codex/hooks.json
Claude hooks:        ~/.claude/settings.json
Cursor hooks:        ~/.cursor/hooks.json
```

The setup helper does not write the private vault path into Git or into the
Skill package.

## 10. Verification gates before LLD-03

The following must pass before LLD-03 implementation begins:

- portable frontmatter and internal resource provenance tests;
- canonical Skill symlink/copy exposure without content divergence;
- idempotent setup and safe preservation of unrelated settings;
- explicit/env/config vault precedence and clear failure without a vault;
- Codex, Claude Code, and Cursor fixture normalizers;
- inactive conversations produce no Work Brain session;
- explicit activation captures exact user/assistant order;
- abrupt termination leaves a recoverable session without fabricated text;
- hook failures cannot corrupt source data and hooks perform no LLM calls;
- no code path requires MCP;
- the existing LLD-01 and useful LLD-02 tests remain green;
- manual smoke checklist exists for all three hosts and distinguishes fixture
  contract coverage from runtime-tested hosts.

LLD-03 v3 must be cross-reviewed against this document and HLD-001 v3 before
its implementation starts.
