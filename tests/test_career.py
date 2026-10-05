from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from work_brain import CareerService, MarkdownQuestionBankProvider, QuestionBank, QuestionFilters, ToolRegistry, Vault, new_uuid7


def entry_payload(session: dict, *, revision: int = 1, supersedes: int | None = None, summary: str = "A conflict was resolved with new evidence.") -> dict:
    sections = {name: [] for name in (
        "context", "observations", "significance", "contribution", "reasoning", "evidence",
        "alternatives_tradeoffs", "decisions_actions", "expectations", "outcomes", "learning", "open_questions",
    )}
    sections["context"] = [{"text": "A teammate disagreed with the proposed migration.", "basis": "stated", "source_turns": [1]}]
    return {
        "entry_id": session["entry_id"], "session_id": session["session_id"], "revision": revision,
        "commit_id": new_uuid7(), "created_at": "2026-09-30T10:05:00+01:00",
        "supersedes_revision": supersedes, "revision_reason": "reextract" if revision > 1 else "initial_commit",
        "provenance_kind": "contemporaneous", "title": "Conflict resolution", "summary": summary,
        "occurrence": {"start": "2026-09-30T10:00:00+01:00", "end": "2026-09-30T10:05:00+01:00", "precision": "instant", "label": None},
        "modes": ["think"], "domain_tags": ["engineering"], "sections": sections,
        "state_mutations": [], "entity_refs": [], "artifact_refs": [], "source_refs": [],
    }


class CareerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.vault = Vault(self.root / "vault").initialize()
        self.bank_path = self.root / "questions.md"
        self.bank_path.write_text(
            "# Judgment\n"
            "- [Ambiguity] [synthetic] How did you decide when information was missing?\n"
            "- [Conflict] [synthetic] Tell me about a disagreement you resolved.\n"
            "- [technical-depth] [synthetic] Tell me about a difficult debugging problem.\n",
            encoding="utf-8",
        )
        self.bank = QuestionBank("synthetic", self.bank_path, "public_shared")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_markdown_questions_are_normalized_filtered_and_stable(self) -> None:
        provider = MarkdownQuestionBankProvider([self.bank])
        first = provider.search_questions(QuestionFilters.from_values(tags_all=["AMBIGUITY"]), limit=10)
        second = provider.search_questions(QuestionFilters.from_values(tags_all=["ambiguity"]), limit=10)
        self.assertEqual(1, len(first))
        self.assertEqual(first[0].ref, second[0].ref)
        self.assertEqual("Judgment", first[0].section)
        self.assertEqual("Ambiguity", first[0].tags[0].display)
        self.assertEqual("public_shared", first[0].source_class)
        self.assertEqual(first[0].ref, provider.choose_question(QuestionFilters.from_values(tags_all=["ambiguity"]), seed=7).ref)
        self.assertEqual([], provider.diagnostics)

    def test_questions_are_separate_from_evidence_and_need_no_model(self) -> None:
        service = CareerService(self.vault, banks=[self.bank])
        result = service.search_questions(filters=QuestionFilters.from_values(tags_all=["conflict"]))
        self.assertEqual(1, len(result["questions"]))
        self.assertEqual([], self.vault.all_current_entries())
        self.assertEqual({"search_questions", "get_question", "choose_question", "search_evidence", "hydrate_evidence", "mark_interview_candidate", "unmark_interview_candidate", "list_interview_candidates"}, {item.name for item in ToolRegistry(self.vault).definitions("career")})

    def test_prepare_pages_evidence_but_mock_does_not_reveal_it(self) -> None:
        session = self.vault.create_session(started_at="2026-09-30T10:00:00+01:00")
        self.vault.append_turn(session["session_id"], "user", "We resolved a disagreement with a teammate.")
        self.vault.commit_entry(session["session_id"], entry_payload(session))
        service = CareerService(self.vault, banks=[self.bank])
        question = service.choose_question(filters=QuestionFilters.from_values(tags_all=["conflict"]))
        prepared = service.prepare(question=question, page_size=1)
        mocked = service.mock(question=question)
        self.assertEqual("prepare", prepared["mode"])
        self.assertIn("evidence", prepared)
        self.assertTrue(prepared["selection_required"])
        self.assertEqual("mock", mocked["mode"])
        self.assertIsNone(mocked["evidence"])
        self.assertFalse(mocked["reveal_evidence_before_answer"])

    def test_candidate_mark_is_explicit_durable_and_follows_revision(self) -> None:
        session = self.vault.create_session(started_at="2026-09-30T10:00:00+01:00")
        self.vault.append_turn(session["session_id"], "user", "We resolved a disagreement with a teammate.")
        first = self.vault.commit_entry(session["session_id"], entry_payload(session))
        service = CareerService(self.vault, banks=[self.bank])
        marked = service.marks.mark(first.entry_id, note="Use the trade-off angle.")
        self.assertEqual(1, marked["entry_revision_at_event"])
        self.assertFalse(marked["idempotent"])
        same = service.marks.mark(first.entry_id, note="Use the trade-off angle.")
        self.assertTrue(same["idempotent"])
        second_payload = entry_payload(session, revision=2, supersedes=1, summary="The disagreement was resolved after testing the trade-off.")
        self.vault.commit_entry(session["session_id"], second_payload)
        current = service.marks.list()
        self.assertEqual(1, len(current))
        self.assertEqual(1, current[0]["entry_revision_at_event"])
        self.assertFalse(current[0]["orphaned"])
        removed = service.marks.unmark(first.entry_id)
        self.assertEqual("unmark", removed["action"])
        self.assertEqual([], service.marks.list())
        self.assertTrue((self.vault.root / "career/marks.jsonl").exists())

    def test_tool_cannot_create_mark_from_model_suggestion_alone(self) -> None:
        session = self.vault.create_session(started_at="2026-09-30T10:00:00+01:00")
        self.vault.append_turn(session["session_id"], "user", "A candidate story.")
        entry = self.vault.commit_entry(session["session_id"], entry_payload(session))
        registry = ToolRegistry(self.vault)
        refused = registry.call("mark_interview_candidate", entry_id=entry.entry_id, note="model thinks this is strong")
        self.assertFalse(refused.ok)
        self.assertIsNone(CareerService(self.vault).marks.get(entry.entry_id))
        accepted = registry.call("mark_interview_candidate", entry_id=entry.entry_id, note="I chose this story", explicit_user_intent=True)
        self.assertTrue(accepted.ok)

    def test_cli_can_query_a_configured_bank(self) -> None:
        from work_brain.cli import main
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, main(["--vault", str(self.vault.root), "career", "--bank", f"synthetic={self.bank_path}", "questions", "search", "--tag-all", "conflict"]))
        payload = json.loads(output.getvalue())
        self.assertEqual(1, len(payload["questions"]))


if __name__ == "__main__":
    unittest.main()
