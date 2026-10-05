from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from .config import read_config
from .errors import IntegrityError, ValidationError
from .timeutil import date_for_timestamp, timestamp_now, validate_calendar_date


PROFILE_DOCUMENT_VERSION = 1
PROFILE_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
PROFILE_FIELDS = {
    "id", "label", "workflow", "channel", "audience", "purpose", "scope",
    "tone", "format", "rendering", "include", "exclude", "triggers", "cadence", "schedule", "delivery",
}
SCOPE_FIELDS = {"entities", "workspaces", "projects", "experiences", "domain_tags", "time_window"}
RENDERING_FIELDS = {"markup", "layout", "max_length"}
SCHEDULE_FIELDS = {"weekdays", "time"}
DELIVERY_FIELDS = {"mode", "webhook_env"}
TRIGGERS = {"after_close_day", "after_work_item", "scheduled"}
CADENCES = {"on_demand", "daily", "weekly", "twice_weekly"}
TIME_WINDOWS = {"today", "week_to_date", "work_item"}
WEEKDAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}


def default_profiles_path() -> Path:
    configured = os.environ.get("XDG_CONFIG_HOME")
    base = Path(configured).expanduser() if configured else Path.home() / ".config"
    return base / "work-brain" / "communication-profiles.json"


def resolve_profiles_path(
    explicit: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    config_path: str | Path | None = None,
) -> Path:
    env = environ if environ is not None else os.environ
    raw = explicit or env.get("WORK_BRAIN_PROFILES")
    if raw is None:
        configured = read_config(config_path).get("communication_profiles")
        raw = configured if isinstance(configured, str) else None
    if raw is None:
        return default_profiles_path()
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate.resolve()


def set_profiles_path(profiles: str | Path, path: str | Path | None = None) -> Path:
    candidate = Path(profiles).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = candidate.resolve()
    current = read_config(path)
    current["communication_profiles"] = str(candidate)
    from .config import write_config
    write_config(current, path)
    return candidate


def _non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"profile {field} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValidationError(f"profile {field} must be a non-empty list of strings")
    return tuple(item.strip() for item in value)


