# Professional Second Brain — High-Level Design

**Document ID:** `PSB-HLD-001`  
**Version:** `2`  
**Status:** Draft for LLD cross-review  
**Date:** `2026-09-30`  
**Architecture posture:** Local-first, hexagonal, model-efficient, user-controlled  

## 1. Executive Summary

This design defines a local-first professional second brain whose primary long-term payoff is interview and career preparation, while providing immediate day-to-day value as a thinking partner, lightweight work-operations assistant, and communication aid.

The system is built around continuous conversational use throughout the workday. Each conversation is captured verbatim, probed by an LLM using reusable SOPs, transformed into structured professional evidence, and indexed for later exact, lexical, and semantic retrieval. A daily journal is a human-readable projection over those conversations rather than the sole source of truth.

The initial product is a single-user CLI that may remain open throughout the day. It uses a configurable LLM with Luna Max as the maximum normal model tier, SQLite for structured metadata and full-text search, and local vector embeddings for semantic retrieval. The design deliberately avoids background infrastructure, cloud services, and heavyweight agent frameworks in the first implementation.

The architecture is hexagonal. Domain and application behavior depend on ports; local Markdown, SQLite, embeddings, terminal/Yap input, and the chosen LLM are adapters. This preserves a natural future path to web/mobile and AWS-hosted variants without designing those systems now.

The public repository contains application code, Skills/SOPs, schemas, migrations, synthetic examples, tests, and only publication-safe shared resources. Each user's private vault contains conversations, journals, current work state, career context, restricted/private question banks, career marks, artifact references, and the local search index. User data is never required to live in the public repository.

## 2. Purpose and Context

### 2.1 Product problem

Professionals leave behind durable work artifacts such as commits, PRs, documents, task lists, and messages, but those artifacts often fail to preserve the human context that becomes valuable later: reasoning, uncertainty, alternatives, disagreement, personal contribution, customer interpretation, expectations, mistakes, changes of mind, and eventual outcomes.

Traditional interview preparation attempts to reconstruct this material after the fact. The result is expensive, incomplete, and vulnerable to hindsight distortion.

This system instead captures professional evidence while work is happening and makes the capture itself useful immediately by acting as a rigorous conversational thinking partner.

### 2.2 Primary product thesis

The product should help the user think more clearly about work today while automatically building a durable record of professional experience for future career use.

The four initial projections are:

1. **Think** — reason through technical, product, customer, sales, marketing, strategy, and other professional problems with a curious, questioning partner.
2. **Operate** — maintain lightweight personal work state, priorities, blockers, commitments, and context recovery.
3. **Communicate** — transform richer private context into concise audience-appropriate updates, especially asynchronous team communication.
4. **Career** — retrieve and reconstruct experiences for interview preparation, practice, critique, CV/review material, and historical career backfill.

These projections MUST NOT define separate evidence stores. They are different ways of reading, probing, and projecting the same underlying professional evidence.

## 3. Scope and Non-Goals

### 3.1 In scope for the initial local product

- Single-user local CLI.
- Continuous use throughout the workday.
- Bounded conversational sessions within an always-available terminal experience.
- Verbatim raw conversation preservation.
- Structured session-entry extraction.
- Daily journal assembly from sessions.
- Lightweight current-work-state tracking.
- Historical career backfill from memory and artifacts.
- User-supplied interview question banks, with deterministic tag/text filtering.
- Interview-practice and career-retrieval workflows over the same professional evidence corpus.
- Durable user-authored interview-candidate marks that reference existing evidence without rewriting it.
- Hybrid retrieval using structured SQL access, SQLite FTS5, and vector similarity.
- Local embeddings.
- Rebuildable indexes.
- SOP/Skill-driven agent behavior.
- Domain-aware probe guidance for engineering, product, customer, sales, marketing, strategy, leadership, and future domains.
- Human-in-the-loop story/evidence selection for interview use.
- Public code repository with a separate private user vault.

### 3.2 Explicit non-goals for the initial product

- Team-wide project-management platform.
- Jira/Linear replacement.
- Full CRM.
- Calendar system.
- Meeting transcription product.
- Generic personal-life second brain.
- Collaborative editing of the user's private professional evidence.
- Hosted SaaS.
- AWS deployment.
- Mobile application.
- Direct WhatsApp integration.
- Full Google Sheets synchronization.
- Automatic ingestion of every GitHub artifact.
- Autonomous career-story ranking or selection of a single “best” story.
- Treating interview-question text as professional evidence or mixing question banks into the professional evidence index.
- Automatic model-derived career scoring/annotation as a v1 requirement.
- Continuous background agents or daemons.

Future versions MAY add some of these capabilities through adapters or new projections, but they MUST NOT create current contracts without a current requirement.

## 4. Effective Source Set

