from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from work_brain import ExperienceService, Vault, new_uuid7


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
        session = self.vault.create_session(started_at="2026-10-04T10:00:00+01:00")
        self.vault.append_turn(session["session_id"], "user", "An ungrouped decision remains valid evidence.")
        raw = payload(session, workspace_id=self.workspace["entity_id"], project_id=self.project["entity_id"], experience_id=self.architecture["entity_id"], title="Ungrouped", summary="Ungrouped", started_at="2026-10-04T10:00:00+01:00", tags=["engineering"])
        raw["entity_refs"] = []
        self.vault.commit_entry(session["session_id"], raw, refresh_projections=False)
        self.assertEqual([], ExperienceService(self.vault).list()["experiences"])
        self.assertEqual([], self.vault.all_current_entries()[0].entity_refs)


if __name__ == "__main__":
    unittest.main()
