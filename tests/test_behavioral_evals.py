from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BehavioralEvalContractTests(unittest.TestCase):
    """Cheap transcript-contract checks for behavior owned by the host model.

    The repository does not own an LLM provider, so these fixtures deliberately
    test the durable behavioral contract and SOP coverage rather than pretending
    that a scripted response is a model-quality benchmark.
    """

    def test_transcript_fixtures_cover_the_high_value_behaviors(self) -> None:
        fixtures = json.loads((ROOT / "tests/fixtures/behavioral_scenarios.json").read_text(encoding="utf-8"))
        self.assertEqual(6, len(fixtures))
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