This HLD is governed by the design decisions established in the current design conversation plus the supplied HLD/LLD authoring conventions.

Key approved decisions from discovery include:

- Hexagonal architecture is preferred.
- Local CLI is the first implementation target.
- Future cloud/AWS hosting is a portability concern, not a current infrastructure requirement.
- The product is a professional second brain, not a generic second brain.
- Interview/career preparation is the primary long-term payoff.
- Thinking partnership and day-to-day operations provide immediate recurring value.
- Raw conversations are preserved verbatim.
- Conversation/session is the unit of ingestion; day is the unit of journaling.
- The daily journal is continuously built throughout the day and may include morning and end-of-day conversations.
- Structured entries are extracted after each committed conversation/session.
- SQLite provides structured operations and FTS5.
- Vector embeddings provide semantic retrieval.
- Retrieval should favor recall and user judgment rather than AI-selected “best” stories.
- Luna Max is the maximum normal model tier; the product should remain useful with weaker models through strong SOPs and bounded context.
- The public repository and private professional vault are separate.
- Question banks are a separate reference corpus from professional evidence. Publication-safe banks may be shipped in the public repository; restricted/private banks stay in the vault.
- Career retrieval is pageable: bounded pages protect model context, but there is no product-level hard cap that silently hides later candidates.
- A user may durably mark an entry as an interview candidate without changing the underlying professional evidence. Model-derived career annotations, if added later, remain replaceable projection data.
- The required v1 design set is LLD-01 Core Domain/Persistence, LLD-02 Agent Runtime/SOPs, LLD-03 Retrieval, and LLD-04 Interview Practice/Career Retrieval. A dedicated CLI LLD and connector LLD are not required for v1.

## 5. Known, Assumed, Open, and Validation Prerequisite State

### 5.1 Known

- One user owns and controls the professional evidence in the initial product.
- The system is local-first.
- The CLI may remain open throughout the workday.
- Raw conversational source material must be preserved.
- Conversation quality depends on model capability; raw transcript preservation cannot recover information that the model failed to elicit.
- Strong SOPs are therefore a core product mechanism, not merely documentation.
- SQLite, FTS, and vectors are complementary retrieval mechanisms.
- Query-time RAG means retrieving bounded relevant evidence and augmenting the LLM context rather than loading all historical logs.
- Interview-question banks can be queried cheaply by tags/text and do not need vector indexing at current scale.
- The current supplied question bank includes provenance categories that distinguish internal-bank, official-question, official-prep-prompt, official-derived, and official-exercise material; publication rights must therefore be evaluated per bank/source rather than assumed.

### 5.2 Assumed

- The initial user normally interacts through text, potentially produced by a local voice-to-text utility such as Yap.
- A typical user's corpus remains small enough that local SQLite and exact/brute-force or lightweight vector search remain operationally simple for years.
- A single local device is sufficient for the first version.
- User-specific professional data can be stored in a filesystem vault adjacent to, but outside, the public application repository.

### 5.3 Open

- Exact programming language and package choices for the first implementation.
- Exact local embedding model and vector-search library/SQLite extension.
- Exact CLI agent runtime and how it exposes Skills/SOPs and application tools to the configured LLM.
- Exact representation of amendments/corrections to structured entries.
- Exact question-bank interchange format.

These are LLD-level decisions unless later evidence shows that one changes an HLD invariant.

### 5.4 Validation prerequisites

Before implementation, verify:

- The selected local agent runtime's support for loading Skills/SOPs and exposing local tools.
- The local SQLite build supports FTS5.
- The selected vector adapter and embedding model work on the target laptop without requiring a background service.
- The selected model/runtime can emit reliable structured session-commit payloads under the expected token limits.

## 6. Design Goals and Architectural Principles

### 6.1 Preserve high-decay information

The system should preferentially capture professional information that is expensive or impossible to reconstruct later, including reasoning, uncertainty, alternatives, personal contribution, informal disagreement, customer interpretation, expectations, mistakes, and changes of mind.

### 6.2 Conversation quality is product quality

The system MUST treat probing quality as a first-class concern. A weak conversation cannot be repaired later merely because the transcript was preserved.

SOPs, examples, probe packs, and targeted context retrieval SHOULD reduce dependence on stronger models, but the architecture MUST NOT assume that instructions eliminate model-capability differences.

### 6.3 Preserve source before interpretation

Raw conversational turns MUST be durably appended as the conversation occurs. Structured interpretation MUST NOT be the only surviving representation.

### 6.4 Separate durable evidence from replaceable interpretation

Raw conversations and explicit user corrections are durable source evidence. Structured entries, journals, summaries, story mappings, and indexes may be regenerated as schemas, prompts, or models improve.

### 6.5 Keep the model context bounded

