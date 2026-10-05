from __future__ import annotations

import json
import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest

from work_brain.cli import main
from work_brain.errors import ValidationError
from work_brain.model import ModelResponse, ScriptedModel
from work_brain.orchestrator import SessionOrchestrator
from work_brain.profiles import CommunicationProfileStore
from work_brain.retrieval import EvidenceRetriever
from work_brain.tools import ToolRegistry
from work_brain.vault import Vault
from work_brain import new_uuid7


ROOT = Path(__file__).resolve().parents[1]
RANQ_PROFILE = ROOT / ".work-brain-local/communication-profiles.json"


class CommunicationProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Vault(Path(self.tempdir.name) / "vault").initialize()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _commit(self, *, title: str, summary: str, started_at: str, entity_id: str,
                workspace_id: str | None = None, project_id: str | None = None) -> None:
        session = self.vault.create_session(
            started_at=started_at,
            modes=["communicate"],
            domain_tags=["founder"],
        )
        self.vault.append_turn(session["session_id"], "user", summary, recorded_at=started_at)
        sections = {name: [] for name in (
            "context", "observations", "significance", "contribution", "reasoning", "evidence",
            "alternatives_tradeoffs", "decisions_actions", "expectations", "outcomes", "learning", "open_questions",
        )}
        sections["context"] = [{"text": summary, "basis": "stated", "source_turns": [1]}]
        self.vault.commit_entry(session["session_id"], {
            "entry_id": session["entry_id"], "session_id": session["session_id"], "revision": 1,
            "commit_id": new_uuid7(), "created_at": started_at, "supersedes_revision": None,
            "revision_reason": "initial_commit", "provenance_kind": "contemporaneous",
            "title": title, "summary": summary,
            "occurrence": {"start": started_at, "end": None, "precision": "instant", "label": None},
            "modes": ["communicate"], "domain_tags": ["founder"], "sections": sections,
            "workspace_entity_id": workspace_id, "project_entity_id": project_id,
            "state_mutations": [], "entity_refs": [{"entity_id": entity_id, "relation": "about"}],
            "artifact_refs": [], "source_refs": [],
        })

    def test_ranq_whatsapp_profile_is_valid_and_user_scoped(self) -> None:
        store = CommunicationProfileStore.load(RANQ_PROFILE)
        profile = store.get("ranq_whatsapp")
        self.assertEqual("communicate", profile.workflow)
        self.assertEqual("WhatsApp", profile.channel)
        self.assertEqual(["ranq"], profile.scope["workspaces"])
        self.assertEqual("work_item", profile.scope["time_window"])
        self.assertEqual(("after_work_item",), profile.triggers)
        self.assertEqual("on_demand", profile.cadence)
        self.assertEqual({"markup": "plain_text", "layout": "compact", "max_length": 1200}, profile.rendering)
        self.assertIn("business impact", profile.include)
        self.assertIn("technical jargon", profile.exclude)

    def test_communicate_can_read_a_validated_profile_through_a_high_level_tool(self) -> None:
        store = CommunicationProfileStore.load(RANQ_PROFILE)
        registry = ToolRegistry(self.vault, profile_store=store)
        names = {tool.name for tool in registry.definitions("communicate")}
        self.assertIn("get_communication_profile", names)
        result = registry.call("get_communication_profile", profile_id="ranq_whatsapp")
        self.assertTrue(result.ok)
        self.assertEqual("WhatsApp", result.data["channel"])
        self.assertEqual(["ranq"], result.data["scope"]["workspaces"])

    def test_profile_search_applies_exact_ranq_work_item_scope(self) -> None:
        store = CommunicationProfileStore.load(RANQ_PROFILE)
        seen: dict[str, object] = {}

        def search(**arguments: object) -> dict[str, object]:
            seen.update(arguments)
            return {"status": "ok", "cards": [{"title": "matched"}]}

        registry = ToolRegistry(
            self.vault,
            retrieval={"search_evidence": search},
            profile_store=store,
        )
        result = registry.call(
            "search_profile_evidence",
            profile_id="ranq_whatsapp",
            work_item="Ranq launch",
            query="what moved forward",
        )
        self.assertTrue(result.ok)
        self.assertEqual("Ranq launch what moved forward", seen["query"])
        filters = seen["filters"]
        self.assertEqual(["ranq"], filters["workspaces"])
        self.assertNotIn("occurred_after", filters)
        self.assertNotIn("occurred_before", filters)

    def test_ranq_work_item_uses_text_entity_fallback_for_legacy_entries(self) -> None:
        store = CommunicationProfileStore.load(RANQ_PROFILE)
        calls: list[dict[str, object]] = []

        def search(**arguments: object) -> dict[str, object]:
            calls.append(arguments)
            if "workspaces" in arguments["filters"]:
                return {"status": "ok", "cards": []}
            return {"status": "ok", "cards": [{"title": "legacy Ranq entry"}]}

        registry = ToolRegistry(
            self.vault,
            retrieval={"search_evidence": search},
            profile_store=store,
        )
        result = registry.call(
            "search_profile_evidence", profile_id="ranq_whatsapp",
            work_item="auth architecture", query="progress",
        )
        self.assertTrue(result.ok)
        self.assertEqual(2, len(calls))
        self.assertEqual("ranq auth architecture progress", calls[1]["query"])
        self.assertEqual({}, calls[1]["filters"])
        self.assertEqual("text_entity_fallback", result.data["profile_scope"]["retrieval_mode"])
        self.assertEqual("ranq_whatsapp", result.data["profile_scope"]["profile_id"])

    def test_profile_id_starts_a_scoped_communicate_session(self) -> None:
        store = CommunicationProfileStore.load(RANQ_PROFILE)
        registry = ToolRegistry(self.vault, profile_store=store)
        model = ScriptedModel(responses=["I need one confirmed Ranq outcome before drafting."])
        orchestrator = SessionOrchestrator(self.vault, model, tools=registry)
        orchestrator.start(
            "Draft today's Ranq WhatsApp update.",
            workflow="communicate",
            profile_id="ranq_whatsapp",
        )
        self.assertEqual("ranq_whatsapp", orchestrator.profile_id)
        self.assertEqual("ranq_whatsapp", registry.active_profile_id)
        self.assertEqual(
            "ranq_whatsapp",
            self.vault.read_session(orchestrator.session_id)["runtime"]["profile_id"],
        )
        self.assertIn("search_profile_evidence", model.calls[0]["tools"])
        self.assertNotIn("search_evidence", model.calls[0]["tools"])

    def test_ranq_whatsapp_dry_run_uses_only_ranq_work_item_evidence(self) -> None:
        ranq = self.vault.upsert_entity(
            kind="workspace", canonical_name="Ranq", aliases=["ranq"],
            created_at="2026-09-30T09:00:00+01:00", updated_at="2026-09-30T09:00:00+01:00",
        )
        other = self.vault.upsert_entity(
            kind="workspace", canonical_name="Other workspace", aliases=["other"],
            created_at="2026-09-30T09:00:00+01:00", updated_at="2026-09-30T09:00:00+01:00",
        )
        self._commit(
            title="Ranq launch today", summary="Ranq launch moved forward with a confirmed pilot.",
            started_at="2026-10-01T10:00:00+01:00", entity_id=ranq["entity_id"], workspace_id=ranq["entity_id"],
        )
        self._commit(
            title="Ranq launch yesterday", summary="Ranq launch had an earlier exploratory discussion.",
            started_at="2026-09-30T10:00:00+01:00", entity_id=ranq["entity_id"], workspace_id=ranq["entity_id"],
        )
        self._commit(
            title="Other launch today", summary="Other project launch moved forward.",
            started_at="2026-10-01T11:00:00+01:00", entity_id=other["entity_id"], workspace_id=other["entity_id"],
        )
        registry = ToolRegistry(
            self.vault,
            profile_store=CommunicationProfileStore.load(RANQ_PROFILE),
            retrieval={"search_evidence": EvidenceRetriever(self.vault).search},
        )
        result = registry.call(
            "search_profile_evidence", profile_id="ranq_whatsapp", work_item="launch", query="progress",
            page_size=10,
        )
        self.assertTrue(result.ok, result.error)
        self.assertEqual(
            ["Ranq launch today", "Ranq launch yesterday"],
            [card["title"] for card in result.data["cards"]],
        )

    def test_close_day_has_no_profile_prompt_for_work_item_only_profiles(self) -> None:
        store = CommunicationProfileStore.load(RANQ_PROFILE)
        registry = ToolRegistry(self.vault, profile_store=store)
        result = registry.call("list_post_close_communication_profiles")
        self.assertTrue(result.ok)
        self.assertEqual([], result.data)

    def test_discord_and_ranq_progress_profiles_are_event_driven(self) -> None:
        store = CommunicationProfileStore.load(RANQ_PROFILE)
        profile = store.get("discord_progress")
        self.assertEqual({"time_window": "work_item"}, profile.scope)
        self.assertEqual("on_demand", profile.cadence)
        self.assertEqual(("after_work_item",), profile.triggers)
        self.assertEqual("draft_only", profile.delivery["mode"])
        self.assertEqual("markdown", profile.rendering["markup"])
        self.assertEqual("structured", profile.rendering["layout"])
        registry = ToolRegistry(self.vault, profile_store=store)
        result = registry.call("list_work_item_communication_profiles")
        self.assertTrue(result.ok)
        self.assertEqual(["discord_progress", "ranq_whatsapp"], [item["id"] for item in result.data])

        missing_anchor = registry.call(
            "search_profile_evidence", profile_id="discord_progress", query="what changed",
        )
        self.assertFalse(missing_anchor.ok)
        self.assertIn("work_item is required", missing_anchor.error)

        seen: dict[str, object] = {}

        def search(**arguments: object) -> dict[str, object]:
            seen.update(arguments)
            return {"status": "ok", "cards": []}

        anchored_registry = ToolRegistry(
            self.vault,
            retrieval={"search_evidence": search},
            profile_store=store,
        )
        anchored = anchored_registry.call(
            "search_profile_evidence", profile_id="discord_progress",
            work_item="auth architecture", query="what changed",
        )
        self.assertTrue(anchored.ok)
        self.assertEqual("auth architecture what changed", seen["query"])
        self.assertEqual({}, seen["filters"])

    def test_close_day_model_can_see_no_profile_when_none_is_opted_in(self) -> None:
        store = CommunicationProfileStore.load(RANQ_PROFILE)
        registry = ToolRegistry(self.vault, profile_store=store)
        model = ScriptedModel(responses=[
            ModelResponse("", ({"name": "list_post_close_communication_profiles", "arguments": {}},)),
            "No post-close communication profile is configured.",
        ])
        orchestrator = SessionOrchestrator(self.vault, model, tools=registry)
        orchestrator.start(workflow="close-day")
        response = orchestrator.turn("close my day")
        self.assertEqual("list_post_close_communication_profiles", model.calls[0]["tools"][2])
        self.assertIn("No post-close", response.text)

    def test_cli_can_validate_list_and_show_a_profile(self) -> None:
        output = tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False)
        try:
            output.write(json.dumps({"version": 1, "profiles": [CommunicationProfileStore.load(RANQ_PROFILE).get("ranq_whatsapp").to_dict()]}))
            output.close()
            self.assertEqual(0, main(["--profiles", output.name, "profiles", "validate"]))
            self.assertEqual(0, main(["--profiles", output.name, "profiles", "show", "ranq_whatsapp"]))
        finally:
            Path(output.name).unlink(missing_ok=True)

    def test_ranq_profile_is_ignored_by_git(self) -> None:
        relative = RANQ_PROFILE.relative_to(ROOT)
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", str(relative)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_invalid_profile_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            path.write_text(json.dumps({"version": 1, "profiles": [{"id": "Bad ID"}]}), encoding="utf-8")
            with self.assertRaises(ValidationError):
                CommunicationProfileStore.load(path)

    def test_context_backfill_creates_an_immutable_metadata_revision(self) -> None:
        subject = self.vault.upsert_entity(
            kind="workspace", canonical_name="Unclassified workspace",
            created_at="2026-09-30T09:00:00+01:00", updated_at="2026-09-30T09:00:00+01:00",
        )
        self._commit(
            title="Auth decision", summary="Compared two authorization approaches.",
            started_at="2026-10-01T12:00:00+01:00", entity_id=subject["entity_id"],
        )
        current = self.vault.all_current_entries()[0]
        updated = self.vault.backfill_entry_context(
            current.entry_id, workspace="Ranq", project="Auth implementation",
        )
        self.assertEqual(2, updated.revision)
        self.assertEqual("metadata_backfill", updated.revision_reason)
        self.assertNotEqual(current.workspace_entity_id, updated.workspace_entity_id)
        self.assertIsNotNone(updated.project_entity_id)
        revisions = self.vault.all_entry_revisions()
        self.assertEqual([1, 2], [entry.revision for entry, _ in revisions])
        self.assertIsNone(revisions[0][0].workspace_entity_id)
        self.assertTrue(any(ref["revision"] == 1 for ref in updated.source_refs if ref["kind"] == "entry"))

    def test_cli_backfill_context_applies_defaults_and_overrides(self) -> None:
        subject = self.vault.upsert_entity(
            kind="workspace", canonical_name="Existing workspace",
            created_at="2026-09-30T09:00:00+01:00", updated_at="2026-09-30T09:00:00+01:00",
        )
        self._commit(
            title="Backfill target", summary="An existing committed experience.",
            started_at="2026-10-01T13:00:00+01:00", entity_id=subject["entity_id"],
        )
        entry = self.vault.all_current_entries()[0]
        mapping = tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False)
        try:
            json.dump({"defaults": {"workspace": "Ranq"}, "entries": {entry.entry_id: {"project": "Auth implementation"}}}, mapping)
            mapping.close()
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(["--vault", str(self.vault.root), "backfill-context", "--file", mapping.name]))
            updated = self.vault.get_current_entry(entry.entry_id)
            self.assertEqual(2, updated.revision)
            self.assertIsNotNone(updated.workspace_entity_id)
            self.assertIsNotNone(updated.project_entity_id)
        finally:
            Path(mapping.name).unlink(missing_ok=True)

    def test_cli_backfill_tags_is_additive_and_immutable(self) -> None:
        subject = self.vault.upsert_entity(
            kind="workspace", canonical_name="Tagged workspace",
            created_at="2026-09-30T09:00:00+01:00", updated_at="2026-09-30T09:00:00+01:00",
        )
        self._commit(
            title="Auth tags", summary="Reviewed login and authorization boundaries.",
            started_at="2026-10-01T14:00:00+01:00", entity_id=subject["entity_id"],
        )
        entry = self.vault.all_current_entries()[0]
        mapping = tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False)
        try:
            json.dump({"entries": {entry.entry_id: {"domain_tags": ["Authentication", "access_control", "security"]}}}, mapping)
            mapping.close()
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(["--vault", str(self.vault.root), "backfill-tags", "--file", mapping.name]))
            updated = self.vault.get_current_entry(entry.entry_id)
            self.assertEqual(["founder", "authentication", "access-control", "security"], updated.domain_tags)
            self.assertEqual(2, updated.revision)
            self.assertEqual("metadata_backfill", updated.revision_reason)
            self.assertEqual([1, 2], [item.revision for item, _ in self.vault.all_entry_revisions()])
        finally:
            Path(mapping.name).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
