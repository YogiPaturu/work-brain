# Professional Second Brain — LLD-02: Agent Runtime, Skills/SOPs, and Session Orchestration

**Document ID:** `PSB-LLD-002`  
**Version:** `2`  
**Status:** Draft for sibling cross-review  
**Date:** `2026-09-30`  
**Parent HLD:** `PSB-HLD-001` v2  
**Sibling dependencies:** `PSB-LLD-001` v2, `PSB-LLD-003` v2, `PSB-LLD-004` v1  
**Implementation posture:** **Prescriptive with bounded local discretion**

## 1. Executive Summary

This LLD defines the local agent runtime that turns an always-available terminal into bounded professional-thinking sessions without requiring one enormous day-long model context.

The runtime owns session lifecycle, Skill/SOP selection and progressive loading, domain-probe selection, model/tool orchestration, context budgets, structured commit generation, commit repair, incomplete-session recovery, and explicit maintenance flows such as re-extraction. It consumes the persistence contracts from LLD-01 and the retrieval contracts that will be finalized by LLD-03.

The normal path deliberately uses one conversational model context per bounded session. User and assistant turns are persisted incrementally while the conversation is happening. When the session closes, the same active model context produces a compact structured `CommitDraft`; deterministic application code validates and resolves that draft into the authoritative `SessionEntry` contract owned by LLD-01. Normal commit therefore does not require a second full-transcript extraction call.

The design assumes Luna Max is the maximum normal model tier and explicitly forbids hidden escalation to a stronger model. It is designed to remain useful with weaker models by shifting repeatable work into deterministic routing, small progressive SOPs, domain probe packs, high-level application tools, schema validation, bounded retrieval, and local post-processing. This mitigates but does not eliminate the failure mode where a weaker model conducts a weaker conversation and therefore never elicits information that later processing cannot reconstruct.

No daemon, worker queue, or background agent is required. All correctness-sensitive work is synchronous with session interaction or explicit maintenance commands.

## 2. Effective Source Set

This LLD is governed by:

1. `PSB-HLD-001` v2 — Professional Second Brain High-Level Design.
2. `PSB-LLD-001` v2 — Core Domain, Vault, and Persistence Contract.
3. `RANQ-LLD-PROMPT-01` v3 — Low-Level Design Discovery and Authoring SOP used as the authoring process.
4. The approved design decisions established in the current project conversation, including:
   - OpenAI-compatible Skills are the reusable workflow package/discovery mechanism;
   - Agent SOP files are the procedural workflow format inside that package;
   - conversation/session is the ingestion unit;
   - day is the journal aggregation unit;
   - raw transcript retention does not repair information never elicited by a weak conversation;
   - strong SOPs/probe packs are therefore a first-class quality mechanism;
   - user judgment remains authoritative for career-story selection;
   - normal workflows must not consume stronger-model quota needed for coding.

No current external-service behavior is required to settle this LLD. Exact model/API names and SDK mechanics are implementation prerequisites rather than architecture decisions.

## 3. HLD Decisions Implemented Here

This LLD implements these parent-HLD decisions:

- bounded conversational sessions within an always-available local terminal;
- one professional evidence model shared by Think, Operate, Communicate, and Career;
- progressive Skill/SOP/probe guidance rather than one monolithic prompt;
- Luna Max as the maximum normal model tier;
- support for weaker models through stronger instructions and deterministic application behavior;
- high-level tools that hide raw SQL, FTS, vector, and persistence mechanics from the LLM;
- no required background jobs;
- normal structured commit from the existing conversational context rather than a second full-history model pass;
- raw-turn durability independent of later extraction success;
- local-first/private-vault trust boundary.

The following HLD invariants directly constrain this LLD:

- conversation quality is product quality;
- raw transcript preservation cannot recover questions the model failed to ask;
- raw source is persisted before derived interpretation;
- the agent must not choose a single “best” career story for the user;
- the day-level journal is continuously materialized after session commits and does not depend on close-day;
- the LLM must not generate arbitrary SQL or directly operate vector indexes;
- no private vault data belongs in the public Skill package or public repository fixtures.

## 4. HLD Decisions Outside This LLD

This LLD does not redefine:

- durable raw/session/entry/state/amendment schemas — LLD-01;
- FTS/vector chunking, candidate fusion, retrieval ranking, and source hydration internals — LLD-03;
- exact terminal command syntax, Yap integration, screen rendering, or shell UX — thin local adapter/implementer discretion;
- interview question-bank parsing/filtering, Career candidate marks, detailed interview-practice behavior, and career-specific projection rules — LLD-04;
- external GitHub/Google/WhatsApp integrations — future adapter/LLD when required.

This LLD may define the orchestration hooks those siblings consume, but MUST NOT invent their domain contracts.

## 5. Implementation Posture, Decisions, Assumptions, and Prerequisites

### 5.1 Implementation posture

This LLD is **prescriptive with bounded local discretion**.

The implementation MUST preserve:

- session lifecycle semantics;
- turn-persistence ordering;
- Skill/SOP progressive-loading behavior;
- the model/tool trust boundary;
- structured `CommitDraft` semantics;
- context-budget and rollover behavior;
- no-hidden-escalation model policy;
- bounded commit-repair behavior;
- recovery semantics for interrupted sessions;
- the LLD-01 source-first publication contract.

Private helper names, internal object decomposition, equivalent async/sync function factoring, and exact model-SDK wrapper mechanics remain local discretion.

### 5.2 Resolved decisions

- One writer process has at most one active conversational session at a time in v1.
- A session has one active workflow at a time, while its persisted `modes` list may contain multiple observed modes.
- Explicit user intent selects a workflow deterministically when possible; model routing is not required for phrases/commands that already identify the workflow.
- `SKILL.md` is a small control plane/router; detailed procedures live in `.sop.md` reference files.
- The SOP format inside the Skill follows the supplied Agent SOP convention: Overview, Parameters, Steps, constraints, and examples/troubleshooting where useful.
- Core conversation guidance and one workflow SOP are loaded at session start; domain probe packs are loaded lazily and selectively.
- The runtime normally keeps at most one domain probe pack active; at most two may be active when the conversation genuinely spans two domains.
- Normal session commit is emitted from the same model context used for the conversation.
- The model never generates authoritative IDs, revision numbers, timestamps, SQL, index operations, or filesystem paths.
- The runtime validates all model-produced structured data before persistence.
- Commit validation may be repaired by the same model a bounded number of times; structural failure never causes raw-turn loss.
- Post-commit persistence, journal/state projection, FTS/index updates, and embeddings do not require additional model calls.
- There is no automatic use of a model stronger than the configured normal model.
- Context pressure is handled by committing/rolling over into a new bounded session rather than indefinitely expanding the active model context.

### 5.3 Repository assumptions

- The chosen model adapter can support either native tool calling or an equivalently strict structured-output contract.
- The runtime can report or configure the model context-window limit and maximum output reservation.
- Skills and SOP references are available as local public-repository files.
- LLD-01 persistence operations are exposed through application ports rather than direct filesystem writes from the model.
- LLD-03 will expose compact retrieval operations with stable evidence references.