The application SHOULD remember state so the model does not need to repeatedly ingest large historical contexts. Skills/SOPs and probe packs SHOULD be progressively loaded based on the current task and domain.

### 6.6 Prefer deterministic local work after the conversation

Once a session commit payload exists, persistence, FTS updates, embedding generation, index updates, and deterministic state materialization SHOULD occur without additional LLM calls.

### 6.7 Human judgment over AI ranking

The system MAY use relevance scores internally to retrieve evidence efficiently, but Career workflows MUST NOT present an AI-selected winner as the authoritative “best story.” Relevant evidence should be surfaced with enough context for the user to choose.

### 6.8 Local-first privacy

Private professional evidence MUST remain outside the public repository. The local product SHOULD send only the bounded context required for the active LLM interaction to the configured model provider.

## 7. Settled Contracts and Invariants

### 7.1 Core information layers

The system has four conceptual information layers:

```text
L0 Raw Conversations
   Immutable/verbatim conversational source material and provenance.

L1 Structured Session Entries
   Current structured interpretation of professionally relevant content from a session.

L2 Daily Journal + Current Work State
   Human-readable chronological journal and operational materialized state.

L3 Derived/Searchable Knowledge
   SQLite metadata, FTS index, vectors, project/story mappings, summaries, and other replaceable projections.
```

L0 protects against bad extraction or future schema changes. It does NOT protect against a poor probing conversation that never elicited important information.

### 7.2 Ingestion and journaling units

- A **session/conversation** is the unit of ingestion and structured commit.
- A **day** is the unit of chronological journaling.
- Longer periods are derived views/summaries.
- End-of-day closure is useful but MUST NOT be required for data safety.

### 7.3 Raw conversation durability

- Each conversational turn MUST be persisted incrementally or otherwise durably enough that a process crash does not normally lose the whole session.
- Once a session is committed, its verbatim source MUST NOT be silently rewritten.
- User corrections to facts MUST remain distinguishable from the original source material.

### 7.4 Structured session entry

A committed session entry MUST be able to represent, when relevant:

- context/problem;
- observations/evidence;
- significance/stakes;
- user contribution/ownership;
- beliefs, hypotheses, assumptions, and uncertainty;
- alternatives and trade-offs;
- decisions/actions and rationale;
- expectations;
- outcomes/impact;
- learning or change of mind;
- current state/open loops/next actions;
- people/entities/projects;
- artifact references;
- provenance, including whether evidence is contemporaneous or reconstructed.

Not every session MUST populate every facet.

### 7.5 Epistemic history

The system MUST preserve meaningful belief evolution when present:

```text
initial belief -> challenge/new evidence -> updated belief
```

Later knowledge MUST NOT silently overwrite what the user believed or knew at the earlier time.

### 7.6 Current work state

Current state is a materialized operational view over explicit state-change evidence and user corrections. It MUST be rebuildable from durable evidence plus explicit amendments.

### 7.7 Index authority

SQLite relational indexes, FTS indexes, and vector indexes are derived and rebuildable. They MUST NOT be the sole authoritative store of professional evidence.

### 7.8 Public/private boundary

The public repository MUST contain only reusable product material such as:

- application code;
- Skills and SOPs;
- probe guidance;
- schemas;
- migrations;
- synthetic/demo fixtures;
- publication-safe shared question resources;
- public documentation;
- tests and tooling.

A private vault MUST contain user-specific or sensitive material such as:

- raw conversations;
- daily journals;
- current state;
- user career facts;
- company-specific internal context;
- private/restricted question banks;
- user-authored career marks;
- artifact references containing confidential URLs/identifiers;
- generated indexes/databases;
- credentials/secrets.

The public repository MUST NOT require inclusion of a user's private vault to function. A question bank MUST NOT be copied into the public repository merely because the application can load it; redistribution/publication safety is a property of that bank's source/provenance.

### 7.9 Question corpus is separate from professional evidence

Interview questions are reference inputs that ask, “What might I be asked?” Professional evidence answers, “What actually happened in my work?” These corpora MUST remain separate.

The question-bank layer MAY use deterministic tag/text filtering and does not require FTS/vector indexing in v1. A selected question MAY become an input query to professional-evidence retrieval, but question text MUST NOT be indexed as if it were user experience.

### 7.10 Projection metadata must not rewrite evidence

A projection MAY attach metadata to an existing stable evidence identity without changing the underlying SessionEntry. Two categories are distinct:

- **user-authored marks/preferences** — durable user intent such as “this is an interview candidate”;
- **model-derived annotations** — replaceable interpretations such as inferred interview capabilities or likely matching question themes.

User-authored marks are authoritative only as statements of user preference. Model-derived annotations are never authoritative professional facts and MAY be regenerated or discarded. V1 requires user-authored interview-candidate marks; automatic model-derived career annotation is optional/deferred.

