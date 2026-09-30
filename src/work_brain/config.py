from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from .errors import IntegrityError, ValidationError
from .fsutil import atomic_replace_json, ensure_private_dir, ensure_private_file


def default_config_path() -> Path:
    configured = os.environ.get("XDG_CONFIG_HOME")
    base = Path(configured).expanduser() if configured else Path.home() / ".config"
    return base / "work-brain" / "config.json"


def read_config(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path).expanduser() if path else default_config_path()
    if not target.exists():
        return {}
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IntegrityError(f"invalid Work Brain configuration: {target}") from exc
    if not isinstance(value, dict):
        raise IntegrityError(f"Work Brain configuration must be a JSON object: {target}")
    return value


def write_config(value: Mapping[str, Any], path: str | Path | None = None) -> Path:
    target = Path(path).expanduser() if path else default_config_path()
    ensure_private_dir(target.parent)
    atomic_replace_json(target, dict(value))
    ensure_private_file(target)
    return target


def set_vault_path(vault: str | Path, path: str | Path | None = None) -> Path:
    candidate = Path(vault).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = candidate.resolve()
    current = read_config(path)
    current["vault"] = str(candidate)
    write_config(current, path)
    return candidate


def resolve_vault_path(
    explicit: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    config_path: str | Path | None = None,
) -> Path:
    env = environ if environ is not None else os.environ
    raw = explicit or env.get("WORK_BRAIN_VAULT")
    if raw is None:
        configured = read_config(config_path).get("vault")
        raw = configured if isinstance(configured, str) else None
    if not isinstance(raw, (str, Path)) or not str(raw).strip():
        raise ValidationError(
            "private vault path is required; pass --vault, set WORK_BRAIN_VAULT, "
            "or configure work-brain with `work-brain config set-vault PATH`"
        )
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate.resolve()
