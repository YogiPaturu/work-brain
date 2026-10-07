WORK-BRAIN-SOP-BACKFILL v3

# Work Brain Backfill

## Overview

Reconstruct one historical professional Experience with explicit uncertainty
and `reconstructed` provenance. Preserve the distinction between what was known
at the time, what is remembered now, and what hindsight suggests. Attach it to
an existing stable Experience when the match is clear; create a new one when
the historical story is distinct; leave it unassigned when uncertain.

## Parameters

- **user_message** (required): The historical experience or memory to reconstruct.
- **historical_context** (optional): Approximate time, project, role, or surrounding context.
- **retrieved_evidence** (optional): Bounded related evidence returned by configured tools.
- **artifacts** (optional): User-identified documents, tickets, notes, or other references.
- **current_session_context** (optional): Turns already captured for this backfill.

**Constraints for parameter acquisition:**

- The agent MUST establish a persistence-compatible historical occurrence before commit; approximate or unknown time is valid when represented honestly.
- The agent MUST treat this as one coherent historical experience.
- The agent MUST retrieve related evidence when available to reduce accidental duplication, but MUST continue transparently if retrieval is unavailable.

### Conversation profile

Use the shared conversational moves with this profile:

- **Explore:** deep; allow partial, nonlinear recollection before forcing an evidence structure.
- **Probe:** deep; ask the highest-value historical frontier question one at a time.
- **Challenge:** evidence-focused; use the shared triggers for ambiguous ownership, unsupported causality, vague outcome, contradiction, or unclear terminology.
- **Resolve:** prefer source-backed artifacts or Work Brain retrieval over asking the user to guess.
- **Reflect:** only after contemporaneous facts and hindsight have been separated.

This workflow is historical evidence mode. Do not suggest what the user's remembered fact, motive, metric, ownership, sequence, or outcome probably was.

## Steps

### 1. Bound the Historical Experience

Bound the reconstruction to one coherent historical experience and establish the best-supported occurrence precision and role context. Do not force the user to provide the full structure immediately; allow useful partial recollections to emerge when they help establish the boundary.

**Constraints:**

- You MUST ask for an approximate time or explicitly record that the time is unknown or approximate.
- You MUST NOT invent a date, role, project, or sequence of events.
- You MUST split an unrelated live event or a second historical experience into another session.

### 2. Separate Time-of-Event Knowledge from Hindsight

Explore what the user remembers observing, believing, deciding, and doing at the time before imposing a complete evidence structure. Use the shared frontier to probe the highest-value unresolved historical question. Only after contemporaneous evidence is distinguished should you examine what later evidence or hindsight changed.

**Constraints:**

- You MUST distinguish contemporaneous belief from later interpretation.
- You SHOULD identify the source or basis of important claims.
- You MUST preserve uncertainty around causality, metrics, ownership, and outcomes.
- You MUST ask historical questions in a non-leading form.
- You MUST NOT offer a plausible remembered answer for the user to approve.
- You MAY present source-backed evidence candidates when retrieval or an artifact supplies them, but you MUST distinguish those candidates from the user's memory.

When historical evidence may continue an existing Experience, use bounded
related-entry discovery and load `references/experience-review.md` before
grouping it. Do not merge or associate entries automatically; leave them
unassigned when the relationship is uncertain.

For an explicit request to mine existing history, request one bounded
`experience mine` batch at a time. Review its anchors and related candidates
using the Experience-review reference, hydrate only promising evidence, obtain
explicit approval before using `experience associate`, and continue with the
returned cursor. Do not exhaust the corpus into one model context or treat the
batch as automatic clustering.

### 3. Reconstruct the Evidence Shape

Use the existing evidence dimensions as a reconstruction map, not a completeness checklist. Capture context, observations, significance, contribution, reasoning, evidence, alternatives and trade-offs, decisions and actions, expectations, outcomes, learning, and open questions only as supported. Prioritize gaps that materially affect the coherence or evidentiary value of the reconstructed experience.

**Constraints:**

- You MUST preserve the user’s actual contribution without inflating it.
- You MUST NOT convert a later outcome into a fact known at the time.
- You SHOULD attach artifacts or related-entry references only when the user or configured tool provides stable references.
- You MUST NOT continue probing only to fill every evidence section.

### 4. Reflection Boundary

When the later outcome or hindsight materially changed the user's belief, you MAY reflect on what changed and what the user would repeat or change now. Keep this reflection explicitly separate from what was known or believed at the time.

### 5. Confirm Scope and Commit as Reconstructed

Summarize the reconstructed experience, its uncertainty, and any missing
evidence. Ask the user to correct it before producing the CommitDraft.

**Constraints:**

- You MUST keep the final occurrence historical and the provenance reconstructed.
- You MUST NOT mix unrelated current work into this entry.
- You MUST use the configured CommitDraft shape; the application owns IDs, timestamps, revisions, and persistence.

## Examples

### Example Input

`Help me reconstruct the incident review from around spring 2024.`

### Example Response

`Let's keep this to that incident review. Start with whatever you remember most clearly from the time—what was happening, what you believed, or what you did. We can structure it after the reliable pieces emerge.`

## Troubleshooting

### The Date Is Uncertain

Keep the best-supported approximate occurrence and its precision. Never choose a
specific day merely because the schema allows one.

### The User Starts Discussing Current Work

Name the boundary and offer to commit the historical reconstruction first or
open a separate contemporaneous session for the current work.
