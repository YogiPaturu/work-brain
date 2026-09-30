# Work Brain — Future Considerations

**Status:** Non-normative design notes
**Purpose:** Preserve deferred ideas, possible extensions, and future design questions without making them requirements for the current implementation baseline.

These items are intentionally outside the current HLD/LLD contract unless a future revision explicitly promotes them into scope.

## Future Projections and Use Cases

### Teach
Use accumulated professional evidence to help explain concepts, decisions, trade-offs, and lessons to other people.

Design intent:
- Reuse existing context, reasoning, alternatives, outcomes, and learning.
- Do not require a dedicated teaching schema.
- Derive explanations from existing evidence.
- Preserve any explicit principles or lessons the user naturally states, but do not force a separate "generalization" field into every entry.

### Quiz / Learning
Generate questions based on the user's own work history and things they reasonably should understand from their experience.

Possible forms:
- Technical concept checks based on systems the user designed or debugged.
- Questions about assumptions that later proved wrong.
- Questions about architecture trade-offs previously considered.
- Business/product questions based on customer or market decisions.
- Reflection questions about lessons, feedback, and changed beliefs.

This should remain a projection over existing evidence rather than create a separate learning data model.

### Performance Review / Promotion
Use professional evidence to reconstruct:
- impact;
- ownership;
- scope;
- difficult decisions;
- leadership;
- technical depth;
- business/customer impact;
- growth over time.

The system should surface supporting evidence rather than invent a performance narrative unsupported by the journal.

### Writing and Knowledge Sharing
Potential outputs:
- technical articles;
- internal design explanations;
- project retrospectives;
- case studies;
- portfolio material;
- onboarding or handover documents;
- founder/company-history narratives.

These should consume canonical evidence and artifacts rather than create parallel source-of-truth records.

### Career Extensions
Possible future workflows:
- CV and LinkedIn updates;
- recruiter conversations;
- performance-review preparation;
- promotion packets;
- networking/casual project explanations;
- career-trajectory review;
- strength and leverage analysis;
- project/career retrospectives.

## Career and Interview Intelligence

### Automatic Career Annotations
A future projection may inspect entries and derive signals such as:

- ownership;
- conflict;
- influence;
- ambiguity;
- technical depth;
- customer focus;
- execution;
- judgment;
- learning;
- impact;
- leadership;
- strategy.

These annotations should:
- remain derived and replaceable;
- reference canonical entry IDs;
- be regenerable when SOPs, models, or question banks improve;
- never overwrite the source journal entry;
- never be treated as the user's judgment of story quality.

### User-Selected Interview Candidates
If the user explicitly says an experience is a useful interview example, preserve that as durable user-authored preference.

Keep distinct:
1. automatic relevance signals;
2. explicit user candidate marks;
3. runtime story selection for a specific interview question.

Do not introduce AI story scores or "best story" rankings.

### Question Banks
Support multiple question-bank sources:
- public or redistributable bundled banks;
- private local banks;
- company-specific banks;
- personal question collections.

Question banks remain separate from the professional evidence corpus.

Future improvements may include:
- more providers;
- refreshed company-specific material;
- personal tagging;
- question coverage analysis;
- retrieval regression cases based on human-marked relevant experiences.

## Domain-Aware Thinking and Probing

The evidence schema should remain domain-neutral, while probing can become increasingly domain-aware.

Potential probe packs include:
- engineering;
- architecture;
- debugging;
- product;
- customer research;
- sales;
- marketing;
- business development;
- strategy;
- leadership;
- hiring;
- people management;
- founder decisions.

The goal is to allow very different query and reasoning patterns without creating separate journal schemas.

A future system may become substantially better at switching probe packs automatically based on conversation context.

## Model and SOP Evolution

The system should continue to target modest model requirements for routine use.

Future work may include:
- evaluating weaker models against representative conversations;
- refining SOPs and examples to reduce dependence on model capability;
- measuring which tasks require stronger reasoning;
- optional routing between probing, extraction, coaching, and lightweight transformation models;
- re-driving historical conversations with better extraction models.

Known limitation:
- preserved raw conversations protect against bad extraction and schema changes;
- they do not recover information that a weak conversational model failed to elicit in the first place.

SOP quality, examples, retrieval context, and probe packs should reduce this risk but cannot eliminate it.

## Interface Evolution

### CLI / TUI
The initial CLI should remain thin.

A dedicated interface LLD may become worthwhile if the product later adds:
- full-screen TUI;
- multiple concurrent sessions;
- richer browsing;
- background status indicators;
- persistent panes;
- complex navigation;
- configurable keybindings;
- local daemon behavior.

### Mobile Capture
Possible future capabilities:
- quick voice capture;
- phone-based thinking sessions;
- mobile journal review;
- offline capture;
- cross-device continuity.

Do not add mobile-specific IDs, synchronization fields, or device state until a real mobile requirement exists.

### Voice
Current local speech-to-text can remain an input adapter.

Future possibilities:
- native voice session UX;
- automatic transcription metadata;
- speaker-aware capture;
- voice-specific editing or confirmation.

## Hosted / Cloud Version

