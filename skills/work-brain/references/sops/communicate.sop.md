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
- **retrieved_evidence** (optional): Bounded relevant evidence from the private vault.

**Constraints for parameter acquisition:**

- The agent MUST clarify missing `audience` or `purpose` before drafting when either would materially change the message.
- The agent MUST treat private context as non-shareable unless the user explicitly authorizes its use in this draft.
- The agent MUST produce a draft for review; no external-send capability is implied.

## Steps

### 1. Define the Communication Job

Confirm the audience, purpose, desired action, tone, format, deadline, and
constraints. Identify whether the user wants a new draft, a rewrite, or a
critique.

**Constraints:**

- You MUST ask one concise clarification when a missing parameter changes the message materially.
- You SHOULD keep the message’s purpose to one primary outcome.
- You MUST NOT infer authorization to disclose sensitive or private details.

### 2. Select Shareable Evidence

Retrieve only relevant evidence when needed. Separate user-stated facts,
source-supported facts, private speculation, sensitive details, and model
inference before using any detail in the draft.

**Constraints:**

- You MUST include only facts appropriate for the named audience and purpose.
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
summarize the approved facts separately from the draft and request confirmation
before committing it.

**Constraints:**

- You MUST NOT treat an unapproved draft as a confirmed user statement.
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