### 5.4 Implementation prerequisites

Before implementation freeze:

- select the implementation language/runtime;
- select the initial model adapter and verify its structured tool/output behavior with the configured Luna Max-or-weaker target;
- validate the Skill-loading strategy in the chosen local agent runtime;
- cross-review `CommitDraft` resolution with LLD-01;
- cross-review evidence-card/search/hydration/pagination contracts with LLD-03;
- cross-review Career question/mark tool additions with LLD-04.

These are implementation prerequisites, not current architecture blockers.

### 5.5 Implementer discretion

The implementer may choose:

- internal agent-loop library or a small custom loop;
- exact function/class names;
- exact prompt-template syntax;
- whether model token accounting uses provider-reported counts or a compatible local tokenizer;
- exact configuration-file serialization;
- exact retry backoff for transient model transport failures, provided it does not create unbounded repeated model calls.

## 6. Runtime Architecture

The runtime is a hexagonal application service with the following logical components:

```text
User/CLI adapter
     |
     v
SessionOrchestrator
     |
     +--> SkillLoader ---------> public Skill/SOP/probe files
     |
     +--> ContextPlanner ------> state/retrieval ports
     |
     +--> ConversationModel ---> configured LLM adapter
     |
     +--> AgentToolRegistry ---> high-level application tools
     |
     +--> SessionStore --------> LLD-01 persistence port
     |
     +--> CommitResolver ------> validates/resolves CommitDraft
     |
     +--> ProjectionHooks -----> journal/state/index updates
```

The model receives only high-level tools. It MUST NOT receive raw database handles, arbitrary shell access, direct filesystem mutation, or raw vector-index APIs in v1.

## 7. Public Skill and SOP Package

### 7.1 Required public layout

The public repository contains one initial professional-brain Skill:

```text
skills/
└── professional-brain/
    ├── SKILL.md
    ├── agents/
    │   └── openai.yaml
    └── references/
        ├── sops/
        │   ├── core-conversation.sop.md
        │   ├── think.sop.md
        │   ├── operate.sop.md
        │   ├── communicate.sop.md
        │   ├── career.sop.md
        │   ├── open-day.sop.md
        │   ├── close-day.sop.md
        │   └── backfill.sop.md
        ├── probes/
        │   ├── engineering.md
        │   ├── debugging.md
        │   ├── product.md
        │   ├── customer.md
        │   ├── sales.md
        │   ├── marketing.md
        │   ├── strategy.md
        │   └── leadership.md
        ├── schemas/
        │   └── commit-draft.md
        └── tools/
            └── agent-tools.md
```

No user-specific question bank, transcript, professional facts, private example, employer artifact, or vault path is included in this package.

### 7.2 `SKILL.md` responsibility

`SKILL.md` MUST remain compact. It owns:

- capability description and triggering conditions;
- workflow routing table;
- references to the core SOP, workflow SOPs, probe packs, schema, and tool contract;
- progressive-loading rules;
- rule that private user data is retrieved through tools rather than embedded in the Skill;
- rule that explicit workflow intent bypasses unnecessary model routing.

`SKILL.md` MUST NOT duplicate every SOP/probe instruction.

### 7.3 Instruction-resource identity

Each SOP/probe resource MUST declare a stable resource ID and integer version in its body, for example:

```text
PSB-SOP-CORE v1
PSB-SOP-THINK v1
PSB-PROBE-ENGINEERING v1
```

The runtime records loaded resource identities in `session.json.runtime.sops` using:

```text
<resource-id>@<integer-version>
```

Example:

```json
[
  "PSB-SOP-CORE@1",
  "PSB-SOP-THINK@1",
  "PSB-PROBE-ENGINEERING@1"
]
```

Versioning is required here because prompt/SOP provenance is a current debugging and evaluation requirement; it is not speculative protocol versioning.

## 8. Core SOP Contract

`core-conversation.sop.md` is loaded for every professional-brain session and MUST encode the common behavioral contract.

Its required behavior is:

- first understand the user's actual problem or intent;
- probe adaptively rather than asking a fixed questionnaire;
- optimize for high recall of valuable, high-decay professional information;
- prioritize reasoning, uncertainty, alternatives, evidence, ownership, decisions, changed beliefs, outcomes, and unresolved state when relevant;
- challenge vague or weak reasoning with questions about evidence, assumptions, failure modes, alternatives, reversibility, and what would change the user's mind;
- follow unexpected branches when they become more valuable than the original checklist path;
- accept `skip`, `not relevant`, `don't know`, `enough`, and equivalent signals without pressure;
- stop probing when the experience is sufficiently understood, questions would repeat, or the user asks to move on;
- preserve meaningful belief evolution rather than rewriting the final belief as though it was always held;
- avoid contrarianism for its own sake;
- avoid mechanically interrogating every `SessionEntry` field;
- distinguish user-stated facts from model inference;
- do not fabricate missing outcomes, metrics, dates, ownership, or certainty;
- do not expose hidden reasoning or require hidden chain-of-thought retention;
- treat retrieved context as evidence/context, not as permission to overwrite what the user currently says.

### 8.1 Coverage map

The model MAY maintain an internal lightweight coverage map while conversing:

```text
context
significance
contribution
reasoning
 evidence
alternatives/tradeoffs
decision/action
expectation
outcome
learning
state/open loops
artifacts
```

The coverage map is not a form and is not persisted. It is only used to choose the highest-value next question.

The SOP MUST instruct the model to ask: `What important information is likely to be forgotten, distorted by hindsight, or impossible to reconstruct from artifacts later?`

## 9. Workflow Selection and Mode Semantics

### 9.1 Workflow identifiers

V1 workflow identifiers are:

```text
think
operate
communicate
career
open-day
close-day
backfill
```

These are orchestration workflows, not persistence enums. LLD-01 persists open-string `modes` so future workflows can be added without source migration.

### 9.2 Selection precedence

Workflow selection follows this order:

1. **Explicit runtime/local-interface selection** supplied by the thin local adapter.
2. **Explicit natural-language intent** recognized deterministically from a configured alias table where unambiguous, e.g. `think with me`, `close my day`, `practice interview`.
3. **Continuation of the currently active workflow** when a session is already open.
4. **Small model-based classification** only when the user's intent remains ambiguous and classification materially changes the required SOP/toolset.
5. Default to `think` for an open-ended professional reasoning conversation when no stronger signal exists.

The runtime MUST NOT spend a separate model call merely to classify a request that is already explicit.

### 9.3 Active workflow versus persisted modes

One workflow SOP is active at a time to keep instructions small.

The session may accumulate multiple persisted mode labels if the conversation crosses concerns. Example:

```text
active workflow: think
persisted modes: [think, operate]
```

