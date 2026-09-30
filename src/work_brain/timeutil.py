from __future__ import annotations

from datetime import date, datetime, timezone
import re

from .errors import ValidationError


def parse_timestamp(value: str, field: str = "timestamp") -> datetime:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{field} must be an RFC3339 timestamp with an offset")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value):
        raise ValidationError(f"{field} must be an RFC3339 timestamp with an offset")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValidationError(f"{field} must be a valid RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError(f"{field} must include an explicit UTC offset")
    return parsed


def timestamp_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def date_for_timestamp(value: str) -> str:
    return parse_timestamp(value).date().isoformat()


def validate_calendar_date(value: str, field: str = "date") -> str:
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field} must be YYYY-MM-DD") from exc
    return value


def canonical_json_timestamp(value: str) -> str:
    return parse_timestamp(value).isoformat(timespec="microseconds")