### 7.11 Pageable retrieval without a silent total cap

Search MAY order candidates internally for efficient traversal, but Career-facing retrieval MUST support continuation/page traversal. Page size is bounded for token efficiency; the system MUST NOT imply that the first page contains every relevant experience when more candidates remain. Numeric relevance/story scores remain internal and MUST NOT be used to choose the user's story.

## 8. Target Architecture

### 8.1 Hexagonal architecture

```text
                         Agent / CLI
                             |
                      Application Layer
                             |
          +------------------+------------------+
          |                  |                  |
       Domain              Ports            Use Cases
          |                  |                  |
          +------------------+------------------+
                             |
     +-----------------------+-----------------------+
     |              |              |                 |
  Markdown       SQLite/FTS     Vector           LLM/Skill
  Adapter         Adapter       Adapter           Adapter
     |
 private vault
```

### 8.2 Domain concepts

The domain model centers on:

- `ConversationSession`
- `RawTurn`
- `SessionEntry`
- `DailyJournal`
- `WorkState`
- `OpenLoop`
- `Project/Context`
- `ArtifactReference`
- `QuestionBank` / `QuestionRef`
- `CareerCandidateMark` (user-authored projection metadata)
- provenance and user amendments

Exact language types and persistence shapes are delegated to LLDs.

### 8.3 Application use cases

Initial application use cases include:

- start/resume a session;
- run a Think interaction;
- run an Operate interaction;
- run a Communicate interaction;
- run a Career interaction;
- filter/select an interview question;
- page through relevant professional evidence for a question;
- mark/unmark an evidence entry as an interview candidate;
- commit a session;
- open a day;
- close a day;
- retrieve current state;
- retrieve recent work;
- search professional evidence;
- hydrate source evidence;
- backfill a historical experience;
- reindex derived stores;
- validate local data integrity.

### 8.4 Skills and SOPs

A reusable Skill package acts as the agent workflow entry point/control plane. SOPs define procedures within that skill. Probe packs and schemas are references loaded only when relevant.

Conceptually:

```text
professional-brain Skill
  |
  +-- core conversation SOP
  +-- think SOP
  +-- operate SOP
  +-- communicate SOP
  +-- career SOP
  +-- open-day SOP
  +-- close-day SOP
  +-- backfill SOP
  |
  +-- domain probe references
  +-- evidence schema references
  +-- retrieval/tool contract references
```

The exact packaging format is an adapter/runtime concern; the workflow semantics belong to the application contract.

## 9. Key Workflows and Interactions

### 9.1 Generic session lifecycle

```text
Start session
   |
Persist session identity
   |
Retrieve bounded relevant context
   |
Load core SOP + mode SOP + relevant probe pack(s)
   |
Conversation / probing / challenge
   |
Persist each raw turn
   |
User finishes or explicit commit
   |
Produce structured SessionEntry
   |
Persist structured entry
   |
Update journal/state
   |
Update SQLite/FTS/vector indexes synchronously
   |
Session ends
```

### 9.2 Think workflow

The Think workflow is intended for real-time reasoning, not retrospective note-taking.

The agent SHOULD:

- establish the actual problem;
- retrieve relevant prior context when useful;
- understand the user's current reasoning;
- question assumptions, evidence, alternatives, and failure cases;
- follow important branches rather than a fixed questionnaire;
- allow the user to decline or dismiss irrelevant probes cheaply;
- preserve meaningful evolution of thought;
- update state when the reasoning produces decisions or next actions.

### 9.3 Operate workflow

The Operate workflow reads current state, recent evidence, open loops, and explicit commitments to help the user recover context and decide what to do next.

The system MUST remain a lightweight personal operational layer rather than forcing heavyweight task-management ceremony.

### 9.4 Communicate workflow

Communicate transforms private evidence/state into audience-appropriate output. It MUST NOT require the team to access or collaboratively edit the user's private professional evidence.

For the initial Ranq use case, concise asynchronous updates suitable for simple-English team communication are a target output.

### 9.5 Career workflow

Career supports a concrete interview-preparation loop:

```text
filter/select question
        ↓
search professional evidence
        ↓
show a bounded page of candidate experiences
        ↓
user selects story / asks for more
        ↓
hydrate selected evidence
        ↓
practice / probe / critique
        ↓
optionally preserve new reflection or a user candidate mark
```

It also supports historical role/project backfill and later CV/performance-review/career-evidence synthesis.

The system MUST distinguish contemporaneous evidence from reconstructed historical evidence. It MUST NOT require a precomputed “story” object for an experience to be usable in interviews. A newly committed conversation can become useful immediately through general evidence retrieval; explicit user marking is an optional durable preference layer.

