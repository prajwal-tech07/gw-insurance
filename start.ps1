# Start ClaimSaathi on Windows, then open http://127.0.0.1:8000
#   powershell -ExecutionPolicy Bypass -File start.ps1

Set-Location "$PSScriptRoot\backend"
if (-not (Test-Path ".venv")) { Write-Host "Run setup.ps1 first." -ForegroundColor Red; exit 1 }
if (-not (Test-Path "$PSScriptRoot\frontend\dist")) { Write-Host "Frontend not built: run setup.ps1 (or 'npm run build' in frontend)." -ForegroundColor Yellow }
Write-Host "ClaimSaathi is running at http://127.0.0.1:8000  (Ctrl+C to stop)" -ForegroundColor Green
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
