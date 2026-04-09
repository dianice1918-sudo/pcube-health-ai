param(
  [string]$TemplatePath = ".env.example",
  [string]$OutputPath = ".env.production"
)

function New-RandomSecret([int]$bytes = 48) {
  $buffer = New-Object byte[] $bytes
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buffer)
  return [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+','-').Replace('/','_')
}

$root = Split-Path -Parent $PSScriptRoot
$template = Join-Path $root $TemplatePath
$output = Join-Path $root $OutputPath

if (-not (Test-Path $template)) {
  Write-Error "Template not found: $template"
  exit 1
}

$content = Get-Content -Path $template -Raw
$content = $content -replace 'JWT_SECRET=replace-with-strong-random-secret', ('JWT_SECRET=' + (New-RandomSecret 64))
$content = $content -replace 'LOGIN_OTP_SECRET=', ('LOGIN_OTP_SECRET=' + (New-RandomSecret 48))
$content = $content -replace 'APP_ENV=production', 'APP_ENV=production'
$content = $content -replace 'ENABLE_DOCS=false', 'ENABLE_DOCS=false'
$content = $content -replace 'ENABLE_SCHEDULER=false', 'ENABLE_SCHEDULER=false'
$content = $content -replace 'ALLOW_SQLITE_IN_PRODUCTION=', 'ALLOW_SQLITE_IN_PRODUCTION=false'

Set-Content -Path $output -Value $content -NoNewline
Write-Host "Generated $output"
Write-Host "Next steps:"
Write-Host " - Fill DATABASE_URL with your real PostgreSQL connection string"
Write-Host " - Fill your real CORS/host values"
Write-Host " - Add your provider secrets outside git"
Write-Host " - Keep AI values unchanged if you want the same provider after launch"
