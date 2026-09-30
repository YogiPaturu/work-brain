# Professional Second Brain — LLD-03: Retrieval, FTS, Embeddings, and Index Lifecycle

**Document ID:** `PSB-LLD-003`  
**Version:** `2`  
**Status:** Draft for sibling cross-review  
**Date:** `2026-09-30`  
**Parent HLD:** `PSB-HLD-001 v2`  
**Sibling contracts:** `PSB-LLD-001 v2`, `PSB-LLD-002 v2`, `PSB-LLD-004 v1`  
**Implementation posture:** Prescriptive with bounded local discretion

## 1. Executive Summary

This LLD defines the searchable corpus, exact/lexical/semantic retrieval contracts, SQLite retrieval schema, local embedding implementation, deterministic candidate fusion, source hydration, staleness handling, incremental indexing, full reindex behavior, and retrieval evaluation framework for the local Professional Second Brain.

The design keeps the retrieval subsystem deliberately small:

```text
current structured SessionEntry revisions
        |
        v
 deterministic chunker
        |
        +--> SQLite retrieval metadata
        +--> SQLite FTS5
        +--> local float32 embeddings in SQLite
                    |
                    v
          exact in-process cosine search
                    |
                    v
        deterministic entry-level fusion
                    |
                    v
            compact EvidenceCards
                    |
                    v
       hydrate current source by stable ref
```

V1 does **not** use a vector database, ANN service, background indexing worker, retrieval LLM, reranking model, or provider-hosted embedding API. FTS5 and semantic search operate over the same deterministic chunk corpus. Structured filters are resolved through SQLite. Semantic similarity uses a small local embedding model and exact NumPy cosine/dot-product search over normalized vectors loaded from SQLite.

The model-facing contract remains intentionally narrow:

```text
search_evidence(query, filters, page_size, cursor)
hydrate_evidence(refs)
```

The LLM does not choose SQL versus FTS versus vector search. A non-empty evidence query deterministically uses hybrid retrieval when both components are healthy. The application may degrade to lexical-only or semantic-only search when one component is unavailable, but must state that degradation explicitly. Stale indexed revisions are never silently returned as current evidence.

Retrieval scores are internal implementation signals. Model-facing `EvidenceCard`s expose why an item matched through sections/snippets and signal types, but do not expose numeric scores or declare a “best” career story. The user remains the final judge of which experience or angle is most useful.

## 2. Purpose and Scope

### 2.1 Responsibility

LLD-03 owns:

- the current searchable evidence corpus;
- deterministic chunk generation;
- retrieval-owned SQLite tables and indexes;
- FTS5 tokenization and lexical candidate generation;
- local embedding generation and model identity;
- vector storage and exact semantic candidate generation;
- structured retrieval filters;
- deterministic lexical/semantic fusion;
- compact `EvidenceCard` results;
- stable `EvidenceRef` and source hydration behavior;
- index update hooks used after source commit;
- staleness detection and degraded-search semantics;
- full `reindex` behavior;
- retrieval integrity checks consumed by `doctor`;
- retrieval smoke-test/evaluation harness.

### 2.2 Explicitly outside this LLD

This LLD does not own:

- source SessionEntry semantics, revisions, amendments, state, entities, artifacts, or vault durability — LLD-01;
- probing behavior, SOP loading, session orchestration, model selection, context budget, or commit extraction — LLD-02;
- terminal command names, result presentation, progress UX, or onboarding — thin local adapter/implementer discretion;
- interview-question storage/parsing, interview practice, user career marks, or career-specific query workflow — LLD-04;
- communication sanitization — LLD-02;
- hosted/cloud search architecture;
- team/multi-user retrieval;
- external web search;
- automatic artifact-content ingestion;
- raw-transcript indexing in v1;
- retrieval-time LLM reranking.

### 2.3 Core design objective

Retrieval should make the user's professional evidence easy to find with high useful recall while remaining local, deterministic, cheap, explainable, rebuildable, and simple enough that a weaker conversational model can use it without understanding storage mechanics.

## 3. Effective Source Set

This LLD is governed by:

1. `PSB-HLD-001 v2`.
2. `PSB-LLD-001 v2` — Core Domain, Vault, and Persistence.
3. `PSB-LLD-002 v2` — Agent Runtime, Skills/SOPs, and Session Orchestration.
4. The approved design conversation up to `2026-09-30` where it establishes that:
   - SQL, FTS5, and vectors are complementary;
   - the same evidence chunks should feed lexical and semantic search;
   - Career retrieval should favor recall and user judgment rather than AI-selected “best” stories;
   - local-first simplicity is more important than premature search infrastructure;
   - token-efficient retrieval cards should precede hydration;
   - question banks and real user queries may act as human-reviewed retrieval smoke tests.

No implementation repository exists yet whose source body overrides these contracts.

## 4. Parent HLD Decisions Implemented Here

This LLD implements the following HLD decisions:

- SQLite is the local structured query/index substrate.
- FTS5 provides lexical search.
- local embeddings provide semantic retrieval.
- FTS and vectors operate over the same evidence corpus.
- exact structured filters support date, project/entity, provenance, and related metadata.
- model-facing tools expose application intent, not raw SQL/FTS/vector mechanics.
- indexes are derived and rebuildable, never authoritative professional evidence.
- retrieval should be bounded before model-context insertion.
- retrieval should optimize for useful recall rather than aggressively hiding plausible experiences.
- numeric relevance may be used internally but must not become an authoritative “best story” judgment.
- indexing and embedding generation happen without extra LLM calls.
- no background worker or daemon is required.

## 5. HLD Decisions Outside This LLD

This LLD consumes but does not redefine:

- conversation/session as ingestion unit;
- day as journaling unit;
- raw transcript durability;
- SessionEntry schema and revision semantics;
- contemporaneous vs reconstructed provenance;
- user correction/amendment semantics;
- WorkState semantics;
- public-repository/private-vault boundary;
- Skill/SOP/probe behavior;
- model ceiling and weak-model strategy;
- CLI interaction model;
- Career workflow rule that the user chooses the story/angle.

## 6. Implementation Posture and Decision Classification

### 6.1 Implementation posture

`prescriptive_with_bounded_local_discretion`

This LLD fixes search semantics, searchable corpus, chunk identity, FTS/vector behavior, model-facing result shapes, staleness behavior, and reindex rules. Equivalent private helper/module organization remains implementer discretion.

### 6.2 Resolved design decisions

- V1 searchable evidence consists of **current structured SessionEntry revisions**, not raw transcripts.
- Older SessionEntry revisions remain hydratable by exact identity for audit/debugging but are excluded from normal search.
- Every current entry produces deterministic overview, section, and state chunks.
- FTS5 and embeddings index the same chunk rows.
- V1 uses `BAAI/bge-small-en-v1.5` as the default local embedding model.
- V1 semantic vectors are 384-dimensional, L2-normalized `float32` values.
- V1 embedding runtime SHOULD use a local ONNX/CPU-capable adapter such as FastEmbed; the port contract, not the library, is authoritative.
- V1 vector backend is exact in-process matrix dot-product search over vectors stored in SQLite; no ANN index is required.
- Hybrid search uses entry-level Reciprocal Rank Fusion after lexical and semantic chunk hits are grouped by entry.
- RRF constant is `60`.
- Default model-facing page size is `8`; allowed range is `1..20`.
- Search supports opaque continuation cursors and has no product-level total-result cap.
- Each hybrid branch may evaluate all eligible entries at personal-corpus scale; pagination is applied after deterministic fusion rather than by silently discarding candidates beyond an arbitrary global top-K.
- Numeric scores/ranks are internal diagnostics and are omitted from normal model-facing `EvidenceCard`s.
- Search excludes stale entry revisions rather than returning them as current evidence.
- `hydrate_evidence` reads authoritative source files through LLD-01; it does not trust indexed text as source truth.
- A full reindex may make search temporarily unavailable; this is acceptable because the index is derived and the corpus is small.
- There are no background indexing jobs.

### 6.3 Repository assumptions

- The implementation language can call SQLite with FTS5 support and NumPy-compatible local matrix operations.
- The target laptop can run the selected small embedding model locally on CPU.
- Current SessionEntry JSON can be loaded through the LLD-01 domain/persistence port.
- LLD-01 exposes current entry metadata including `entry_id`, `current_revision`, `current_hash`, and relationships.
- SQLite database access is single-writer in v1.

### 6.4 Implementation prerequisites

Before freezing the implementation baseline:

- verify the target SQLite build includes FTS5;
- verify the selected local embedding adapter supports `BAAI/bge-small-en-v1.5` and returns 384-dimensional vectors on the target laptop;
- run the retrieval smoke corpus against the default embedding model and confirm acceptable useful recall;
- benchmark exact vector search on a synthetic corpus representative of at least several years of use;
- cross-review `EvidenceRef`, `EvidenceCard`, hydration, and index status contracts with LLD-01 and LLD-02;
- cross-review Career recall/pagination/evaluation behavior with LLD-04.

These are implementation validation prerequisites, not unresolved architecture decisions.

### 6.5 Implementer discretion

The implementer may choose:

- exact Python package used to run the default embedding model if it satisfies this LLD's adapter behavior;
- internal class/function/module names;
- batch size for embedding generation;
- whether the vector matrix cache is rebuilt eagerly after an update or lazily on the next semantic query;
- exact SQL helper/query-builder structure;
- exact snippet-window algorithm provided it obeys the size and source rules here.

## 7. Retrieval Architecture

```text
                    authoritative source
                  SessionEntry current rev
                           |
                           v
                  RetrievalIndexer
                           |
                    deterministic chunks
                           |
             +-------------+-------------+
             |             |             |
             v             v             v
      retrieval_*       FTS5 table    embeddings
      metadata           lexical       float32 BLOB
             |             |             |
             +-------------+-------------+
                           |
                      RetrievalEngine
                           |
             +-------------+-------------+
             |                           |
             v                           v
       StructuredFilter             VectorCache
             |                           |
             +-----------+---------------+
                         v
                  candidate fusion
                         |
                         v
                    EvidenceCard[]
                         |
                         v
                    EvidenceRef[]
                         |
                         v
                  SourceHydrator
                         |
                         v
                 authoritative entry
```

The retrieval engine is a deterministic application service behind a `EvidenceRetriever` port. The embedding model is behind an `EmbeddingProvider` port. Storage-specific FTS/vector details remain inside adapters.

## 8. Searchable Corpus Contract

### 8.1 Search unit

The searchable corpus is built from the **current revision** of each committed SessionEntry.

V1 does not directly index:

- raw transcript turns;
- daily journal Markdown;
- current WorkState snapshot;
- historical/superseded entry revisions;
- question-bank text;
- full external artifact contents;
- generated communication drafts;
- model operational logs.

Rationale:

- SessionEntry is the curated professional-evidence projection designed for retrieval.
- Indexing the daily journal would duplicate the same evidence.
- Indexing WorkState would duplicate operational state already available through `get_current_state`.
- Indexing raw transcripts would materially increase noise and token exposure while not repairing information that a weak conversation failed to elicit.
- Raw transcripts remain available for re-extraction and targeted future tooling.

A future approved revision MAY add transcript fallback search as a separate corpus, but it must remain distinguishable from structured evidence and must not silently mix transcript fragments with user-confirmed structured evidence.

### 8.2 Current revision only

Normal search MUST include only the revision where:

```text
retrieval_entries.entry_id = entries.entry_id
AND retrieval_entries.source_revision = entries.current_revision
AND retrieval_entries.source_hash = entries.current_hash
```

This protects search from surfacing stale interpretations after re-extraction or user correction.

### 8.3 Searchable text

Searchable text may include only information already represented by the current SessionEntry and its current related catalog metadata:

- title;
- summary;
- section statement text;
- state mutation user-facing text;
- modes;
- domains;
- related entity canonical names and aliases;
- related artifact labels/kinds;
- occurrence label when present.

Internal filesystem paths, SQLite paths, hidden prompts, operational logs, embedding vectors, and raw model reasoning are not searchable evidence text.

## 9. Deterministic Chunking Contract

### 9.1 Retrieval recipe identity

The v1 retrieval recipe is:

```text
PSB-RETRIEVAL-RECIPE@1
```

The recipe identity exists because chunking/embedding/tokenization changes require deterministic staleness detection and a full reindex. This is a current operational requirement, not speculative source-versioning.

### 9.2 Chunk types

Each current SessionEntry produces:

1. exactly one `overview` chunk;
2. zero or more `section` chunks;
3. zero or more `state` chunks.

#### Overview chunk

Contains:

```text
Title: <title>
Summary: <summary>
Domains: <domains if any>
Modes: <modes if any>
Entities: <canonical names if any>
Artifacts: <artifact labels if any>
```

The overview chunk is always generated even if the summary is short.

#### Section chunks

For each non-empty semantic section in this order:

```text
context
observations
significance
contribution
reasoning
evidence
alternatives_tradeoffs
decisions_actions
expectations
outcomes
learning
open_questions
```

The text format is:

```text
<section display name>
- <statement 1 text>
- <statement 2 text>
...
```

`basis` and `source_turns` are not inserted into embedding/FTS text; they remain available during hydration.

#### State chunks

When the entry contains state mutations, group them into one or more chunks containing user-facing fields such as:

```text
<kind>: <title>
status: <status>
next: <next_action if present>
waiting on: <waiting_on if present>
details: <details if present>
```

IDs are metadata, not semantic chunk prose.

### 9.3 Chunk size

Target maximum chunk size is `1,600` Unicode characters before metadata decoration.

Rules:

- split only at statement/state-item boundaries when possible;
- if one statement exceeds the target by itself, split at a whitespace boundary near the target;
- never split an identifier or URL merely to hit an exact length;
- preserve source order;
- never paraphrase or summarize solely for chunking;
- the final short remainder is retained as its own chunk rather than discarded.

This size is intentionally conservative for the default small embedding model and keeps search snippets/hydration precise.

### 9.4 Deterministic chunk identity

Each chunk identity is derived from:

```text
recipe_id
entry_id
source_revision
chunk_kind
section_key or "-"
ordinal
```

The canonical key string is UTF-8 encoded with `\0` separators and SHA-256 hashed. The lowercase 64-character hex digest is `chunk_id`.

Example conceptual input:

```text
PSB-RETRIEVAL-RECIPE@1\0<entry_id>\01\0section\0reasoning\00
```

Chunk identity is an index identity, not a domain identity. It therefore does not use UUIDv7.

### 9.5 Chunk content hash

Each chunk stores:

```text
text_hash = sha256(UTF-8 normalized chunk text)
```

Normalization is Unicode NFKC plus LF newlines; semantic text is otherwise preserved.

### 9.6 Same-corpus invariant

For a healthy current index, every current `retrieval_chunks` row MUST have:

- exactly one corresponding FTS row;
- exactly one corresponding embedding row for the configured embedding model.

A component failure may temporarily violate this target invariant, but the affected entry/component MUST then be marked stale/degraded and excluded from falsely “healthy” search.

## 10. Embedding Contract

### 10.1 Default embedding model

V1 default:

```text
model_id: BAAI/bge-small-en-v1.5
dimensions: 384
dtype: float32
normalization: L2
execution: local CPU
```

The application does not vendor model weights in the public repository. The embedding adapter may obtain/cache weights through the package's normal local model-cache mechanism during explicit setup/first use.

### 10.2 Query/document behavior

The embedding port exposes distinct operations:

```text
embed_documents(texts[]) -> normalized float32 vectors
embed_query(text)        -> normalized float32 vector
```

The default BGE adapter SHOULD apply the model's retrieval-query instruction/prefix inside `embed_query` while leaving document text unmodified. That adapter-specific prompting MUST NOT leak into higher application layers.

### 10.3 Model identity

The stored embedding identity MUST include enough information to invalidate vectors when semantically incompatible embedding behavior changes:

```text
provider = local
model_id = BAAI/bge-small-en-v1.5
dimensions = 384
normalization = l2
adapter_recipe = PSB-BGE-QUERY-ADAPTER@1
```

A change to any of these values makes the semantic index globally stale until reindexed.

### 10.4 Vector serialization

Vectors are stored as contiguous little-endian IEEE-754 `float32` bytes in SQLite.

Required validation before insert:

- exact dimension `384`;
- all values finite;
- L2 norm within implementation tolerance of `1.0`;
- byte length exactly `384 * 4`.

### 10.5 No remote embedding fallback

V1 MUST NOT silently send private evidence to a hosted embedding API if local embedding fails.

If the local embedding component is unavailable, retrieval degrades to lexical/structured search and reports the degradation.

## 11. Vector Backend

### 11.1 Selected backend

V1 uses exact in-process semantic search:

```text
SQLite-stored normalized float32 vectors
    -> load into process memory
    -> NumPy-compatible matrix
    -> query_vector dot matrix.T
    -> ordered eligible candidate chunks
```

Because all vectors are L2-normalized, dot product is cosine similarity.

### 11.2 Cache behavior

The retrieval adapter MAY maintain one in-memory vector matrix cache per open vault.

The cache contains:

- matrix `[N, 384]`;
- aligned `chunk_id[]`;
- aligned `entry_id[]`;
- optional precomputed metadata needed for filter masking;
- the retrieval recipe/model fingerprint that produced the cache.

The cache is invalidated after successful semantic index mutation. It may be rebuilt eagerly or lazily.

### 11.3 Why exact search

Exact search is selected because:

- expected v1 corpus is thousands to low tens of thousands of chunks;
- it avoids native ANN-extension installation friction for friends using the public repository;
- it has no background service;
- it is deterministic and easy to test;
- it preserves adapter portability to `sqlite-vec`, HNSW, or a hosted vector store later.

### 11.4 Reconsideration triggers

The vector backend should be reconsidered when one or more are sustained on target hardware:

- more than `100,000` current chunks;
- vector-cache memory exceeds roughly `200 MB`;
- semantic candidate generation p95 exceeds `300 ms` for ordinary filtered/unfiltered queries;
- startup/cache-build latency becomes a material interactive problem.

These are architecture reconsideration triggers, not hard product limits.

## 12. Retrieval-Owned SQLite Schema

All tables below live in the same rebuildable SQLite database used by LLD-01. They are owned by LLD-03 and may be dropped/rebuilt without losing authoritative professional evidence.

### 12.1 `retrieval_entries`

```sql
CREATE TABLE retrieval_entries (
    entry_id TEXT PRIMARY KEY,
    source_revision INTEGER NOT NULL,
    source_hash TEXT NOT NULL,
    dependency_hash TEXT NOT NULL,
    recipe_id TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    provenance_kind TEXT NOT NULL,
    occurrence_start_ms INTEGER,
    occurrence_end_ms INTEGER,
    occurrence_precision TEXT NOT NULL,
    occurrence_label TEXT,
    has_outcome INTEGER NOT NULL,
    has_open_questions INTEGER NOT NULL,
    indexed_at TEXT NOT NULL
);

CREATE INDEX retrieval_entries_by_occurrence
    ON retrieval_entries(occurrence_start_ms, entry_id);

CREATE INDEX retrieval_entries_by_provenance
    ON retrieval_entries(provenance_kind, occurrence_start_ms);
```

`has_outcome` is true when the current entry's `sections.outcomes` is non-empty. `has_open_questions` is true when `sections.open_questions` is non-empty.

### 12.2 Modes and domains

```sql
CREATE TABLE retrieval_entry_modes (
    entry_id TEXT NOT NULL REFERENCES retrieval_entries(entry_id) ON DELETE CASCADE,
    mode TEXT NOT NULL,
    PRIMARY KEY (entry_id, mode)
);

CREATE TABLE retrieval_entry_domains (
    entry_id TEXT NOT NULL REFERENCES retrieval_entries(entry_id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    PRIMARY KEY (entry_id, domain)
);

CREATE INDEX retrieval_modes_lookup
    ON retrieval_entry_modes(mode, entry_id);

CREATE INDEX retrieval_domains_lookup
    ON retrieval_entry_domains(domain, entry_id);
```

Values are copied from the current SessionEntry as open-string tokens.

### 12.3 `retrieval_chunks`

```sql
CREATE TABLE retrieval_chunks (
    chunk_id TEXT PRIMARY KEY,
    entry_id TEXT NOT NULL REFERENCES retrieval_entries(entry_id) ON DELETE CASCADE,
    source_revision INTEGER NOT NULL,
    chunk_kind TEXT NOT NULL,
    section_key TEXT,
    ordinal INTEGER NOT NULL,
    text TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    UNIQUE (entry_id, source_revision, chunk_kind, section_key, ordinal)
);

CREATE INDEX retrieval_chunks_by_entry
    ON retrieval_chunks(entry_id, ordinal);
```

Allowed `chunk_kind` values in v1:

```text
overview
section
state
```

### 12.4 FTS5 table

V1 uses a standalone derived FTS table rather than external-content triggers:

```sql
CREATE VIRTUAL TABLE retrieval_fts USING fts5(
    chunk_id UNINDEXED,
    entry_id UNINDEXED,
    title,
    body,
    metadata,
    tokenize = 'unicode61 remove_diacritics 2'
);
```

Implementation MUST preserve `_` and `-` as useful identifier characters when supported by the target FTS5 tokenizer configuration. Exact tokenizer syntax is validated against the target SQLite build before freeze.

Column intent:

- `title` — current entry title;
- `body` — exact chunk text;
- `metadata` — domains, modes, current related entity names/aliases, artifact labels/kinds, occurrence label.

Lexical ranking weights are:

```text
title:    3.0
body:     1.0
metadata: 1.5
```

The implementation may express these weights using the target FTS5 `bm25()` call or an equivalent deterministic formula.

### 12.5 `retrieval_embeddings`

```sql
CREATE TABLE retrieval_embeddings (
    chunk_id TEXT PRIMARY KEY REFERENCES retrieval_chunks(chunk_id) ON DELETE CASCADE,
    model_id TEXT NOT NULL,
    adapter_recipe TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    text_hash TEXT NOT NULL,
    vector BLOB NOT NULL,
    embedded_at TEXT NOT NULL
);

CREATE INDEX retrieval_embeddings_by_model
    ON retrieval_embeddings(model_id, adapter_recipe);
```

### 12.6 Retrieval metadata

