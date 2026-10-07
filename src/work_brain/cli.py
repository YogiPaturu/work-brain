from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from .capture import HarnessCaptureService, record_capture_hook_failure
from .career import CareerService, QuestionBank, QuestionFilters, QuestionRef
from .capture_status import live_status as build_live_status, session_status as build_session_status, status_text
from .commit import CommitResolver, commit_draft_contract
from .config import default_config_path, read_config, resolve_vault_path, set_vault_path
from .context_resolver import ContextResolver
from .domain import normalize_domain_tags
from .errors import FeatureUnavailable, IntegrityError, LockError, PersistenceError, ValidationError, VaultAccessError
from .experiences import ExperienceService
from .fsutil import read_json
from .hook import process as process_capture_hook
from .instructions import SkillLoader
from .lifecycle import CaptureLifecycle, CommitLifecycle, transition
from .setup import HarnessSetup
from .retrieval import EvidenceRetriever
from .services import CommitPublicationResult, ProjectionMaintenance
from .profiles import CommunicationProfileStore, resolve_profiles_path, set_profiles_path
from .timeutil import timestamp_now
from .vault import Vault


EXIT_ERROR = 1
EXIT_VALIDATION = 3
EXIT_PERSISTENCE = 4
EXIT_LOCK = 5
EXIT_UNAVAILABLE = 6


def _json_dump(value: Any, *, sort_keys: bool = True) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=sort_keys, separators=(",", ":")))


