from __future__ import annotations

from datetime import datetime, timedelta

from . import db
from .config import MODEL_CONFIG_PATH, SCALER_PATH, read_json
from .features import build_feature_matrix, scale_features
from .inference import predict, verify_assets
from .metrics import evaluate
from .smard import SourceDataIncomplete, fetch_observations
from .timeutils import UTC, iso_utc


class JobInProgress(RuntimeError):
    pass


def canonical_origin(now: datetime | None = None) -> datetime:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    origin = now.replace(hour=12, minute=0, second=0, microsecond=0)
    return origin if now >= origin else origin - timedelta(days=1)


def evaluate_previous(origin_utc: datetime) -> None:
    run, rows = db.previous_forecast_rows(origin_utc)
    if not run:
        return
    available = sum(row["actual_price_eur_mwh"] is not None for row in rows)
    metrics = None
    if len(rows) == 24 and available == 24:
        metrics = evaluate(
            [row["actual_price_eur_mwh"] for row in rows],
            [row["predicted_price_eur_mwh"] for row in rows],
            [iso_utc(row["delivery_time_utc"]) for row in rows],
        )
        metrics["worst_hour"]["delivery_time_utc"] = rows[
            max(
                range(24),
                key=lambda index: abs(
                    rows[index]["predicted_price_eur_mwh"]
                    - rows[index]["actual_price_eur_mwh"]
                ),
            )
        ]["delivery_time_utc"]
    db.upsert_evaluation(run["id"], available, metrics)


def run_daily_forecast(now: datetime | None = None) -> dict:
    origin = canonical_origin(now)
    manifest = verify_assets()
    config = read_json(MODEL_CONFIG_PATH)
    scaler = read_json(SCALER_PATH)
    run_id, state = db.claim_run(
        origin,
        config["model_version"],
        manifest["artifacts_sha256"]["best_cnn_lstm.onnx"],
        origin - timedelta(hours=168),
        origin - timedelta(hours=1),
    )
    if state == "complete":
        return {"schema_version": "1.0", "status": "complete", "forecast_origin_utc": iso_utc(origin), "idempotent": True}
    if state == "running":
        raise JobInProgress("A forecast job for this origin is already running.")

    try:
        observations = fetch_observations(origin)
        db.upsert_observations(observations)
        evaluate_previous(origin)
        matrix = build_feature_matrix(observations)
        scaled = scale_features(matrix, scaler)
        prediction = predict(scaled)
        points = [
            {
                "horizon": horizon + 1,
                "delivery_time_utc": origin + timedelta(hours=horizon),
                "predicted_price_eur_mwh": float(value),
            }
            for horizon, value in enumerate(prediction)
        ]
        db.store_forecast(run_id, points)
        return {
            "schema_version": "1.0",
            "status": "complete",
            "forecast_origin_utc": iso_utc(origin),
            "forecast_points": 24,
            "idempotent": False,
        }
    except SourceDataIncomplete as error:
        db.mark_run(run_id, "pending", "source_incomplete", str(error))
        return {"schema_version": "1.0", "status": "pending", "forecast_origin_utc": iso_utc(origin), "message": str(error)}
    except Exception as error:
        db.mark_run(run_id, "failed", type(error).__name__, str(error)[:500])
        raise
