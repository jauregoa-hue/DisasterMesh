param([switch]$SQLiteDemo)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment' }
}
& .\.venv\Scripts\python.exe -m pip install -r requirements-gateway.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
npm.cmd ci
if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
if ($SQLiteDemo) { & .\.venv\Scripts\python.exe scripts/configure_env.py --sqlite-demo }
else { & .\.venv\Scripts\python.exe scripts/configure_env.py }
if ($LASTEXITCODE -ne 0) { throw 'Environment setup failed' }
