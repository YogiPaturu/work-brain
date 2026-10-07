from __future__ import annotations

from contextlib import redirect_stdout
import json
from io import StringIO
from pathlib import Path
import re
import tempfile
import unittest
import builtins
from unittest.mock import patch

from work_brain.cli import main
from work_brain.commit import CommitDraftValidator, commit_draft_contract
from work_brain.domain import ENTRY_SECTIONS
from work_brain.errors import ValidationError, VaultAccessError
from work_brain.cli import EXIT_PERSISTENCE
from work_brain.vault import Vault


ROOT = Path(__file__).resolve().parents[1]


def read_cli_schema() -> tuple[int, dict, str]:
    output = StringIO()
    with redirect_stdout(output):
        code = main(["schema", "commit-draft", "--json"])
    encoded = output.getvalue()
    return code, json.loads(encoded), encoded


def populated_template() -> dict:
    value = json.loads(json.dumps(commit_draft_contract()["template"]))
    value.update({
        "title": "CommitDraft schema contract",
        "summary": "The generated scaffold is used without changing structural keys.",
        "workspace": "Work Brain",
        "project": "CommitDraft schema",
    })
    value["sections"]["context"] = [{
        "text": "The generated scaffold supplies the canonical section keys.",
        "basis": "stated",
        "source_turns": [1],
    }]
    return value