```sql
CREATE TABLE retrieval_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

Required v1 keys:

```text
recipe_id
embedding_model_id
embedding_adapter_recipe
embedding_dimensions
fts_recipe
index_state
full_reindex_started_at
full_reindex_completed_at
```

`index_state` values:

```text
current
building
stale
```

This metadata applies to retrieval projections only; it is not a source schema version.

### 12.7 Dependency hash

`dependency_hash` is SHA-256 over a deterministic serialization of:

```text
entry current_hash
+ current related entity IDs/canonical names/aliases/updated_at
+ current related artifact IDs/kinds/labels/updated_at
```

This detects search-text drift caused by catalog changes without treating entity/artifact labels as authoritative copies in the retrieval index.

## 13. Structured Filter Contract

### 13.1 Model-facing `EvidenceFilters`

```json
{
  "occurred_after": null,
  "occurred_before": null,
  "entities": [],
  "domains": [],
  "modes": [],
  "provenance_kind": null,
  "has_outcome": null
}
```

All fields are optional.

### 13.2 Date semantics

`occurred_after` and `occurred_before` accept either:

- `YYYY-MM-DD`; or
- RFC3339 timestamp with offset.

The runtime converts them to UTC epoch milliseconds.

Semantics:

- `occurred_after` is inclusive;
- `occurred_before` is exclusive;
- when an entry has no occurrence start, it does not match a date-bounded search unless the filter explicitly supports unknown dates in a future revision.

### 13.3 Entity filter resolution

Each string in `entities` may be:

- an exact stable `entity_id`; or
- a canonical name/alias.

Name/alias resolution uses LLD-01 Unicode normalization and case-folding rules.

Behavior:

- zero matches -> filter resolves to an empty eligible set;
- exactly one semantic entity match -> use that `entity_id`;
- more than one match -> return `ambiguous_filter` with compact candidate identities; do not guess.

Multiple entities use **any-of** semantics in v1.

### 13.4 Domain/mode filters

Multiple `domains` or `modes` use any-of semantics.

Tokens are matched by Unicode case-folded equality after trimming surrounding whitespace.

### 13.5 Provenance filter

Allowed values:

```text
contemporaneous
reconstructed
```

### 13.6 Outcome filter

`has_outcome=true` means the current entry has at least one outcome statement.

`has_outcome=false` means the current entry has none.

This is a structural signal only; it does not imply success/failure.

### 13.7 No hidden filters

V1 MUST NOT secretly prefer or exclude evidence based on:

- employer;
- recency;
- perceived seniority;
- estimated interview quality;
- positive versus negative outcome;
- inferred “story strength.”

If a workflow wants one of those constraints, it must express a supported explicit filter or perform user-visible reasoning over the returned evidence.

## 14. Lexical Retrieval

### 14.1 Query normalization

For `search_evidence`, lexical query handling:

1. Unicode NFKC normalize;
2. trim whitespace;
3. reject empty query after normalization;
4. enforce maximum `1,000` characters;
5. tokenize/sanitize user text so FTS syntax is not directly executable by the caller;
6. generate a high-recall lexical expression from literal tokens/phrases.

The model/user string is never concatenated into arbitrary SQL.

### 14.2 High-recall lexical expression

V1 SHOULD construct a safe OR-oriented token expression so a candidate can match a useful subset of the query terms.

Quoted user phrases MAY receive an additional exact-phrase boost, but phrase syntax is parsed by application code rather than passed directly to FTS5.

Stopword removal is not required in v1; FTS/BM25 ranking and hybrid fusion are sufficient at expected scale.

### 14.3 Candidate generation

FTS candidate generation MUST retain enough entry-level matches to support continuation through the full eligible result set at personal-corpus scale. V1 may materialize all eligible FTS entry candidates before fusion rather than impose an arbitrary global top-K.

Structured filters are applied before/within lexical candidate selection so narrow filters cannot lose valid results behind globally higher-ranked out-of-scope rows.

### 14.4 Entry grouping

FTS returns chunk hits. Before hybrid fusion:

- group chunks by `entry_id`;
- use the best lexical chunk rank as the entry's lexical rank;
- retain at most two lexical match snippets and at most three matched section keys per entry;
- duplicate chunks from the same entry do not create multiple entry candidates.

## 15. Semantic Retrieval

### 15.1 Candidate generation

For every non-empty `search_evidence` query when the semantic component is healthy:

1. `embed_query(query)`;
2. resolve eligible entry IDs from structured filters;
3. mask vector rows to eligible entries;
4. compute exact dot products;
5. retain/order eligible chunk similarities needed to support the full paged result sequence at personal-corpus scale.

V1 MAY sort all eligible semantic chunk similarities in memory. Page slicing occurs only after entry grouping and hybrid fusion; no arbitrary branch-level total cap may make later evidence unreachable.

### 15.2 Entry grouping

Before fusion:

- group semantic chunk hits by `entry_id`;
- use the highest-similarity chunk as the entry's semantic rank;
- retain at most two semantic snippets and at most three matched section keys;
- duplicate chunk hits from one entry do not consume multiple result slots.

### 15.3 No hard similarity threshold in v1

V1 does not impose a universal cosine threshold because embedding-score distributions vary by query and model.

Low-value results are controlled by bounded page size, user-controlled continuation, and hybrid ordering rather than a threshold that could create false negatives. Evaluation may justify a future threshold revision.

## 16. Hybrid Candidate Fusion

### 16.1 Deterministic fusion

When both lexical and semantic components are healthy, fusion occurs at **entry level** using Reciprocal Rank Fusion:

```text
rrf(entry) = sum(1 / (60 + rank_i))
```

where `rank_i` is the 1-based entry rank within each available branch.

A candidate appearing in both branches receives both contributions.

### 16.2 Why RRF

RRF is selected because:

- BM25 and cosine scores are not directly comparable;
- it requires no learned ranker;
- it is deterministic;
- it is robust to one modality producing differently scaled scores;
- it avoids spending LLM tokens on reranking.

### 16.3 Tie-breaking

If fused scores tie exactly, use in order:

1. candidate appearing in both lexical and semantic branches;
2. better minimum branch rank;
3. more recent `occurrence_start_ms` when both are known;
4. lexical `entry_id` ordering for deterministic final stability.

Recency is only a final deterministic tie-breaker, not a hidden relevance boost.

### 16.4 Partial-component fusion

- lexical healthy, semantic unavailable/stale -> lexical ordering only;
- semantic healthy, lexical unavailable/stale -> semantic ordering only;
- both unavailable -> `retrieval_unavailable`, not an empty “no results” response.

The result status must expose which component is degraded.

### 16.5 Pagination and continuation

After deterministic fusion, return one bounded page.

Default `page_size`:

```text
8
```

Allowed:

```text
1..20
```

There is no product-level total-result cap in v1. If additional fused candidates remain, the result MUST include an opaque `next_cursor`. A continuation request returns the next page in the same deterministic ordering without exposing numeric scores to the model/user.

The cursor MUST bind to at least:

- normalized query;
- normalized filters;
- retrieval/index generation identity;
- continuation position.

The model treats the cursor as opaque. If the underlying retrieval generation changes before continuation, the tool MUST return `cursor_expired` and require a fresh search rather than silently changing the result set mid-pagination.

## 17. Stable Evidence Reference

### 17.1 `EvidenceRef`

The model-facing stable source reference is:

```json
{
  "entry_id": "<uuidv7>",
  "revision": 2
}
```

The reference points to one immutable LLD-01 SessionEntry revision.

### 17.2 Current-search invariant

Normal `search_evidence` returns refs only to current entry revisions.

### 17.3 Historical hydration

`hydrate_evidence` MAY hydrate an older revision when explicitly passed a valid historical ref for audit/debugging. It must mark that result `historical` and identify the current revision number.

The tool never silently upgrades a supplied historical ref to the current revision.

## 18. `EvidenceCard` Contract

### 18.1 Purpose

An EvidenceCard is deliberately small enough for a weak model to decide whether full hydration is useful.

Target size is normally under roughly `180` model tokens per card.

### 18.2 Shape

```json
{
  "ref": {
    "entry_id": "0199...",
    "revision": 1
  },
  "title": "Thinking through asynchronous submission generation",
  "when": {
    "start": "2026-09-30T10:42:03.122+01:00",
    "end": "2026-09-30T11:08:41.004+01:00",
    "precision": "instant",
    "label": null
  },
  "summary": "Considered moving submission generation async and deferred it after reframing the main concern around failure isolation.",
  "provenance_kind": "contemporaneous",
  "modes": ["think", "operate"],
  "domains": ["engineering"],
  "entities": [
    {"entity_id": "0199...", "kind": "project", "name": "Ranq"}
  ],
  "match": {
    "signals": ["lexical", "semantic"],
    "sections": ["reasoning", "alternatives_tradeoffs"],
    "snippets": [
      "Initially believed latency was the main reason...",
      "Queueing would improve failure isolation but add operational complexity..."
    ]
  },
  "flags": {
    "has_outcome": false,
    "has_open_questions": true
  }
}
```

### 18.3 Match signal values

Allowed v1 signals:

```text
lexical
semantic
```

Structured filtering does not appear as a match signal; it constrains candidate eligibility.

### 18.4 Snippet rules

- at most two snippets per card;
- each snippet at most `220` Unicode characters;
- use exact indexed text, not LLM paraphrase;
- preserve enough surrounding text to be intelligible;
- snippets may append `…` when clipped;
- do not include raw transcript text in search cards.

### 18.5 Scores are not model-facing

Normal EvidenceCards MUST NOT include:

- cosine similarity;
- BM25 score;
- RRF score;
- “quality” score;
- story score;
- seniority score;
- selected winner.

A separate debug/diagnostic interface MAY expose retrieval ranks and scores to developers/users, but those values are not inserted into the conversational model context by default.

## 19. `search_evidence` Tool Contract

### 19.1 Request

First page:

```json
{
  "query": "times I changed technical direction after new evidence",
  "filters": {
    "occurred_after": null,
    "occurred_before": null,
    "entities": ["Ranq"],
    "domains": ["engineering"],
    "modes": [],
    "provenance_kind": null,
    "has_outcome": null
  },
  "page_size": 8,
  "cursor": null
}
```

Continuation uses the same `query`/`filters`/`page_size` plus the opaque cursor returned by the previous result.

Validation:

- `query` required, 1..1000 chars after trimming;
- `filters` optional;
- `page_size` optional, default 8, 1..20;
- `cursor` optional opaque string;
- when `cursor` is supplied, query/filter/page-size fingerprint MUST match the cursor contract;
- unknown filter keys rejected rather than ignored;
- invalid date/provenance types rejected;
- ambiguous entity aliases return typed ambiguity rather than guessed resolution.

### 19.2 Result

```json
{
  "status": "ok",
  "degraded_components": [],
  "incomplete": false,
  "omitted_stale_entries": 0,
  "cards": [],
  "next_cursor": null
}
```

`status` values:

```text
ok
degraded
retrieval_unavailable
invalid_request
ambiguous_filter
cursor_expired
```

`next_cursor` is null only when the fused candidate sequence is exhausted for the current search generation. The caller MUST NOT infer that the first page is exhaustive when it is non-null.

### 19.3 `incomplete`

`incomplete=true` when one or more known-current source entries are omitted because retrieval indexing is stale or building.

The agent MUST NOT interpret an incomplete empty result as proof that no relevant evidence exists. Pagination exhaustion and index completeness are separate concepts.

### 19.4 Empty healthy result

Only when:

- `status=ok`;
- `incomplete=false`;
- both required healthy retrieval branches produced no eligible match; and
- `next_cursor=null`;

may the caller describe the current indexed corpus as having no matches for that exact query/filters. It still MUST NOT claim the user's history contains no relevant experience in an absolute sense.

### 19.5 Internal ordering is not a story judgment

The ordered page sequence exists only to traverse a finite search result set efficiently. It MUST NOT be labeled “best stories,” “top experiences,” or equivalent evaluative language. Career workflows may show all pages on user request, and may overlay user-authored marks from LLD-04 without altering LLD-03 scores/fusion.

## 20. `hydrate_evidence` Tool Contract

### 20.1 Request

```json
{
  "refs": [
    {"entry_id": "0199...", "revision": 1}
  ]
}
```

V1 accepts `1..4` refs per call.

More refs are rejected with `too_many_refs`; the caller should hydrate a smaller subset rather than receiving an arbitrarily truncated combined payload.

### 20.2 Source of truth

Hydration MUST:

1. validate the stable ref;
2. read the immutable SessionEntry revision through LLD-01;
3. resolve current entity/artifact display metadata through LLD-01 catalogs;
4. return structured source evidence.

Hydration MUST NOT return indexed chunk text as though it were authoritative source.

### 20.3 Result shape

```json
{
  "items": [
    {
      "ref": {"entry_id": "0199...", "revision": 1},
      "status": "current",
      "current_revision": 1,
      "entry": {
        "title": "...",
        "summary": "...",
        "occurrence": {},
        "provenance_kind": "contemporaneous",
        "modes": [],
        "domains": [],
        "sections": {
          "reasoning": [
            {
              "text": "...",
              "basis": "stated",
              "source_turns": [5, 6]
            }
          ]
        },
        "state_mutations": [],
        "source_refs": []
      },
      "entities": [],
      "artifacts": []
    }
  ]
}
```

Per-item status:

```text
current
historical
not_found
corrupt_source
```

### 20.4 Historical status

If the requested revision exists but is not current:

- return the exact requested immutable revision;
- set `status="historical"`;
- set `current_revision` to the latest revision;
- do not silently substitute current content.

### 20.5 Source turns

Hydrated statements retain `source_turns` sequence numbers, but raw turn text is not included by default.

A future explicit source-inspection tool may retrieve turn text when audit/debugging requires it. This keeps normal hydration small.

## 21. Index Dependency and Staleness Model

### 21.1 Entry staleness

A retrieval entry is current only when all hold:

```text
source_revision == entries.current_revision
source_hash == entries.current_hash
dependency_hash == recomputed current dependency hash
recipe_id == configured retrieval recipe
```

### 21.2 Semantic staleness

A semantic component is current only when:

- retrieval recipe matches;
- model ID matches;
- adapter recipe matches;
- dimensions match;
- every eligible current chunk has one embedding whose `text_hash` matches the chunk.

### 21.3 Lexical staleness

A lexical component is current only when every eligible current chunk has exactly one FTS row produced by the current FTS recipe.

### 21.4 Global recipe change

Any change to:

- chunking recipe;
- FTS tokenization recipe;
- embedding model identity;
- embedding adapter recipe;

sets the corresponding retrieval component/global index state to `stale` and requires full reindex before that component is considered healthy.

### 21.5 Catalog dependency changes

When an Entity or ArtifactReference used by one or more entries changes display/search metadata, the application SHOULD invoke:

```text
mark_dependency_changed(kind, id)
```

which marks related retrieval entries stale and optionally reindexes them synchronously.

Even if that hook is missed, `doctor` MUST detect the dependency-hash mismatch.

This hook is a new cross-LLD contract for LLD-01 sibling review.

## 22. Incremental Index Update Contract

### 22.1 Internal application hook

After LLD-01 source publication, the application invokes:

```text
index_entry(entry_id)
```

The LLM never calls this tool directly.

### 22.2 Normal `index_entry` algorithm

1. Read `entries` current metadata from LLD-01 SQLite projection.
2. Read the authoritative current SessionEntry revision file.
3. Verify file content hash equals `entries.current_hash`.
4. Resolve current related entity/artifact search metadata.
5. Compute dependency hash.
6. Generate deterministic chunks in memory.
7. Generate all embeddings for those chunks in one or more local batches.
8. Validate embedding dimensions/norms/finiteness.
9. Open one SQLite write transaction.
10. Delete retrieval-owned rows for this `entry_id`.
11. Insert `retrieval_entries`, modes/domains, chunks, FTS rows, and embeddings.
12. Commit transaction.
13. Invalidate the in-process vector cache.
14. Return `IndexUpdateResult`.

Embedding generation occurs **before** deleting the old retrieval rows so an embedding failure does not replace a previously valid search projection with a half-built one.

### 22.3 `IndexUpdateResult`

```json
{
  "entry_id": "0199...",
  "source_revision": 2,
  "source_hash": "...",
  "dependency_hash": "...",
  "status": "indexed",
  "chunk_count": 7,
  "recipe_id": "PSB-RETRIEVAL-RECIPE@1",
  "embedding_model_id": "BAAI/bge-small-en-v1.5",
  "indexed_at": "2026-09-30T21:00:00+01:00"
}
```

Status values:

```text
indexed
already_current
stale
failed
```

### 22.4 Idempotency

Calling `index_entry(entry_id)` repeatedly against the same current source/dependency/recipe state MUST yield an equivalent retrieval projection.

If the current stored retrieval row already matches source revision/hash, dependency hash, and recipe/model fingerprints, the implementation MAY return `already_current` without regenerating embeddings.

### 22.5 Source-first failure semantics

If indexing fails:

- no LLD-01 source file is rolled back;
- the source commit remains valid;
- the old retrieval projection, if any, is treated stale and excluded from normal current search;
- the runtime reports derived-state failure;
- startup reconciliation, `doctor`, or `reindex` can repair it.

## 23. Deletion and Revision Replacement

### 23.1 New current revision

When an entry publishes revision `N+1`, `index_entry(entry_id)` atomically replaces retrieval rows for revision `N` with rows for `N+1` after new embeddings are successfully prepared.

Normal search therefore never intentionally returns both revisions.

### 23.2 Entry deletion

If LLD-01 performs an approved hard source deletion, the application invokes:

```text
remove_entry_from_index(entry_id)
```

which deletes retrieval entry/chunk/FTS/embedding rows transactionally and invalidates the vector cache.

### 23.3 Historical revisions

Historical revisions are not kept in retrieval-owned tables. They remain available through LLD-01 exact read/hydration by stable `EvidenceRef`.

## 24. Full Reindex Contract

### 24.1 Purpose

`reindex` rebuilds all retrieval-owned state from authoritative current source.

It is required when:

- retrieval tables are missing/corrupt;
- recipe/model identity changes;
- a large catalog/source reconciliation occurred;
- smoke testing needs a clean index;
- the user explicitly requests maintenance.

### 24.2 No background worker

`reindex` is an explicit foreground maintenance operation in v1.

The terminal/UI may display progress, but there is no resident queue or daemon.

### 24.3 Algorithm

1. Acquire the local retrieval/index write lock.
2. Set `retrieval_meta.index_state = building`.
3. Clear retrieval-owned tables only.
4. Enumerate all current committed entries from LLD-01.
5. For each entry:
   - validate authoritative current source;
   - chunk deterministically;
   - batch-embed locally;
   - write retrieval rows transactionally.
6. Verify global corpus invariants.
7. Set current recipe/model metadata.
8. Set `index_state = current` and `full_reindex_completed_at`.
9. Rebuild/invalidate vector cache.
10. Release lock.

### 24.4 Crash behavior

If the process crashes while reindexing:

- source evidence remains untouched;
- `index_state` remains `building` or fails final verification;
- normal search MUST NOT represent the partially rebuilt corpus as complete;
- rerunning `reindex` from the beginning is safe.

V1 deliberately accepts temporary search unavailability during explicit full reindex instead of implementing a more complex shadow-index cutover.

## 25. Retrieval Availability and Degraded Modes

### 25.1 Component states

Logical component states:

```text
healthy
stale
unavailable
building
```

Components:

```text
structured metadata
fts
semantic
```

### 25.2 Structured metadata failure

If SQLite structured retrieval metadata cannot be read, `search_evidence` is `retrieval_unavailable` because candidate eligibility/currentness cannot be established safely.

### 25.3 FTS failure

If FTS is unavailable/stale while structured metadata + semantic search are healthy:

- search semantic-only;
- `status=degraded`;
- include `"fts"` in `degraded_components`.

### 25.4 Semantic failure

If semantic search is unavailable/stale while structured metadata + FTS are healthy:

- search lexical-only;
- `status=degraded`;
- include `"semantic"` in `degraded_components`.

### 25.5 Both retrieval modalities fail

If both FTS and semantic search are unusable:

```text
status = retrieval_unavailable
cards = []
incomplete = true
```

The conversational agent may continue without historical search but must not claim it checked history.

### 25.6 Per-entry staleness

Known-stale current entries are excluded from search results and counted in `omitted_stale_entries`.

If this count is non-zero, `incomplete=true`.

## 26. Exact/Structured Retrieval Outside `search_evidence`

### 26.1 `get_current_state`

Owned by LLD-01/LLD-02 and does not use FTS/vector search.

### 26.2 `get_recent_work`

The application convenience operation SHOULD primarily use current entry metadata ordered by occurrence/commit time rather than semantic search.

LLD-03 MAY supply the exact query implementation over `entries`/`retrieval_entries`, but it MUST NOT force a vector search for a purely chronological request.

### 26.3 Design principle

Use the cheapest deterministic access path that matches the question:

```text
known exact/current state -> SQL/domain read
chronological recent work -> SQL
fuzzy evidence question -> FTS + vector hybrid
source detail -> hydrate by EvidenceRef
```

The LLM chooses among high-level user-intent tools, not among storage engines.

## 27. Source Hydration and Commit Provenance

### 27.1 Material use of prior evidence

When retrieved prior evidence materially influences a new conversation/commit, LLD-02 may emit:

```json
{"entry_id":"<uuid>","revision":2}
```

from the `EvidenceRef` returned by this LLD.

LLD-01 persists it as a source-entry reference.

### 27.2 No chunk IDs in durable source provenance

Durable SessionEntry `source_refs` MUST reference entry/revision identity, not `chunk_id`.

Chunk IDs are derived from the retrieval recipe and may change when retrieval implementation changes. They are unsuitable as durable professional-evidence references.

### 27.3 Hydration independent of index health

If the caller already has a valid EvidenceRef, source hydration can succeed even when FTS/vector search is unavailable because it reads LLD-01 source directly.

## 28. Privacy and Trust Behavior

### 28.1 Local processing

V1 lexical indexing, embeddings, vector search, and retrieval fusion occur locally.

No professional evidence is sent to an external search/vector/embedding provider by this LLD.

### 28.2 Model-visible retrieval

Only the selected EvidenceCards and explicit hydrated evidence are inserted into conversational model context.

The entire vault MUST NOT be preloaded.

### 28.3 Search index privacy

The SQLite database contains derived private evidence text and embeddings. It belongs inside the user's private vault and MUST NOT be committed to the public repository.

### 28.4 Embeddings are private derived data

Embeddings MUST be treated as private user data even though they are not human-readable source text.

Deleting/exporting a vault must treat the retrieval database consistently with private derived data.

### 28.5 No hidden external telemetry

The retrieval adapter MUST NOT send query text, chunk text, embeddings, or private identifiers to third-party telemetry by default.

## 29. Performance and Token-Efficiency Requirements

### 29.1 Interaction goals

Retrieval should feel effectively immediate at expected local scale.

Target engineering budgets on the primary development laptop after warm model/cache load:

```text
structured filter resolution: < 50 ms typical
FTS candidate generation:     < 100 ms typical
vector candidate generation:  < 150 ms typical at ordinary corpus size
fusion/card building:          < 50 ms typical
```

These are implementation targets, not correctness invariants.

### 29.2 Cold embedding model load

Cold local model initialization may exceed interactive search targets. The persistent terminal SHOULD keep the embedding adapter loaded after first use for the process lifetime unless memory pressure requires otherwise.

### 29.3 Model-context cost

- default search page: 8 compact cards;
- each card target: ~180 tokens or less;
- hydration: max 4 entries per call;
- search before hydration;
- no numeric debug payload in model context;
- no raw transcript injection by default.

### 29.4 No LLM retrieval subcalls

The retrieval subsystem performs no LLM calls for:

- query classification;
- lexical query generation;
- embedding generation;
- reranking;
- snippet generation;
- fusion;
- staleness detection;
- indexing.

This preserves the user's conversational-model quota for actual thinking/coding use.

## 30. Retrieval Smoke-Test and Evaluation Framework

### 30.1 Purpose

The evaluation framework exists to answer a practical question:

> Given a real professional query, did retrieval surface the experiences a human considers relevant?

It is not intended to produce an AI-defined quality ranking of career stories.

### 30.2 Two evaluation modes

#### Labeled retrieval cases

A case may record human-known relevant entries:

```yaml
id: changed-direction-after-evidence
query: "Tell me about a time I changed technical direction after new evidence"
filters:
  domains: [engineering]
