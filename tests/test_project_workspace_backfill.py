from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from work_brain import IntegrityError, ValidationError, Vault, new_uuid7
from work_brain.cli import main


ENTRY_SECTIONS = (
    "context", "observations", "significance", "contribution", "reasoning",
    "evidence", "alternatives_tradeoffs", "decisions_actions", "expectations",
    "outcomes", "learning", "open_questions",
)


class ProjectWorkspaceBackfillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Vault(Path(self.tempdir.name) / "vault").initialize()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _entry(self, *, project_id: str, workspace_id: str | None, started_at: str, title: str = "Historical work") -> str:
        session = self.vault.create_session(started_at=started_at, modes=["think"], domain_tags=["engineering"])
        self.vault.append_turn(session["session_id"], "user", title, recorded_at=started_at)
        sections = {name: [] for name in ENTRY_SECTIONS}
        sections["context"] = [{"text": title, "basis": "stated", "source_turns": [1]}]
        self.vault.commit_entry(session["session_id"], {
            "entry_id": session["entry_id"], "session_id": session["session_id"], "revision": 1,
            "commit_id": new_uuid7(), "created_at": started_at, "supersedes_revision": None,
            "revision_reason": "initial_commit", "provenance_kind": "contemporaneous",
            "title": title, "summary": title, "occurrence": {
                "start": started_at, "end": None, "precision": "instant", "label": None,
            }, "modes": ["think"], "domain_tags": ["engineering"], "sections": sections,
            "workspace_entity_id": workspace_id, "project_entity_id": project_id,
            "state_mutations": [], "entity_refs": [], "artifact_refs": [], "source_refs": [],
        }, refresh_projections=False)
        return session["entry_id"]

    def _legacy_project(self, name: str = "Authentication") -> dict[str, object]:
        return self.vault.upsert_entity(
            kind="project", canonical_name=name, aliases=["Auth"],
            description="A durable project", created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )

    def test_unique_workspace_evidence_allows_null_entries_and_repeated_entries(self) -> None:
        workspace = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        project = self._legacy_project()
        self._entry(project_id=project["entity_id"], workspace_id=workspace["entity_id"], started_at="2026-01-02T10:00:00+00:00")
        self._entry(project_id=project["entity_id"], workspace_id=workspace["entity_id"], started_at="2026-01-03T10:00:00+00:00")
        self._entry(project_id=project["entity_id"], workspace_id=None, started_at="2026-01-04T10:00:00+00:00")

        plan = self.vault.project_workspace_backfill_plan()

        self.assertEqual(1, plan["counts"]["assignments"])
        assignment = plan["assignments"][0]
        self.assertEqual(project["entity_id"], assignment["project_entity_id"])
        self.assertEqual(workspace["entity_id"], assignment["workspace_entity_id"])
        self.assertEqual(2, assignment["evidence_entry_count"])

    def test_multiple_workspaces_are_a_conflict_and_are_not_applied(self) -> None:
        ranq = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        personal = self.vault.upsert_entity(kind="workspace", canonical_name="Personal")
        project = self._legacy_project("Website")
        self._entry(project_id=project["entity_id"], workspace_id=ranq["entity_id"], started_at="2026-01-02T10:00:00+00:00")
        self._entry(project_id=project["entity_id"], workspace_id=personal["entity_id"], started_at="2026-01-03T10:00:00+00:00")

        plan = self.vault.project_workspace_backfill_plan()

        self.assertEqual(1, plan["counts"]["conflicts"])
        self.assertEqual(0, plan["counts"]["assignments"])
        source_project = json.loads(
            (self.vault.root / "catalog/entities" / f"{project['entity_id']}.json").read_text()
        )
        self.assertNotIn("workspace_entity_id", source_project)

    def test_no_workspace_evidence_is_unresolved_and_owned_projects_are_skipped(self) -> None:
        unresolved = self._legacy_project("No evidence")
        workspace = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        owned = self.vault.upsert_entity(
            kind="project", canonical_name="Already owned", workspace_entity_id=workspace["entity_id"]
        )

        plan = self.vault.project_workspace_backfill_plan()

        self.assertEqual(1, plan["counts"]["unresolved"])
        self.assertEqual(unresolved["entity_id"], plan["unresolved"][0]["project_entity_id"])
        all_ids = {item["project_entity_id"] for item in plan["assignments"] + plan["conflicts"] + plan["unresolved"]}
        self.assertNotIn(owned["entity_id"], all_ids)
        self.assertEqual([owned["entity_id"]], [item["project_entity_id"] for item in plan["already_owned"]])

    def test_same_name_projects_backfill_independently_by_stable_id(self) -> None:
        ranq = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        personal = self.vault.upsert_entity(kind="workspace", canonical_name="Personal")
        ranq_project = self._legacy_project("Website")
        personal_project = self._legacy_project("Website")
        self._entry(project_id=ranq_project["entity_id"], workspace_id=ranq["entity_id"], started_at="2026-01-02T10:00:00+00:00")
        self._entry(project_id=personal_project["entity_id"], workspace_id=personal["entity_id"], started_at="2026-01-03T10:00:00+00:00")

        plan = self.vault.project_workspace_backfill_plan()
        assignments = {item["project_entity_id"]: item["workspace_entity_id"] for item in plan["assignments"]}

        self.assertEqual({ranq_project["entity_id"], personal_project["entity_id"]}, set(assignments))
        self.assertEqual(ranq["entity_id"], assignments[ranq_project["entity_id"]])
        self.assertEqual(personal["entity_id"], assignments[personal_project["entity_id"]])

    def test_explicit_operation_preserves_project_metadata_and_is_idempotent(self) -> None:
        workspace = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        project = self._legacy_project()
        before_entry = self._entry(project_id=project["entity_id"], workspace_id=workspace["entity_id"], started_at="2026-01-02T10:00:00+00:00")
        entry_paths = sorted(self.vault.root.glob("sessions/*/*/*/*/entries/*.json"))
        entry_bytes = {path: path.read_bytes() for path in entry_paths}

        result = self.vault.backfill_project_workspace(project["entity_id"], workspace["entity_id"])
        updated = result["entity"]

        self.assertTrue(result["changed"])
        self.assertEqual(project["entity_id"], updated["entity_id"])
        self.assertEqual(project["canonical_name"], updated["canonical_name"])
        self.assertEqual(project["aliases"], updated["aliases"])
        self.assertEqual(project["description"], updated["description"])
        self.assertEqual(project["created_at"], updated["created_at"])
        self.assertEqual(workspace["entity_id"], updated["workspace_entity_id"])
        self.assertNotEqual(project["updated_at"], updated["updated_at"])
        self.assertEqual(entry_bytes, {path: path.read_bytes() for path in entry_paths})
        self.assertEqual(before_entry, self.vault.all_current_entries()[0].entry_id)

        second = self.vault.backfill_project_workspace(project["entity_id"], workspace["entity_id"])
        self.assertFalse(second["changed"])

    def test_invalid_explicit_operation_is_rejected(self) -> None:
        workspace = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        project = self._legacy_project()
        with self.assertRaises(ValidationError):
            self.vault.backfill_project_workspace(project["entity_id"], new_uuid7())
        with self.assertRaises(ValidationError):
            self.vault.backfill_project_workspace(workspace["entity_id"], workspace["entity_id"])
        owned = self.vault.upsert_entity(kind="project", canonical_name="Owned", workspace_entity_id=workspace["entity_id"])
        other = self.vault.upsert_entity(kind="workspace", canonical_name="Other")
        with self.assertRaisesRegex(IntegrityError, "cannot be changed"):
            self.vault.backfill_project_workspace(owned["entity_id"], other["entity_id"])

    def test_cli_dry_run_is_read_only_and_apply_refreshes_projection(self) -> None:
        workspace = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        project = self._legacy_project()
        self._entry(project_id=project["entity_id"], workspace_id=workspace["entity_id"], started_at="2026-01-02T10:00:00+00:00")
        project_path = self.vault.root / "catalog/entities" / f"{project['entity_id']}.json"
        before = project_path.read_bytes()

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(0, main(["--vault", str(self.vault.root), "backfill-project-workspaces", "--dry-run"]))
        dry_run = json.loads(output.getvalue())
        self.assertTrue(dry_run["dry_run"])
        self.assertEqual(before, project_path.read_bytes())

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(0, main(["--vault", str(self.vault.root), "backfill-project-workspaces"]))
        applied = json.loads(output.getvalue())
        self.assertEqual([project["entity_id"]], [item["project_entity_id"] for item in applied["updated"]])
        self.assertEqual("current", applied["maintenance"]["status"])
        with closing(self.vault._database().connect()) as conn:
            row = conn.execute(
                "SELECT workspace_entity_id FROM entities WHERE entity_id = ?", (project["entity_id"],)
            ).fetchone()
        self.assertEqual(workspace["entity_id"], row["workspace_entity_id"])
        self.vault.database_path.unlink()
        self.vault.rebuild_all()
        with closing(self.vault._database().connect()) as conn:
            row = conn.execute(
                "SELECT workspace_entity_id FROM entities WHERE entity_id = ?", (project["entity_id"],)
            ).fetchone()
        self.assertEqual(workspace["entity_id"], row["workspace_entity_id"])
        self.assertEqual([], self.vault.doctor())

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(0, main(["--vault", str(self.vault.root), "backfill-project-workspaces"]))
        second = json.loads(output.getvalue())
        self.assertEqual([], second["updated"])
        self.assertIn(project["entity_id"], second["unchanged"])
        self.assertEqual("not_needed", second["maintenance"]["status"])


if __name__ == "__main__":
    unittest.main()
