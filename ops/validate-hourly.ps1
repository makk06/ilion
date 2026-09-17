param(
  [string]$Backend = 'D:\dev_project\2026_tourist_congestion_app\tourist_congestion_backend',
  [string]$Python = 'D:\dev_project\2026_tourist_congestion_app\.integration-venv\Scripts\python.exe'
)
$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $Backend
try {
  & $Python manage.py hourly_crowd advance --artifacts '../output/hourly-validation/operational' --output '../output/hourly-validation/status.json'
  exit $LASTEXITCODE
} finally {
  Pop-Location
}