class CommitDraftSchemaTests(unittest.TestCase):
    def test_vault_access_failure_has_stable_cli_error(self) -> None:
        output = StringIO()
        with redirect_stdout(output), patch("work_brain.cli._run", side_effect=VaultAccessError("Work Brain cannot write the vault at /private/vault: denied")):
            code = main(["--json", "init"])
        payload = json.loads(output.getvalue())
        self.assertEqual(EXIT_PERSISTENCE, code)
        self.assertEqual("vault_access_denied", payload["error"]["code"])
        self.assertIn("writable_roots", payload["error"]["hint"])
        self.assertIn("Do not modify the CommitDraft", payload["error"]["hint"])

    def test_commit_draft_lock_denial_preserves_recoverable_captured_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            vault = Vault(Path(temporary) / "vault").initialize()
            session = vault.create_session(modes=["think"], runtime={"workflow": "think"})
            vault.append_turn(session["session_id"], "user", "Preserve this captured turn if publication is denied.")
            original_session = vault.read_session(session["session_id"])
            original_turns = vault.list_turns(session["session_id"])
            draft_path = Path(temporary) / "draft.json"
            draft_path.write_text(json.dumps(populated_template()), encoding="utf-8")
            real_open = builtins.open

            def deny_writer_lock(path, *args, **kwargs):
                if Path(path) == vault.root / ".vault.write.lock":
                    raise PermissionError(1, "operation not permitted", str(path))
                return real_open(path, *args, **kwargs)

            output = StringIO()
            with patch("builtins.open", side_effect=deny_writer_lock), redirect_stdout(output):
                code = main([
                    "--vault", str(vault.root), "--json", "commit-draft",
                    "--session-id", session["session_id"], "--file", str(draft_path),
                    "--workflow", "think",
                ])

            payload = json.loads(output.getvalue())
            self.assertEqual(EXIT_PERSISTENCE, code)
            self.assertEqual("vault_access_denied", payload["error"]["code"])
            self.assertEqual(original_session, vault.read_session(session["session_id"]))
            self.assertEqual(original_turns, vault.list_turns(session["session_id"]))
            self.assertEqual([], vault.all_entry_revisions())
            self.assertEqual([session["session_id"]], [item["session_id"] for item in vault.all_sessions()])
            recoverable_output = StringIO()
            with redirect_stdout(recoverable_output):
                self.assertEqual(0, main(["--vault", str(vault.root), "--json", "recoverable"]))
            recoverable = json.loads(recoverable_output.getvalue())
            self.assertEqual([session["session_id"]], [item["session_id"] for item in recoverable])

    def test_skill_and_core_sop_distinguish_vault_access_from_schema_repair(self) -> None:
        for relative in ("skills/work-brain/SKILL.md", "skills/work-brain/references/sops/core-conversation.sop.md"):
            content = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("vault_access_denied", content)
            self.assertIn("not CommitDraft validation", content)
            self.assertIn("invalid_request", content)

    def test_cli_contract_is_deterministic_and_needs_no_vault(self) -> None:
        with patch("work_brain.cli._vault", side_effect=AssertionError("schema command must not resolve a vault")):
            first_code, first, first_json = read_cli_schema()
            second_code, second, second_json = read_cli_schema()

        self.assertEqual(0, first_code)
        self.assertEqual(0, second_code)
        self.assertEqual(first, second)
        self.assertEqual(first_json, second_json)
        self.assertEqual("commit-draft", first["schema"])
        self.assertEqual(list(ENTRY_SECTIONS), first["section_names"])
        self.assertEqual(list(ENTRY_SECTIONS), list(first["template"]["sections"]))
        self.assertNotIn("state", first["template"]["sections"])
        self.assertNotIn("artifacts", first["template"]["sections"])
        self.assertIn("state_changes", first["template"])
        self.assertIn("artifact_candidates", first["template"])

    def test_validator_accepts_generated_scaffold_and_rejects_section_aliases(self) -> None:
        value = populated_template()
        validated = CommitDraftValidator().validate(value, turn_count=1, workflow="think")
        self.assertEqual(list(ENTRY_SECTIONS), list(validated.sections))

        for alias in ("alternatives", "alternatives_and_tradeoffs", "decisions", "decisions_and_actions"):
            invalid = populated_template()
            invalid["sections"][alias] = invalid["sections"].pop(
                "alternatives_tradeoffs" if alias.startswith("alternatives") else "decisions_actions"
            )
            with self.subTest(alias=alias), self.assertRaisesRegex(ValidationError, "exactly the supported entry section names"):
                CommitDraftValidator().validate(invalid, turn_count=1, workflow="think")

        invalid = populated_template()
        invalid["sections"]["state"] = []
        with self.assertRaisesRegex(ValidationError, "exactly the supported entry section names"):
            CommitDraftValidator().validate(invalid, turn_count=1, workflow="think")

    def test_generated_scaffold_publishes_through_existing_commit_draft_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            vault = Vault(Path(temporary) / "vault").initialize()
            session = vault.create_session(modes=["think"], runtime={"workflow": "think"})
            vault.append_turn(session["session_id"], "user", "Use the generated CommitDraft structure.")
            draft_path = Path(temporary) / "draft.json"
            draft_path.write_text(json.dumps(populated_template()), encoding="utf-8")
            output = StringIO()

            with redirect_stdout(output):
                result = main([
                    "--vault", str(vault.root), "commit-draft",
                    "--session-id", session["session_id"], "--workflow", "think",
                    "--file", str(draft_path),
                ])

            self.assertEqual(0, result)
            published = json.loads(output.getvalue())
            self.assertEqual("committed", published["source_status"])
            self.assertEqual("committed", vault.read_session(session["session_id"])["runtime"]["commit_status"])

    def test_skill_requires_runtime_schema_and_documented_sections_match_domain(self) -> None:
        skill = (ROOT / "skills/work-brain/SKILL.md").read_text(encoding="utf-8")
        schema_doc = (ROOT / "skills/work-brain/references/schemas/commit-draft.md").read_text(encoding="utf-8")
        core = (ROOT / "skills/work-brain/references/sops/core-conversation.sop.md").read_text(encoding="utf-8")
        agent_tools = (ROOT / "skills/work-brain/references/tools/agent-tools.md").read_text(encoding="utf-8")

        skill = " ".join(skill.split())
        self.assertIn("work-brain schema commit-draft --json", skill)
        self.assertIn("Do not query this contract during ordinary conversation turns", skill)
        self.assertIn("classify the failure", skill)
        self.assertIn("work-brain schema commit-draft --json", core)
        self.assertIn("at most once on the same target session", core)
        self.assertIn("work-brain schema commit-draft --json", agent_tools)
        self.assertIn("work-brain schema commit-draft --json", schema_doc)

        match = re.search(r"<!-- COMMIT-DRAFT-SECTION-NAMES -->\s*```text\n(.*?)\n```", schema_doc, re.DOTALL)
        self.assertIsNotNone(match)
        documented_names = tuple(match.group(1).splitlines()) if match else ()
        self.assertEqual(ENTRY_SECTIONS, documented_names)


if __name__ == "__main__":
    unittest.main()
