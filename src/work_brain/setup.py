from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import shlex
import sys
import sysconfig
from typing import Any, Iterable

from .errors import IntegrityError, ValidationError
from .fsutil import atomic_replace_json, ensure_private_dir


@dataclass(frozen=True)
class HostSetup:
    name: str
    skill_relative: str
    settings_relative: str
    events: tuple[str, ...]


HOST_SETUPS = {
    "codex": HostSetup("codex", ".agents/skills/work-brain", ".codex/hooks.json", ("SessionStart", "UserPromptSubmit", "Stop", "SessionEnd", "Interrupt")),
    "claude": HostSetup("claude", ".claude/skills/work-brain", ".claude/settings.json", ("SessionStart", "UserPromptSubmit", "Stop", "SessionEnd", "Interrupt")),
    "cursor": HostSetup("cursor", ".agents/skills/work-brain", ".cursor/hooks.json", ("sessionStart", "beforeSubmitPrompt", "afterAgentResponse", "sessionEnd")),
}


@dataclass
class SetupReport:
    host: str
    skill_path: str
    settings_path: str
    changes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "skill_path": self.skill_path,
            "settings_path": self.settings_path,
            "changes": list(self.changes),
            "warnings": list(self.warnings),
        }


class HarnessSetup:
    """Idempotently exposes one canonical Skill and installs additive hooks."""

    def __init__(
        self,
        *,
        home: str | Path | None = None,
        skill_source: str | Path | None = None,
        executable: str | Path | None = None,
    ) -> None:
        self.home = Path(home).expanduser().resolve() if home else Path.home()
        self.skill_source = Path(skill_source).resolve() if skill_source else self._default_skill_source()
        if not self.skill_source.is_dir() or not (self.skill_source / "SKILL.md").exists():
            raise ValidationError(f"canonical Work Brain Skill is missing: {self.skill_source}")
        self.executable = Path(executable).resolve() if executable else self._default_executable()

    @staticmethod
    def _default_skill_source() -> Path:
        candidates = (
            # Source checkout / editable development install.
            Path(__file__).resolve().parents[2] / "skills/work-brain",
            # Wheel installs, including pipx-managed environments.
            Path(sysconfig.get_path("data")) / "share/work-brain/skills/work-brain",
        )
        for candidate in candidates:
            if candidate.is_dir() and (candidate / "SKILL.md").exists():
                return candidate
        return candidates[0]

    def _default_executable(self) -> Path | None:
        # Use the interpreter that owns the installed package so hooks can use
        # the dependency-light module entrypoint.  Searching for the generic
        # CLI here would route hooks through its much larger import graph.
        return Path(sys.executable)

    def _host(self, host: str) -> HostSetup:
        normalized = "claude" if host == "claude-code" else host
        try:
            return HOST_SETUPS[normalized]
        except KeyError as exc:
            raise ValidationError(f"unsupported setup host: {host}") from exc

    def skill_path(self, host: str) -> Path:
        return self.home / self._host(host).skill_relative

    def settings_path(self, host: str) -> Path:
        return self.home / self._host(host).settings_relative

    def hook_command(self, host: str) -> str:
        executable = self.executable or Path(sys.executable)
        python_executable = Path(sys.executable)
        if executable in {python_executable, python_executable.resolve()}:
            return shlex.join([str(executable), "-m", "work_brain.hook", "--host", "claude-code" if host == "claude" else host])
        return shlex.join([str(executable), "capture-hook", "--host", "claude-code" if host == "claude" else host])

    def _hook_item(self, host: str, command: str) -> dict[str, Any]:
        # Codex and Claude group command hooks under a hook-entry object.
        # Cursor's hooks.json uses direct command entries and a required schema
        # version at the document root.
        if host == "cursor":
            return {"type": "command", "command": command, "timeout": 30}
        return {"hooks": [{"type": "command", "command": command, "timeout": 30}]}

    def _read_settings(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise IntegrityError(f"existing harness settings are not valid JSON: {path}") from exc
        if not isinstance(value, dict):
            raise IntegrityError(f"existing harness settings must be a JSON object: {path}")
        if "hooks" in value and not isinstance(value["hooks"], dict):
            raise IntegrityError(f"existing harness hooks must be a JSON object: {path}")
        return value

    @staticmethod
    def _contains_command(group: Any, command: str) -> bool:
        if not isinstance(group, list):
            return False
        for item in group:
            if not isinstance(item, dict):
                continue
            hooks = item.get("hooks")
            if not isinstance(hooks, list):
                hooks = [item]
            for hook in hooks:
                if isinstance(hook, dict) and hook.get("type") == "command" and hook.get("command") == command:
                    return True
        return False

    @staticmethod
    def _is_capture_hook(command: Any, host: str) -> bool:
        token = "claude-code" if host == "claude" else host
        return isinstance(command, str) and command.endswith(f"capture-hook --host {token}")

    def _normalize_capture_group(self, group: list[Any], host: str, command: str) -> tuple[list[Any], bool, bool]:
        """Repair stale Work Brain entries without touching unrelated hooks."""
        normalized: list[Any] = []
        found = False
        changed = False
        for item in group:
            if not isinstance(item, dict):
                normalized.append(item)
                continue
            nested = item.get("hooks")
            if isinstance(nested, list):
                kept: list[Any] = []
                for hook in nested:
                    if isinstance(hook, dict) and self._is_capture_hook(hook.get("command"), host):
                        if found:
                            changed = True
                            continue
                        replacement = dict(hook)
                        replacement["type"] = "command"
                        replacement["command"] = command
                        kept.append(replacement)
                        found = True
                        changed = changed or replacement != hook
                    else:
                        kept.append(hook)
                if kept:
                    replacement = dict(item)
                    replacement["hooks"] = kept
                    normalized.append(replacement)
                elif nested:
                    changed = True
                continue
            if self._is_capture_hook(item.get("command"), host):
                if found:
                    changed = True
                    continue
                replacement = dict(item)
                replacement["type"] = "command"
                replacement["command"] = command
                normalized.append(replacement)
                found = True
                changed = changed or replacement != item
                continue
            normalized.append(item)
        if not found:
            normalized.append(self._hook_item(host, command))
            changed = True
        return normalized, changed, found

    def _install_hooks(self, host: str, path: Path, events: Iterable[str]) -> list[str]:
        settings = self._read_settings(path)
        hooks = settings.setdefault("hooks", {})
        if host == "cursor":
            version = settings.setdefault("version", 1)
            if version != 1:
                raise IntegrityError(f"Cursor hooks config must use version 1: {path}")
        command = self.hook_command(host)
        changes: list[str] = []
        for event in events:
            group = hooks.setdefault(event, [])
            if not isinstance(group, list):
                raise IntegrityError(f"existing hook event must contain a JSON array: {path}#{event}")
            normalized, changed, found = self._normalize_capture_group(group, host, command)
            if changed:
                hooks[event] = normalized
                changes.append(f"{'updated' if found else 'added'} {event} hook")
        if changes:
            ensure_private_dir(path.parent)
            atomic_replace_json(path, settings)
        return changes

    def _expose_skill(self, target: Path) -> str:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            if target.resolve() == self.skill_source:
                return "Skill link already points to canonical source"
            if target.resolve().is_dir() and self._same_tree(target.resolve(), self.skill_source):
                return "Skill link already matches canonical source"
            raise IntegrityError(f"refusing to replace existing Skill link: {target}")
        if target.exists():
            if target.is_dir() and self._same_tree(target, self.skill_source):
                return "Skill copy already matches canonical repository"
            raise IntegrityError(f"refusing to overwrite existing Skill path: {target}")
        target.symlink_to(self.skill_source, target_is_directory=True)
        return "linked canonical Skill"

    @staticmethod
    def _same_tree(left: Path, right: Path) -> bool:
        left_files = sorted(path.relative_to(left) for path in left.rglob("*") if path.is_file())
        right_files = sorted(path.relative_to(right) for path in right.rglob("*") if path.is_file())
        if left_files != right_files:
            return False
        return all((left / rel).read_bytes() == (right / rel).read_bytes() for rel in left_files)

    def install(self, host: str, *, check: bool = False) -> SetupReport:
        spec = self._host(host)
        target = self.home / spec.skill_relative
        settings = self.home / spec.settings_relative
        report = SetupReport(spec.name, str(target), str(settings))
        if check:
            if not target.exists() or not self._same_tree(target, self.skill_source):
                report.warnings.append(f"Skill is not exposed at {target}")
            try:
                settings_data = self._read_settings(settings)
                command = self.hook_command(host)
                for event in spec.events:
                    if not self._contains_command(settings_data.get("hooks", {}).get(event), command):
                        report.warnings.append(f"missing {event} hook")
            except IntegrityError as exc:
                report.warnings.append(str(exc))
            return report
        report.changes.append(self._expose_skill(target))
        report.changes.extend(self._install_hooks(host, settings, spec.events))
        return report
