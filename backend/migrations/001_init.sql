CREATE TABLE IF NOT EXISTS hourly_observations (
    timestamp_utc TIMESTAMPTZ PRIMARY KEY,
    price_eur_mwh DOUBLE PRECISION NOT NULL,
    load_actual_mwh DOUBLE PRECISION NOT NULL,
    load_forecast_mwh DOUBLE PRECISION NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS forecast_runs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    forecast_origin_utc TIMESTAMPTZ NOT NULL UNIQUE,
    model_version TEXT NOT NULL,
    model_sha256 TEXT NOT NULL,
    input_start_utc TIMESTAMPTZ NOT NULL,
    input_end_utc TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'pending', 'complete', 'failed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    generated_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_code TEXT,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS forecast_points (
    forecast_run_id BIGINT NOT NULL REFERENCES forecast_runs(id) ON DELETE CASCADE,
    horizon SMALLINT NOT NULL CHECK (horizon BETWEEN 1 AND 24),
    delivery_time_utc TIMESTAMPTZ NOT NULL,
    predicted_price_eur_mwh DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (forecast_run_id, horizon),
    UNIQUE (forecast_run_id, delivery_time_utc)
);

CREATE TABLE IF NOT EXISTS forecast_evaluations (
    forecast_run_id BIGINT PRIMARY KEY REFERENCES forecast_runs(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('pending', 'complete')),
    available_actual_hours SMALLINT NOT NULL CHECK (available_actual_hours BETWEEN 0 AND 24),
    evaluated_at TIMESTAMPTZ,
    mae_eur_mwh DOUBLE PRECISION,
    rmse_eur_mwh DOUBLE PRECISION,
    smape_pct DOUBLE PRECISION,
    mape_guarded_pct DOUBLE PRECISION,
    mape_excluded_hours SMALLINT NOT NULL DEFAULT 0,
    mape_min_abs_actual_eur_mwh DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    worst_delivery_time_utc TIMESTAMPTZ,
    worst_actual_price_eur_mwh DOUBLE PRECISION,
    worst_predicted_price_eur_mwh DOUBLE PRECISION,
    worst_absolute_error_eur_mwh DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS rag_rate_limits (
    client_key TEXT NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    request_count INTEGER NOT NULL CHECK (request_count > 0),
    PRIMARY KEY (client_key, window_start)
);

CREATE INDEX IF NOT EXISTS forecast_runs_status_origin_idx
    ON forecast_runs (status, forecast_origin_utc DESC);
