from __future__ import annotations

import numpy as np


MAPE_MIN_ABS_ACTUAL = 1.0


def evaluate(actual, predicted, timestamps) -> dict:
    actual = np.asarray(actual, dtype=np.float64)
    predicted = np.asarray(predicted, dtype=np.float64)
    if actual.shape != predicted.shape or actual.size == 0:
        raise ValueError("Actual and predicted values must have the same non-empty shape.")
    if not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("Metrics require finite values.")
    error = predicted - actual
    absolute = np.abs(error)
    denominator = np.abs(actual) + np.abs(predicted) + 1e-6
    valid_mape = np.abs(actual) >= MAPE_MIN_ABS_ACTUAL
    worst_index = int(np.argmax(absolute))
    return {
        "evaluated_hours": int(actual.size),
        "mae_eur_mwh": float(absolute.mean()),
        "rmse_eur_mwh": float(np.sqrt(np.mean(error**2))),
        "smape_pct": float(100 * np.mean(2 * absolute / denominator)),
        "mape_guarded_pct": (
            float(100 * np.mean(absolute[valid_mape] / np.abs(actual[valid_mape])))
            if valid_mape.any()
            else None
        ),
        "mape_excluded_hours": int((~valid_mape).sum()),
        "mape_min_abs_actual_eur_mwh": MAPE_MIN_ABS_ACTUAL,
        "worst_hour": {
            "delivery_time_utc": timestamps[worst_index],
            "actual_price_eur_mwh": float(actual[worst_index]),
            "predicted_price_eur_mwh": float(predicted[worst_index]),
            "absolute_error_eur_mwh": float(absolute[worst_index]),
        },
    }
