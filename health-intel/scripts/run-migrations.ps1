param(
  [string]$EnvFile = ".env.production"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $EnvFile)) {
  throw "Env file not found: $EnvFile"
}

Get-Content -Path $EnvFile | ForEach-Object {
  $line = $_.Trim()
  if ($line -and -not $line.StartsWith("#")) {
    $pair = $line -split "=", 2
    if ($pair.Count -eq 2) {
      $name = $pair[0].Trim()
      $value = $pair[1]
      [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
  }
}

python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) {
  throw "Alembic migration run failed. Install the updated requirements or use docker compose production so migrations run inside the container."
}
