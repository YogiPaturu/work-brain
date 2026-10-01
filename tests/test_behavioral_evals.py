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


if __name__ == "__main__":
    unittest.main()
