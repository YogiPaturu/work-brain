from __future__ import annotations

import tempfile
import unittest
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import re
from typing import Any
from unittest.mock import patch

from work_brain import (
    CommitResolver,
    CommitDraftValidator,
    EvidenceRetriever,
    RuntimeState,
    ScriptedModel,
    SessionOrchestrator,
    SkillLoader,
    ToolRegistry,
    ValidationError,
    Vault,
    new_uuid7,
    select_workflow,
)
from work_brain.model import ModelResponse
from work_brain.domain import ENTRY_SECTIONS
from work_brain.capture import HarnessCaptureService, normalize_capture_event, record_capture_hook_failure
from work_brain.cli import main
from work_brain.fsutil import append_jsonl


def draft(*, workflow: str = "think", bad_runtime_field: bool = False) -> dict:
    sections = {name: [] for name in ENTRY_SECTIONS}
    sections["context"] = [{"text": "We examined the import boundary.", "basis": "stated", "source_turns": [1]}]
    value = {
        "title": "Import boundary decision",
        "summary": "Clarified the trade-off and next experiment.",
        "historical_occurrence": {
            "start": "2026-09-29", "end": None, "precision": "day", "label": "historical"
        } if workflow == "backfill" else None,
        "domain_tags": ["engineering"],
        "workspace": "Work Brain",
        "project": "Import boundary",
        "sections": sections,
        "state_changes": [], "entity_candidates": [], "artifact_candidates": [], "source_entry_refs": [],
    }
    if bad_runtime_field:
        value["entry_id"] = new_uuid7()
    return value


class RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Vault(Path(self.tempdir.name) / "vault").initialize()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_skill_loader_is_progressive_and_versioned(self) -> None:
        loaded = SkillLoader().load("think", ["engineering", "product", "leadership"])
        self.assertEqual(["WORK-BRAIN-SKILL@2", "WORK-BRAIN-SOP-CORE@3", "WORK-BRAIN-SOP-THINK@3", "WORK-BRAIN-PROBE-ENGINEERING@2", "WORK-BRAIN-PROBE-PRODUCT@2"], loaded.identities)
        self.assertNotIn("WORK-BRAIN-PROBE-LEADERSHIP@2", loaded.identities)

    def test_commit_instruction_load_includes_schema_and_tag_reference(self) -> None:
        loaded = SkillLoader().load("think", ["engineering"], include_commit_schema=True)
        self.assertIn("WORK-BRAIN-SCHEMA-COMMIT-DRAFT@1", loaded.identities)
        self.assertIn("WORK-BRAIN-DOMAIN-TAGS@1", loaded.identities)
        self.assertIn("`domain_tags`", loaded.text)
        self.assertIn("authentication", loaded.text)

    def test_new_probe_packs_are_selectable_and_still_bounded(self) -> None:
        loaded = SkillLoader().load("think", ["architecture", "founder", "people"])
        self.assertEqual(["WORK-BRAIN-PROBE-ARCHITECTURE@1", "WORK-BRAIN-PROBE-FOUNDER@1"], loaded.identities[-2:])
        self.assertNotIn("PEOPLE-MANAGEMENT", loaded.text)

    def test_skill_has_native_metadata(self) -> None:
        skill = (Path(__file__).resolve().parents[1] / "skills/work-brain/SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\nname: work-brain\ndescription: "))
        self.assertIn("\n---\n\nWORK-BRAIN-SKILL v2\n", skill)
        agent_yaml = (Path(__file__).resolve().parents[1] / "skills/work-brain/agents/openai.yaml").read_text(encoding="utf-8")
        self.assertTrue(agent_yaml.startswith("interface:\n"))
        self.assertIn("  display_name:", agent_yaml)
        self.assertIn("  short_description:", agent_yaml)
        self.assertIn("  default_prompt:", agent_yaml)
        self.assertIn("## Development / authoring boundary", skill)
        self.assertIn("Skill discovery or loading is not activation", skill)

    def test_experience_review_is_progressive_and_packaged(self) -> None:
        root = Path(__file__).resolve().parents[1]
        skill = (root / "skills/work-brain/SKILL.md").read_text(encoding="utf-8")
        review = (root / "skills/work-brain/references/experience-review.md").read_text(encoding="utf-8")
        agent_tools = (root / "skills/work-brain/references/tools/agent-tools.md").read_text(encoding="utf-8")
        cli_reference = (root / "skills/work-brain/references/tools/work-brain-cli.md").read_text(encoding="utf-8")
        package = (root / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn("references/experience-review.md` only when evaluating", skill)
        self.assertNotIn("WORK-BRAIN-EXPERIENCE-REVIEW", SkillLoader().load("think").text)
        for phrase in (
            "bounded human/model review",
            "`experience related --entry-id ENTRY_ID --limit 8`",
            "bounded recall candidates",
            "same exact current",
            "Time proximity, topic or technology similarity",
            "INCLUDE`, `EXCLUDE`, or `UNCERTAIN",
            "sharing a Project",
            "without a causal",
            "False merges are worse",
            "experience get",
            "already in another coherent Experience",
            "require explicit user intent",
            "neutral, durable title",
            "interview question",
            "lightweight CommitDraft",
            "leave the entry unassigned",
            "Retrieval degradation or incomplete results",
            "Do not invent confidence or similarity scores",
            "scan hundreds of entries",
            "Do not add merge or split behavior",
            "experience mine --page-size 5 --related-limit 6",
            "returned opaque cursor",
            "automatic clustering",
        ):
            self.assertIn(phrase, review)
        self.assertIn("load `references/experience-review.md`", agent_tools)
        self.assertIn("load `references/experience-review.md`", cli_reference)
        for workflow in ("think", "backfill", "career"):
            workflow_sop = (root / f"skills/work-brain/references/sops/{workflow}.sop.md").read_text(encoding="utf-8")
            self.assertIn("references/experience-review.md", workflow_sop)
        self.assertIn("skills/work-brain/references/experience-review.md", package)

    def test_sops_follow_agent_sop_structure_and_are_versioned(self) -> None:
        sop_dir = Path(__file__).resolve().parents[1] / "skills/work-brain/references/sops"
        sop_files = sorted(sop_dir.glob("*.sop.md"))
        self.assertEqual(8, len(sop_files))
        for path in sop_files:
            text = path.read_text(encoding="utf-8")
            self.assertRegex(text, r"(?m)^WORK-BRAIN-SOP-[A-Z0-9-]+ v3$")
            self.assertRegex(text, r"(?m)^# (?!#).+$")
            for section in ("Overview", "Parameters", "Steps", "Examples", "Troubleshooting"):
                self.assertIn(f"## {section}", text, path.name)
            step_names = re.findall(r"(?m)^### \d+\. .+$", text)
            self.assertGreaterEqual(len(step_names), 2, path.name)
            expected_constraint_blocks = len(step_names) - (1 if path.name == "backfill.sop.md" else 0)
            self.assertEqual(expected_constraint_blocks, len(re.findall(r"(?m)^\*\*Constraints:\*\*$", text)), path.name)
            self.assertRegex(text, r"(?m)^- \*\*[a-z][a-z0-9_]*\*\* \((required|optional)")
        core = (sop_dir / "core-conversation.sop.md").read_text(encoding="utf-8")
        self.assertIn("Ask the following memory-gap question only when that assessment identifies a", core)
        self.assertIn("MUST NOT ask it merely to perform a closing ceremony", core)

    def test_workflow_selection_is_deterministic(self) -> None:
        self.assertEqual("think", select_workflow("think with me"))
        self.assertEqual("close-day", select_workflow("close my day"))
        self.assertEqual("open-day", select_workflow("open my work journal"))
        self.assertEqual("think", select_workflow("start work brain"))
        self.assertEqual("operate", select_workflow(None, "operate"))
        self.assertEqual("think", select_workflow("something ambiguous"))

    def test_orchestrator_persists_turn_before_model_and_resolves_commit(self) -> None:
        model = ScriptedModel(drafts=[draft()])
        orchestrator = SessionOrchestrator(self.vault, model)
        session = orchestrator.start("I am deciding how to isolate imports.", workflow="think", domain_tags=["engineering"])
        self.assertEqual(RuntimeState.ACTIVE, orchestrator.state)
        self.assertEqual(2, len(self.vault.list_turns(session["session_id"])))
        entry = orchestrator.close()
        self.assertEqual(1, entry.revision)
        self.assertEqual(RuntimeState.COMMITTED, orchestrator.state)
        self.assertEqual(["respond", "commit_draft"], [call["kind"] for call in model.calls])
        self.assertEqual(["WORK-BRAIN-SKILL@2", "WORK-BRAIN-SOP-CORE@3", "WORK-BRAIN-SOP-THINK@3", "WORK-BRAIN-SCHEMA-COMMIT-DRAFT@1", "WORK-BRAIN-DOMAIN-TAGS@1", "WORK-BRAIN-PROBE-ENGINEERING@2"], self.vault.read_session(session["session_id"])["runtime"]["sops"])

    def test_cli_commit_draft_finalizes_lifecycle_and_status_ignores_stale_pending_flag(self) -> None:
        session = self.vault.create_session(
            started_at="2026-10-01T16:40:00+01:00",
            modes=["think"],
            runtime={"workflow": "think", "capture_status": "recoverable", "commit_status": "pending_auto_commit"},
        )
        self.vault.append_turn(session["session_id"], "user", "Preserve the bounded decision.")
        draft_path = Path(self.tempdir.name) / "commit-draft.json"
        draft_path.write_text(json.dumps(draft()), encoding="utf-8")

        with redirect_stdout(StringIO()):
            self.assertEqual(0, main([
                "--vault", str(self.vault.root), "commit-draft",
                "--session-id", session["session_id"], "--file", str(draft_path),
            ]))

        finalized = self.vault.read_session(session["session_id"])
        self.assertEqual("committed", finalized["runtime"]["commit_status"])
        self.assertEqual("committed", finalized["runtime"]["capture_status"])
        self.assertEqual("closed", finalized["runtime"]["capture_boundary"])
        self.assertIsNotNone(finalized["ended_at"])

        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, main([
                "--vault", str(self.vault.root), "session", "status",
                "--session-id", session["session_id"], "--json",
            ]))
        status = json.loads(output.getvalue())
        self.assertEqual("committed", status["lifecycle"])
        self.assertEqual("committed", status["commit_status"])
        self.assertTrue(status["has_committed_entry"])

        # Protect against the exact legacy shape that caused the dashboard bug.
        stale = self.vault.read_session(session["session_id"])
        stale["ended_at"] = None
        stale["runtime"]["commit_status"] = "pending_auto_commit"
        self.vault.update_session_metadata(session["session_id"], stale)
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, main([
                "--vault", str(self.vault.root), "session", "status",
                "--session-id", session["session_id"], "--json",
            ]))
        legacy_status = json.loads(output.getvalue())
        self.assertEqual("committed", legacy_status["lifecycle"])
        self.assertEqual("committed", legacy_status["commit_status"])

    def test_commit_result_distinguishes_source_success_from_projection_failure_and_is_idempotent(self) -> None:
        session = self.vault.create_session(started_at="2026-10-01T16:40:00+01:00", modes=["think"])
        self.vault.append_turn(session["session_id"], "user", "Keep the source commit durable.")
        original = self.vault.reconcile_database
        self.vault.reconcile_database = lambda: (_ for _ in ()).throw(RuntimeError("projection unavailable"))
        first = CommitResolver(self.vault).publish_result(session["session_id"], draft(), workflow="think")
        self.assertEqual("committed", first.source_status)
        self.assertEqual("failed", first.maintenance.projection_status)
        self.vault.reconcile_database = original
        second = CommitResolver(self.vault).publish_result(session["session_id"], draft(), workflow="think")
        self.assertEqual(first.entry_id, second.entry_id)
        self.assertEqual(first.revision, second.revision)
        self.assertEqual(1, len(self.vault.all_entry_revisions()))
        self.vault.rebuild_all()
        self.assertEqual([], self.vault.doctor())

    def test_invalid_draft_does_not_publish_planned_catalog_objects(self) -> None:
        session = self.vault.create_session(started_at="2026-10-01T16:40:00+01:00", modes=["think"])
        self.vault.append_turn(session["session_id"], "user", "Reject invalid provenance before catalog writes.")
        invalid = draft()
        invalid["source_entry_refs"] = [{"entry_id": new_uuid7(), "revision": 1}]
        with self.assertRaises(ValidationError):
            CommitResolver(self.vault).publish(session["session_id"], invalid, workflow="think")
        self.assertEqual([], list((self.vault.root / "catalog/entities").glob("*.json")))
        self.assertEqual([], list((self.vault.root / "catalog/artifacts").glob("*.json")))
        self.assertEqual([], self.vault.all_entry_revisions())

    def test_retrieval_publication_failure_reports_source_success_and_rebuilds(self) -> None:
        session = self.vault.create_session(started_at="2026-10-01T16:40:00+01:00", modes=["think"])
        self.vault.append_turn(session["session_id"], "user", "Keep the source when index publication fails.")
        with patch("work_brain.retrieval.EvidenceRetriever.index_entry", side_effect=RuntimeError("index publication unavailable")):
            result = CommitResolver(self.vault).publish_result(session["session_id"], draft(), workflow="think")
        self.assertEqual("committed", result.source_status)
        self.assertEqual("failed", result.maintenance.retrieval_status)
        self.assertEqual(1, len(self.vault.all_entry_revisions()))
        EvidenceRetriever(self.vault).reindex()
        self.assertEqual([], self.vault.doctor())

    def test_codex_hook_failure_is_harmless_but_observable(self) -> None:
        payload = json.dumps({"event": "UserPromptSubmit", "session_id": "hook-failure"})
        with patch("sys.stdin", StringIO(payload)), redirect_stdout(StringIO()) as output:
            self.assertEqual(0, main(["--vault", str(self.vault.root), "capture-hook", "--host", "codex"]))
        self.assertEqual({}, json.loads(output.getvalue()))
        health = self.vault.capture_hook_health()
        self.assertEqual("codex", health[-1]["host"])
        self.assertEqual("capture_hook_failure", health[-1]["category"])

    def test_capture_hook_success_recovers_same_host_without_erasing_history(self) -> None:
        record_capture_hook_failure(self.vault, host="codex", category="capture_hook_failure", error=ValueError("old failure"))
        history_path = self.vault.root / "context/capture-hook-health.jsonl"
        history_before = history_path.read_text(encoding="utf-8")
        self.assertEqual(["codex"], [item["host"] for item in self.vault.capture_hook_health()])

        with patch("sys.stdin", StringIO(json.dumps({"event": "SessionStart", "session_id": "healthy-codex"}))), redirect_stdout(StringIO()):
            self.assertEqual(0, main(["--vault", str(self.vault.root), "capture-hook", "--host", "codex"]))

        self.assertEqual([], self.vault.capture_hook_health())
        self.assertEqual(history_before, history_path.read_text(encoding="utf-8"))
        status = json.loads((self.vault.root / "context/capture-hook-status.json").read_text(encoding="utf-8"))
        self.assertEqual("healthy", status["codex"]["status"])
        self.assertIn("last_failure", status["codex"])

    def test_capture_hook_health_is_independent_per_host_and_reopens_on_new_failure(self) -> None:
        record_capture_hook_failure(self.vault, host="codex", category="capture_hook_failure", error=ValueError("codex failure"))
        with patch("sys.stdin", StringIO(json.dumps({"event": "SessionStart", "session_id": "healthy-claude"}))), redirect_stdout(StringIO()):
            self.assertEqual(0, main(["--vault", str(self.vault.root), "capture-hook", "--host", "claude-code"]))
        self.assertEqual(["codex"], [item["host"] for item in self.vault.capture_hook_health()])

        with patch("sys.stdin", StringIO(json.dumps({"event": "SessionStart", "session_id": "healthy-codex"}))), redirect_stdout(StringIO()):
            self.assertEqual(0, main(["--vault", str(self.vault.root), "capture-hook", "--host", "codex"]))
        self.assertEqual([], self.vault.capture_hook_health())

        record_capture_hook_failure(self.vault, host="codex", category="capture_hook_failure", error=ValueError("new failure"))
        self.assertEqual(["codex"], [item["host"] for item in self.vault.capture_hook_health()])

    def test_legacy_failure_history_is_unresolved_until_same_host_succeeds(self) -> None:
        history_path = self.vault.root / "context/capture-hook-health.jsonl"
        append_jsonl(history_path, {
            "recorded_at": "2026-10-06T17:14:03+01:00",
            "host": "codex",
            "category": "capture_hook_failure",
            "error_type": "ValueError",
            "message": "legacy failure",
        })
        self.assertFalse((self.vault.root / "context/capture-hook-status.json").exists())
        self.assertEqual(["codex"], [item["host"] for item in self.vault.capture_hook_health()])

        with patch("sys.stdin", StringIO(json.dumps({"event": "SessionStart", "session_id": "legacy-recovered"}))), redirect_stdout(StringIO()):
            self.assertEqual(0, main(["--vault", str(self.vault.root), "capture-hook", "--host", "codex"]))
        self.assertEqual([], self.vault.capture_hook_health())
        self.assertEqual(1, len(history_path.read_text(encoding="utf-8").splitlines()))

    def test_status_and_doctor_report_only_unresolved_capture_hook_failures(self) -> None:
        record_capture_hook_failure(self.vault, host="codex", category="capture_hook_failure", error=ValueError("failure"))
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, main(["--vault", str(self.vault.root), "status", "--json"]))
        self.assertEqual(1, len(json.loads(output.getvalue())["capture_hook_health"]))
        self.assertTrue(any("unresolved failure" in item for item in self.vault.doctor()))

        with patch("sys.stdin", StringIO(json.dumps({"event": "SessionStart", "session_id": "doctor-recovered"}))), redirect_stdout(StringIO()):
            self.assertEqual(0, main(["--vault", str(self.vault.root), "capture-hook", "--host", "codex"]))
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, main(["--vault", str(self.vault.root), "status", "--json"]))
        self.assertEqual([], json.loads(output.getvalue())["capture_hook_health"])
        self.assertFalse(any("capture hook has" in item for item in self.vault.doctor()))

    def test_doctor_distinguishes_corrupt_derived_database(self) -> None:
        broken = Vault(Path(self.tempdir.name) / "broken-doctor").initialize()
        broken.database_path.write_text("not sqlite", encoding="utf-8")
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(4, main(["--vault", str(broken.root), "doctor", "--json"]))
        result = json.loads(output.getvalue())
        self.assertFalse(result["ok"])
        self.assertEqual("failed", result["embedding"]["status"])
        self.assertTrue(any("SQLite" in item or "retrieval health" in item for item in result["diagnostics"]))

    def test_model_tool_calls_execute_and_return_without_polluting_raw_turns(self) -> None:
        model = ScriptedModel(responses=[
            ModelResponse("", ({"id": "call-1", "name": "get_recent_work", "arguments": {"limit": 1}},)),
            ModelResponse("There is no recent committed work yet."),
        ])
        orchestrator = SessionOrchestrator(self.vault, model)
        session = orchestrator.start("What have I already captured?", workflow="operate")
        self.assertEqual(2, len(self.vault.list_turns(session["session_id"])))
        self.assertEqual("There is no recent committed work yet.", self.vault.list_turns(session["session_id"])[1]["content"])
        self.assertEqual(["respond", "respond"], [call["kind"] for call in model.calls])
        self.assertEqual(3, model.calls[1]["message_count"])
        self.assertEqual("tool", orchestrator._messages[2]["role"])
        self.assertEqual(4, len(orchestrator._messages))
        self.assertEqual("There is no recent committed work yet.", orchestrator._messages[3]["content"])

    def test_close_day_record_includes_day_entries_unjournaled_entries_and_uncommitted_raw(self) -> None:
        committed = self.vault.create_session(
            started_at="2026-10-01T09:00:00+01:00", modes=["think"], domain_tags=["engineering"],
        )
        self.vault.append_turn(committed["session_id"], "user", "Capture the completed import decision.")
        CommitResolver(self.vault).publish(committed["session_id"], draft(), workflow="think")

        unjournaled = self.vault.create_session(
            started_at="2026-08-01T09:00:00+01:00", modes=["think"], domain_tags=["engineering"],
        )
        self.vault.append_turn(unjournaled["session_id"], "user", "Capture an older committed item.")
        CommitResolver(self.vault).publish(unjournaled["session_id"], draft(), workflow="think")
        unjournaled_journal = self.vault.root / "journal/2026/08/2026-08-01.md"
        unjournaled_journal.unlink()

        raw = self.vault.create_session(
            started_at="2026-10-01T16:00:00+01:00",
            modes=["operate"],
            runtime={"workflow": "operate", "capture_status": "recoverable", "commit_status": "pending_auto_commit"},
        )
        self.vault.append_turn(raw["session_id"], "user", "Review the remaining follow-up work.")

        previous_day = self.vault.create_session(
            started_at="2026-08-01T16:00:00+01:00",
            modes=["think"],
            runtime={"workflow": "think", "capture_status": "recoverable", "commit_status": "pending_auto_commit"},
        )
        self.vault.append_turn(previous_day["session_id"], "user", "Older raw work.")

        registry = ToolRegistry(self.vault)
        names = {tool.name for tool in registry.definitions("close-day")}
        self.assertIn("get_close_day_record", names)
        result = registry.call("get_close_day_record", local_date="2026-10-01")

        self.assertTrue(result.ok)
        self.assertEqual("2026-10-01", result.data["local_date"])
        self.assertEqual([committed["entry_id"]], [item["entry_id"] for item in result.data["committed_entries"]])
        self.assertEqual(
            [unjournaled["entry_id"]],
            [item["entry_id"] for item in result.data["unjournaled_entries"]],
        )
        self.assertFalse(result.data["unjournaled_entries"][0]["journal_associated"])
        self.assertEqual(
            [previous_day["session_id"], raw["session_id"]],
            [item["session_id"] for item in result.data["uncommitted_raw_sessions"]],
        )
        self.assertEqual("Review the remaining follow-up work.", result.data["uncommitted_raw_sessions"][1]["turns"][0]["content"])

    def test_malformed_or_disallowed_tool_call_returns_structured_error(self) -> None:
        model = ScriptedModel(responses=[
            ModelResponse("", ({"id": "call-1", "name": "filesystem", "arguments": {}},)),
            ModelResponse("I could not use that unavailable tool."),
        ])
        orchestrator = SessionOrchestrator(self.vault, model)
        orchestrator.start("Inspect the current work.", workflow="operate")
        self.assertIn("not available in workflow", orchestrator._messages[2]["content"])

    def test_runtime_owned_fields_are_rejected_before_publication(self) -> None:
        validator = CommitDraftValidator()
        with self.assertRaises(ValidationError):
            validator.validate(draft(bad_runtime_field=True), turn_count=1, workflow="think")

    def test_commit_draft_requires_workspace_and_project_classification(self) -> None:
        value = draft()
        value.pop("workspace")
        with self.assertRaisesRegex(ValidationError, "must include workspace"):
            CommitDraftValidator().validate(value, turn_count=1, workflow="think")

        value = draft()
        value.pop("project")
        with self.assertRaisesRegex(ValidationError, "must include project"):
            CommitDraftValidator().validate(value, turn_count=1, workflow="think")

        value = draft()
        value["project"] = None
        with self.assertRaisesRegex(ValidationError, "project must be a required non-empty string"):
            CommitDraftValidator().validate(value, turn_count=1, workflow="think")

    def _publish_context_ref_draft(self, value: dict) -> Any:
        session = self.vault.create_session(started_at="2026-10-01T16:40:00+01:00", modes=["think"])
        self.vault.append_turn(session["session_id"], "user", "Use the resolved work context.")
        return CommitResolver(self.vault).publish(session["session_id"], value, workflow="think")

    def test_existing_context_refs_commit_exact_catalog_ids(self) -> None:
        workspace = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        project = self.vault.upsert_entity(kind="project", canonical_name="Authentication", aliases=["Auth"])
        value = draft()
        value.update({
            "workspace": "Ranq", "workspace_ref": workspace["entity_id"],
            "project": "Authentication", "project_ref": project["entity_id"],
        })

        entry = self._publish_context_ref_draft(value)

        self.assertEqual(workspace["entity_id"], entry.workspace_entity_id)
        self.assertEqual(project["entity_id"], entry.project_entity_id)

    def test_explicit_project_ref_bypasses_ambiguous_name_resolution(self) -> None:
        workspace = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        first = self.vault.upsert_entity(kind="project", canonical_name="Auth")
        second = self.vault.upsert_entity(kind="project", canonical_name="Auth")
        value = draft()
        value.update({
            "workspace": "Ranq", "workspace_ref": workspace["entity_id"],
            "project": "Auth", "project_ref": second["entity_id"],
        })

        entry = self._publish_context_ref_draft(value)

        self.assertEqual(second["entity_id"], entry.project_entity_id)
        self.assertNotEqual(first["entity_id"], entry.project_entity_id)

    def test_nonexistent_context_ref_is_rejected(self) -> None:
        value = draft()
        value["workspace_ref"] = new_uuid7()

        with self.assertRaisesRegex(ValidationError, "workspace_ref does not identify an existing workspace"):
            self._publish_context_ref_draft(value)
        self.assertEqual([], self.vault.all_entry_revisions())

    def test_context_refs_must_have_the_expected_kind(self) -> None:
        workspace = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        project = self.vault.upsert_entity(kind="project", canonical_name="Authentication")

        value = draft()
        value["workspace_ref"] = project["entity_id"]
        with self.assertRaisesRegex(ValidationError, "workspace_ref must identify a workspace"):
            self._publish_context_ref_draft(value)

        value = draft()
        value["project_ref"] = workspace["entity_id"]
        with self.assertRaisesRegex(ValidationError, "project_ref must identify a project"):
            self._publish_context_ref_draft(value)
        self.assertEqual([], self.vault.all_entry_revisions())

    def test_context_ref_name_mismatch_is_rejected(self) -> None:
        workspace = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        value = draft()
        value.update({"workspace": "Other", "workspace_ref": workspace["entity_id"]})

        with self.assertRaisesRegex(ValidationError, "workspace_ref does not match"):
            self._publish_context_ref_draft(value)
        self.assertEqual([], self.vault.all_entry_revisions())

    def test_valid_context_refs_do_not_create_entities_or_modify_aliases(self) -> None:
        workspace = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq", aliases=["R"])
        project = self.vault.upsert_entity(kind="project", canonical_name="Authentication", aliases=["Auth"])
        before = {
            path.name: path.read_text(encoding="utf-8")
            for path in (self.vault.root / "catalog/entities").glob("*.json")
        }
        value = draft()
        value.update({
            "workspace": "Ranq",
            "workspace_ref": workspace["entity_id"],
            "project": "Auth", "project_ref": project["entity_id"],
        })

        self._publish_context_ref_draft(value)

        after = {
            path.name: path.read_text(encoding="utf-8")
            for path in (self.vault.root / "catalog/entities").glob("*.json")
        }
        self.assertEqual(before, after)

    def test_name_only_context_drafts_remain_compatible(self) -> None:
        existing_workspace = self.vault.upsert_entity(kind="workspace", canonical_name="Work Brain")
        existing_project = self.vault.upsert_entity(kind="project", canonical_name="Import boundary")
        entry = self._publish_context_ref_draft(draft())

        self.assertEqual(existing_workspace["entity_id"], entry.workspace_entity_id)
        self.assertEqual(existing_project["entity_id"], entry.project_entity_id)

        new_value = draft()
        new_value.update({"workspace": "New workspace", "project": "New project"})
        new_entry = self._publish_context_ref_draft(new_value)
        self.assertIsNotNone(new_entry.workspace_entity_id)
        self.assertIsNotNone(new_entry.project_entity_id)
        self.assertEqual(4, len(list((self.vault.root / "catalog/entities").glob("*.json"))))

    def test_name_only_project_resolution_is_scoped_to_workspace(self) -> None:
        ranq = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        personal = self.vault.upsert_entity(kind="workspace", canonical_name="Personal")
        existing = self.vault.upsert_entity(
            kind="project", canonical_name="Website", workspace_entity_id=ranq["entity_id"],
        )

        ranq_draft = draft()
        ranq_draft.update({"workspace": "Ranq", "project": "Website"})
        ranq_entry = self._publish_context_ref_draft(ranq_draft)
        self.assertEqual(existing["entity_id"], ranq_entry.project_entity_id)

        personal_draft = draft()
        personal_draft.update({"workspace": "Personal", "project": "Website"})
        personal_entry = self._publish_context_ref_draft(personal_draft)
        self.assertNotEqual(existing["entity_id"], personal_entry.project_entity_id)
        created = json.loads(
            (self.vault.root / "catalog/entities" / f"{personal_entry.project_entity_id}.json").read_text()
        )
        self.assertEqual(personal["entity_id"], created["workspace_entity_id"])

    def test_explicit_project_ref_cannot_cross_workspace_ownership(self) -> None:
        ranq = self.vault.upsert_entity(kind="workspace", canonical_name="Ranq")
        personal = self.vault.upsert_entity(kind="workspace", canonical_name="Personal")
        project = self.vault.upsert_entity(
            kind="project", canonical_name="Website", workspace_entity_id=ranq["entity_id"],
        )
        value = draft()
        value.update({
            "workspace": "Personal", "workspace_ref": personal["entity_id"],
            "project": "Website", "project_ref": project["entity_id"],
        })
        with self.assertRaisesRegex(ValidationError, "different workspace"):
            self._publish_context_ref_draft(value)

    def test_new_workspace_and_project_are_persisted_with_ownership(self) -> None:
        value = draft()
        value.update({"workspace": "New workspace", "project": "New project"})

        entry = self._publish_context_ref_draft(value)

        workspace = next(
            json.loads(path.read_text())
            for path in (self.vault.root / "catalog/entities").glob("*.json")
            if json.loads(path.read_text())["entity_id"] == entry.workspace_entity_id
        )
        project = json.loads(
            (self.vault.root / "catalog/entities" / f"{entry.project_entity_id}.json").read_text()
        )
        self.assertEqual("workspace", workspace["kind"])
        self.assertEqual(workspace["entity_id"], project["workspace_entity_id"])

    def test_persisted_context_fields_are_not_commitdraft_inputs(self) -> None:
        value = draft()
        value["project_entity_id"] = new_uuid7()
        with self.assertRaisesRegex(ValidationError, "use workspace_ref/project_ref"):
            CommitDraftValidator().validate(value, turn_count=1, workflow="think")

    def test_domain_tags_have_no_artificial_count_limit(self) -> None:
        value = draft()
        value["domain_tags"] = [f"topic-{index}" for index in range(25)]
        validated = CommitDraftValidator().validate(value, turn_count=1, workflow="think")
        self.assertEqual(25, len(validated.domain_tags))

    def test_domain_tags_normalize_technical_terms_for_retrieval(self) -> None:
        value = draft()
        value["domain_tags"] = ["Security", "authentication", "login", "access control", "authentication"]
        validated = CommitDraftValidator().validate(value, turn_count=1, workflow="think")
        self.assertEqual(["security", "authentication", "login", "access-control"], validated.domain_tags)

    def test_commit_draft_rejects_legacy_domains_field(self) -> None:
        value = draft()
        value.pop("domain_tags")
        value["domains"] = ["engineering"]
        with self.assertRaisesRegex(ValidationError, "uses domain_tags"):
            CommitDraftValidator().validate(value, turn_count=1, workflow="think")

    def test_experience_entity_candidate_defaults_to_experience_relation(self) -> None:
        value = draft()
        value["entity_candidates"] = [{
            "kind": "experience",
            "canonical_name": "Auth migration decision",
        }]
        validated = CommitDraftValidator().validate(value, turn_count=1, workflow="think")
        self.assertEqual("experience", validated.entity_candidates[0]["relation"])

    def test_existing_experience_contract_requires_and_accepts_explicit_relation(self) -> None:
        experience = self.vault.upsert_entity(kind="experience", canonical_name="Auth migration")
        valid = draft()
        valid["entity_candidates"] = [{
            "entity_id": experience["entity_id"], "kind": "experience", "relation": "experience",
        }]
        session = self.vault.create_session(started_at="2026-10-01T10:00:00+01:00")
        self.vault.append_turn(session["session_id"], "user", "The authentication migration changed direction.")
        entry = CommitResolver(self.vault).publish(session["session_id"], valid, workflow="think")
        self.assertEqual([{"entity_id": experience["entity_id"], "relation": "experience"}], entry.entity_refs)

        invalid = draft()
        invalid["entity_candidates"] = [{
            "entity_id": experience["entity_id"], "kind": "experience", "relation": "subject",
        }]
        with self.assertRaisesRegex(ValidationError, "relation=experience"):
            CommitDraftValidator().validate(invalid, turn_count=1, workflow="think")

    def test_commit_statements_require_exact_source_turns(self) -> None:
        value = draft()
        value["sections"]["context"][0]["source_turns"] = []
        with self.assertRaises(ValidationError):
            CommitDraftValidator().validate(value, turn_count=1, workflow="think")

    def test_commit_rejects_assistant_only_source_turns(self) -> None:
        session = self.vault.create_session(modes=["think"])
        self.vault.append_turn(session["session_id"], "assistant", "Synthetic summary")
        with self.assertRaisesRegex(ValidationError, "user-authored source turn"):
            CommitResolver(self.vault).publish(session["session_id"], draft(), workflow="think")
        self.assertEqual([], self.vault.all_current_entries())

    def test_transcript_import_preserves_supplied_raw_turns(self) -> None:
        result = HarnessCaptureService(self.vault).import_transcript({
            "source": "manual smoke transcript",
            "started_at": "2026-10-01T13:30:00+01:00",
            "workflow": "think",
            "modes": ["think"],
            "domain_tags": ["product"],
            "turns": [
                {"role": "user", "content": "I changed the design after testing the first approach."},
                {"role": "assistant", "content": "What evidence changed your mind?"},
            ],
        })
        self.assertEqual("imported", result["status"])
        self.assertTrue(result["raw_turns_preserved"])
        session = self.vault.read_session(result["session_id"])
        self.assertEqual("imported", session["runtime"]["capture_fidelity"])
        self.assertEqual(
            ["I changed the design after testing the first approach.", "What evidence changed your mind?"],
            [turn["content"] for turn in self.vault.list_turns(result["session_id"])],
        )

    def test_commit_repair_is_bounded_and_raw_session_remains_recoverable(self) -> None:
        model = ScriptedModel(drafts=[draft(bad_runtime_field=True)], repairs=[])
        orchestrator = SessionOrchestrator(self.vault, model)
        session = orchestrator.start("Keep this raw conversation.", workflow="think")
        with self.assertRaises(ValidationError):
            orchestrator.close()
        self.assertEqual(RuntimeState.RECOVERABLE, orchestrator.state)
        self.assertEqual(2, len(self.vault.list_turns(session["session_id"])))
        self.assertEqual([], self.vault.all_current_entries())
        self.assertEqual(2, len([call for call in model.calls if call["kind"] == "repair_commit_draft"]))

    def test_backfill_requires_historical_occurrence_and_tools_are_high_level(self) -> None:
        validator = CommitDraftValidator()
        self.assertEqual("reconstructed", "reconstructed" if validator.validate(draft(workflow="backfill"), turn_count=1, workflow="backfill") else "")
        registry = ToolRegistry(self.vault)
        self.assertEqual({"resolve_context", "get_current_state", "get_recent_work"}, {tool.name for tool in registry.definitions("open-day")})
        self.assertIn("resolve_context", {tool.name for tool in registry.definitions("close-day")})
        self.assertIn("list_post_close_communication_profiles", {tool.name for tool in registry.definitions("close-day")})
        self.assertFalse(any(tool.name in {"sql", "filesystem", "vector"} for tool in registry.definitions("think")))

    def test_resolver_owns_catalog_and_state_ids(self) -> None:
        model_draft = draft()
        model_draft["workspace"] = "Ranq"
        model_draft["project"] = "Import Service"
        model_draft["state_changes"] = [{"operation": "create", "kind": "task", "fields": {"title": "Run import experiment"}, "source_turns": [1]}]
        model = ScriptedModel(drafts=[model_draft])
        orchestrator = SessionOrchestrator(self.vault, model)
        session = orchestrator.start("We need to run an import experiment.", workflow="operate")
        orchestrator.close()
        self.assertEqual(2, len(list((self.vault.root / "catalog/entities").glob("*.json"))))
        state = json.loads((self.vault.root / "state/current.json").read_text(encoding="utf-8"))
        self.assertEqual("Run import experiment", state["items"][0]["title"])
        entry = self.vault.get_current_entry(session["entry_id"])
        self.assertIsNotNone(entry.workspace_entity_id)
        self.assertIsNotNone(entry.project_entity_id)
        self.assertEqual("operate", self.vault.get_current_entry(session["entry_id"]).modes[0])

    def test_context_pressure_rolls_to_a_new_session(self) -> None:
        model = ScriptedModel(drafts=[draft(), draft()], context_window=5_700, output_reserve=300)
        orchestrator = SessionOrchestrator(self.vault, model)
        first = orchestrator.start("Short first topic.", workflow="think")
        orchestrator.turn("x" * 2_000)
        orchestrator.turn("y" * 1_000)
        sessions = self.vault.all_sessions()
        self.assertGreaterEqual(len(sessions), 2)
        self.assertEqual("Short first topic.", self.vault.list_turns(first["session_id"])[0]["content"])
        # Each bounded context may commit before opening a continuation.  The
        # exact number depends on the planner threshold, but the original
        # work must have produced at least one durable entry.
        self.assertGreaterEqual(len(self.vault.all_current_entries()), 1)

    def test_close_day_can_finish_without_publishing_new_evidence(self) -> None:
        model = ScriptedModel(responses=["The day is already represented; nothing new needs recording."])
        orchestrator = SessionOrchestrator(self.vault, model)
        session = orchestrator.start("close my day")
        orchestrator.complete_without_commit()
        self.assertEqual(RuntimeState.COMMITTED, orchestrator.state)
        self.assertEqual([], self.vault.all_current_entries())
        self.assertIsNotNone(self.vault.read_session(session["session_id"])["ended_at"])
        self.assertEqual("no_new_evidence", self.vault.read_session(session["session_id"])["runtime"]["commit_status"])

    def test_start_commits_a_stale_capture_before_opening_new_session(self) -> None:
        capture = HarnessCaptureService(self.vault)
        old = capture.handle(normalize_capture_event("codex", {
            "event": "UserPromptSubmit", "session_id": "rollover-host",
            "prompt": "work brain: capture the old decision",
            "recorded_at": "2026-09-29T10:00:00+01:00",
        }))
        capture.handle(normalize_capture_event("codex", {
            "event": "SessionEnd", "session_id": "rollover-host",
            "recorded_at": "2026-09-29T10:01:00+01:00",
        }))
        capture.rollover_stale_sessions(reference_at="2026-10-01T10:00:00+01:00")
        model = ScriptedModel(drafts=[draft()])
        orchestrator = SessionOrchestrator(self.vault, model)
        current = orchestrator.start("start my day", workflow="open-day", started_at="2026-10-01T10:00:00+01:00")
        self.assertEqual("committed", orchestrator.last_rollover_commits[0]["status"])
        self.assertEqual(old["session_id"], orchestrator.last_rollover_commits[0]["session_id"])
        self.assertEqual(1, len(self.vault.all_current_entries()))
        self.assertIsNotNone(self.vault.read_session(old["session_id"])["ended_at"])
        self.assertIsNone(self.vault.read_session(current["session_id"])["ended_at"])

    def test_non_day_activation_also_recovers_stale_capture(self) -> None:
        capture = HarnessCaptureService(self.vault)
        old = capture.handle(normalize_capture_event("codex", {
            "event": "UserPromptSubmit", "session_id": "think-rollover-host",
            "prompt": "work brain: capture the old architecture decision",
            "recorded_at": "2026-09-29T10:00:00+01:00",
        }))
        capture.handle(normalize_capture_event("codex", {
            "event": "SessionEnd", "session_id": "think-rollover-host",
            "recorded_at": "2026-09-29T10:01:00+01:00",
        }))
        capture.rollover_stale_sessions(reference_at="2026-10-01T10:00:00+01:00")
        orchestrator = SessionOrchestrator(self.vault, ScriptedModel(drafts=[draft()]))
        current = orchestrator.start("think with me about the next decision", workflow="think", started_at="2026-10-01T10:00:00+01:00")
        self.assertEqual("think", orchestrator.workflow)
        self.assertEqual(old["session_id"], orchestrator.last_rollover_commits[0]["session_id"])
        self.assertEqual(1, len(self.vault.all_current_entries()))
        self.assertIsNone(self.vault.read_session(current["session_id"])["ended_at"])

    def test_next_live_start_commits_closed_pending_boundary_without_duplicate_source(self) -> None:
        capture = HarnessCaptureService(self.vault)
        old = capture.handle(normalize_capture_event("codex", {
            "event": "UserPromptSubmit", "session_id": "same-day-host",
            "prompt": "work brain: preserve this bounded decision",
            "recorded_at": "2026-10-01T10:00:00+01:00",
        }))
        capture.handle(normalize_capture_event("codex", {
            "event": "SessionEnd", "session_id": "same-day-host",
            "recorded_at": "2026-10-01T10:01:00+01:00",
        }))
        closed = self.vault.read_session(old["session_id"])
        self.assertIsNotNone(closed["ended_at"])
        self.assertEqual("pending_auto_commit", closed["runtime"]["commit_status"])

        model = ScriptedModel(drafts=[draft()], responses=["The next bounded session is ready."])
        orchestrator = SessionOrchestrator(self.vault, model)
        current = orchestrator.start("start my day", workflow="open-day", started_at="2026-10-01T10:02:00+01:00")
        self.assertEqual("committed", orchestrator.last_rollover_commits[0]["status"])
        self.assertEqual(old["session_id"], orchestrator.last_rollover_commits[0]["session_id"])
        self.assertEqual("committed", self.vault.read_session(old["session_id"])["runtime"]["commit_status"])
        self.assertIsNone(self.vault.read_session(current["session_id"])["ended_at"])
        self.assertEqual(1, len(self.vault.all_current_entries()))

    def test_active_turn_can_route_to_close_day_without_rewriting_raw_text(self) -> None:
        model = ScriptedModel(responses=["The day is already represented; nothing new needs recording.", "The close-day check is complete."])
        orchestrator = SessionOrchestrator(self.vault, model)
        session = orchestrator.start("start my day")
        orchestrator.turn("close my day")
        self.assertEqual("close-day", orchestrator.workflow)
        self.assertEqual("close my day", self.vault.list_turns(session["session_id"])[2]["content"])
        self.assertEqual("close-day", self.vault.read_session(session["session_id"])["runtime"]["workflow"])

    def test_reextract_creates_revision_without_rewriting_turns(self) -> None:
        model = ScriptedModel(drafts=[draft(), draft()])
        orchestrator = SessionOrchestrator(self.vault, model)
        session = orchestrator.start("Capture this once.", workflow="think")
        orchestrator.close()
        before = self.vault.list_turns(session["session_id"])
        second = orchestrator.reextract(session["session_id"], workflow="think")
        self.assertEqual(2, second.revision)
        self.assertEqual(before, self.vault.list_turns(session["session_id"]))


if __name__ == "__main__":
    unittest.main()