### 9.6 Open-day and close-day workflows

Opening a day SHOULD retrieve current state and recent trajectory rather than re-read all prior logs.

Closing a day SHOULD function as a gap check and operational-state reconciliation. If the user has used the system throughout the day, close-day should be brief. Missing a close-day session MUST NOT lose already committed work.

## 10. Data, State, and Retrieval Architecture

### 10.1 Filesystem vault

The private vault owns durable human-readable source and projection files, including raw conversations and daily journals.

A representative layout is:

```text
career-vault/
  conversations/YYYY/MM/DD/
  journal/YYYY/MM/YYYY-MM-DD.md
  state/current.md
  context/
  questions/
  artifacts/
  index/professional-brain.sqlite
```

Exact filenames and formats are delegated to the data/persistence LLD.

### 10.2 SQLite responsibilities

SQLite owns local structured query state and metadata needed for efficient retrieval and integrity checking. It also provides FTS5 lexical search.

Structured SQL access SHOULD handle exact filters such as:

- date/time ranges;
- project/context identity;
- open/closed state;
- outcome-known/unknown;
- provenance type;
- explicit entity relationships.

### 10.3 Lexical retrieval

FTS5 MUST index the same evidence corpus used by semantic retrieval so exact terms, names, identifiers, technologies, metrics, and phrases can be found reliably.

### 10.4 Semantic retrieval

Local embeddings MUST provide semantic similarity over the same evidence corpus. The exact embedding model and vector backend are delegated to the retrieval LLD.

### 10.5 Hybrid retrieval contract

The application exposes high-level retrieval operations to the agent rather than exposing raw SQL/FTS/vector mechanics.

Conceptual operations include:

- get current state;
- get recent work;
- get project context;
- get open loops;
- search evidence with optional structured filters;
- hydrate source evidence by stable identity.

`search evidence` MAY internally combine:

```text
structured filters
+ FTS lexical candidates
+ vector semantic candidates
+ deterministic candidate fusion
```

The exact fusion algorithm, ranking constants, page size, continuation contract, and internal ordering belong in the retrieval LLD.

### 10.6 Retrieval philosophy

Career retrieval SHOULD optimize for useful recall rather than aggressively hiding weaker candidates. Internal scores MAY order candidates for usability, but the interface MUST leave story/angle selection to the user. Search results MUST expose whether additional pages remain so a bounded first page is not mistaken for an exhaustive set.

### 10.7 Question-bank retrieval

Question-bank lookup is a separate lightweight path. V1 SHOULD parse configured question resources into normalized question records and support deterministic filtering by tags, source/provenance, company, capability, and text. It SHOULD NOT spend embedding or conversational-model budget merely to choose a question from a few hundred tagged prompts.

## 11. Model and Token-Efficiency Architecture

### 11.1 Model portability

All LLM behavior MUST go through an application port. No domain logic may require a specific model/provider.

### 11.2 Normal model ceiling

The normal product workflow MUST be designed to run with Luna Max as the upper model tier and SHOULD remain useful with weaker models.

### 11.3 SOP-first reliability

The product SHOULD move repeatable intelligence into reusable instructions, examples, probe packs, schemas, and deterministic application tools rather than repeatedly spending model tokens rediscovering process.

### 11.4 Bounded context assembly

Each session SHOULD receive only:

- compact core instructions;
- the active mode SOP;
- relevant domain probe references;
- compact current state;
- a bounded set of relevant prior evidence;
- the current conversation.

The full historical corpus and all SOPs MUST NOT be inserted into every model call.

### 11.5 Session commit efficiency

When supported by the runtime, the active conversation SHOULD produce the structured session-commit payload using the current session context rather than requiring a separate full re-read/extraction call.

If extraction fails or schemas later improve, the preserved raw transcript MAY be reprocessed later.

## 12. Security, Privacy, Trust, and Failure Behavior

### 12.1 Privacy boundary

Professional evidence may contain confidential employer, customer, technical, or career information. The private vault is therefore a trust boundary.

The initial product SHOULD:

- default to local storage;
- exclude vault data from the public repository;
- avoid unnecessary transmission of unrelated evidence to the configured LLM;
- avoid logging secrets in application logs;
- keep embeddings local in the initial design.

### 12.2 Process/session crash

Raw turns SHOULD be persisted during the conversation so a crash does not normally destroy the entire session.

If structured commit fails, the raw transcript MUST remain available and the session MUST be recoverable/reprocessable.

### 12.3 Index failure

Failure to update SQLite FTS or vectors MUST NOT destroy or invalidate the source conversation/session entry. Reindexing MUST be safe and idempotent.

### 12.4 Model extraction failure

The system MUST distinguish source capture from extracted interpretation. A malformed or incomplete structured payload MUST be rejected or marked incomplete rather than silently becoming authoritative evidence.

