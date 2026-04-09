param(
  [string]$BindHost = "127.0.0.1",
  [int]$Port = 8000
)

$root = Split-Path -Parent $PSScriptRoot
$venvCandidates = @(
  (Join-Path $root "venv\\Scripts\\python.exe"),
  (Join-Path $root ".venv\\Scripts\\python.exe")
)
$python = $venvCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) {
  Write-Error "Python venv not found. Create venv in `venv` or `.venv` first."
  exit 1
}

$env:APP_ENV = "development"
$env:ENABLE_DOCS = "true"
$env:API_PORT = "$Port"
$env:UVICORN_PORT = "$Port"

Write-Host "Starting FastAPI on http://$BindHost`:$Port (single-server mode)..."
Push-Location $root
try {
  & $python -m uvicorn app.main:app --host $BindHost --port $Port
} finally {
  Pop-Location
}
