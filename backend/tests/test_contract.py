import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from forecast.features import build_feature_matrix, scale_features
from forecast.inference import get_session, predict, verify_assets
from forecast import jobs
from forecast.metrics import evaluate
from forecast.rag import classify_question, deterministic_dynamic_answer
from forecast.timeutils import UTC, local_fields


ROOT = Path(__file__).parent.parent


def test_feature_and_model_fixtures_match_notebook():
    fixture = json.loads((Path(__file__).parent / "fixtures" / "feature_parity.json").read_text())
    observations = [
        {**row, "timestamp_utc": datetime.fromisoformat(row["timestamp_utc"].replace("Z", "+00:00"))}
        for row in fixture["observations"]
    ]
    actual = build_feature_matrix(observations)
    np.testing.assert_allclose(actual, fixture["expected_features"], rtol=1e-10, atol=1e-10)
    scaler = json.loads((ROOT / "assets" / "scaler_parameters.json").read_text())
    assert scale_features(actual, scaler).shape == (168, 15)


def test_onnx_matches_fixed_keras_smoke_fixture():
    verify_assets()
    fixture = json.loads((ROOT / "assets" / "smoke_test.json").read_text())
    scaled = np.asarray(fixture["scaled_input"], dtype=np.float32)
    session = get_session()
    output = session.run(None, {session.get_inputs()[0].name: scaled[None]})[0][0]
    np.testing.assert_allclose(output, fixture["expected_scaled_output"], rtol=1e-4, atol=1e-4)
    assert np.max(np.abs(predict(scaled) - fixture["expected_price_eur_mwh"])) < 0.01


def test_feature_validation_rejects_missing_and_nonfinite_values():
    fixture = json.loads((Path(__file__).parent / "fixtures" / "feature_parity.json").read_text())
    observations = [
        {**row, "timestamp_utc": datetime.fromisoformat(row["timestamp_utc"].replace("Z", "+00:00"))}
        for row in fixture["observations"]
    ]
    with pytest.raises(ValueError, match="336"):
        build_feature_matrix(observations[:-1])
    observations[200]["price_eur_mwh"] = float("nan")
    with pytest.raises(ValueError, match="nonfinite"):
        build_feature_matrix(observations)


def test_metrics_guard_zero_and_negative_actuals():
    rows = [
        {"delivery_time_utc": f"2024-01-01T0{i}:00:00Z", "actual_price_eur_mwh": actual, "predicted_price_eur_mwh": prediction}
        for i, (actual, prediction) in enumerate([(0.0, 2.0), (-2.0, -1.0), (4.0, 5.0)])
    ]
    result = evaluate(
        [row["actual_price_eur_mwh"] for row in rows],
        [row["predicted_price_eur_mwh"] for row in rows],
        [row["delivery_time_utc"] for row in rows],
    )
    assert result["mape_excluded_hours"] == 1
    assert result["worst_hour"]["absolute_error_eur_mwh"] == 2.0
    assert all(np.isfinite(result[name]) for name in ("mae_eur_mwh", "rmse_eur_mwh", "smape_pct", "mape_guarded_pct"))


@pytest.mark.parametrize(
    ("instant", "local"),
    [
        (datetime(2024, 3, 31, 1, tzinfo=UTC), "2024-03-31T03:00:00"),
        (datetime(2024, 10, 27, 1, tzinfo=UTC), "2024-10-27T02:00:00"),
    ],
)
def test_berlin_dst_display_preserves_utc(instant, local):
    assert local_fields(instant)[0].startswith(local)


@pytest.mark.parametrize("origin", [datetime(2024, 3, 30, 12, tzinfo=UTC), datetime(2024, 10, 26, 12, tzinfo=UTC)])
def test_dst_forecast_still_has_24_unique_utc_hours(origin):
    hours = [origin + timedelta(hours=index) for index in range(24)]
    assert len(set(hours)) == 24
    assert all(hours[index] - hours[index - 1] == timedelta(hours=1) for index in range(1, 24))


def test_duplicate_job_returns_completed_run_without_refetch(monkeypatch):
    monkeypatch.setattr(jobs, "verify_assets", lambda: {"artifacts_sha256": {"best_cnn_lstm.onnx": "hash"}})
    monkeypatch.setattr(jobs, "read_json", lambda path: {"model_version": "cnn_lstm_v1_frozen"})
    monkeypatch.setattr(jobs.db, "claim_run", lambda *args: (1, "complete"))
    monkeypatch.setattr(jobs, "fetch_observations", lambda origin: pytest.fail("idempotent run refetched SMARD"))
    result = jobs.run_daily_forecast(datetime(2024, 1, 2, 13, tzinfo=UTC))
    assert result["status"] == "complete" and result["idempotent"] is True


def test_rag_routes_and_deterministic_metrics():
    assert classify_question("What was yesterday's MAE?") == "dynamic"
    assert classify_question("What is the model architecture?") == "static"
    assert classify_question("Who won the football match?") == "unsupported"
    payload = {
        "status": "complete",
        "forecast_origin_utc": "2024-01-01T12:00:00Z",
        "metrics": {"mae_eur_mwh": 2.5, "rmse_eur_mwh": 3.0, "smape_pct": 4.0, "mape_guarded_pct": 5.0, "mape_excluded_hours": 1},
        "worst_hour": None,
        "message": "Evaluation complete.",
    }
    answer = deterministic_dynamic_answer("What was yesterday's MAE?", payload)
    assert answer["route"] == "dynamic" and "2.500 EUR/MWh" in answer["answer"]
