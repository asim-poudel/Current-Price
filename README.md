# Current Price

Current Price forecasts Germany's next 24 day-ahead electricity prices. It combines recent SMARD market data, a frozen CNN-LSTM model, a FastAPI service, PostgreSQL storage, and a responsive Next.js dashboard. This guide explains the repository, the forecast pipeline, local setup, tests, and Vercel deployment.

## Live deployment

Website: [https://current-price-hhh.vercel.app](https://current-price-hhh.vercel.app)

## What the application shows

The dashboard presents the current 24-hour forecast and the result of the previous forecast:

- A 24-hour day-ahead price chart and hourly values in EUR/MWh
- Berlin and Coordinated Universal Time (UTC) delivery timestamps
- Predicted prices compared with observed prices from SMARD
- Mean absolute error (MAE), root mean squared error (RMSE), symmetric mean absolute percentage error (sMAPE), guarded MAPE, and the worst forecast hour
- Project Q&A grounded in static model documentation and current evaluation data
- Backend, model, database, and forecast status

## How forecasting works

Each run uses a canonical forecast origin of 12:00 UTC:

1. The backend downloads price and load data from the newest three SMARD weekly blocks.
2. It selects exactly 336 hourly observations from `origin - 336h` through `origin - 1h`.
3. It rejects missing hours, duplicate timestamps, nulls, and nonfinite values. The backend never interpolates production data.
4. The first 168 hours warm the lag and rolling features. The final 168 rows form the model input.
5. The backend builds 15 features in the frozen training order, applies the stored scaler, and runs ONNX Runtime with an input shape of `(1, 168, 15)`.
6. The model returns 24 scaled prices. The backend reverses the target scaling and stores one prediction for each UTC delivery hour.
7. The next run evaluates the preceding forecast after all 24 observed prices are available.

The SMARD series are:

| Data | Filter | Region |
| --- | --- | --- |
| Day-ahead price | `4169` | `DE-LU` |
| Actual grid load | `410` | `DE` |
| Forecast grid load | `411` | `DE` |

The model is frozen. Daily jobs run inference only and never retrain it.

## Application flow

The backend owns ingestion and inference. PostgreSQL connects the scheduled job to the public API and dashboard:

```text
SMARD API
   |
   v
FastAPI daily job -> validation -> 15 features -> scaler -> ONNX model
   |                                                     |
   +---------------- PostgreSQL <------------------------+
                         |
                         v
              Forecast, evaluation, and Q&A APIs
                         |
                         v
                  Next.js dashboard
```

The Q&A route handles current metric questions with deterministic code. Static and mixed questions use the bundled retrieval index and Gemini. The static index never stores dynamic evaluation values.

## Project structure

The repository separates deployable services from research and export artifacts:

| Path | Purpose |
| --- | --- |
| `backend/app.py` | FastAPI routes, error envelopes, CORS, and request validation |
| `backend/forecast/` | SMARD ingestion, feature engineering, ONNX inference, metrics, database access, jobs, and Q&A |
| `backend/assets/` | Deployable ONNX model, scaler parameters, smoke fixture, RAG index, and SHA-256 manifest |
| `backend/migrations/` | PostgreSQL schema |
| `backend/tests/` | Backend contract, feature, job, metric, and API tests |
| `frontend/app/` | Next.js App Router entry point and global design system |
| `frontend/components/` | Dashboard, charts, forecast table, metrics, and Q&A components |
| `frontend/lib/` | Typed API client and public response types |
| `frontend/tests/` | Mock API and Playwright browser tests |
| `scripts/local-smoke.ps1` | Docker-backed frontend and backend integration check |
| `scripts/export_model.py` | Controlled Keras-to-ONNX export and artifact refresh |
| `notebook/` | Data preparation, feature, model, evaluation, and RAG notebooks |
| `data/` | Archived SMARD source data and processed research data |
| `models/` | Original Keras model and training-time scalers |
| `rag_assets/` | Source RAG artifacts used by the export process |
| `results/` | Offline predictions and evaluation reports |
| `docs/` | Data dictionary and static RAG source material |
| `compose.yaml` | Local PostgreSQL 17 service |

## Prerequisites

Install these tools before starting:

- Python 3.12
- uv 0.11 or later
- Node.js 20.9 or later
- Docker Desktop with the Docker engine running
- PowerShell 7 or Windows PowerShell 5.1

Gemini is optional for local forecasting. Add a Gemini API key only when you need static or mixed Q&A answers.

## Configure local environment files

The `.env.example` files are templates. Applications do not read them directly. Copy each template to `.env.local` from the repository root:

```powershell
Copy-Item backend\.env.example backend\.env.local
Copy-Item frontend\.env.example frontend\.env.local
```

The local templates already contain the Docker database address, development-only job secret, rate-limit salt, and both supported frontend origins. Keep production secrets out of these files and out of the frontend.

Backend variables:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection string |
| `GEMINI_API_KEY` | Gemini access for static and mixed Q&A |
| `CRON_SECRET` | Bearer secret for scheduled and manual forecast jobs |
| `RATE_LIMIT_SALT` | Salt used to HMAC-hash client IP addresses |
| `ALLOWED_ORIGINS` | Comma-separated frontend origins without trailing slashes |

Frontend variable:

| Variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | Public FastAPI base URL, such as `http://localhost:8000` |

Restart a development server after changing its `.env.local` file.

## Run the project locally

Run each application in its own PowerShell terminal.

### 1. Start PostgreSQL

From the repository root:

```powershell
docker compose up -d --wait postgres
```

The development database listens on port `5432` and stores its data in the `currentprice_postgres` Docker volume.

### 2. Install and migrate the backend

From the repository root:

```powershell
cd backend
uv run --env-file .env.local --with-requirements requirements.txt --python 3.12 python migrate.py
```

The migration is idempotent. It creates tables for observations, forecast runs, forecast points, evaluations, and Q&A rate limits. It does not insert historical fixtures into operational data.

### 3. Start FastAPI

From `backend/`:

```powershell
uv run --env-file .env.local --with-requirements requirements.txt --python 3.12 uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Check the service at `http://127.0.0.1:8000/api/health`. The response should report `ok` for both the model and database.

### 4. Install and start Next.js

Open another PowerShell terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://localhost:3000`. The dashboard should show `Live` or `Awaiting first forecast`. If it shows `Backend API not configured`, confirm that `frontend/.env.local` exists, then restart Next.js.

### 5. Create the first forecast

The dashboard has no live forecast until the daily job completes. Call the authenticated endpoint with the development secret:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/jobs/daily-forecast `
  -Headers @{ Authorization = "Bearer local-dev-secret" }
```

A `pending` response means SMARD has not published every required hour. Database, model, authentication, and application failures return an error instead.

## Verify the project

Run unit, production-build, browser, and integration checks before deployment.

Run backend tests from `backend/`:

```powershell
uv run --with-requirements requirements-dev.txt --python 3.12 python -m pytest
```

Run frontend checks from `frontend/`:

```powershell
npm run lint
npm run build
npx playwright install chromium
npm run test:e2e
```

Run the real Docker-backed integration check from the repository root:

```powershell
.\scripts\local-smoke.ps1
```

The smoke script uses ports `18000` and `13000`. Add `-RunForecast` to include a live SMARD request and forecast attempt:

```powershell
.\scripts\local-smoke.ps1 -RunForecast
```

## API endpoints

Every public JSON response uses `schema_version: "1.0"`.

| Method | Endpoint | Purpose | Authentication |
| --- | --- | --- | --- |
| `GET` | `/api/health` | Model, database, and latest job health | None |
| `GET` | `/api/forecast/current` | Latest completed 24-hour forecast | None |
| `GET` | `/api/evaluation/latest` | Latest evaluation metrics | None |
| `GET` | `/api/evaluation/latest/series` | Predicted and observed hourly series | None |
| `POST` | `/api/rag/ask` | Static, dynamic, or mixed project Q&A | Rate limited |
| `GET` | `/api/jobs/daily-forecast` | Vercel Cron execution | Bearer secret |
| `POST` | `/api/jobs/daily-forecast` | Manual retry | Bearer secret |

UTC is the canonical storage timezone. API rows also include Berlin display time, timezone abbreviation, and UTC offset.

## Deploy to Vercel

Create two Vercel projects from the same repository.

### Deploy the backend

Configure the backend project:

- Root Directory: `backend`
- Framework Preset: FastAPI
- Region: Frankfurt (`fra1`)
- Environment variables: `DATABASE_URL`, `GEMINI_API_KEY`, `CRON_SECRET`, `RATE_LIMIT_SALT`, and `ALLOWED_ORIGINS`

Create a Neon PostgreSQL database and run `backend/migrate.py` against its connection string before the first forecast. The backend cron runs at `0 13 * * *` UTC and keeps a canonical 12:00 UTC forecast origin.

### Deploy the frontend

Configure the frontend project:

- Root Directory: `frontend`
- Framework Preset: Next.js
- Environment variable: `NEXT_PUBLIC_API_BASE_URL=https://your_backend_project.vercel.app`

Add the deployed frontend origin to the backend's `ALLOWED_ORIGINS`, then redeploy the backend configuration. Never expose database, Gemini, cron, or rate-limit secrets through a `NEXT_PUBLIC_` variable.

## Rebuild frozen model assets

Normal development and deployment use the committed ONNX bundle. Rebuild it only when the frozen production artifacts intentionally change.

Create an isolated environment and run the exporter from the repository root:

```powershell
py -3.12 -m venv scripts\.venv
scripts\.venv\Scripts\python.exe -m pip install -r scripts\requirements-convert.txt
scripts\.venv\Scripts\python.exe -m pip install --no-deps tf2onnx==1.16.1
scripts\.venv\Scripts\python.exe scripts\export_model.py
```

The exporter produces the opset 18 ONNX model, verifies Keras parity, refreshes scaler parameters and smoke data, copies RAG assets, and updates SHA-256 hashes.

## Troubleshooting local setup

Use the backend health response and the dashboard notice to identify the failing layer:

| Problem | Check |
| --- | --- |
| `Backend API not configured` | Create `frontend/.env.local`, set `NEXT_PUBLIC_API_BASE_URL`, and restart Next.js |
| `Backend unavailable` | Confirm FastAPI is listening on port `8000` and open `/api/health` |
| `Database unavailable` | Start Docker, run `docker compose up -d --wait postgres`, and apply the migration |
| Browser reports a CORS failure | Add the exact frontend origin to `ALLOWED_ORIGINS` without a trailing slash |
| Dashboard has no forecast | Run the manual job and inspect its `complete`, `pending`, or error response |
| Static Q&A fails | Set `GEMINI_API_KEY`; metric-only questions do not require Gemini |

Stop the local database without deleting its data:

```powershell
docker compose down
```

To erase the local database volume and start from an empty database, run `docker compose down -v`. This deletion cannot be reversed.