### 12.5 Poor probing/model failure

The system cannot reconstruct information that the conversation never elicited. This is an accepted product limitation. Mitigations include stronger SOPs, examples, probe packs, model evaluation, and optional use of stronger models for high-value sessions.

## 13. Scalability, Reliability, Operability, and Cost

### 13.1 Scale

The initial expected corpus—years of daily sessions and thousands of evidence chunks—is small relative to the capacity of local SQLite, FTS5, and lightweight vector search.

The design MUST NOT introduce distributed infrastructure merely for anticipated personal-history scale.

### 13.2 Reliability

Durability comes from preserving raw source and structured entries in the vault. Derived indexes remain rebuildable.

### 13.3 Operability

Initial maintenance should be explicit and local:

- `reindex` rebuilds derived indexes;
- `doctor` checks integrity/staleness/broken references;
- explicit synthesis commands may be added later.

No background daemon, cron job, queue, or scheduler is required for correctness in v1.

### 13.4 Cost

Primary variable cost is LLM usage. Architecture therefore prioritizes bounded retrieval, progressive instruction loading, same-session commit extraction, local embeddings, and deterministic post-processing.

Cloud storage/search cost is not a current concern because hosted infrastructure is out of scope.

## 14. Alternatives Considered and Tradeoffs

### 14.1 One giant daily conversation

**Rejected.** Keeping one continuously growing LLM context all day wastes tokens, degrades context quality, and couples unrelated discussions.

Selected approach: persistent terminal experience with bounded sessions and explicit retrieval between them.

### 14.2 End-of-day-only journaling

**Rejected.** It loses contemporaneous reasoning and forces memory reconstruction.

Selected approach: commit useful sessions throughout the day; end-of-day is only a gap/state pass.

### 14.3 Structured entries without raw transcripts

**Rejected.** It makes future schema/model improvements unable to reprocess source material and destroys conversational provenance.

### 14.4 Raw transcripts only

**Rejected.** Retrieval and daily operation become expensive and noisy; the model repeatedly has to reconstruct structure.

### 14.5 Vector-only retrieval

**Rejected.** Exact names, identifiers, acronyms, technologies, and metrics benefit from lexical and structured retrieval.

### 14.6 FTS-only retrieval

**Rejected.** Semantically related experiences may use very different wording.

### 14.7 LLM-generated arbitrary SQL

**Rejected.** It wastes model capability and creates unnecessary correctness/debugging risk.

Selected approach: high-level application retrieval tools implemented deterministically.

### 14.8 Dedicated OpenSearch/vector service for v1

**Rejected.** Personal corpus scale does not justify a service, daemon, ports, or distributed operational surface.

### 14.9 Separate databases for Think/Operate/Communicate/Career

**Rejected.** One professional experience may serve all projections. Separate schemas would duplicate and fragment evidence.

## 15. Repository and Vault Topology

### 15.1 Public repository

Representative structure:

```text
professional-brain/
  README.md
  pyproject.toml or equivalent
  src/
    professional_brain/
      domain/
      application/
      adapters/
  skills/
    professional-brain/
      SKILL.md
      agents/
      references/
        sops/
        probes/
        schemas/
        retrieval/
  resources/
    questions/              # only publication-safe/shared banks
  migrations/
  docs/
    architecture/
    design-notes/           # explicitly non-normative future ideas
  tests/
    unit/
    integration/
    retrieval-smoke/
  scripts/
```

The public repository SHOULD include a safe example vault with synthetic data sufficient for development and demonstrations. Generic future ideas such as Teach, Quiz, mobile capture, hosted/AWS, richer TUI, or connectors SHOULD live in `docs/design-notes/` until they become current requirements; their presence there MUST NOT create implementation contracts.

### 15.2 Private vault

The user vault MUST be separately configurable and git-ignored by default if located within the repository working tree.

Representative additional career/reference paths are:

```text
career-vault/
  questions/                # private/restricted question banks
  career/
    marks.jsonl             # user-authored career-candidate preferences
```

The repository SHOULD ship a template/example configuration but MUST NOT require user-specific data in source control.

### 15.3 Question-bank publication boundary

Private or restricted interview-question banks MUST remain in the user's vault and MUST NOT be assumed safe to publish merely because the application supports loading them.

The public repository MAY include synthetic/sample question packs, public-domain/licensed packs, or other publication-safe resources plus the question-bank parser/schema. The supplied multi-company bank is useful as a local reference and smoke-test source, but its provenance tags include exact/internal and derived material, so the architecture MUST NOT assume the entire file is safe to redistribute.

## 16. Migration, Activation, Rollout, and Rollback

The first implementation has no production migration requirement.

