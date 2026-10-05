# Work Brain — LLD-04: Interview Practice and Career Retrieval

**Document ID:** `WORK-BRAIN-LLD-004`
**Version:** `1`
**Status:** Implemented v1; retained as the normative contract
**Date:** `2026-09-30`
**Parent HLD:** `WORK-BRAIN-HLD-001` v2
**Sibling contracts:** `WORK-BRAIN-LLD-001` v2, `WORK-BRAIN-LLD-002` v2, `WORK-BRAIN-LLD-003` v2
**Implementation posture:** **Prescriptive with bounded local discretion**

## 1. Executive Summary

This LLD defines the Career projection for the initial local Work Brain: deterministic interview-question lookup, pageable retrieval of relevant professional evidence, user-led story/angle selection, interview preparation and mock-practice flows, evidence-grounded critique, and durable user-authored interview-candidate marks.

The core rule is:

```text
question corpus                        professional evidence corpus
("what might I be asked?")            ("what actually happened?")
        |                                         |
        v                                         v
QuestionBankProvider                    LLD-03 search/hydrate
        |                                         |
        +---------------+-------------------------+
                        v
                  Career workflow
                        |
                  user chooses story
                        |
               practice / critique
```

The question corpus and professional-evidence corpus remain separate. V1 does not embed or vector-index the question bank. A few hundred tagged interview questions are cheap to parse/filter deterministically. Selected question text becomes an input to professional-evidence retrieval; it does not become professional evidence itself.

Career preparation is Experience-centric over the same evidence corpus:

```text
question -> ranked evidence -> Experience aggregation -> candidate Experiences
                         \-> ungrouped single-entry candidates
```

An Experience candidate is a bounded card with stable identity and supporting
entry refs. Hydration resolves those refs to SessionEntry revisions and raw
turns. The system does not persist story scores, fit explanations, or invented
outcomes. Historical evidence that has no Experience association remains a
valid single-entry candidate.

The system may internally order search candidates, but it does not score or choose the user's “best” story. LLD-03 returns bounded pages plus an opaque continuation cursor. The Career workflow shows that more candidates exist when appropriate and lets the user continue until satisfied or the search is exhausted.

A user may explicitly mark either a stable Experience or an individual ungrouped
entry as an interview candidate. Marks use a `{target_kind, target_id}`
contract, preserve the legacy entry-mark fields when reading/writing entry
events, and remain preference metadata rather than professional evidence. An
Experience mark remains valid as more entry revisions are attached. Automatic
model-derived career annotations are deliberately not required in v1.

## 2. Effective Source Set

This LLD is governed by:

1. `WORK-BRAIN-HLD-001` v2.
2. `WORK-BRAIN-LLD-001` v2 — Core Domain, Vault, and Persistence Contract.
3. `WORK-BRAIN-LLD-002` v2 — Agent Runtime, Skills/SOPs, and Session Orchestration.
4. `WORK-BRAIN-LLD-003` v2 — Retrieval, FTS, Embeddings, and Index Lifecycle.
5. The supplied interview question bank as a representative v1 input shape: Markdown sections containing question lines prefixed by bracket tags for company, capability, employer signal, and provenance.
6. `RANQ-LLD-PROMPT-01` v3 as the authoring discipline.

The supplied bank is reference/test input, not automatically public-repository content. Its provenance distinguishes exact/internal-bank material, official questions/prompts/exercises, and official-derived practice prompts; redistribution safety must therefore be decided per source/bank rather than inferred from file format.

## 3. HLD Decisions Implemented Here

This LLD implements these settled HLD decisions:

- Career is a projection over the same SessionEntry evidence used by Think/Operate/Communicate.
- Question banks are a separate reference corpus from professional evidence.
- Question-bank selection should be lightweight and deterministic at current scale.
- Career retrieval favors useful recall and human choice rather than an AI-selected winner.
- Professional-evidence retrieval is pageable and does not silently stop at an arbitrary total top-K.
- Numeric retrieval scores are not story-quality scores and are not model-facing by default.
- User-authored career marks may be durable without changing professional evidence.
- Model-derived career annotations, if added later, are replaceable projection data.
- Public-repository resources and private/restricted question banks must remain separable.
- No background worker is required for Career correctness.
- Luna Max remains the maximum normal conversational model tier; question lookup and mark persistence must not spend model calls unnecessarily.

