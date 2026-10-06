from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
import json
from unittest.mock import patch

from work_brain import EvidenceRetriever, ExperienceService, LocalHashEmbeddingProvider, ToolRegistry, ValidationError, Vault, new_uuid7


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

    def _commit_unassigned(self, when: str, *, title: str, tags: list[str], occurrence: dict | None = None):
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
        if occurrence is not None:
            raw["occurrence"] = occurrence
        return self.vault.commit_entry(session["session_id"], raw, refresh_projections=False)

    def _commit_context(self, when: str, *, workspace_id: str, project_id: str, title: str, summary: str | None = None, experience_id: str | None = None):
        session = self.vault.create_session(started_at=when)
        self.vault.append_turn(session["session_id"], "user", title)
        raw = payload(
            session,
            workspace_id=workspace_id,
            project_id=project_id,
            experience_id=experience_id or self.architecture["entity_id"],
            title=title,
            summary=summary or title,
            started_at=when,
            tags=["engineering"],
        )
        raw["entity_refs"] = ([{"entity_id": experience_id, "relation": "experience"}] if experience_id else [])
        return self.vault.commit_entry(session["session_id"], raw, refresh_projections=False)

    def _related_service(self) -> ExperienceService:
        self.vault.reconcile_database()
        retriever = EvidenceRetriever(self.vault, LocalHashEmbeddingProvider())
        retriever.reindex()
        return ExperienceService(self.vault, retriever=retriever)

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

    def test_related_excludes_anchor_and_returns_same_context_candidates(self) -> None:
        anchor = self._commit_context(
            "2026-10-01T10:00:00+01:00",
            workspace_id=self.workspace["entity_id"], project_id=self.project["entity_id"],
            title="Authentication migration architecture", summary="Authentication migration architecture decision",
        )
        related = self._commit_context(
            "2026-10-03T10:00:00+01:00",
            workspace_id=self.workspace["entity_id"], project_id=self.project["entity_id"],
            title="Authentication migration rollout", summary="Authentication migration rollout decision",
        )
        self._commit_context(
            "2026-10-04T10:00:00+01:00",
            workspace_id=self.workspace["entity_id"], project_id=self.project["entity_id"],
            title="Database cleanup", summary="Unrelated database cleanup",
        )

        result = self._related_service().related(anchor.entry_id, limit=5)

        self.assertEqual(anchor.entry_id, result["anchor"]["entry_id"])
        self.assertEqual(1, result["anchor"]["revision"])
        self.assertNotIn(anchor.entry_id, {item["entry_ref"]["entry_id"] for item in result["candidates"]})
        self.assertIn(related.entry_id, {item["entry_ref"]["entry_id"] for item in result["candidates"]})
        self.assertEqual("ungrouped_entry", next(item for item in result["candidates"] if item["entry_ref"]["entry_id"] == related.entry_id)["candidate_type"])

    def test_related_enforces_exact_workspace_project_tuple(self) -> None:
        other_workspace = self.vault.upsert_entity(kind="workspace", canonical_name="Personal")
        local_project = self.vault.upsert_entity(
            kind="project", canonical_name="Website", workspace_entity_id=self.workspace["entity_id"]
        )
        other_project = self.vault.upsert_entity(kind="project", canonical_name="Website", workspace_entity_id=other_workspace["entity_id"])
        other_same_project = self.vault.upsert_entity(kind="project", canonical_name="Authentication Personal")
        anchor = self._commit_context(
            "2026-10-01T10:00:00+01:00", workspace_id=self.workspace["entity_id"], project_id=local_project["entity_id"],
            title="Website migration", summary="Website migration decision",
        )
        same_context = self._commit_context(
            "2026-10-02T10:00:00+01:00", workspace_id=self.workspace["entity_id"], project_id=local_project["entity_id"],
            title="Website migration rollout", summary="Website migration rollout",
        )
        wrong_workspace = self._commit_context(
            "2026-10-03T10:00:00+01:00", workspace_id=other_workspace["entity_id"], project_id=other_project["entity_id"],
            title="Website migration rollout", summary="Website migration rollout",
        )
        wrong_project = self._commit_context(
            "2026-10-04T10:00:00+01:00", workspace_id=self.workspace["entity_id"], project_id=other_same_project["entity_id"],
            title="Authentication migration rollout", summary="Authentication migration rollout",
        )

        result = self._related_service().related(anchor.entry_id, limit=8)
        ids = {item["entry_ref"]["entry_id"] for item in result["candidates"]}
        self.assertIn(same_context.entry_id, ids)
        self.assertNotIn(wrong_workspace.entry_id, ids)
        self.assertNotIn(wrong_project.entry_id, ids)

    def test_related_exposes_experience_members_and_anchor_experience(self) -> None:
        anchor = self._commit_context(
            "2026-10-01T10:00:00+01:00", workspace_id=self.workspace["entity_id"], project_id=self.project["entity_id"],
            title="Migration architecture", experience_id=self.architecture["entity_id"],
        )
        member = self._commit_context(
            "2026-10-02T10:00:00+01:00", workspace_id=self.workspace["entity_id"], project_id=self.project["entity_id"],
            title="Migration architecture rollout", experience_id=self.architecture["entity_id"],
        )
        ungrouped = self._commit_context(
            "2026-10-03T10:00:00+01:00", workspace_id=self.workspace["entity_id"], project_id=self.project["entity_id"],
            title="Migration architecture follow-up",
        )

        result = self._related_service().related(anchor.entry_id, limit=8)
        member_result = next(item for item in result["candidates"] if item["entry_ref"]["entry_id"] == member.entry_id)
        ungrouped_result = next(item for item in result["candidates"] if item["entry_ref"]["entry_id"] == ungrouped.entry_id)
        self.assertEqual([self.architecture["entity_id"]], result["anchor"]["experience_ids"])
        self.assertEqual("experience_member", member_result["candidate_type"])
        self.assertEqual(self.architecture["entity_id"], member_result["experience"]["experience_id"])
        self.assertEqual("ungrouped_entry", ungrouped_result["candidate_type"])
        self.assertIsNone(ungrouped_result["experience"])

    def test_related_propagates_degraded_state_and_is_read_only(self) -> None:
        anchor = self._commit_context(
            "2026-10-01T10:00:00+01:00", workspace_id=self.workspace["entity_id"], project_id=self.project["entity_id"],
            title="Degraded retrieval anchor",
        )
        related = self._commit_context(
            "2026-10-02T10:00:00+01:00", workspace_id=self.workspace["entity_id"], project_id=self.project["entity_id"],
            title="Degraded retrieval continuation",
        )
        before_entries = [(entry.entry_id, entry.revision, entry.entity_refs) for entry in self.vault.all_current_entries()]
        before_entities = sorted(path.read_text(encoding="utf-8") for path in (self.vault.root / "catalog/entities").glob("*.json"))

        class DegradedRetriever:
            def search(self, query: str, *, filters: dict[str, list[str]], page_size: int) -> dict:
                self.query = query
                self.filters = filters
                self.page_size = page_size
                return {
                    "status": "degraded", "degraded_components": ["semantic"], "incomplete": True,
                    "omitted_stale_entries": 1,
                    "cards": [{"ref": {"entry_id": related.entry_id, "revision": 1}, "match": {"signals": ["lexical"], "snippets": ["continuation"]}}],
                    "embedding": {"status": "degraded"},
                }

        result = ExperienceService(self.vault, retriever=DegradedRetriever()).related(anchor.entry_id, limit=1)
        self.assertEqual("degraded", result["status"])
        self.assertTrue(result["incomplete"])
        self.assertEqual(["semantic"], result["degraded_components"])
        self.assertEqual(1, result["omitted_stale_entries"])
        self.assertEqual(1, len(result["candidates"]))
        self.assertEqual(before_entries, [(entry.entry_id, entry.revision, entry.entity_refs) for entry in self.vault.all_current_entries()])
        self.assertEqual(before_entities, sorted(path.read_text(encoding="utf-8") for path in (self.vault.root / "catalog/entities").glob("*.json")))

    def test_mine_selects_visible_current_ungrouped_entries_oldest_first(self) -> None:
        grouped = self._commit("2026-10-01T10:00:00+01:00", self.architecture, title="Already grouped", tags=["engineering"])
        older = self._commit_unassigned("2026-10-02T10:00:00+01:00", title="Older ungrouped", tags=["engineering"])
        newer = self._commit_unassigned("2026-10-03T10:00:00+01:00", title="Newer ungrouped", tags=["engineering"])

        result = self._related_service().mine(page_size=10, related_limit=1)

        self.assertEqual([older.entry_id, newer.entry_id], [item["anchor"]["entry_id"] for item in result["items"]])
        self.assertNotIn(grouped.entry_id, [item["anchor"]["entry_id"] for item in result["items"]])

    def test_mine_excludes_archived_and_quarantined_entries(self) -> None:
        archived = self._commit_unassigned("2026-09-01T10:00:00+01:00", title="Archived anchor", tags=["engineering"])
        quarantined = self._commit_unassigned("2026-09-02T10:00:00+01:00", title="Quarantined anchor", tags=["engineering"])
        visible = self._commit_unassigned("2026-09-03T10:00:00+01:00", title="Visible anchor", tags=["engineering"])
        self.vault.archive_session(archived.session_id, reason="not part of normal views")
        self.vault.quarantine_entry(quarantined.session_id, reason="fixture quarantine")

        result = self._related_service().mine(page_size=10, related_limit=1)

        self.assertEqual([visible.entry_id], [item["anchor"]["entry_id"] for item in result["items"]])

    def test_mine_uses_occurrence_then_entry_id_for_deterministic_order(self) -> None:
        occurrence_first = self._commit_unassigned(
            "2026-10-03T10:00:00+01:00",
            title="Occurrence is earlier",
            tags=["engineering"],
            occurrence={"start": "2025-01-01T00:00:00+00:00", "end": "2025-01-01T00:00:00+00:00", "precision": "instant", "label": None},
        )
        # The fixture is committed with a known occurrence by default; use a
        # separate entry with unknown occurrence to exercise the created_at
        # fallback without rewriting source after publication.
        unknown = self._commit_unassigned(
            "2025-06-01T10:00:00+01:00", title="Unknown occurrence fallback", tags=["engineering"],
            occurrence={"start": None, "end": None, "precision": "unknown", "label": None},
        )

        result = self._related_service().mine(page_size=10, related_limit=1)
        ids = [item["anchor"]["entry_id"] for item in result["items"]]
        self.assertLess(ids.index(occurrence_first.entry_id), ids.index(unknown.entry_id))
        same_time = [
            self._commit_unassigned(
                "2025-07-01T10:00:00+01:00", title=f"Tie {index}", tags=["engineering"],
                occurrence={"start": "2025-07-01T00:00:00+00:00", "end": "2025-07-01T00:00:00+00:00", "precision": "instant", "label": None},
            ) for index in range(2)
        ]
        result = self._related_service().mine(page_size=10, related_limit=1)
        tie_ids = [item["anchor"]["entry_id"] for item in result["items"] if item["anchor"]["entry_id"] in {entry.entry_id for entry in same_time}]
        self.assertEqual(sorted(tie_ids), tie_ids)

    def test_mine_keyset_cursor_survives_association_of_earlier_entries(self) -> None:
        entries = [
            self._commit_unassigned(f"2026-09-{index:02d}T10:00:00+01:00", title=f"Anchor {index}", tags=["engineering"])
            for index in range(1, 8)
        ]
        service = self._related_service()
        first = service.mine(page_size=3, related_limit=1)
        first_ids = [item["anchor"]["entry_id"] for item in first["items"]]
        self.assertEqual([entry.entry_id for entry in entries[:3]], first_ids)
        service.associate_entries(first_ids, experience_id=self.architecture["entity_id"])

        second = service.mine(page_size=3, related_limit=1, cursor=first["next_cursor"])

        self.assertEqual([entry.entry_id for entry in entries[3:6]], [item["anchor"]["entry_id"] for item in second["items"]])

    def test_mine_keyset_cursor_skips_a_future_entry_without_offset_drift(self) -> None:
        entries = [
            self._commit_unassigned(f"2026-09-{index:02d}T10:00:00+01:00", title=f"Future anchor {index}", tags=["engineering"])
            for index in range(1, 6)
        ]
        service = self._related_service()
        first = service.mine(page_size=2, related_limit=1)
        service.associate(entries[3].entry_id, experience_id=self.architecture["entity_id"])

        second = service.mine(page_size=3, related_limit=1, cursor=first["next_cursor"])

        self.assertEqual([entries[2].entry_id, entries[4].entry_id], [item["anchor"]["entry_id"] for item in second["items"]])

    def test_mine_cursor_orders_entry_id_within_same_chronology_key(self) -> None:
        entries = [
            self._commit_unassigned(
                "2026-09-01T10:00:00+01:00",
                title=f"Tie anchor {index}",
                tags=["engineering"],
            )
            for index in range(3)
        ]
        expected = sorted(entries, key=lambda entry: entry.entry_id)
        source_order = [expected[2], expected[0], expected[1]]
        service = self._related_service()

        def enumerated_in_source_order(*, include_archived: bool = False):
            return list(source_order)

        with patch.object(self.vault, "all_current_entries", side_effect=enumerated_in_source_order):
            cursor = None
            actual = []
            while True:
                result = service.mine(page_size=1, related_limit=1, cursor=cursor)
                actual.extend(item["anchor"]["entry_id"] for item in result["items"])
                cursor = result["next_cursor"]
                if cursor is None:
                    break

        self.assertEqual([entry.entry_id for entry in expected], actual)

    def test_mine_filters_and_rejects_changed_or_malformed_cursors(self) -> None:
        self._commit_unassigned("2026-10-01T10:00:00+01:00", title="Engineering anchor", tags=["engineering"])
        self._commit_unassigned("2026-10-02T10:00:00+01:00", title="Second engineering anchor", tags=["engineering"])
        self._commit_unassigned("2026-10-03T10:00:00+01:00", title="Security anchor", tags=["security"])
        other_workspace = self.vault.upsert_entity(kind="workspace", canonical_name="Personal")
        other_project = self.vault.upsert_entity(kind="project", canonical_name="Side project")
        scoped = self._commit_context(
            "2026-10-04T10:00:00+01:00", workspace_id=other_workspace["entity_id"],
            project_id=other_project["entity_id"], title="Scoped engineering anchor",
        )
        service = self._related_service()
        first = service.mine(page_size=1, related_limit=1, filters={"domain_tags": ["engineering"]})
        scoped_result = service.mine(
            page_size=5, related_limit=1,
            filters={"workspaces": [other_workspace["entity_id"]], "projects": [other_project["entity_id"]]},
        )
        self.assertEqual([scoped.entry_id], [item["anchor"]["entry_id"] for item in scoped_result["items"]])
        with self.assertRaisesRegex(ValidationError, "cursor"):
            service.mine(page_size=1, related_limit=1, cursor="not-a-cursor")
        changed = service.mine(
            page_size=1, related_limit=1, filters={"domain_tags": ["security"]}, cursor=first["next_cursor"]
        )
        self.assertEqual("cursor_expired", changed["status"])
        with self.assertRaisesRegex(ValidationError, "page_size"):
            service.mine(page_size=0)
        with self.assertRaisesRegex(ValidationError, "related_limit"):
            service.mine(related_limit=0)

    def test_mine_preserves_anchor_when_related_retrieval_is_degraded(self) -> None:
        anchor = self._commit_unassigned("2026-10-01T10:00:00+01:00", title="Degraded mining anchor", tags=["engineering"])

        class DegradedRetriever:
            def search(self, query: str, *, filters: dict[str, list[str]], page_size: int) -> dict:
                return {"status": "retrieval_unavailable", "degraded_components": ["index"], "incomplete": True, "cards": [], "embedding": {"status": "failed"}}

        result = ExperienceService(self.vault, retriever=DegradedRetriever()).mine(page_size=1, related_limit=1)

        self.assertEqual([anchor.entry_id], [item["anchor"]["entry_id"] for item in result["items"]])
        self.assertEqual("degraded", result["status"])
        self.assertTrue(result["incomplete"])
        self.assertEqual(["index"], result["degraded_components"])

    def test_mine_is_read_only_and_delegates_related_for_only_page_anchors(self) -> None:
        anchors = [
            self._commit_unassigned(f"2026-09-{index:02d}T10:00:00+01:00", title=f"Read-only {index}", tags=["engineering"])
            for index in range(1, 4)
        ]
        service = ExperienceService(self.vault)
        calls: list[str] = []

        def related(entry_id: str, *, limit: int) -> dict:
            calls.append(entry_id)
            return {"status": "ok", "anchor": {"entry_id": entry_id}, "candidates": [], "degraded_components": [], "incomplete": False}

        service.related = related  # type: ignore[method-assign]
        before_entries = [(entry.entry_id, entry.revision, entry.entity_refs) for entry in self.vault.all_current_entries()]
        before_entities = sorted(path.read_text(encoding="utf-8") for path in (self.vault.root / "catalog/entities").glob("*.json"))
        result = service.mine(page_size=2, related_limit=3)

        self.assertEqual([entry.entry_id for entry in anchors[:2]], calls)
        self.assertEqual([entry.entry_id for entry in anchors[:2]], [item["anchor"]["entry_id"] for item in result["items"]])
        self.assertEqual(before_entries, [(entry.entry_id, entry.revision, entry.entity_refs) for entry in self.vault.all_current_entries()])
        self.assertEqual(before_entities, sorted(path.read_text(encoding="utf-8") for path in (self.vault.root / "catalog/entities").glob("*.json")))

    def test_mine_cli_and_backfill_tool_return_machine_readable_batches(self) -> None:
        anchor = self._commit_unassigned("2026-10-01T10:00:00+01:00", title="CLI mining anchor", tags=["engineering"])
        self._related_service()
        from work_brain.cli import main
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, main(["--vault", str(self.vault.root), "experience", "mine", "--page-size", "1", "--related-limit", "1"]))
        value = json.loads(output.getvalue())
        self.assertEqual(anchor.entry_id, value["items"][0]["anchor"]["entry_id"])
        registry = ToolRegistry(self.vault)
        self.assertIn("get_experience_mining_batch", {tool.name for tool in registry.definitions("backfill")})
        tool_result = registry.call("get_experience_mining_batch", page_size=1, related_limit=1)
        self.assertTrue(tool_result.ok)

    def test_related_validates_limit_and_cli_returns_json(self) -> None:
        anchor = self._commit_context(
            "2026-10-01T10:00:00+01:00", workspace_id=self.workspace["entity_id"], project_id=self.project["entity_id"],
            title="CLI related anchor",
        )
        with self.assertRaisesRegex(ValidationError, "limit"):
            ExperienceService(self.vault).related(anchor.entry_id, limit=0)
        self._related_service()
        from work_brain.cli import main
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, main(["--vault", str(self.vault.root), "experience", "related", "--entry-id", anchor.entry_id, "--limit", "1"]))
        value = json.loads(output.getvalue())
        self.assertEqual(anchor.entry_id, value["anchor"]["entry_id"])
        self.assertLessEqual(len(value["candidates"]), 1)


if __name__ == "__main__":
    unittest.main()