Initial rollout SHOULD proceed with a disposable/synthetic vault until the session lifecycle and persistence contracts are proven. The user's real historical backfill can then be imported incrementally.

Any future hosted/cloud migration MUST preserve the distinction between source evidence and derived indexes. A cloud design MUST NOT silently make a derived search index the only copy of professional evidence.

Exact local-to-cloud synchronization, multi-device conflict handling, encryption, identity, and tenancy are future HLD responsibilities rather than current extension points.

## 17. Risks, Consult Decisions, Blockers, and Deferred Decisions

### 17.1 Risks

- Weak model probing may miss valuable information at capture time.
- Overly large or generic SOPs may reduce weaker-model compliance rather than improve it.
- Structured extraction may accidentally convert inference into fact if provenance/evidence rules are weak.
- Continuous use may generate many low-value sessions unless commit logic distinguishes ephemeral conversation from durable evidence.
- User trust may be harmed if private thought is accidentally emitted in team-facing communication.
- Search recall may be insufficient if chunking or embedding quality is poor.

### 17.2 Consult

None required to begin LLD authoring.

### 17.3 Blockers

None at HLD level.

### 17.4 Deferred decisions

- Exact programming language.
- Exact vector backend/model.
- Hosted/AWS architecture.
- Mobile interface.
- Multi-device sync.
- Direct GitHub/Google Sheets/WhatsApp connectors.

## 18. LLD Decomposition and Cross-LLD Contract Register

### LLD-01 — Core Domain, Vault, and Persistence Contract

**Responsibility**

Define the concrete domain types and durable local data contract for raw sessions, structured entries, daily journals, work state, open loops, projects/entities, artifacts, provenance, amendments, and vault layout.

**Must settle**

- stable identifiers;
- exact Markdown/structured formats;
- append/rewrite/supersession semantics;
- raw-turn durability;
- user correction/amendment behavior;
- daily-journal materialization;
- state rebuilding rules;
- filesystem safety and atomicity;
- SQLite metadata schema and migrations that are persistence-owned rather than retrieval-owned;
- derived-index dependency invalidation hooks required by LLD-03.

### LLD-02 — Agent Runtime, Skills/SOPs, and Session Orchestration

**Responsibility**

Define how the local agent starts sessions, selects/loads the professional-brain Skill, applies core/mode/domain SOPs, retrieves context, probes, commits structured evidence, handles token budgets, performs safe communication drafting, and recovers incomplete sessions.

**Must settle**

- session lifecycle/state machine;
- tool contract exposed to the LLM;
- Skill/SOP directory and loading rules;
- Think/Operate/Communicate/Career/open-day/close-day/backfill workflows;
- communication privacy/sanitization behavior for draft generation;
- domain-probe selection;
- structured commit payload contract;
- model adapter and fallback behavior;
- context-budget policy;
- incomplete/malformed extraction handling.

### LLD-03 — Retrieval, FTS, Embeddings, and Index Lifecycle

**Responsibility**

Define the concrete searchable professional-evidence corpus and hybrid retrieval implementation.

**Must settle**

- retrieval access patterns;
- searchable chunk definitions;
- SQLite tables/indexes owned by retrieval;
- FTS5 schema/query handling;
- embedding model and metadata;
- vector backend;
- candidate fusion/internal ordering;
- structured filters;
- pageable continuation without a silent total-result cap;
- source hydration;
- incremental indexing/idempotency;
- `reindex` and staleness detection;
- retrieval smoke-test framework.

### LLD-04 — Interview Practice and Career Retrieval

**Responsibility**

Define the concrete Career projection over question resources and shared professional evidence.

**Must settle**

- normalized question-bank provider and deterministic tag/text filtering;
- public/shared versus private/restricted question-source boundaries;
- interview preparation and mock-practice flows;
- paged evidence discovery with user-led story/angle selection;
- answer critique grounded in hydrated evidence;
- durable user-authored interview-candidate marks;
- optional/deferred model-derived career annotations without changing core evidence;
- question-bank-driven retrieval smoke inputs;
- no AI story score/winner contract.

### 18.1 No dedicated CLI or connector LLD in v1

The initial CLI is a thin local adapter over the application contracts above. Exact command syntax, Yap/stdin handling, formatting, and configuration-file mechanics are implementer discretion unless later UX complexity creates a material architecture boundary. A dedicated CLI/TUI LLD MAY be created later if the interface gains independent state or lifecycle complexity.

External GitHub/Google/Slack/other connectors are likewise deferred until a concrete integration requirement exists. They will be adapter/future-LLD concerns and MUST NOT shape current persistence or trust contracts speculatively.

### 18.2 Implementation sequencing

Recommended sequence:

