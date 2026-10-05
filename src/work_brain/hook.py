"""Minimal host-hook entrypoint.

This module intentionally avoids the application CLI, retrieval, career, and
commit imports.  It is the process boundary used by installed host hooks;
``work-brain capture-hook`` remains available as a compatibility command.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .capture import HarnessCaptureService, normalize_capture_event, record_capture_hook_failure
from .capture_status import live_status, status_text
from .config import resolve_vault_path
from .vault import Vault


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="work-brain-hook")
    parser.add_argument("--vault")
    parser.add_argument("--config")
    parser.add_argument("--host", required=True, choices=("codex", "claude-code", "cursor"))
    return parser


def codex_output(vault: Vault, event: Any, result: dict[str, Any]) -> dict[str, Any]:
    """Return only fields accepted by the Codex hook protocol."""
    event_names = {
        "session_start": "SessionStart",
        "user_prompt": "UserPromptSubmit",
        "assistant_message": "Stop",
    }
    hook_event_name = event_names.get(event.kind)
    if hook_event_name is None:
        return {}
    snapshot = live_status(vault)
    if not snapshot.get("primary") and not result.get("captured"):
        return {}
    banner = status_text(snapshot, quiet=True)
    if hook_event_name == "Stop":
        return {"systemMessage": banner}
    return {
        "systemMessage": banner,
        "hookSpecificOutput": {
            "hookEventName": hook_event_name,
            "additionalContext": f"Deterministic Work Brain lifecycle status:\n{status_text(snapshot)}",
        },
    }


def process(vault: Vault, host: str, payload: dict[str, Any]) -> dict[str, Any]:
    event = normalize_capture_event(host, payload)
    result = HarnessCaptureService(vault).handle(event)
    if host == "codex":
        return {"_hook_output": codex_output(vault, event, result)}
    return result


def _record_failure(explicit_vault: str | None, config: str | None, host: str, error: Exception) -> None:
    try:
        root = resolve_vault_path(explicit_vault, config_path=config)
        record_capture_hook_failure(Vault(root), host=host, category="capture_hook_failure", error=error)
    except Exception:
        # Failure reporting must never become a second host-hook failure.
        pass


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("capture hook input must be a JSON object")
        vault = Vault(resolve_vault_path(args.vault, config_path=args.config))
        result = process(vault, args.host, payload)
        output = result.get("_hook_output", {}) if args.host == "codex" else result
        print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 0
    except Exception as exc:
        if args.host == "codex":
            _record_failure(args.vault, args.config, args.host, exc)
            print("{}")
            return 0
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
