from __future__ import annotations

import json
import os
import shutil
import sys
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from work_brain.capture import HarnessCaptureService, normalize_capture_event
from work_brain.cli import main
from work_brain.config import resolve_vault_path, set_vault_path
from work_brain.setup import HarnessSetup
from work_brain.vault import Vault
from work_brain.orchestrator import route_prompt


class HarnessV3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.vault = Vault(root / "vault").initialize()
        self.home = root / "home"
        self.home.mkdir()
        self.skill_source = Path(__file__).resolve().parents[1] / "skills/work-brain"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_all_host_payloads_normalize_to_shared_events(self) -> None:
        codex = normalize_capture_event("codex", {"event": "UserPromptSubmit", "session_id": "c1", "prompt": "work brain: think", "model": "codex-model"})
        claude = normalize_capture_event("claude-code", {"hook_event_name": "Stop", "session_id": "c2", "last_assistant_message": "done"})
        cursor = normalize_capture_event("cursor", {"event": "afterAgentResponse", "conversation_id": "c3", "text": "done"})
        self.assertEqual(("codex", "user_prompt", "c1", "codex-model"), (codex.host, codex.kind, codex.host_session_id, codex.host_model))
        self.assertEqual(("claude-code", "assistant_message", "c2"), (claude.host, claude.kind, claude.host_session_id))
        self.assertEqual(("cursor", "assistant_message", "c3"), (cursor.host, cursor.kind, cursor.host_session_id))
        self.assertTrue(normalize_capture_event("claude-code", {"hook_event_name": "UserPromptSubmit", "session_id": "c4", "prompt": "/work-brain"}).explicit_activation)

    def test_skill_loading_does_not_activate_development_capture(self) -> None:
        prompts = (
            "edit the Work Brain think SOP",
            "fix the Work Brain capture tests",
            "change the Work Brain skill package",
        )
        service = HarnessCaptureService(self.vault)
        for index, prompt in enumerate(prompts):
            payload = {"event": "UserPromptSubmit", "session_id": f"development-{index}", "prompt": prompt,
                       "skill": "work-brain", "skill_invoked": True}
            event = normalize_capture_event("codex", payload)
            self.assertFalse(event.explicit_activation, prompt)
            result = service.handle(event)
            self.assertEqual("inactive", result["status"], prompt)
        self.assertEqual([], self.vault.all_sessions())
        explicit = normalize_capture_event("codex", {
            "event": "UserPromptSubmit", "session_id": "explicit-skill", "prompt": "inspect this",
            "skill": "work-brain", "skill_invocation_explicit": True,
        })
        self.assertTrue(explicit.explicit_activation)

    def test_speech_friendly_activation_is_table_driven_and_raw_safe(self) -> None:
        prompts = (
            "work brain start my day",
            "work brain: start my day",
            "work brain, start my day",
            "WORK BRAIN START MY DAY",
        )
        for index, prompt in enumerate(prompts):
            event = normalize_capture_event("codex", {"event": "UserPromptSubmit", "session_id": f"speech-{index}", "prompt": prompt})
            self.assertTrue(event.explicit_activation, prompt)
            self.assertEqual("open-day", event.workflow_hint, prompt)
            self.assertEqual("start my day", event.routed_content.casefold().strip(" ,:!?"), prompt.casefold().replace("work brain", "").strip(" ,:!?"))
            route = route_prompt(prompt)
            self.assertTrue(route.activation)
            self.assertEqual("start my day", route.routed_content.casefold().strip(" ,:!?"), prompt.casefold().replace("work brain", "").strip(" ,:!?"))
        self.assertFalse(normalize_capture_event("codex", {"event": "UserPromptSubmit", "session_id": "speech-no", "prompt": "brainstorm this"}).explicit_activation)
        self.assertFalse(normalize_capture_event("codex", {"event": "UserPromptSubmit", "session_id": "speech-no-2", "prompt": "think about this"}).explicit_activation)
        raw = "Work Brain, help me think through whether we should move this async"
        route = route_prompt(raw)
        self.assertTrue(route.activation)
        self.assertEqual("help me think through whether we should move this async", route.routed_content)
        service = HarnessCaptureService(self.vault)
        started = service.handle(normalize_capture_event("codex", {"event": "UserPromptSubmit", "session_id": "raw-safe", "prompt": raw}))
        self.assertEqual(raw, self.vault.list_turns(started["session_id"])[0]["content"])

    def test_general_workflow_routing_uses_one_normalization_stage(self) -> None:
        cases = (
            ("work brain what should I work on next", "operate"),
            ("work brain what should I work on", "operate"),
            ("Work Brain, where did I leave off?", "operate"),
            ("work brain catch me up", "operate"),
            ("work brain interview me", "career"),
            ("work brain help me think through queues", "think"),
            ("Start My Day.", "open-day"),
            ("Close My Day.", "close-day"),
        )
        for prompt, workflow in cases:
            route = route_prompt(prompt)
            self.assertEqual(workflow, route.workflow, prompt)
        self.assertFalse(route_prompt("brainstorm this").activation)
        self.assertFalse(route_prompt("this is a brain teaser").activation)
        self.assertEqual("think with me about queues.", route_prompt("WORK BRAIN, think with me about queues.").routed_content)
        capture = route_prompt("Capture This: I fixed the authentication issue")
        self.assertTrue(capture.activation)
        self.assertEqual("I fixed the authentication issue", capture.routed_content)
        self.assertIsNone(capture.lifecycle)
        self.assertEqual("commit-keep-active", route_prompt("That's Enough").lifecycle)
        self.assertEqual("deactivate", route_prompt("STOP WORK BRAIN").lifecycle)

    def test_inactive_chat_is_not_captured_and_explicit_capture_is_exact(self) -> None:
        service = HarnessCaptureService(self.vault)
        inactive = service.handle(normalize_capture_event("codex", {"event": "UserPromptSubmit", "session_id": "ordinary", "prompt": "Fix the build"}))
        self.assertEqual("inactive", inactive["status"])
        self.assertEqual("inactive", inactive["lifecycle"])
        self.assertIn("no raw turns are being saved", inactive["message"])
        self.assertEqual([], self.vault.all_sessions())

        service.handle(normalize_capture_event("codex", {"event": "SessionStart", "session_id": "active"}))
        started = service.handle(normalize_capture_event("codex", {"event": "UserPromptSubmit", "session_id": "active", "prompt": "work brain: think with me about the migration"}))
        self.assertTrue(started["captured"])
        service.handle(normalize_capture_event("codex", {"event": "Stop", "session_id": "active", "last_assistant_message": "What would success look like?"}))
        session = self.vault.read_session(started["session_id"])
        self.assertEqual("codex", session["runtime"]["host"])
        self.assertEqual("verbatim", session["runtime"]["capture_fidelity"])
        self.assertEqual(["work brain: think with me about the migration", "What would success look like?"], [turn["content"] for turn in self.vault.list_turns(started["session_id"])])

    def test_start_my_day_is_a_narrow_natural_activation_for_open_day(self) -> None:
        service = HarnessCaptureService(self.vault)
        started = service.handle(normalize_capture_event("codex", {"event": "UserPromptSubmit", "session_id": "day-1", "prompt": "Start My Day."}))
        self.assertTrue(started["captured"])
        self.assertEqual("open-day", started["workflow"])
        session = self.vault.read_session(started["session_id"])
        self.assertEqual("open-day", session["runtime"]["workflow"])
        self.assertEqual(["Start My Day."], [turn["content"] for turn in self.vault.list_turns(started["session_id"])])
        journal = service.handle(normalize_capture_event("codex", {"event": "UserPromptSubmit", "session_id": "day-2", "prompt": "Open My Work Journal!!!"}))
        self.assertEqual("open-day", journal["workflow"])

    def test_active_session_captures_follow_up_without_prefix(self) -> None:
        service = HarnessCaptureService(self.vault)
        started = service.handle(normalize_capture_event("codex", {"event": "UserPromptSubmit", "session_id": "follow-up", "prompt": "start work brain"}))
        follow_up = service.handle(normalize_capture_event("codex", {"event": "UserPromptSubmit", "session_id": "follow-up", "prompt": "The ordinary next question is still in scope."}))
        self.assertTrue(follow_up["captured"])
        self.assertEqual(["start work brain", "The ordinary next question is still in scope."], [turn["content"] for turn in self.vault.list_turns(started["session_id"])])

    def test_close_my_day_deactivates_without_creating_evidence(self) -> None:
        service = HarnessCaptureService(self.vault)
        started = service.handle(normalize_capture_event("codex", {"event": "UserPromptSubmit", "session_id": "close-day", "prompt": "work brain: think with me"}))
        before = [entry.to_dict() for entry in self.vault.all_current_entries()]
        requested = service.handle(normalize_capture_event("codex", {"event": "UserPromptSubmit", "session_id": "close-day", "prompt": "close my day"}))
        self.assertEqual("close-day", requested["workflow"])
        finished = service.handle(normalize_capture_event("codex", {"event": "Stop", "session_id": "close-day", "last_assistant_message": "No new durable evidence; your existing work remains unchanged."}))
        self.assertEqual("closed", finished["status"])
        self.assertTrue(finished["deactivated"])
        self.assertEqual({}, json.loads((self.vault.root / "context/capture-mappings.json").read_text(encoding="utf-8")))
        self.assertEqual(before, [entry.to_dict() for entry in self.vault.all_current_entries()])
        closed_session = self.vault.read_session(started["session_id"])
        self.assertEqual("closed", closed_session["runtime"]["capture_status"])
        self.assertIsNotNone(closed_session["ended_at"])

    def test_session_end_deactivates_without_fabricating_text(self) -> None:
        service = HarnessCaptureService(self.vault)
        started = service.handle(normalize_capture_event("cursor", {"event": "beforeSubmitPrompt", "conversation_id": "cursor-1", "prompt": "work brain: operate with me"}))
        ended = service.handle(normalize_capture_event("cursor", {"event": "sessionEnd", "conversation_id": "cursor-1"}))
        self.assertEqual("recoverable", ended["status"])
        session = self.vault.read_session(started["session_id"])
        self.assertIsNotNone(session["ended_at"])
        self.assertEqual(1, len(self.vault.list_turns(started["session_id"])))
        self.assertEqual("recoverable", session["runtime"]["capture_status"])
        self.assertEqual("closed", session["runtime"]["capture_boundary"])
        self.assertEqual("pending_auto_commit", session["runtime"]["commit_status"])

    def test_explicit_close_deactivates_mapping(self) -> None:
        service = HarnessCaptureService(self.vault)
        started = service.handle(normalize_capture_event("codex", {"event": "UserPromptSubmit", "session_id": "close-1", "prompt": "work brain: close this"}))
        closed = service.stop_session(started["session_id"])
        self.assertTrue(closed["deactivated"])
        self.assertEqual("closed", self.vault.read_session(started["session_id"])["runtime"]["capture_status"])
        self.assertEqual({}, json.loads((self.vault.root / "context/capture-mappings.json").read_text(encoding="utf-8")))

    def test_commit_rotation_keeps_host_capture_active_for_next_bounded_session(self) -> None:
        service = HarnessCaptureService(self.vault)
        started = service.handle(normalize_capture_event("codex", {
            "event": "UserPromptSubmit", "session_id": "day-long", "prompt": "start my day"
        }))
        rotated = service.rotate_session(started["session_id"])
        self.assertTrue(rotated["rotated"])
        self.assertNotEqual(started["session_id"], rotated["session_id"])
        previous = self.vault.read_session(started["session_id"])
        self.assertEqual("committed", previous["runtime"]["capture_status"])
        self.assertEqual("closed", previous["runtime"]["capture_boundary"])
        self.assertNotIn("commit_status", self.vault.read_session(rotated["session_id"])["runtime"])
        follow_up = service.handle(normalize_capture_event("codex", {
            "event": "UserPromptSubmit", "session_id": "day-long", "prompt": "I am now deciding the migration boundary."
        }))
        self.assertEqual(rotated["session_id"], follow_up["session_id"])
        self.assertEqual(["I am now deciding the migration boundary."], [
            turn["content"] for turn in self.vault.list_turns(rotated["session_id"])
        ])
        mapping = json.loads((self.vault.root / "context/capture-mappings.json").read_text(encoding="utf-8"))
        self.assertEqual(rotated["session_id"], mapping["codex:day-long"]["session_id"])

    def test_stop_work_brain_deactivates_after_visible_response(self) -> None:
        service = HarnessCaptureService(self.vault)
        started = service.handle(normalize_capture_event("codex", {
            "event": "UserPromptSubmit", "session_id": "stop-speech", "prompt": "start work brain"
        }))
        requested = service.handle(normalize_capture_event("codex", {
            "event": "UserPromptSubmit", "session_id": "stop-speech", "prompt": "STOP WORK BRAIN"
        }))
        self.assertTrue(requested["captured"])
        self.assertEqual("deactivate", normalize_capture_event("codex", {
            "event": "UserPromptSubmit", "session_id": "stop-speech", "prompt": "STOP WORK BRAIN"
        }).lifecycle)
        finished = service.handle(normalize_capture_event("codex", {
            "event": "Stop", "session_id": "stop-speech", "last_assistant_message": "Capture is closed."
        }))
        self.assertTrue(finished["deactivated"])
        self.assertEqual({}, json.loads((self.vault.root / "context/capture-mappings.json").read_text(encoding="utf-8")))
        self.assertEqual("closed", self.vault.read_session(started["session_id"])["runtime"]["capture_status"])

    def test_setup_is_idempotent_and_preserves_unrelated_settings(self) -> None:
        settings = self.home / ".codex/hooks.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"unrelated": {"keep": True}, "hooks": {"PreToolUse": [{"keep": True}]}}), encoding="utf-8")
        setup = HarnessSetup(home=self.home, skill_source=self.skill_source, executable="/opt/work-brain")
        first = setup.install("codex")
        second = setup.install("codex")
        self.assertTrue((self.home / ".agents/skills/work-brain/SKILL.md").exists())
        self.assertEqual({"keep": True}, json.loads(settings.read_text(encoding="utf-8"))["unrelated"])
        value = json.loads(settings.read_text(encoding="utf-8"))
        self.assertEqual(1, len(value["hooks"]["UserPromptSubmit"]))
        self.assertTrue(first.changes)
        self.assertFalse(any("added UserPromptSubmit" in change for change in second.changes))
        self.assertEqual([], setup.install("codex", check=True).warnings)

        cursor = setup.install("cursor")
        cursor_settings = json.loads((self.home / ".cursor/hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(1, cursor_settings["version"])
        self.assertEqual("command", cursor_settings["hooks"]["afterAgentResponse"][0]["type"])
        self.assertTrue(cursor.changes)

    def test_setup_accepts_equivalent_skill_link_from_another_install(self) -> None:
        target = self.home / ".agents/skills/work-brain"
        target.parent.mkdir(parents=True)
        equivalent = self.home / "packaged-skill"
        shutil.copytree(self.skill_source, equivalent)
        target.symlink_to(equivalent, target_is_directory=True)
        setup = HarnessSetup(home=self.home, skill_source=self.skill_source, executable="/opt/work-brain")
        report = setup.install("codex")
        self.assertIn("Skill link already matches canonical source", report.changes)

    def test_setup_uses_module_mode_for_current_python(self) -> None:
        setup = HarnessSetup(home=self.home, skill_source=self.skill_source, executable=sys.executable)
        self.assertIn(" -m work_brain.hook --host codex", setup.hook_command("codex"))

    def test_hook_module_does_not_import_application_heavy_modules(self) -> None:
        source_root = Path(__file__).resolve().parents[1] / "src"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(source_root)
        probe = subprocess.run(
            [sys.executable, "-c", "import sys; import work_brain.hook; print(sorted(name for name in sys.modules if name in {'work_brain.career', 'work_brain.commit', 'work_brain.instructions', 'work_brain.retrieval'}))"],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual("[]", probe.stdout.strip())

    def test_setup_can_find_packaged_skill_from_install_prefix(self) -> None:
        self.assertEqual(self.skill_source, HarnessSetup._default_skill_source())

    def test_setup_repairs_stale_work_brain_hooks_without_touching_unrelated_hooks(self) -> None:
        settings = self.home / ".codex/hooks.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"hooks": {
            "SessionStart": [
                {"hooks": [{"type": "command", "command": "old-python -m work_brain capture-hook --host codex"}]},
                {"hooks": [{"type": "command", "command": "old-python capture-hook --host codex"}]},
                {"hooks": [{"type": "command", "command": "keep-me"}]},
            ]
        }}), encoding="utf-8")
        setup = HarnessSetup(home=self.home, skill_source=self.skill_source, executable=sys.executable)
        setup.install("codex")
        value = json.loads(settings.read_text(encoding="utf-8"))
        commands = [hook["command"] for item in value["hooks"]["SessionStart"] for hook in item["hooks"]]
        self.assertEqual(sorted(["keep-me", setup.hook_command("codex")]), sorted(commands))

    def test_vault_resolution_precedence_and_cli_json(self) -> None:
        root = Path(self.tempdir.name)
        config = root / "config.json"
        explicit = root / "explicit"
        environment = root / "environment"
        configured = root / "configured"
        set_vault_path(configured, config)
        self.assertEqual(explicit.resolve(), resolve_vault_path(explicit, environ={"WORK_BRAIN_VAULT": str(environment)}, config_path=config))
        self.assertEqual(environment.resolve(), resolve_vault_path(None, environ={"WORK_BRAIN_VAULT": str(environment)}, config_path=config))
        self.assertEqual(configured.resolve(), resolve_vault_path(None, environ={}, config_path=config))

        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, main(["--vault", str(self.vault.root), "state", "current"]))
        self.assertEqual({"items": []}, json.loads(output.getvalue()))

        trailing_json_output = StringIO()
        with redirect_stdout(trailing_json_output):
            self.assertEqual(0, main(["--vault", str(self.vault.root), "state", "current", "--json"]))
        self.assertEqual({"items": []}, json.loads(trailing_json_output.getvalue()))

        config_output = StringIO()
        config_path = root / "cli-config.json"
        with redirect_stdout(config_output):
            self.assertEqual(0, main(["--config", str(config_path), "config", "set-vault", str(self.vault.root)]))
            self.assertEqual(0, main(["--config", str(config_path), "state", "current"]))
        self.assertEqual({"items": []}, json.loads(config_output.getvalue().splitlines()[-1]))

    def test_cli_reads_persisted_session_turns(self) -> None:
        service = HarnessCaptureService(self.vault)
        started = service.handle(normalize_capture_event("codex", {
            "event": "UserPromptSubmit", "session_id": "read-turns", "prompt": "work brain: inspect this"
        }))
        service.handle(normalize_capture_event("codex", {
            "event": "Stop", "session_id": "read-turns", "last_assistant_message": "Here is the persisted response."
        }))
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, main([
                "--vault", str(self.vault.root), "session", "turns",
                "--session-id", started["session_id"], "--limit", "1",
            ]))
        value = json.loads(output.getvalue())
        self.assertEqual(2, value["turn_count"])
        self.assertTrue(value["has_more"])
        self.assertEqual("work brain: inspect this", value["turns"][0]["content"])

    def test_session_status_reports_capture_health_without_raw_content(self) -> None:
        service = HarnessCaptureService(self.vault)
        started = service.handle(normalize_capture_event("codex", {
            "event": "UserPromptSubmit", "session_id": "status-view", "prompt": "work brain: inspect this"
        }))
        self.assertEqual("active_capture", started["lifecycle"])
        self.assertEqual(1, started["turn_count"])
        self.assertIsNotNone(started["last_captured_at"])
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, main([
                "--vault", str(self.vault.root), "session", "status",
                "--session-id", started["session_id"],
            ]))
        value = json.loads(output.getvalue())
        self.assertEqual("active_capture", value["lifecycle"])
        self.assertEqual(1, value["turn_count"])
        self.assertEqual(1, value["last_captured_turn"]["sequence"])
        self.assertEqual("active", value["capture_status"])
        self.assertTrue(value["capture_active"])
        self.assertEqual("Capture is active; raw turns are being saved.", value["message"])
        self.assertEqual("status-view", value["host_mappings"][0]["host_session_id"])
        self.assertNotIn("content", value["last_captured_turn"])

    def test_live_status_auto_detects_active_session_and_has_prompt_view(self) -> None:
        service = HarnessCaptureService(self.vault)
        started = service.handle(normalize_capture_event("codex", {
            "event": "UserPromptSubmit", "session_id": "live-status", "prompt": "work brain: show status"
        }))

        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, main(["--vault", str(self.vault.root), "status"]))
        self.assertIn("WORK BRAIN LIVE", output.getvalue())
        self.assertIn("Capture     ACTIVE", output.getvalue())
        self.assertIn(f"Session     {started['session_id']}", output.getvalue())
        self.assertIn("Turns       1", output.getvalue())

        quiet = StringIO()
        with redirect_stdout(quiet):
            self.assertEqual(0, main(["--vault", str(self.vault.root), "status", "--quiet"]))
        self.assertEqual("[Work Brain: ACTIVE · 1 turns · commit not_started]\n", quiet.getvalue())

    def test_live_status_json_distinguishes_inactive_from_recoverable(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, main(["--vault", str(self.vault.root), "status", "--json"]))
        value = json.loads(output.getvalue())
        self.assertEqual("inactive", value["lifecycle"])
        self.assertFalse(value["capture_active"])
        self.assertEqual([], value["active_sessions"])
        self.assertEqual([], value["recoverable_sessions"])

    def test_stale_rollover_closes_inactive_boundary_but_preserves_turns(self) -> None:
        service = HarnessCaptureService(self.vault)
        old = service.handle(normalize_capture_event("codex", {
            "event": "UserPromptSubmit", "session_id": "old-host", "prompt": "work brain: old decision",
            "recorded_at": "2026-09-29T10:00:00+01:00",
        }))
        service.handle(normalize_capture_event("codex", {
            "event": "SessionEnd", "session_id": "old-host",
            "recorded_at": "2026-09-29T10:01:00+01:00",
        }))
        yesterday = service.handle(normalize_capture_event("codex", {
            "event": "UserPromptSubmit", "session_id": "yesterday-host", "prompt": "work brain: yesterday",
            "recorded_at": "2026-09-30T10:00:00+01:00",
        }))
        service.handle(normalize_capture_event("codex", {
            "event": "SessionEnd", "session_id": "yesterday-host",
            "recorded_at": "2026-09-30T10:01:00+01:00",
        }))

        rolled = service.rollover_stale_sessions(reference_at="2026-10-01T10:00:00+01:00")
        self.assertEqual([old["session_id"]], [item["session_id"] for item in rolled])
        old_session = self.vault.read_session(old["session_id"])
        self.assertIsNotNone(old_session["ended_at"])
        self.assertEqual("rolled_over", old_session["runtime"]["capture_status"])
        self.assertEqual("pending_auto_commit", old_session["runtime"]["commit_status"])
        self.assertEqual("work brain: old decision", self.vault.list_turns(old["session_id"])[0]["content"])
        self.assertEqual("recoverable", self.vault.read_session(yesterday["session_id"])["runtime"]["capture_status"])

    def test_codex_capture_hook_emits_only_valid_host_output(self) -> None:
        payloads = (
            {"hook_event_name": "SessionStart", "session_id": "hook-session", "source": "startup"},
            {"hook_event_name": "UserPromptSubmit", "session_id": "hook-session", "turn_id": "turn-1", "prompt": "start my day"},
            {"hook_event_name": "Stop", "session_id": "hook-session", "turn_id": "turn-1", "last_assistant_message": "done"},
            {"hook_event_name": "SessionEnd", "session_id": "hook-session", "reason": "other"},
            {"hook_event_name": "Interrupt", "session_id": "hook-session", "turn_id": "turn-1"},
        )
        outputs = []
        for payload in payloads:
            output = StringIO()
            with redirect_stdout(output):
                with patch("sys.stdin", StringIO(json.dumps(payload))):
                    self.assertEqual(0, main(["--vault", str(self.vault.root), "capture-hook", "--host", "codex"]))
            outputs.append(json.loads(output.getvalue()))
        self.assertEqual({}, outputs[0])
        self.assertEqual("UserPromptSubmit", outputs[1]["hookSpecificOutput"]["hookEventName"])
        self.assertIn("Capture     ACTIVE", outputs[1]["hookSpecificOutput"]["additionalContext"])
        self.assertIn("Work Brain: ACTIVE", outputs[1]["systemMessage"])
        self.assertIn("2 turns", outputs[2]["systemMessage"])
        self.assertNotIn("hookSpecificOutput", outputs[2])
        self.assertEqual({}, outputs[3])
        self.assertEqual({}, outputs[4])

    def test_codex_capture_hook_swallows_internal_errors_at_host_boundary(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            with patch("sys.stdin", StringIO(json.dumps({"hook_event_name": "SessionStart"}))):
                self.assertEqual(0, main(["--vault", str(self.vault.root), "capture-hook", "--host", "codex"]))
        self.assertEqual({}, json.loads(output.getvalue()))

    def test_capture_hook_rejects_malformed_payload_without_writing_source(self) -> None:
        service = HarnessCaptureService(self.vault)
        with self.assertRaises(Exception):
            normalize_capture_event("codex", {"event": "UserPromptSubmit", "session_id": "bad"})
        self.assertEqual([], self.vault.all_sessions())


if __name__ == "__main__":
    unittest.main()
