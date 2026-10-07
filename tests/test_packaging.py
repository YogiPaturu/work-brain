from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from work_brain.instructions import SkillLoader


ROOT = Path(__file__).resolve().parents[1]


class DistributionResourceTests(unittest.TestCase):
    def test_built_wheel_contains_runtime_migrations_and_skill_resources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheel_dir = Path(temporary)
            subprocess.run(
                [sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(wheel_dir), str(ROOT)],
                check=True,
                capture_output=True,
                text=True,
            )
            wheel_path = next(wheel_dir.glob("work_brain-*.whl"))

            with zipfile.ZipFile(wheel_path) as wheel:
                names = wheel.namelist()
                installed_files = {
                    name.split(".data/data/", 1)[1]
                    for name in names
                    if ".data/data/" in name
                }

            migration_names = {path.name for path in (ROOT / "migrations").glob("*.sql")}
            self.assertTrue(migration_names)
            self.assertTrue({f"share/work-brain/migrations/{name}" for name in migration_names} <= installed_files)
            required_resources = {
                "share/work-brain/skills/work-brain/SKILL.md",
                "share/work-brain/skills/work-brain/agents/openai.yaml",
                "share/work-brain/skills/work-brain/references/sops/core-conversation.sop.md",
                "share/work-brain/skills/work-brain/references/sops/think.sop.md",
                "share/work-brain/skills/work-brain/references/sops/backfill.sop.md",
                "share/work-brain/skills/work-brain/references/experience-review.md",
                "share/work-brain/skills/work-brain/references/schemas/commit-draft.md",
                "share/work-brain/skills/work-brain/references/probes/engineering.md",
                "share/work-brain/skills/work-brain/references/tools/agent-tools.md",
                "share/work-brain/skills/work-brain/references/tools/work-brain-cli.md",
            }
            self.assertTrue(required_resources <= installed_files)

    def test_loader_finds_skill_from_installed_data_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            prefix = Path(temporary)
            installed_skills = prefix / "share/work-brain/skills"
            installed_skills.mkdir(parents=True)
            source_skill = ROOT / "skills/work-brain"
            import shutil
            shutil.copytree(source_skill, installed_skills / "work-brain")
            empty_cwd = prefix / "empty"
            empty_cwd.mkdir()
            fake_module = prefix / "lib/python/site-packages/work_brain/instructions.py"
            with (
                patch("work_brain.instructions.__file__", str(fake_module)),
                patch("work_brain.instructions.Path.cwd", return_value=empty_cwd),
                patch("work_brain.instructions.sysconfig.get_path", return_value=str(prefix)),
            ):
                think = SkillLoader().load("think")
                backfill = SkillLoader().load("backfill")
                committing = SkillLoader().load("think", include_commit_schema=True)

            self.assertEqual("WORK-BRAIN-SKILL", think.skill.resource_id)
            self.assertTrue(any(resource.path.name == "think.sop.md" for resource in think.resources))
            self.assertTrue(any(resource.path.name == "backfill.sop.md" for resource in backfill.resources))
            self.assertTrue(any(resource.path.name == "commit-draft.md" for resource in committing.resources))


if __name__ == "__main__":
    unittest.main()
