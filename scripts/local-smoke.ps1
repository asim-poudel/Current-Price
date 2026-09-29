param(
    [switch]$RunForecast,
    [int]$BackendPort = 18000,
    [int]$FrontendPort = 13000,
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendRoot = Join-Path $projectRoot "backend"
$frontendRoot = Join-Path $projectRoot "frontend"
$python = $PythonPath
if (-not $python) { $python = Join-Path $backendRoot ".venv\Scripts\python.exe" }
if (-not (Test-Path -LiteralPath $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}
$npm = (Get-Command npm.cmd -ErrorAction Stop).Source
$backendBase = "http://127.0.0.1:$BackendPort"
$frontendBase = "http://127.0.0.1:$FrontendPort"

docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker Desktop is installed but its engine is not running." }
docker compose -f (Join-Path $projectRoot "compose.yaml") up -d --wait postgres
if ($LASTEXITCODE -ne 0) { throw "Local Postgres did not start." }

$env:DATABASE_URL = "postgresql://currentprice:currentprice_dev@localhost:5432/currentprice"
$env:CRON_SECRET = "local-dev-secret"
$env:RATE_LIMIT_SALT = "local-dev-salt-change-before-production"
$env:ALLOWED_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000,$frontendBase"
$env:NEXT_PUBLIC_API_BASE_URL = $backendBase
$env:NEXT_DIST_DIR = ".next-smoke"

& $python (Join-Path $backendRoot "migrate.py")
if ($LASTEXITCODE -ne 0) { throw "Database migration failed." }

$backendProcess = $null
$frontendProcess = $null
try {
    $backendProcess = Start-Process -WindowStyle Hidden -PassThru -FilePath $python -WorkingDirectory $backendRoot -ArgumentList "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "$BackendPort"
    $frontendProcess = Start-Process -WindowStyle Hidden -PassThru -FilePath $npm -WorkingDirectory $frontendRoot -ArgumentList "run", "dev", "--", "--hostname", "127.0.0.1", "--port", "$FrontendPort"

    $health = $null
    $deadline = (Get-Date).AddSeconds(45)
    do {
        try { $health = Invoke-RestMethod "$backendBase/api/health"; break } catch { Start-Sleep -Milliseconds 500 }
    } while ((Get-Date) -lt $deadline)
    if (-not $health) { throw "Backend did not become ready within 45 seconds." }
    if ($health.status -ne "ok" -or $health.checks.model -ne "ok" -or $health.checks.database -ne "ok") {
        throw "Backend health check is not fully operational: $($health | ConvertTo-Json -Compress)"
    }

    $preflight = Invoke-WebRequest -Method Options "$backendBase/api/forecast/current" -Headers @{ Origin = $frontendBase; "Access-Control-Request-Method" = "GET" }
    if ($preflight.Headers["Access-Control-Allow-Origin"] -ne $frontendBase) { throw "CORS preflight failed." }

    if ($RunForecast) {
        $job = Invoke-RestMethod -Method Post "$backendBase/api/jobs/daily-forecast" -Headers @{ Authorization = "Bearer local-dev-secret" }
        if ($job.status -notin @("complete", "pending")) { throw "Unexpected forecast status: $($job.status)" }
    }

    $answer = Invoke-RestMethod -Method Post "$backendBase/api/rag/ask" -ContentType "application/json" -Body '{"question":"What was yesterday''s MAE?"}'
    if ($answer.schema_version -ne "1.0" -or $answer.route -ne "dynamic") { throw "Backend Q&A contract failed." }

    $page = $null
    $deadline = (Get-Date).AddSeconds(45)
    do {
        try { $page = Invoke-WebRequest $frontendBase; break } catch { Start-Sleep -Milliseconds 500 }
    } while ((Get-Date) -lt $deadline)
    if (-not $page -or $page.Content -notmatch "Current Price") { throw "Frontend did not render Current Price." }
    if ($page.Content -notmatch "Live|Awaiting first forecast") { throw "Frontend did not render the backend connection state." }

    Write-Host "Local integration passed: Postgres, FastAPI, CORS, Q&A, and Next.js are communicating."
} finally {
    if ($frontendProcess -and -not $frontendProcess.HasExited) { taskkill.exe /PID $frontendProcess.Id /T /F *> $null }
    if ($backendProcess -and -not $backendProcess.HasExited) { Stop-Process -Id $backendProcess.Id -Force }
}
