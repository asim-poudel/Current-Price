import Image from "next/image";
import type { DashboardData, ForecastRow } from "@/lib/types";
import { ComparisonChart } from "./ComparisonChart";
import { ForecastChart } from "./ForecastChart";
import { QuestionBar } from "./QuestionBar";

const number = (value: number | null | undefined, unit = "") => value == null ? "Pending" : `${value.toFixed(2)}${unit}`;
const date = (value: string) => new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(new Date(value));
const delivery = (value: string, timeZone: string) => new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone }).format(new Date(value));
const zoneLabel = (value: string) => value.replace(/[()]/g, "").replace(/\s+/g, " ").trim();

function berlinHeading(rows: ForecastRow[]) {
  const zones = new Set(rows.map((row) => zoneLabel(row.german_timezone)));
  return zones.size === 1 ? `Berlin time (${[...zones][0]})` : "Berlin time (CET/CEST)";
}

export function Dashboard({ health, forecast: forecastResult, evaluation: evaluationResult, series: seriesResult }: DashboardData) {
  const forecast = forecastResult.data;
  const evaluation = evaluationResult.data;
  const series = seriesResult.data;
  const connection = connectionState(health, forecastResult.issue?.status);
  const questionEnabled = health.data?.checks?.database === "ok";
  const hasMixedBerlinZones = new Set(forecast?.rows.map((row) => zoneLabel(row.german_timezone))).size > 1;

  return (
    <main>
      <header className="masthead">
        <p className="market-label">Germany - Day-ahead market</p>
        <h1><Image className="title-icon" src="/current-price-icon.png" alt="" width={425} height={419} priority />Current Price</h1>
        <p className="project-description">Current Price uses recent SMARD market and grid data to forecast Germany&apos;s next 24 day-ahead electricity prices. It also compares the previous forecast with observed prices and explains the model&apos;s latest performance.</p>
      </header>

      <dl className="status-grid" aria-label="Forecast service summary">
        <div className="meta-card" data-testid="model-card"><dt>Model</dt><dd>CNN LSTM</dd></div>
        <div className="meta-card" data-testid="update-card"><dt>Last update</dt><dd>{forecast ? `${date(forecast.generated_at_utc)} UTC` : "Awaiting first run"}</dd></div>
        <div className="meta-card" data-testid="status-card"><dt>Status</dt><dd><span className={`status ${connection.tone}`}>{connection.label}</span></dd></div>
      </dl>

      {connection.notice ? (
        <div className={`service-notice ${connection.tone}`} role="status">
          <strong>{connection.notice.title}</strong>
          <span>{connection.notice.message}</span>
        </div>
      ) : null}

      <section className="dashboard-card forecast-chart-card" aria-labelledby="forecast-title">
        <div className="section-heading">
          <div><p className="section-label">Next 24 delivery hours</p><h2 id="forecast-title">Day-ahead price path</h2></div>
          <p className="unit">EUR / MWh</p>
        </div>
        {forecast?.rows.length ? <ForecastChart rows={forecast.rows} /> : <Empty text={connection.emptyMessage} />}
      </section>

      {forecast?.rows.length ? (
        <section className="dashboard-card forecast-table-card" aria-labelledby="forecast-table-title">
          <div className="section-heading table-heading">
            <div><p className="section-label">24 hourly values</p><h2 id="forecast-table-title">Hourly forecast</h2></div>
            <p className="table-hint">Six rows visible</p>
          </div>
          <div className="table-wrap forecast-table" role="region" aria-label="Scrollable hourly electricity price forecast" tabIndex={0}>
            <table>
              <caption className="sr-only">All 24 hourly forecast values</caption>
              <colgroup><col className="col-berlin" /><col className="col-utc" /><col className="col-price" /><col className="col-unit" /></colgroup>
              <thead><tr><th>{berlinHeading(forecast.rows)}</th><th>UTC time</th><th className="numeric">Price</th><th>Unit</th></tr></thead>
              <tbody>{forecast.rows.map((row) => <tr key={row.horizon}><td>{delivery(row.delivery_time_utc, "Europe/Berlin")}{hasMixedBerlinZones ? <small className="inline-zone">{zoneLabel(row.german_timezone).split(" ")[0]}</small> : null}</td><td>{delivery(row.delivery_time_utc, "UTC")}</td><td className={`numeric ${row.predicted_price_eur_mwh < 0 ? "negative" : ""}`}>{row.predicted_price_eur_mwh.toFixed(2)}</td><td>EUR/MWh</td></tr>)}</tbody>
            </table>
          </div>
          <MobileForecast rows={forecast.rows} />
        </section>
      ) : null}

      <section className="dashboard-card evaluation" aria-labelledby="evaluation-title">
        <div className="section-heading">
          <div><p className="section-label">Previous forecast</p><h2 id="evaluation-title">Prediction vs. observed price</h2></div>
          {evaluation ? <span className={`status ${evaluation.status === "complete" ? "ok" : "pending"}`}>{evaluation.status === "complete" ? "24 / 24 actuals" : `${evaluation.available_actual_hours} / 24 actuals`}</span> : null}
        </div>
        <div className="evaluation-grid">
          <div>{series?.rows.length ? <ComparisonChart rows={series.rows} /> : <Empty text="The prior forecast comparison will appear after a forecast run." />}</div>
          <div className="metrics">
            <Metric label="MAE" value={number(evaluation?.metrics?.mae_eur_mwh)} unit="EUR/MWh" />
            <Metric label="RMSE" value={number(evaluation?.metrics?.rmse_eur_mwh)} unit="EUR/MWh" />
            <Metric label="sMAPE" value={number(evaluation?.metrics?.smape_pct, "%")} />
            <Metric label="Guarded MAPE" value={number(evaluation?.metrics?.mape_guarded_pct, "%")} note={evaluation?.metrics ? `${evaluation.metrics.mape_excluded_hours} excluded below ${evaluation.metrics.mape_min_abs_actual_eur_mwh} EUR/MWh` : undefined} />
            <div className="worst"><span>Worst hour</span><strong>{evaluation?.worst_hour ? number(evaluation.worst_hour.absolute_error_eur_mwh, " EUR/MWh") : "Pending"}</strong>{evaluation?.worst_hour ? <small>{date(evaluation.worst_hour.delivery_time_utc)} UTC</small> : null}</div>
          </div>
        </div>
      </section>

      <QuestionBar enabled={questionEnabled} disabledReason={connection.questionMessage} />
      <footer>• notjustauser • DATA SOURCE: SMARD</footer>
    </main>
  );
}

