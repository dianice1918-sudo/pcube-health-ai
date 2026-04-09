param(
  [string]$TaskName = "PCUBE-Local-5500"
)

schtasks /Delete /F /TN $TaskName | Out-Null
Write-Host "Removed autostart task: $TaskName"