```text
LLD-01 Core Domain/Vault
       |
       +----> LLD-02 Agent Runtime/SOPs
       |
       +----> LLD-03 Retrieval/Indexing
                    |
                    +----> LLD-04 Interview/Career

Then implement the smallest vertical slice through all four contracts.
```

LLD-01, LLD-02, and LLD-03 share enough contracts that they MUST be cross-reviewed before the core implementation baseline freezes. LLD-04 then consumes those contracts and MUST NOT introduce a second professional-evidence model.

### 18.3 Cross-LLD Contract Register

| Contract | Authoritative owner | Consumers |
|---|---|---|
| Session identity and lifecycle states | LLD-02 | LLD-01, local interface adapter |
| Raw conversation persistence contract | LLD-01 | LLD-02 |
| Structured SessionEntry semantic contract | LLD-01 | LLD-02, LLD-03, LLD-04 |
| Provenance/amendment semantics | LLD-01 | LLD-02, LLD-04 |
| Current WorkState semantic contract | LLD-01 | LLD-02 |
| Retrieval application operations and pagination | LLD-03 | LLD-02, LLD-04 |
| Source hydration/stable evidence identity | LLD-03 + LLD-01 | LLD-02, LLD-04 |
| Structured session-commit payload | LLD-02 + LLD-01 | LLD-03 |
| Question-bank loading/filtering contract | LLD-04 | LLD-02 Career workflow |
| CareerCandidateMark durable preference contract | LLD-04 | LLD-02 Career workflow |
| Communication draft privacy/sanitization | LLD-02 | local interface adapter |
| Public-repo/private-vault boundary | HLD / LLD-01 | all LLDs |
| Model portability/token-boundary invariant | HLD / LLD-02 | LLD-04 |

## 19. Required Validation and Evidence

Before freezing v1 implementation:

- Demonstrate a Think session that is durably captured turn-by-turn.
- Demonstrate successful structured commit without a second full-history model pass.
- Demonstrate retrieval of that session by exact structured filter, FTS, and semantic query.
- Demonstrate reindexing from durable evidence after deleting the derived index.
- Demonstrate failure recovery when structured extraction fails after the raw transcript was saved.
- Demonstrate close-day is optional for preserving earlier sessions.
- Demonstrate a Career query that returns multiple plausible experiences without selecting a single winner for the user.
- Demonstrate pagination/continuation beyond the first Career evidence page without exposing numeric story scores.
- Demonstrate deterministic question-bank filtering from a configured bank and prove the question corpus is not mixed into the professional-evidence index.
- Demonstrate marking and unmarking an evidence entry as an interview candidate without rewriting the SessionEntry.
- Demonstrate historical backfill marked as reconstructed rather than contemporaneous.
- Demonstrate the public repository can run against a synthetic example vault and contains no real private user data.
- Demonstrate a clean private-vault path/configuration for a second user/friend.

## 20. HLD-to-LLD Handoff

The following decisions are settled and LLDs MUST NOT reopen them without discovering a genuine conflict:

- hexagonal architecture;
- local-first CLI v1;
- separate public code repository and private professional vault;
- raw conversations preserved verbatim;
- conversation/session is the ingestion unit;
- day is the journal aggregation unit;
- journal/state/indexes are projections over more durable evidence;
- Think/Operate/Communicate/Career share one evidence model;
- SQLite structured retrieval + FTS and semantic vector retrieval are all part of the local retrieval architecture;
- same evidence corpus feeds lexical and semantic retrieval;
- high-level retrieval tools shield the LLM from raw SQL/vector mechanics;
- no required background jobs in v1;
- Luna Max is the maximum normal model tier and token efficiency is a first-class requirement;
- Skills/SOPs/probe packs provide progressive workflow guidance;
- the system surfaces relevant career evidence and leaves story selection to the user;
- question banks remain a separate reference corpus; only publication-safe banks belong in the public repository;
- user-authored career marks may reference evidence but do not rewrite professional facts;
- model-derived career annotations, if added, are replaceable projection data;
- Career retrieval supports bounded pages plus continuation and never claims the first page is exhaustive when more results remain;
- a dedicated CLI LLD and connector LLD are not required for v1;
- future AWS/mobile/multi-device architecture is deferred.

LLDs are free to decide exact language/library choices, schemas, indexes, module boundaries, command syntax, embedding model, vector backend, fusion algorithm, file serialization, and local helper structure provided they preserve these HLD contracts. Non-normative future capabilities belong in design notes until a current requirement promotes them into an HLD/LLD revision.

## 21. Final Quality Gate

This HLD is ready for LLD authoring if another competent engineer or coding agent can proceed without inventing a source-of-truth boundary, privacy boundary, session/journal lifecycle, retrieval architecture, model portability rule, or public/private repository boundary.

At this revision, those boundaries are explicit. The remaining ambiguity is intentionally implementation-level and belongs in the named LLDs.
