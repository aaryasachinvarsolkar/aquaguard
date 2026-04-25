Set-Location $PSScriptRoot
Write-Host "Starting OceanSense backend on http://localhost:8000 ..." -ForegroundColor Cyan
uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
