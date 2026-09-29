from __future__ import annotations

import json
import math
import time
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .timeutils import UTC


BASE_URL = "https://www.smard.de/app/chart_data"
SERIES = {
    "price_eur_mwh": (4169, "DE-LU"),
    "load_actual_mwh": (410, "DE"),
    "load_forecast_mwh": (411, "DE"),
}


class SmardError(RuntimeError):
    pass


class SourceDataIncomplete(SmardError):
    pass


def _get_json(url: str, attempts: int = 3) -> dict:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": "currentprice/1.0"})
            with urlopen(request, timeout=20) as response:
                if "json" not in response.headers.get_content_type():
                    raise SmardError("SMARD returned a non-JSON response.")
                payload = json.load(response)
                if not isinstance(payload, dict):
                    raise SmardError("SMARD returned an invalid JSON object.")
                return payload
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, SmardError) as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    raise SmardError("SMARD request failed after retries.") from last_error


def _fetch_series(filter_id: int, region: str) -> dict[datetime, float]:
    index = _get_json(f"{BASE_URL}/{filter_id}/{region}/index_hour.json")
    timestamps = index.get("timestamps")
    if not isinstance(timestamps, list) or len(timestamps) < 3:
        raise SmardError("SMARD index did not contain three hourly windows.")

    result: dict[datetime, float] = {}
    for window_start in sorted(set(timestamps))[-3:]:
        if not isinstance(window_start, int):
            raise SmardError("SMARD index contained an invalid timestamp.")
        url = (
            f"{BASE_URL}/{filter_id}/{region}/"
            f"{filter_id}_{region}_hour_{window_start}.json"
        )
        payload = _get_json(url)
        rows = payload.get("series")
        if not isinstance(rows, list):
            raise SmardError("SMARD series payload is missing rows.")
        for row in rows:
            if not isinstance(row, list) or len(row) != 2 or not isinstance(row[0], int):
                raise SmardError("SMARD series contained a malformed row.")
            if row[1] is None:
                continue
            value = float(row[1])
            if not math.isfinite(value):
                raise SmardError("SMARD series contained a nonfinite value.")
            timestamp = datetime.fromtimestamp(row[0] / 1000, tz=UTC)
            existing = result.get(timestamp)
            if existing is not None and existing != value:
                raise SmardError("SMARD returned conflicting duplicate values.")
            result[timestamp] = value
    return result


def fetch_observations(origin_utc: datetime) -> list[dict]:
    origin_utc = origin_utc.astimezone(UTC)
    series = {
        name: _fetch_series(filter_id, region)
        for name, (filter_id, region) in SERIES.items()
    }
    expected = [origin_utc - timedelta(hours=336 - offset) for offset in range(336)]
    observations = []
    missing: list[datetime] = []
    for timestamp in expected:
        if any(timestamp not in values for values in series.values()):
            missing.append(timestamp)
            continue
        observations.append(
            {
                "timestamp_utc": timestamp,
                **{name: values[timestamp] for name, values in series.items()},
            }
        )
    if missing:
        rendered = ", ".join(item.isoformat() for item in missing[:5])
        raise SourceDataIncomplete(
            f"SMARD does not yet have all 336 required hours; missing {len(missing)}: {rendered}"
        )
    return observations
