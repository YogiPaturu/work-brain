WORK-BRAIN-SOP-OPEN-DAY v3

# Work Brain Open Day

## Overview

Orient the user to current work using compact state and recent committed work.
This remains a convenient start-of-day view, not the product’s canonical unit.
It helps the user choose focus; it does not silently create a plan or claim
that yesterday’s work is complete.

## Parameters

- **user_message** (required): The start-of-day request or stated intention.
- **current_state** (required): Compact active state from the application.
- **recent_work** (required): Bounded recent committed work.
- **session_status** (required): Read-only lifecycle status for active and
  recoverable capture sessions.
- **rollover_sessions** (optional): Sessions older than one full intervening
  calendar day whose capture boundaries were automatically closed.
- **local_date** (optional): The application’s local date for the session.
- **user_constraints** (optional): Time, energy, meetings, or other constraints supplied by the user.

**Constraints for parameter acquisition:**

- The application MUST provide `current_state`, `recent_work`, and
  `session_status` when starting this workflow.
- The agent MUST say when either source is missing or stale.
- The agent MUST let the user choose or revise priorities.

### Conversation profile

Use the shared conversational moves minimally:

- **Explore:** light; accept the user's stated constraints or focus.
- **Probe:** only to choose focus or resolve one material constraint.
- **Challenge:** normally off.
- **Resolve:** identify today's focus and an observable first action.
- **Reflect:** off.

Open-day is orientation, not a morning interview.

## Steps

### 1. Read the Compact Working Set

Review lifecycle status, current state, and recent work before broader
historical retrieval. Group items into carryovers, waiting items, commitments,
and possible priorities. Clearly distinguish no committed entries, recoverable
raw sessions, active capture, and closed/no-new-evidence sessions.

**Constraints:**

- You MUST prefer the supplied compact sources over an unbounded history dump.
- You SHOULD identify dependencies and stale items without declaring them resolved.
- You MUST NOT infer that an item is complete merely because it is absent from recent work.
- If rollover sessions are present, read their bounded turns, create and publish
  a CommitDraft automatically when they contain meaningful evidence, and close
  them as `no_new_evidence` when they do not. Do not ask the user to say
  “save” for this recovery step.
- Rollover recovery MUST use the session selected by the application. Do not
  create a fresh session and copy a summary into it. Preserve the rolled-over
  raw turns and use their exact sequences as CommitDraft provenance.
- A session exactly one calendar day old is a midnight edge case and MUST remain
  recoverable unless the host explicitly closed it. Sessions more than one day
  old may be rolled over only when their host mapping is inactive/recoverable;
  never silently close an active same-day session.

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
- You MUST NOT deepen the conversation into historical evidence capture merely because a surfaced item could become a useful Experience or interview story.
- Beginning this workflow is also a workflow boundary: any prior recoverable
  session selected for rollover is committed or explicitly closed before the
  new day’s focus is presented.
- If a commit fails, distinguish a provenance problem from missing evidence;
  report the recoverable session and defer it rather than manufacturing turns
  or merging it into an older entry.

Rely on the runtime-provided lifecycle banner when present; do not repeat it in
the model response. Use the application’s `session status` fields rather than
inferring state from whether `work recent` is empty. If no runtime lifecycle
information was supplied, the agent MAY present the compact capture and commit
state from the verified application status. In either case, explain an
exceptional, ambiguous, or decision-relevant condition concisely before
continuing. The verified state should distinguish whether capture is active,
whether raw turns are recoverable, whether the session is imported, and whether
a structured entry exists.

For example:

```text
Work Brain
Capture: INACTIVE — this host conversation is not being captured.
Last session: recoverable raw, 5 turns; last captured at 13:03.
Commit: no entry.
Action: say “capture this” to resume.
```

When capture is active, show the Work Brain session ID, turn count, and last
captured time. When a commit has failed, say that raw turns are safe and the
structured commit is pending. Never describe an empty recent-work result as
proof that no raw session exists.

## Examples

### Example Input

`Help me start the day.`

### Example Response

`I see the import decision, the waiting schema review, and yesterday’s unfinished test. Which should be today’s primary focus?`

## Troubleshooting

### State Is Empty or Stale

Tell the user what is unavailable, ask for the current focus directly, and avoid
presenting an empty state as proof that there is no work.
