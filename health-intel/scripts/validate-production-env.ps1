param(
  [string]$EnvFile = ".env.production"
)

$ErrorActionPreference = "Stop"

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

function Assert-NonPlaceholder {
  param(
    [hashtable]$EnvMap,
    [string]$Name
  )

  $value = ""
  if ($EnvMap.ContainsKey($Name)) {
    $value = [string]$EnvMap[$Name]
  }
  if ([string]::IsNullOrWhiteSpace($value)) {
    throw "$Name is missing"
  }
  if ($value -match "REPLACE_WITH|YOUR_" -or $value -match "replace-with") {
    throw "$Name still contains a placeholder value"
  }
}

function Test-Configured {
  param(
    [hashtable]$EnvMap,
    [string[]]$Names
  )

  foreach ($name in $Names) {
    $value = ""
    if ($EnvMap.ContainsKey($name)) {
      $value = [string]$EnvMap[$name]
    }
    if ([string]::IsNullOrWhiteSpace($value)) {
      return $false
    }
    if ($value -match "REPLACE_WITH|YOUR_" -or $value -match "replace-with") {
      return $false
    }
  }

  return $true
}

$envMap = Load-EnvFile -Path $EnvFile

Assert-NonPlaceholder -EnvMap $envMap -Name "APP_ENV"
if ($envMap["APP_ENV"].ToLowerInvariant() -ne "production") {
  throw "APP_ENV must be production"
}

Assert-NonPlaceholder -EnvMap $envMap -Name "DATABASE_URL"
$databaseUrl = [string]$envMap["DATABASE_URL"]
if ($databaseUrl -match "^sqlite") {
  throw "DATABASE_URL must point to PostgreSQL, not SQLite"
}
if ($databaseUrl -notmatch "^postgres(ql)?(\+psycopg2)?://") {
  throw "DATABASE_URL must be a PostgreSQL connection string"
}

Assert-NonPlaceholder -EnvMap $envMap -Name "JWT_SECRET"
Assert-NonPlaceholder -EnvMap $envMap -Name "ALLOWED_HOSTS"
Assert-NonPlaceholder -EnvMap $envMap -Name "CORS_ALLOW_ORIGINS"

if ($envMap["ALLOWED_HOSTS"] -eq "*") {
  throw "ALLOWED_HOSTS cannot be '*' in production"
}

$enableDocs = ""
if ($envMap.ContainsKey("ENABLE_DOCS")) {
  $enableDocs = [string]$envMap["ENABLE_DOCS"]
}
if ($enableDocs.ToLowerInvariant() -eq "true") {
  throw "ENABLE_DOCS should be false in production"
}

$runStartupSchemaPatches = ""
if ($envMap.ContainsKey("RUN_STARTUP_SCHEMA_PATCHES")) {
  $runStartupSchemaPatches = [string]$envMap["RUN_STARTUP_SCHEMA_PATCHES"]
}
if ($runStartupSchemaPatches.ToLowerInvariant() -eq "true") {
  throw "RUN_STARTUP_SCHEMA_PATCHES should be false for production deploys that use Alembic"
}

$loginOtpEnabled = ""
if ($envMap.ContainsKey("LOGIN_OTP_ENABLED")) {
  $loginOtpEnabled = [string]$envMap["LOGIN_OTP_ENABLED"]
}
if ($loginOtpEnabled.ToLowerInvariant() -eq "true") {
  foreach ($name in @("LOGIN_OTP_SECRET", "SMTP_HOST", "SMTP_USER", "SMTP_PASS")) {
    Assert-NonPlaceholder -EnvMap $envMap -Name $name
  }
}

$llmProvider = ""
if ($envMap.ContainsKey("LLM_PROVIDER")) {
  $llmProvider = [string]$envMap["LLM_PROVIDER"]
}
switch ($llmProvider.ToLowerInvariant()) {
  "openai" {
    Assert-NonPlaceholder -EnvMap $envMap -Name "OPENAI_API_KEY"
  }
  "pinecone" {
    foreach ($name in @("PINECONE_API_KEY", "PINECONE_ASSISTANT_NAME")) {
      Assert-NonPlaceholder -EnvMap $envMap -Name $name
    }
  }
  "xai" {
    Assert-NonPlaceholder -EnvMap $envMap -Name "XAI_API_KEY"
  }
  "ollama" {
  }
  default {
    throw "Unsupported or missing LLM_PROVIDER: $llmProvider"
  }
}

$fcmConfigured = Test-Configured -EnvMap $envMap -Names @("FCM_PROJECT_ID", "FCM_SERVICE_ACCOUNT_FILE")
if ($fcmConfigured) {
  $serviceAccountPath = [string]$envMap["FCM_SERVICE_ACCOUNT_FILE"]
  $localFallbackPath = Join-Path (Get-Location) "service-account.json"
  $serviceAccountExists = (Test-Path $serviceAccountPath) -or (($serviceAccountPath -eq "/run/secrets/service-account.json") -and (Test-Path $localFallbackPath))
  if (-not $serviceAccountExists) {
    throw "FCM service account file was configured but not found: $serviceAccountPath"
  }
}

$wearablesConfigured =
  (Test-Configured -EnvMap $envMap -Names @("GOOGLE_FIT_CLIENT_ID", "GOOGLE_FIT_CLIENT_SECRET", "GOOGLE_FIT_REDIRECT_URI")) -or
  (Test-Configured -EnvMap $envMap -Names @("FITBIT_CLIENT_ID", "FITBIT_CLIENT_SECRET", "FITBIT_REDIRECT_URI"))

Write-Host "Production env validation passed for $EnvFile"
Write-Host "Optional integration readiness:"
Write-Host ("- Firebase push: " + ($(if ($fcmConfigured) { "configured" } else { "not configured" })))
Write-Host ("- Wearables: " + ($(if ($wearablesConfigured) { "configured" } else { "not configured" })))
Write-Host "- Twilio: disabled for email-only production flow"
