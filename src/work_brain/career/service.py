from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from ..retrieval import EvidenceRetriever
from .marks import CareerCandidateMarkStore
from .questions import MarkdownQuestionBankProvider, QuestionBank, QuestionFilters, QuestionRef


class CareerService:
    """Application boundary for LLD-04; never mutates professional evidence."""

    def __init__(self, vault: Any, *, banks: Iterable[QuestionBank] | None = None, retriever: EvidenceRetriever | None = None):
        self.vault = vault
        configured = list(banks) if banks is not None else self._default_banks(vault)
        self.questions = MarkdownQuestionBankProvider(configured)
        self.marks = CareerCandidateMarkStore(vault)
        self.retriever = retriever or EvidenceRetriever(vault)

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
        evidence = self.retriever.search(query or selected["text"], page_size=page_size, cursor=cursor)
        return {"mode": "prepare", "question": selected, "evidence": evidence, "selection_required": True, "story_scores": None}

    def mock(self, *, question: Mapping[str, Any] | None = None, question_text: str | None = None, filters: QuestionFilters | None = None, seed: int | None = None) -> dict[str, Any]:
        selected = self._resolve_question(question, question_text, filters, seed)
        return {"mode": "mock", "question": selected, "reveal_evidence_before_answer": False, "evidence": None, "critique_requires_hydrated_evidence": True}

    def search_evidence(self, query: str, *, filters: Mapping[str, Any] | None = None, page_size: int = 8, cursor: str | None = None) -> dict[str, Any]:
        return self.retriever.search(query, filters=filters, page_size=page_size, cursor=cursor)

    def hydrate_evidence(self, refs: list[Mapping[str, Any]]) -> dict[str, Any]:
        return self.retriever.hydrate(refs)

    def _resolve_question(self, question: Mapping[str, Any] | None, question_text: str | None, filters: QuestionFilters | None, seed: int | None) -> dict[str, Any]:
        if question is not None:
            ref = QuestionRef.from_value(question.get("ref", question))
            return self.get_question(ref)
        if question_text:
            return {"ref": None, "text": question_text, "tags": [], "section": None, "source_class": "user_supplied"}
        return self.choose_question(filters=filters, seed=seed)
