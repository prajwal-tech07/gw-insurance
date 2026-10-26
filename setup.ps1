# One-time setup on Windows. Run from the claimsaathi folder:
#   powershell -ExecutionPolicy Bypass -File setup.ps1

function Check($step) {
    if ($LASTEXITCODE -ne 0) { Write-Host "Setup failed at: $step" -ForegroundColor Red; exit 1 }
}

Set-Location "$PSScriptRoot\backend"
if (-not (Test-Path ".venv")) { python -m venv .venv; Check "creating the Python environment" }
.\.venv\Scripts\python.exe -m pip install --upgrade pip; Check "upgrading pip"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt; Check "installing Python packages"
.\.venv\Scripts\python.exe -m pytest -q; Check "backend tests"

Set-Location "$PSScriptRoot\frontend"
npm install; Check "installing frontend packages"
npm run build; Check "building the frontend"

Set-Location $PSScriptRoot
Write-Host "Setup done. Start the app with:  powershell -ExecutionPolicy Bypass -File start.ps1" -ForegroundColor Green
