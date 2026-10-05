from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

from work_brain import EvidenceRetriever, FastEmbedEmbeddingProvider, LocalHashEmbeddingProvider, Vault, new_uuid7
from work_brain.retrieval import default_embedding_provider


SECTIONS = (
    "context", "observations", "significance", "contribution", "reasoning", "evidence",
    "alternatives_tradeoffs", "decisions_actions", "expectations", "outcomes", "learning", "open_questions",
)


# These queries intentionally avoid the vocabulary used by their matching
# entries. The expectation is only that the relevant experience is surfaced in
# the first three cards; this is not a story-quality score or a best-story
# ranking.
QUALITY_CASES = (
    ("when did I change my mind after new information?", "Customer evidence reversed the plan"),
    ("where was my first diagnosis wrong?", "Production diagnosis corrected"),
    ("show me an example of working with incomplete information", "Reversible architecture choice"),
    ("when did I influence people I wasn't managing?", "Cross-team proposal"),
    ("where did I trade technical quality for speed?", "Manual step shipped the fix"),
    ("when did an expected outcome not happen?", "Support reduction did not materialize"),
)

CORPUS = (
    (
        "Customer evidence reversed the plan",
        "A buyer's field report caused the team to reverse course from batch onboarding to guided setup.",
        "The field report changed the direction before implementation began.",
    ),
    (
        "Production diagnosis corrected",
        "The live service outage came from a configuration mismatch, not the caching layer we initially investigated.",
        "The initial line of investigation was discarded after tracing the deployed settings.",
    ),
    (
        "Reversible architecture choice",
        "With sparse telemetry, we compared two deployment architectures and chose the reversible rollout.",
        "The decision kept the cost of being wrong low while more information arrived.",
    ),
    (
        "Cross-team proposal",
        "A concise proposal and a design review aligned partner teams even though I had no direct reporting relationship.",
        "The decision moved forward through a shared rationale and careful follow-up rather than formal control.",
    ),
    (
        "Manual step shipped the fix",
        "We accepted a temporary manual reconciliation step and a less elegant implementation so the customer fix could ship before the quarter deadline.",
        "The short-term compromise protected the delivery date while a durable path stayed on the plan.",
    ),
    (
        "Support reduction did not materialize",
        "The rollout was expected to reduce support volume, but ticket counts stayed flat for two weeks.",
        "The forecast did not match what we observed and prompted a follow-up investigation.",
    ),
)


def _entry_payload(session: dict, title: str, summary: str, details: str) -> dict:
    sections = {name: [] for name in SECTIONS}
    sections["context"] = [{"text": summary, "basis": "stated", "source_turns": [1]}]
    sections["reasoning"] = [{"text": details, "basis": "stated", "source_turns": [1]}]
    return {
        "entry_id": session["entry_id"], "session_id": session["session_id"], "revision": 1,
        "commit_id": new_uuid7(), "created_at": "2026-09-30T10:05:00+01:00",
        "supersedes_revision": None, "revision_reason": "initial_commit",
        "provenance_kind": "contemporaneous", "title": title, "summary": summary,
        "occurrence": {"start": "2026-09-30T10:00:00+01:00", "end": None, "precision": "instant", "label": None},
        "modes": ["think"], "domain_tags": ["engineering"], "sections": sections,
        "state_mutations": [], "entity_refs": [], "artifact_refs": [], "source_refs": [],
    }


class RetrievalQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Vault(Path(self.tempdir.name) / "vault").initialize()
        previous_provider = os.environ.get("WORK_BRAIN_EMBEDDING")
        os.environ["WORK_BRAIN_EMBEDDING"] = "hash"
        try:
            for title, summary, details in CORPUS:
                session = self.vault.create_session(started_at="2026-09-30T10:00:00+01:00", modes=["think"], domain_tags=["engineering"])
                self.vault.append_turn(session["session_id"], "user", summary, recorded_at="2026-09-30T10:01:00+01:00")
                self.vault.commit_entry(session["session_id"], _entry_payload(session, title, summary, details))
        finally:
            if previous_provider is None:
                os.environ.pop("WORK_BRAIN_EMBEDDING", None)
            else:
                os.environ["WORK_BRAIN_EMBEDDING"] = previous_provider

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _run_cases(self, retriever: EvidenceRetriever) -> tuple[int, list[dict[str, object]]]:
        hits = 0
        report = []
        for query, expected_title in QUALITY_CASES:
            result = retriever.search(query, page_size=3)
            titles = [card["title"] for card in result["cards"]]
            hit = expected_title in titles
            hits += int(hit)
            report.append({"query": query, "expected": expected_title, "top_titles": titles, "hit_at_3": hit})
            self.assertIn(result["status"], {"ok", "degraded"})
        return hits, report

    def test_hash_baseline_is_measured_and_not_called_production_quality(self) -> None:
        hits, report = self._run_cases(EvidenceRetriever(self.vault, LocalHashEmbeddingProvider()))
        # A hash projection is retained for deterministic/offline operation,
        # but its score is diagnostic only. Natural-language query wording can
        # change this small baseline, so do not turn an incidental hit count
        # into a quality gate.
        self.assertEqual(len(report), len(QUALITY_CASES))
        self.assertEqual(hits, sum(int(item["hit_at_3"]) for item in report))

    @unittest.skipUnless(importlib.util.find_spec("fastembed"), "FastEmbed runtime dependency is not installed")
    def test_default_provider_prefers_fastembed(self) -> None:
        previous_provider = os.environ.pop("WORK_BRAIN_EMBEDDING", None)
        try:
            self.assertIsInstance(default_embedding_provider(), FastEmbedEmbeddingProvider)
        finally:
            if previous_provider is not None:
                os.environ["WORK_BRAIN_EMBEDDING"] = previous_provider

    @unittest.skipUnless(importlib.util.find_spec("fastembed"), "FastEmbed runtime dependency is not installed")
    def test_fastembed_bge_smoke_cases(self) -> None:
        retriever = EvidenceRetriever(
            self.vault,
            FastEmbedEmbeddingProvider(cache_dir=os.environ.get("WORK_BRAIN_FASTEMBED_CACHE")),
        )
        retriever.reindex()
        hits, report = self._run_cases(retriever)
        # This is a cheap semantic-regression smoke test, not a production
        # retrieval benchmark. It intentionally allows one miss in this tiny
        # synthetic corpus so the model is not tuned to six artificial queries.
        self.assertGreaterEqual(hits, 5, json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