@dataclass(frozen=True)
class CommunicationProfile:
    profile_id: str
    label: str
    workflow: str
    channel: str
    audience: str
    purpose: str
    scope: dict[str, Any]
    tone: str
    format: tuple[str, ...]
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    triggers: tuple[str, ...]
    cadence: str
    schedule: dict[str, Any]
    delivery: dict[str, Any]
    rendering: dict[str, Any]

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], *, index: int = 0) -> "CommunicationProfile":
        if not isinstance(raw, Mapping):
            raise ValidationError(f"communication profile {index} must be an object")
        unknown = sorted(set(raw) - PROFILE_FIELDS)
        if unknown:
            raise ValidationError(f"communication profile {index} has unknown fields: {', '.join(unknown)}")
        profile_id = _non_empty_string(raw.get("id"), "id")
        if not PROFILE_ID_RE.fullmatch(profile_id):
            raise ValidationError("profile id must use lowercase letters, numbers, '_' or '-' and start with a letter")
        workflow = _non_empty_string(raw.get("workflow"), "workflow")
        if workflow != "communicate":
            raise ValidationError(f"profile {profile_id} must use workflow=communicate")
        scope = raw.get("scope")
        if not isinstance(scope, Mapping):
            raise ValidationError(f"profile {profile_id} scope must be an object")
        unknown_scope = sorted(set(scope) - SCOPE_FIELDS)
        if unknown_scope:
            raise ValidationError(f"profile {profile_id} has unknown scope fields: {', '.join(unknown_scope)}")
        normalized_scope: dict[str, Any] = {}
        for field in ("entities", "workspaces", "projects", "experiences", "domain_tags"):
            if field in scope:
                normalized_scope[field] = list(_string_list(scope[field], f"scope.{field}"))
        if "time_window" in scope:
            time_window = _non_empty_string(scope["time_window"], "scope.time_window")
            if time_window not in TIME_WINDOWS:
                raise ValidationError(
                    f"profile {profile_id} scope.time_window must be one of: {', '.join(sorted(TIME_WINDOWS))}"
                )
            normalized_scope["time_window"] = time_window
        raw_triggers = raw.get("triggers", [])
        if not isinstance(raw_triggers, list) or not all(isinstance(item, str) and item.strip() for item in raw_triggers):
            raise ValidationError(f"profile {profile_id} triggers must be a list of strings")
        triggers = tuple(item.strip() for item in raw_triggers)
        unknown_triggers = sorted(set(triggers) - TRIGGERS)
        if unknown_triggers:
            raise ValidationError(f"profile {profile_id} has unknown triggers: {', '.join(unknown_triggers)}")
        cadence = raw.get("cadence", "on_demand")
        if not isinstance(cadence, str) or cadence not in CADENCES:
            raise ValidationError(f"profile {profile_id} cadence must be one of: {', '.join(sorted(CADENCES))}")
        raw_schedule = raw.get("schedule", {})
        if not isinstance(raw_schedule, Mapping):
            raise ValidationError(f"profile {profile_id} schedule must be an object")
        unknown_schedule = sorted(set(raw_schedule) - SCHEDULE_FIELDS)
        if unknown_schedule:
            raise ValidationError(f"profile {profile_id} has unknown schedule fields: {', '.join(unknown_schedule)}")
        schedule: dict[str, Any] = {}
        if "weekdays" in raw_schedule:
            weekdays = _string_list(raw_schedule["weekdays"], "schedule.weekdays")
            normalized_weekdays = [item.casefold() for item in weekdays]
            invalid_weekdays = sorted(set(normalized_weekdays) - WEEKDAYS)
            if invalid_weekdays:
                raise ValidationError(f"profile {profile_id} has invalid schedule weekdays: {', '.join(invalid_weekdays)}")
            schedule["weekdays"] = normalized_weekdays
        if "time" in raw_schedule:
            schedule_time = _non_empty_string(raw_schedule["time"], "schedule.time")
            if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", schedule_time):
                raise ValidationError(f"profile {profile_id} schedule.time must use HH:MM")
            schedule["time"] = schedule_time
        raw_delivery = raw.get("delivery", {})
        if not isinstance(raw_delivery, Mapping):
            raise ValidationError(f"profile {profile_id} delivery must be an object")
        unknown_delivery = sorted(set(raw_delivery) - DELIVERY_FIELDS)
        if unknown_delivery:
            raise ValidationError(f"profile {profile_id} has unknown delivery fields: {', '.join(unknown_delivery)}")
        delivery_mode = raw_delivery.get("mode", "draft_only")
        if delivery_mode not in {"draft_only", "send"}:
            raise ValidationError(f"profile {profile_id} delivery.mode must be draft_only or send")
        delivery: dict[str, Any] = {"mode": delivery_mode}
        if "webhook_env" in raw_delivery:
            delivery["webhook_env"] = _non_empty_string(raw_delivery["webhook_env"], "delivery.webhook_env")
        if delivery_mode == "send" and "webhook_env" not in delivery:
            raise ValidationError(f"profile {profile_id} delivery.webhook_env is required when delivery.mode=send")
        raw_rendering = raw.get("rendering", {})
        if not isinstance(raw_rendering, Mapping):
            raise ValidationError(f"profile {profile_id} rendering must be an object")
        unknown_rendering = sorted(set(raw_rendering) - RENDERING_FIELDS)
        if unknown_rendering:
            raise ValidationError(f"profile {profile_id} has unknown rendering fields: {', '.join(unknown_rendering)}")
        markup = raw_rendering.get("markup", "plain_text")
        if markup not in {"plain_text", "markdown"}:
            raise ValidationError(f"profile {profile_id} rendering.markup must be plain_text or markdown")
        layout = raw_rendering.get("layout", "compact")
        if layout not in {"compact", "structured"}:
            raise ValidationError(f"profile {profile_id} rendering.layout must be compact or structured")
        max_length = raw_rendering.get("max_length")
        if max_length is not None and (not isinstance(max_length, int) or not 1 <= max_length <= 10000):
            raise ValidationError(f"profile {profile_id} rendering.max_length must be between 1 and 10000")
        rendering: dict[str, Any] = {"markup": markup, "layout": layout}
        if max_length is not None:
            rendering["max_length"] = max_length
        return cls(
            profile_id=profile_id,
            label=_non_empty_string(raw.get("label"), "label"),
            workflow=workflow,
            channel=_non_empty_string(raw.get("channel"), "channel"),
            audience=_non_empty_string(raw.get("audience"), "audience"),
            purpose=_non_empty_string(raw.get("purpose"), "purpose"),
            scope=normalized_scope,
            tone=_non_empty_string(raw.get("tone"), "tone"),
            format=_string_list(raw.get("format"), "format"),
            include=_string_list(raw.get("include"), "include"),
            exclude=_string_list(raw.get("exclude"), "exclude"),
            triggers=triggers,
            cadence=cadence,
            schedule=schedule,
            delivery=delivery,
            rendering=rendering,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.profile_id,
            "label": self.label,
            "workflow": self.workflow,
            "channel": self.channel,
            "audience": self.audience,
            "purpose": self.purpose,
            "scope": self.scope,
            "tone": self.tone,
            "format": list(self.format),
            "include": list(self.include),
            "exclude": list(self.exclude),
            "triggers": list(self.triggers),
            "cadence": self.cadence,
            "schedule": self.schedule,
            "delivery": self.delivery,
            "rendering": self.rendering,
        }

    def retrieval_filters(self, *, local_date: str | None = None) -> dict[str, Any]:
        """Translate the profile scope into non-bypassable evidence filters."""

        filters: dict[str, Any] = {}
        for field in ("entities", "workspaces", "projects", "experiences", "domain_tags"):
            if self.scope.get(field):
                filters[field] = list(self.scope[field])
        if self.scope.get("time_window") in {"today", "week_to_date"}:
            selected_date = local_date or date_for_timestamp(timestamp_now())
            validate_calendar_date(selected_date, "local_date")
            local_zone = datetime.now().astimezone().tzinfo
            selected_day = datetime.fromisoformat(selected_date).date()
            if self.scope.get("time_window") == "week_to_date":
                selected_day -= timedelta(days=selected_day.weekday())
            start = datetime.combine(
                selected_day, time.min, tzinfo=local_zone
            )
            end = datetime.combine(
                datetime.fromisoformat(selected_date).date() + timedelta(days=1),
                time.min,
                tzinfo=local_zone,
            )
            filters["occurred_after"] = start.isoformat()
            filters["occurred_before"] = end.isoformat()
        return filters