## 4. HLD Decisions Outside This LLD

This LLD does not redefine:

- raw conversation, SessionEntry, provenance, amendments, WorkState, entity/artifact authority — LLD-01;
- session lifecycle, Skill/SOP loading, model/tool orchestration, context budget, commit semantics, or communication sanitization — LLD-02;
- evidence chunking, FTS, embeddings, vector search, RRF ordering, pagination cursor internals, staleness, or hydration — LLD-03;
- exact terminal command syntax, screen layout, Yap integration, or shell UX — thin local adapter/implementer discretion;
- CV generation, performance-review generation, Teach/Quiz projections, or hosted career services — future requirements/designs;
- external company/recruiter scraping or web search.

## 5. Implementation Posture and Decision Classification

### 5.1 Implementation posture

`prescriptive_with_bounded_local_discretion`

This LLD fixes question normalization/query semantics, source boundaries, user-story selection behavior, interview practice states, durable candidate-mark semantics, evidence-grounded critique rules, and the no-winner/no-score contract. Private helper names, exact CLI aliases, and equivalent parser decomposition are implementer discretion.

### 5.2 Resolved design decisions

- V1 supports one or more configured question banks through a `QuestionBankProvider` port.
- The initial Markdown adapter recognizes question lines with one or more leading bracket tags followed by question text.
- Tag matching is case-insensitive after normalization; original display spelling is preserved.
- V1 question lookup uses deterministic in-memory parsing/filtering; no FTS/vector/LLM call is required to find a question.
- Every normalized question receives a deterministic `QuestionRef` derived from stable bank identity plus normalized question content.
- Public/shared banks and private vault banks use the same provider contract and preserve source provenance.
- Career evidence uses LLD-03 `search_evidence` pages (and `select_evidence` for filter-only scopes) plus `hydrate_evidence`; LLD-04 does not maintain a second professional-evidence index.
- The user, not the model, chooses the story/angle used for preparation.
- V1 supports two practice flows: `prepare` and `mock`.
- User-authored candidate marks are append-only events in private `career/marks.jsonl`.
- Candidate marks target either a stable Experience or an individual entry. Entry events record the revision current when marked for audit; Experience marks have no entry revision and remain valid as membership grows.
- Mark/unmark operations are idempotent at the application command level and latest event wins for current preference state.
- Automatic model-derived career capability/story annotations are deferred from v1.
- Career marks do not influence LLD-03's numeric retrieval fusion; they may be overlaid in presentation or used as an explicit user filter/list.

### 5.3 Repository assumptions

- LLD-03 provides the v2 pageable search contract with score-free EvidenceCards and opaque continuation cursors.
- LLD-02 can add Career-specific tools to the `career` tool profile without exposing them to every workflow.
- LLD-01 stable `entry_id` persists across structured-entry revisions.
- The local filesystem can read public repository resources and private vault resources through configured roots.

### 5.4 Implementation prerequisites

Before implementation freeze:

- configure at least one redistribution-safe synthetic/public question fixture for tests;
- configure the user's supplied bank locally without copying it into public fixtures unless redistribution rights are confirmed;
- cross-review exact `EvidenceRef`/pagination semantics with LLD-03;
- cross-review candidate-mark vault ownership with LLD-01;
- cross-review Career tool-profile and practice transitions with LLD-02;
- validate that the Markdown parser handles the supplied bank's tag patterns and section headings.

### 5.5 Implementer discretion

The implementer may choose:

- internal parser/tokenizer library versus simple line parsing;
- exact bank configuration filename/format;
- exact random-selection PRNG implementation for ad hoc practice;
- exact terminal presentation of questions/cards/marks;
- private class/module decomposition;
- whether current mark state is recomputed from the small JSONL file on demand or cached in memory.

## 6. Domain and Port Model

### 6.1 Core Career types

```text
BankId
QuestionRef
InterviewQuestion
QuestionFilters
CareerCandidateMarkEvent
CareerCandidateMark
PracticeMode
PracticeSessionState
```

These are Career projection types. They do not alter the universal SessionEntry schema.

### 6.2 Ports

```text
QuestionBankProvider
  list_banks()
  search_questions(filters, text, limit)
  get_question(ref)
  choose_question(filters, seed?)

CareerMarkStore
  append_mark_event(event)
  get_current_mark(target_kind, target_id)
  list_current_marks()

EvidenceRetriever       # LLD-03
  search_evidence(...)
  hydrate_evidence(...)

CareerConversation      # LLD-02 runtime/model/SOP
```

