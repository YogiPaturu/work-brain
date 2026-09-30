from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .domain import ENTRY_SECTIONS, SessionEntry
from .fsutil import atomic_replace_json
from .timeutil import parse_timestamp


def _apply_mutation(items: dict[str, dict[str, Any]], entry: SessionEntry, mutation: Any) -> None:
    fields = dict(mutation.fields)
    item_id = mutation.state_item_id
    if mutation.operation == "create":
        if item_id in items:
            raise ValueError(f"state item already exists: {item_id}")
        status = fields.get("status", "active")
        if status not in {"active", "waiting", "done", "dropped"}:
            raise ValueError(f"invalid state status: {status}")
        now = fields.get("updated_at", entry.created_at)
        item = {
            "state_item_id": item_id,
            "kind": mutation.kind,
            "title": fields["title"],
            "status": status,
            "project_entity_id": fields.get("project_entity_id"),
            "details": fields.get("details"),
            "next_action": fields.get("next_action"),
            "waiting_on": fields.get("waiting_on"),
            "due_at": fields.get("due_at"),
            "opened_at": fields.get("opened_at", entry.created_at),
            "updated_at": now,
            "closed_at": fields.get("closed_at") if status in {"done", "dropped"} else None,
            "last_source_entry_id": entry.entry_id,
        }
        parse_timestamp(item["opened_at"], "state.opened_at")
        parse_timestamp(item["updated_at"], "state.updated_at")
        items[item_id] = item
        return
    if item_id not in items:
        raise ValueError(f"state item does not exist: {item_id}")
    item = dict(items[item_id])
    if mutation.operation == "update":
        if mutation.kind is not None and mutation.kind != item["kind"]:
            raise ValueError("state item kind cannot change")
        for key, value in fields.items():
            if key not in {"title", "status", "project_entity_id", "details", "next_action", "waiting_on", "due_at", "updated_at", "closed_at"}:
                raise ValueError(f"unsupported state update field: {key}")
            item[key] = value
        if item["status"] not in {"active", "waiting", "done", "dropped"}:
            raise ValueError("invalid state status")
    elif mutation.operation == "close":
        item["status"] = fields.get("status", "done")
        if item["status"] not in {"done", "dropped"}:
            raise ValueError("close status must be done or dropped")
        item["closed_at"] = fields.get("closed_at", entry.created_at)
    elif mutation.operation == "reopen":
        item["status"] = fields.get("status", "active")
        if item["status"] not in {"active", "waiting"}:
            raise ValueError("reopen status must be active or waiting")
        item["closed_at"] = None
    item["updated_at"] = fields.get("updated_at", entry.created_at)
    item["last_source_entry_id"] = entry.entry_id
    parse_timestamp(item["updated_at"], "state.updated_at")
    if item.get("closed_at") is not None:
        parse_timestamp(item["closed_at"], "state.closed_at")
    items[item_id] = item


def rebuild_state(entries: Iterable[SessionEntry], path: Path) -> dict[str, Any]:
    items: dict[str, dict[str, Any]] = {}
    ordered = sorted(entries, key=lambda entry: (entry.created_at, entry.entry_id))
    for entry in ordered:
        for mutation in entry.state_mutations:
            _apply_mutation(items, entry, mutation)
    result = {"items": sorted(items.values(), key=lambda item: item["state_item_id"])}
    atomic_replace_json(path, result)
    return result


def journal_text(date: str, sessions: list[dict[str, Any]], entries_by_id: dict[str, SessionEntry]) -> str:
    ordered = sorted(
        (session for session in sessions if session["local_date"] == date),
        key=lambda session: (session["started_at"], session["entry_id"]),
    )
    lines = [f"# {date}", ""]
    for session in ordered:
        entry = entries_by_id.get(session["entry_id"])
        if entry is None:
            continue
        time = parse_timestamp(session["started_at"]).strftime("%H:%M")
        lines.extend([f"## {time} — {entry.title}", f"<!-- entry_id: {entry.entry_id}; revision: {entry.revision} -->", ""])
        if entry.summary:
            lines.extend(["### Summary", entry.summary, ""])
        for section in ENTRY_SECTIONS:
            statements = entry.sections[section]
            if not statements:
                continue
            heading = section.replace("_", " ").title()
            lines.extend([f"### {heading}"])
            for statement in statements:
                prefix = "[inferred] " if statement.basis == "inferred" else ""
                lines.append(f"- {prefix}{statement.text}")
            lines.append("")
        if entry.state_mutations:
            lines.extend(["### Current State / Next", ""])
            for mutation in entry.state_mutations:
                title = mutation.fields.get("title", mutation.state_item_id)
                lines.append(f"- {mutation.operation}: {title}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_journal(date: str, sessions: list[dict[str, Any]], entries_by_id: dict[str, SessionEntry], path: Path) -> str:
    text = journal_text(date, sessions, entries_by_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    from .fsutil import atomic_replace_bytes
    atomic_replace_bytes(path, text.encode("utf-8"))
    return text
