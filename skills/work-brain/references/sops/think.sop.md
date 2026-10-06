WORK-BRAIN-SOP-THINK v2

# Work Brain Think

## Overview

Help the user reason through one coherent professional problem, decision, or
belief. The goal is clearer judgment and a durable record of the reasoning, not
debate for its own sake. When the conversation clearly continues or creates a
long-lived professional Experience, the host may associate the resulting entry;
classification remains optional and must not interrupt useful reasoning.

## Parameters

- **user_message** (required): The current problem, decision, or belief under examination.
- **current_session_context** (optional): Relevant turns from the active session.
- **retrieved_evidence** (optional): Bounded evidence returned by the configured retrieval adapter.
- **domain_probes** (optional): Relevant domain-specific prompts.
- **desired_decision** (optional): A decision, recommendation, or next experiment the user wants to reach.

**Constraints for parameter acquisition:**

- The agent MUST ask for the missing decision or problem boundary when it cannot identify one.
- The agent MAY use retrieval when it could change the reasoning, but MUST continue transparently if the adapter is unavailable.
- The agent MUST NOT invent evidence to make an argument stronger.

## Steps

### 1. Frame the Problem

State the problem in the user’s terms and identify the decision, belief, or
trade-off being examined. Distinguish a request for analysis from a request to
make a decision on the user’s behalf.

**Constraints:**

- You MUST confirm the target when multiple decisions are present.
- You SHOULD define what a useful outcome would look like.
- You MUST NOT silently substitute a different problem because it is easier to analyze.

### 2. Gather Decision-Relevant Evidence

Ask about observations, constraints, current evidence, alternatives, prior
attempts, failure modes, reversibility, and the signal that would change the
user’s mind. Use bounded evidence retrieval when relevant.

**Constraints:**

- You MUST separate facts, assumptions, interpretations, and unknowns.
- You SHOULD retrieve and hydrate only evidence that bears on the decision.
- You MUST NOT treat a missing retrieval result as proof that no evidence exists.
- You MUST NOT be contrarian for its own sake; challenge a claim only when it could change the decision.

When the current work may continue a prior Experience, use the bounded related
entry operation and load `references/experience-review.md` for grouping review.
Candidate discovery is not an automatic association; leave the evidence
unassigned when the causal or goal continuity is uncertain.

### 3. Compare Options and Trade-offs

Present the meaningful alternatives and their consequences, including the cost
of waiting or taking no action. Make uncertainty and reversibility explicit.

**Constraints:**

- You SHOULD preserve the user’s own priorities and constraints.
- You MUST identify material downside risks and failure modes.
- You MAY recommend a reversible experiment when a full decision is premature.
- You MUST NOT claim certainty that the evidence does not support.

### 4. Converge on a Decision or Next Experiment

Summarize the current conclusion, expected signal, next concrete action, owner,
and unresolved questions. Record meaningful changes in belief rather than only
the final recommendation.

**Constraints:**

- You MUST let the user accept, revise, defer, or reject the conclusion.
- You SHOULD state what observation would cause the decision to be revisited.
- You MUST NOT create a commitment or change work state without the user’s explicit confirmation or statement.

## Examples

### Example Input

`Should I spend this week improving reliability or adding the next integration?`

### Example Response

`The decision is reliability work versus the integration. What recent failure or customer signal would make reliability the clear priority?`

## Troubleshooting

### The Discussion Becomes Abstract

Ask for one concrete recent example, observed signal, or decision constraint,
then return to the stated problem.

### No Decision Is Ready

Capture the uncertainty, define the next reversible experiment or evidence to
collect, and leave the decision explicitly open.
