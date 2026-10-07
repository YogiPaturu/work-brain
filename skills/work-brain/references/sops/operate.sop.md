WORK-BRAIN-SOP-OPERATE v2

# Work Brain Operate

## Overview

Help the user recover and update current work state. Keep the interaction
action-oriented: identify the relevant open loop, clarify its state, and leave
the user with a concrete next action or an explicit blocker.

## Parameters

- **user_message** (required): The request to recover, inspect, or update work state.
- **current_state** (optional): Compact state supplied by the application.
- **recent_work** (optional): A bounded list of recent committed work.
- **retrieved_evidence** (optional): Evidence relevant to the active task.
- **source_turns** (optional): Turn references supporting a proposed state change.

**Constraints for parameter acquisition:**

- The agent MUST read compact current state before requesting broad historical search.
- The application MUST own state IDs, timestamps, revisions, and persistence.
- The agent MUST ask for missing ownership or status rather than guessing.

## Steps

### 1. Recover the Working Set

Read current state and recent work, then identify active tasks, waiting items,
commitments, blockers, and next actions relevant to the user’s request.

**Constraints:**

- You MUST prefer compact state and recent work over an unbounded history dump.
- You SHOULD distinguish active, waiting, blocked, completed, and unknown states.
- You MUST say when state data is stale, missing, or unavailable.

### 2. Identify the State Change

Ask only the questions needed to clarify the target item, owner, status,
dependency, due expectation, or next concrete action. Keep unrelated items out
of the session.

**Constraints:**

- You MUST not silently reprioritize the user’s work.
- You SHOULD propose a concise interpretation only when the state is inferred.
- An explicit user update such as “I finished X” or “I am waiting on Y” is
  sufficient stated support and MUST NOT trigger a redundant confirmation.
- You MUST NOT turn an agent suggestion into a durable state mutation without
  explicit user support; the user's direct statement is already support.

### 3. Make the Next Action Concrete

For the selected item, state the next action, expected signal or completion
condition, and blocker if one exists. If several items compete, present the
smallest useful choice set and let the user choose.

**Constraints:**

- You MUST identify an owner when an action is being committed.
- You SHOULD make the next action small enough to start without another planning session.
- You MUST preserve unresolved ambiguity as an open question rather than hiding it.

### 4. Record Supported Changes

Propose the state changes with source-turn references. The application resolves
stable IDs and publishes validated mutations after the user has supplied or
confirmed the facts.

**Constraints:**

- You MUST attach source turns to each proposed change when the contract requires them.
- You MUST NOT invent task IDs, timestamps, or completion evidence.
- You MUST keep the raw conversation as the source even if a state mutation is later corrected.

When the selected task clearly continues prior work, first resolve the exact
workspace/project context and use a small, context-scoped evidence search before
commit. Reuse a clearly matching existing Experience identity from relevant
EvidenceCards in the CommitDraft. This check is optional: routine state updates
do not require Experience retrieval, and unclear or degraded results stay
unassigned. See `references/experience-review.md` for the decision rules.

## Examples

### Example Input

`What am I waiting on for the import project?`

### Example Response

`The current state shows a waiting item for the schema decision. Is the next action to ask the data team for the decision, or is another dependency now blocking it?`

## Troubleshooting

### State Does Not Match the User

Treat the user’s correction as new source evidence, explain the proposed
correction, and let the application record an amendment or new state revision.
