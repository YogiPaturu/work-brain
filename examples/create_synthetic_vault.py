"""Create a publication-safe Work Brain vault for local demonstrations."""

from __future__ import annotations

import argparse

from work_brain import Vault, new_uuid7


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", required=True)
    args = parser.parse_args()
    vault = Vault(args.vault).initialize()
    session = vault.create_session(
        started_at="2026-09-30T09:00:00+01:00",
        modes=["think"],
        domains=["engineering"],
        runtime={"model": "synthetic", "skill": "work-brain"},
    )
    vault.append_turn(session["session_id"], "user", "The synthetic import flow is slow.", recorded_at="2026-09-30T09:01:00+01:00")
    vault.append_turn(session["session_id"], "assistant", "What evidence do you have?", recorded_at="2026-09-30T09:01:05+01:00")
    sections = {name: [] for name in (
        "context", "observations", "significance", "contribution", "reasoning", "evidence",
        "alternatives_tradeoffs", "decisions_actions", "expectations", "outcomes", "learning", "open_questions",
    )}
    sections["context"] = [{"text": "The synthetic import flow is slow.", "basis": "stated", "source_turns": [1]}]
    sections["reasoning"] = [{"text": "The bottleneck may be in parsing rather than storage.", "basis": "inferred", "source_turns": [1, 2]}]
    vault.commit_entry(session["session_id"], {
        "entry_id": session["entry_id"], "session_id": session["session_id"], "revision": 1,
        "commit_id": new_uuid7(), "created_at": "2026-09-30T09:02:00+01:00", "supersedes_revision": None,
        "revision_reason": "initial_commit", "provenance_kind": "contemporaneous", "title": "Synthetic import investigation",
        "summary": "A synthetic example of a captured engineering investigation.",
        "occurrence": {"start": "2026-09-30T09:00:00+01:00", "end": "2026-09-30T09:02:00+01:00", "precision": "instant", "label": None},
        "modes": ["think"], "domains": ["engineering"], "sections": sections,
        "state_mutations": [], "entity_refs": [], "artifact_refs": [], "source_refs": [],
    })
    print(f"created synthetic vault at {vault.root}")


if __name__ == "__main__":
    main()

