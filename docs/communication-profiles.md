# Communication profiles

Communication profiles are user-owned preferences layered on top of the
generic `communicate` workflow. They are data, not new workflows and not
permissions to bypass Work Brain's evidence or privacy rules.

The supported document shape is:

```json
{
  "version": 1,
  "profiles": [
    {
      "id": "ranq_whatsapp",
      "label": "Ranq WhatsApp update",
      "workflow": "communicate",
      "channel": "WhatsApp",
      "audience": "non-technical co-founders",
      "purpose": "Explain progress on a named work item",
      "scope": {
        "workspaces": ["ranq"],
        "time_window": "work_item"
      },
      "tone": "plain-English and concise",
      "format": ["progress", "impact", "next step"],
      "rendering": {"markup": "plain_text", "layout": "compact", "max_length": 1200},
      "include": ["confirmed facts", "business impact"],
      "exclude": ["private speculation", "unapproved commitments"],
      "triggers": ["after_work_item"],
      "cadence": "on_demand",
      "delivery": {"mode": "draft_only"}
    }
  ]
}
```

Profiles are resolved in this order:

1. `--profiles PATH`;
2. `WORK_BRAIN_PROFILES`;
3. `communication_profiles` in the local Work Brain config;
4. `~/.config/work-brain/communication-profiles.json`.

Useful commands:

```bash
work-brain profiles list
work-brain profiles show ranq_whatsapp
work-brain profiles validate
work-brain config set-profiles "$HOME/.config/work-brain/communication-profiles.json"
```

The repository's Ranq example lives in `.work-brain-local/`, which is ignored
by Git. It is a local development profile and is not part of the distributable
package.

Profiles are channel contracts as well as audience preferences. WhatsApp can
use compact plain text, while Discord can use structured Markdown, headings,
bullets, and more deliberate spacing. The same profile system supports broad
Discord updates. The local example
includes `discord_progress`, an on-demand Markdown generator triggered when a
substantial work item closes. It is not a daily or weekly activity log, and it
does not require a Discord connection.

`delivery.mode` defaults to `draft_only`. A Discord profile may reference a
webhook through an environment-variable name, but the secret itself must stay
outside the profile file. Automatic sending is a separate host delivery step;
the communication workflow still produces a reviewable draft and never sends
as a side effect of retrieval.

## Post-close prompts

Profiles may opt into a post-close-day prompt with:

```json
"triggers": ["after_close_day"]
```

At close-day, Work Brain can offer profiles configured with
`triggers: ["after_close_day"]` as the next action. If several are configured,
the host should show a short selection rather than drafting all of them.
It does not send anything or silently create a communication draft. The user
selects the profile, then the host starts a new `communicate` session with that
profile and retrieves the bounded evidence for its scope. In the Python host
adapter this handoff is explicit:

```python
orchestrator.start(
    "Draft today's Ranq WhatsApp update.",
    workflow="communicate",
    profile_id="ranq_whatsapp",
)
```

The profile-scoped search applies `entities`, `workspaces`, `projects`, `experiences`, `domain_tags`, and the supported
`time_window` (`today`, `week_to_date`, or `work_item`) before lexical or
semantic retrieval. A `work_item` profile uses the named work item as the
retrieval anchor and deliberately does not impose a calendar-day limit, so the
evidence can span several days or weeks. The model cannot remove these
constraints through tool arguments.

## Work-item completion

Profiles may opt into a meaningful-completion trigger with:

```json
"triggers": ["after_work_item"],
"cadence": "on_demand",
"scope": {"time_window": "work_item"}
```

This is appropriate for a Discord progress profile: the host offers the
profile after a substantial item closes, and the host supplies that work item's
name as the retrieval anchor. The user can then select it to draft a message.
Small tasks and routine activity should not trigger it.

## Workspace and project backfill

Workspace and project classification is stored on the structured entry. The
repository preserves existing immutable revisions and backfills classification
by publishing a new revision with `revision_reason: "metadata_backfill"`.

Use an explicit mapping file so the application never guesses a private
workspace from free text:

```json
{
  "defaults": {"workspace": "Ranq"},
  "entries": {
    "<entry_id>": {"project": "Auth implementation"}
  }
}
```

Then run:

```bash
work-brain --vault /path/to/vault backfill-context --file context-backfill.json
```

Use `--dry-run` to inspect the planned revisions first.

When older entries mention the selected workspace or project but lack an
explicit catalog reference, retrieval first tries metadata scope and then falls
back to the scoped name plus work-item text as a bounded search anchor. A
workspace is a broad working context such as `Ranq` or `Brother-in-law health
tech`; a project is a specific effort such as `Auth implementation` or `Billing
Right Code`; `domain_tags` remain multi-valued tags such as `auth`, `architecture`,
or `billing`.
