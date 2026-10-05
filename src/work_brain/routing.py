"""Dependency-light prompt routing primitives used by capture hooks."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


WORKFLOWS = (
    "think", "operate", "communicate", "career", "open-day", "close-day", "backfill",
)


@dataclass(frozen=True)
class PromptRoute:
    """Routing metadata derived from a prompt without changing its raw text."""

    raw: str
    activation: bool
    routed_content: str
    normalized_content: str
    workflow: str
    recognized: bool
    lifecycle: str | None = None


WORKFLOW_ALIASES: tuple[tuple[str, str], ...] = (
    ("open my work journal", "open-day"), ("start my day", "open-day"),
    ("start work brain", "think"), ("open day", "open-day"),
    ("close my day", "close-day"), ("finish my day", "close-day"),
    ("wrap up my day", "close-day"), ("close day", "close-day"),
    ("help me think through", "think"), ("challenge my thinking", "think"),
    ("think with me", "think"), ("think", "think"), ("reason", "think"),
    ("where did i leave off", "operate"), ("where was i", "operate"),
    ("what should i work on next", "operate"), ("what should i work on", "operate"),
    ("what am i working on", "operate"), ("catch me up", "operate"),
    ("give me a quick update", "operate"), ("quick update", "operate"),
    ("plan my work", "operate"), ("what should i do", "operate"), ("operate", "operate"),
    ("draft a message", "communicate"), ("communicate", "communicate"),
    ("practice this interview question", "career"), ("help me prepare for", "career"),
    ("interview me", "career"), ("practice interview", "career"), ("career", "career"),
    ("remember a past experience", "backfill"), ("backfill", "backfill"),
)

NATURAL_ACTIVATION_ALIASES = frozenset({
    "start my day", "open my work journal", "start work brain", "capture this", "journal this",
})

LIFECYCLE_ALIASES: tuple[tuple[str, str], ...] = (
    ("that s enough", "commit-keep-active"), ("thats enough", "commit-keep-active"),
    ("finish this", "commit-keep-active"), ("save this", "commit-keep-active"),
    ("done with this", "commit-keep-active"), ("close this session", "commit-keep-active"),
    ("stop work brain", "deactivate"),
)


def normalize_routing_text(value: str) -> str:
    """Normalize only command/routing text; never use this for persistence."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.strip().split())


def _strip_work_brain_prefix(raw: str) -> tuple[bool, str]:
    candidate = raw.strip()
    match = re.match(r"(?:[/\$])?work(?:\s+|-)brain(?=$|[^\w])", candidate, flags=re.IGNORECASE)
    if not match:
        return False, raw
    remainder = candidate[match.end():]
    return True, re.sub(r"^[\s,.:;!?/\\|_\-–—]+", "", remainder)


def _strip_capture_prefix(raw: str) -> tuple[bool, str]:
    """Recognize explicit mid-conversation capture without choosing a workflow."""
    candidate = raw.strip()
    match = re.match(r"(?:capture\s+this|journal\s+this)(?=$|[^\w])", candidate, flags=re.IGNORECASE)
    if not match:
        return False, raw
    remainder = candidate[match.end():]
    return True, re.sub(r"^[\s,.:;!?/\\|_\-–—]+", "", remainder)


def _workflow_for_normalized(normalized: str, current: str | None = None) -> tuple[str, bool]:
    for phrase, workflow in sorted(WORKFLOW_ALIASES, key=lambda item: len(item[0]), reverse=True):
        if normalized == phrase or normalized.startswith(phrase + " "):
            return workflow, True
    if current in WORKFLOWS:
        return current, False
    return "think", False


def _lifecycle_for_normalized(normalized: str) -> str | None:
    for phrase, lifecycle in sorted(LIFECYCLE_ALIASES, key=lambda item: len(item[0]), reverse=True):
        if normalized == phrase or normalized.startswith(phrase + " "):
            return lifecycle
    if normalized in {"close my day", "finish my day", "wrap up my day", "close day"}:
        return "deactivate"
    return None


def route_prompt(intent: str | None, current: str | None = None) -> PromptRoute:
    raw = intent if isinstance(intent, str) else ""
    activation, routed = _strip_work_brain_prefix(raw)
    capture_activation, routed = _strip_capture_prefix(routed)
    activation = activation or capture_activation
    normalized = normalize_routing_text(routed)
    workflow, recognized = _workflow_for_normalized(normalized, current)
    if not activation and normalized in NATURAL_ACTIVATION_ALIASES:
        activation = True
    return PromptRoute(
        raw=raw, activation=activation, routed_content=routed,
        normalized_content=normalized, workflow=workflow, recognized=recognized,
        lifecycle=_lifecycle_for_normalized(normalized),
    )


ALIASES = dict(WORKFLOW_ALIASES)


def select_workflow(intent: str | None, current: str | None = None) -> str:
    return route_prompt(intent, current).workflow
