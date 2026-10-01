from __future__ import annotations

from dataclasses import dataclass
import hashlib
import random
import re
import unicodedata
from pathlib import Path
from typing import Iterable, Mapping, Protocol

from ..errors import ValidationError


QUESTION_LINE = re.compile(r"^\s*(?:[-*+]\s+)?(?P<tags>(?:\[[^\]]+\]\s*)+)(?P<text>\S.*)\s*$")
SOURCE_CLASSES = {"public_shared", "private_local"}


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


@dataclass(frozen=True)
class QuestionRef:
    bank_id: str
    question_id: str

    def __post_init__(self) -> None:
        if not self.bank_id or self.bank_id.strip() != self.bank_id or any(ch.isspace() for ch in self.bank_id):
            raise ValidationError("question ref bank_id must be a non-empty token")
        if not re.fullmatch(r"q_[0-9a-f]{16,64}", self.question_id):
            raise ValidationError("question ref question_id must be a content hash")

    def to_dict(self) -> dict[str, str]:
        return {"bank_id": self.bank_id, "question_id": self.question_id}

    @classmethod
    def from_value(cls, value: Mapping[str, object]) -> "QuestionRef":
        if not isinstance(value, Mapping):
            raise ValidationError("question_ref must be an object")
        bank_id, question_id = value.get("bank_id"), value.get("question_id")
        if not isinstance(bank_id, str) or not isinstance(question_id, str):
            raise ValidationError("question_ref requires bank_id and question_id")
        return cls(bank_id, question_id)


@dataclass(frozen=True)
class QuestionTag:
    normalized: str
    display: str

    def to_dict(self) -> dict[str, str]:
        return {"normalized": self.normalized, "display": self.display}


@dataclass(frozen=True)
class InterviewQuestion:
    ref: QuestionRef
    text: str
    tags: tuple[QuestionTag, ...]
    section: str | None
    source_class: str
    source_path: str | None = None
    source_line: int | None = None

    @property
    def normalized_tags(self) -> frozenset[str]:
        return frozenset(tag.normalized for tag in self.tags)

    def to_dict(self, *, include_local_provenance: bool = False) -> dict[str, object]:
        value: dict[str, object] = {
            "ref": self.ref.to_dict(),
            "text": self.text,
            "tags": [tag.to_dict() for tag in self.tags],
            "section": self.section,
            "source_class": self.source_class,
        }
        if include_local_provenance:
            value["source_path"] = self.source_path
            value["source_line"] = self.source_line
        return value


@dataclass(frozen=True)
class QuestionBank:
    bank_id: str
    path: Path
    source_class: str

    def __post_init__(self) -> None:
        if not self.bank_id or self.bank_id.strip() != self.bank_id or any(ch.isspace() for ch in self.bank_id):
            raise ValidationError("bank_id must be a non-empty token")
        if self.source_class not in SOURCE_CLASSES:
            raise ValidationError("source_class must be public_shared or private_local")


@dataclass(frozen=True)
class QuestionFilters:
    tags_all: tuple[str, ...] = ()
    tags_any: tuple[str, ...] = ()
    exclude_tags: tuple[str, ...] = ()
    bank_ids: tuple[str, ...] = ()

    @classmethod
    def from_values(
        cls,
        *,
        tags_all: Iterable[str] = (),
        tags_any: Iterable[str] = (),
        exclude_tags: Iterable[str] = (),
        bank_ids: Iterable[str] = (),
    ) -> "QuestionFilters":
        def values(items: Iterable[str], field: str) -> tuple[str, ...]:
            result = tuple(_normalize(item) for item in items)
            if any(not item for item in result):
                raise ValidationError(f"{field} must contain non-empty strings")
            return result
        return cls(values(tags_all, "tags_all"), values(tags_any, "tags_any"), values(exclude_tags, "exclude_tags"), values(bank_ids, "bank_ids"))


class QuestionBankProvider(Protocol):
    def list_banks(self) -> list[QuestionBank]: ...
    def search_questions(self, filters: QuestionFilters | None = None, text: str | None = None, limit: int = 20) -> list[InterviewQuestion]: ...
    def get_question(self, ref: QuestionRef) -> InterviewQuestion: ...
    def choose_question(self, filters: QuestionFilters | None = None, text: str | None = None, seed: int | None = None) -> InterviewQuestion: ...


