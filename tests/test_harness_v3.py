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