def _error_payload(code: str, message: str, hint: str | None = None) -> dict[str, Any]:
    error = {"code": code, "message": message}
    if hint is not None:
        error["hint"] = hint
    return {"ok": False, "error": error}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="work-brain")
    parser.add_argument("--vault", help="private vault path")
    parser.add_argument("--config", help="optional local configuration path")
    parser.add_argument("--profiles", help="communication profiles JSON path")
    parser.add_argument("--json", action="store_true", help="emit deterministic machine-readable JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the private vault")
    sub.add_parser("rebuild", help="rebuild projections and SQLite")
    sub.add_parser("reindex", help="rebuild the derived retrieval index")
    sub.add_parser("doctor", help="validate the vault")
    backfill_context = sub.add_parser("backfill-context", help="add workspace/project metadata as new entry revisions")
    backfill_context.add_argument("--file", required=True, help="JSON mapping with defaults and entry assignments")
    backfill_context.add_argument("--dry-run", action="store_true")
    backfill_tags = sub.add_parser("backfill-tags", help="add domain tags as new entry revisions")
    backfill_tags.add_argument("--file", required=True, help="JSON mapping with defaults and entry assignments")
    backfill_tags.add_argument("--dry-run", action="store_true")
    backfill_project_workspaces = sub.add_parser(
        "backfill-project-workspaces",
        help="assign deterministic workspace ownership to legacy projects",
    )
    backfill_project_workspaces.add_argument("--dry-run", action="store_true")
    migrate_tags = sub.add_parser("migrate-domain-tags", help="rename legacy domains keys in structured vault JSON")
    migrate_tags.add_argument("--dry-run", action="store_true")

    config = sub.add_parser("config", help="manage local user configuration")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    set_vault = config_sub.add_parser("set-vault", help="set the default private vault path")
    set_vault.add_argument("path")
    set_profiles = config_sub.add_parser("set-profiles", help="set the communication profiles JSON path")
    set_profiles.add_argument("path")
    config_sub.add_parser("show", help="show local configuration")

    profiles = sub.add_parser("profiles", help="manage user-owned communication profiles")
    profiles_sub = profiles.add_subparsers(dest="profiles_command", required=True)
    profiles_sub.add_parser("list", help="list available communication profiles")
    show_profile = profiles_sub.add_parser("show", help="show one communication profile")
    show_profile.add_argument("profile_id")
    profiles_sub.add_parser("validate", help="validate the communication profiles document")

    start = sub.add_parser("session-start", help="create a bounded conversation session")
    start.add_argument("--started-at")
    start.add_argument("--mode", action="append", default=[])
    start.add_argument("--domain-tag", action="append", default=[])
    session = sub.add_parser("session", help="inspect persisted conversation sessions")
    session_sub = session.add_subparsers(dest="session_command", required=True)
    turns = session_sub.add_parser("turns", help="read the raw persisted turns for a session")
    turns.add_argument("--session-id", required=True)
    turns.add_argument("--offset", type=int, default=0)
    turns.add_argument("--limit", type=int)
    status = session_sub.add_parser("status", help="read capture and persistence status for a session")
    status.add_argument("--session-id", required=True)
    close = session_sub.add_parser("close", help="close a session without publishing a structured entry")
    close.add_argument("--session-id", required=True)
    close.add_argument("--reason", choices=["no_new_evidence", "abandoned"], default="no_new_evidence")
    quarantine = session_sub.add_parser("quarantine", help="hide one bad structured entry while preserving raw turns")
    quarantine.add_argument("--session-id", required=True)
    quarantine.add_argument("--reason", required=True)
    archive = session_sub.add_parser("archive", help="hide a closed session while preserving all raw turns")
    archive.add_argument("--session-id", required=True)
    archive.add_argument("--reason", required=True)
    import_transcript = session_sub.add_parser("import", help="import an explicitly supplied transcript as raw turns")
    import_transcript.add_argument("--file", required=True, help="JSON transcript object containing a turns list")
    commit = sub.add_parser("commit", help="publish a resolved SessionEntry JSON payload")
    commit.add_argument("--session-id", required=True)
    commit.add_argument("--file", required=True, help="JSON file containing the resolved SessionEntry payload")
    draft = sub.add_parser("commit-draft", help="validate and resolve a CommitDraft")
    draft.add_argument("--session-id", required=True)
    draft.add_argument("--workflow", help="workflow; defaults to the session's active workflow")
    draft.add_argument("--file", help="JSON file; omit or use - to read CommitDraft from stdin")
    schema = sub.add_parser("schema", help="show machine-readable application schemas")
    schema_sub = schema.add_subparsers(dest="schema_command", required=True)
    schema_sub.add_parser("commit-draft", help="show the canonical CommitDraft contract and template")
    skills = sub.add_parser("skills", help="show progressively loaded Skill/SOP resources")
    skills.add_argument("--workflow", default="think")
    skills.add_argument("--domain-tag", action="append", default=[])
    sub.add_parser("recoverable", help="list unfinished sessions")

    live_status = sub.add_parser("status", help="show live capture and commit lifecycle status")
    live_status.add_argument("--watch", action="store_true", help="refresh the status continuously")
    live_status.add_argument("--interval", type=float, default=2.0, help="watch refresh interval in seconds")
    live_status.add_argument("--quiet", action="store_true", help="print a one-line prompt-friendly status")

    state = sub.add_parser("state", help="agent-facing Work Brain state operations")
    state_sub = state.add_subparsers(dest="state_command", required=True)
    state_sub.add_parser("current")
    work = sub.add_parser("work", help="agent-facing work operations")
    work_sub = work.add_subparsers(dest="work_command", required=True)
    recent = work_sub.add_parser("recent")
    recent.add_argument("--limit", type=int, default=8)
    loops = work_sub.add_parser("loops")
    loops.add_argument("--limit", type=int, default=20)
    evidence = sub.add_parser("evidence", help="agent-facing evidence operations")
    evidence_sub = evidence.add_subparsers(dest="evidence_command", required=True)
    search = evidence_sub.add_parser("search")
    search.add_argument("--query", required=True)
    search.add_argument("--page-size", type=int, default=10)
    search.add_argument("--filters", help="JSON object containing EvidenceFilters")
    search.add_argument("--cursor")
    select = evidence_sub.add_parser("select", help="select evidence using filters without a text query")
    select.add_argument("--page-size", type=int, default=10)
    select.add_argument("--filters", help="JSON object containing EvidenceFilters")
    select.add_argument("--cursor")
    hydrate = evidence_sub.add_parser("hydrate")
    hydrate.add_argument("--file", help="JSON object with refs; omit or use - to read stdin")
    get = evidence_sub.add_parser("get")
    get.add_argument("--entry-id", required=True)
    get.add_argument("--revision", type=int)

    context = sub.add_parser("context", help="agent-facing context resolution")
    context_sub = context.add_subparsers(dest="context_command", required=True)
    context_resolve = context_sub.add_parser("resolve", help="resolve existing workspace/project identities")
    context_resolve.add_argument("--workspace", dest="workspace_hint")
    context_resolve.add_argument("--project", dest="project_hint")
    context_resolve.add_argument("--limit", type=int, default=5)

    experience = sub.add_parser("experience", help="read source-backed professional Experiences")
    experience_sub = experience.add_subparsers(dest="experience_command", required=True)
    experience_list = experience_sub.add_parser("list")
    experience_list.add_argument("--limit", type=int, default=8)
    experience_list.add_argument("--filters", help="JSON object containing evidence filters")
    experience_search = experience_sub.add_parser("search")
    experience_search.add_argument("--query", required=True)
    experience_search.add_argument("--page-size", type=int, default=8)
    experience_search.add_argument("--filters", help="JSON object containing evidence filters")
    experience_search.add_argument("--cursor")
    experience_get = experience_sub.add_parser("get")
    experience_get.add_argument("--experience-id", required=True)
    experience_mine = experience_sub.add_parser("mine", help="enumerate bounded ungrouped historical entries for Experience review")
    experience_mine.add_argument("--page-size", type=int, default=5)
    experience_mine.add_argument("--related-limit", type=int, default=6)
    experience_mine.add_argument("--filters", help="JSON object containing anchor filters")
    experience_mine.add_argument("--cursor")
    experience_related = experience_sub.add_parser("related", help="find bounded evidence related to one entry")
    experience_related.add_argument("--entry-id", required=True)
    experience_related.add_argument("--limit", type=int, default=8)
    experience_hydrate = experience_sub.add_parser("hydrate")
    experience_hydrate.add_argument("--experience-id", required=True)
    experience_hydrate.add_argument("--file", help="JSON object with optional refs; omit or use - to read stdin")
    experience_associate = experience_sub.add_parser("associate", help="attach or remove source-backed Experience links")
    experience_associate.add_argument("--entry-id", action="append", required=True)
    target = experience_associate.add_mutually_exclusive_group()
    target.add_argument("--experience-id")
    target.add_argument("--experience-name")
    experience_associate.add_argument("--remove", action="store_true")
    experience_associate.add_argument("--move", action="store_true")

    career = sub.add_parser("career", help="interview practice and career retrieval")
    career.add_argument("--bank", action="append", default=[], metavar="BANK_ID=PATH", help="question bank; repeat for multiple banks")
    career_sub = career.add_subparsers(dest="career_command", required=True)
    questions = career_sub.add_parser("questions", help="query configured question banks")
    questions_sub = questions.add_subparsers(dest="questions_command", required=True)
    question_search = questions_sub.add_parser("search")
    question_search.add_argument("--text")
    question_search.add_argument("--tag-all", action="append", default=[])
    question_search.add_argument("--tag-any", action="append", default=[])
    question_search.add_argument("--exclude-tag", action="append", default=[])
    question_search.add_argument("--bank-id", action="append", default=[])
    question_search.add_argument("--limit", type=int, default=20)
    question_choose = questions_sub.add_parser("choose")
    question_choose.add_argument("--text")
    question_choose.add_argument("--tag-all", action="append", default=[])
    question_choose.add_argument("--tag-any", action="append", default=[])
    question_choose.add_argument("--exclude-tag", action="append", default=[])
    question_choose.add_argument("--bank-id", action="append", default=[])
    question_choose.add_argument("--seed", type=int)
    question_get = questions_sub.add_parser("get")
    question_get.add_argument("--bank-id", required=True)
    question_get.add_argument("--question-id", required=True)
    candidates = career_sub.add_parser("candidates", help="manage explicit interview candidate marks")
    candidates_sub = candidates.add_subparsers(dest="candidates_command", required=True)
    candidates_sub.add_parser("list")
    mark = candidates_sub.add_parser("mark")
    mark.add_argument("--entry-id")
    mark.add_argument("--experience-id")
    mark.add_argument("--target-id")
    mark.add_argument("--target-kind", choices=["entry", "experience"])
    mark.add_argument("--note")
    mark.add_argument("--question-ref", action="append", default=[], metavar="BANK_ID/QUESTION_ID")
    unmark = candidates_sub.add_parser("unmark")
    unmark.add_argument("--entry-id")
    unmark.add_argument("--experience-id")
    unmark.add_argument("--target-id")
    unmark.add_argument("--target-kind", choices=["entry", "experience"])
    prepare = career_sub.add_parser("prepare", help="select a question and retrieve plausible evidence")
    prepare.add_argument("--question-text")
    prepare.add_argument("--question-ref", metavar="BANK_ID/QUESTION_ID")
    prepare.add_argument("--query")
    prepare.add_argument("--tag-all", action="append", default=[])
    prepare.add_argument("--tag-any", action="append", default=[])
    prepare.add_argument("--exclude-tag", action="append", default=[])
    prepare.add_argument("--bank-id", action="append", default=[])
    prepare.add_argument("--page-size", type=int, default=8)
    prepare.add_argument("--cursor")
    prepare.add_argument("--seed", type=int)
    mock = career_sub.add_parser("mock", help="select a question without revealing evidence before the answer")
    mock.add_argument("--question-text")
    mock.add_argument("--question-ref", metavar="BANK_ID/QUESTION_ID")
    mock.add_argument("--tag-all", action="append", default=[])
    mock.add_argument("--tag-any", action="append", default=[])
    mock.add_argument("--exclude-tag", action="append", default=[])
    mock.add_argument("--bank-id", action="append", default=[])
    mock.add_argument("--seed", type=int)

    capture = sub.add_parser("capture-hook", help="normalize one host hook JSON object from stdin")
    capture.add_argument("--host", required=True, choices=["codex", "claude-code", "cursor"])
    stop = sub.add_parser("capture-stop", help="deactivate an explicitly captured host conversation")
    stop.add_argument("--host", required=True, choices=["codex", "claude-code", "cursor"])
    stop.add_argument("--host-session-id", required=True)
    stop.add_argument("--session-id")
    setup = sub.add_parser("setup", help="expose the canonical Skill and install additive host hooks")
    setup.add_argument("host", choices=["codex", "claude", "claude-code", "cursor"])
    setup.add_argument("--check", action="store_true")
    return parser


