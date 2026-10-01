WORK-BRAIN-PROBE-ARCHITECTURE v1

# Architecture Probe

## Notice

System boundary, ownership, coupling, data flow, failure isolation, operational
cost, migration risk, and reversibility.

## Conditional probes

- **Boundary choice:** What responsibility belongs here, and what dependency is
  being deliberately introduced?
- **Trade-off:** Which alternative was credible, and what constraint ruled it
  out?
- **Migration:** What is the safe intermediate state, rollback boundary, and
  evidence that the new boundary works?

## Constraint

Use this only when architecture is the actual decision, not because a technical
word appeared in the conversation.