No Career port exposes raw SQL, FTS, vector primitives, or direct SessionEntry mutation.

## 7. Question Bank Source and Normalization Contract

### 7.1 Source classes

Configured banks have one source class:

```text
public_shared
private_local
```

`public_shared` means the application is permitted/configured to load the bank from the repository/resources path. It is not an automatic legal conclusion; repository maintainers remain responsible for what they publish.

`private_local` banks live outside public source control, normally under:

```text
career-vault/questions/
```

### 7.2 Stable bank identity

Each configured bank has a stable human-assigned `bank_id`, for example:

```text
interview-question-bank
personal-amazon-notes
synthetic-demo
```

Renaming the underlying file does not change `bank_id` unless the user intentionally creates a new logical bank.

### 7.3 Markdown question parsing

The v1 Markdown adapter:

- ignores headings, blank lines, source-index prose, and non-question list items that do not match the configured question-line grammar;
- recognizes list lines beginning with one or more bracket tags followed by non-empty question text;
- preserves all original tags for display/provenance;
- normalizes tags for filtering by Unicode casefold + surrounding-whitespace trim;
- preserves the containing Markdown heading as optional `section` metadata;
- preserves source line number/path only as local provenance/debug metadata, not stable identity.

Representative input:

```text
- [meta] [Embracing ambiguity] [ambiguity] [adaptability] [decision-making] [official-question] How do you operate ...?
```

### 7.4 Normalized `InterviewQuestion`

```json
{
  "ref": {
    "bank_id": "interview-question-bank",
    "question_id": "q_6f0b..."
  },
  "text": "How do you operate in an ambiguous, fast-changing environment when information or clarity is missing?",
  "tags": [
    {"normalized": "meta", "display": "meta"},
    {"normalized": "embracing ambiguity", "display": "Embracing ambiguity"},
    {"normalized": "ambiguity", "display": "ambiguity"},
    {"normalized": "official-question", "display": "official-question"}
  ],
  "section": "Judgment & Ambiguity",
  "source_class": "private_local"
}
```

`question_id` is derived as a deterministic SHA-256-based identifier over:

```text
bank_id + "\n" + normalized full question line
```

A material question-text/tag change therefore creates a new question identity. This is acceptable for a reference corpus; no durable professional fact depends on a question ID remaining stable across edited question content.

### 7.5 Provenance tags

The provider treats provenance-looking tags such as:

```text
internal-bank
official-question
official-prep-prompt
official-derived
official-exercise
```

as ordinary filterable tags with preserved display value. The parser does not reinterpret or upgrade provenance claims beyond what the bank itself states.

## 8. Question Query Contract

### 8.1 `QuestionFilters`

```json
{
  "tags_all": ["conflict"],
  "tags_any": ["amazon", "meta"],
  "exclude_tags": ["manager"],
  "bank_ids": []
}
```

All fields are optional. Unknown filter keys are rejected.

### 8.2 `search_questions`

```json
{
  "filters": {
    "tags_all": ["technical-depth"],
    "tags_any": ["openai", "stripe"]
  },
  "text": null,
  "limit": 20
}
```

Semantics:

- tag filters are deterministic set operations over normalized tags;
- optional `text` is case-insensitive substring/token matching over question text and tags;
- default limit is 20, max 100;
- result order is source-bank configuration order, then source order within bank unless the caller explicitly requests random selection;
- no quality/relevance score is generated.

### 8.3 `choose_question`

For “interview me” without an explicit question, the application may choose one question from the filtered set without an LLM call.

- If zero match: return typed `no_question_match`.
- If one match: return it.
- If multiple match: choose pseudorandomly for ordinary practice or deterministically when a `seed` is supplied for tests.
- The choice does not imply that the selected question is more important or more likely to be asked.

### 8.4 `get_question`

Fetches one exact `QuestionRef`; missing/changed question returns typed `question_not_found` rather than silently substituting a similar prompt.

## 9. Career Candidate Mark Contract

### 9.1 Purpose

A CareerCandidateMark records the user's durable preference:

> “I want to remember this entry as a possible interview example.”

It is not a professional fact, a model judgment, or a story-quality score.

### 9.2 Durable source

Private path:

```text
career-vault/career/marks.jsonl
```

