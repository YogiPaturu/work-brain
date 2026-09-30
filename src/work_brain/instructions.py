from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
from typing import Iterable

from .errors import ValidationError


RESOURCE_RE = re.compile(r"^([A-Z][A-Z0-9-]+)\s+v(\d+)\s*$")
WORKFLOWS = (
    "think", "operate", "communicate", "career", "open-day", "close-day", "backfill",
)
WORKFLOW_SOPS = {workflow: f"{workflow}.sop.md" for workflow in WORKFLOWS}
DOMAIN_ALIASES = {
    "eng": "engineering", "software": "engineering", "debug": "debugging",
    "product-management": "product", "customers": "customer", "bizdev": "sales",
    "exec": "leadership",
}


@dataclass(frozen=True)
class InstructionResource:
    resource_id: str
    version: int
    path: Path
    text: str

    @property
    def identity(self) -> str:
        return f"{self.resource_id}@{self.version}"


@dataclass(frozen=True)
class LoadedInstructions:
    skill: InstructionResource
    resources: tuple[InstructionResource, ...]
    missing: tuple[str, ...] = ()

    @property
    def identities(self) -> list[str]:
        return [resource.identity for resource in self.resources]

    @property
    def text(self) -> str:
        return "\n\n".join(resource.text for resource in self.resources)


class SkillLoader:
    """Loads the smallest useful public Skill/SOP/probe set for a session."""

    def __init__(self, skills_root: str | Path | None = None):
        default_candidates = [Path(__file__).resolve().parents[2] / "skills", Path.cwd() / "skills"]
        configured = skills_root or os.environ.get("WORK_BRAIN_SKILLS")
        self.skills_root = Path(configured) if configured else next(
            (candidate for candidate in default_candidates if candidate.exists()), default_candidates[0]
        )
        self.skill_dir = self.skills_root / "work-brain"

    def load(self, workflow: str, domains: Iterable[str] = ()) -> LoadedInstructions:
        if workflow not in WORKFLOWS:
            raise ValidationError(f"unknown workflow: {workflow}")
        skill = self._resource(self.skill_dir / "SKILL.md")
        resources = [skill, self._resource(self.skill_dir / "references/sops/core-conversation.sop.md")]
        resources.append(self._resource(self.skill_dir / "references/sops" / WORKFLOW_SOPS[workflow]))
        missing: list[str] = []
        seen_domains: set[str] = set()
        for raw_domain in domains:
            domain = self.normalize_domain(raw_domain)
            if domain in seen_domains:
                continue
            seen_domains.add(domain)
            probe = self.skill_dir / "references/probes" / f"{domain}.md"
            if probe.exists():
                resources.append(self._resource(probe))
            else:
                missing.append(domain)
            if len(seen_domains) == 2:
                break
        return LoadedInstructions(skill, tuple(resources), tuple(missing))

    @staticmethod
    def normalize_domain(value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError("domain must be a non-empty string")
        normalized = value.strip().casefold().replace("_", "-").replace(" ", "-")
        return DOMAIN_ALIASES.get(normalized, normalized)

    @staticmethod
    def _resource(path: Path) -> InstructionResource:
        if not path.exists():
            raise ValidationError(f"instruction resource is missing: {path}")
        text = path.read_text(encoding="utf-8")
        match = next(
            (candidate for line in text.splitlines()[:8] if line.strip()
             for candidate in (RESOURCE_RE.match(line.strip()),) if candidate),
            None,
        )
        if match is None:
            raise ValidationError(f"instruction resource has no '<ID> v<number>' header: {path}")
        return InstructionResource(match.group(1), int(match.group(2)), path, text)