expected_relevant:
  - <entry-id-a>
  - <entry-id-b>
review_pages: 3
```

The harness reports:

- which expected relevant IDs were returned;
- which were missed;
- recall within reviewed pages;
- retrieved result count/pages traversed;
- degraded/stale component state.

It does **not** require a particular winner/order unless a future evaluation explicitly tests ordering mechanics.

#### Unlabeled human-review queries

Question-bank items or ad hoc prompts may be run without labels. The harness prints/cards all retrieved candidates for manual review and allows the user to later mark:

```text
relevant
not relevant
uncertain
```

Those labels may become future regression cases.

### 30.3 Public versus private evaluation data

Public repository:

- synthetic SessionEntries;
- synthetic retrieval cases;
- no real user/employer data;
- no copyrighted/private interview bank unless redistribution rights allow it.

Private vault/local test configuration:

- user's real question banks;
- real entry IDs;
- personal relevance judgments;
- optional local retrieval-evaluation history.

### 30.4 Primary evaluation philosophy

Because the product favors recall and human choice, v1 retrieval evaluation emphasizes:

- known-relevant recall;
- obvious junk detection through manual review;
- regression detection after changing chunking/embeddings/fusion;
- exact identifier/name recovery;
- semantic paraphrase recovery.

MRR, NDCG, AI story scoring, and learned relevance models are not required for v1.

## 31. Adversarial and Correctness Tests

The implementation MUST include evidence for at least these behaviors:

| Requirement / invariant | Test / evidence |
|---|---|
| FTS and vectors use same chunk corpus | compare current chunk IDs against FTS/embedding row sets |
| deterministic chunking | same entry/revision/recipe produces identical chunk IDs/text hashes across runs |
| current revision only | correction creates revision N+1; search never returns N as current |
| stale revision excluded | force failed reindex after revision change; old result is omitted and incomplete=true |
| exact identifier retrieval | synthetic names/acronyms/IDs recover through FTS |
| semantic paraphrase retrieval | query with no important lexical overlap returns known semantic match |
| structured date filter | out-of-range semantically strong item is excluded |
| entity alias filter | unambiguous alias resolves; ambiguous alias returns typed error |
| FTS outage degradation | semantic results returned with explicit degraded status |
| semantic outage degradation | lexical results returned with explicit degraded status |
| both modalities unavailable | typed retrieval_unavailable; no false empty-match claim |
| hydration authority | mutate derived index text; hydration still returns immutable source entry |
| historical hydration | old valid revision returns status=historical/current_revision=N |
| source-first safety | index failure leaves LLD-01 source intact |
| reindex idempotency | two full reindexes produce equivalent current chunk/ref sets |
| recipe change invalidation | change recipe/model fingerprint; old component becomes stale |
| embedding validation | wrong dimension/NaN vector rejected before transaction |
| no score leakage | normal model-facing card schema contains no numeric ranking score |
| bounded cards | fixture snippets/card serialization respect limits |
| private repo separation | generated SQLite index absent from public fixture repo except synthetic test databases |

## 32. Observability and Diagnostics

### 32.1 Operational diagnostics

Local diagnostics MAY record:

- query duration by stage;
- lexical candidate count;
- semantic candidate count;
- fused candidate count;
- number of stale entries omitted;
- vector cache size/build time;
- index update duration;
- reindex progress;
- embedding model/recipe identity;
- component health state.

### 32.2 Private content logging

Diagnostics SHOULD NOT persist full query text, chunk text, EvidenceCards, embeddings, or hydrated entry content by default.

A user-enabled local debug mode MAY temporarily display scores/query details interactively, but should not create a new durable shadow transcript unless explicitly requested.

### 32.3 `doctor` integration

LLD-01 `doctor` or an LLD-03 diagnostic helper MUST be able to report:

- retrieval table existence;
- recipe/model metadata mismatch;
- missing/current-stale retrieval entries;
- current source entries absent from index;
- retrieval entries whose source revision/hash no longer matches;
- dependency-hash mismatch;
- FTS/chunk row mismatch;
- embedding/chunk row mismatch;
- wrong embedding dimensions/model IDs;
- `index_state=building/stale` left after interrupted maintenance.

Repair of retrieval-owned state may be offered through explicit reindex/reconcile behavior, but doctor never rewrites authoritative source.

## 33. Failure Semantics

| Failure | Required behavior |
|---|---|
| entry source missing/corrupt during indexing | fail index update; report source problem; do not invent retrieval row |
| local embedding model unavailable | preserve old index as stale; search FTS-only if safe |
| embedding generation fails for one new entry | keep old projection stale/excluded; source commit remains valid |
| SQLite write fails | rollback retrieval transaction; source unchanged |
| FTS query error | degrade to semantic if healthy; report FTS degradation |
| vector cache build fails | degrade to FTS if healthy; report semantic degradation |
| one entry stale | exclude it, set incomplete=true, report count |
| reindex interrupted | index_state remains building/stale; rerun safe |
| entity filter ambiguous | return typed ambiguity; never choose silently |
| EvidenceRef revision absent | hydration status not_found |
| requested historical ref exists | return exact old revision marked historical |
| all search components unhealthy | retrieval_unavailable; conversation may continue without claiming retrieval |

## 34. Concurrency, Locking, and Idempotency

### 34.1 Single-process/single-writer assumption

V1 assumes one local active writer per vault.

A filesystem/process lock owned by the application SHOULD prevent two CLI instances from concurrently mutating retrieval state for the same vault.

### 34.2 SQLite transaction boundaries

Each `index_entry` replacement is one SQLite transaction covering:

- retrieval entry metadata;
- mode/domain rows;
- chunk rows;
- FTS rows;
- embedding rows.

Vector generation happens before this transaction.

### 34.3 Search during incremental update

SQLite snapshot/transaction semantics may allow reads while a single entry update commits. Search must observe either the old complete derived state or the new complete derived state, never partial rows from that transaction.

Because currentness is validated against LLD-01 current revision/hash, an old projection whose source has already advanced is filtered as stale.

### 34.4 Full reindex lock

Full reindex owns the retrieval write lock for its duration. Search while `index_state=building` SHOULD return explicit unavailable/incomplete state rather than pretending the partially rebuilt index is complete.

## 35. Cost and Scaling Consequences

### 35.1 Monetary cost

V1 retrieval has no per-query hosted-search or embedding API cost.

Costs are local:

- disk for SQLite text/vectors;
- CPU for embeddings and exact search;
- memory for optional vector cache;
- one-time model-weight download/cache.

### 35.2 Storage estimate

At 384 dimensions and float32:

```text
1 vector ~= 1,536 bytes before SQLite overhead
10,000 chunks ~= 15 MB raw vector bytes
50,000 chunks ~= 77 MB raw vector bytes
100,000 chunks ~= 154 MB raw vector bytes
```

FTS/chunk text adds additional but still modest local storage at expected personal scale.

### 35.3 Write amplification

Each changed entry writes:

- one retrieval entry row;
- a small number of mode/domain rows;
- approximately one overview + populated section/state chunks;
- one FTS row per chunk;
- one embedding per chunk.

This is acceptable at one-user conversational write volume.

## 36. Alternatives Considered

### 36.1 Vector-only retrieval

**Rejected.** Exact names, acronyms, metrics, identifiers, technologies, and quoted phrases benefit materially from FTS.

### 36.2 FTS-only retrieval

**Rejected.** Interview and reflective queries frequently paraphrase experiences using different vocabulary from the original entry.

### 36.3 Let the LLM choose SQL versus FTS versus vector

**Rejected.** It wastes model capability/tokens, adds nondeterminism, and burdens weaker models with storage-engine knowledge.

### 36.4 LLM reranking after hybrid retrieval

**Rejected for v1.** It consumes quota, adds latency, and risks turning retrieval into AI story selection. Deterministic RRF is adequate for initial personal scale.

### 36.5 `sqlite-vec` as the initial vector backend

**Deferred.** It is a reasonable future adapter, but exact in-process NumPy search removes native-extension installation friction and is sufficient at expected corpus scale.

### 36.6 Dedicated vector database/OpenSearch

**Rejected for v1.** Operational complexity is unjustified for a small local personal corpus.

### 36.7 Raw transcript indexing

**Rejected/deferred for v1.** It increases noise and private-context exposure. Raw transcripts remain available for re-extraction and future targeted search if structured-only retrieval proves insufficient.

### 36.8 Journal indexing

**Rejected.** The daily journal is a projection over the same entries and would duplicate evidence in the search corpus.

### 36.9 Learned fusion model

**Rejected.** No labeled dataset or need justifies a learned ranker. RRF is transparent and deterministic.

### 36.10 Hard cosine relevance threshold

**Rejected for v1.** It risks hiding useful low-score experiences and conflicts with the high-recall retrieval philosophy.

### 36.11 Shadow-index atomic full reindex

**Deferred.** Derived search may be temporarily unavailable during explicit maintenance. A shadow cutover adds complexity without a current availability requirement.

## 37. Repository / Module Change Map

Representative public implementation layout:

```text
src/professional_brain/
├── domain/
│   └── retrieval_types.py
├── application/
│   ├── retrieval/
│   │   ├── search_service.py
│   │   ├── hydration_service.py
│   │   ├── index_service.py
│   │   ├── chunker.py
│   │   ├── fusion.py
│   │   └── filters.py
│   └── ports/
│       ├── evidence_retriever.py
│       └── embedding_provider.py
├── adapters/
│   ├── sqlite/
│   │   ├── retrieval_repository.py
│   │   └── retrieval_fts.py
│   └── embeddings/
│       └── bge_small_local.py
└── diagnostics/
    └── retrieval_doctor.py

