param(
  [string]$TaskName = "PCUBE-Local-5500"
)

$script = Join-Path $PSScriptRoot "run-local-5500.ps1"
if (-not (Test-Path $script)) {
  Write-Error "run-local-5500.ps1 not found in scripts folder."
  exit 1
}

$command = "powershell -ExecutionPolicy Bypass -File `"$script`""

schtasks /Create /F /SC ONLOGON /RL LIMITED /TN $TaskName /TR $command | Out-Null
Write-Host "Installed autostart task: $TaskName"