A future hosted version may replace local adapters without changing the core domain model.

Potential areas:
- hosted evidence store;
- remote retrieval;
- account identity;
- encryption and secrets;
- multi-device sync;
- backup and recovery;
- web/mobile clients;
- scheduled processing;
- managed integrations.

AWS remains a possible implementation environment, not a current architectural requirement.

Potential future services should be selected only when real requirements justify them. Do not introduce DynamoDB, OpenSearch, S3, queues, workers, or other cloud infrastructure merely to prepare for hypothetical scale.

## Multi-Device Sync

This is intentionally deferred.

Future design will need to decide:
- source-of-truth ownership;
- conflict handling;
- offline edits;
- session concurrency;
- amendment ordering;
- index synchronization;
- encryption;
- deletion semantics.

Do not synchronize a mutable SQLite database directly between devices.

## Connectors and External Artifacts

Potential integrations:
- GitHub;
- Google Drive;
- Google Docs;
- Google Sheets;
- Slack;
- Calendar;
- email;
- task-management systems;
- CRM systems.

Design intent:
- artifacts remain supporting evidence;
- avoid copying information that already has a durable external source;
- preserve links, identifiers, and relevant context;
- use adapters behind stable application ports;
- add connector-specific LLDs only when a concrete integration is being implemented.

The system should remain useful without connectors.

## Team Communication

Potential future outputs:
- WhatsApp updates;
- standup summaries;
- weekly meeting preparation;
- stakeholder updates;
- project explanations;
- handoff summaries.

Private reasoning must remain private by default.

Communication projections should intentionally sanitize:
- uncertainty not intended for the audience;
- private disagreement;
- sensitive reflections;
- confidential material;
- raw internal reasoning.

## Operational Intelligence

Possible future queries:
- what work is repeatedly blocked;
- what kinds of tasks are underestimated;
- which commitments are frequently carried over;
- recurring dependencies;
- priority drift;
- context-switch costs;
- unresolved decisions;
- stale open loops;
- forecast versus actual outcomes.

These should derive from existing state transitions, expectations, outcomes, and journal evidence.

## Business and Founder Intelligence

The journal may support analysis beyond engineering, including:
- customer assumptions;
- sales objections;
- positioning hypotheses;
- acquisition channels;
- pricing decisions;
- strategy changes;
- product discovery;
- business-model evolution;
- market interpretation;
- investor/fundraising preparation;
- company history.

This does not require a separate business schema.

The same core evidence model should support domain-specific query patterns and probe packs.

## Retrieval Evolution

Current retrieval should remain lightweight.

Potential future improvements:
- alternative embedding models;
- sqlite-vec or another vector implementation;
- approximate nearest-neighbor search if data volume ever justifies it;
- learned or model-assisted reranking;
- richer metadata filtering;
- project/person/customer/entity views;
- temporal weighting;
- relationship-aware retrieval;
- retrieval evaluation dashboards.

Any change should preserve:
- canonical evidence ownership;
- regenerability of indexes;
- human control over story selection;
- high recall for career queries;
- no hidden dependence on one embedding provider.

## Background Processing and Automation

The initial system should have no required daemon or worker.

Possible future background jobs:
- scheduled reindexing;
- automatic career annotation;
- periodic project summaries;
- monthly/quarterly retrospectives;
- open-loop follow-up;
- stale-state detection;
- scheduled backup;
- connector synchronization.

Only introduce background processing when the user benefit outweighs the operational complexity.

## Historical Backfill

Future improvements may make backfill richer:
- artifact-assisted reconstruction;
- Git history;
- old docs;
- calendar context;
- project timelines;
- interview-focused reconstruction.

Backfilled evidence must continue to distinguish:
- what was known or believed at the time;
- what is remembered later;
- what later evidence revealed.

Do not rewrite historical belief with hindsight.

## Privacy, Security, and Publication

The public repository should contain:
- application code;
- generic Skills/SOPs;
- schemas;
- generic probe packs;
- architecture documents;
- publication-safe test data;
- generic example question banks where redistribution is allowed.

The private vault should contain:
- real conversations;
- journal entries;
- personal career facts;
- employer/project history;
- customer details;
- private question banks;
- confidential artifacts;
- personal annotations.

Future hosted designs must explicitly address:
- encryption;
- account isolation;
- confidential employer information;
- data retention;
- export;
- deletion;
- connector permissions.

## Candidate Future LLDs

Create a new LLD only when a real requirement makes the implementation contract non-trivial.

Possible future LLDs:
- richer CLI/TUI;
- connector framework or a specific connector;
- hosted/cloud deployment;
- multi-device synchronization;
- mobile capture;
- background automation;
- advanced career annotation;
- team communication outputs.

Do not create these LLDs preemptively.

## Architectural Principle for Future Work

Future capabilities should normally be added as:

```text
existing canonical evidence
        +
new SOP / projection / adapter
        ↓
new capability
```

rather than:

```text
new capability
        ↓
new source-of-truth schema
```

Promote a future consideration into the HLD/LLD baseline only when it creates a real current requirement, invariant, interface, state-ownership rule, trust boundary, migration requirement, or implementation dependency.
