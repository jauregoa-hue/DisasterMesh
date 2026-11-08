param([switch]$SkipDatabase)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $projectRoot
if (-not (Test-Path -LiteralPath '.env')) { throw 'Run scripts/setup.ps1 first' }
New-Item -ItemType Directory -Path '.local' -Force | Out-Null
$dialect = & .\.venv\Scripts\python.exe -c "from dotenv import dotenv_values; print(dotenv_values('.env')['DATABASE_URL'].split(':')[0])"
if (-not $SkipDatabase -and $dialect -eq 'postgresql+psycopg') {
    & .\.venv\Scripts\python.exe scripts/local_postgres.py start --download
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL startup failed. See .local/postgres/server.log' }
}
foreach ($port in @(8000,5173)) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        throw "Port $port is already in use. Stop the existing app before running start.ps1."
    }
}
$backend = Start-Process -FilePath "$projectRoot\.venv\Scripts\python.exe" -ArgumentList @('-m','uvicorn','main:app','--env-file','.env','--host','127.0.0.1','--port','8000') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput '.local/backend.stdout.log' -RedirectStandardError '.local/backend.stderr.log'
$vitePath = Join-Path $projectRoot 'node_modules\vite\bin\vite.js'
$frontend = Start-Process -FilePath (Get-Command node.exe).Source -ArgumentList @('"' + $vitePath + '"') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput '.local/frontend.stdout.log' -RedirectStandardError '.local/frontend.stderr.log'
@{backend=$backend.Id; frontend=$frontend.Id} | ConvertTo-Json | Set-Content -LiteralPath '.local/runtime.json'
$ready = $false
for ($attempt=0; $attempt -lt 30; $attempt++) {
    try {
        $health = Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 1
        $ui = Invoke-WebRequest 'http://127.0.0.1:5173' -UseBasicParsing -TimeoutSec 1
        if ($health.status -eq 'ok' -and $ui.StatusCode -eq 200) { $ready = $true; break }
    } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $ready) { throw 'Startup failed. Inspect .local/backend.stderr.log and .local/frontend.stderr.log; run scripts/stop.ps1 before retrying.' }
Write-Host "Dashboard: http://localhost:5173   API: http://localhost:8000/docs   Database: $($health.database)"
Write-Host 'Logs: .local/*.log. Run the USB receiver in a separate terminal after connecting COM9.'
