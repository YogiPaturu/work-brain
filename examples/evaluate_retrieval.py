"""Report recall@3 and recall@5 on the checked-in synthetic evaluation fixture.

This is deliberately report-only. The fixture is large enough to expose
confusion between plausible entries, but it is not a production benchmark or a
quality threshold. The six-case unittest remains the cheap regression smoke
test.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from work_brain import EvidenceRetriever, FastEmbedEmbeddingProvider, LocalHashEmbeddingProvider, Vault, new_uuid7


SECTIONS = (
    "context", "observations", "significance", "contribution", "reasoning", "evidence",
    "alternatives_tradeoffs", "decisions_actions", "expectations", "outcomes", "learning", "open_questions",
)


def _payload(session: dict, item: dict) -> dict:
    sections = {name: [] for name in SECTIONS}
    sections["context"] = [{"text": item["summary"], "basis": "stated", "source_turns": [1]}]
    sections["reasoning"] = [{"text": item["details"], "basis": "stated", "source_turns": [1]}]
    return {
        "entry_id": session["entry_id"], "session_id": session["session_id"], "revision": 1,
        "commit_id": new_uuid7(), "created_at": "2026-09-30T10:05:00+01:00",
        "supersedes_revision": None, "revision_reason": "initial_commit",
        "provenance_kind": "contemporaneous", "title": item["title"], "summary": item["summary"],
        "occurrence": {"start": "2026-09-30T10:00:00+01:00", "end": None, "precision": "instant", "label": None},
        "modes": item["modes"], "domains": item["domains"], "sections": sections,
        "state_mutations": [], "entity_refs": [], "artifact_refs": [], "source_refs": [],
    }


def _provider(name: str):
    if name == "hash":
        return LocalHashEmbeddingProvider()
    if name == "fastembed":
        return FastEmbedEmbeddingProvider(cache_dir=os.environ.get("WORK_BRAIN_FASTEMBED_CACHE"))
    return None


def evaluate(fixture: dict, embedding: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="work-brain-retrieval-eval-") as temporary:
        vault = Vault(Path(temporary) / "vault").initialize()
        for item in fixture["entries"]:
            session = vault.create_session(started_at="2026-09-30T10:00:00+01:00", modes=item["modes"], domains=item["domains"])
            vault.append_turn(session["session_id"], "user", item["summary"], recorded_at="2026-09-30T10:01:00+01:00")
            vault.commit_entry(session["session_id"], _payload(session, item))
        retriever = EvidenceRetriever(vault, _provider(embedding))
        retriever.reindex()
        cases = []
        totals = {"recall_at_3": 0.0, "recall_at_5": 0.0}
        for case in fixture["queries"]:
            relevant = set(case["relevant_titles"])
            result = retriever.search(case["query"], page_size=5)
            titles = [card["title"] for card in result["cards"]]
            recall = {}
            for k in (3, 5):
                recall[f"recall_at_{k}"] = len(relevant.intersection(titles[:k])) / len(relevant)
                totals[f"recall_at_{k}"] += recall[f"recall_at_{k}"]
            cases.append({"query": case["query"], "relevant": sorted(relevant), "top_titles": titles, **recall})
        count = len(cases)
        return {
            "embedding": embedding,
            "entries": len(fixture["entries"]),
            "queries": count,
            "mean_recall_at_3": round(totals["recall_at_3"] / count, 4),
            "mean_recall_at_5": round(totals["recall_at_5"] / count, 4),
            "cases": cases,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--embedding", choices=("auto", "hash", "fastembed"), default="auto")
    parser.add_argument("--fixture", default=str(Path(__file__).with_name("retrieval_evaluation.json")))
    args = parser.parse_args()
    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    print(json.dumps(evaluate(fixture, args.embedding), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
