from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

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

    def test_inactive_chat_is_not_captured_and_explicit_capture_is_exact(self) -> None:
        service = HarnessCaptureService(self.vault)
        inactive = service.handle(normalize_capture_event("codex", {"event": "UserPromptSubmit", "session_id": "ordinary", "prompt": "Fix the build"}))
        self.assertEqual("inactive", inactive["status"])
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
        self.assertIsNone(session["ended_at"])
        self.assertEqual(1, len(self.vault.list_turns(started["session_id"])))
        self.assertEqual("recoverable", session["runtime"]["capture_status"])

    def test_explicit_close_deactivates_mapping(self) -> None:
        service = HarnessCaptureService(self.vault)
        started = service.handle(normalize_capture_event("codex", {"event": "UserPromptSubmit", "session_id": "close-1", "prompt": "work brain: close this"}))
        closed = service.stop_session(started["session_id"])
        self.assertTrue(closed["deactivated"])
        self.assertEqual("closed", self.vault.read_session(started["session_id"])["runtime"]["capture_status"])
        self.assertEqual({}, json.loads((self.vault.root / "context/capture-mappings.json").read_text(encoding="utf-8")))

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

        config_output = StringIO()
        config_path = root / "cli-config.json"
        with redirect_stdout(config_output):
            self.assertEqual(0, main(["--config", str(config_path), "config", "set-vault", str(self.vault.root)]))
            self.assertEqual(0, main(["--config", str(config_path), "state", "current"]))
        self.assertEqual({"items": []}, json.loads(config_output.getvalue().splitlines()[-1]))

    def test_capture_hook_rejects_malformed_payload_without_writing_source(self) -> None:
        service = HarnessCaptureService(self.vault)
        with self.assertRaises(Exception):
            normalize_capture_event("codex", {"event": "UserPromptSubmit", "session_id": "bad"})
        self.assertEqual([], self.vault.all_sessions())


if __name__ == "__main__":
    unittest.main()
