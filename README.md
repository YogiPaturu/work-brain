# Work Brain

Work Brain is a local-first professional evidence system: a bounded CLI
conversation experience that helps a person think through work today while
preserving durable evidence for future context recovery, communication, and
career preparation.

The design is defined by the included HLD and four LLDs. The system is
single-user, privacy-first, hexagonal, and source-first: raw conversations and
explicit user corrections are durable source; journals, current state, SQLite,
FTS, vectors, and career views are rebuildable projections.

## What it is for

Work Brain has four projections over one professional-evidence corpus:

- Think: challenge assumptions, reason through alternatives, and preserve how
  beliefs changed.
- Operate: recover current work state, open loops, commitments, blockers, and
  next actions.
- Communicate: turn private context into concise audience-appropriate drafts
  without exposing the private vault.
- Career: filter interview questions, retrieve multiple plausible experiences,
  practice answers, and let the user choose the story or angle.

It is not a team project-management system, hosted SaaS, meeting transcription
service, CRM, or generic personal-life knowledge base.

## HLD and LLD implementation map

| Layer | Responsibility | This checkout |
|---|---|---|
| HLD | Product boundaries, privacy model, shared evidence model, local-first architecture | Design source included |
| LLD1 | Vault, raw turns, entry revisions, amendments, entities, artifacts, WorkState, journals, SQLite metadata, rebuilds, integrity checks | Implemented in `src/work_brain` |
| LLD2 | Skills/SOPs, session orchestration, model adapter port, probing, CommitDraft resolution, Think/Operate/Communicate workflows | Implemented in `src/work_brain`, `skills/work-brain`, and `tests/test_lld2.py` |
| LLD3 | FTS5, local embeddings, vector index, hybrid retrieval, pagination, hydration, index lifecycle | Contract documented; retrieval backend is not yet in the runnable baseline |
| LLD4 | Question-bank normalization/filtering, interview practice, human-led career retrieval, candidate marks | Contract documented; career projection is not yet in the runnable baseline |

This distinction is deliberate. The README describes the complete HLD target
and the LLD boundaries, while runnable commands below describe what is already
safe to use. LLD2–LLD4 must consume the LLD1 contracts; they must not create a
second evidence store.

## Quick start

The project has no runtime dependencies beyond Python 3.11+ and SQLite.

```bash
python3 -m venv .venv
.venv/bin/pip install -e .

export WORK_BRAIN_VAULT="$PWD/career-vault"
work-brain --vault "$WORK_BRAIN_VAULT" init
work-brain --vault "$WORK_BRAIN_VAULT" doctor
```

Run the tests directly from a checkout:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Optional voice interface: Yap

