param(
  [string]$ApiBase = "http://127.0.0.1:8000",
  [switch]$IncludeAI,
  [switch]$SkipProtectedRoutes
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

function Invoke-JsonRequestAllowFailure {
  param(
    [string]$Method,
    [string]$Url,
    [hashtable]$Headers,
    [object]$Body
  )

  try {
    $payload = Invoke-JsonRequest -Method $Method -Url $Url -Headers $Headers -Body $Body
    return @{
      Ok          = $true
      StatusCode  = 200
      Body        = $payload
      ErrorDetail = $null
    }
  }
  catch {
    $statusCode = 0
    $detail = $_.Exception.Message
    $response = $_.Exception.Response
    if ($null -ne $response) {
      try {
        $statusCode = [int]$response.StatusCode
      }
      catch {
        $statusCode = 0
      }
      try {
        $stream = $response.GetResponseStream()
        if ($null -ne $stream) {
          $reader = New-Object System.IO.StreamReader($stream)
          $rawBody = $reader.ReadToEnd()
          if (-not [string]::IsNullOrWhiteSpace($rawBody)) {
            $detail = $rawBody
          }
        }
      }
      catch {
      }
    }

    return @{
      Ok          = $false
      StatusCode  = $statusCode
      Body        = $null
      ErrorDetail = $detail
    }
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

Write-Host "Checking frontend routes..."
foreach ($path in @("/app/", "/app/login", "/app/checker", "/assets/style.css")) {
  $response = Invoke-WebRequest -Method GET -Uri "$ApiBase$path" -TimeoutSec 15 -UseBasicParsing
  if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 400) {
    throw "frontend route check failed for $path with status $($response.StatusCode)"
  }
}
Write-Host "frontend routes ok"

Write-Host "Registering test user $email ..."
$register = Invoke-JsonRequest -Method POST -Url "$ApiBase/register" -Headers @{} -Body @{
  email     = $email
  full_name = $fullName
  password  = $password
}

$token = [string]$register.access_token
if (-not [string]::IsNullOrWhiteSpace([string]$register.access_token)) {
  Write-Host "auth ok"
}
elseif ($register.otp_required -eq $true) {
  Write-Host "OTP is enabled for this deployment; requesting a login verification code..."
  $otpRequest = Invoke-JsonRequest -Method POST -Url "$ApiBase/login/request-code" -Headers @{} -Body @{
    email    = $email
    password = $password
  }
  Assert-HasValue -Name "otp.challenge_id" -Value $otpRequest.challenge_id
  Write-Host "OTP request ok"
  if ($SkipProtectedRoutes) {
    Write-Host "Protected-route checks skipped because OTP verification requires a real delivered code."
    Write-Host "Smoke test passed for $ApiBase (manual OTP verification still required)"
    return
  }
  throw "OTP is enabled, so protected-route checks require manual verification. Re-run with -SkipProtectedRoutes to keep this as a pre-auth smoke test."
}
else {
  Write-Host "No access token on register; trying login..."
  $login = Invoke-JsonRequestAllowFailure -Method POST -Url "$ApiBase/login" -Headers @{} -Body @{
    email    = $email
    password = $password
  }
  if ($login.Ok) {
    $token = [string]$login.Body.access_token
  }
  elseif ($login.StatusCode -eq 403 -and [string]$login.ErrorDetail -match "OTP verification required") {
    Write-Host "Password login correctly requires OTP on this deployment."
    $otpRequest = Invoke-JsonRequest -Method POST -Url "$ApiBase/login/request-code" -Headers @{} -Body @{
      email    = $email
      password = $password
    }
    Assert-HasValue -Name "otp.challenge_id" -Value $otpRequest.challenge_id
    Write-Host "OTP request ok"
    if ($SkipProtectedRoutes) {
      Write-Host "Protected-route checks skipped because OTP verification requires a real delivered code."
      Write-Host "Smoke test passed for $ApiBase (manual OTP verification still required)"
      return
    }
    throw "OTP is enabled, so protected-route checks require manual verification. Re-run with -SkipProtectedRoutes to keep this as a pre-auth smoke test."
  }
  else {
    throw "Login failed during smoke test: $($login.ErrorDetail)"
  }
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
