from __future__ import annotations

from contextlib import closing
import json
import tempfile
import unittest
from pathlib import Path

from work_brain import IntegrityError, PersistenceError, Vault, new_uuid7


def entry_payload(session: dict, *, commit_id: str | None = None, reason: str = "initial_commit", revision: int = 1, supersedes: int | None = None) -> dict:
    sections = {name: [] for name in (
        "context", "observations", "significance", "contribution", "reasoning", "evidence",
        "alternatives_tradeoffs", "decisions_actions", "expectations", "outcomes", "learning", "open_questions",
    )}
    sections["context"] = [{"text": "The import path was unreliable.", "basis": "stated", "source_turns": [1]}]
    return {
        "entry_id": session["entry_id"], "session_id": session["session_id"], "revision": revision,
        "commit_id": commit_id or new_uuid7(), "created_at": "2026-09-30T10:05:00+01:00",
        "supersedes_revision": supersedes, "revision_reason": reason, "provenance_kind": "contemporaneous",
        "title": "Import reliability", "summary": "Investigated an unreliable import path.",
        "occurrence": {"start": "2026-09-30T10:00:00+01:00", "end": "2026-09-30T10:05:00+01:00", "precision": "instant", "label": None},
        "modes": ["think"], "domains": ["engineering"], "sections": sections,
        "state_mutations": [], "entity_refs": [], "artifact_refs": [], "source_refs": [],
    }


class VaultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Vault(Path(self.tempdir.name) / "career-vault").initialize()
        self.session = self.vault.create_session(started_at="2026-09-30T10:00:00+01:00", modes=["think"], domains=["engineering"])

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_turn_append_retry_and_middle_corruption(self) -> None:
        turn_id = new_uuid7()
        first = self.vault.append_turn(self.session["session_id"], "user", "hello", turn_id=turn_id, recorded_at="2026-09-30T10:01:00+01:00")
        self.assertEqual(first, self.vault.append_turn(self.session["session_id"], "user", "hello", turn_id=turn_id, sequence=1, recorded_at="2026-09-30T10:01:00+01:00"))
        self.vault.append_turn(self.session["session_id"], "assistant", "What matters?", recorded_at="2026-09-30T10:02:00+01:00")
        self.assertEqual(2, len(self.vault.list_turns(self.session["session_id"])))
        turns_path = self.vault.session_dir(self.session["session_id"]) / "turns.jsonl"
        turns_path.write_text(turns_path.read_text() + '{"broken":', encoding="utf-8")
        self.assertEqual(2, len(self.vault.list_turns(self.session["session_id"])))
        turns_path.write_text(turns_path.read_text() + "not-json\n", encoding="utf-8")
        with self.assertRaises(IntegrityError):
            self.vault.list_turns(self.session["session_id"])

    def test_revision_history_correction_and_rebuildable_projections(self) -> None:
        self.vault.append_turn(self.session["session_id"], "user", "The import path is unreliable.", recorded_at="2026-09-30T10:01:00+01:00")
        payload = entry_payload(self.session)
        entry = self.vault.commit_entry(self.session["session_id"], payload)
        self.assertEqual(1, entry.revision)
        retry = self.vault.commit_entry(self.session["session_id"], payload)
        self.assertEqual(entry.commit_id, retry.commit_id)
        second_payload = entry_payload(self.session, reason="reextract", revision=2, supersedes=1)
        second_payload["commit_id"] = new_uuid7()
        second_payload["summary"] = "Re-extracted the same investigation with clearer context."
        self.vault.commit_entry(self.session["session_id"], second_payload)
        revisions = self.vault.all_entry_revisions()
        self.assertEqual([1, 2], [item.revision for item, _ in revisions])
        journal = self.vault.root / "journal/2026/09/2026-09-30.md"
        self.assertIn("revision: 2", journal.read_text())
        state = self.vault.root / "state/current.json"
        database = self.vault.database_path
        journal.unlink()
        state.unlink()
        database.unlink()
        self.vault.rebuild_all()
        self.assertTrue(journal.exists())
        self.assertTrue(state.exists())
        self.assertTrue(database.exists())
        self.assertEqual([], self.vault.doctor())

    def test_entity_artifact_and_state_are_materialized(self) -> None:
        entity = self.vault.upsert_entity(kind="project", canonical_name="Work Brain")
        artifact = self.vault.upsert_artifact(kind="url", label="Design", locator="https://example.test/design")
        self.vault.append_turn(self.session["session_id"], "user", "I will run the design experiment.", recorded_at="2026-09-30T10:01:00+01:00")
        mutation_id, state_id = new_uuid7(), new_uuid7()
        payload = entry_payload(self.session)
        payload["entity_refs"] = [{"entity_id": entity["entity_id"], "relation": "project"}]
        payload["artifact_refs"] = [{"artifact_id": artifact["artifact_id"], "relation": "supports"}]
        payload["state_mutations"] = [{"mutation_id": mutation_id, "operation": "create", "state_item_id": state_id, "kind": "task", "fields": {"title": "Run design experiment", "project_entity_id": entity["entity_id"], "next_action": "Run it"}, "source_turns": [1]}]
        self.vault.commit_entry(self.session["session_id"], payload)
        state = json.loads((self.vault.root / "state/current.json").read_text())
        self.assertEqual(state_id, state["items"][0]["state_item_id"])
        with closing(self.vault._database().connect()) as conn:
            self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM entry_artifacts").fetchone()[0])
            self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM state_items").fetchone()[0])

    def test_reconstructed_entry_and_amendment(self) -> None:
        amendment = self.vault.create_amendment(target_kind="entry", target_id=self.session["entry_id"], statement="The original estimate was corrected.", source_session_id=self.session["session_id"])
        self.assertTrue(list((self.vault.root / "amendments").rglob(f"{amendment['amendment_id']}.json")))
        self.vault.append_turn(self.session["session_id"], "user", "This is a historical backfill.", recorded_at="2026-09-30T10:01:00+01:00")
        payload = entry_payload(self.session)
        payload["provenance_kind"] = "reconstructed"
        first = self.vault.commit_entry(self.session["session_id"], payload)
        corrected = self.vault.apply_amendment(amendment["amendment_id"])
        self.assertEqual("reconstructed", first.provenance_kind)
        self.assertEqual("user_correction", corrected.revision_reason)
        self.assertEqual(2, corrected.revision)
        self.assertIn(amendment["amendment_id"], {ref["id"] for ref in corrected.source_refs})

    def test_source_commit_survives_derived_failure(self) -> None:
        self.vault.append_turn(self.session["session_id"], "user", "Capture before projection failure.", recorded_at="2026-09-30T10:01:00+01:00")
        payload = entry_payload(self.session)
        original = self.vault.reconcile_database
        self.vault.reconcile_database = lambda: (_ for _ in ()).throw(RuntimeError("simulated SQLite failure"))
        with self.assertRaises(PersistenceError):
            self.vault.commit_entry(self.session["session_id"], payload)
        self.vault.reconcile_database = original
        self.assertEqual(1, len(self.vault.all_entry_revisions()))

    def test_single_writer_lock(self) -> None:
        from work_brain.lock import VaultLock
        first = VaultLock(self.vault.root / ".vault.write.lock")
        second = VaultLock(self.vault.root / ".vault.write.lock")
        first.acquire()
        try:
            with self.assertRaises(Exception):
                second.acquire()
        finally:
            first.release()

    def test_dependency_hooks_and_explicit_deletion(self) -> None:
        events: list[tuple[str, str]] = []
        hook_vault = Vault(Path(self.tempdir.name) / "hook-vault", dependency_change_hook=lambda kind, value: events.append((kind, value)))
        hook_vault.initialize()
        entity = hook_vault.upsert_entity(kind="project", canonical_name="Hooks")
        artifact = hook_vault.upsert_artifact(kind="url", label="Hook target", locator="https://example.test/hook")
        self.assertEqual({"entity", "artifact"}, {kind for kind, _ in events})
        self.assertIn(entity["entity_id"], {value for _, value in events})
        self.assertIn(artifact["artifact_id"], {value for _, value in events})
        self.vault.append_turn(self.session["session_id"], "user", "Delete this synthetic session.", recorded_at="2026-09-30T10:01:00+01:00")
        self.vault.commit_entry(self.session["session_id"], entry_payload(self.session))
        self.vault.delete_session(self.session["session_id"], complete_removal=True)
        self.assertEqual([], self.vault.all_sessions())
        self.assertFalse((self.vault.root / "state/current.json").read_text().find(self.session["entry_id"]) >= 0)

    def test_quarantine_preserves_raw_turns_and_hides_entry(self) -> None:
        self.vault.append_turn(self.session["session_id"], "user", "This raw evidence must remain.", recorded_at="2026-09-30T10:01:00+01:00")
        self.vault.commit_entry(self.session["session_id"], entry_payload(self.session))
        self.vault.quarantine_entry(self.session["session_id"], reason="synthetic assistant-only capture")
        self.assertEqual([], self.vault.all_current_entries())
        self.assertEqual("This raw evidence must remain.", self.vault.list_turns(self.session["session_id"])[0]["content"])
        self.assertTrue((self.vault.root / "quarantine/entries/2026-09-30" / self.session["session_id"] / "0001.json").exists())


if __name__ == "__main__":
    unittest.main()