If the user materially changes workflow, the runtime MAY replace the active workflow SOP while keeping the same session only when the topic remains one coherent experience. If the new workflow represents a materially different topic, the runtime SHOULD commit the current session and start a new one.

## 10. Domain Probe-Pack Selection

### 10.1 Probe packs are guidance, not workflows

Probe packs provide domain-specific things to notice and useful questions; they do not define persistence semantics or mandatory questionnaires.

### 10.2 Loading rules

- No domain pack is mandatory at session start.
- If the opening request has an obvious domain, the runtime MAY load one pack immediately.
- Otherwise the core/workflow SOP starts without a domain pack.
- The agent may request a relevant pack when the domain becomes clear.
- Normally only one domain pack remains active.
- A second pack MAY be active for genuinely cross-domain reasoning, such as engineering + product or sales + strategy.
- More than two active domain packs are prohibited in v1; the runtime must replace lower-value packs rather than accumulate them.

### 10.3 Example probe concerns

Probe packs SHOULD cover concerns such as:

| Domain | Example concerns |
|---|---|
| engineering | requirements, architecture, scale, consistency, reliability, operational complexity, security, alternatives |
| debugging | symptoms, hypotheses, evidence, experiments, narrowing path, root cause, recurrence prevention |
| product | user problem, evidence, requested feature vs underlying need, prioritization, adoption, trade-offs |
| customer | stated request, underlying need, evidence, surprise, pattern vs anecdote, decision impact |
| sales | buyer, objection, decision process, trust, competition, response, conversion signal |
| marketing | audience, positioning, channel, message, hypothesis, experiment, signal |
| strategy | thesis, assumptions, alternatives, downside, reversibility, expected signal |
| leadership | responsibility, disagreement, influence, communication, reaction, outcome, learning |

These lists are prompts to notice signal; they MUST NOT force irrelevant questions.

## 11. Session Lifecycle State Machine

### 11.1 Logical states

The application runtime uses these logical states:

```text
IDLE
ACTIVE
COMMITTING
COMMITTED   (terminal transition before returning to IDLE)
RECOVERABLE (derived recovery state)
```

`RECOVERABLE` is not required as a new field in LLD-01 source files. It is derived when startup finds an unfinished session or a structurally incomplete commit.

### 11.2 Normal lifecycle

```text
IDLE
  |
  | initialize session
  v
ACTIVE
  |
  | close/rollover request
  v
COMMITTING
  |
  | entry published + session snapshot finalized
  v
COMMITTED
  |
  v
IDLE
```

### 11.3 Session initialization

Before the first model response, the runtime MUST:

1. acquire the LLD-01 vault write lock;
2. generate `session_id` and stable `entry_id` using the LLD-01 UUIDv7 convention;
3. establish `started_at` and `local_date`;
4. create/update `session.json` with `ended_at = null`;
5. select/load the core SOP and active workflow SOP;
6. persist the first user turn before sending it to the model.

The model does not control session identity.

### 11.4 Turn ordering

For every visible conversational exchange:

```text
user input
  -> append/fsync user turn
  -> model/tool loop
  -> produce visible assistant text
  -> append/fsync assistant turn
  -> await next user input
```

Internal tool calls and tool payloads are not raw conversational turns and are not required in `turns.jsonl`.

If retrieved evidence materially supports the final entry, the final commit MUST preserve stable source relationships as required by LLD-01/LLD-03.

### 11.5 Close transition

When the runtime decides to close the session:

1. stop accepting new user input into that session;
2. choose `ended_at` in memory;
3. request a structured `CommitDraft` from the existing active model context;
4. validate/repair the draft as specified in §17;
5. generate `commit_id` and resolve deterministic IDs/refs;
6. invoke the LLD-01 source-first entry publication;
7. after entry publication succeeds, atomically update `session.json` with `ended_at`, final modes/domains, model ID, and loaded instruction-resource IDs;
8. invoke LLD-01 state/journal projection and LLD-03 index hooks;
9. release the session as committed.

This ordering intentionally prefers a recoverable published entry over a closed session snapshot with no entry.

If a crash occurs after entry publication but before `session.json` is finalized, recovery MUST detect the published entry and repair/finalize the mutable session snapshot without generating another entry revision.

## 12. Session Boundaries and Automatic Rollover

### 12.1 Semantic boundary

A session SHOULD represent one coherent conversational unit such as:

- one architecture/design problem;
- one debugging investigation;
- one planning conversation;
- one customer/sales reflection;
- one interview practice question or coherent practice block;
- one historical experience during backfill.

A terminal process may remain open all day while many sessions start and end.

### 12.2 Topic-switch boundary

When the user moves to a materially unrelated topic, the runtime SHOULD commit the current session and begin another rather than retaining unrelated context for convenience.

### 12.3 Context-pressure rollover

The runtime MUST calculate a usable input budget from the model adapter's context-window limit and configured output reserve.

Default policy:

- reserve at least 15% of the context window for model output/tool arguments;
- keep loaded core/workflow/probe instructions below 15% of usable input where practical;
- keep hydrated historical retrieval context below 20% of usable input where practical;
- trigger rollover when the accumulated active transcript plus loaded context reaches 70% of usable input.

These percentages are configurable runtime defaults, not persisted source contracts.

At rollover:

1. commit the current session normally from its active context;
2. start a new continuation session;
3. seed the new session with the prior committed entry's compact title/summary/current decision/open loops plus stable entry reference, not the entire prior transcript;
4. preserve the same active workflow unless the user changed intent.

Rollover MUST NOT require summarizing the entire raw transcript into a new canonical source object.

## 13. Context Planning

### 13.1 Context sources

The model context may contain:

```text
base runtime/system instructions
+ professional-brain Skill control instructions
+ core conversation SOP
+ active workflow SOP
+ zero/one/two probe packs
+ compact current state when relevant
+ compact recent/retrieved evidence cards
+ hydrated evidence only when necessary
+ current session turns
```

### 13.2 Excluded by default

The runtime MUST NOT automatically inject:

- the entire vault;
- all logs for the day;
- all SOPs;
- all probe packs;
- all interview question banks;
- full historical transcripts;
- raw SQL/FTS/vector internals;
- unrelated project context.

### 13.3 Read-before-hydrate retrieval pattern

Historical evidence SHOULD be retrieved in two stages:

```text
search -> compact evidence cards -> hydrate only selected refs
```

LLD-03 owns exact card/chunk semantics. This LLD requires that a card be small enough to decide whether hydration is worthwhile and include a stable evidence reference.

### 13.4 State context

`operate`, `open-day`, and `close-day` normally receive compact current WorkState without a model search step.

`think` MAY receive a very small current-state snapshot when it helps orient the discussion, but SHOULD NOT preload broad history.

## 14. Agent Tool Contract

### 14.1 Tool design principles

Tools exposed to the model MUST:

- represent user/application intent rather than storage mechanics;
- return compact typed results;
- include stable IDs/references where later provenance may matter;
- validate all parameters deterministically;
- expose no arbitrary SQL, filesystem path write, shell, or vector API;
- minimize the number of distinct tools a weaker model must choose among.