class MarkdownQuestionBankProvider:
    """Deterministic, read-only parser for tagged Markdown question banks."""

    def __init__(self, banks: Iterable[QuestionBank]):
        self._banks = tuple(banks)
        if len({bank.bank_id for bank in self._banks}) != len(self._banks):
            raise ValidationError("question bank IDs must be unique")
        self.diagnostics: list[dict[str, object]] = []
        self._questions: dict[QuestionRef, InterviewQuestion] | None = None

    def list_banks(self) -> list[QuestionBank]:
        return list(self._banks)

    def _parse(self) -> dict[QuestionRef, InterviewQuestion]:
        if self._questions is not None:
            return self._questions
        result: dict[QuestionRef, InterviewQuestion] = {}
        self.diagnostics = []
        for bank in self._banks:
            if not bank.path.exists():
                self.diagnostics.append({"code": "bank_missing", "bank_id": bank.bank_id, "path": str(bank.path)})
                continue
            section: str | None = None
            for line_number, raw_line in enumerate(bank.path.read_text(encoding="utf-8").splitlines(), 1):
                heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", raw_line)
                if heading:
                    section = heading.group(1).strip()
                    continue
                match = QUESTION_LINE.match(raw_line)
                if not match:
                    continue
                raw_tags = re.findall(r"\[([^\]]+)\]", match.group("tags"))
                text = match.group("text").strip()
                if not raw_tags or not text:
                    continue
                tags = tuple(QuestionTag(_normalize(tag), tag.strip()) for tag in raw_tags if tag.strip())
                if not tags:
                    self.diagnostics.append({"code": "malformed_question", "bank_id": bank.bank_id, "line": line_number})
                    continue
                stable_line = " ".join([*(tag.normalized for tag in tags), _normalize(text)])
                question_id = "q_" + hashlib.sha256(f"{bank.bank_id}\n{stable_line}".encode("utf-8")).hexdigest()[:32]
                ref = QuestionRef(bank.bank_id, question_id)
                question = InterviewQuestion(ref, text, tags, section, bank.source_class, str(bank.path), line_number)
                if ref in result:
                    self.diagnostics.append({"code": "duplicate_question", "bank_id": bank.bank_id, "line": line_number, "question_id": question_id})
                    continue
                result[ref] = question
        self._questions = result
        return result

    def search_questions(self, filters: QuestionFilters | None = None, text: str | None = None, limit: int = 20) -> list[InterviewQuestion]:
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValidationError("question limit must be between 1 and 100")
        filters = filters or QuestionFilters()
        needle = _normalize(text) if text is not None else ""
        if text is not None and not needle:
            raise ValidationError("question text search must be non-empty")
        matches: list[InterviewQuestion] = []
        for question in self._parse().values():
            tags = question.normalized_tags
            if filters.bank_ids and _normalize(question.ref.bank_id) not in filters.bank_ids:
                continue
            if not set(filters.tags_all).issubset(tags):
                continue
            if filters.tags_any and not tags.intersection(filters.tags_any):
                continue
            if tags.intersection(filters.exclude_tags):
                continue
            haystack = " ".join((question.text, *(tag.normalized for tag in question.tags), question.section or ""))
            if needle and needle not in _normalize(haystack):
                continue
            matches.append(question)
            if len(matches) == limit:
                break
        return matches

    def get_question(self, ref: QuestionRef) -> InterviewQuestion:
        question = self._parse().get(ref)
        if question is None:
            raise ValidationError(f"question_not_found: {ref.bank_id}/{ref.question_id}")
        return question

    def choose_question(self, filters: QuestionFilters | None = None, text: str | None = None, seed: int | None = None) -> InterviewQuestion:
        matches = self.search_questions(filters, text, limit=100)
        if not matches:
            raise ValidationError("no_question_match")
        if len(matches) == 1:
            return matches[0]
        chooser = random.Random(seed) if seed is not None else random.SystemRandom()
        return chooser.choice(matches)
