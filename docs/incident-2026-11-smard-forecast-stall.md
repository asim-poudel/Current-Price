# Forecast updates stopped after 19 November 2026

**Observed:** 24 November 2026, 16:41 UTC (22:26 Nepal time)

**Affected service:** [Current Price website](https://current-price-hhh.vercel.app/)

**Status at observation:** Forecast generation blocked by incomplete SMARD data; backend and database reachable.

## What happened

The last completed forecast has origin **19 November 2026, 12:00 UTC** and was generated at **13:25 UTC** that day. The daily job continued to start on 20, 21, 22, 23, and 24 November, but each of those runs ended as `pending` with error code `source_incomplete`. The website kept returning the most recent *completed* forecast, so visitors saw the 19 November values after their delivery hours had passed. Before the local display fix described below, it also showed a misleading **Live** status.

| Date, UTC | Production job result | Evidence |
| --- | --- | --- |
| 18 November | Pending | Four required SMARD hours were unavailable at that day's run. |
| 19 November | Complete | 24 forecast points stored; latest completed forecast. |
| 20–24 November | Pending each day | Database rows have `error_code = source_incomplete`; the 24 November row reports 74 missing required hours. |

## Why the pipeline stopped

The backend cron is configured for **13:00 UTC daily** in [`backend/vercel.json`](../backend/vercel.json). [`run_daily_forecast`](../backend/forecast/jobs.py) first claims a database row, then asks [`fetch_observations`](../backend/forecast/smard.py) for **336 consecutive hourly observations** ending one hour before the 12:00 UTC forecast origin. Every hour must contain all three inputs: Germany/Luxembourg day-ahead price, German actual grid load, and German forecast grid load. The job does not interpolate missing values. If any required input is absent, it marks the run `pending` *before* feature construction and model inference. This is the intended data-quality guard: a forecast with fabricated or misaligned inputs would be misleading.

On 24 November, direct reads of SMARD's hourly JSON showed:

| Input | Missing required hours | Missing span, UTC |
| --- | ---: | --- |
| Day-ahead price (filter 4169, `DE-LU`) | 61 | 19 Nov 23:00–21 Nov 22:00 (48 hours); 23 Nov 23:00–24 Nov 11:00 (13 hours) |
| Actual grid load (filter 410, `DE`) | 26 | 23 Nov 10:00–24 Nov 11:00 |
| Forecast grid load (filter 411, `DE`) | 0 | Complete for the required window |

The price and actual-load gaps overlap, so **74 distinct hours** are incomplete. SMARD's quarter-hour data and the alternate `DE` region for the price series did not fill these gaps when checked. The relevant source indexes are [price](https://www.smard.de/app/chart_data/4169/DE-LU/index_hour.json) and [actual load](https://www.smard.de/app/chart_data/410/DE/index_hour.json). Their indexes point to weekly JSON blocks; some rows in those blocks have `null` values. The **reason SMARD has not supplied those values is unconfirmed**. This investigation found no evidence that the project deleted them or that a database write caused the gap.

## What was checked

- The [public backend health endpoint](https://current-price-two.vercel.app/api/health) returned `status: ok`, with model and database checks both `ok`; its latest job was `2026-11-24T12:00:00Z`, `pending`.
- The [current forecast endpoint](https://current-price-two.vercel.app/api/forecast/current) returned the completed 19 November forecast with 24 points. The [latest evaluation](https://current-price-two.vercel.app/api/evaluation/latest) was for the 17 November forecast; later input gaps prevented newer evaluations.
- A **read-only production PostgreSQL query** found 42 completed runs, 16 pending runs, and zero failed runs. All completed runs had 24 forecast points. There were no orphan evaluations or incomplete stored observations. The latest stored observation was 19 November 11:00 UTC, consistent with ingestion stopping when the subsequent windows failed validation.
- Local backend tests passed: **21/21**, including the fixed-model inference fixture. This does not prove that production inference ran after 19 November; pending jobs stop before inference.
- The Vercel CLI token on this machine was invalid, so Vercel execution logs could not be inspected. The database run timestamps and error codes provide direct evidence that the scheduled endpoint was invoked each day.

## Recovery

1. Check the three SMARD hourly series for the **current** 336-hour input window. All required hours must have non-null values. A fresh job attempt will remain pending until the gaps are filled; repeatedly invoking it sooner will not produce a valid forecast.
2. Once the source window is complete, allow the next 13:00 UTC cron run or rerun the current day's job with the backend's `CRON_SECRET`. For example, from a trusted PowerShell session with that secret already in the environment:

   ```powershell
   Invoke-RestMethod -Method Post -Uri 'https://current-price-two.vercel.app/api/jobs/daily-forecast' -Headers @{ Authorization = "Bearer $env:CRON_SECRET" }
   ```

3. Confirm `/api/health` reports the current job as `complete`, `/api/forecast/current` has the new origin and 24 points, and the website shows the new generated time. If the job remains pending, read the latest `forecast_runs.error_message` and check SMARD again.
4. The current job endpoint always selects the current 12:00 UTC origin. It does **not** backfill missed forecast dates. Historical backfill would require a controlled date-specific job and a source fetcher that selects weekly blocks for that date; the present fetcher reads only the newest three blocks.

## Changes and prevention

The frontend change in [`Dashboard.tsx`](../frontend/components/Dashboard.tsx) shows **Data pending**, identifies the last completed forecast, and labels its chart **Last completed forecast** when a newer run is pending. Lint and the new dashboard regression test passed. At the time of the initial investigation, this change had not yet been deployed because the local Vercel CLI token was invalid. Confirm the production page after the GitHub-triggered deployment.

Recommended follow-up work:

1. Alert on forecast age, `pending` runs, and per-series SMARD completeness. A healthy database connection alone does not mean the forecast is current.
2. Add a retry schedule that fits the hosting plan so data published after the daily run can be used promptly. Retries help only after SMARD supplies the missing values.
3. If forecasts for missed dates matter, build an explicit backfill path with date-specific weekly-block selection and tests. Do not silently impute missing prices or loads or substitute another source without validating units, timestamps, and model feature compatibility.

**Lesson:** Treat source freshness, job completion, database health, and displayed forecast age as separate signals. The pipeline correctly refused incomplete input; the monitoring and page status did not make that distinction clear enough.
