from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
import json
from unittest.mock import patch

from work_brain import EvidenceRetriever, ExperienceService, ValidationError, Vault, new_uuid7


SECTIONS = (
    "context", "observations", "significance", "contribution", "reasoning",
    "evidence", "alternatives_tradeoffs", "decisions_actions", "expectations",
    "outcomes", "learning", "open_questions",
)


def payload(session: dict, *, workspace_id: str, project_id: str, experience_id: str, title: str, summary: str, started_at: str, tags: list[str], outcome: bool = False) -> dict:
    sections = {name: [] for name in SECTIONS}
    sections["context"] = [{"text": summary, "basis": "stated", "source_turns": [1]}]
    sections["contribution"] = [{"text": "I owned the decision analysis.", "basis": "stated", "source_turns": [1]}]
    if outcome:
        sections["outcomes"] = [{"text": "The rollout completed successfully.", "basis": "stated", "source_turns": [1]}]
    return {
        "entry_id": session["entry_id"], "session_id": session["session_id"], "revision": 1,
        "commit_id": new_uuid7(), "created_at": started_at, "supersedes_revision": None,
        "revision_reason": "initial_commit", "provenance_kind": "contemporaneous", "title": title,
        "summary": summary, "occurrence": {"start": started_at, "end": started_at, "precision": "instant", "label": None},
        "modes": ["think"], "domain_tags": tags, "workspace_entity_id": workspace_id,
        "project_entity_id": project_id, "sections": sections, "state_mutations": [],
        "entity_refs": [{"entity_id": experience_id, "relation": "experience"}],
        "artifact_refs": [], "source_refs": [],
    }


class ExperienceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Vault(Path(self.tempdir.name) / "vault").initialize()
        self.workspace = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        self.project = self.vault.upsert_entity(kind="project", canonical_name="Payments")
        self.architecture = self.vault.upsert_entity(kind="experience", canonical_name="Choosing the migration architecture")
        self.influence = self.vault.upsert_entity(kind="experience", canonical_name="Persuading the API team")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _commit(self, when: str, experience: dict, *, title: str, tags: list[str], outcome: bool = False):
        session = self.vault.create_session(started_at=when)
        self.vault.append_turn(session["session_id"], "user", title)
        return self.vault.commit_entry(
            session["session_id"],
            payload(session, workspace_id=self.workspace["entity_id"], project_id=self.project["entity_id"],
                    experience_id=experience["entity_id"], title=title, summary=title, started_at=when,
                    tags=tags, outcome=outcome),
            refresh_projections=False,
        )

    def _commit_unassigned(self, when: str, *, title: str, tags: list[str]):
        session = self.vault.create_session(started_at=when)
        self.vault.append_turn(session["session_id"], "user", title)
        raw = payload(
            session,
            workspace_id=self.workspace["entity_id"],
            project_id=self.project["entity_id"],
            experience_id=self.architecture["entity_id"],
            title=title,
            summary=title,
            started_at=when,
            tags=tags,
        )
        raw["entity_refs"] = []
        return self.vault.commit_entry(session["session_id"], raw, refresh_projections=False)

    def test_experience_spans_entries_and_keeps_stable_source_refs(self) -> None:
        first = self._commit("2026-10-01T10:00:00+01:00", self.architecture, title="Architecture options", tags=["architecture"])
        second = self._commit("2026-10-03T10:00:00+01:00", self.architecture, title="Architecture decision", tags=["authentication", "security"], outcome=True)
        card = ExperienceService(self.vault).get(self.architecture["entity_id"])
        self.assertEqual("Choosing the migration architecture", card["title"])
        self.assertEqual(2, card["entry_count"])
        self.assertEqual([first.entry_id, second.entry_id], [ref["entry_id"] for ref in card["supporting_entry_refs"]])
        self.assertEqual(["architecture", "authentication", "security"], card["domain_tags"])
        self.assertTrue(card["evidence_signals"]["outcomes"])
        self.assertEqual(first.revision, card["supporting_entry_refs"][0]["revision"])

    def test_multiple_experiences_in_one_project_remain_separate(self) -> None:
        self._commit("2026-10-01T10:00:00+01:00", self.architecture, title="Architecture", tags=["architecture"])
        self._commit("2026-10-02T10:00:00+01:00", self.influence, title="API disagreement", tags=["stakeholder-influence"])
        result = ExperienceService(self.vault).list(limit=10)
        self.assertEqual({self.architecture["entity_id"], self.influence["entity_id"]}, {item["experience_id"] for item in result["experiences"]})
        self.assertEqual({1}, {item["entry_count"] for item in result["experiences"]})

    def test_experience_association_is_optional(self) -> None:
        self._commit_unassigned("2026-10-04T10:00:00+01:00", title="Ungrouped", tags=["engineering"])
        self.assertEqual([], ExperienceService(self.vault).list()["experiences"])
        self.assertEqual([], self.vault.all_current_entries()[0].entity_refs)

    def test_batch_experience_association_updates_each_entry(self) -> None:
        first = self._commit_unassigned("2026-10-04T10:00:00+01:00", title="First ungrouped decision", tags=["engineering"])
        second = self._commit_unassigned("2026-10-04T11:00:00+01:00", title="Second ungrouped decision", tags=["security"])

        result = ExperienceService(self.vault).associate_entries(
            [first.entry_id, second.entry_id], experience_id=self.architecture["entity_id"]
        )

        self.assertEqual("committed", result["source_status"])
        self.assertEqual(2, result["count"])
        self.assertEqual("current", result["retrieval_status"])
        for entry_id in (first.entry_id, second.entry_id):
            updated = self.vault.get_current_entry(entry_id)
            self.assertEqual(2, updated.revision)
            self.assertEqual(
                [self.architecture["entity_id"]],
                [ref["entity_id"] for ref in updated.entity_refs if ref["relation"] == "experience"],
            )

    def test_hydration_accepts_only_exact_card_revisions(self) -> None:
        entry = self._commit("2026-10-01T10:00:00+01:00", self.architecture, title="Architecture", tags=["architecture"])
        service = ExperienceService(self.vault)
        with self.assertRaisesRegex(ValidationError, "must belong"):
            service.hydrate(self.architecture["entity_id"], refs=[{"entry_id": entry.entry_id, "revision": 2}])

    def test_post_hoc_association_publishes_metadata_revision_and_preserves_old_revision(self) -> None:
        session = self.vault.create_session(started_at="2026-10-04T10:00:00+01:00")
        self.vault.append_turn(session["session_id"], "user", "This was an ungrouped decision.")
        raw = payload(session, workspace_id=self.workspace["entity_id"], project_id=self.project["entity_id"], experience_id=self.architecture["entity_id"], title="Ungrouped", summary="Ungrouped", started_at="2026-10-04T10:00:00+01:00", tags=["engineering"])
        raw["entity_refs"] = []
        entry = self.vault.commit_entry(
            session["session_id"],
            raw,
            refresh_projections=False,
        )
        updated = ExperienceService(self.vault).associate(entry.entry_id, experience_id=self.architecture["entity_id"])
        self.assertEqual(2, updated["revision"])
        revisions = [item for item, _ in self.vault.all_entry_revisions() if item.entry_id == entry.entry_id]
        self.assertEqual([1, 2], [item.revision for item in revisions])
        self.assertEqual([], revisions[0].entity_refs)
        self.assertEqual([{"entity_id": self.architecture["entity_id"], "relation": "experience"}], revisions[1].entity_refs)
        self.assertEqual("metadata_backfill", revisions[1].revision_reason)

    def test_post_hoc_association_reports_source_success_when_retrieval_fails(self) -> None:
        entry = self._commit_unassigned(
            "2026-10-04T10:00:00+01:00",
            title="Association survives retrieval failure",
            tags=["engineering"],
        )

        with patch.object(EvidenceRetriever, "index_entry", side_effect=RuntimeError("index unavailable")):
            result = ExperienceService(self.vault).associate(
                entry.entry_id,
                experience_id=self.architecture["entity_id"],
            )

        self.assertEqual("committed", result["source_status"])
        self.assertEqual("failed", result["retrieval_status"])
        self.assertEqual(2, self.vault.get_current_entry(entry.entry_id).revision)

        EvidenceRetriever(self.vault).reindex()
        self.assertEqual([], self.vault.doctor())

    def test_post_hoc_association_rejects_mixed_project_context(self) -> None:
        other_project = self.vault.upsert_entity(kind="project", canonical_name="Search")
        first = self._commit("2026-10-01T10:00:00+01:00", self.architecture, title="First", tags=["architecture"])
        session = self.vault.create_session(started_at="2026-10-02T10:00:00+01:00")
        self.vault.append_turn(session["session_id"], "user", "A different project entry.")
        second_payload = payload(session, workspace_id=self.workspace["entity_id"], project_id=other_project["entity_id"], experience_id=self.architecture["entity_id"], title="Second", summary="Second", started_at="2026-10-02T10:00:00+01:00", tags=["architecture"])
        second_payload["entity_refs"] = []
        second = self.vault.commit_entry(session["session_id"], second_payload, refresh_projections=False)
        with self.assertRaisesRegex(ValidationError, "does not match"):
            ExperienceService(self.vault).associate(second.entry_id, experience_id=self.architecture["entity_id"])
        self.assertEqual([], self.vault.get_current_entry(second.entry_id).entity_refs)

    def test_cli_lists_experiences_as_machine_readable_cards(self) -> None:
        self._commit("2026-10-01T10:00:00+01:00", self.architecture, title="Architecture", tags=["architecture"])
        from work_brain.cli import main
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, main(["--vault", str(self.vault.root), "experience", "list"]))
        value = json.loads(output.getvalue())
        self.assertEqual(self.architecture["entity_id"], value["experiences"][0]["experience_id"])


if __name__ == "__main__":
    unittest.main()
