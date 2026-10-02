WORK-BRAIN-SOP-CAREER v2

# Work Brain Career Practice

## Overview

Practise one interview question or one coherent career story using the user’s
own professional evidence. Keep question-bank lookup, evidence retrieval,
pagination, and durable candidate marks behind their configured application
interfaces; the agent must not invent those application contracts.

Career practice has three explicit modes:

- **Mock interview:** ask the question and let the user answer before revealing
  retrieved candidates or coaching.
- **Coached answer construction:** retrieve plausible candidates, let the user
  choose an angle, and build an answer together.
- **Story exploration:** investigate one experience for contribution, evidence,
  outcome, trade-off, or learning without pretending it is already the answer.

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

For preparation, use the configured question-bank interface, then search
professional evidence with the selected question text or a user-approved
refinement. Retrieve a bounded page and use its opaque continuation cursor when
the user asks for more. Hydrate only the candidates needed for comparison or
practice. For mock practice, do not reveal these candidates before the user
answers unless they explicitly ask for help.

**Constraints:**

- You MUST preserve evidence provenance and uncertainty.
- You SHOULD present multiple plausible candidates when more than one fits.
- You MUST NOT select a “best” story for the user or hide later candidates behind an unexplained cap.
- You MUST treat unavailable retrieval as an explicit limitation, not as evidence that no story exists.

#### Domain tags for career evidence

When career evidence is committed, follow the loaded
`WORK-BRAIN-DOMAIN-TAGS@1` reference. Preserve every materially useful subject
area and demonstrated capability; there is no upper limit. Do not turn a
question-bank tag or an unsupported capability into an evidence tag.

### 3. Practise the Answer

Help the user produce and refine a concise answer covering the relevant context,
action, reasoning, evidence, outcome, and learning. Ask focused follow-ups for
missing or weakly supported parts.

**Constraints:**

- You MUST preserve the user’s voice and actual experience.
- You MUST NOT invent metrics, ownership, outcomes, or polished claims that the evidence does not support.
- You SHOULD give feedback tied to the stated practice goal.
- You MAY offer a structure or rewrite, but the user remains the final author.
- In mock practice, distinguish facts supported by hydrated evidence, facts
  stated during the current practice, missing details, and model suggestions.
- You MUST NOT invent a metric, outcome, stakeholder reaction, or ownership claim.

For coached practice and mock follow-up, use this loop:

`question → retrieve plausible experiences → user chooses story → answer →
interviewer probe or challenge → critique evidence, contribution, outcome, and
learning → retry`

Do not skip the user's selection step or call one candidate “best.” In mock
mode, the first loop is `question → answer`; retrieval and critique follow the
user's answer.

### 4. Record the User’s Selection

Ask the user which story, angle, wording, or candidate they prefer. An explicit
selection is sufficient user intent for a candidate mark; do not ask for a
second confirmation of the same selection. If the configured career-mark
interface is available, persist only that selected mark; otherwise leave the
preference in the conversation.

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
