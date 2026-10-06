WORK-BRAIN-SOP-BACKFILL v2

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

## Steps

### 1. Bound the Historical Experience

Identify the one experience being reconstructed, its approximate occurrence, the
user’s role at the time, and the precision that can honestly be supported.

**Constraints:**

- You MUST ask for an approximate time or explicitly record that the time is unknown or approximate.
- You MUST NOT invent a date, role, project, or sequence of events.
- You MUST split an unrelated live event or a second historical experience into another session.

### 2. Separate Time-of-Event Knowledge from Hindsight

Explore what the user observed, believed, decided, and did then, followed by
what later evidence or hindsight changed. Use related evidence only to prompt
recall and check duplication, not to overwrite the user’s account silently.

**Constraints:**

- You MUST distinguish contemporaneous belief from later interpretation.
- You SHOULD identify the source or basis of important claims.
- You MUST preserve uncertainty around causality, metrics, ownership, and outcomes.

When historical evidence may continue an existing Experience, use bounded
related-entry discovery and load `references/experience-review.md` before
grouping it. Do not merge or associate entries automatically; leave them
unassigned when the relationship is uncertain.

### 3. Reconstruct the Evidence Shape

Capture context, observations, significance, contribution, reasoning, evidence,
alternatives and trade-offs, decisions and actions, expectations, outcomes,
learning, and open questions as supported. Leave unsupported sections empty or
explicitly uncertain rather than filling them with plausible detail.

**Constraints:**

- You MUST preserve the user’s actual contribution without inflating it.
- You MUST NOT convert a later outcome into a fact known at the time.
- You SHOULD attach artifacts or related-entry references only when the user or configured tool provides stable references.

### 4. Confirm Scope and Commit as Reconstructed

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

`Let’s keep this to one incident review. What do you remember being known at the time, and which parts are clearer only in hindsight?`

## Troubleshooting

### The Date Is Uncertain

Keep the best-supported approximate occurrence and its precision. Never choose a
specific day merely because the schema allows one.

### The User Starts Discussing Current Work

Name the boundary and offer to commit the historical reconstruction first or
open a separate contemporaneous session for the current work.
