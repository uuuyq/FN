param(
    [string]$Python,
    [string]$At = '03:00'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (!$Python) {
    $pythonOutput = & conda run -n fitplan python -c 'import sys; print(sys.executable)'
    if ($LASTEXITCODE -ne 0) { throw 'Conda fitplan environment is unavailable' }
    $Python = ($pythonOutput | Where-Object { $_.Trim() } | Select-Object -Last 1).Trim()
}
$Python = (Resolve-Path -LiteralPath $Python).Path
$taskName = 'FitPlan-WorkoutCleanup'
$backend = Join-Path $projectRoot 'backend'
$action = New-ScheduledTaskAction -Execute $Python -Argument '-m scripts.cleanup_workouts' -WorkingDirectory $backend
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing -and ($existing.Actions.WorkingDirectory -ne $backend)) {
    throw 'An unrelated task uses this name; refusing to overwrite it'
}
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Purge FitPlan workouts closed for at least seven days. Logs: runtime/workout-cleanup.log' -Force | Out-Null
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
Get-ScheduledTaskInfo -TaskName $taskName | Select-Object NextRunTime, LastTaskResult