class CommunicationProfileStore:
    """Validated, user-owned communication profiles."""

    def __init__(self, profiles: list[CommunicationProfile], *, path: Path | None = None):
        self.path = path
        self._profiles = {profile.profile_id: profile for profile in profiles}

    @classmethod
    def load(cls, path: str | Path | None = None, *, config_path: str | Path | None = None) -> "CommunicationProfileStore":
        target = resolve_profiles_path(path, config_path=config_path)
        if not target.exists():
            return cls([], path=target)
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise IntegrityError(f"invalid communication profiles JSON: {target}") from exc
        if not isinstance(raw, Mapping):
            raise ValidationError("communication profiles document must be an object")
        version = raw.get("version")
        if version != PROFILE_DOCUMENT_VERSION:
            raise ValidationError(f"communication profiles version must be {PROFILE_DOCUMENT_VERSION}")
        values = raw.get("profiles")
        if not isinstance(values, list):
            raise ValidationError("communication profiles must be a list")
        profiles = [CommunicationProfile.from_dict(value, index=index) for index, value in enumerate(values)]
        ids = [profile.profile_id for profile in profiles]
        if len(ids) != len(set(ids)):
            raise ValidationError("communication profile ids must be unique")
        return cls(profiles, path=target)

    def list(self) -> list[CommunicationProfile]:
        return [self._profiles[key] for key in sorted(self._profiles)]

    def get(self, profile_id: str) -> CommunicationProfile:
        if not isinstance(profile_id, str) or not profile_id.strip():
            raise ValidationError("profile_id must be a non-empty string")
        try:
            return self._profiles[profile_id.strip()]
        except KeyError as exc:
            source = f" in {self.path}" if self.path else ""
            raise ValidationError(f"communication profile not found: {profile_id}{source}") from exc

    def triggered_after_close_day(self) -> list[CommunicationProfile]:
        return [profile for profile in self.list() if "after_close_day" in profile.triggers]

    def triggered_scheduled(self) -> list[CommunicationProfile]:
        return [profile for profile in self.list() if "scheduled" in profile.triggers]

    def triggered_after_work_item(self) -> list[CommunicationProfile]:
        return [profile for profile in self.list() if "after_work_item" in profile.triggers]


def profiles_document(profiles: list[CommunicationProfile]) -> dict[str, Any]:
    return {"version": PROFILE_DOCUMENT_VERSION, "profiles": [profile.to_dict() for profile in profiles]}