### 14.2 Core read tools

The initial logical tool surface is:

```text
get_current_state(filters?)
get_recent_work(scope)
search_evidence(query, filters, page_size, cursor)
hydrate_evidence(refs)
```

Ownership:

- `get_current_state` consumes LLD-01 WorkState;
- `get_recent_work` is an application convenience operation over LLD-01 metadata/current entries and may later delegate search details to LLD-03;
- `search_evidence` and `hydrate_evidence` are owned concretely by LLD-03.

The model MUST NOT choose whether a query is SQL, FTS, vector, or hybrid; the application/retrieval layer decides.

### 14.3 Write tools

V1 write tools are phase-gated:

```text
commit_session(draft)
record_amendment(target, statement, source_turns)
```

`commit_session` is enabled only during the runtime's `COMMITTING` phase.

`record_amendment` is enabled only when the user has explicitly corrected existing durable evidence and the target has been resolved. It MUST NOT be used for ordinary reinterpretation.

The model does not directly write journal, WorkState, SQLite, FTS, vector, session files, or amendment files.

### 14.4 Extension tools

LLD-04 adds Career-specific question-bank and candidate-mark tools. Any extension tool MUST be added to the relevant workflow tool profile rather than globally exposing every tool to every session.

## 15. Toolset Profiles

The runtime loads the smallest useful toolset for the active workflow.

| Workflow | Default read tools | Additional behavior |
|---|---|---|
| think | search/hydrate on demand; optional current state | no broad prefetch |
| operate | current state + recent work | search only when needed |
| communicate | recent work/search/hydrate | no external-send tool in v1 |
| career | search/hydrate + LLD-04 question/mark tools | pageable evidence results, explicit user story selection, no AI winner |
| open-day | current state + recent work | prioritize carryovers/commitments |
| close-day | current state + today's recent work | gap check, not full-day reconstruction |
| backfill | search/hydrate existing related evidence | `reconstructed` provenance |

The runtime MUST NOT expose a mutating external integration tool in v1.

## 16. Structured `CommitDraft` Contract

### 16.1 Purpose

`CommitDraft` is the model-produced semantic payload. It is not itself durable source and is not identical to LLD-01 `SessionEntry`.

The application resolves it into LLD-01 types and generates all authoritative metadata/IDs.

### 16.2 Runtime-owned fields

The model MUST NOT produce authoritative values for:

```text
session_id
entry_id
revision
commit_id
created_at
supersedes_revision
revision_reason
provenance_kind
contemporaneous occurrence start/end
runtime model/SOP metadata
new UUIDs
```

The runtime derives these from the active workflow/session and LLD-01.

### 16.3 Model-produced shape

The model emits:

```json
{
  "title": "Thinking through asynchronous submission generation",
  "summary": "Clarified that failure isolation, rather than latency alone, is the strongest reason to consider asynchronous processing; deferred the change pending more evidence.",
  "historical_occurrence": null,
  "domains": ["engineering"],
  "sections": {
    "context": [],
    "observations": [],
    "significance": [],
    "contribution": [],
    "reasoning": [],
    "evidence": [],
    "alternatives_tradeoffs": [],
    "decisions_actions": [],
    "expectations": [],
    "outcomes": [],
    "learning": [],
    "open_questions": []
  },
  "state_changes": [],
  "entity_candidates": [],
  "artifact_candidates": [],
  "source_entry_refs": []
}
```

### 16.4 Statement draft

Each `sections.*` element uses the LLD-01 Statement semantics:

```json
{
  "text": "Failure isolation is the primary concern, not latency alone.",
  "basis": "stated",
  "source_turns": [5, 6]
}
```

Validation MUST ensure referenced turn sequences exist in the active session.

### 16.5 Historical occurrence

For a normal contemporaneous session:

```text
historical_occurrence = null
```

The runtime maps the session's `started_at`/selected `ended_at` to the final entry occurrence.

For `backfill`, `historical_occurrence` MUST contain an LLD-01 occurrence value. Approximate/unknown time is allowed; the model MUST NOT invent false date precision.

### 16.6 Domains

`domains` is an open lowercase-token list proposed by the model and normalized by the runtime. It SHOULD reflect actual subject matter rather than every loaded probe pack.

### 16.7 State-change draft

The model uses:

```json
{
  "operation": "create",
  "target_state_item_id": null,
  "kind": "task",
  "fields": {
    "title": "Run representative-query experiment",
    "status": "active",
    "next_action": "Run the evaluation against the representative query set"
  },
  "source_turns": [7, 8]
}
```

Rules:

- create operations omit `target_state_item_id`; the application generates the new stable ID;
- update/close/reopen MUST use an existing stable state-item ID returned by `get_current_state` or otherwise resolved deterministically;
- the runtime MUST NOT guess between ambiguous state items based only on similar titles;
- the runtime maps each accepted draft to the exact LLD-01 `StateMutation` contract.

### 16.8 Entity candidate

An existing entity may be referenced by stable ID:

```json
{"entity_id":"<uuid>"}
```

A new candidate uses:

```json
{
  "entity_id": null,
  "kind": "project",
  "canonical_name": "Ranq",
  "aliases": []
}
```

Resolution rules:

1. reuse an exact stable ID when supplied and valid;
2. reuse one unambiguous normalized canonical/alias match of the same kind;
3. create a new entity when there is no match;
4. fail validation on ambiguous multi-match rather than silently merging identities.

### 16.9 Artifact candidate

Artifact candidates follow the same principle: existing stable ID when known; otherwise enough type/label/locator metadata for the LLD-01 artifact resolver to create one. The model MUST NOT fabricate an artifact URL/path it was not given.

### 16.10 Source-entry refs

When prior professional evidence materially influenced the conversation/commit, the model may emit:

```json
{"entry_id":"<uuid>","revision":2}
```

The runtime validates that the reference exists. LLD-01 stores it as an `entry` source reference.

## 17. Commit Validation, Repair, and Publication

### 17.1 Validation stages

`CommitDraft` validation occurs in this order:

1. structural JSON/tool-schema validation;
2. title/summary/string limits and normalization;
3. source-turn existence and provenance validation;
4. section/basis validation against LLD-01;
5. historical-occurrence rule validation;
6. state-item target validation;
7. entity/artifact resolution;
8. source-entry reference validation;
9. conversion into the exact LLD-01 `SessionEntry` revision request.

### 17.2 Repair loop

If the model emits an invalid draft:

1. return a compact machine-readable validation error to the same active model context;
2. ask it to repair only the invalid structured payload;
3. allow at most **two** repair attempts after the initial invalid attempt.

The repair prompt MUST NOT resend the entire session transcript because the active model context already contains it.

If the third total attempt remains invalid, the runtime MUST:

- leave the raw session intact;
- leave `ended_at` unset unless an entry was actually published;
- surface the session as `RECOVERABLE`;
- avoid fabricating a partial structured entry;
- permit later resume or explicit re-extraction.

