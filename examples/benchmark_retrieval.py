"""Measure separate-process and cache-warm retrieval latency on a private vault.

This is intentionally a small diagnostic harness, not a performance gate. It
prints JSON so results can be saved locally without putting personal queries or
vault data into the repository.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from work_brain import CommitResolver, EvidenceRetriever, FastEmbedEmbeddingProvider, LocalHashEmbeddingProvider, Vault
from work_brain.domain import ENTRY_SECTIONS


SYNTHETIC_CASES = (
    ("Import reliability", "Investigated an unreliable import path and isolated the failure boundary."),
    ("Guided onboarding", "A customer field report led the team to replace batch onboarding with guided setup."),
    ("Queue operations", "Reduced operational risk by making retries and idempotency explicit in the queue worker."),
    ("Access control", "Separated authentication from authorization so security policy changes stay reviewable."),
    ("Hiring loop", "Improved the engineering hiring loop by using a consistent evidence-based rubric."),
    ("Pricing experiment", "Ran a pricing experiment and used customer interviews to narrow the next test."),
)


def _milliseconds(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)


def _provider(name: str):
    if name == "hash":
        return LocalHashEmbeddingProvider()
    if name == "fastembed":
        return FastEmbedEmbeddingProvider(cache_dir=os.environ.get("WORK_BRAIN_FASTEMBED_CACHE"))
    return None


def _synthetic_draft(title: str, summary: str) -> dict:
    sections = {name: [] for name in ENTRY_SECTIONS}
    sections["context"] = [{"text": summary, "basis": "stated", "source_turns": [1]}]
    sections["reasoning"] = [{"text": f"Reasoning for {title}.", "basis": "stated", "source_turns": [1]}]
    return {
        "title": title,
        "summary": summary,
        "domain_tags": ["engineering"],
        "workspace": "Synthetic benchmark",
        "project": "Retrieval benchmark",
        "sections": sections,
        "state_changes": [],
        "entity_candidates": [],
        "artifact_candidates": [],
        "source_entry_refs": [],
    }


def _build_synthetic_vault(root: Path) -> None:
    vault = Vault(root).initialize()
    resolver = CommitResolver(vault)
    for index, (title, summary) in enumerate(SYNTHETIC_CASES, start=1):
        session = vault.create_session(started_at=f"2026-01-{index:02d}T10:00:00+00:00", modes=["think"], domain_tags=["engineering"])
        vault.append_turn(session["session_id"], "user", summary, recorded_at=f"2026-01-{index:02d}T10:01:00+00:00")
        resolver.publish_result(session["session_id"], _synthetic_draft(title, summary), workflow="think")
    EvidenceRetriever(vault, LocalHashEmbeddingProvider()).reindex()


def _single(vault: str, query: str, embedding: str) -> None:
    start = time.perf_counter()
    result = EvidenceRetriever(Vault(vault).initialize(), _provider(embedding)).search(query)
    print(json.dumps({"embedding": embedding, "latency_ms": _milliseconds(start), "status": result["status"], "cards": len(result["cards"])}, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault")
    parser.add_argument("--synthetic", action="store_true", help="build a disposable six-entry fixture instead of using a vault")
    parser.add_argument("--query", default="import reliability")
    parser.add_argument("--embedding", choices=("auto", "hash", "fastembed"), default="auto")
    parser.add_argument("--single", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.vault and not args.synthetic:
        parser.error("--vault is required unless --synthetic is used")
    if args.single:
        _single(args.vault, args.query, args.embedding)
        return
    tempdir = tempfile.TemporaryDirectory() if args.synthetic else None
    vault_path = Path(tempdir.name) / "benchmark-vault" if tempdir else Path(args.vault).expanduser()
    if args.synthetic:
        _build_synthetic_vault(vault_path)
    vault = str(vault_path)
    cold_start = time.perf_counter()
    completed = subprocess.run(
        [sys.executable, __file__, "--vault", vault, "--query", args.query, "--embedding", args.embedding, "--single"],
        check=True, capture_output=True, text=True,
    )
    cold = json.loads(completed.stdout)
    retriever = EvidenceRetriever(Vault(vault).initialize(), _provider(args.embedding))
    first_start = time.perf_counter()
    first = retriever.search(args.query)
    first_ms = _milliseconds(first_start)
    warm_start = time.perf_counter()
    warm = retriever.search(args.query)
    warm_ms = _milliseconds(warm_start)
    print(json.dumps({
        "cold_process_ms": round((time.perf_counter() - cold_start) * 1000, 3),
        "embedding": args.embedding,
        "cold_query": cold,
        "process_first_query_ms": first_ms,
        "process_first_status": first["status"],
        "process_cache_warm_query_ms": warm_ms,
        "process_cache_warm_status": warm["status"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
