from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from work_brain import ContextResolver, EvidenceRetriever, LocalHashEmbeddingProvider, ToolRegistry, Vault, new_uuid7
from work_brain.cli import main


SECTIONS = (
    "context", "observations", "significance", "contribution", "reasoning", "evidence",
    "alternatives_tradeoffs", "decisions_actions", "expectations", "outcomes", "learning", "open_questions",
)


class ContextResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Vault(Path(self.tempdir.name) / "vault").initialize()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _commit(self, *, workspace_id: str, project_id: str, summary: str, started_at: str) -> str:
        session = self.vault.create_session(started_at=started_at, modes=["think"])
        self.vault.append_turn(session["session_id"], "user", summary)
        sections = {name: [] for name in SECTIONS}
        sections["context"] = [{"text": summary, "basis": "stated", "source_turns": [1]}]
        payload = {
            "entry_id": session["entry_id"],
            "session_id": session["session_id"],
            "revision": 1,
            "commit_id": new_uuid7(),
            "created_at": started_at,
            "supersedes_revision": None,
            "revision_reason": "initial_commit",
            "provenance_kind": "contemporaneous",
            "title": summary,
            "summary": summary,
            "occurrence": {"start": started_at, "end": None, "precision": "instant", "label": None},
            "modes": ["think"],
            "domain_tags": ["engineering"],
            "workspace_entity_id": workspace_id,
            "project_entity_id": project_id,
            "sections": sections,
            "state_mutations": [],
            "entity_refs": [],
            "artifact_refs": [],
            "source_refs": [],
        }
        self.vault.commit_entry(session["session_id"], payload, refresh_projections=False)
        return session["entry_id"]

    def _rebuild_indexes(self) -> EvidenceRetriever:
        self.vault.reconcile_database()
        retriever = EvidenceRetriever(self.vault, LocalHashEmbeddingProvider())
        retriever.reindex()
        return retriever

    def _source_snapshot(self) -> dict[str, bytes]:
        paths = list((self.vault.root / "catalog/entities").glob("*.json"))
        paths.extend((self.vault.root / "sessions").rglob("*.json"))
        paths.extend((self.vault.root / "sessions").rglob("*.jsonl"))
        return {str(path): path.read_bytes() for path in sorted(paths)}

    def test_exact_canonical_and_alias_lookup_is_source_verified_and_read_only(self) -> None:
        workspace = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        project = self.vault.upsert_entity(kind="project", canonical_name="Authentication", aliases=["Auth"])
        self._rebuild_indexes()
        before = self._source_snapshot()

        result = ContextResolver(self.vault).resolve_context(workspace_hint="ranq", project_hint="Auth")

        self.assertEqual("resolved", result["workspace"]["status"])
        self.assertEqual(workspace["entity_id"], result["workspace"]["candidates"][0]["entity_id"])
        self.assertEqual("canonical", result["workspace"]["candidates"][0]["matched_by"])
        self.assertEqual("resolved", result["project"]["status"])
        self.assertEqual(project["entity_id"], result["project"]["candidates"][0]["entity_id"])
        self.assertEqual("alias", result["project"]["candidates"][0]["matched_by"])
        self.assertEqual(before, self._source_snapshot())

    def test_historical_project_candidates_are_scoped_to_resolved_workspace(self) -> None:
        ranq = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        other = self.vault.upsert_entity(kind="workspace", canonical_name="Other")
        auth = self.vault.upsert_entity(kind="project", canonical_name="Authentication")
        search = self.vault.upsert_entity(kind="project", canonical_name="Search")
        self._commit(
            workspace_id=ranq["entity_id"], project_id=auth["entity_id"],
            summary="Investigated token refresh work in the authentication flow.",
            started_at="2026-05-01T10:00:00+01:00",
        )
        self._commit(
            workspace_id=other["entity_id"], project_id=search["entity_id"],
            summary="Investigated token refresh work in search indexing.",
            started_at="2026-05-02T10:00:00+01:00",
        )
        retriever = self._rebuild_indexes()

        result = ContextResolver(self.vault, search_evidence=retriever.search).resolve_context(
            workspace_hint="Ranq", project_hint="token refresh work",
        )

        self.assertEqual("candidates", result["project"]["status"])
        self.assertEqual([auth["entity_id"]], [item["entity_id"] for item in result["project"]["candidates"]])
        candidate = result["project"]["candidates"][0]
        self.assertEqual("historical_evidence", candidate["matched_by"])
        self.assertEqual(1, candidate["evidence_match_count"])
        self.assertLessEqual(len(candidate["supporting_entries"]), 3)

    def test_ambiguous_exact_project_name_is_not_guessed(self) -> None:
        first = self.vault.upsert_entity(kind="project", canonical_name="Authentication", aliases=["Auth"])
        second = self.vault.upsert_entity(kind="project", canonical_name="Authentication Platform", aliases=["Auth"])
        self._rebuild_indexes()

        result = ContextResolver(self.vault).resolve_context(project_hint="Auth")

        self.assertEqual("ambiguous", result["project"]["status"])
        self.assertEqual(
            {first["entity_id"], second["entity_id"]},
            {item["entity_id"] for item in result["project"]["candidates"]},
        )

    def test_exact_project_limit_does_not_hide_ambiguity(self) -> None:
        self.vault.upsert_entity(kind="project", canonical_name="Authentication")
        self.vault.upsert_entity(kind="project", canonical_name="Authentication")
        self._rebuild_indexes()

        result = ContextResolver(self.vault).resolve_context(project_hint="Authentication", limit=1)

        self.assertEqual("ambiguous", result["project"]["status"])
        self.assertEqual(1, len(result["project"]["candidates"]))

    def test_exact_workspace_limit_does_not_hide_ambiguity(self) -> None:
        self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        self._rebuild_indexes()

        result = ContextResolver(self.vault).resolve_context(workspace_hint="Ranq", limit=1)

        self.assertEqual("ambiguous", result["workspace"]["status"])
        self.assertEqual(1, len(result["workspace"]["candidates"]))

    def test_partial_projection_cannot_hide_authoritative_exact_ambiguity(self) -> None:
        first = self.vault.upsert_entity(kind="project", canonical_name="Authentication")
        second = self.vault.upsert_entity(kind="project", canonical_name="Authentication")
        self._rebuild_indexes()

        conn = self.vault._database().connect()
        try:
            conn.execute("DELETE FROM entity_aliases WHERE entity_id = ?", (second["entity_id"],))
            conn.commit()
        finally:
            conn.close()

        result = ContextResolver(self.vault).resolve_context(project_hint="Authentication")

        self.assertEqual("ambiguous", result["project"]["status"])
        self.assertEqual(
            {first["entity_id"], second["entity_id"]},
            {item["entity_id"] for item in result["project"]["candidates"]},
        )

    def test_open_and_close_day_expose_context_resolution(self) -> None:
        registry = ToolRegistry(self.vault)

        self.assertIn("resolve_context", {item.name for item in registry.definitions("open-day")})
        self.assertIn("resolve_context", {item.name for item in registry.definitions("close-day")})

    def test_workspace_cooccurrence_disambiguates_exact_project_alias(self) -> None:
        workspace = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        first = self.vault.upsert_entity(kind="project", canonical_name="Authentication", aliases=["Auth"])
        second = self.vault.upsert_entity(kind="project", canonical_name="Authentication Platform", aliases=["Auth"])
        self._commit(
            workspace_id=workspace["entity_id"], project_id=first["entity_id"],
            summary="The authentication project used the existing Auth context.",
            started_at="2026-05-01T10:00:00+01:00",
        )
        self._rebuild_indexes()

        result = ContextResolver(self.vault).resolve_context(workspace_hint="Ranq", project_hint="Auth")

        self.assertEqual("resolved", result["project"]["status"])
        self.assertEqual(first["entity_id"], result["project"]["candidates"][0]["entity_id"])
        self.assertNotEqual(second["entity_id"], result["project"]["candidates"][0]["entity_id"])

    def test_workspace_cooccurrence_disambiguates_before_output_limit(self) -> None:
        workspace = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        first = self.vault.upsert_entity(kind="project", canonical_name="Authentication", aliases=["Auth"])
        self.vault.upsert_entity(kind="project", canonical_name="Authentication Platform", aliases=["Auth"])
        self._commit(
            workspace_id=workspace["entity_id"], project_id=first["entity_id"],
            summary="The authentication project used the existing Auth context.",
            started_at="2026-05-01T10:00:00+01:00",
        )
        self._rebuild_indexes()

        result = ContextResolver(self.vault).resolve_context(
            workspace_hint="Ranq", project_hint="Auth", limit=1,
        )

        self.assertEqual("resolved", result["project"]["status"])
        self.assertEqual([first["entity_id"]], [item["entity_id"] for item in result["project"]["candidates"]])
        self.assertLessEqual(len(result["workspace"]["candidates"]), 1)
        self.assertLessEqual(len(result["project"]["candidates"]), 1)

    def test_workspace_owned_exact_projects_resolve_without_history(self) -> None:
        ranq = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        personal = self.vault.upsert_entity(kind="workspace", canonical_name="Personal")
        ranq_project = self.vault.upsert_entity(
            kind="project", canonical_name="Website", workspace_entity_id=ranq["entity_id"],
        )
        personal_project = self.vault.upsert_entity(
            kind="project", canonical_name="Website", workspace_entity_id=personal["entity_id"],
        )
        self._rebuild_indexes()

        ranq_result = ContextResolver(self.vault).resolve_context(
            workspace_hint="Ranq", project_hint="Website",
        )
        personal_result = ContextResolver(self.vault).resolve_context(
            workspace_hint="Personal", project_hint="Website",
        )
        self.assertEqual("resolved", ranq_result["project"]["status"])
        self.assertEqual(ranq_project["entity_id"], ranq_result["project"]["candidates"][0]["entity_id"])
        self.assertEqual("resolved", personal_result["project"]["status"])
        self.assertEqual(personal_project["entity_id"], personal_result["project"]["candidates"][0]["entity_id"])

    def test_workspace_owned_duplicate_project_names_are_ambiguous_without_workspace(self) -> None:
        ranq = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        personal = self.vault.upsert_entity(kind="workspace", canonical_name="Personal")
        first = self.vault.upsert_entity(
            kind="project", canonical_name="Website", workspace_entity_id=ranq["entity_id"],
        )
        second = self.vault.upsert_entity(
            kind="project", canonical_name="Website", workspace_entity_id=personal["entity_id"],
        )
        self._rebuild_indexes()

        result = ContextResolver(self.vault).resolve_context(project_hint="Website")

        self.assertEqual("ambiguous", result["project"]["status"])
        self.assertEqual(
            {first["entity_id"], second["entity_id"]},
            {item["entity_id"] for item in result["project"]["candidates"]},
        )

    def test_historical_unavailability_does_not_hide_exact_resolution(self) -> None:
        workspace = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        self._rebuild_indexes()

        def unavailable(**_: object) -> dict[str, object]:
            raise RuntimeError("retrieval unavailable")

        result = ContextResolver(self.vault, search_evidence=unavailable).resolve_context(
            workspace_hint="Ranq", project_hint="token refresh work",
        )

        self.assertEqual("resolved", result["workspace"]["status"])
        self.assertEqual("unresolved", result["project"]["status"])
        self.assertEqual("unavailable", result["project"]["historical_status"])
        self.assertEqual(workspace["entity_id"], result["workspace"]["candidates"][0]["entity_id"])

    def test_tool_and_cli_expose_bounded_read_operation(self) -> None:
        workspace = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        self._rebuild_indexes()
        registry = ToolRegistry(self.vault)
        self.assertIn("resolve_context", {item.name for item in registry.definitions("think")})
        tool_result = registry.call("resolve_context", workspace_hint="Ranq")
        self.assertTrue(tool_result.ok)
        self.assertEqual(workspace["entity_id"], tool_result.data["workspace"]["candidates"][0]["entity_id"])

        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, main(["--vault", str(self.vault.root), "context", "resolve", "--workspace", "Ranq"]))
        cli_result = json.loads(output.getvalue())
        self.assertEqual("resolved", cli_result["workspace"]["status"])


if __name__ == "__main__":
    unittest.main()
