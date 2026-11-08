# SSUET RideShare :: one-shot backend setup for Windows.
#
#   powershell -ExecutionPolicy Bypass -File scripts\setup-backend.ps1
#
# Creates backend\.venv (NOT a .venv at the repository root — uvicorn must be run from
# backend\, otherwise `import app` fails), installs the pinned requirements and runs the
# test suite. Calling the interpreter directly means no Activate.ps1 and no execution policy
# to fight with.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "backend")

$python = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Creating backend\.venv ..." -ForegroundColor Cyan
    python -m venv .venv
} else {
    Write-Host "Reusing backend\.venv" -ForegroundColor Cyan
}

& $python -m pip install --upgrade pip
& $python -m pip install -r requirements.txt

Write-Host "`nRunning the test suite ..." -ForegroundColor Cyan
& $python -m pytest -q
Write-Host "`nBackend ready. Start the API with:" -ForegroundColor Green
Write-Host '  cd backend; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000'
