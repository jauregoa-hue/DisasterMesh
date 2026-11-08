param([switch]$KeepDatabase)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $projectRoot
function Stop-ProjectProcess([int]$processId) {
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
    if ($processInfo -and $processInfo.CommandLine -and $processInfo.CommandLine.Contains($projectRoot)) {
        foreach ($child in (Get-CimInstance Win32_Process -Filter "ParentProcessId=$processId" -ErrorAction SilentlyContinue)) {
            Stop-ProjectProcess $child.ProcessId
        }
        Stop-Process -Id $processId -ErrorAction SilentlyContinue
    }
}
if (Test-Path -LiteralPath '.local/runtime.json') {
    $runtime = Get-Content -LiteralPath '.local/runtime.json' -Raw | ConvertFrom-Json
    foreach ($processId in @($runtime.backend, $runtime.frontend)) {
        Stop-ProjectProcess $processId
    }
    Remove-Item -LiteralPath '.local/runtime.json'
}
if (-not $KeepDatabase -and (Test-Path -LiteralPath '.local/postgres/data/PG_VERSION')) {
    & .\.venv\Scripts\python.exe scripts/local_postgres.py stop
}
Write-Host 'Stopped local services. Database and queued SOS data are preserved.'