This file is LLD-04-owned durable user preference state. It is not part of the public repository and is not a derived index.

### 9.3 Event shape

```json
{
  "event_id": "0199...",
  "occurred_at": "2026-09-30T18:45:00.000+01:00",
  "entry_id": "0199...",
  "entry_revision_at_event": 2,
  "action": "mark",
  "note": "Good conflict story; focus on how evidence changed the direction.",
  "question_refs": []
}
```

`action`:

```text
mark | unmark
```

Rules:

- IDs/timestamps are application-generated, not model-authoritative.
- `target_kind` MUST be `entry` or `experience`, and `target_id` MUST resolve through LLD-01/catalog records.
- Entry `target_revision_at_event` records what the user was looking at; current entry mark state follows stable `entry_id` across later revisions. Experience marks follow stable Experience identity as more entries are attached.
- `note` is optional and MUST represent user-provided/confirmed preference text; the model MUST NOT silently write its own assessment as if the user said it.
- `question_refs` is optional and only records explicit association requested/confirmed by the user.
- events are append-only; current state is latest valid event per `(target_kind, target_id)`.
- the single-writer vault rule from LLD-01 applies. A mark/unmark is acknowledged only after its JSONL record is durably flushed; a malformed final partial record may be recovered using the same trailing-record principle as other append-only local sources, while corruption in the middle of the file fails visibly.

### 9.4 Mark commands

Model-facing/application operations:

```text
mark_interview_candidate(target_kind, target_id, note?, question_refs?)
unmark_interview_candidate(target_kind, target_id)
list_interview_candidates()
associate_entry_experience(entry_id, experience_id | experience_name, move?, remove?)
```

The model MAY suggest marking an entry or Experience, but persistence requires
explicit user intent such as “mark this,” “this is a good interview example,”
or equivalent. A model's private belief that an entry or Experience looks
strong MUST NOT create a user mark automatically. Historical entries can be
associated later through an immutable metadata-only SessionEntry revision;
previous revisions remain readable and the association does not copy facts.

## 10. Automatic Career Annotation Extension Boundary

V1 requires no automatic career annotation pass.

A future revision MAY derive replaceable metadata such as:

```text
possible capabilities: conflict, ownership, technical-depth
possible matching question themes
missing outcome/metric signals
```

from existing SessionEntries. Such annotation:

- MUST reference stable evidence identity rather than copy/replace professional facts;
- MUST be visibly model-derived;
- MUST be regenerable after model/SOP/question-bank changes;
- MUST NOT overwrite user candidate marks;
- MUST NOT become an input requirement for ordinary evidence retrieval;
- MAY be cached in derived SQLite/projection state later without changing LLD-01 source authority.

This means a new conversation can be a useful interview example immediately even if no annotation job has ever run: the evidence is already searchable through LLD-03.

## 11. Interview Preparation Flow

`prepare` is for deciding which experience/angle to use before answering.

```text
select/receive question
        |
        v
search_evidence(question text / user refinement)
        |
        v
aggregate matches into candidate Experiences
        |
        +--> user selects Experience ---+
        |                               |
        +--> user asks "show more" ---> next_cursor
                                        |
                                        v
                               hydrate selected Experience
                                        |
                                        v
                           discuss story/angle and gaps
                                        |
                                        v
                          optionally mark candidate
```

Rules:

- The first page MUST NOT be described as exhaustive when `next_cursor` exists.
- Grouped candidates MUST expose stable supporting entry refs; relevant
  ungrouped entries remain single-entry candidates.
- The agent MUST NOT declare one card the best story.
- It MAY explain why an experience appears plausibly related to the question using card/hydrated evidence.
- User marks MAY be displayed as `you marked this as a candidate` but MUST NOT affect retrieval score/fusion.
- Hydration SHOULD normally wait until the user selects one or a small number of entries.

## 12. Mock Interview Flow

`mock` is for practice under interview-like conditions.

1. Obtain an explicit or selected question.
2. Ask the question without first revealing retrieved story suggestions unless the user asks for help.
3. Probe the user's answer conversationally using the Career SOP and relevant question/subquestion content.
4. After the answer, retrieve/hydrate relevant historical evidence when useful for critique or factual grounding.
5. Critique the answer; do not invent missing facts.
6. Ask whether the user wants to retry, inspect alternative experiences, or preserve a new reflection/correction.

