from __future__ import annotations

import secrets
import time
import uuid
import re

from .errors import ValidationError

UUID7_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def new_uuid7() -> str:
    """Generate a canonical lowercase UUIDv7 without a third-party package."""
    timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    random_a = secrets.randbits(12)
    random_b = secrets.randbits(62)
    value = (timestamp_ms << 80) | (0x7 << 76) | (random_a << 64)
    value |= (0b10 << 62) | random_b
    return str(uuid.UUID(int=value))


def validate_uuid7(value: str, field: str = "id") -> str:
    if not isinstance(value, str) or not UUID7_RE.fullmatch(value):
        raise ValidationError(f"{field} must be a canonical lowercase UUIDv7")
    parsed = uuid.UUID(value)
    if parsed.version != 7 or parsed.variant != uuid.RFC_4122:
        raise ValidationError(f"{field} must be a UUIDv7 with RFC4122 variant")
    return value

