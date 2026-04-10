param(
  [string]$ApiBase,
  [string]$EnvFile = ".env.production",
  [switch]$IncludeAI,
  [switch]$SkipProtectedRoutes
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ApiBase)) {
  throw "Provide -ApiBase, for example https://api.yourdomain.com"
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Load-EnvFile {
  param([string]$Path)

  if (-not (Test-Path $Path)) {
    throw "Env file not found: $Path"
  }

  $values = @{}
  foreach ($rawLine in Get-Content -Path $Path) {
    $line = $rawLine.Trim()
    if (-not $line -or $line.StartsWith("#")) {
      continue
    }

    $pair = $line -split "=", 2
    if ($pair.Count -ne 2) {
      continue
    }

    $values[$pair[0].Trim()] = $pair[1]
  }

  return $values
}

& (Join-Path $scriptRoot "validate-production-env.ps1") -EnvFile $EnvFile
$envMap = Load-EnvFile -Path $EnvFile
$otpEnabled = [string]$envMap["LOGIN_OTP_ENABLED"]
$effectiveSkipProtectedRoutes = $SkipProtectedRoutes
if (-not $effectiveSkipProtectedRoutes -and $otpEnabled.ToLowerInvariant() -eq "true") {
  $effectiveSkipProtectedRoutes = $true
}

& (Join-Path $scriptRoot "smoke-test.ps1") -ApiBase $ApiBase -IncludeAI:$IncludeAI -SkipProtectedRoutes:$effectiveSkipProtectedRoutes

Write-Host ""
Write-Host "Manual live verification still required for enabled external integrations:"
Write-Host "- OTP/email: request a real login code and confirm delivery/verification"
Write-Host "- Twilio: send one real SMS/WhatsApp alert if those features are enabled"
Write-Host "- Pinecone assistant files: upload one sample file through the app if file chat is enabled"
Write-Host "- Push notifications: register one real device token and trigger a test push"
Write-Host "- Wearables: complete one Google Fit/Fitbit OAuth connect flow if advertised"
