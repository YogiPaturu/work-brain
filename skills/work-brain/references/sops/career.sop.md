WORK-BRAIN-SOP-CAREER v2

# Work Brain Career Practice

## Overview

Practise one interview question or one coherent career story using the user’s
own professional evidence. Keep question-bank lookup, evidence retrieval,
pagination, and durable candidate marks behind their configured application
interfaces; the agent must not invent those LLD4 contracts.

## Parameters

- **user_message** (required): The interview-practice request or story the user wants to rehearse.
- **interview_question** (optional): An explicit question supplied by the user.
- **practice_goal** (optional): The target such as concision, evidence, structure, or delivery.
- **retrieved_candidates** (optional): A bounded set of plausible evidence candidates returned by the configured career tools.
- **current_session_context** (optional): Relevant turns from the active practice session.

**Constraints for parameter acquisition:**

- The agent MUST use the explicit question when one is supplied.
- If no question is supplied and the configured question-bank interface is unavailable, the agent MUST ask the user for a question or practice goal rather than pretending to query a bank.
- The agent MUST leave story and angle selection to the user.
- The agent MUST NOT load or expose an entire private question bank or evidence corpus.

## Steps

### 1. Define the Practice Target

Confirm the question, role or audience if relevant, and the skill the user wants
to practise. Bound the session to one question or one coherent story.

**Constraints:**

- You MUST distinguish question practice from general career advice.
- You SHOULD ask for the desired answer length or format when it affects practice.
- You MUST start a new bounded session when the user switches to an unrelated story.

### 2. Gather Plausible Evidence

Use the configured question-bank or evidence interfaces when available. Retrieve
a bounded set of plausible experiences and hydrate only the candidates needed
for comparison or practice.

**Constraints:**

- You MUST preserve evidence provenance and uncertainty.
- You SHOULD present multiple plausible candidates when more than one fits.
- You MUST NOT select a “best” story for the user or hide later candidates behind an unexplained cap.
- You MUST treat unavailable retrieval as an explicit limitation, not as evidence that no story exists.

### 3. Practise the Answer

Help the user produce and refine a concise answer covering the relevant context,
action, reasoning, evidence, outcome, and learning. Ask focused follow-ups for
missing or weakly supported parts.

**Constraints:**

- You MUST preserve the user’s voice and actual experience.
- You MUST NOT invent metrics, ownership, outcomes, or polished claims that the evidence does not support.
- You SHOULD give feedback tied to the stated practice goal.
- You MAY offer a structure or rewrite, but the user remains the final author.

### 4. Record the User’s Selection

Ask the user which story, angle, wording, or candidate they prefer. If the
configured career-mark interface is available, propose the explicit mark for
user confirmation; otherwise leave the preference in the conversation.

**Constraints:**

- You MUST obtain explicit user selection before creating a durable candidate mark.
- You MUST NOT rewrite underlying evidence merely because a story was selected.
- You SHOULD record why the user selected an angle when they provide that reason.

## Examples

### Example Input

`Practise a “tell me about a difficult decision” answer from my engineering work.`

### Example Response

`I can help with that. Do you want to optimise for a 90-second answer, clearer trade-off reasoning, or stronger evidence of impact?`

## Troubleshooting

### No Candidate Clearly Fits

Say whether the gap is missing evidence, an overly narrow question, or
unavailable retrieval. Ask the user whether to broaden the search, practise a
different story, or backfill the missing experience.
