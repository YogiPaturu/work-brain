WORK-BRAIN-SOP-OPEN-DAY v2

# Work Brain Open Day

## Overview

Orient the user to current work at the start of a day using compact state and
recent committed work. This workflow helps the user choose focus; it does not
silently create a plan or claim that yesterday’s work is complete.

## Parameters

- **user_message** (required): The start-of-day request or stated intention.
- **current_state** (required): Compact active state from the application.
- **recent_work** (required): Bounded recent committed work.
- **local_date** (optional): The application’s local date for the session.
- **user_constraints** (optional): Time, energy, meetings, or other constraints supplied by the user.

**Constraints for parameter acquisition:**

- The application MUST provide `current_state` and `recent_work` when starting this workflow.
- The agent MUST say when either source is missing or stale.
- The agent MUST let the user choose or revise priorities.

## Steps

### 1. Read the Compact Working Set

Review current state and recent work before broader historical retrieval. Group
items into carryovers, waiting items, commitments, and possible priorities.

**Constraints:**

- You MUST prefer the supplied compact sources over an unbounded history dump.
- You SHOULD identify dependencies and stale items without declaring them resolved.
- You MUST NOT infer that an item is complete merely because it is absent from recent work.

### 2. Surface Focus Options

Present a concise view of what could matter today, including the reason each
item is surfaced and any blocker or time constraint.

**Constraints:**

- You MUST distinguish facts from suggestions.
- You SHOULD present a small choice set rather than an exhaustive backlog.
- You MUST NOT silently reprioritize, create deadlines, or assign work to others.

### 3. Confirm the User’s Focus

Ask the user to choose, revise, defer, or reject the proposed focus. Convert the
choice into one or more concrete next actions once the user chooses or states
the intention directly; do not ask them to confirm the same explicit intention
twice.

**Constraints:**

- You MUST ask for confirmation before durable state mutation when the action is
  agent-inferred; an explicit user intention is sufficient support.
- You SHOULD make the selected next action observable and easy to start.
- You MUST preserve unresolved items as carryovers or open loops rather than hiding them.

## Examples

### Example Input

`Help me start the day.`

### Example Response

`I see the import decision, the waiting schema review, and yesterday’s unfinished test. Which should be today’s primary focus?`

## Troubleshooting

### State Is Empty or Stale

Tell the user what is unavailable, ask for the current focus directly, and avoid
presenting an empty state as proof that there is no work.
