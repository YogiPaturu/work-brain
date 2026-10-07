WORK-BRAIN-EXPERIENCE-REVIEW v1

# Experience Review

Load this reference for bounded human/model review when deciding whether live
work continues a durable Experience or when reviewing related SessionEntries.
Both paths use source-backed judgment, not automatic clustering.

## What an Experience means

A Project is durable work context. An Experience is a coherent professional
story or arc within that context. One Project may contain separate Experiences,
such as diagnosing token-refresh failures, choosing a migration architecture,
recovering a failed rollout, or persuading another team to adopt an API
contract.

An Experience may span days or months when later evidence clearly continues the
same initiative, decision, incident, launch, negotiation, experiment, or
outcome arc. Time proximity, topic or technology similarity, domain tags, and
embedding similarity are not sufficient on their own.

Every member of one Experience MUST have the same exact current
`(workspace_entity_id, project_entity_id)` tuple. Stable IDs own this boundary;
matching names do not. Never use review to cross a workspace or project
context boundary.

## Review procedure

1. Start from one anchor SessionEntry and call
   `experience related --entry-id ENTRY_ID --limit 8`.
2. Treat the returned entries as bounded recall candidates, never as a grouping
   decision or similarity truth.
3. Inspect the anchor's current Experience membership.
4. For materially plausible candidates, use `experience get` or bounded
   `experience hydrate`/evidence hydration as needed. Inspect enough
   source-backed evidence to decide the boundary, not the whole vault.
5. Classify each candidate as `INCLUDE`, `EXCLUDE`, or `UNCERTAIN`.
6. Choose one outcome: extend an existing Experience, propose a new one, or
   make no change. When evidence is uncertain, leave the entry unassigned.

Useful INCLUDE signals are a shared concrete problem or objective, an entry
that explicitly follows an earlier decision or action, implementation or
rollout of that decision, a later attributable outcome or learning, a shared
incident/launch/negotiation/migration/experiment, a durable artifact that links
the narrative, or explicit user confirmation that the events were one effort.

Useful EXCLUDE signals are merely sharing a Project, technology, tag, or
competency; recurring routine work; separate incidents with similar symptoms;
independent decisions or outcomes; or semantic similarity without a causal or
goal relationship. An entry already in another coherent Experience is a
boundary signal, not a reason to move it. False merges are worse than
temporary under-grouping.

## Existing and proposed Experiences

If the anchor belongs to Experience E, members of E may be included when
relevant and ungrouped candidates may be proposed as extensions. An entry
belonging to another Experience must not be silently moved or merged; surface
its stable Experience identity and require explicit user intent for any
post-hoc change. Do not add merge or split behavior.

If the relevant entries are ungrouped and form one coherent arc, propose a new
Experience with a neutral, durable title describing the actual work. Do not use
an interview question, generic competency, unsupported outcome, or unnecessary
date as the title. Do not invent aliases from vague conversational phrases.

## Mutation and uncertainty

`experience related` is read-only. Post-hoc association is metadata mutation:
use `experience associate` only after the user explicitly approves the selected
entries and either the existing stable `experience_id` or the proposed new
title. One approval is enough. Use the application operation, never edit
catalog JSON or SessionEntry files and never rewrite historical evidence.

For clear live continuation, preserve the existing lightweight CommitDraft
behavior; do not add a second confirmation ceremony. If the continuation or
new Experience is not clear, omit the association and keep the evidence fully
searchable and durable.

Retrieval degradation or incomplete results are limitations, not evidence that
no relationship exists. Do not invent confidence or similarity scores. These
rules define bounded selection semantics; do not scan hundreds of entries or
add a background miner, or automatically create, merge, split, or associate
Experiences.

## LIVE Experience continuity

For live `think` and `operate` work, check continuity before CommitDraft
publication only when the current bounded work plausibly continues a durable
professional arc. Signals include an explicit follow-up, implementation of a
captured design or decision, an outcome following an earlier action, or another
phase of the same migration, incident, launch, negotiation, experiment, or
initiative. Routine state updates, generic planning, simple communication
drafting, and unrelated day opening or closing do not require Experience
retrieval. Backfill and career keep their own Experience semantics.

First resolve the exact current workspace and project context. Never cross the
exact `(workspace_entity_id, project_entity_id)` boundary; if it cannot be
established safely, do not attach an Experience. In `operate`, prefer the
existing bounded path: resolve context, search a compact query within that
context, inspect the returned EvidenceCards and their `experiences`, then
hydrate only selected evidence if the boundary is unclear. `think` may use the
existing bounded Experience search/get/hydrate operations when cleaner. Keep
result counts small; never scan broad history or call `experience mine` for a
live session.

Reuse one existing Experience only when exact context matches and source-backed
evidence shows the same causal or goal-directed arc. Put its stable entity ID
in the CommitDraft Experience entity candidate. For example, continuing the
Ranq workspace authorization design may reuse “Ranq authentication and
authorization design” when prior evidence clearly supports that arc; an
unrelated OAuth cleanup does not join solely because it concerns
authentication. “Start LLD2 implementation” may reuse “Ranq Auth
implementation” when exact context and prior LLD work establish that sequence.

If live work clearly forms a durable arc but no existing Experience is a clear
match, the existing CommitDraft behavior may propose a neutral durable title.
Do not create one merely because retrieval failed. If several Experiences are
plausible, continuity is only topical, context is ambiguous, or retrieval is
degraded/incomplete, leave the entry unassigned; missing candidates do not
prove no Experience exists. Surface material retrieval limitations. Unassigned
work remains searchable and historical mining may revisit it later.

Clear live continuity needs no second approval ceremony: the current session
provides its evidence and normal CommitDraft publication owns the reference.
Explicit user approval remains required for post-hoc historical changes through
`experience associate`. Do not repair a committed entry with automatic
post-commit lookup or association.

The opaque cursor belongs only to explicit historical `experience mine`
backfill traversal. Never use or persist it in open-day, operate, think,
communicate, close-day, or normal CommitDraft publication. Historical mining
is cleanup, not part of the daily live lifecycle.

## Historical mining batches

When the user explicitly asks to mine historical work, request one bounded
batch with `experience mine --page-size 5 --related-limit 6`. Review the
returned ungrouped anchors and their related-entry recall with the same
INCLUDE/EXCLUDE/UNCERTAIN criteria, hydrating only evidence needed to resolve a
plausible group. Present proposed post-hoc groupings for explicit approval,
then use `experience associate` only for the approved entries and target. Use
the returned opaque cursor for the next page; do not load hundreds of anchors
or candidates into one context and do not treat mining as automatic clustering.
