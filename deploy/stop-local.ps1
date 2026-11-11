$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$stateFile = Join-Path $projectRoot 'runtime/process.json'
if (!(Test-Path -LiteralPath $stateFile)) {
    Write-Host 'No background instance recorded'
} else {
    $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    $process = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
    if ($process) {
        if ($process.StartTime.ToUniversalTime().Ticks.ToString() -ne $state.started -or $process.Path -ne $state.python) {
            throw 'Recorded process identity does not match; refusing to stop it'
        }
        Stop-Process -Id $process.Id
        $process.WaitForExit(10000) | Out-Null
    }
    Remove-Item -LiteralPath $stateFile
    Write-Host 'FitPlan stopped. SQLite WAL is recovered at the next connection.'
}
$taskName = 'FitPlan-WorkoutCleanup'
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
    if ($task.Actions.WorkingDirectory -ne (Join-Path $projectRoot 'backend')) {
        throw 'An unrelated task uses this name; refusing to unregister it'
    }
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host 'Workout cleanup task unregistered'
}
