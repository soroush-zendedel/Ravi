# Start Ravi AI Infrastructure
Write-Host "Starting Ravi AI Infrastructure..." -ForegroundColor Green
docker compose up -d --build
Write-Host "Ravi is running at http://127.0.0.1:4000" -ForegroundColor Cyan
