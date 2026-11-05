# Start Ravi AI Infrastructure (PowerShell helper)
# Prefer using the cross-platform CLI:  ravi start

Write-Host "Starting Ravi AI Infrastructure..." -ForegroundColor Green

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".env")) {
    Write-Host ".env not found. Copy .env.example to .env and configure it first." -ForegroundColor Yellow
    exit 1
}

docker compose up -d --build
if ($LASTEXITCODE -eq 0) {
    Write-Host "Ravi is running at http://127.0.0.1:4000" -ForegroundColor Cyan
    Write-Host "Tip: install the CLI with  pip install -e .   then use  ravi --help" -ForegroundColor DarkGray
} else {
    Write-Host "Failed to start. Check Docker and .env." -ForegroundColor Red
    exit $LASTEXITCODE
}
