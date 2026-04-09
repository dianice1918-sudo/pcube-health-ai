param(
  [string]$ApiBase = "http://127.0.0.1:8000",
  [switch]$IncludeAI
)

$ErrorActionPreference = "Stop"

function Invoke-JsonRequest {
  param(
    [string]$Method,
    [string]$Url,
    [hashtable]$Headers,
    [object]$Body
  )

  $params = @{
    Method      = $Method
    Uri         = $Url
    ContentType = "application/json"
    Headers     = $Headers
    TimeoutSec  = 20
  }
  if ($null -ne $Body) {
    $params.Body = ($Body | ConvertTo-Json -Depth 8 -Compress)
  }
  return Invoke-RestMethod @params
}

function Assert-HasValue {
  param([string]$Name, $Value)
  if ($null -eq $Value -or [string]::IsNullOrWhiteSpace([string]$Value)) {
    throw "$Name was empty"
  }
}

$stamp = Get-Date -Format "yyyyMMddHHmmss"
$email = "smoke.$stamp@example.com"
$password = "SmokeTest123"
$fullName = "Smoke Test $stamp"

Write-Host "Checking health..."
$health = Invoke-RestMethod -Method GET -Uri "$ApiBase/healthz" -TimeoutSec 10
Assert-HasValue -Name "health.status" -Value $health.status
Write-Host "healthz ok"

Write-Host "Checking readiness..."
$ready = Invoke-RestMethod -Method GET -Uri "$ApiBase/readyz" -TimeoutSec 10
Assert-HasValue -Name "ready.status" -Value $ready.status
Write-Host "readyz ok"

Write-Host "Registering test user $email ..."
$register = Invoke-JsonRequest -Method POST -Url "$ApiBase/register" -Headers @{} -Body @{
  email     = $email
  full_name = $fullName
  password  = $password
}

$token = [string]$register.access_token
if ([string]::IsNullOrWhiteSpace($token)) {
  Write-Host "No access token on register; trying login..."
  $login = Invoke-JsonRequest -Method POST -Url "$ApiBase/login" -Headers @{} -Body @{
    email    = $email
    password = $password
  }
  $token = [string]$login.access_token
}
Assert-HasValue -Name "auth token" -Value $token
Write-Host "auth ok"

$authHeaders = @{ Authorization = "Bearer $token" }

Write-Host "Checking location route..."
$location = Invoke-RestMethod -Method GET -Uri "$ApiBase/users/me/location" -Headers $authHeaders -TimeoutSec 15
if ($null -eq $location) { throw "location response was empty" }
Write-Host "location ok"

Write-Host "Checking dashboard route..."
$dashboard = Invoke-RestMethod -Method GET -Uri "$ApiBase/users/me/dashboard" -Headers $authHeaders -TimeoutSec 15
if ($null -eq $dashboard) { throw "dashboard response was empty" }
Write-Host "dashboard ok"

if ($IncludeAI) {
  Write-Host "Checking chat route..."
  $chat = Invoke-JsonRequest -Method POST -Url "$ApiBase/chat" -Headers $authHeaders -Body @{
    message = "Reply with the single word OK."
  }
  if ($null -eq $chat) { throw "chat response was empty" }
  Write-Host "chat ok"
}

Write-Host "Smoke test passed for $ApiBase"
