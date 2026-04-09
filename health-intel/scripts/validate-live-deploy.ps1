param(
  [string]$ApiBase,
  [string]$EnvFile = ".env.production",
  [switch]$IncludeAI
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ApiBase)) {
  throw "Provide -ApiBase, for example https://api.yourdomain.com"
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

& (Join-Path $scriptRoot "validate-production-env.ps1") -EnvFile $EnvFile
& (Join-Path $scriptRoot "smoke-test.ps1") -ApiBase $ApiBase -IncludeAI:$IncludeAI

Write-Host ""
Write-Host "Manual live verification still required for enabled external integrations:"
Write-Host "- OTP/email: request a real login code and confirm delivery/verification"
Write-Host "- Twilio: send one real SMS/WhatsApp alert if those features are enabled"
Write-Host "- Pinecone assistant files: upload one sample file through the app if file chat is enabled"
Write-Host "- Push notifications: register one real device token and trigger a test push"
Write-Host "- Wearables: complete one Google Fit/Fitbit OAuth connect flow if advertised"