### 17.3 Normal publication

On valid draft:

- runtime assigns authoritative metadata;
- LLD-01 publishes immutable entry revision 1 with `revision_reason=initial_commit`;
- runtime finalizes `session.json` only after successful entry publication;
- state/journal/index reconciliation follows LLD-01 source-first ordering.

## 18. Re-extraction Flow

Re-extraction exists because extraction/schema/SOP quality can improve even when the original conversation cannot.

An explicit maintenance action MAY reprocess a committed raw transcript using the current configured model/SOPs.

Flow:

```text
load raw turns
+ load current entry
+ load current extraction SOP/schema
-> model emits new CommitDraft
-> validate/resolve
-> publish next revision with revision_reason=reextract
```

Rules:

- re-extraction is explicit, not background;
- it creates a new `commit_id` and next revision;
- it MUST NOT alter raw turns;
- it MUST NOT claim to recover information that the original conversation never elicited;
- affected journal/state/search projections are rebuilt from the new current revision.

## 19. Explicit Correction / Amendment Flow

### 19.1 Trigger

An amendment flow is permitted only when the user explicitly corrects existing evidence, for example:

```text
"That number yesterday was 12%, not 20%."
```

The runtime/model must resolve the target entry/entity/artifact before writing the amendment.

### 19.2 Source capture

The correction itself occurs in a normal raw session and is therefore preserved as raw conversational source.

### 19.3 Amendment creation

After target resolution, `record_amendment` creates the immutable LLD-01 Amendment with the current correction session as `source_session_id`.

### 19.4 Applying the amendment

Applying an amendment to a structured entry is synchronous and may require one additional model call because the prior entry must be semantically revised without mechanically patching ambiguous prose.

Input is limited to:

```text
current target entry
+ amendment statement
+ minimal relevant source context if needed
+ current entry schema
```

The result is validated and published as the next entry revision with:

```text
revision_reason = user_correction
source_refs includes amendment ID
```

If semantic application fails, the amendment remains durable and visible as unapplied work; the previous entry revision remains current until a valid corrected revision is published. No raw source is lost.

## 20. Recovery of Interrupted Sessions

### 20.1 Startup detection

On writer startup, the runtime checks for sessions with:

- `ended_at = null`; or
- a published current entry but an unfinalized session snapshot.

### 20.2 Recovery cases

**Case A — raw session, no published entry**

Treat as `RECOVERABLE`. The user may resume the same session context or request commit/re-extraction from the raw transcript. The local interface owns the exact prompt/UX.

**Case B — entry published, `session.json` not finalized**

Repair the mutable session snapshot from the published entry and stored raw-turn timestamps. MUST NOT create another entry revision.

**Case C — malformed incomplete final JSONL line**

Use LLD-01 trailing-record recovery before model context is reconstructed.

**Case D — corrupted non-tail raw record**

Fail integrity validation and do not silently resume.

### 20.3 Model-context reconstruction

When resuming after process restart, the runtime may reconstruct the active model context from:

```text
core/workflow/probe resources recorded or current equivalents
+ compact relevant context
+ the recoverable session's raw visible turns
```

If the transcript is too large for current context policy, the runtime SHOULD commit/re-extract the recoverable session and continue in a new linked session rather than dropping arbitrary old turns.

## 21. Workflow SOP Contracts

### 21.1 Think

`think.sop.md` MUST:

- identify what the user is trying to decide/understand;
- surface assumptions and missing evidence;
- probe alternatives and trade-offs;
- test failure modes and reversibility when relevant;
- ask what evidence would change the user's mind;
- retrieve historical evidence only when it materially improves reasoning;
- allow the conversation to end with uncertainty rather than forcing a decision;
- commit the reasoning path, decision/current view, learning, and open questions that are worth preserving.

### 21.2 Operate

`operate.sop.md` MUST:

- begin from current WorkState when relevant;
- distinguish `where did I leave off?` from `what should I work on?`;
- reason about real commitments, blockers, waiting-on, dependencies, deadlines, importance, and next actions;
- avoid Jira-style process overhead;
- emit state changes only when the conversation actually changes operational state.

### 21.3 Communicate

`communicate.sop.md` MUST:

- treat private journal evidence as source material, not output to be copied wholesale;
- retrieve only the evidence/state needed for the requested audience/time period;
- distinguish user-stated/shareable facts from private speculation, sensitive customer/employer information, and model inference;
- preserve the user's intended meaning while minimizing unnecessary private reasoning;
- omit confidential URLs/identifiers, secrets, and private reasoning unless the user explicitly asks to include them in the draft;
- never treat an inferred statement as externally safe merely because it exists in a SessionEntry;
- generate a draft for user review and MUST NOT automatically send to an external channel in v1;
- keep audience/output templates as configurable reference material rather than durable evidence schema.

### 21.4 Career

`career.sop.md` MUST:

- accept an explicit interview question or obtain one through LLD-04's deterministic question-bank tools;
- use LLD-03 pageable evidence retrieval and make `more available` visible when the first page is not exhaustive;
- retrieve multiple plausible experiences rather than selecting one winner;
- explain possible relevance from evidence content without numeric story/quality scores;
- let the user choose the story/angle or explicitly request another page;
- hydrate only the evidence selected for preparation/critique;
- support LLD-04 `prepare` and `mock` practice flows without changing SessionEntry semantics;
- allow the user to mark/unmark an entry as an interview candidate through LLD-04;
- preserve new professional facts/learning from interview practice only when the user actually provides them;
- treat user career marks as preference metadata, not as evidence that an experience is objectively strong;
- defer question-bank normalization, mark persistence, and detailed interview protocol to LLD-04.

### 21.5 Open day

`open-day.sop.md` MUST:

- read current WorkState and compact recent work;
- surface carryovers, blockers/waiting, real commitments, and unresolved questions;
- ask what changed externally since the last work period;
- help establish intended outcomes for the day;
- commit only new plans/state/evidence rather than restating all retrieved history.

### 21.6 Close day

`close-day.sop.md` MUST:

- read today's committed entry cards plus current WorkState;
- act as a gap-detection safety net, not as the creator of the day's journal;
- ask whether anything important happened that the system did not discuss;
- capture unresolved outcomes, new blockers, changed beliefs, commitments, or missing events;
- remain optional for preservation correctness.

### 21.7 Backfill

`backfill.sop.md` MUST:

- set runtime provenance to `reconstructed`;
- distinguish remembered-at-the-time belief from hindsight knowledge when both appear;
- retrieve existing related evidence to reduce accidental duplication;
- prefer one coherent historical experience per durable session;
- if the user moves into an unrelated historical experience, commit and start another session;
- preserve uncertainty rather than inventing historical precision.

A backfill session MUST NOT mix an unrelated live contemporaneous event into the same durable entry. The runtime must split the session to preserve LLD-01 provenance semantics.

## 22. Model Adapter Contract

### 22.1 Required capabilities

The `ConversationModel` port must support:

