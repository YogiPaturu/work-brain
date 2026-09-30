from __future__ import annotations

import argparse
import json
import sys

from .vault import Vault


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="work-brain")
    parser.add_argument("--vault", required=True, help="private vault path")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("rebuild")
    sub.add_parser("doctor")
    start = sub.add_parser("session-start", help="create a bounded conversation session")
    start.add_argument("--started-at")
    start.add_argument("--mode", action="append", default=[])
    start.add_argument("--domain", action="append", default=[])
    turn = sub.add_parser("turn", help="append one durable user or assistant turn")
    turn.add_argument("--session-id", required=True)
    turn.add_argument("--role", required=True, choices=["user", "assistant"])
    turn.add_argument("--content", required=True)
    turn.add_argument("--recorded-at")
    commit = sub.add_parser("commit", help="publish a resolved LLD1 SessionEntry JSON payload")
    commit.add_argument("--session-id", required=True)
    commit.add_argument("--file", required=True, help="JSON file containing the resolved SessionEntry payload")
    args = parser.parse_args(argv)
    vault = Vault(args.vault)
    if args.command == "init":
        vault.initialize()
        print(f"initialized {vault.root}")
        return 0
    if args.command == "rebuild":
        vault.rebuild_all()
        print("rebuilt projections and SQLite")
        return 0
    if args.command == "session-start":
        session = vault.create_session(started_at=args.started_at, modes=args.mode, domains=args.domain)
        print(json.dumps(session, ensure_ascii=False, indent=2))
        return 0
    if args.command == "turn":
        turn = vault.append_turn(args.session_id, args.role, args.content, recorded_at=args.recorded_at)
        print(json.dumps(turn, ensure_ascii=False, indent=2))
        return 0
    if args.command == "commit":
        with open(args.file, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        entry = vault.commit_entry(args.session_id, payload)
        print(json.dumps({"entry_id": entry.entry_id, "revision": entry.revision, "commit_id": entry.commit_id}, indent=2))
        return 0
    diagnostics = vault.doctor()
    if diagnostics:
        print("\n".join(diagnostics))
        return 1
    print("vault is healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