The mock flow MAY use the original bank question's embedded follow-ups, but it MUST NOT claim those follow-ups were asked by a real employer unless the bank provenance itself supports that claim.

## 13. Evidence Search Query Behavior

### 13.1 Initial query

The cheapest default is the selected question text itself. No separate model call is required to rewrite the query.

The active Career conversation MAY refine the evidence query using the question's capability tags or the user's requested angle if the first result set is poor. Query refinement occurs inside the existing conversational context; it is not a separate ranking model.

### 13.2 Pagination

LLD-04 consumes LLD-03's opaque cursor exactly.

- Default first page uses LLD-03 default page size.
- `show more`, `more`, or equivalent continues with the same query/filter fingerprint.
- The workflow MAY traverse until cursor exhaustion if the user explicitly asks for all candidates.
- To protect model context, previously displayed cards need not all be reinserted into every later model call; the application may keep their stable refs/display state outside prompt context.

### 13.3 No hidden career filter

Career search MUST NOT silently restrict evidence to entries already marked as interview candidates. General evidence remains discoverable whether or not the user previously recognized its career value.

## 14. Story Selection and Human Authority

The system distinguishes:

```text
retrieval ordering           implementation/search mechanics
user candidate mark          durable user preference
runtime story selection      choice for this question/session
model explanation            non-authoritative assistance
```

These MUST NOT collapse into one score/status.

The user may select:

- one evidence entry;
- multiple entries to compare;
- a particular angle within one entry;
- none of the surfaced entries and request more/refine the search.

The model MUST NOT persist `best_story`, `story_score`, `seniority_score`, or equivalent authoritative ranking fields.

## 15. Interview Critique Contract

Critique SHOULD evaluate dimensions relevant to the selected question, such as:

- context/stakes clarity;
- personal ownership/contribution;
- reasoning, evidence, alternatives, and trade-offs;
- action specificity;
- outcome/impact/metrics when actually known;
- reflection/learning;
- conflict/influence dynamics where applicable;
- technical depth where applicable;
- communication clarity and concision.

Critique MUST distinguish:

```text
supported by hydrated evidence
stated by user during this practice session
missing / should be clarified
model suggestion
```

The agent MUST NOT fabricate a metric, outcome, stakeholder reaction, technical detail, or ownership claim merely to make an answer stronger.

If practice surfaces genuinely new factual detail about the underlying experience, normal LLD-02/LLD-01 commit/amendment semantics apply. Career critique itself is not automatically professional evidence.

## 16. Question-Bank-Driven Retrieval Evaluation

The question bank is also a retrieval smoke-query source.

Two modes are supported:

```text
unlabeled review
question -> LLD-03 pages -> human inspects candidates

labeled regression
question -> expected relevant entry IDs -> measure recall across configured pages
```

Human labels:

```text
relevant
not_relevant
uncertain
```

The harness does not require an AI-selected story winner or fixed ordering unless a future test explicitly targets retrieval ordering mechanics.

Private question text, private entry IDs, and personal labels remain outside public fixtures. Public repository tests use synthetic/distributable questions and synthetic evidence.

## 17. Career Tool Profile

The LLD-02 `career` workflow may expose:

```text
search_questions
get_question
choose_question
search_evidence
hydrate_evidence
mark_interview_candidate
unmark_interview_candidate
list_interview_candidates
commit_session
```

Tools unrelated to Career are not added merely because they exist elsewhere in the application.

Question lookup and mark persistence require no conversational-model call.

## 18. Failure Semantics

| Failure | Behavior |
|---|---|
| question bank missing/unreadable | typed bank error; explicit question practice may still proceed |
| malformed question line | skip with diagnostic or fail configured strict validation; never invent text |
| duplicate normalized question line in same bank | deduplicate by deterministic QuestionRef and report duplicate diagnostic |
| private bank accidentally configured as public path | warn/fail configured publication-safety check; never auto-copy |
| LLD-03 retrieval degraded | preserve degraded/incomplete semantics in Career workflow |
| cursor expired | rerun search from first page and state that the result set refreshed |
| candidate-mark append fails | do not claim the mark was saved; SessionEntry remains unaffected |
| marked entry/Experience later deleted or missing | mark becomes an orphaned diagnostic until explicitly removed/archived; never retarget automatically |
| question edited and old QuestionRef no longer resolves | return `question_not_found`; do not substitute a similar question |

## 19. Privacy and Publication Boundaries

