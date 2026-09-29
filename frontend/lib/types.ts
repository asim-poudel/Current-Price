export type ForecastRow = {
  horizon: number;
  delivery_time_utc: string;
  delivery_time_local: string;
  german_timezone: string;
  predicted_price_eur_mwh: number;
};

export type Forecast = {
  schema_version: "1.0";
  status: string;
  model_version: string;
  forecast_origin_utc: string;
  generated_at_utc: string;
  rows: ForecastRow[];
};

export type Evaluation = {
  schema_version: "1.0";
  status: "pending" | "complete";
  forecast_origin_utc: string;
  available_actual_hours: number;
  metrics: null | {
    mae_eur_mwh: number;
    rmse_eur_mwh: number;
    smape_pct: number;
    mape_guarded_pct: number | null;
    mape_excluded_hours: number;
    mape_min_abs_actual_eur_mwh: number;
  };
  worst_hour: null | {
    delivery_time_utc: string;
    actual_price_eur_mwh: number;
    predicted_price_eur_mwh: number;
    absolute_error_eur_mwh: number;
  };
  message: string;
};

export type EvaluationSeries = {
  schema_version: "1.0";
  status: "pending" | "complete";
  rows: Array<ForecastRow & { actual_price_eur_mwh: number | null }>;
};

export type Health = {
  schema_version: "1.0";
  status: "ok" | "degraded";
  model_version: string;
  checks: { model: "ok" | "error"; database: "ok" | "error" };
  latest_job: null | { forecast_origin_utc: string; status: string };
};

export type ApiError = {
  schema_version: "1.0";
  error: { code: string; message: string };
};

export type ApiIssue = {
  kind: "not_configured" | "unreachable" | "response_error";
  status?: number;
  code?: string;
  message: string;
};

export type ApiResult<T> = { data: T | null; issue: ApiIssue | null };

export type DashboardData = {
  health: ApiResult<Health>;
  forecast: ApiResult<Forecast>;
  evaluation: ApiResult<Evaluation>;
  series: ApiResult<EvaluationSeries>;
};