[Yap](https://github.com/latent-variable/Yap) is a useful conversational
front end for Work Brain on macOS. It gives your terminal-based LLM ears and a
voice: dictate into the active terminal, then select an answer and have Yap
read it back. Yap is optional and separate from Work Brain; Work Brain remains
responsible for durable turns, structured commits, and the private vault.

Install Yap with Homebrew:

```bash
# Install Homebrew first if it is not already installed: https://brew.sh
brew install --cask latent-variable/tap/yap
```

On first launch, open Yap's model settings and download its voice model, then
grant Microphone and Accessibility permissions when macOS asks. The default
shortcuts documented by Yap are `⌘⇧D` to dictate and `⌘⇧R` to read selected
text aloud. You can change them in Yap's settings.

A practical Work Brain loop is:

1. Start your CLI LLM in the terminal and give it the Work Brain Skill/SOP
   context described below.
2. Press Yap's dictate shortcut, speak your thought, and press it again to
   insert the text into the terminal prompt.
3. Let the LLM ask questions and answer them conversationally. Persist each
   visible user and assistant turn with `work-brain turn` before moving on.
4. When the bounded session is complete, have the LLM emit an LLD2
   `CommitDraft`, then publish it with `work-brain commit-draft`.
5. Select the useful part of the LLM response and use Yap's read shortcut when
   you want the terminal to brief you aloud.

Yap's audio and models remain on your Mac according to its project
documentation. Keep Work Brain's vault outside the public repository and do
not put provider credentials into prompts, turns, or the vault.

Create a publication-safe synthetic vault:

```bash
PYTHONPATH=src python3 examples/create_synthetic_vault.py \
  --vault /tmp/work-brain-synthetic
work-brain --vault /tmp/work-brain-synthetic doctor
```

## CLI commands

All commands require a private-vault path before the subcommand.

```bash
# Create or validate the vault structure.
work-brain --vault "$WORK_BRAIN_VAULT" init
work-brain --vault "$WORK_BRAIN_VAULT" doctor
work-brain --vault "$WORK_BRAIN_VAULT" rebuild

# Inspect the progressive Skill/SOP/probe set for a workflow.
work-brain --vault "$WORK_BRAIN_VAULT" skills \
  --workflow think --domain engineering

# Start a bounded session and note the printed session_id.
work-brain --vault "$WORK_BRAIN_VAULT" session-start \
  --mode think --domain engineering

# Persist each CLI-LLM/user turn immediately.
work-brain --vault "$WORK_BRAIN_VAULT" turn \
  --session-id <session-id> --role user --content "I am deciding whether to move this job async."
work-brain --vault "$WORK_BRAIN_VAULT" turn \
  --session-id <session-id> --role assistant --content "What problem would async processing solve?"

# Publish a validated, resolved LLD1 SessionEntry JSON payload.
work-brain --vault "$WORK_BRAIN_VAULT" commit \
  --session-id <session-id> --file resolved-entry.json

# Or validate and resolve an LLD2 model-produced CommitDraft.
work-brain --vault "$WORK_BRAIN_VAULT" commit-draft \
  --session-id <session-id> --workflow think --file commit-draft.json

# Inspect unfinished sessions after an interrupted model/process.
work-brain --vault "$WORK_BRAIN_VAULT" recoverable
```

`commit` accepts the resolved LLD1 `SessionEntry` shape. `commit-draft` accepts
the strict LLD2 model shape and performs validation, stable-ID resolution,
source-reference checks, and source-first publication for you.

## Connecting a CLI LLM

Work Brain does not hard-code a model provider or require a background agent.
Connect any CLI LLM by placing a small adapter between the LLM process and the
vault:

```text
CLI LLM / voice-to-text
          |
          v
thin Work Brain adapter
  - starts/resumes a session
  - appends every user/assistant turn
  - assembles bounded context
  - asks the model for a CommitDraft in the active context
  - validates and resolves the draft through `CommitResolver`
          |
          v
Vault.commit_entry() or `work-brain commit-draft`
```

The adapter should follow this lifecycle:

1. Start one bounded session and persist its `session_id` and `entry_id`.
2. Append every accepted user and assistant message immediately. Do not wait
   for end-of-day closure.
3. Give the model only the active conversation, compact current state, the
   relevant SOP/probe guidance, and bounded retrieved evidence.
4. Ask the model for an LLD2 `CommitDraft`, preserving statement basis and
   source-turn references. A normal commit should use the active model context;
   it should not reread the entire historical vault.
5. Resolve the draft into the LLD1 `SessionEntry` contract, including UUIDv7
   identities, revision metadata, provenance, entity/artifact references, and
   state mutations.
6. Publish through the Work Brain persistence port or the `commit-draft` command.
   Source publication happens before journals, state, SQLite, FTS, or vector
   updates.

For a provider-specific integration, replace `your-cli-llm` with the command
that accepts a prompt on stdin and returns the LLD2 CommitDraft JSON on stdout:

```bash
your-cli-llm --json < bounded-commit-prompt.json > commit-draft.json
work-brain --vault "$WORK_BRAIN_VAULT" commit-draft \
  --session-id "$SESSION_ID" --workflow think --file commit-draft.json
```

The repository intentionally does not assume a particular CLI LLM, API key
scheme, prompt format, or voice-to-text utility. Keep provider credentials out
of the vault, transcripts, artifact locators, and SQLite.

## Durable data model

The private vault is the trust boundary and uses this topology:

```text
career-vault/
  sessions/YYYY/MM/DD/<session-id>/
    session.json              # mutable session metadata snapshot
    turns.jsonl                # append-only verbatim conversation source
    entries/0001.json          # immutable structured revision history
  amendments/YYYY/MM/DD/<amendment-id>.json
  catalog/entities/<entity-id>.json
  catalog/artifacts/<artifact-id>.json
  journal/YYYY/MM/YYYY-MM-DD.md       # generated daily projection
  state/current.json                   # generated WorkState projection
  career/marks.jsonl                   # LLD4-owned preference metadata
  questions/                            # private question banks
  index/work-brain.sqlite              # rebuildable metadata/index database
```

Important invariants:

- Turns are appended and flushed before the next conversational step is
  acknowledged. Only an incomplete trailing JSONL record may be recovered;
  malformed middle data fails visibly.
- Each session has one stable `entry_id`. Re-extraction and correction create
  immutable revisions rather than rewriting history.
- `contemporaneous` and `reconstructed` evidence remain distinguishable.
- User amendments preserve the original transcript and create a
  `user_correction` revision when applied.
- WorkState and journals can be regenerated from source files.
- SQLite is never the sole copy of professional evidence.
- A vault has one active writer. A second writer fails clearly.

## Repository layout

```text
src/work_brain/              LLD1 domain/persistence plus LLD2 runtime services
skills/work-brain/           public Skill, SOPs, and domain probes
migrations/                  persistence-owned SQLite migrations
examples/                    synthetic vault and integration examples
tests/                       LLD1 durability and LLD2 runtime/contract tests
work-brain-hld-v2.md         high-level architecture
work-brain-lld-01-*.md       vault and persistence contract
work-brain-lld-02-*.md       agent runtime and SOP contract
work-brain-lld-03-*.md       retrieval and index contract
work-brain-lld-04-*.md       interview and career contract
```

Private vaults should live outside the repository or under an ignored path.
The public tree must contain only reusable code, documentation, migrations,
tests, and synthetic/publication-safe fixtures.

## Recovery and maintenance

If a model commit fails, the raw transcript remains available for retry. If a
journal, WorkState, SQLite, or future retrieval index update fails after source
publication, run:

```bash
work-brain --vault "$WORK_BRAIN_VAULT" rebuild
work-brain --vault "$WORK_BRAIN_VAULT" doctor
```

`doctor` reports malformed source, broken references, stale projections,
missing SQLite rows, source-hash mismatches, and unsafe private-vault Git
placement. It does not silently rewrite raw evidence.

## Design references

- [High-Level Design](work-brain-hld-v2.md)
- [LLD1: Core Domain, Vault, and Persistence](work-brain-lld-01-core-domain-vault-persistence-v2.md)
- [LLD2: Agent Runtime, Skills/SOPs, and Session Orchestration](work-brain-lld-02-agent-runtime-skills-session-orchestration-v2.md)
- [LLD3: Retrieval, FTS, Embeddings, and Index Lifecycle](work-brain-lld-03-retrieval-fts-embeddings-index-lifecycle-v2.md)
- [LLD4: Interview Practice and Career Retrieval](work-brain-lld-04-interview-practice-career-retrieval-v1.md)
