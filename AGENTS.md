# Work Brain repository guidance

## Scope

This repository contains the public Work Brain application and its installable
Skill/SOP resources. Private vaults, user profiles, hooks, SQLite files, and
captured conversations do not belong in the repository.

## Before changing code

- Treat `skills/work-brain/SKILL.md`, schemas, SOPs, and `src/work_brain/` as one
  contract. Keep public names and persisted names consistent.
- Use the documented CLI for private-vault reads and mutations. Never inspect or
  edit a private vault's SQLite database or source JSON directly from a task.
- Preserve immutable evidence and rebuildable projections. Schema migrations
  must be explicit, idempotent, and covered by tests.

## Verification

Run:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -q
PYTHONPATH=src python3 -m compileall -q src examples
git diff --check
```

For packaging changes, build a wheel and verify that all Skill/SOP/schema
resources required by `SkillLoader` are present in the artifact.

## Editing

Use `apply_patch` for focused edits. Do not commit private vault paths,
profiles, generated databases, model caches, or host settings.
