param([string]$Project = 'D:\dev_project\2026_tourist_congestion_app')
$ErrorActionPreference = 'Stop'
$projectPath = (Resolve-Path -LiteralPath $Project).Path
$backendPath = Join-Path $projectPath 'tourist_congestion_backend'
$pythonPath = Join-Path $projectPath '.integration-venv\Scripts\pythonw.exe'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
foreach ($job in @(
    @{Name='IlionCrowdCollection'; Action='collect'; Legacy='collect-crowd.ps1'; Minutes=1; Timeout=5},
    @{Name='IlionHourlyValidation'; Action='evaluate'; Legacy='validate-hourly.ps1'; Minutes=60; Timeout=45}
)) {
  $scriptPath = Join-Path $projectPath 'ops\hourly-job.py'
  foreach ($path in @($scriptPath, $pythonPath, (Join-Path $backendPath 'manage.py'))) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required file missing: $path" }
  }
  $arguments = '"{0}" {1}' -f $scriptPath, $job.Action
  $oldScript = Join-Path $projectPath ('ops\' + $job.Legacy)
  $oldPython = Join-Path $projectPath '.integration-venv\Scripts\python.exe'
  $oldArguments = '-NoProfile -NonInteractive -WindowStyle Hidden -File "{0}" -Backend "{1}" -Python "{2}"' -f $oldScript, $backendPath, $oldPython
  $existing = Get-ScheduledTask -TaskName $job.Name -ErrorAction SilentlyContinue
  if ($existing -and ($existing.Actions.Arguments -ne $arguments) -and ($existing.Actions.Arguments -ne $oldArguments)) {
    throw "Existing task differs; refusing to overwrite: $($job.Name)"
  }
  $action = New-ScheduledTaskAction -Execute $pythonPath -Argument $arguments -WorkingDirectory $backendPath
  $trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) -RepetitionInterval (New-TimeSpan -Minutes $job.Minutes)
  $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes $job.Timeout)
  Register-ScheduledTask -TaskName $job.Name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Ilion hourly crowd study; fixed API quotas; no automatic model promotion.' -Force | Select-Object TaskName, State
}
