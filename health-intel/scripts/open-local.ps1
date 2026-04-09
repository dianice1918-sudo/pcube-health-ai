param(
  [string]$Url = "",
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

function Test-PortOpen([string]$TargetHost, [int]$TargetPort) {
  try {
    return Test-NetConnection -ComputerName $TargetHost -Port $TargetPort -InformationLevel Quiet
  } catch {
    return $false
  }
}

function Test-Health([string]$TargetHost, [int]$TargetPort) {
  $healthUrl = "http://$TargetHost`:$TargetPort/healthz"
  try {
    $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2
    return $resp.StatusCode -eq 200
  } catch {
    return $false
  }
}

$candidatePorts = @($Port, 8001, 8002, 5500, 5501, 5502) | Select-Object -Unique
$selectedPort = $null
$healthOk = $false

foreach ($candidate in $candidatePorts) {
  $portOpen = Test-PortOpen -TargetHost $BindHost -TargetPort $candidate
  $candidateHealthOk = $false
  if ($portOpen) {
    $candidateHealthOk = Test-Health -TargetHost $BindHost -TargetPort $candidate
    if ($candidateHealthOk) {
      $selectedPort = $candidate
      $healthOk = $true
      break
    }
    Write-Host "Port $candidate is busy with another app. Trying the next port..."
    continue
  }
  $selectedPort = $candidate
  break
}

if (-not $selectedPort) {
  Write-Error "No free local app port was found. Stop Live Server (or anything else) on ports 5500-5502/8000-8002, then retry."
  exit 1
}

if (-not $healthOk) {
  Write-Host "API not running on $BindHost`:$selectedPort. Starting..."
  $env:APP_ENV = "development"
  $env:ENABLE_DOCS = "true"
  $env:API_PORT = "$selectedPort"
  $env:UVICORN_PORT = "$selectedPort"
  $logDir = Join-Path $root "tmp"
  if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
  }
  $stdoutLog = Join-Path $logDir "open-local-$selectedPort.out.log"
  $stderrLog = Join-Path $logDir "open-local-$selectedPort.err.log"
  $apiProcess = Start-Process -FilePath $python -ArgumentList @(
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    $BindHost,
    "--port",
    "$selectedPort"
  ) -WorkingDirectory $root -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -PassThru

  $healthOk = $false
  for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 700
    if ($apiProcess.HasExited) {
      break
    }
    if (Test-Health -TargetHost $BindHost -TargetPort $selectedPort) {
      $healthOk = $true
      break
    }
  }
  if (-not $healthOk) {
    Write-Error "API failed to start on http://$BindHost`:$selectedPort. Check $stderrLog and $stdoutLog, or run scripts\\run-local-5500.ps1 -Port $selectedPort in a terminal to see the startup error."
    exit 1
  }
}

if (-not $Url) {
  $Url = "http://$BindHost`:$selectedPort/app/login"
}

Write-Host "Opening $Url"
Start-Process $Url | Out-Null
