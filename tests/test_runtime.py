from __future__ import annotations

import tempfile
import unittest
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import re
from unittest.mock import patch

from work_brain import (
    CommitResolver,
    CommitDraftValidator,
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
from work_brain.capture import HarnessCaptureService, normalize_capture_event
from work_brain.cli import main


def draft(*, workflow: str = "think", bad_runtime_field: bool = False) -> dict:
    sections = {name: [] for name in (
        "context", "observations", "significance", "contribution", "reasoning", "evidence",
        "alternatives_tradeoffs", "decisions_actions", "expectations", "outcomes", "learning", "open_questions",
    )}
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
        self.assertEqual(["WORK-BRAIN-SKILL@2", "WORK-BRAIN-SOP-CORE@2", "WORK-BRAIN-SOP-THINK@2", "WORK-BRAIN-PROBE-ENGINEERING@2", "WORK-BRAIN-PROBE-PRODUCT@2"], loaded.identities)
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

    def test_sops_follow_agent_sop_structure_and_are_versioned(self) -> None:
        sop_dir = Path(__file__).resolve().parents[1] / "skills/work-brain/references/sops"
        sop_files = sorted(sop_dir.glob("*.sop.md"))
        self.assertEqual(8, len(sop_files))
        for path in sop_files:
            text = path.read_text(encoding="utf-8")
            self.assertRegex(text, r"(?m)^WORK-BRAIN-SOP-[A-Z0-9-]+ v2$")
            self.assertRegex(text, r"(?m)^# (?!#).+$")
            for section in ("Overview", "Parameters", "Steps", "Examples", "Troubleshooting"):
                self.assertIn(f"## {section}", text, path.name)
            step_names = re.findall(r"(?m)^### \d+\. .+$", text)
            self.assertGreaterEqual(len(step_names), 2, path.name)
            self.assertEqual(len(step_names), len(re.findall(r"(?m)^\*\*Constraints:\*\*$", text)), path.name)
            self.assertRegex(text, r"(?m)^- \*\*[a-z][a-z0-9_]*\*\* \((required|optional)")

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
        self.assertEqual(["WORK-BRAIN-SKILL@2", "WORK-BRAIN-SOP-CORE@2", "WORK-BRAIN-SOP-THINK@2", "WORK-BRAIN-SCHEMA-COMMIT-DRAFT@1", "WORK-BRAIN-DOMAIN-TAGS@1", "WORK-BRAIN-PROBE-ENGINEERING@2"], self.vault.read_session(session["session_id"])["runtime"]["sops"])

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

    def test_codex_hook_failure_is_harmless_but_observable(self) -> None:
        payload = json.dumps({"event": "UserPromptSubmit", "session_id": "hook-failure"})
        with patch("sys.stdin", StringIO(payload)), redirect_stdout(StringIO()) as output:
            self.assertEqual(0, main(["--vault", str(self.vault.root), "capture-hook", "--host", "codex"]))
        self.assertEqual({}, json.loads(output.getvalue()))
        health = self.vault.capture_hook_health()
        self.assertEqual("codex", health[-1]["host"])
        self.assertEqual("capture_hook_failure", health[-1]["category"])

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
        self.assertEqual({"get_current_state", "get_recent_work"}, {tool.name for tool in registry.definitions("open-day")})
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
