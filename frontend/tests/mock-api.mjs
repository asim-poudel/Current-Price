import { createServer } from "node:http";

let mode = "healthy";

function rowsFor(originText, zoneForIndex) {
  const origin = new Date(originText);
  return Array.from({ length: 24 }, (_, index) => {
    const instant = new Date(origin.getTime() + index * 3_600_000);
    const zone = zoneForIndex(index);
    const offsetHours = zone.startsWith("CEST") ? 2 : 1;
    return {
      horizon: index + 1,
      delivery_time_utc: instant.toISOString(),
      delivery_time_local: new Date(instant.getTime() + offsetHours * 3_600_000).toISOString().replace("Z", offsetHours === 2 ? "+02:00" : "+01:00"),
      german_timezone: zone,
      predicted_price_eur_mwh: index === 5 ? -4.25 : 62 + Math.sin(index / 3) * 18,
    };
  });
}

const summerOrigin = "2026-09-28T12:00:00Z";
const summerRows = rowsFor(summerOrigin, () => "CEST (+02:00)");
const winterRows = rowsFor("2026-01-15T12:00:00Z", () => "CET (+01:00)");
const mixedRows = rowsFor("2026-03-29T00:00:00Z", (index) => index === 0 ? "CET (+01:00)" : "CEST (+02:00)");

const health = { schema_version: "1.0", status: "ok", model_version: "cnn_lstm_v1_frozen", checks: { model: "ok", database: "ok" }, latest_job: { forecast_origin_utc: summerOrigin, status: "complete" } };
const evaluation = { schema_version: "1.0", status: "complete", forecast_origin_utc: "2026-09-27T12:00:00Z", available_actual_hours: 24, metrics: { mae_eur_mwh: 5.2, rmse_eur_mwh: 7.1, smape_pct: 8.3, mape_guarded_pct: 9.4, mape_excluded_hours: 1, mape_min_abs_actual_eur_mwh: 1 }, worst_hour: { delivery_time_utc: "2026-09-27T18:00:00Z", actual_price_eur_mwh: 50, predicted_price_eur_mwh: 72, absolute_error_eur_mwh: 22 }, message: "Evaluation complete." };
const series = { schema_version: "1.0", status: "complete", rows: summerRows.map((row, index) => ({ ...row, actual_price_eur_mwh: index === 23 ? null : row.predicted_price_eur_mwh + Math.cos(index) * 5 })) };

function forecast() {
  const rows = mode === "winter" ? winterRows : mode === "mixed" ? mixedRows : summerRows;
  return { schema_version: "1.0", status: "complete", model_version: "cnn_lstm_v1_frozen", forecast_origin_utc: rows[0].delivery_time_utc, generated_at_utc: "2026-09-28T13:05:00Z", rows };
}

createServer((request, response) => {
  response.setHeader("Access-Control-Allow-Origin", "*");
  response.setHeader("Access-Control-Allow-Headers", "Content-Type");
  response.setHeader("Content-Type", "application/json");
  if (request.method === "OPTIONS") return response.writeHead(204).end();
  if (request.url?.startsWith("/__test/mode/")) {
    mode = request.url.split("/").at(-1) ?? "healthy";
    return response.end(JSON.stringify({ mode }));
  }

  if (mode === "unavailable") {
    response.writeHead(503);
    return response.end(JSON.stringify({ schema_version: "1.0", error: { code: "service_unavailable", message: "The service is unavailable." } }));
  }
  if (mode === "incompatible" && request.url === "/api/health") return response.end(JSON.stringify({ status: "ok" }));
  if (mode === "degraded" && request.url === "/api/health") return response.end(JSON.stringify({ schema_version: "1.0", status: "degraded", model_version: "cnn_lstm_v1_frozen", checks: { model: "ok", database: "error" }, latest_job: null }));
  if (mode === "degraded") {
    response.writeHead(503);
    return response.end(JSON.stringify({ schema_version: "1.0", error: { code: "database_unavailable", message: "The database service is unavailable." } }));
  }
  if (mode === "empty" && request.url !== "/api/health" && request.url !== "/api/rag/ask") {
    response.writeHead(404);
    return response.end(JSON.stringify({ schema_version: "1.0", error: { code: "not_found", message: "No forecast is available yet." } }));
  }
  if (request.url === "/api/rag/ask") return response.end(JSON.stringify({ schema_version: "1.0", answer: "Yesterday's MAE was 5.20 EUR/MWh.", source_ids: ["dynamic:previous_evaluation"], data_status: "complete", route: "dynamic" }));
  if (request.url === "/api/health") return response.end(JSON.stringify(health));
  if (request.url === "/api/forecast/current") return response.end(JSON.stringify(forecast()));
  if (request.url === "/api/evaluation/latest") return response.end(JSON.stringify(evaluation));
  if (request.url === "/api/evaluation/latest/series") return response.end(JSON.stringify(series));
  response.writeHead(404);
  response.end(JSON.stringify({ detail: "Not found" }));
}).listen(4010, "127.0.0.1");
