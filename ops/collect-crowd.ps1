param(
  [string]$Backend = 'D:\dev_project\2026_tourist_congestion_app\tourist_congestion_backend',
  [string]$Python = 'D:\dev_project\2026_tourist_congestion_app\.integration-venv\Scripts\python.exe'
)
$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $Backend
try {
  & $Python manage.py collect_crowd_inputs --once --max-seconds 45
  exit $LASTEXITCODE
} finally {
  Pop-Location
}
