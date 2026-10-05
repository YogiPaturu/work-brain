from __future__ import annotations

from contextlib import closing
import json
import tempfile
import unittest
from pathlib import Path

from work_brain import EvidenceRetriever, LocalHashEmbeddingProvider, Vault, new_uuid7
from work_brain.retrieval import StaleIndexWork


SECTIONS = (
    "context", "observations", "significance", "contribution", "reasoning", "evidence",
    "alternatives_tradeoffs", "decisions_actions", "expectations", "outcomes", "learning", "open_questions",
)


def payload(session: dict, *, title: str, summary: str, revision: int = 1, supersedes: int | None = None) -> dict:
    sections = {name: [] for name in SECTIONS}
    sections["context"] = [{"text": summary, "basis": "stated", "source_turns": [1]}]
    sections["reasoning"] = [{"text": f"Reasoning for {title} after new evidence.", "basis": "stated", "source_turns": [1]}]
    return {
        "entry_id": session["entry_id"], "session_id": session["session_id"], "revision": revision,
        "commit_id": new_uuid7(), "created_at": "2026-09-30T10:05:00+01:00",
        "supersedes_revision": supersedes, "revision_reason": "initial_commit" if revision == 1 else "reextract",
        "provenance_kind": "contemporaneous", "title": title, "summary": summary,
        "occurrence": {"start": "2026-09-30T10:00:00+01:00", "end": None, "precision": "instant", "label": None},
        "modes": ["think"], "domain_tags": ["engineering"], "sections": sections,
        "state_mutations": [], "entity_refs": [], "artifact_refs": [], "source_refs": [],
    }


class RetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Vault(Path(self.tempdir.name) / "vault").initialize()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_embedding_work_runs_without_authoritative_writer_lock(self) -> None:
        session = self._commit("Lock boundary", "Embedding must not block source capture.")
        vault = self.vault

        class LockObservingProvider(LocalHashEmbeddingProvider):
            def __init__(self) -> None:
                super().__init__()
                self.source_lock_depths: list[int] = []

            def embed_documents(self, texts: list[str]) -> list[list[float]]:
                self.source_lock_depths.append(vault._lock_depth)
                return super().embed_documents(texts)

        provider = LockObservingProvider()
        EvidenceRetriever(vault, provider).index_entry(session["entry_id"])
        self.assertEqual([0], provider.source_lock_depths)

    def test_stale_embedding_work_cannot_publish_over_newer_revision(self) -> None:
        session = self._commit("Stale embedding", "The source revision may change during embedding.")
        vault = self.vault
        original = payload(session, title="Newer source", summary="A newer source revision wins.", revision=2, supersedes=1)

        class RevisionChangingProvider(LocalHashEmbeddingProvider):
            changed = False

            def embed_documents(self, texts: list[str]) -> list[list[float]]:
                if not self.changed:
                    self.changed = True
                    vault.commit_entry(session["session_id"], original, refresh_projections=False)
                return super().embed_documents(texts)

        with self.assertRaises(StaleIndexWork):
            EvidenceRetriever(vault, RevisionChangingProvider()).index_entry(session["entry_id"])
        self.assertEqual(2, vault.get_current_entry(session["entry_id"]).revision)

    def _commit(self, title: str, summary: str) -> dict:
        session = self.vault.create_session(started_at="2026-09-30T10:00:00+01:00", modes=["think"], domain_tags=["engineering"])
        self.vault.append_turn(session["session_id"], "user", summary, recorded_at="2026-09-30T10:01:00+01:00")
        self.vault.commit_entry(session["session_id"], payload(session, title=title, summary=summary))
        EvidenceRetriever(self.vault).reindex()
        return session

    def test_search_uses_one_chunk_corpus_and_bounded_cards(self) -> None:
        session = self._commit("Import reliability", "Investigated an unreliable import path.")
        result = EvidenceRetriever(self.vault).search("import reliability")
        self.assertEqual("ok", result["status"])
        self.assertEqual(session["entry_id"], result["cards"][0]["ref"]["entry_id"])
        self.assertNotIn("score", json.dumps(result["cards"]))
        with closing(self.vault._database().connect()) as conn:
            chunks = {row[0] for row in conn.execute("SELECT chunk_id FROM retrieval_chunks")}
            fts = {row[0] for row in conn.execute("SELECT chunk_id FROM retrieval_fts")}
            vectors = {row[0] for row in conn.execute("SELECT chunk_id FROM retrieval_embeddings")}
        self.assertEqual(chunks, fts)
        self.assertEqual(chunks, vectors)

    def test_revision_replaces_current_search_and_historical_hydration_is_exact(self) -> None:
        session = self._commit("Original direction", "The original direction was recorded.")
        current = self.vault.get_current_entry(session["entry_id"])
        second = payload(session, title="Corrected direction", summary="The corrected direction is now authoritative.", revision=2, supersedes=1)
        self.vault.commit_entry(session["session_id"], second)
        EvidenceRetriever(self.vault).reindex()
        result = EvidenceRetriever(self.vault).search("direction")
        self.assertEqual(2, result["cards"][0]["ref"]["revision"])
        hydrated = EvidenceRetriever(self.vault).hydrate([{"entry_id": current.entry_id, "revision": 1}])
        self.assertEqual("historical", hydrated["items"][0]["status"])
        self.assertEqual(2, hydrated["items"][0]["current_revision"])
        self.assertEqual("Original direction", hydrated["items"][0]["entry"]["title"])

    def test_filters_and_opaque_pagination(self) -> None:
        self._commit("Alpha import", "Alpha import investigation.")
        self._commit("Beta import", "Beta import investigation.")
        self._commit("Gamma import", "Gamma import investigation.")
        retriever = EvidenceRetriever(self.vault)
        first = retriever.search("import", page_size=2, filters={"domain_tags": ["engineering"]})
        self.assertEqual(2, len(first["cards"]))
        self.assertIsNotNone(first["next_cursor"])
        second = retriever.search("import", page_size=2, filters={"domain_tags": ["engineering"]}, cursor=first["next_cursor"])
        self.assertEqual(1, len(second["cards"]))
        self.assertIsNone(second["next_cursor"])
        self.assertEqual("cursor_expired", retriever.search("import", page_size=1, cursor=first["next_cursor"], filters={"domain_tags": ["product"]})["status"])

    def test_reindex_is_idempotent_and_repairs_derived_damage(self) -> None:
        self._commit("Repair index", "The retrieval index can be rebuilt.")
        retriever = EvidenceRetriever(self.vault)
        with closing(self.vault._database().connect()) as conn:
            with conn:
                conn.execute("DELETE FROM retrieval_fts")
        self.assertTrue(retriever.doctor())
        result = retriever.search("rebuilt")
        self.assertEqual("degraded", result["status"])
        before = retriever.reindex()
        after = retriever.reindex()
        self.assertEqual(before["indexed_entries"], after["indexed_entries"])
        self.assertEqual(before["indexed_chunks"], after["indexed_chunks"])
        self.assertEqual([], retriever.doctor())

    def test_search_and_reindex_report_embedding_provider(self) -> None:
        self._commit("Provider diagnostics", "The retrieval provider should be visible to users.")
        retriever = EvidenceRetriever(self.vault, LocalHashEmbeddingProvider())
        reindexed = retriever.reindex()
        self.assertEqual("hash", reindexed["embedding"]["provider"])
        self.assertEqual("hash-fallback", reindexed["embedding"]["semantic_quality"])
        self.assertEqual("fallback", retriever.search("provider diagnostics")["embedding"]["status"])


if __name__ == "__main__":
    unittest.main()
