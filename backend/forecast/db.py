from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta

import psycopg
from psycopg.rows import dict_row

from .config import required_env


class DatabaseUnavailable(RuntimeError):
    pass


@contextmanager
def connection():
    try:
        database_url = required_env("DATABASE_URL")
    except RuntimeError as error:
        raise DatabaseUnavailable("Database configuration is unavailable.") from error
    try:
        with psycopg.connect(
            database_url, row_factory=dict_row, prepare_threshold=None
        ) as conn:
            yield conn
    except psycopg.OperationalError as error:
        raise DatabaseUnavailable("Database connection is unavailable.") from error


def ping() -> None:
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT 1")


def claim_run(
    origin_utc: datetime,
    model_version: str,
    model_sha256: str,
    input_start_utc: datetime,
    input_end_utc: datetime,
) -> tuple[int, str]:
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO forecast_runs (
                forecast_origin_utc, model_version, model_sha256,
                input_start_utc, input_end_utc, status, started_at
            ) VALUES (%s, %s, %s, %s, %s, 'running', NOW())
            ON CONFLICT (forecast_origin_utc) DO NOTHING
            RETURNING id
            """,
            (origin_utc, model_version, model_sha256, input_start_utc, input_end_utc),
        )
        inserted = cursor.fetchone()
        if inserted:
            return inserted["id"], "claimed"

        cursor.execute(
            "SELECT id, status, started_at FROM forecast_runs WHERE forecast_origin_utc = %s FOR UPDATE",
            (origin_utc,),
        )
        run = cursor.fetchone()
        if run["status"] == "complete":
            return run["id"], "complete"
        if run["status"] == "running" and run["started_at"] > datetime.now(
            run["started_at"].tzinfo
        ) - timedelta(minutes=15):
            return run["id"], "running"
        cursor.execute(
            """
            UPDATE forecast_runs
            SET status = 'running', started_at = NOW(), completed_at = NULL,
                error_code = NULL, error_message = NULL,
                model_version = %s, model_sha256 = %s,
                input_start_utc = %s, input_end_utc = %s
            WHERE id = %s
            """,
            (model_version, model_sha256, input_start_utc, input_end_utc, run["id"]),
        )
        return run["id"], "claimed"


def mark_run(run_id: int, status: str, error_code: str | None, message: str | None) -> None:
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE forecast_runs
            SET status = %s, error_code = %s, error_message = %s,
                completed_at = CASE WHEN %s IN ('complete', 'failed') THEN NOW() ELSE NULL END
            WHERE id = %s
            """,
            (status, error_code, message, status, run_id),
        )


def upsert_observations(observations: list[dict]) -> None:
    values = [
        (
            row["timestamp_utc"],
            row["price_eur_mwh"],
            row["load_actual_mwh"],
            row["load_forecast_mwh"],
        )
        for row in observations
    ]
    with connection() as conn, conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO hourly_observations (
                timestamp_utc, price_eur_mwh, load_actual_mwh, load_forecast_mwh, fetched_at
            ) VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (timestamp_utc) DO UPDATE SET
                price_eur_mwh = EXCLUDED.price_eur_mwh,
                load_actual_mwh = EXCLUDED.load_actual_mwh,
                load_forecast_mwh = EXCLUDED.load_forecast_mwh,
                fetched_at = NOW()
            """,
            values,
        )


def store_forecast(run_id: int, points: list[dict]) -> None:
    values = [
        (run_id, point["horizon"], point["delivery_time_utc"], point["predicted_price_eur_mwh"])
        for point in points
    ]
    with connection() as conn, conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO forecast_points (
                forecast_run_id, horizon, delivery_time_utc, predicted_price_eur_mwh
            ) VALUES (%s, %s, %s, %s)
            ON CONFLICT (forecast_run_id, horizon) DO UPDATE SET
                delivery_time_utc = EXCLUDED.delivery_time_utc,
                predicted_price_eur_mwh = EXCLUDED.predicted_price_eur_mwh
            """,
            values,
        )
        cursor.execute(
            """
            UPDATE forecast_runs
            SET status = 'complete', generated_at = NOW(), completed_at = NOW(),
                error_code = NULL, error_message = NULL
            WHERE id = %s
            """,
            (run_id,),
        )