```text
send conversational turns
receive visible assistant text
invoke/read high-level tools or strict equivalent structured actions
emit CommitDraft under a constrained schema
report/configure context-window and output limits
return stable model identifier for provenance
```

Hidden chain-of-thought access is not required and MUST NOT be treated as a product dependency.

### 22.2 Model selection

V1 has one configured normal conversational model.

- It may be Luna Max or a weaker model.
- The runtime MUST NOT silently escalate above the configured ceiling.
- A stronger model may only be used later through an explicit user/configuration choice, not automatic fallback.

### 22.3 Weak-model strategy

The runtime reduces weak-model burden by:

- deterministic workflow routing when possible;
- progressive SOP loading;
- small domain probe packs;
- high-level tools;
- deterministic IDs and state resolution;
- schema-constrained commit;
- deterministic validation/repair errors;
- bounded retrieval cards rather than raw corpus injection;
- local post-processing with zero model calls.

These measures improve consistency but do not guarantee strong probing. A model that fails to notice or ask about a material issue may leave the transcript permanently incomplete. This is an accepted v1 failure mode to be measured with real-session evaluation.

### 22.4 Transport failure

Transient model transport errors MAY be retried by the adapter with a small bounded retry count. The adapter MUST NOT duplicate already-persisted visible assistant turns or re-append user turns.

If a model call fails permanently, raw source remains valid and the session stays recoverable.

## 23. Token and Bandwidth Policy

### 23.1 Goals

The token policy exists to:

- avoid consuming model quota needed for normal coding work;
- keep latency low;
- keep weaker-model attention focused;
- avoid accidental all-history prompts.

### 23.2 Rules

The runtime MUST:

- avoid a separate classification call for explicit workflow intent;
- avoid a second full-transcript extraction call on normal commit;
- never load all SOP/probe files by default;
- never inject an entire question bank merely to select one question; use LLD-04 deterministic filters/get-by-ID;
- use retrieval cards before hydration;
- bound each retrieval page and model-context insertion without imposing a hidden total-result cap;
- perform persistence, indexing, journal rendering, and embeddings without an LLM;
- roll over long sessions rather than repeatedly re-sending an ever-growing day context.

### 23.3 Default retrieval insertion limits

LLD-03 v2 defines a default search `page_size` of 8 with continuation when more candidates remain. LLD-02 further limits what is inserted into the active model context:

- one normal search call requests the default 8-card page unless the workflow has a specific reason to change page size;
- automatic context insertion SHOULD include at most 5 cards from that page;
- automatic hydration SHOULD include at most 3 evidence refs;
- additional pages/hydration require an explicit model/user need;
- presence of `next_cursor` MUST be preserved so context limits are not mistaken for retrieval exhaustiveness.

These are context-management defaults, not retrieval-ranking guarantees or total-result caps.

## 24. Failure Semantics

| Failure | Required behavior |
|---|---|
| model unavailable before response | user turn remains durable; session recoverable |
| model emits malformed tool call | return structured tool error; do not mutate source |
| model emits invalid CommitDraft | bounded repair; then leave session recoverable |
| commit source publication fails | session remains uncommitted/recoverable |
| entry published, SQLite/journal/index fails | source remains valid; reconcile later per LLD-01 |
| session snapshot finalization fails after entry publish | repair snapshot on recovery; no duplicate revision |
| retrieval unavailable | continue conversation without pretending historical evidence was checked; user may proceed |
| probe pack missing | continue with core/workflow SOP; report configuration issue in diagnostics |
| ambiguous entity/state target | fail mutation resolution; do not guess |
| context budget exceeded | commit/roll over; do not silently drop arbitrary history |
| weak conversation misses key issue | accepted quality failure; cannot be repaired from absent information |

## 25. Security, Privacy, and Trust Behavior

### 25.1 Model-visible private data

The model may receive private professional evidence only when needed for the active user-requested workflow.

The runtime MUST minimize retrieval scope and MUST NOT preload the entire private vault.

### 25.2 Runtime logs

Operational logs SHOULD store metadata such as:

```text
session ID
model ID
instruction-resource IDs
model/tool latency
tool name
success/failure code
result counts
token counts when available
```

Operational logs SHOULD NOT persist full prompts, private transcript text, hydrated evidence text, or generated communication drafts by default because the authoritative source already exists in the vault.

### 25.3 External actions

No workflow in this LLD may directly send WhatsApp/email, mutate GitHub, update Google Sheets, or execute arbitrary network actions. Such actions require explicit future adapter/LLD contracts.

### 25.4 Communication boundary

`communicate` is a draft-generation workflow. Private/inferred reasoning is not automatically shareable merely because it exists in the journal. This LLD owns the v1 sanitization boundary; future outbound connectors may add stricter channel-specific controls.

## 26. Observability and Evaluation Evidence

The runtime MUST expose enough local diagnostics to evaluate model/SOP behavior without logging hidden chain of thought.

Per committed session, diagnostics SHOULD be able to report:

- model identifier;
- loaded SOP/probe resource versions;
- workflow/mode;
- domain labels;
- number of visible turns;
- retrieval tool calls and counts;
- context/token estimates where available;
- commit validation attempts;
- whether rollover occurred;
- commit success/failure;
- post-commit projection/index status.

Quality evaluation is separate from structural correctness. A session may commit valid JSON and still represent a weak conversation. Real-session smoke tests SHOULD therefore inspect questions asked, missing high-value evidence, and structured capture quality.

## 27. No-Background-Job Contract

V1 requires no scheduler, daemon, queue, or background agent.

All model work is triggered by:

- an active user conversation;
- explicit session close/rollover;
- explicit re-extraction;
- explicit correction/amendment application;
- explicit future maintenance command.

Journal/state/index work may run immediately after commit in the same process. A failure is repaired by explicit startup reconciliation, `doctor`, or `reindex`, not by a required resident worker.

## 28. Repository / Module Change Map

Because the implementation language is not yet frozen, this LLD defines logical modules rather than language-specific filenames.

```text
src/professional_brain/
├── application/
│   ├── session_orchestrator
│   ├── context_planner
│   ├── commit_resolver
│   ├── recovery_service
│   └── instruction_registry
├── domain/
│   ├── session_lifecycle
│   ├── commit_draft
│   └── tool_contracts
├── ports/
│   ├── conversation_model
│   ├── skill_loader
│   ├── evidence_retriever
│   ├── session_store
│   └── projection_hooks
└── adapters/
    ├── model/
    └── skill_filesystem/

skills/professional-brain/
└── ... as defined in §7
```

LLD-03 and LLD-04 may add adapters/ports without changing these ownership boundaries. A future interface/connector LLD may do the same when a concrete requirement exists.

## 29. Cross-LLD Contract Register

### 29.1 Contracts owned by LLD-02