- Question-bank source paths and raw question text may be private.
- Candidate marks are private by default.
- Career notes may contain candid self-evaluation and MUST remain in the private vault.
- Public repository fixtures MUST use synthetic/licensed/distributable question content.
- The application MUST NOT infer that `official-question` or `official-derived` tags imply redistribution permission.
- LLD-02 communication drafting MUST NOT automatically include career marks or critique notes in team-facing output.

## 20. Performance and Token-Efficiency Requirements

At the current scale:

- parse configured Markdown question banks in-process;
- cache parsed bank records by file content hash during one process lifetime if useful;
- use deterministic tag/text filtering instead of embeddings for question lookup;
- do not send the full question bank to the LLM;
- show bounded evidence pages and hydrate only selected entries;
- do not run an automatic career-annotation model pass after every session;
- write candidate marks synchronously with a single append + durable flush before acknowledging success;
- no background worker/daemon is required.

## 21. Persistence and Access Patterns

### 21.1 Question banks

Question banks are read-only reference inputs from configured repository/private paths. LLD-04 does not mutate them during normal use.

Access patterns:

```text
list banks
filter questions by tags/bank/text
fetch exact QuestionRef
choose one filtered question
```

No database index is required for these patterns at a few hundred/thousand questions.

### 21.2 Candidate marks

Authoritative access patterns:

```text
append mark/unmark event
get current mark for target_kind + target_id
list current marked targets
```

The JSONL event file is expected to remain tiny. V1 may scan it on process start and maintain an in-memory current-state map. A SQLite cache MAY be added later only if measurements justify it; it would be derived and rebuildable from `marks.jsonl`.

## 22. Repository / File Change Map

Representative ownership:

```text
src/work_brain/career/
  questions.*          # normalized types/query service
  marks.*              # mark event/domain service
  practice.*           # application workflow integration

src/work_brain/ports/
  question_bank.*
  career_mark_store.*

src/work_brain/adapters/questions/
  tagged_markdown.*

src/work_brain/adapters/career/
  jsonl_marks.*

skills/work-brain/references/sops/
  career.sop.md         # LLD-02-owned workflow instructions; updated to consume this contract

resources/questions/
  ...                   # publication-safe only

tests/
  unit/career/
  integration/career/
  retrieval-smoke/
```

Exact filenames/modules remain implementer discretion; responsibility boundaries do not.

## 23. Cross-LLD Contract Register

### 23.1 Contracts owned by LLD-04

| Contract | Consumers |
|---|---|
| `QuestionRef` / normalized `InterviewQuestion` | LLD-02 Career workflow, tests |
| `QuestionFilters` and deterministic question lookup | LLD-02 Career workflow |
| public/shared vs private-local question source class | installer/config/docs |
| CareerCandidateMark event/current-state semantics | LLD-02 Career workflow, local interface |
| `prepare` vs `mock` practice semantics | LLD-02 Career SOP |
| question-bank smoke-input behavior | retrieval evaluation harness |

### 23.2 Contracts consumed from LLD-01 v2

| Contract | LLD-04 usage |
|---|---|
| stable `entry_id` across revisions | candidate mark identity |
| immutable SessionEntry revision refs | audit when mark was created; hydrated critique |
| private-vault boundary | `questions/` and `career/marks.jsonl` |
| explicit amendment/re-extraction semantics | new factual detail/correction discovered during practice |
| source authority | Career metadata never rewrites professional facts |

### 23.3 Contracts consumed from LLD-02 v2

| Contract | LLD-04 usage |
|---|---|
| Career workflow selection/SOP | hosts practice flow |
| high-level tool registry/profile | exposes only Career tools when relevant |
| model ceiling/no hidden escalation | critique/practice model policy |
| bounded context | question + cards + selected hydration only |
| commit semantics | optional preservation of new factual learning |

### 23.4 Contracts consumed from LLD-03 v2

| Contract | LLD-04 usage |
|---|---|
| score-free EvidenceCard | candidate display/context |
| EvidenceRef | story selection/hydration |
| pageable search + opaque `next_cursor` | show-more/all-candidate flow |
| degraded/incomplete state | prevents false no-evidence conclusions |
| hydrate_evidence | grounded preparation/critique |
| human-labeled smoke cases | question-bank evaluation |

## 24. Alternatives Considered

### 24.1 Precompute a canonical “story” object for every entry