def previous_forecast_rows(origin_utc: datetime) -> tuple[dict | None, list[dict]]:
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT * FROM forecast_runs
            WHERE status = 'complete' AND forecast_origin_utc < %s
            ORDER BY forecast_origin_utc DESC LIMIT 1
            """,
            (origin_utc,),
        )
        run = cursor.fetchone()
        if not run:
            return None, []
        cursor.execute(
            """
            SELECT p.horizon, p.delivery_time_utc, p.predicted_price_eur_mwh,
                   o.price_eur_mwh AS actual_price_eur_mwh
            FROM forecast_points p
            LEFT JOIN hourly_observations o ON o.timestamp_utc = p.delivery_time_utc
            WHERE p.forecast_run_id = %s
            ORDER BY p.horizon
            """,
            (run["id"],),
        )
        return run, cursor.fetchall()


def upsert_evaluation(run_id: int, available_hours: int, metrics: dict | None) -> None:
    worst = metrics.get("worst_hour") if metrics else None
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO forecast_evaluations (
                forecast_run_id, status, available_actual_hours, evaluated_at,
                mae_eur_mwh, rmse_eur_mwh, smape_pct, mape_guarded_pct,
                mape_excluded_hours, mape_min_abs_actual_eur_mwh,
                worst_delivery_time_utc, worst_actual_price_eur_mwh,
                worst_predicted_price_eur_mwh, worst_absolute_error_eur_mwh
            ) VALUES (
                %s, %s, %s, CASE WHEN %s = 24 THEN NOW() ELSE NULL END,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (forecast_run_id) DO UPDATE SET
                status = EXCLUDED.status,
                available_actual_hours = EXCLUDED.available_actual_hours,
                evaluated_at = EXCLUDED.evaluated_at,
                mae_eur_mwh = EXCLUDED.mae_eur_mwh,
                rmse_eur_mwh = EXCLUDED.rmse_eur_mwh,
                smape_pct = EXCLUDED.smape_pct,
                mape_guarded_pct = EXCLUDED.mape_guarded_pct,
                mape_excluded_hours = EXCLUDED.mape_excluded_hours,
                mape_min_abs_actual_eur_mwh = EXCLUDED.mape_min_abs_actual_eur_mwh,
                worst_delivery_time_utc = EXCLUDED.worst_delivery_time_utc,
                worst_actual_price_eur_mwh = EXCLUDED.worst_actual_price_eur_mwh,
                worst_predicted_price_eur_mwh = EXCLUDED.worst_predicted_price_eur_mwh,
                worst_absolute_error_eur_mwh = EXCLUDED.worst_absolute_error_eur_mwh
            """,
            (
                run_id,
                "complete" if metrics else "pending",
                available_hours,
                available_hours,
                metrics.get("mae_eur_mwh") if metrics else None,
                metrics.get("rmse_eur_mwh") if metrics else None,
                metrics.get("smape_pct") if metrics else None,
                metrics.get("mape_guarded_pct") if metrics else None,
                metrics.get("mape_excluded_hours") if metrics else 0,
                metrics.get("mape_min_abs_actual_eur_mwh", 1.0) if metrics else 1.0,
                worst.get("delivery_time_utc") if worst else None,
                worst.get("actual_price_eur_mwh") if worst else None,
                worst.get("predicted_price_eur_mwh") if worst else None,
                worst.get("absolute_error_eur_mwh") if worst else None,
            ),
        )


def latest_forecast() -> tuple[dict | None, list[dict]]:
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM forecast_runs WHERE status = 'complete' ORDER BY forecast_origin_utc DESC LIMIT 1"
        )
        run = cursor.fetchone()
        if not run:
            return None, []
        cursor.execute(
            "SELECT * FROM forecast_points WHERE forecast_run_id = %s ORDER BY horizon",
            (run["id"],),
        )
        return run, cursor.fetchall()


def latest_evaluation() -> dict | None:
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT e.*, r.forecast_origin_utc, r.model_version
            FROM forecast_evaluations e
            JOIN forecast_runs r ON r.id = e.forecast_run_id
            ORDER BY r.forecast_origin_utc DESC LIMIT 1
            """
        )
        return cursor.fetchone()


def latest_evaluation_series() -> tuple[dict | None, list[dict]]:
    evaluation = latest_evaluation()
    if not evaluation:
        return None, []
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.horizon, p.delivery_time_utc, p.predicted_price_eur_mwh,
                   o.price_eur_mwh AS actual_price_eur_mwh
            FROM forecast_points p
            LEFT JOIN hourly_observations o ON o.timestamp_utc = p.delivery_time_utc
            WHERE p.forecast_run_id = %s
            ORDER BY p.horizon
            """,
            (evaluation["forecast_run_id"],),
        )
        return evaluation, cursor.fetchall()


def latest_run() -> dict | None:
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT * FROM forecast_runs ORDER BY forecast_origin_utc DESC LIMIT 1")
        return cursor.fetchone()


def increment_rate_limit(client_key: str, window_start: datetime) -> int:
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "DELETE FROM rag_rate_limits WHERE window_start < NOW() - INTERVAL '1 day'"
        )
        cursor.execute(
            """
            INSERT INTO rag_rate_limits (client_key, window_start, request_count)
            VALUES (%s, %s, 1)
            ON CONFLICT (client_key, window_start) DO UPDATE
            SET request_count = rag_rate_limits.request_count + 1
            RETURNING request_count
            """,
            (client_key, window_start),
        )
        return cursor.fetchone()["request_count"]
