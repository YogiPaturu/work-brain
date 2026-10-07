from __future__ import annotations

import json
from pathlib import Path
import unittest

from work_brain.domain import ENTRY_SECTIONS
from work_brain.instructions import SkillLoader


ROOT = Path(__file__).resolve().parents[1]


class BehavioralEvalContractTests(unittest.TestCase):
    """Cheap transcript-contract checks for behavior owned by the host model.

    The repository does not own an LLM provider, so these fixtures deliberately
    test the durable behavioral contract and SOP coverage rather than pretending
    that a scripted response is a model-quality benchmark.
    """

    def test_transcript_fixtures_cover_the_high_value_behaviors(self) -> None:
        fixtures = json.loads((ROOT / "tests/fixtures/behavioral_scenarios.json").read_text(encoding="utf-8"))
        self.assertEqual(12, len(fixtures))
        self.assertEqual({
            "think_architecture", "operate_explicit_state", "communicate_scoped_draft",
            "career_multiple_candidates", "backfill_uncertain_date", "close_day_without_new_evidence",
            "frontier_prerequisite_order", "challenge_ambiguous_ownership",
            "challenge_unsupported_causality", "resolve_external_human",
            "resolve_empirical_uncertainty", "stop_on_enough",
        }, {item["id"] for item in fixtures})
        self.assertEqual({"think", "operate", "communicate", "career", "backfill", "close-day"},
                         {item["workflow"] for item in fixtures})
        for item in fixtures:
            self.assertGreaterEqual(len(item["transcript"]), 2, item["id"])
            self.assertTrue(item["checks"], item["id"])
            self.assertTrue(all(turn["role"] in {"user", "assistant"} for turn in item["transcript"]), item["id"])

    def test_sop_text_covers_the_fixture_expectations(self) -> None:
        core = (ROOT / "skills/work-brain/references/sops/core-conversation.sop.md").read_text(encoding="utf-8")
        communicate = (ROOT / "skills/work-brain/references/sops/communicate.sop.md").read_text(encoding="utf-8")
        career = (ROOT / "skills/work-brain/references/sops/career.sop.md").read_text(encoding="utf-8")
        backfill = (ROOT / "skills/work-brain/references/sops/backfill.sop.md").read_text(encoding="utf-8")
        close_day = (ROOT / "skills/work-brain/references/sops/close-day.sop.md").read_text(encoding="utf-8")
        self.assertIn("one high-value question", core)
        self.assertIn("explicit user statement", core)
        self.assertIn("Decision:", core)
        self.assertIn("Open loop:", core)
        self.assertIn("audience and asks for a draft", communicate)
        self.assertIn("question → retrieve plausible experiences", career)
        self.assertIn("uncertain", backfill.casefold())
        self.assertIn("without manufacturing", close_day.casefold())
        self.assertIn("close-day", close_day.casefold())

    def test_core_synthesis_contract_is_present(self) -> None:
        core = (ROOT / "skills/work-brain/references/sops/core-conversation.sop.md").read_text(encoding="utf-8")
        for phrase in (
            "Established:", "Unresolved:", "Frontier:", "Explore:", "Probe:",
            "Challenge:", "Resolve:", "Reflect:", "Ambiguous ownership",
            "Unsupported causality", "Vague outcome", "Hidden assumption",
            "Missing meaningful alternative", "Prospective versus historical evidence",
            "Another person owns the missing knowledge", "inherently empirical",
            "MUST default to one high-value question at a time",
        ):
            self.assertIn(phrase.casefold(), core.casefold())

    def test_workflow_synthesis_contract_is_present(self) -> None:
        def read(name: str) -> str:
            return (ROOT / f"skills/work-brain/references/sops/{name}.sop.md").read_text(encoding="utf-8").casefold()

        think = read("think")
        operate = read("operate")
        backfill = read("backfill")
        career = read("career")
        close_day = read("close-day")
        open_day = read("open-day")
        communicate = read("communicate")
        self.assertIn("this is prospective decision mode", think)
        self.assertIn("recommendations are allowed", think)
        self.assertIn("an explicit state update is already evidence", operate)
        self.assertIn("substantive trade-off or decision", operate)
        self.assertIn("historical evidence mode", backfill)
        self.assertIn("must not offer a plausible remembered answer", backfill)
        self.assertIn("what evidence, if any, connected the incident to queue saturation at the time?", backfill)
        self.assertIn("what did you personally do, and what was done by the broader team?", backfill)
        self.assertIn("evidence problem from a presentation problem", career)
        self.assertIn("first loop is `question → answer`", career)
        self.assertIn("not a retrospective ceremony", close_day)
        self.assertIn("orientation, not a morning interview", open_day)
        self.assertIn("primarily consumes established evidence", communicate)

    def test_evidence_persistence_shape_is_unchanged(self) -> None:
        self.assertEqual((
            "context", "observations", "significance", "contribution", "reasoning",
            "evidence", "alternatives_tradeoffs", "decisions_actions", "expectations",
            "outcomes", "learning", "open_questions",
        ), ENTRY_SECTIONS)

    def test_think_loader_adds_no_primitive_resource(self) -> None:
        loaded = SkillLoader().load("think")
        self.assertEqual([
            "WORK-BRAIN-SKILL@2", "WORK-BRAIN-SOP-CORE@3", "WORK-BRAIN-SOP-THINK@3",
        ], loaded.identities)

    def test_live_experience_continuity_contract_is_bounded_and_optional(self) -> None:
        review = (ROOT / "skills/work-brain/references/experience-review.md").read_text(encoding="utf-8")
        core = (ROOT / "skills/work-brain/references/sops/core-conversation.sop.md").read_text(encoding="utf-8")
        operate = (ROOT / "skills/work-brain/references/sops/operate.sop.md").read_text(encoding="utf-8")
        tools = (ROOT / "skills/work-brain/references/tools/agent-tools.md").read_text(encoding="utf-8")
        review = " ".join(review.split())
        core = " ".join(core.split())
        operate = " ".join(operate.split())
        tools = " ".join(tools.split())

        self.assertIn("For live `think` and `operate` work", review)
        self.assertIn("only when the current bounded work plausibly continues", review)
        self.assertIn("Routine state updates", review)
        self.assertIn("resolve the exact current workspace and project context", review)
        self.assertIn("(workspace_entity_id, project_entity_id)", review)
        self.assertIn("search a compact query within that", review)
        self.assertIn("EvidenceCards and their `experiences`", review)
        self.assertIn("stable entity ID", review)
        self.assertIn("If several Experiences are plausible", review)
        self.assertIn("continuity is only topical", review)
        self.assertIn("degraded/incomplete", review)
        self.assertIn("Do not create one merely because retrieval failed", review)
        self.assertIn("Do not repair a committed entry with automatic post-commit lookup or association", review)
        self.assertIn("historical `experience mine`", review)
        self.assertIn("The opaque cursor belongs only to explicit historical", review)
        self.assertIn("open-day, operate, think, communicate, close-day", review)

        self.assertIn("MAY do", core)
        self.assertIn("Historical `experience mine` and its cursor are not part of normal live commits", core)
        self.assertIn("routine state updates do not require Experience retrieval", operate)
        self.assertIn("EvidenceCards that include existing Experience identities with stable entity IDs", tools)

    def test_think_live_continuity_does_not_require_a_committed_related_anchor(self) -> None:
        think = (ROOT / "skills/work-brain/references/sops/think.sop.md").read_text(encoding="utf-8")
        think = " ".join(think.split())
        self.assertIn("When current live work may continue a prior Experience, use bounded evidence or Experience retrieval", think)
        self.assertIn("inspect stable existing Experience identities", think)
        self.assertIn("Use `experience related` only when reviewing an existing committed anchor SessionEntry with its `entry_id`", think)
        self.assertIn("Load `references/experience-review.md` for the continuity decision", think)
        self.assertIn("Leave the work unassigned when causal or goal continuity is uncertain", think)

    def test_live_and_post_hoc_experience_confirmation_are_distinct(self) -> None:
        review = (ROOT / "skills/work-brain/references/experience-review.md").read_text(encoding="utf-8")
        review = " ".join(review.split())
        self.assertIn("Clear live continuity needs no second approval ceremony", review)
        self.assertIn("Explicit user approval remains required for post-hoc historical changes through `experience associate`", review)
        self.assertIn("normal CommitDraft publication owns the reference", review)
        self.assertIn("Do not repair a committed entry with automatic post-commit lookup or association", review)

    def test_historical_mining_remains_an_explicit_backfill_only_traversal(self) -> None:
        review = (ROOT / "skills/work-brain/references/experience-review.md").read_text(encoding="utf-8")
        review = " ".join(review.split())
        historical = review.split("## Historical mining batches", maxsplit=1)[1]
        self.assertIn("When the user explicitly asks to mine historical work", historical)
        self.assertIn("Use the returned opaque cursor for the next page", historical)
        self.assertIn("The opaque cursor belongs only to explicit historical", review)
        self.assertIn("Never use or persist it in open-day, operate, think, communicate, close-day", review)


if __name__ == "__main__":
    unittest.main()
