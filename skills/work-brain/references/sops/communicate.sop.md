WORK-BRAIN-SOP-COMMUNICATE v2

# Work Brain Communicate

## Overview

Draft a clear, audience-appropriate message from private professional context.
The workflow protects the boundary between what the user knows privately and
what the intended audience should receive.

## Parameters

- **user_message** (required): The communication request or draft objective.
- **audience** (required): The intended recipient or audience.
- **purpose** (required): The outcome the message should achieve.
- **desired_action** (optional): The action or response requested from the audience.
- **tone** (optional): Desired tone, with a neutral professional tone as the default.
- **share_constraints** (optional): Facts, details, or topics that must or must not be shared.
- **profile_id** (optional): A user-owned communication profile that supplies the channel, audience, scope, and format defaults.
- **retrieved_evidence** (optional): Bounded relevant evidence from the private vault.
- **evidence_scope** (optional): A composable scope such as time range, workspace,
  project, Experience, domain tags, or current state.

**Constraints for parameter acquisition:**

- The agent MUST clarify missing `audience` or `purpose` before drafting when either would materially change the message.
- A request that names an audience and asks for a draft from the discussed
  context authorizes use of relevant private context for that audience and
  purpose. This does not authorize unrelated facts, external sending, or reuse
  outside the requested draft.
- The agent MUST produce a draft for review; no external-send capability is implied.
- When `profile_id` is supplied, the agent SHOULD load the validated profile through
  the configured profile tool and treat it as user preference, not as permission
  to weaken evidence or privacy rules.
- The active profile's `rendering` contract is channel-specific. Workspace and
  project scope are separate: workspace identifies the broad working context,
  while project identifies the specific effort. The agent MUST
  preserve plain-text compactness for WhatsApp profiles and may use structured
  Markdown only when the selected profile explicitly permits it.
- For a profile-scoped draft, the agent MUST use the profile-scoped evidence
  search tool. It MUST NOT broaden the entity, domain, or time window by issuing
  an unrestricted search for the same draft.

## Steps

### 1. Define the Communication Job

Confirm the audience, purpose, desired action, tone, format, deadline, and
constraints. If a profile is named, use its values as defaults and confirm only
the material gaps or conflicts. Identify whether the user wants a new draft, a
rewrite, or a critique.

**Constraints:**

- You MUST ask one concise clarification when a missing parameter changes the message materially.
- You SHOULD keep the message’s purpose to one primary outcome.
- You MUST NOT infer authorization to disclose unrelated or sensitive details
  merely because they exist in the vault. Keep authorization scoped to the
  named audience, purpose, and requested format.

### 2. Select Shareable Evidence

Retrieve only relevant evidence when needed. If a profile is active, retrieve
through its exact scope first. Separate user-stated facts,
source-supported facts, private speculation, sensitive details, and model
inference before using any detail in the draft.

**Constraints:**

- You MUST include only facts appropriate for the named audience and purpose.
- Daily and weekly updates are time-filtered views, not journal-owned records.
  Project and Experience updates may span many dates and must use the same
  composable evidence selection capability.
- You MUST label uncertainty or omit it rather than turning inference into fact.
- You MUST NOT expose private vault paths, raw search mechanics, or unrelated personal context.
- You SHOULD ask the user to approve an ambiguous sensitive detail before including it.

### 3. Draft for Review

Produce the message in the requested format, followed by a short note of any
assumptions, omitted details, or choices that need review.

**Constraints:**

- You MUST make the draft easy to copy and edit.
- You SHOULD offer one concise alternative only when tone or positioning is genuinely ambiguous.
- You MUST NOT send, schedule, post, or invoke an external system.

### 4. Confirm Before Durable Capture

If the user wants the communication decision or reusable context captured,
summarize the approved facts separately from the draft. The user's explicit
facts do not need a second confirmation; only an agent-inferred fact,
interpretation, or durable mutation needs confirmation before committing it.

**Constraints:**

- You MUST NOT treat model wording in an unapproved draft as a confirmed user
  statement. Preserve the distinction between explicit source facts and drafted
  shareable language.
- You SHOULD preserve the distinction between the private source context and the shareable wording.
- You MUST use the configured CommitDraft contract for any durable session commit.

## Examples

### Example Input

`Write a short update to my manager explaining why the launch moved.`

### Example Clarification

`What outcome do you want from your manager: awareness, approval for the new date, or help removing a blocker?`

## Troubleshooting

### The Draft Contains Sensitive Detail

Remove or generalize the detail, explain that it was excluded, and ask the user
whether an explicitly approved version is needed.
