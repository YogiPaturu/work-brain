WORK-BRAIN-TOOLS v3

The host agent uses intent-level application operations only. In the
harness-hosted v1 path, these are executed as documented `work-brain` CLI
commands through the harness's existing shell capability:

- `get_current_state`
- `get_recent_work`
- `search_evidence`
- `hydrate_evidence`
- `search_questions`
- `get_question`
- `choose_question`
- `mark_interview_candidate` only after explicit user confirmation
- `unmark_interview_candidate` only after explicit user confirmation
- `list_interview_candidates`
- `commit-draft` through stdin or a bounded file during the committing phase

Tools return compact typed results and stable references. Work Brain never
exposes raw SQL, vector primitives, arbitrary vault filesystem mutation, or
internal persistence operations as part of its supported application
interface. Retrieval implementation belongs behind the application adapter
and LLD3 contract.

The host agent can read other files that its own permissions allow. A Skill is
not a security boundary; the documented CLI is the supported Work Brain
interface and the private vault remains local.

The CLI accepts structured arguments and emits deterministic JSON. A provider
may internally map a logical operation to a tool call, but that is host-agent
behavior rather than a Work Brain model/tool loop. Work Brain v1 does not make
a second LLM call behind the host.

For example, the host may execute:

```sh
work-brain state current
work-brain work recent --limit 5
work-brain evidence search --query "import reliability" --page-size 10
work-brain career questions search --tag-all conflict
work-brain career prepare --question-text "Tell me about a difficult decision"
work-brain career mock --question-text "Tell me about a difficult decision"
```

Structured CommitDraft input MAY be an object on stdin or a JSON file. The
application validates the request, applies the active workflow contract, and
returns a compact JSON result. Unknown, malformed, or failed calls become
stable structured errors; they MUST NOT mutate the vault. Tool payloads and
host shell details are not appended to the raw visible-turn transcript.

Career question lookup is deterministic and does not require a model call.
Question banks are separate from professional evidence. `prepare` may show a
bounded page of plausible EvidenceCards and an opaque continuation cursor;
`mock` asks the question first and does not reveal evidence suggestions before
the answer. The user chooses the story/angle. Candidate marks are private
preference events and require explicit confirmation; a model suggestion alone
must never persist one.

The existing `ToolRegistry` and bounded standalone model/tool loop remain
available for provider-free tests and future standalone mode. They are not a
production v1 dependency and do not define the harness-hosted architecture.
