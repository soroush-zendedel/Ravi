# Stop Ravi AI Infrastructure (PowerShell helper)
# Prefer using the cross-platform CLI:  ravi stop

Write-Host "Stopping Ravi AI Infrastructure..." -ForegroundColor Yellow

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

docker compose down
if ($LASTEXITCODE -eq 0) {
    Write-Host "Ravi stopped successfully." -ForegroundColor Green
} else {
    Write-Host "Failed to stop." -ForegroundColor Red
    exit $LASTEXITCODE
}