migrations/
└── <retrieval migration files>

tests/
├── unit/
│   └── retrieval/
├── integration/
│   └── retrieval/
└── retrieval-smoke/
    ├── synthetic-vault/
    └── cases/
```

Exact module names remain implementer discretion; ownership boundaries do not.

## 38. Cross-LLD Contract Register

### 38.1 Contracts owned by LLD-03

| Contract | Consumers |
|---|---|
| searchable corpus = current SessionEntry revisions | LLD-01, LLD-02, LLD-04 |
| `PSB-RETRIEVAL-RECIPE@1` chunk semantics | diagnostics, index lifecycle |
| `EvidenceRef {entry_id, revision}` | LLD-01, LLD-02, LLD-04 |
| `EvidenceFilters` | LLD-02, LLD-04 |
| `EvidenceCard` | LLD-02, LLD-04 |
| pageable `search_evidence` request/result + opaque cursor | LLD-02, LLD-04 |
| `hydrate_evidence` request/result | LLD-02, LLD-04 |
| retrieval component/degraded/incomplete/cursor-expiry semantics | LLD-02, LLD-04 |
| `index_entry`/remove/reindex internal hooks | LLD-01, diagnostics |
| retrieval staleness/dependency rules | LLD-01, diagnostics |
| hybrid RRF behavior | retrieval tests/evaluation |
| local embedding identity/backend | installer/config/diagnostics |
| retrieval smoke-test case contract | LLD-04, public/private test harness |

### 38.2 Contracts consumed from LLD-01 v2

| LLD-01 contract | LLD-03 usage |
|---|---|
| UUIDv7 entry/session/entity/artifact identities | stable source relationships |
| current SessionEntry revision and immutable historical revisions | search corpus + hydration |
| `entries.current_revision/current_hash` | currentness/staleness validation |
| statement sections | deterministic semantic chunks |
| modes/domains | filters and card metadata |
| occurrence/provenance | structured filters/cards |
| `entry_entities`/entity catalog | filters + search metadata |
| `entry_artifacts`/artifact catalog | card/hydration/search metadata |
| source-first commit ordering | indexing occurs only after source publication |
| catalog dependency-change hook | marks affected entries stale/reindexes searchable metadata |
| rebuildable SQLite posture | retrieval tables are derived |

### 38.3 Contracts consumed from LLD-02 v2

| LLD-02 contract | LLD-03 usage |
|---|---|
| model-facing tool surface | exposes only search/hydrate, never SQL/vector primitives |
| default page size 8 | default `search_evidence.page_size` |
| read-before-hydrate context pattern | card/hydration separation |
| context budget | compact card design/max hydration refs |
| source-entry refs in CommitDraft | use `EvidenceRef` identity |
| retrieval outage semantics | typed degraded/unavailable result |
| no retrieval LLM reranker requirement | deterministic fusion only |

### 38.4 Contracts consumed/validated with LLD-04

LLD-04 MUST preserve:

- high-recall Career queries;
- bounded pages plus explicit continuation rather than a story winner;
- question-bank text as a separate corpus, never inserted into the professional-evidence index;
- user CareerCandidateMarks as an overlay/reference to EvidenceRefs, not a retrieval score;
- question-bank queries as optional unlabeled/labeled smoke inputs;
- human relevance labeling as evaluation evidence;
- projection-specific query phrasing without changing underlying search storage contracts.

### 38.5 Thin local interface boundary

The local adapter may display degraded/incomplete search, reindex progress, ambiguous filters, and optional debug scores. Debug scores MUST remain outside normal model context and MUST NOT be presented as interview-story quality. No dedicated CLI LLD is required for these mechanics in v1.

## 39. Documentation Drift / Consolidated Sibling Refinements

Version 2 consolidates the previously pending LLD-01 dependency-invalidation hook and replaces the v1 `limit 1..20` total-result contract with bounded `page_size 1..20` plus opaque continuation. This changes retrieval traversal, not professional-evidence authority or the internal RRF algorithm.

No genuine conflict remains among `PSB-HLD-001 v2`, `PSB-LLD-001 v2`, and `PSB-LLD-002 v2`. LLD-04 consumes these contracts without introducing a second evidence index.

## 40. Ordered Implementation Plan

### Step 1 — Implement retrieval domain types

Implement validators/value objects for:

- EvidenceRef;
- EvidenceFilters;
- EvidenceCard;
- SearchEvidenceRequest/Result and opaque SearchCursor validation;
- HydratedEvidence;
- component/index states.

**Gate:** normative JSON examples validate; unknown keys/invalid limits/dates/provenance fail deterministically.

### Step 2 — Implement deterministic chunker

Implement `PSB-RETRIEVAL-RECIPE@1` over synthetic SessionEntry fixtures.

**Gate:** golden tests prove deterministic chunk IDs/text hashes and same output across repeated runs.

### Step 3 — Add retrieval-owned SQLite migrations

Create retrieval metadata, mode/domain, chunk, FTS, embedding, and meta tables.

**Gate:** migration up/down/rebuild test preserves LLD-01 tables and creates no authoritative source dependency.

### Step 4 — Implement FTS indexing/search

Add safe query parsing, structured-filter joins, weighted BM25 candidate generation, entry grouping, and snippets.

**Gate:** exact identifiers/names/phrases and filtered lexical cases pass.

### Step 5 — Implement local embedding adapter

Add the default BGE-small local adapter with query/document operations, vector normalization, dimension validation, and local cache behavior.

**Gate:** adapter produces deterministic-shape finite 384-d normalized vectors on target laptop.

### Step 6 — Implement exact vector backend

Load stored vectors to matrix cache, apply eligible-entry mask, compute exact dot-product candidates, group by entry.

**Gate:** semantic paraphrase fixtures recover known matches and meet ordinary-corpus latency target.

### Step 7 — Implement RRF fusion and EvidenceCards

Fuse branch ranks, deterministic tie-break, snippets/metadata, no numeric score leakage.

**Gate:** hybrid fixtures produce deterministic card ordering and model-facing schema.

### Step 8 — Implement source hydration

Read exact immutable revisions through LLD-01, resolve entity/artifact metadata, mark current/historical status.

**Gate:** poisoned derived index fixture cannot alter hydrated source result.

### Step 9 — Implement incremental index hook

Wire `index_entry` after LLD-01 source publication with embeddings-before-delete and one SQLite replacement transaction.

**Gate:** induced embedding/SQLite failures never damage source and never expose stale old revision as current.

### Step 10 — Implement staleness/doctor/reindex

Add recipe/dependency validation, component health, explicit full rebuild, interrupted reindex detection.

**Gate:** delete/corrupt/recipe-change fixtures are detected and recover through explicit reindex.

### Step 11 — Build retrieval smoke harness

Support labeled relevant-entry sets plus unlabeled human review from synthetic/public and private question sources.

**Gate:** harness reports recall/misses without requiring a story winner or AI evaluator.

### Step 12 — Final sibling cross-review

Cross-review LLD-01/02/03 exact shared contracts before core implementation baseline freeze.

**Gate:** report only genuine conflicts, documentation drift, Consult, Blocker, readiness; no unresolved cross-contract ambiguity remains.

## 41. Objective Acceptance Criteria

LLD-03 is implementation-ready when all are true:

- current SessionEntry revisions are the only normal searchable source;
- deterministic chunking produces one shared FTS/vector corpus;
- FTS5 retrieves exact names, identifiers, acronyms, and phrases from fixtures;
- semantic search retrieves paraphrased known-relevant evidence with no important lexical overlap;
- structured filters are applied before candidate truncation;
- entity ambiguity is surfaced rather than guessed;
- hybrid search uses deterministic RRF with `k=60`;
- search returns compact score-free EvidenceCards with stable EvidenceRefs and a continuation cursor when more candidates remain;
- pagination can traverse beyond the first 20 candidates without a product-level hard total cap;
- a stale cursor after index-generation change fails as `cursor_expired` rather than silently changing the sequence;
- `hydrate_evidence` reads authoritative immutable source, not index text;
- stale old revisions cannot appear as current search results;
- partial FTS/vector outages degrade explicitly rather than silently;
- both search modalities unavailable returns retrieval_unavailable, not healthy empty results;
- per-entry staleness sets incomplete=true and reports omitted count;
- incremental index update is idempotent and source-safe;
- full reindex is restart-safe and may temporarily disable complete search without affecting source;
- default embeddings are local and no private evidence is sent to hosted embedding/vector services;
- no LLM call is used for indexing, embedding, query routing, snippet creation, fusion, or reranking;
- retrieval smoke tests support human-known relevant sets and unlabeled question-bank review across one or more pages;
- public tests contain only synthetic/distributable data;
- LLD-01/02/04 cross-review agrees on EvidenceRef/card/pagination/hydration/index-staleness contracts.

## 42. Design Decision Register

| Decision | Status | Rationale |
|---|---|---|
| current structured entries as v1 search corpus | Resolved | curated durable evidence; lower noise than transcripts |
| raw transcript search | Implementer discretion? No — deferred | not part of v1 contract |
| overview + section + state chunks | Resolved | balances context and granularity |
| deterministic SHA-256 chunk IDs | Resolved | rebuildable/idempotent derived identity |
| BAAI/bge-small-en-v1.5 default | Resolved subject to implementation validation | small local English retrieval model, 384 dims |
| exact local NumPy vector search | Resolved | simplest install and adequate personal scale |
| sqlite-vec | Deferred | swap adapter if scale warrants |
| FTS5 unicode61 | Resolved subject to target build validation | exact lexical recovery with SQLite-native index |
| RRF k=60 | Resolved | score-scale-independent deterministic fusion |
| no universal cosine threshold | Resolved | protect recall |
| score-free model-facing cards | Resolved | avoid ranking anchoring and token noise |
| bounded page size + opaque continuation, no total cap | Resolved | preserves token efficiency without silently hiding later candidates |
| EvidenceRef = entry_id + revision | Resolved | durable source identity independent of chunk recipe |
| max 4 hydration refs/call | Resolved | bounded context and weak-model simplicity |
| no background jobs | Resolved | local simplicity; explicit reconciliation |
| in-place explicit full reindex | Resolved | derived index availability not critical enough for shadow cutover |
| query-time LLM reranking | Rejected v1 | quota/latency/nondeterminism |
| user/human relevance labels for smoke tests | Resolved | matches human-in-driver-seat philosophy |

## 43. Consult, Blocker, and Validation Prerequisites

### Consult

None currently.

### Blocker

The core LLD implementation baseline MUST NOT freeze until LLD-01, LLD-02, LLD-03, and LLD-04 complete sibling cross-review of:

- current-source identity/staleness;
- dependency invalidation;
- EvidenceRef;
- EvidenceCard;
- pageable search/hydration result semantics and cursor expiry;
- source-first index hook ordering.

This does not block continued LLD authoring.

### Validation prerequisites

- FTS5 present and tokenizer behavior verified on target SQLite build.
- Default embedding adapter/model executes locally and returns required vector shape.
- Retrieval smoke corpus demonstrates acceptable useful recall before the embedding default is frozen for implementation release.
- Exact vector-search latency/memory verified at representative synthetic scale.

## 44. Final Coding-Agent Readiness Gate

Before publication as the frozen implementation baseline, verify:

- all shared types match sibling LLDs exactly;
- no retrieval-owned field has become an authoritative source field;
- no old entry revision can leak through normal search after correction/re-extraction;
- FTS and semantic indexes are provably the same chunk corpus when healthy;
- every index member has a current access/correctness requirement;
- public/private repository boundaries are preserved;
- no hidden hosted embedding/search call exists;
- no model-facing retrieval path exposes raw storage primitives;
- no example includes numeric career/story scoring;
- no implementation agent must invent chunking, filter, fusion, hydration, staleness, or failure behavior.

If these checks pass after sibling cross-review, `PSB-HLD-001 v2 + PSB-LLD-001 v2 + PSB-LLD-002 v2 + PSB-LLD-003 v2 + PSB-LLD-004 v1` form a coherent local v1 design set suitable for freezing the implementation baseline.
