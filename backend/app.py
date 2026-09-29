from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from forecast import db
from forecast.config import MODEL_CONFIG_PATH, allowed_origins, read_json, required_env
from forecast.inference import verify_assets
from forecast.jobs import JobInProgress, run_daily_forecast
from forecast.rag import answer_question
from forecast.timeutils import UTC, iso_utc, local_fields


app = FastAPI(title="Electricity Forecast API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "schema_version": "1.0",
            "error": {"code": code, "message": message},
        },
    )


@app.exception_handler(db.DatabaseUnavailable)
def database_unavailable(_: Request, __: db.DatabaseUnavailable):
    return _error(503, "database_unavailable", "The database service is unavailable.")


@app.exception_handler(HTTPException)
def http_error(_: Request, error: HTTPException):
    codes = {
        401: "unauthorized",
        404: "not_found",
        409: "job_in_progress",
        422: "invalid_request",
        429: "rate_limited",
        503: "service_unavailable",
    }
    message = error.detail if isinstance(error.detail, str) else "The request could not be completed."
    return _error(error.status_code, codes.get(error.status_code, "request_failed"), message)


@app.exception_handler(RequestValidationError)
def validation_error(_: Request, __: RequestValidationError):
    return _error(422, "invalid_request", "The request payload is invalid.")


def _job_authorized(request: Request) -> bool:
    secret = required_env("CRON_SECRET")
    return hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {secret}")


def _serialize_forecast(run: dict, rows: list[dict]) -> dict:
    origin_local, origin_zone = local_fields(run["forecast_origin_utc"])
    return {
        "schema_version": "1.0",
        "status": run["status"],
        "model_version": run["model_version"],
        "forecast_origin_utc": iso_utc(run["forecast_origin_utc"]),
        "forecast_origin_local": origin_local,
        "forecast_origin_timezone": origin_zone,
        "generated_at_utc": iso_utc(run["generated_at"]),
        "rows": [
            {
                "horizon": row["horizon"],
                "delivery_time_utc": iso_utc(row["delivery_time_utc"]),
                "delivery_time_local": local_fields(row["delivery_time_utc"])[0],
                "german_timezone": local_fields(row["delivery_time_utc"])[1],
                "predicted_price_eur_mwh": row["predicted_price_eur_mwh"],
            }
            for row in rows
        ],
    }


def _evaluation_payload(evaluation: dict) -> dict:
    complete = evaluation["status"] == "complete"
    metrics = (
        {
            "evaluated_hours": 24,
            "mae_eur_mwh": evaluation["mae_eur_mwh"],
            "rmse_eur_mwh": evaluation["rmse_eur_mwh"],
            "smape_pct": evaluation["smape_pct"],
            "mape_guarded_pct": evaluation["mape_guarded_pct"],
            "mape_excluded_hours": evaluation["mape_excluded_hours"],
            "mape_min_abs_actual_eur_mwh": evaluation["mape_min_abs_actual_eur_mwh"],
        }
        if complete
        else None
    )
    worst = (
        {
            "delivery_time_utc": iso_utc(evaluation["worst_delivery_time_utc"]),
            "actual_price_eur_mwh": evaluation["worst_actual_price_eur_mwh"],
            "predicted_price_eur_mwh": evaluation["worst_predicted_price_eur_mwh"],
            "absolute_error_eur_mwh": evaluation["worst_absolute_error_eur_mwh"],
        }
        if complete
        else None
    )
    return {
        "schema_version": "1.0",
        "data_class": "live_operational",
        "is_live": True,
        "status": evaluation["status"],
        "model_version": evaluation["model_version"],
        "forecast_origin_utc": iso_utc(evaluation["forecast_origin_utc"]),
        "available_actual_hours": evaluation["available_actual_hours"],
        "metrics": metrics,
        "worst_hour": worst,
        "message": "Evaluation complete." if complete else "Evaluation is waiting for all 24 actual prices.",
    }


@app.get("/api/forecast/current")
def current_forecast():
    run, rows = db.latest_forecast()
    if not run:
        raise HTTPException(status_code=404, detail="No completed forecast is available yet.")
    return _serialize_forecast(run, rows)


@app.get("/api/evaluation/latest")
def current_evaluation():
    evaluation = db.latest_evaluation()
    if not evaluation:
        raise HTTPException(status_code=404, detail="No operational evaluation is available yet.")
    return _evaluation_payload(evaluation)


@app.get("/api/evaluation/latest/series")
def current_evaluation_series():
    evaluation, rows = db.latest_evaluation_series()
    if not evaluation:
        raise HTTPException(status_code=404, detail="No operational evaluation is available yet.")
    return {
        "schema_version": "1.0",
        "status": evaluation["status"],
        "forecast_origin_utc": iso_utc(evaluation["forecast_origin_utc"]),
        "rows": [
            {
                "horizon": row["horizon"],
                "delivery_time_utc": iso_utc(row["delivery_time_utc"]),
                "delivery_time_local": local_fields(row["delivery_time_utc"])[0],
                "german_timezone": local_fields(row["delivery_time_utc"])[1],
                "predicted_price_eur_mwh": row["predicted_price_eur_mwh"],
                "actual_price_eur_mwh": row["actual_price_eur_mwh"],
            }
            for row in rows
        ],
    }


@app.post("/api/rag/ask")
def ask(body: AskRequest, request: Request):
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question cannot be empty.")
    forwarded = request.headers.get("x-forwarded-for", "unknown").split(",", 1)[0].strip()
    client_key = hmac.new(
        required_env("RATE_LIMIT_SALT").encode(), forwarded.encode(), hashlib.sha256
    ).hexdigest()
    window = datetime.now(UTC).replace(second=0, microsecond=0)
    if db.increment_rate_limit(client_key, window) > 10:
        raise HTTPException(status_code=429, detail="Question limit reached. Try again in one minute.")
    evaluation = db.latest_evaluation()
    dynamic = _evaluation_payload(evaluation) if evaluation else None
    try:
        return answer_question(question, dynamic)
    except Exception as error:
        raise HTTPException(status_code=503, detail="The grounded answer service is temporarily unavailable.") from error


@app.get("/api/jobs/daily-forecast")
@app.post("/api/jobs/daily-forecast")
def daily_forecast(request: Request):
    if not _job_authorized(request):
        raise HTTPException(status_code=401, detail="Unauthorized.")
    try:
        result = run_daily_forecast()
    except JobInProgress as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return JSONResponse(result, status_code=202 if result["status"] == "pending" else 200)


@app.get("/api/health")
def health():
    checks: dict[str, str] = {}
    try:
        manifest = verify_assets()
        checks["model"] = "ok"
        model_version = manifest["model_version"]
    except Exception:
        checks["model"] = "error"
        model_version = read_json(MODEL_CONFIG_PATH).get("model_version", "unknown")
    try:
        db.ping()
        checks["database"] = "ok"
        run = db.latest_run()
    except Exception:
        checks["database"] = "error"
        run = None
    return {
        "schema_version": "1.0",
        "status": "ok" if all(value == "ok" for value in checks.values()) else "degraded",
        "model_version": model_version,
        "checks": checks,
        "latest_job": (
            {
                "forecast_origin_utc": iso_utc(run["forecast_origin_utc"]),
                "status": run["status"],
            }
            if run
            else None
        ),
    }