**Rejected.** Story usefulness depends on the question and user-selected angle. The underlying evidence is more durable than a preselected narrative.

### 24.2 Automatically score every entry after commit

**Rejected for v1.** It adds model/token cost, risks anchoring, and creates stale derived judgments. General retrieval already makes new evidence discoverable.

### 24.3 Store career capability tags inside SessionEntry

**Rejected.** It makes a Career interpretation part of the universal evidence schema. Future models/question banks should be able to reinterpret the same entry without source migration.

### 24.4 Only search previously marked interview candidates

**Rejected.** The user may not recognize an experience's value when it is captured. Career retrieval must search the full professional-evidence corpus.

### 24.5 Embed/vector-index the question bank

**Rejected for v1.** A few hundred structured tagged questions are cheaper and clearer to filter deterministically.

### 24.6 Rank stories by model-generated quality score

**Rejected.** Internal retrieval ordering is sufficient to traverse candidates; story/angle choice belongs to the user.

### 24.7 Put all question banks in the public repo

**Rejected.** Publication rights and confidentiality vary by source. The provider must support private-local banks.

## 25. Requirement-to-Evidence Traceability

| Requirement / invariant | Test / evidence |
|---|---|
| question/evidence corpora remain separate | LLD-03 index fixture proves question text absent from professional chunks |
| tagged Markdown parsing | parser fixtures from synthetic lines matching representative bank shape |
| case-insensitive tag filtering | unit tests across tag casing/display preservation |
| no question lookup LLM call | model-adapter spy remains unused for search/get/choose operations |
| first Career page not presented as exhaustive | integration test with non-null `next_cursor` |
| continuation preserves query/filter fingerprint | cursor integration test |
| no AI winner | output contract test contains no story/quality score/winner field |
| user mark requires explicit intent | orchestration test: model suggestion alone does not append mark event |
| mark follows stable entry ID across revision | re-extraction fixture + current mark lookup |
| unmark is durable | append mark then unmark; current state unmarked after restart |
| marked candidates do not hide unmarked evidence | Career search fixture returns relevant unmarked entry |
| critique grounded in evidence | mock/prepare fixture flags unsupported invented detail as failure |
| public/private source boundary | public fixture contains no configured private bank/mark file |
| question-bank smoke evaluation | unlabeled and labeled synthetic cases execute without story scoring |

## 26. Ordered Implementation Plan

### Step 1 — Implement normalized question types and tagged-Markdown parser

Implement `BankId`, `QuestionRef`, `InterviewQuestion`, parser diagnostics, and source classes.

**Gate:** synthetic bank parses deterministically; malformed/duplicate lines have defined diagnostics.

### Step 2 — Implement question query/provider operations

Implement tag/text filters, get-by-ref, and seeded/random choose behavior.

**Gate:** representative capability/company/provenance queries return expected sets without an LLM call.

### Step 3 — Implement CareerCandidateMark JSONL store

Implement append, current-state folding, mark/unmark validation, and explicit-intent application service.

**Gate:** restart preserves current marks and does not alter SessionEntry files.

### Step 4 — Integrate pageable evidence discovery

Wire LLD-03 search/card/cursor/hydration contracts into Career application services.

**Gate:** `show more` reaches later candidates; no numeric story score is exposed.

### Step 5 — Implement `prepare` workflow integration

Wire question -> evidence pages -> user selection -> hydration -> discussion/mark operations.

**Gate:** user can reject first-page candidates, request more, choose one, and hydrate only selected evidence.

### Step 6 — Implement `mock` workflow integration

Ask question first, collect/probe answer, then optionally hydrate evidence for grounded critique.

**Gate:** mock does not leak story suggestions before answer unless requested and critique does not invent unsupported facts.

### Step 7 — Integrate question-bank retrieval smoke harness

Run synthetic/public-safe questions through LLD-03 and support human relevance labels.

**Gate:** harness reports recall across configured pages without requiring a winner/order.

### Step 8 — Final sibling cross-review

Cross-review LLD-01/02/03/04 exact shared contracts.

**Gate:** report no genuine conflict in evidence authority, session/tool boundaries, pagination, source privacy, or mark semantics.

## 27. Objective Acceptance Criteria

LLD-04 is implementation-ready when:

- configured tagged Markdown banks parse into normalized questions with stable refs;
- filtering by capability/company/provenance tags works deterministically;
- question selection requires no model call;
- public/shared and private-local banks use the same provider interface without copying private content to the repository;
- question text is absent from the professional-evidence search corpus;
- Career evidence search uses LLD-03 score-free cards and continuation cursors;
- the user can request later pages and the system never calls the first page exhaustive while `next_cursor` exists;
- the model never chooses/persists a “best story” or story-quality score;
- the user can mark/unmark an entry as an interview candidate with durable restart-safe preference state;
- a candidate mark survives SessionEntry revision changes via stable `entry_id`;
- a model suggestion alone cannot create a user mark;
- unmarked evidence remains eligible for Career retrieval;
- `prepare` and `mock` flows both work through the LLD-02 Career SOP/tool profile;
- critique distinguishes source-supported facts, practice-session statements, missing details, and model suggestions;
- no current workflow requires automatic model-derived career annotation;
- retrieval smoke tests can use question-bank prompts and human relevance labels without AI winner selection;
- LLD-01/02/03 cross-review confirms no source-of-truth, privacy, or pagination conflict.

## 28. Design Decision Register

| Decision | Status | Rationale |
|---|---|---|
| separate question corpus from evidence corpus | Resolved | questions ask what may be asked; SessionEntries record what happened |
| tagged Markdown provider for v1 | Resolved | matches supplied bank and remains human-editable |
| deterministic question filtering, no embeddings | Resolved | current scale and explicit tags make semantic infrastructure unnecessary |
| public/shared + private-local bank sources | Resolved | supports friends/public repo without leaking restricted material |
| QuestionRef hash over bank ID + normalized line | Resolved | stable enough for immutable question content and simple to rebuild |
| pageable professional-evidence discovery | Resolved | preserves high recall without large model context |
| user selects story/angle | Resolved | preserves user agency and avoids false ranking authority |
| append-only user candidate marks | Resolved | durable preference with audit/history and no evidence mutation |
| marks follow entry ID across revisions | Resolved | a user's story preference is about the experience, not one extraction revision |
| automatic career annotation | Deferred | not needed for discoverability; can be derived later |
| story/capability fields inside SessionEntry | Rejected | would couple universal evidence to current interview ontology |
| question-bank embeddings | Rejected v1 | unnecessary cost/complexity |
| exact CLI syntax | Implementer discretion | no separate interface architecture required |

## 29. Documentation Drift

The parent HLD v1 and earlier sibling drafts referred to a CLI LLD-04 and a Career/Projection LLD-05. `WORK-BRAIN-HLD-001 v2` deliberately removes the dedicated CLI LLD from the required v1 design set and assigns `WORK-BRAIN-LLD-004` to Interview Practice and Career Retrieval. Exact CLI mechanics are now a thin-adapter implementation concern.

The earlier sibling drafts also used a total `search_evidence.limit` max of 20. LLD-03 v2 replaces that with bounded page size plus opaque continuation, preserving token efficiency without silently hiding later candidates.

## 30. Consult, Blocker, and Validation Prerequisites

### Consult

None.

### Blocker

The local v1 implementation baseline MUST NOT freeze until LLD-01/02/03/04 cross-review confirms:

- stable evidence identity;
- candidate-mark preference ownership;
- question/evidence corpus separation;
- pageable search/cursor semantics;
- Career tool-profile phase gating;
- public/private question-resource boundaries.

### Validation prerequisites

- parser validation against the supplied question-bank structure;
- one public-safe synthetic question fixture set;
- one private-local bank configuration test;
- retrieval smoke test demonstrating later-page relevant evidence can be reached;
- Luna Max-or-weaker Career SOP smoke sessions for both `prepare` and `mock` flows.

## 31. Final Coding-Agent Readiness Gate

Before freezing this LLD, verify that another competent engineer or coding agent can implement the Career projection without inventing:

- where questions come from or how they are normalized;
- whether question text belongs in the evidence index;
- how public/private question sources differ;
- how question filtering/selection works;
- how paged evidence discovery continues;
- who chooses the interview story;
- how user candidate marks persist and relate to SessionEntry revisions;
- whether model-derived annotations are authoritative;
- when practice creates new professional evidence;
- what critique may and may not invent.

If those checks pass with the sibling cross-review, LLD-04 is ready to join `WORK-BRAIN-HLD-001 v2 + WORK-BRAIN-LLD-001/002/003 v2` as the local v1 implementation baseline.
