# Start Istithmar from the project root (same folder as this script).
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".\venv\Scripts\Activate.ps1")) {
    Write-Error "venv not found. Create it in istithmar_app: python -m venv venv"
}
.\venv\Scripts\Activate.ps1

$env:FLASK_APP = "app.py"
$env:FLASK_DEBUG = "1"

Write-Host "Working directory: $(Get-Location)"
Write-Host "Starting Flask — open http://127.0.0.1:5000/"
flask run
