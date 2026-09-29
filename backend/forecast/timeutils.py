from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


UTC = timezone.utc
BERLIN = ZoneInfo("Europe/Berlin")


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Timestamp must be timezone-aware.")
    return value.astimezone(UTC)


def iso_utc(value: datetime) -> str:
    return as_utc(value).isoformat().replace("+00:00", "Z")


def local_fields(value: datetime) -> tuple[str, str]:
    local = as_utc(value).astimezone(BERLIN)
    offset = local.strftime("%z")
    rendered_offset = f"{offset[:3]}:{offset[3:]}"
    return local.isoformat(), f"{local.tzname() or 'Europe/Berlin'} ({rendered_offset})"
