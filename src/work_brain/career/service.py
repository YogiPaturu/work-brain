from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..retrieval import EvidenceRetriever
from ..experiences import ExperienceService
from .marks import CareerCandidateMarkStore
from .questions import MarkdownQuestionBankProvider, QuestionBank, QuestionFilters, QuestionRef


class CareerService:
    """Application boundary for career workflows; never mutates professional evidence."""

    def __init__(self, vault: Any, *, banks: Iterable[QuestionBank] | None = None, retriever: EvidenceRetriever | None = None):
        self.vault = vault
        configured = list(banks) if banks is not None else self._default_banks(vault)
        self.questions = MarkdownQuestionBankProvider(configured)
        self.marks = CareerCandidateMarkStore(vault)
        self.retriever = retriever or EvidenceRetriever(vault)
        self.experiences = ExperienceService(vault, retriever=self.retriever)

    @staticmethod
    def _default_banks(vault: Any) -> list[QuestionBank]:
        return [QuestionBank(path.stem, path, "private_local") for path in sorted((vault.root / "questions").glob("*.md"))]

    def search_questions(self, *, filters: QuestionFilters | None = None, text: str | None = None, limit: int = 20) -> dict[str, Any]:
        questions = self.questions.search_questions(filters, text, limit)
        return {"banks": [bank.bank_id for bank in self.questions.list_banks()], "diagnostics": list(self.questions.diagnostics), "questions": [question.to_dict() for question in questions]}

    def get_question(self, ref: QuestionRef) -> dict[str, Any]:
        return self.questions.get_question(ref).to_dict()

    def choose_question(self, *, filters: QuestionFilters | None = None, text: str | None = None, seed: int | None = None) -> dict[str, Any]:
        return self.questions.choose_question(filters, text, seed).to_dict()

    def prepare(self, *, question: Mapping[str, Any] | None = None, question_text: str | None = None, query: str | None = None, filters: QuestionFilters | None = None, page_size: int = 8, cursor: str | None = None, seed: int | None = None) -> dict[str, Any]:
        selected = self._resolve_question(question, question_text, filters, seed)
        if not isinstance(page_size, int) or not 1 <= page_size <= 20:
            raise ValueError("page_size must be between 1 and 20")
        evidence_query = query or selected["text"]
        fingerprint = hashlib.sha256(json.dumps({"query": evidence_query, "page_size": page_size}, sort_keys=True).encode()).hexdigest()
        candidate_offset = 0
        if cursor:
            try:
                padded = cursor + "=" * (-len(cursor) % 4)
                cursor_value = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("cursor must be an opaque career continuation") from exc
            if not isinstance(cursor_value, dict) or cursor_value.get("fingerprint") != fingerprint:
                return {
                    "mode": "prepare", "question": selected, "evidence": {"cards": [], "next_cursor": None, "status": "cursor_expired"},
                    "experiences": [], "ungrouped_candidates": [], "candidates": [], "selection_required": True, "story_scores": None,
                }
            candidate_offset = int(cursor_value.get("offset", 0))
        work_limit = max(40, page_size * 8)
        retrieval_page_size = 20
        retrieval_cursor = None
        raw_cards: list[dict[str, Any]] = []
        last_evidence: dict[str, Any] = {"cards": [], "next_cursor": None, "status": "ok"}
        while len(raw_cards) < work_limit:
            last_evidence = self.retriever.search(evidence_query, page_size=retrieval_page_size, cursor=retrieval_cursor)
            raw = last_evidence.get("cards", [])
            if isinstance(raw, list):
                raw_cards.extend(card for card in raw if isinstance(card, dict))
            retrieval_cursor = last_evidence.get("next_cursor")
            candidates = self.experiences.candidates_from_evidence({"cards": raw_cards})
            unique_count = len(candidates["experiences"]) + len(candidates["ungrouped"])
            if unique_count >= candidate_offset + page_size or not retrieval_cursor or last_evidence.get("status") == "retrieval_unavailable":
                break
        candidates = self.experiences.candidates_from_evidence({"cards": raw_cards})
        ordered = [dict(candidate) for candidate in candidates.get("ordered", [*candidates["experiences"], *candidates["ungrouped"]])]
        for candidate in ordered:
            candidate.pop("_best_rank", None)
        page = ordered[candidate_offset:candidate_offset + page_size]
        next_cursor = None
        if candidate_offset + page_size < len(ordered) or retrieval_cursor:
            next_cursor = base64.urlsafe_b64encode(json.dumps({"fingerprint": fingerprint, "offset": candidate_offset + page_size}, sort_keys=True).encode()).decode().rstrip("=")
        evidence = dict(last_evidence)
        evidence["cards"] = raw_cards[:work_limit]
        evidence["next_cursor"] = next_cursor
        return {
            "mode": "prepare",
            "question": selected,
            "evidence": evidence,
            "experiences": [candidate for candidate in page if candidate.get("candidate_type") == "experience"],
            "ungrouped_candidates": [candidate for candidate in page if candidate.get("candidate_type") == "ungrouped_entry"],
            "candidates": page,
            "selection_required": True,
            "story_scores": None,
        }

    def mock(self, *, question: Mapping[str, Any] | None = None, question_text: str | None = None, filters: QuestionFilters | None = None, seed: int | None = None) -> dict[str, Any]:
        selected = self._resolve_question(question, question_text, filters, seed)
        return {"mode": "mock", "question": selected, "reveal_evidence_before_answer": False, "evidence": None, "critique_requires_hydrated_evidence": True}

    def search_evidence(self, query: str, *, filters: Mapping[str, Any] | None = None, page_size: int = 8, cursor: str | None = None) -> dict[str, Any]:
        return self.retriever.search(query, filters=filters, page_size=page_size, cursor=cursor)

    def select_evidence(self, *, filters: Mapping[str, Any] | None = None, page_size: int = 8, cursor: str | None = None) -> dict[str, Any]:
        return self.retriever.select_evidence(filters=filters, page_size=page_size, cursor=cursor)

    def hydrate_evidence(self, refs: list[Mapping[str, Any]]) -> dict[str, Any]:
        return self.retriever.hydrate(refs)

    def _resolve_question(self, question: Mapping[str, Any] | None, question_text: str | None, filters: QuestionFilters | None, seed: int | None) -> dict[str, Any]:
        if question is not None:
            ref = QuestionRef.from_value(question.get("ref", question))
            return self.get_question(ref)
        if question_text:
            return {"ref": None, "text": question_text, "tags": [], "section": None, "source_class": "user_supplied"}
        return self.choose_question(filters=filters, seed=seed)
