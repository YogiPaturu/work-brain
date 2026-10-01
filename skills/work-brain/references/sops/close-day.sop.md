WORK-BRAIN-SOP-CLOSE-DAY v2

# Work Brain Close Day

## Overview

Optionally help the user reflect at the end of a day. Close-day is a gap check
and planning aid, not the source of truth for the day: normal sessions must
already have preserved their raw turns and committed evidence.

## Parameters

- **user_message** (required): The end-of-day request or reflection.
- **current_state** (required): Compact active state from the application.
- **recent_work** (required): Bounded work committed for the current local day.
- **local_date** (optional): The application’s local date.
- **tomorrow_constraints** (optional): Known commitments or limits for the next day.

**Constraints for parameter acquisition:**

- The application MUST provide current state and bounded recent work when available.
- The agent MUST treat close-day as optional for journal correctness.
- The agent MUST NOT reconstruct the entire day from memory or claim exhaustive coverage.

## Steps

### 1. Review Today’s Compact Record

Read current state and today’s recent work. Identify outcomes, unfinished loops,
commitments, decisions, and items that may need a next action.

**Constraints:**

- You MUST distinguish recorded work from the user’s new reflection.
- You SHOULD say when the supplied record is incomplete or unavailable.
- You MUST NOT infer work that is not supported by the record or the user’s words.

### 2. Check for Gaps and Carryovers

Ask a small number of focused questions about missing outcomes, unresolved
commitments, blockers, and tomorrow’s likely first action.

**Constraints:**

- You MUST avoid a full-day interrogation.
- You SHOULD prioritise items with a clear consequence or next action.
- You MUST respect `skip`, `enough`, or an equivalent stop signal.

### 3. Confirm Tomorrow’s Next Actions

Summarize what is complete, what remains open, and the next actions the user
chooses for tomorrow. Keep tentative intentions visibly tentative.

**Constraints:**

- You MUST let the user accept, edit, or reject each proposed carryover.
- You MUST NOT silently create deadlines, commitments, or assignments.
- You SHOULD leave the user with a concise handoff they can use at open-day.

### 4. Commit Only Discussed Evidence

If this conversation contains durable new evidence, produce the configured
CommitDraft; otherwise finish without manufacturing a journal entry.

**Constraints:**

- You MUST commit only what the user actually discussed, explicitly stated, or
  explicitly confirmed.
- You MUST NOT duplicate an earlier session merely to make close-day appear complete.
- The application MUST own persistence and journal projection.

## Examples

### Example Input

`Close my day; what am I carrying forward?`

### Example Response

`Today’s record shows the import decision is open and the schema review is waiting. Is the next action tomorrow to follow up on the review, or should that wait until the decision is made?`

## Troubleshooting

### No Close-Day Session Is Needed

Say that the day’s existing sessions already remain valid and offer a short
summary only if the user wants one.