| Contract | Consumers |
|---|---|
| session lifecycle states/transitions/finalization | LLD-01, local interface adapter |
| active workflow/mode-selection semantics | LLD-01, LLD-04 |
| Skill/SOP/probe package and progressive-loading rules | LLD-04 |
| instruction-resource provenance identity | LLD-01, diagnostics/evaluation |
| model-adapter capability/no-escalation contract | LLD-04 |
| context-budget and rollover policy | local interface adapter |
| high-level model tool surface and phase gating | LLD-03, LLD-04 |
| `CommitDraft` contract | LLD-01, indirectly LLD-03 |
| commit validation/repair behavior | LLD-01 |
| interrupted-session recovery orchestration | LLD-01 |
| re-extraction orchestration | LLD-01 |
| v1 communication draft sanitization boundary | local interface adapter |

### 29.2 Contracts consumed from LLD-01 v2

| Contract | LLD-02 usage |
|---|---|
| UUIDv7 identity | runtime requests session/entry/commit/new-state IDs through application/domain service |
| `turns.jsonl` | every visible turn persisted automatically |
| SessionEntry/Statement semantics | target of CommitDraft resolution |
| provenance kind | runtime fixes contemporaneous vs reconstructed |
| WorkState/StateMutation | operate/open-day/close-day and commit mutations |
| entity/artifact catalogs | stable semantic refs |
| amendments | explicit correction flow |
| source-first publication order | commit orchestration |
| daily journal semantics | close-day does not own journal generation |
| `resource-id@version` SOP provenance | session metadata |
| entry publication before `ended_at` finalization | close-state ordering |

### 29.3 Contracts consumed from LLD-03 v2

LLD-02 consumes:

- `search_evidence` request/filter/page/result shape;
- compact score-free `EvidenceCard`;
- stable `EvidenceRef`;
- `hydrate_evidence`;
- `next_cursor` / cursor-expiry semantics;
- explicit degraded/incomplete retrieval state;
- source-safe incremental index update behavior.

The runtime MUST NOT convert the first page into an assertion that no other candidates exist while `next_cursor` is present.

### 29.4 Contracts consumed from LLD-04

LLD-04 supplies:

- `QuestionRef`/normalized question-bank records;
- deterministic `search_questions`/`get_question`/question selection operations;
- durable user-authored CareerCandidateMark operations;
- `prepare` and `mock` interview-practice semantics;
- career overlay metadata that may decorate evidence cards without rewriting them.

### 29.5 Thin local interface boundary

A dedicated CLI LLD is not required for v1. Exact commands may map directly onto the application operations defined here. The adapter MUST NOT bypass session persistence, phase gating, model ceilings, or correction semantics.

## 30. Alternatives Considered

### 30.1 One day-long model conversation

**Rejected.** It continuously grows context, consumes quota, reduces model attention, entangles unrelated topics, and creates poor recovery boundaries. The terminal may remain open all day, but model sessions are bounded.

### 30.2 Separate extraction model call after every conversation

**Rejected as the normal path.** The active model already has the conversation in context. A final constrained CommitDraft is cheaper and avoids resending the transcript. Explicit re-extraction remains available when needed.

### 30.3 One giant SOP containing all modes and domains

**Rejected.** It wastes context and weakens instruction salience. A small Skill router + core SOP + one active workflow + lazy probe packs is the v1 contract.

### 30.4 Let the LLM decide SQL versus FTS versus vector

**Rejected.** Retrieval mechanics belong behind one application port. Requiring the LLM to choose infrastructure increases error rate and prompt complexity with no user value.

### 30.5 Let the model generate IDs and persistent state mutations directly

**Rejected.** Stable IDs, current-state identity, and persistence rules are deterministic application concerns. The model proposes semantics; application code resolves them.

### 30.6 Automatically escalate difficult sessions to a stronger model

**Rejected for v1.** It violates the user's quota/bandwidth constraint. Model tier is explicit configuration, not an invisible runtime optimization.

### 30.7 Periodic background summarization/re-extraction

**Rejected for v1.** There is no correctness requirement for a daemon. Explicit commit/reextract/reindex keeps the system local, observable, and simple.

### 30.8 Persist every tool call/result as raw source

**Rejected as a requirement.** LLD-01 defines raw conversational source as visible user/assistant turns. Material external evidence is preserved by stable references; full tool payload logging would create unnecessary privacy and storage surface.

## 31. Requirement-to-Evidence Traceability

| Requirement / invariant | Test or evidence |
|---|---|
| explicit `think` intent needs no router model call | integration test records zero classification call |
| first user turn durable before model invocation | injected model crash after invocation start; user turn exists |
| assistant visible turn durable before next input | runtime test verifies append before prompt returns to input loop |
| internal tool call omitted from raw transcript | tool-heavy session fixture contains only visible turns in JSONL |
| progressive SOP loading | Think/engineering session loads core + think + engineering, not unrelated packs |
| max two domain packs | attempt third pack replaces/unloads lower-value pack rather than accumulating |
| no hidden strong-model escalation | adapter audit shows only configured model ID used across failures |
| normal commit uses active context | model-call trace shows no second transcript replay on successful session |
| invalid commit is bounded | fixture fails schema 3 times, session remains recoverable and no entry exists |
| model cannot invent persistent IDs | CommitDraft schema rejects authoritative ID fields/new UUID fields |
| ambiguous state target not guessed | two matching candidates cause validation error/no mutation |
| context pressure rolls over | small synthetic context limit commits session and opens continuation |
| close-day optional for journal | earlier session commits update journal with no close-day session |
| backfill is reconstructed | backfill commit yields LLD-01 reconstructed provenance |
| mixed unrelated live/backfill content split | orchestration test produces separate sessions/provenance |
| re-extraction preserves raw/source history | new revision created, raw turns unchanged |
| correction preserves original source | amendment + user-correction revision exist; original turn/revision unchanged |
| retrieval outage is explicit | Think continues with surfaced retrieval-unavailable state and no false claim of checking history |
| user `skip/enough` stops probing | behavioral smoke test verifies agent moves on without repeated pressure |
| weak-model structural errors cannot corrupt store | fuzzed CommitDrafts fail validator before LLD-01 publication |

## 32. Ordered Implementation Plan

### Step 1 — Implement lifecycle/value contracts

Implement workflow identifiers, runtime lifecycle states, `CommitDraft` types/validators, and tool error/result envelopes.

**Gate:** normative fixtures in §§9, 11, 16, and 17 validate; invalid authoritative IDs/tool states are rejected.

### Step 2 — Implement Skill/SOP filesystem loader

Implement `SKILL.md` discovery, resource identity/version parsing, core/workflow/probe loading, and progressive-loading limits.

**Gate:** tests prove only required resources are loaded and runtime provenance records exact resource identities.

### Step 3 — Implement SessionOrchestrator against an in-memory model stub

Wire LLD-01 session initialization, user/assistant turn ordering, lifecycle transitions, and recovery detection without a real LLM.

**Gate:** crash-injection tests prove persisted-turn ordering and recovery semantics.

### Step 4 — Implement model adapter port and one configured adapter

