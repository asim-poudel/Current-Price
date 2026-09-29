from __future__ import annotations

import math
from datetime import timedelta
from typing import Sequence

import numpy as np

from .timeutils import BERLIN, UTC


FEATURE_ORDER = [
    "load_actual_mwh",
    "load_forecast_mwh",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
    "weekend",
    "price_lag_1",
    "price_lag_24",
    "price_lag_48",
    "price_lag_168",
    "price_roll_mean_24",
    "price_roll_std_24",
    "price_roll_mean_168",
    "price_roll_std_168",
]


def build_feature_matrix(observations: Sequence[dict]) -> np.ndarray:
    if len(observations) != 336:
        raise ValueError(f"Expected 336 observations, received {len(observations)}.")
    ordered = sorted(observations, key=lambda row: row["timestamp_utc"])
    for index, row in enumerate(ordered):
        timestamp = row["timestamp_utc"]
        if timestamp.tzinfo is None or timestamp.astimezone(UTC) != timestamp:
            raise ValueError("Observation timestamps must be UTC-aware.")
        if index and timestamp - ordered[index - 1]["timestamp_utc"] != timedelta(hours=1):
            raise ValueError("Observations must be unique, sorted, and exactly hourly.")
        for field in ("price_eur_mwh", "load_actual_mwh", "load_forecast_mwh"):
            if not math.isfinite(float(row[field])):
                raise ValueError(f"{field} contains a nonfinite value.")

    prices = np.asarray([row["price_eur_mwh"] for row in ordered], dtype=np.float64)
    rows: list[list[float]] = []
    for index in range(168, 336):
        row = ordered[index]
        local = row["timestamp_utc"].astimezone(BERLIN)
        hour_angle = 2 * np.pi * local.hour / 24
        dow_angle = 2 * np.pi * local.weekday() / 7
        past_24 = prices[index - 24 : index]
        past_168 = prices[index - 168 : index]
        rows.append(
            [
                float(row["load_actual_mwh"]),
                float(row["load_forecast_mwh"]),
                float(np.sin(hour_angle)),
                float(np.cos(hour_angle)),
                float(np.sin(dow_angle)),
                float(np.cos(dow_angle)),
                float(local.weekday() >= 5),
                float(prices[index - 1]),
                float(prices[index - 24]),
                float(prices[index - 48]),
                float(prices[index - 168]),
                float(past_24.mean()),
                float(past_24.std(ddof=1)),
                float(past_168.mean()),
                float(past_168.std(ddof=1)),
            ]
        )
    matrix = np.asarray(rows, dtype=np.float64)
    if matrix.shape != (168, 15) or not np.isfinite(matrix).all():
        raise ValueError("Engineered feature matrix violates the (168, 15) contract.")
    return matrix


def scale_features(matrix: np.ndarray, scaler: dict) -> np.ndarray:
    if scaler.get("feature_order") != FEATURE_ORDER:
        raise ValueError("Scaler feature order does not match the frozen contract.")
    mean = np.asarray(scaler["x_scaler"]["mean"], dtype=np.float64)
    scale = np.asarray(scaler["x_scaler"]["scale"], dtype=np.float64)
    if mean.shape != (15,) or scale.shape != (15,) or np.any(scale == 0):
        raise ValueError("Invalid feature scaler parameters.")
    result = ((matrix - mean) / scale).astype(np.float32)
    if result.shape != (168, 15) or not np.isfinite(result).all():
        raise ValueError("Scaled feature matrix violates the frozen contract.")
    return result
