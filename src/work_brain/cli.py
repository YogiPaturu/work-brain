from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .capture import HarnessCaptureService, normalize_capture_event
from .career import CareerService, QuestionBank, QuestionFilters, QuestionRef
from .commit import CommitResolver
from .config import default_config_path, read_config, resolve_vault_path, set_vault_path
from .errors import FeatureUnavailable, IntegrityError, LockError, PersistenceError, ValidationError
from .fsutil import read_json
from .instructions import SkillLoader
from .setup import HarnessSetup
from .retrieval import EvidenceRetriever
from .vault import Vault


EXIT_ERROR = 1
EXIT_VALIDATION = 3
EXIT_PERSISTENCE = 4
EXIT_LOCK = 5
EXIT_UNAVAILABLE = 6


def _json_dump(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _error_payload(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="work-brain")
    parser.add_argument("--vault", help="private vault path")
    parser.add_argument("--config", help="optional local configuration path")
    parser.add_argument("--json", action="store_true", help="emit deterministic machine-readable JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the private vault")
    sub.add_parser("rebuild", help="rebuild projections and SQLite")
    sub.add_parser("reindex", help="rebuild the derived retrieval index")
    sub.add_parser("doctor", help="validate the vault")

    config = sub.add_parser("config", help="manage local user configuration")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    set_vault = config_sub.add_parser("set-vault", help="set the default private vault path")
    set_vault.add_argument("path")
    config_sub.add_parser("show", help="show local configuration")

    start = sub.add_parser("session-start", help="create a bounded conversation session")
    start.add_argument("--started-at")
    start.add_argument("--mode", action="append", default=[])
    start.add_argument("--domain", action="append", default=[])
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
    turn = sub.add_parser("turn", help="append one durable user or assistant turn")
    turn.add_argument("--session-id", required=True)
    turn.add_argument("--role", required=True, choices=["user", "assistant"])
    turn.add_argument("--content")
    turn.add_argument("--recorded-at")
    commit = sub.add_parser("commit", help="publish a resolved SessionEntry JSON payload")
    commit.add_argument("--session-id", required=True)
    commit.add_argument("--file", required=True, help="JSON file containing the resolved SessionEntry payload")
    draft = sub.add_parser("commit-draft", help="validate and resolve a CommitDraft")
    draft.add_argument("--session-id", required=True)
    draft.add_argument("--workflow", help="workflow; defaults to the session's active workflow")
    draft.add_argument("--file", help="JSON file; omit or use - to read CommitDraft from stdin")
    skills = sub.add_parser("skills", help="show progressively loaded Skill/SOP resources")
    skills.add_argument("--workflow", default="think")
    skills.add_argument("--domain", action="append", default=[])
    sub.add_parser("recoverable", help="list unfinished sessions")

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
    hydrate = evidence_sub.add_parser("hydrate")
    hydrate.add_argument("--file", help="JSON object with refs; omit or use - to read stdin")
    get = evidence_sub.add_parser("get")
    get.add_argument("--entry-id", required=True)
    get.add_argument("--revision", type=int)

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
    mark.add_argument("--entry-id", required=True)
    mark.add_argument("--note")
    mark.add_argument("--question-ref", action="append", default=[], metavar="BANK_ID/QUESTION_ID")
    unmark = candidates_sub.add_parser("unmark")
    unmark.add_argument("--entry-id", required=True)
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


def _session_status(vault: Vault, session_id: str) -> dict[str, Any]:
    session = vault.read_session(session_id)
    turns = vault.list_turns(session_id)
    mappings_path = vault.root / HarnessCaptureService.MAP_RELATIVE
    mappings = read_json(mappings_path) if mappings_path.exists() else {}
    host_mappings = [
        {
            "host": value.get("host"),
            "host_session_id": value.get("host_session_id"),
            "workflow": value.get("workflow"),
            "active": value.get("session_id") == session_id,
        }
        for value in mappings.values()
        if isinstance(value, dict) and value.get("session_id") == session_id
    ]
    entries = [entry for entry in vault.all_current_entries() if entry.session_id == session_id]
    runtime = dict(session.get("runtime") or {})
    if host_mappings:
        lifecycle = "active_capture"
    elif session.get("ended_at") is None and runtime.get("capture_status") in {"recoverable", "rolled_over"}:
        lifecycle = "recoverable_raw"
    elif runtime.get("commit_status") == "no_new_evidence":
        lifecycle = "closed_no_new_evidence"
    elif entries:
        lifecycle = "committed"
    else:
        lifecycle = "closed_uncommitted"
    last = turns[-1] if turns else None
    return {
        "session_id": session["session_id"],
        "entry_id": session["entry_id"],
        "local_date": session["local_date"],
        "started_at": session["started_at"],
        "ended_at": session.get("ended_at"),
        "lifecycle": lifecycle,
        "capture_status": runtime.get("capture_status", "not_captured"),
        "commit_status": runtime.get("commit_status"),
        "turn_count": len(turns),
        "last_captured_turn": None if last is None else {
            "sequence": last["sequence"], "role": last["role"], "recorded_at": last["recorded_at"],
        },
        "host_mappings": host_mappings,
        "has_committed_entry": bool(entries),
        "current_revision": max((entry.revision for entry in entries), default=None),
    }


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
        return capture.stop_session(session_id)
    return capture.rotate_session(session_id)


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
    machine = bool(args.json or command in {"state", "work", "evidence", "career", "capture-hook", "capture-stop", "recoverable", "skills", "session-start", "turn", "commit", "commit-draft", "setup", "reindex", "session"})
    if command == "config":
        if args.config_command == "set-vault":
            path = set_vault_path(args.path, args.config)
            return {"config_path": str(Path(args.config).expanduser()) if args.config else str(default_config_path()), "vault": str(path)}, True
        return read_config(args.config), True
    if command == "setup":
        report = HarnessSetup().install(args.host, check=args.check).to_dict()
        if args.vault:
            selected = set_vault_path(args.vault, args.config)
            report["configured_vault"] = str(selected)
        return report, True
    if command == "capture-hook":
        event = normalize_capture_event(args.host, _read_payload("-"))
        return HarnessCaptureService(_vault(args)).handle(event), True
    if command == "capture-stop":
        return HarnessCaptureService(_vault(args)).stop(host=args.host, host_session_id=args.host_session_id, session_id=args.session_id), True

    vault = _vault(args)
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
                return service.marks.mark(args.entry_id, note=args.note, question_refs=refs), True
            return service.marks.unmark(args.entry_id), True
        ref = _question_ref(args.question_ref)
        question = service.get_question(ref) if ref else None
        if args.career_command == "prepare":
            return service.prepare(question=question, question_text=args.question_text, query=args.query, filters=_question_filters(args), page_size=args.page_size, cursor=args.cursor, seed=args.seed), True
        return service.mock(question=question, question_text=args.question_text, filters=_question_filters(args), seed=args.seed), True
    if command == "init":
        vault.initialize()
        EvidenceRetriever(vault).reindex()
        return {"initialized": True, "vault": str(vault.root)}, machine
    if command == "rebuild":
        vault.rebuild_all()
        return {"rebuilt": True, "vault": str(vault.root)}, machine
    if command == "reindex":
        return EvidenceRetriever(vault).reindex(), True
    if command == "doctor":
        diagnostics = vault.doctor()
        retriever = EvidenceRetriever(vault)
        return {
            "ok": not diagnostics,
            "diagnostics": diagnostics,
            "embedding": retriever.embedding_status(retriever.health()),
        }, machine
    if command == "session-start":
        started_at = args.started_at
        rollover = HarnessCaptureService(vault).rollover_stale_sessions(reference_at=started_at)
        session = vault.create_session(started_at=started_at, modes=args.mode, domains=args.domain)
        return {"session": session, "rollover": rollover}, True
    if command == "session" and args.session_command == "turns":
        return _session_turns(vault, args.session_id, offset=args.offset, limit=args.limit), True
    if command == "session" and args.session_command == "status":
        return _session_status(vault, args.session_id), True
    if command == "session" and args.session_command == "close":
        HarnessCaptureService(vault).stop_session(args.session_id)
        return vault.close_session(args.session_id, commit_status=args.reason), True
    if command == "turn":
        content = args.content if args.content is not None else sys.stdin.read()
        return vault.append_turn(args.session_id, args.role, content, recorded_at=args.recorded_at), True
    if command == "commit":
        entry = vault.commit_entry(args.session_id, _read_payload(args.file))
        continuation = _finish_capture_after_commit(vault, args.session_id)
        return {"entry_id": entry.entry_id, "revision": entry.revision, "commit_id": entry.commit_id, "capture": continuation}, True
    if command == "commit-draft":
        session = vault.read_session(args.session_id)
        workflow = args.workflow or (session.get("runtime") or {}).get("workflow") or "think"
        entry = CommitResolver(vault).publish(args.session_id, _read_payload(args.file), workflow=workflow)
        continuation = _finish_capture_after_commit(vault, args.session_id, workflow)
        return {"entry_id": entry.entry_id, "revision": entry.revision, "commit_id": entry.commit_id, "capture": continuation}, True
    if command == "skills":
        loaded = SkillLoader().load(args.workflow, args.domain)
        return {"resources": loaded.identities, "missing": list(loaded.missing)}, True
    if command == "recoverable":
        return [session for session in vault.all_sessions() if session.get("ended_at") is None], True
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
        value, machine = _run(args)
        code = 4 if args.command == "doctor" and not value["ok"] else 0
        if _is_codex_capture_hook(args):
            # Codex hooks have a separate stdout protocol.  The capture result
            # is an internal application response, not a valid Codex hook
            # response; leaking it causes "invalid ... JSON output" errors.
            # Persistence has already happened in _run, so a successful hook
            # is intentionally a JSON no-op.
            _json_dump({})
        elif machine:
            _json_dump(value)
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
        return code
    except SystemExit:
        raise
    except Exception as exc:
        if args is not None and _is_codex_capture_hook(args):
            # Capture is best-effort at the host boundary.  A vault/config
            # problem must not turn an internal error payload into malformed
            # hook output or interfere with the user's Codex turn.
            _json_dump({})
            return 0
        if isinstance(exc, FeatureUnavailable):
            _json_dump(_error_payload("unavailable", str(exc)))
            return EXIT_UNAVAILABLE
        if isinstance(exc, LockError):
            _json_dump(_error_payload("lock_conflict", str(exc)))
            return EXIT_LOCK
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