Implement conversation/tool/structured-output support, model identity, context limits, and no-escalation configuration.

**Gate:** adapter contract test completes a synthetic multi-turn session and structured output using only configured model.

### Step 5 — Implement context planner and tool profiles

Add current-state/recent-work wiring plus placeholder retrieval adapter for LLD-03 contract tests.

**Gate:** workflow fixtures receive only their expected tool/resource sets and bounded context.

### Step 6 — Implement CommitResolver

Resolve statements, turns, state targets, entities/artifacts, runtime-owned metadata, and publish through LLD-01.

**Gate:** valid Think/Operate/Backfill drafts become exact LLD-01 entries; malformed/ambiguous drafts fail before source publication.

### Step 7 — Implement commit repair and incomplete-session recovery

Add bounded validation repair, entry-published/session-unfinalized repair, and raw-only recovery.

**Gate:** each failure case in §24 reaches the defined recoverable state without duplicate entry revisions.

### Step 8 — Implement context-pressure rollover

Add token/context accounting and continuation-session seeding from committed entry summary/source ref.

**Gate:** a forced-small-context integration test rolls over without losing raw evidence or injecting the full prior transcript into the new session.

### Step 9 — Implement re-extraction and amendment application

Add explicit maintenance flows using LLD-01 revision/amendment semantics.

**Gate:** revision history and raw transcript remain immutable; corrected/re-extracted revisions rebuild derived projections correctly.

### Step 10 — Cross-review with LLD-01 and LLD-03

Reconcile commit request/resolution, session finalization ordering, evidence-card/source-hydration, and index hook contracts.

**Gate:** cross-review reports no genuine conflict in shared contracts.

### Step 11 — Cross-review with LLD-04 before Career implementation

Confirm question-bank tools, career marks, pageable career flow, and interview-practice semantics. Communication privacy is already owned by this LLD.

**Gate:** LLD-04 can be implemented without reopening LLD-02 trust/session/model/communication decisions.

## 33. Objective Acceptance Criteria

LLD-02 is implementation-ready when:

- one terminal writer can create a session with LLD-01 IDs and durable raw turn ordering;
- explicit workflow intent bypasses unnecessary classification calls;
- `SKILL.md`, core SOP, workflow SOP, and relevant probe pack load progressively;
- the runtime never loads every workflow/probe pack by default;
- the model sees only high-level tools and cannot execute arbitrary SQL/vector/filesystem operations;
- normal session close produces a valid `CommitDraft` from the active conversation context without replaying the entire transcript through a second extraction call;
- the application, not the model, supplies authoritative IDs/timestamps/revisions/provenance;
- two repair attempts after an invalid draft are the maximum; further failure leaves a recoverable raw session;
- a published entry followed by session-snapshot failure repairs without duplicate revision;
- `think`, `operate`, `open-day`, `close-day`, and `backfill` satisfy the workflow contracts in §21;
- close-day remains optional for journal correctness;
- long sessions roll over before uncontrolled context growth;
- no normal or failure path silently escalates above the configured model ceiling;
- post-commit journal/state/index work performs no additional LLM call;
- re-extraction produces a new revision without rewriting raw source;
- explicit corrections produce amendments and user-correction revisions without rewriting original source;
- weak-model quality limitations are observable through evaluation data even when structure validates;
- LLD-01 and LLD-03 cross-review the shared commit/retrieval contracts before the core implementation baseline freezes.
- LLD-04 can plug question/mark tools into the Career profile without changing the core session or evidence schema.
- Communicate outputs are drafts and do not automatically expose inferred/private evidence.

## 34. Design Decision Register

| Decision | Status | Rationale |
|---|---|---|
| one bounded model session per coherent conversation | Resolved | preserves token efficiency and clean evidence boundaries |
| one active workflow SOP at a time | Resolved | keeps instruction context focused |
| max two active domain probe packs | Resolved | supports cross-domain work without instruction sprawl |
| OpenAI-compatible Skill as package/control plane | Resolved | provides reusable discovery/loading boundary |
| Agent SOP files inside Skill | Resolved | explicit procedural workflow format |
| same active model context emits normal CommitDraft | Resolved | avoids second full-history extraction call |
| model proposes semantics; runtime owns IDs/state resolution | Resolved | reduces weak-model burden and protects persistence integrity |
| no hidden model escalation | Resolved | preserves user quota/coding capacity constraint |
| session rollover rather than indefinite context compaction | Resolved | keeps active context bounded without losing raw source |
| at most two commit-repair attempts | Resolved | bounds token burn while allowing simple structural recovery |
| tool calls not part of raw transcript by default | Resolved | raw source is visible conversation; material evidence uses stable refs |
| explicit re-extraction only | Resolved | avoids background cost and silent reinterpretation |
| explicit amendment flow may use one extra model call | Resolved | corrections are rare and semantic patching should not be guessed mechanically |
| exact implementation language | Implementation prerequisite | does not change runtime contracts |
| exact LLD-03 retrieval page/card schema | Resolved by sibling | consumed as `EvidenceCard` + opaque continuation cursor |
| exact CLI command syntax | Implementer discretion | thin local adapter; no separate LLD in v1 |
| question-bank/mark details | Resolved by sibling LLD-04 | Career-specific extension over shared tools |

## 35. Documentation Drift / Consolidated Sibling Refinements

Version 2 incorporates the previously pending LLD-01 refinements: stable `resource-id@version` instruction identities and entry publication before `ended_at` session finalization. It also consumes LLD-03 v2 pageable search/card contracts. No live cross-sibling conflict remains at authoring time.

## 36. Consult, Blocker, and Validation Prerequisites

### Consult

None.

### Blocker

None for continued LLD authoring.

The implementation baseline MUST NOT freeze until LLD-01/03/04 cross-review confirms commit, pageable retrieval, question-bank, and career-mark contracts consumed by this runtime.

### Validation prerequisites

- verify the chosen model adapter reliably handles tool/structured output at Luna Max and at least one weaker target model;
- verify actual context/token accounting behavior of the chosen adapter;
- verify the local Skill loader can read the required references progressively;
- validate the behavioral SOPs against representative real/synthetic sessions before treating structural tests as quality evidence.

## 37. Final Coding-Agent Readiness Gate

A coding agent implementing this LLD should not need to invent:

- when sessions begin/end/recover;
- when user/assistant turns are persisted;
- how Skills/SOPs/probe packs are organized and loaded;
- how workflows and modes are selected;
- how long sessions stay bounded;
- which tools the LLM may call;
- which fields the model may or may not generate;
- how a model draft becomes an LLD-01 SessionEntry;
- how commit repair is bounded;
- how re-extraction and corrections differ;
- how model-tier limits are enforced;
- how weak-model limitations are treated;
- why no background jobs are required;
- which contracts remain owned by LLD-03/04/05.

The remaining unresolved implementation details are explicit prerequisites or sibling-owned contracts. After LLD-01/LLD-03 cross-review, this LLD can be frozen as the runtime/orchestration baseline.