def _read_payload(path: str | None) -> dict[str, Any]:
    value = json.load(sys.stdin) if path is None or path == "-" else read_json(Path(path))
    if not isinstance(value, dict):
        raise ValidationError("structured input must be a JSON object")
    return value


def _read_transcript(path: str) -> dict[str, Any]:
    value = read_json(Path(path))
    if not isinstance(value, dict):
        raise ValidationError("transcript input must be a JSON object")
    return value


def _backfill_context(vault: Vault, payload: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    defaults = payload.get("defaults", {})
    assignments = payload.get("entries", {})
    if not isinstance(defaults, dict):
        raise ValidationError("backfill-context defaults must be an object")
    if not isinstance(assignments, dict):
        raise ValidationError("backfill-context entries must be an object keyed by entry_id")
    allowed = {"workspace", "project"}
    for label, value in (("defaults", defaults),):
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValidationError(f"backfill-context {label} has unknown field: {unknown[0]}")
    current = {entry.entry_id: entry for entry in vault.all_current_entries()}
    unknown_entries = sorted(set(assignments) - set(current))
    if unknown_entries:
        raise ValidationError(f"backfill-context entry does not exist: {unknown_entries[0]}")
    plan = []
    for entry in sorted(current.values(), key=lambda item: (item.created_at, item.entry_id)):
        override = assignments.get(entry.entry_id)
        if override is not None and not isinstance(override, dict):
            raise ValidationError(f"backfill-context assignment for {entry.entry_id} must be an object")
        override = override or {}
        unknown = sorted(set(override) - allowed)
        if unknown:
            raise ValidationError(f"backfill-context assignment has unknown field: {unknown[0]}")
        requested = dict(defaults)
        requested.update(override)
        if not requested:
            continue
        plan.append({
            "entry_id": entry.entry_id,
            "title": entry.title,
            "from": {"workspace": entry.workspace_entity_id, "project": entry.project_entity_id},
            "requested": requested,
        })
    if dry_run:
        return {"dry_run": True, "planned": plan, "count": len(plan)}
    updated = []
    unchanged = []
    for item in plan:
        entry_id = item["entry_id"]
        requested = item["requested"]
        before = vault.get_current_entry(entry_id)
        changes = {}
        if "workspace" in requested:
            changes["workspace"] = requested["workspace"]
        if "project" in requested:
            changes["project"] = requested["project"]
        entry = vault.backfill_entry_context(entry_id, **changes)
        if entry.revision == before.revision:
            unchanged.append(entry_id)
        else:
            updated.append({"entry_id": entry.entry_id, "revision": entry.revision, "commit_id": entry.commit_id})
    return {"dry_run": False, "updated": updated, "unchanged": unchanged, "count": len(updated)}


def _backfill_tags(vault: Vault, payload: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    defaults = payload.get("defaults", {})
    assignments = payload.get("entries", {})
    if not isinstance(defaults, dict):
        raise ValidationError("backfill-tags defaults must be an object")
    if not isinstance(assignments, dict):
        raise ValidationError("backfill-tags entries must be an object keyed by entry_id")
    allowed = {"domain_tags"}
    unknown = sorted(set(defaults) - allowed)
    if unknown:
        raise ValidationError(f"backfill-tags defaults has unknown field: {unknown[0]}")
    current = {entry.entry_id: entry for entry in vault.all_current_entries()}
    unknown_entries = sorted(set(assignments) - set(current))
    if unknown_entries:
        raise ValidationError(f"backfill-tags entry does not exist: {unknown_entries[0]}")
    plan = []
    for entry in sorted(current.values(), key=lambda item: (item.created_at, item.entry_id)):
        override = assignments.get(entry.entry_id)
        if override is not None and not isinstance(override, dict):
            raise ValidationError(f"backfill-tags assignment for {entry.entry_id} must be an object")
        override = override or {}
        unknown = sorted(set(override) - allowed)
        if unknown:
            raise ValidationError(f"backfill-tags assignment has unknown field: {unknown[0]}")
        requested = dict(defaults)
        requested.update(override)
        if "domain_tags" not in requested:
            continue
        additions = normalize_domain_tags(requested["domain_tags"])
        merged = normalize_domain_tags([*entry.domain_tags, *additions])
        plan.append({
            "entry_id": entry.entry_id,
            "title": entry.title,
            "from": entry.domain_tags,
            "add": [tag for tag in merged if tag not in entry.domain_tags],
            "result": merged,
        })
    if dry_run:
        return {"dry_run": True, "planned": plan, "count": len(plan)}
    updated = []
    unchanged = []
    for item in plan:
        before = vault.get_current_entry(item["entry_id"])
        entry = vault.backfill_entry_domain_tags(item["entry_id"], domain_tags=item["result"])
        if entry.revision == before.revision:
            unchanged.append(item["entry_id"])
        else:
            updated.append({"entry_id": entry.entry_id, "revision": entry.revision, "commit_id": entry.commit_id})
    return {"dry_run": False, "updated": updated, "unchanged": unchanged, "count": len(updated)}


def _backfill_project_workspaces(vault: Vault, *, dry_run: bool) -> dict[str, Any]:
    if dry_run:
        plan = vault.project_workspace_backfill_plan()
        return {"dry_run": True, **plan}

    # Compute and apply under one source writer lock. The explicit source
    # operation also revalidates each target, so a stale plan cannot reparent
    # an already-owned project.
    with vault.write_lock():
        plan = vault.project_workspace_backfill_plan()
        updated: list[dict[str, Any]] = []
        unchanged = [item["project_entity_id"] for item in plan["already_owned"]]
        for assignment in plan["assignments"]:
            result = vault.backfill_project_workspace(
                assignment["project_entity_id"], assignment["workspace_entity_id"]
            )
            if result["changed"]:
                updated.append({
                    "project_entity_id": assignment["project_entity_id"],
                    "workspace_entity_id": assignment["workspace_entity_id"],
                })
            else:
                unchanged.append(assignment["project_entity_id"])

    maintenance: dict[str, Any] = {"status": "not_needed"}
    if updated:
        try:
            retrieval = ProjectionMaintenance(vault).rebuild()
            maintenance = {"status": "current", "retrieval": retrieval}
        except Exception as exc:
            # Source ownership is authoritative and already committed. Keep
            # projection repair visible without reporting the source mutation
            # as an ordinary failed operation.
            maintenance = {"status": "failed", "error": str(exc)}
    return {
        "dry_run": False,
        **plan,
        "updated": updated,
        "unchanged": unchanged,
        "maintenance": maintenance,
    }


def _vault(args: argparse.Namespace) -> Vault:
    return Vault(resolve_vault_path(args.vault, config_path=args.config))


def _current_state(vault: Vault) -> dict[str, Any]:
    return read_json(vault.root / "state/current.json")


def _recent_work(vault: Vault, limit: int) -> list[dict[str, Any]]:
    if not isinstance(limit, int) or not 0 < limit <= 50:
        raise ValidationError("limit must be an integer between 1 and 50")
    entries = sorted(vault.all_current_entries(), key=lambda item: item.created_at, reverse=True)
    return [{"entry_id": e.entry_id, "revision": e.revision, "title": e.title, "summary": e.summary} for e in entries[:limit]]


def _session_turns(vault: Vault, session_id: str, *, offset: int, limit: int | None) -> dict[str, Any]:
    if not isinstance(offset, int) or offset < 0:
        raise ValidationError("offset must be a non-negative integer")
    if limit is not None and (not isinstance(limit, int) or not 1 <= limit <= 1000):
        raise ValidationError("limit must be an integer between 1 and 1000")
    session = vault.read_session(session_id)
    turns = vault.list_turns(session_id)
    selected = turns[offset:] if limit is None else turns[offset:offset + limit]
    return {
        "session_id": session["session_id"],
        "entry_id": session["entry_id"],
        "local_date": session["local_date"],
        "ended_at": session.get("ended_at"),
        "turn_count": len(turns),
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(selected) < len(turns),
        "turns": selected,
    }


def _watch_status(args: argparse.Namespace) -> int:
    if args.json:
        raise ValidationError("--watch cannot be combined with --json")
    if args.interval <= 0:
        raise ValidationError("--interval must be greater than zero")
    vault = _vault(args)
    try:
        while True:
            snapshot = build_live_status(vault)
            if sys.stdout.isatty():
                sys.stdout.write("\033[2J\033[H")
            else:
                sys.stdout.write("\n")
            sys.stdout.write(status_text(snapshot, quiet=args.quiet) + "\n")
            sys.stdout.flush()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        if sys.stdout.isatty():
            sys.stdout.write("\n")
        return 0


def _open_loops(vault: Vault, limit: int) -> list[dict[str, Any]]:
    if not isinstance(limit, int) or not 0 < limit <= 100:
        raise ValidationError("limit must be an integer between 1 and 100")
    state = _current_state(vault)
    return [item for item in state.get("items", []) if item.get("status") not in {"done", "dropped"}][:limit]


def _hydrate(vault: Vault, entry_id: str, revision: int | None) -> dict[str, Any]:
    candidates = [entry for entry, _ in vault.all_entry_revisions() if entry.entry_id == entry_id and (revision is None or entry.revision == revision)]
    if not candidates:
        raise FileNotFoundError(f"evidence entry not found: {entry_id}")
    entry = max(candidates, key=lambda item: item.revision) if revision is None else candidates[0]
    referenced: set[int] = set()
    for statements in entry.sections.values():
        for statement in statements:
            referenced.update(statement.source_turns)
    for mutation in entry.state_mutations:
        referenced.update(mutation.source_turns)
    turns = [turn for turn in vault.list_turns(entry.session_id) if turn["sequence"] in referenced]
    return {"entry": entry.to_dict(), "source_turns": turns}


def _career_service(vault: Vault, specs: list[str]) -> CareerService:
    banks = []
    for spec in specs:
        if "=" not in spec:
            raise ValidationError("--bank must be BANK_ID=PATH")
        bank_id, path = spec.split("=", 1)
        banks.append(QuestionBank(bank_id, Path(path).expanduser().resolve(), "public_shared"))
    return CareerService(vault, banks=banks or None)


def _finish_capture_after_commit(vault: Vault, session_id: str, workflow: str | None = None) -> dict[str, Any]:
    """Keep ordinary host capture active, but close lifecycle workflows."""
    session = vault.read_session(session_id)
    chosen = workflow or (session.get("runtime") or {}).get("workflow") or "think"
    capture = HarnessCaptureService(vault)
    if chosen == "close-day":
        continuation = capture.stop_session(session_id)
    else:
        continuation = capture.rotate_session(session_id)

    # The capture service owns rotation/deactivation, while this CLI path owns
    # publication. Reconcile both pieces so a successful commit cannot remain
    # marked as a recoverable raw session, including sessions with no active
    # host mapping.
    session = vault.read_session(session_id)
    runtime, _ = transition(
        session.get("runtime"),
        capture=CaptureLifecycle.CLOSED,
        commit=CommitLifecycle.COMMITTED,
        ended_at=session.get("ended_at"),
        has_entry=True,
    )
    runtime.update({
        "workflow": chosen,
        "capture_status": "committed",
        "commit_status": "committed",
        "capture_boundary": "closed",
    })
    session["runtime"] = runtime
    session["ended_at"] = session.get("ended_at") or timestamp_now()
    vault.update_session_metadata(session_id, session)
    return continuation


def _question_filters(args: argparse.Namespace) -> QuestionFilters:
    return QuestionFilters.from_values(
        tags_all=getattr(args, "tag_all", []), tags_any=getattr(args, "tag_any", []),
        exclude_tags=getattr(args, "exclude_tag", []), bank_ids=getattr(args, "bank_id", []),
    )


def _question_ref(value: str | None) -> QuestionRef | None:
    if value is None:
        return None
    if "/" not in value:
        raise ValidationError("--question-ref must be BANK_ID/QUESTION_ID")
    bank_id, question_id = value.split("/", 1)
    return QuestionRef(bank_id, question_id)


def _run(args: argparse.Namespace) -> tuple[Any, bool]:
    command = args.command
    machine = bool(args.json or command in {"state", "work", "evidence", "context", "experience", "career", "capture-hook", "capture-stop", "recoverable", "skills", "session-start", "commit", "commit-draft", "setup", "reindex", "session", "profiles", "backfill-context", "backfill-tags", "backfill-project-workspaces", "migrate-domain-tags", "schema"})
    if command == "status":
        snapshot = build_live_status(_vault(args))
        return snapshot, bool(args.json)
    if command == "config":
        if args.config_command == "set-vault":
            path = set_vault_path(args.path, args.config)
            return {"config_path": str(Path(args.config).expanduser()) if args.config else str(default_config_path()), "vault": str(path)}, True
        if args.config_command == "set-profiles":
            path = set_profiles_path(args.path, args.config)
            return {"config_path": str(Path(args.config).expanduser()) if args.config else str(default_config_path()), "communication_profiles": str(path)}, True
        return read_config(args.config), True
    if command == "profiles":
        store = CommunicationProfileStore.load(args.profiles, config_path=args.config)
        if args.profiles_command == "list":
            return {"path": str(resolve_profiles_path(args.profiles, config_path=args.config)), "profiles": [profile.to_dict() for profile in store.list()]}, True
        if args.profiles_command == "show":
            return store.get(args.profile_id).to_dict(), True
        return {"valid": True, "path": str(resolve_profiles_path(args.profiles, config_path=args.config)), "count": len(store.list())}, True
    if command == "setup":
        try:
            vault_path = resolve_vault_path(args.vault, config_path=args.config)
        except ValidationError:
            vault_path = None
        report = HarnessSetup().install(args.host, check=args.check, vault_path=vault_path).to_dict()
        if args.vault:
            selected = set_vault_path(args.vault, args.config)
            report["configured_vault"] = str(selected)
        return report, True
    if command == "capture-hook":
        vault = _vault(args)
        return process_capture_hook(vault, args.host, _read_payload("-")), True
    if command == "capture-stop":
        return HarnessCaptureService(_vault(args)).stop(host=args.host, host_session_id=args.host_session_id, session_id=args.session_id), True
    if command == "schema" and args.schema_command == "commit-draft":
        return commit_draft_contract(), True

    vault = _vault(args)
    if command == "context" and args.context_command == "resolve":
        return ContextResolver(vault).resolve_context(
            workspace_hint=args.workspace_hint,
            project_hint=args.project_hint,
            limit=args.limit,
        ), True
    if command == "experience":
        service = ExperienceService(vault)
        if args.experience_command == "list":
            filters = json.loads(args.filters) if args.filters else None
            if filters is not None and not isinstance(filters, dict):
                raise ValidationError("--filters must be a JSON object")
            return service.list(limit=args.limit, filters=filters), True
        if args.experience_command == "search":
            filters = json.loads(args.filters) if args.filters else None
            if filters is not None and not isinstance(filters, dict):
                raise ValidationError("--filters must be a JSON object")
            return service.search(args.query, filters=filters, page_size=args.page_size, cursor=args.cursor), True
        if args.experience_command == "get":
            return service.get(args.experience_id), True
        if args.experience_command == "mine":
            filters = json.loads(args.filters) if args.filters else None
            if filters is not None and not isinstance(filters, dict):
                raise ValidationError("--filters must be a JSON object")
            return service.mine(
                page_size=args.page_size,
                related_limit=args.related_limit,
                filters=filters,
                cursor=args.cursor,
            ), True
        if args.experience_command == "related":
            return service.related(args.entry_id, limit=args.limit), True
        if args.experience_command == "associate":
            if args.remove and (args.experience_id or args.experience_name):
                raise ValidationError("--remove cannot be combined with an Experience target")
            return service.associate_entries(
                args.entry_id,
                experience_id=args.experience_id,
                experience_name=args.experience_name,
                remove=args.remove,
                move=args.move,
            ), True
        payload = _read_payload(args.file) if args.file else {}
        refs = payload.get("refs")
        if refs is not None and not isinstance(refs, list):
            raise ValidationError("experience hydration refs must be a list")
        return service.hydrate(args.experience_id, refs=refs), True
    if command == "career":
        service = _career_service(vault, args.bank)
        if args.career_command == "questions":
            if args.questions_command == "search":
                return service.search_questions(filters=_question_filters(args), text=args.text, limit=args.limit), True
            if args.questions_command == "choose":
                return service.choose_question(filters=_question_filters(args), text=args.text, seed=args.seed), True
            return service.get_question(QuestionRef(args.bank_id, args.question_id)), True
        if args.career_command == "candidates":
            if args.candidates_command == "list":
                return {"marks": service.marks.list()}, True
            if args.candidates_command == "mark":
                refs = []
                for raw in args.question_ref:
                    ref = _question_ref(raw)
                    refs.append(ref.to_dict())
                target_id = args.target_id or args.entry_id or args.experience_id
                target_kind = args.target_kind or ("experience" if args.experience_id else "entry")
                if not target_id:
                    raise ValidationError("candidate mark requires --target-id, --entry-id, or --experience-id")
                return service.marks.mark(target_id, target_kind=target_kind, note=args.note, question_refs=refs), True
            target_id = args.target_id or args.entry_id or args.experience_id
            target_kind = args.target_kind or ("experience" if args.experience_id else "entry")
            if not target_id:
                raise ValidationError("candidate unmark requires --target-id, --entry-id, or --experience-id")
            return service.marks.unmark(target_id, target_kind=target_kind), True
        ref = _question_ref(args.question_ref)
        question = service.get_question(ref) if ref else None
        if args.career_command == "prepare":
            return service.prepare(question=question, question_text=args.question_text, query=args.query, filters=_question_filters(args), page_size=args.page_size, cursor=args.cursor, seed=args.seed), True
        return service.mock(question=question, question_text=args.question_text, filters=_question_filters(args), seed=args.seed), True
    if command == "init":
        vault.initialize()
        ProjectionMaintenance(vault).rebuild()
        return {"initialized": True, "vault": str(vault.root)}, machine
    if command == "rebuild":
        retrieval = ProjectionMaintenance(vault).rebuild()
        return {"rebuilt": True, "vault": str(vault.root), "retrieval": retrieval}, machine
    if command == "reindex":
        return EvidenceRetriever(vault).reindex(), True
    if command == "backfill-context":
        return _backfill_context(vault, _read_payload(args.file), dry_run=args.dry_run), True
    if command == "backfill-tags":
        return _backfill_tags(vault, _read_payload(args.file), dry_run=args.dry_run), True
    if command == "backfill-project-workspaces":
        return _backfill_project_workspaces(vault, dry_run=args.dry_run), True
    if command == "migrate-domain-tags":
        return vault.migrate_domain_tags(dry_run=args.dry_run), True
    if command == "doctor":
        diagnostics = vault.doctor()
        retriever = EvidenceRetriever(vault)
        try:
            health = retriever.health()
            embedding = retriever.embedding_status(health)
        except Exception as exc:
            diagnostics.append(f"retrieval health unavailable: {exc}")
            embedding = {
                "provider": "unavailable",
                "status": "failed",
                "warning": "Run work-brain reindex after repairing the derived database.",
            }
        return {
            "ok": not diagnostics,
            "diagnostics": diagnostics,
            "embedding": embedding,
        }, machine
    if command == "session-start":
        started_at = args.started_at
        rollover = HarnessCaptureService(vault).rollover_stale_sessions(reference_at=started_at)
        session = vault.create_session(started_at=started_at, modes=args.mode, domain_tags=args.domain_tag)
        return {"session": session, "rollover": rollover}, True
    if command == "session" and args.session_command == "turns":
        return _session_turns(vault, args.session_id, offset=args.offset, limit=args.limit), True
    if command == "session" and args.session_command == "status":
        return build_session_status(vault, args.session_id), True
    if command == "session" and args.session_command == "close":
        HarnessCaptureService(vault).stop_session(args.session_id)
        return vault.close_session(args.session_id, commit_status=args.reason), True
    if command == "session" and args.session_command == "quarantine":
        vault.quarantine_entry(args.session_id, reason=args.reason)
        return {"session_id": args.session_id, "status": "structured_entry_quarantined", "raw_turns_preserved": True}, True
    if command == "session" and args.session_command == "archive":
        vault.archive_session(args.session_id, reason=args.reason)
        return {"session_id": args.session_id, "status": "session_archived", "raw_turns_preserved": True}, True
    if command == "session" and args.session_command == "import":
        return HarnessCaptureService(vault).import_transcript(_read_transcript(args.file)), True
    if command == "commit":
        entry = vault.commit_entry(args.session_id, _read_payload(args.file))
        maintenance = ProjectionMaintenance(vault).after_source_commit(entry)
        continuation = _finish_capture_after_commit(vault, args.session_id)
        result = CommitPublicationResult.from_entry(entry, maintenance, vault.consume_source_warnings())
        return {**result.to_dict(), "capture": continuation}, True
    if command == "commit-draft":
        session = vault.read_session(args.session_id)
        workflow = args.workflow or (session.get("runtime") or {}).get("workflow") or "think"
        result = CommitResolver(vault).publish_result(args.session_id, _read_payload(args.file), workflow=workflow)
        continuation = _finish_capture_after_commit(vault, args.session_id, workflow)
        return {**result.to_dict(), "capture": continuation}, True
    if command == "skills":
        loaded = SkillLoader().load(args.workflow, args.domain_tag)
        return {"resources": loaded.identities, "missing": list(loaded.missing)}, True
    if command == "recoverable":
        entry_session_ids = {entry.session_id for entry in vault.all_current_entries()}
        return [
            session for session in vault.all_sessions()
            if session["session_id"] not in entry_session_ids and (
                session.get("ended_at") is None
                or (session.get("runtime") or {}).get("commit_status") in {"pending_auto_commit", "auto_commit_failed"}
            )
        ], True
    if command == "state" and args.state_command == "current":
        return _current_state(vault), True
    if command == "work" and args.work_command == "recent":
        return _recent_work(vault, args.limit), True
    if command == "work" and args.work_command == "loops":
        return _open_loops(vault, args.limit), True
    if command == "evidence" and args.evidence_command == "get":
        return _hydrate(vault, args.entry_id, args.revision), True
    if command == "evidence" and args.evidence_command == "search":
        filters = json.loads(args.filters) if args.filters else {}
        if not isinstance(filters, dict):
            raise ValidationError("--filters must be a JSON object")
        return EvidenceRetriever(vault).search(args.query, filters=filters, page_size=args.page_size, cursor=args.cursor), True
    if command == "evidence" and args.evidence_command == "select":
        filters = json.loads(args.filters) if args.filters else {}
        if not isinstance(filters, dict):
            raise ValidationError("--filters must be a JSON object")
        return EvidenceRetriever(vault).select_evidence(filters=filters, page_size=args.page_size, cursor=args.cursor), True
    if command == "evidence" and args.evidence_command == "hydrate":
        payload = _read_payload(args.file)
        return EvidenceRetriever(vault).hydrate(payload.get("refs", [])), True
    raise ValidationError(f"unsupported command: {command}")


def _is_codex_capture_hook(args: argparse.Namespace) -> bool:
    return args.command == "capture-hook" and args.host == "codex"


def _normalize_cli_argv(argv: list[str] | None) -> list[str] | None:
    """Accept the global JSON flag before or after a subcommand.

    Agent-generated shell commands commonly append ``--json`` to the
    operation.  argparse only accepts this global option before the
    subcommand, so normalize that harmless placement at the CLI boundary.
    """
    values = list(sys.argv[1:] if argv is None else argv)
    if "--json" not in values:
        return argv
    values.remove("--json")
    values.insert(0, "--json")
    return values


def main(argv: list[str] | None = None) -> int:
    args: argparse.Namespace | None = None
    try:
        args = _parser().parse_args(_normalize_cli_argv(argv))
        if args.command == "status" and args.watch:
            return _watch_status(args)
        value, machine = _run(args)
        code = 4 if args.command == "doctor" and not value["ok"] else 0
        if _is_codex_capture_hook(args):
            # Codex hooks have a separate stdout protocol.  The capture result
            # is an internal application response, not a valid Codex hook
            # response; leaking it causes "invalid ... JSON output" errors.
            # Persistence has already happened in _run, so a successful hook
            # is intentionally a JSON no-op.
            _json_dump(value.get("_hook_output", {}))
        elif machine:
            _json_dump(value, sort_keys=args.command != "schema")
        elif args.command == "init":
            print(f"initialized {value['vault']}")
        elif args.command == "rebuild":
            print("rebuilt projections and SQLite")
        elif args.command == "doctor":
            print("vault is healthy" if value["ok"] else "vault diagnostics failed")
            embedding = value["embedding"]
            print(f"semantic retrieval: {embedding['provider']} ({embedding['status']})")
            if embedding.get("warning"):
                print(f"warning: {embedding['warning']}")
            for diagnostic in value["diagnostics"]:
                print(f"diagnostic: {diagnostic}")
        elif args.command == "status":
            print(status_text(value, quiet=args.quiet))
        return code
    except SystemExit:
        raise
    except Exception as exc:
        if args is not None and _is_codex_capture_hook(args):
            # Capture is best-effort at the host boundary.  A vault/config
            # problem must not turn an internal error payload into malformed
            # hook output or interfere with the user's Codex turn.
            try:
                record_capture_hook_failure(_vault(args), host=args.host, category="capture_hook_failure", error=exc)
            except Exception:
                pass
            _json_dump({})
            return 0
        if isinstance(exc, FeatureUnavailable):
            _json_dump(_error_payload("unavailable", str(exc)))
            return EXIT_UNAVAILABLE
        if isinstance(exc, LockError):
            _json_dump(_error_payload("lock_conflict", str(exc)))
            return EXIT_LOCK
        if isinstance(exc, VaultAccessError):
            hint = ("The configured Work Brain vault must be writable by the current host process. If using Codex workspace-write, "
                    "add the vault to [sandbox_workspace_write].writable_roots in ~/.codex/config.toml, restart Codex, and retry "
                    "the same Work Brain session. Do not modify the CommitDraft to repair this error.")
            _json_dump(_error_payload("vault_access_denied", str(exc), hint))
            return EXIT_PERSISTENCE
        if isinstance(exc, (ValidationError, ValueError)):
            _json_dump(_error_payload("invalid_request", str(exc)))
            return EXIT_VALIDATION
        if isinstance(exc, (PersistenceError, IntegrityError, FileNotFoundError, json.JSONDecodeError)):
            _json_dump(_error_payload("persistence_error", str(exc)))
            return EXIT_PERSISTENCE
        _json_dump(_error_payload("internal_error", str(exc)))
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