function MobileForecast({ rows }: { rows: ForecastRow[] }) {
  return (
    <div className="forecast-mobile-scroll" role="region" aria-label="Scrollable hourly electricity price cards" tabIndex={0}>
      <ul className="forecast-mobile" aria-label="All 24 hourly forecast values">
        {rows.map((row) => (
          <li key={row.horizon}>
            <div className="mobile-hour-time">
              <strong>{delivery(row.delivery_time_utc, "Europe/Berlin")}</strong>
              <span>{zoneLabel(row.german_timezone)}</span>
              <small>{delivery(row.delivery_time_utc, "UTC")} UTC</small>
            </div>
            <b className={row.predicted_price_eur_mwh < 0 ? "negative" : ""}>{row.predicted_price_eur_mwh.toFixed(2)} <small>EUR/MWh</small></b>
          </li>
        ))}
      </ul>
    </div>
  );
}

function connectionState(health: DashboardData["health"], forecastStatus?: number) {
  if (health.issue?.kind === "not_configured") return {
    label: "Not configured", tone: "error", emptyMessage: "Forecast data is unavailable until the backend API address is configured.",
    questionMessage: "Questions are unavailable until the backend API address is configured.",
    notice: { title: "Backend API not configured", message: "Set the frontend API address, then restart the frontend." },
  };
  if (health.issue) return {
    label: "Unreachable", tone: "error", emptyMessage: "Forecast data is unavailable because the backend could not be reached.",
    questionMessage: "Questions are unavailable while the backend cannot be reached.",
    notice: { title: "Backend unavailable", message: "The dashboard could not connect to the forecast service." },
  };
  if (!health.data?.checks) return {
    label: "Incompatible", tone: "error", emptyMessage: "Forecast data is unavailable because the backend response is not compatible with this dashboard.",
    questionMessage: "Questions are unavailable until the current backend is running.",
    notice: { title: "Wrong backend is running", message: "Stop the service on port 8000 and restart FastAPI from this project's backend folder." },
  };
  if (health.data.checks.database === "error") return {
    label: "Setup required", tone: "error", emptyMessage: "Forecast data will appear after the database is connected and the first job completes.",
    questionMessage: "Questions are unavailable until the database is connected.",
    notice: { title: "Database unavailable", message: "The backend is online, but its database connection needs attention." },
  };
  if (health.data.checks.model === "error") return {
    label: "Degraded", tone: "error", emptyMessage: "Forecast data is unavailable while model validation is failing.",
    questionMessage: undefined,
    notice: { title: "Model validation failed", message: "The backend is online, but the production model assets did not validate." },
  };
  if (forecastStatus === 404) return {
    label: "Ready", tone: "pending", emptyMessage: "The backend and database are connected. The first completed forecast is still pending.",
    questionMessage: undefined,
    notice: { title: "Awaiting first forecast", message: "The service is ready; forecast values will appear after the daily job completes." },
  };
  return { label: "Live", tone: "ok", emptyMessage: "No completed forecast is available yet.", questionMessage: undefined, notice: null };
}

function Metric({ label, value, unit, note }: { label: string; value: string; unit?: string; note?: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong>{unit ? <small>{unit}</small> : null}{note ? <small>{note}</small> : null}</div>;
}

function Empty({ text }: { text: string }) {
  return <div className="empty" role="status">{text}</div>;
}
