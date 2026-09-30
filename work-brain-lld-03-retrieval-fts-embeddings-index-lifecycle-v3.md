# Work Brain — LLD-003 v3: Retrieval and Index Lifecycle

**Status:** implementation contract; implementation has not started  
**Supersedes:** `work-brain-lld-03-retrieval-fts-embeddings-index-lifecycle-v2.md`  
**Parent:** [`work-brain-hld-v3.md`](work-brain-hld-v3.md)  
**Sibling:** [`work-brain-lld-02-agent-runtime-skills-session-orchestration-v3.md`](work-brain-lld-02-agent-runtime-skills-session-orchestration-v3.md)

## 1. Purpose and unchanged retrieval contract

LLD-003 remains completely harness-agnostic. Codex, Claude Code, Cursor, Yap,
and the Skill do not choose FTS versus vectors and do not contain retrieval
logic. The application exposes high-level operations equivalent to:

```text
get_current_state
get_recent_work
get_open_loops
search_evidence
hydrate_evidence
```

The host may invoke these operations as separate `work-brain` OS processes.
The CLI is an adapter, not a second evidence store. LLD-03 continues to own
searchable chunks, FTS5, local embeddings, vector search, candidate fusion,
filters, pagination, hydration, incremental indexing, staleness, and reindex.

## 2. v3 architecture correction

The earlier persistent-process assumption is removed. A command invocation MAY
start a cold embedding model and MUST NOT rely on one Work Brain process keeping
the model hot. The first implementation MUST benchmark at least:

- cold process/query latency;
- OS-cache-warm process/query latency;
- query result correctness and degraded-mode behavior;
- index rebuild cost from the durable vault.

If repeated local embedding startup is acceptable, retain the simple CLI. Do
not add a daemon preemptively. A daemon becomes a future measured optimization,
not a hidden v1 dependency.

## 3. Contracts consumed and preserved

LLD-03 consumes LLD-01's source-first SessionEntry revisions, stable entry and
revision identity, provenance, amendments, and rebuildable SQLite. It consumes
LLD-02's bounded application payloads, CLI operation boundary, and stable
`EvidenceRef`/hydration semantics. It MUST NOT know which harness initiated a
query or how Skill discovery occurred.

Search results MUST be bounded pages with opaque continuation, stable source
references, and explicit degraded/incomplete/index-state semantics. Hydration
MUST resolve stable references against authoritative source and MUST NOT expose
internal SQLite paths, vectors, prompts, or raw model reasoning as evidence.

## 4. Implementation plan

The v2 design remains the detailed schema and algorithm reference where it does
not conflict with this v3 process boundary. Before coding, cross-review and
carry forward its contracts for:

1. deterministic chunk identity and current-revision corpus membership;
2. FTS5 schema and safe query parsing;
3. embedding metadata and vector backend selection;
4. candidate fusion, structured filters, and opaque cursors;
5. source hydration and token-bounded payloads;
6. source-commit indexing hooks, idempotent reindex, and staleness detection;
7. public/private corpus separation and question-bank exclusion;
8. retrieval smoke tests and benchmark fixtures.

The LLD-03 application adapter will be callable from the CLI without a
persistent server:

```text
host shell
  -> work-brain evidence search ...
  -> EvidenceRetriever
       -> metadata/SQL
       -> FTS5
       -> local embedding/vector search
```

## 5. Readiness gate

This document is implementation-ready only after the HLD-001 v3 and LLD-002
v3 references are accepted, the CLI/capture boundary tests pass, and the
benchmark harness records cold and OS-cache-warm latency. LLD-03 implementation
must not introduce MCP, a daemon, a provider-specific retriever, or host-aware
logic.
