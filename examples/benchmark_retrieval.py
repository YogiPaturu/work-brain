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
import time
from pathlib import Path

from work_brain import EvidenceRetriever, FastEmbedEmbeddingProvider, LocalHashEmbeddingProvider, Vault


def _milliseconds(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)


def _provider(name: str):
    if name == "hash":
        return LocalHashEmbeddingProvider()
    if name == "fastembed":
        return FastEmbedEmbeddingProvider(cache_dir=os.environ.get("WORK_BRAIN_FASTEMBED_CACHE"))
    return None


def _single(vault: str, query: str, embedding: str) -> None:
    start = time.perf_counter()
    result = EvidenceRetriever(Vault(vault).initialize(), _provider(embedding)).search(query)
    print(json.dumps({"embedding": embedding, "latency_ms": _milliseconds(start), "status": result["status"], "cards": len(result["cards"])}, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", required=True)
    parser.add_argument("--query", default="import reliability")
    parser.add_argument("--embedding", choices=("auto", "hash", "fastembed"), default="auto")
    parser.add_argument("--single", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.single:
        _single(args.vault, args.query, args.embedding)
        return
    vault = str(Path(args.vault).expanduser())
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
