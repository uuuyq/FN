# Usage: powershell -ExecutionPolicy Bypass -File deploy/local.ps1 [--stop]
$ErrorActionPreference = 'Stop'
if ($args.Count -gt 1 -or ($args.Count -eq 1 -and $args[0] -notin @('--stop', '-Stop'))) {
    throw 'Usage: local.ps1 [--stop]'
}
$projectRoot = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $projectRoot 'backend'
function Remove-Maintenance {
    foreach ($name in @('FNote-WorkoutCleanup', 'FNote-DatabaseBackup')) {
        $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        if ($task) {
            if ($task.Actions.WorkingDirectory -ne $backend) { throw "Unrelated task: $name" }
            Stop-ScheduledTask -TaskName $name -ErrorAction Stop
            Unregister-ScheduledTask -TaskName $name -Confirm:$false
        }
    }
}
function Register-Maintenance {
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    # UTC+08 offset makes the schedule independent of the Windows display timezone.
    foreach ($spec in @(@('FNote-WorkoutCleanup', '-m scripts.cleanup_workouts', '03:00:00'), @('FNote-DatabaseBackup', '-m scripts.local backup', '03:30:00'))) {
        $existing = Get-ScheduledTask -TaskName $spec[0] -ErrorAction SilentlyContinue
        if ($existing -and $existing.Actions.WorkingDirectory -ne $backend) { throw 'Unrelated scheduled task; refusing to overwrite' }
        $action = New-ScheduledTaskAction -Execute $python -Argument $spec[1] -WorkingDirectory $backend
        $trigger = New-ScheduledTaskTrigger -Daily -At '03:00'
        $trigger.StartBoundary = '2026-01-01T' + $spec[2] + '+08:00'
        Register-ScheduledTask -TaskName $spec[0] -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
    }
    Write-Host 'Maintenance registered: cleanup 03:00, backup 03:30 Asia/Shanghai (30 days).'
}
if ($args.Count -eq 1) {
    Remove-Maintenance
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
        Write-Host 'FNote stopped. SQLite WAL is recovered at the next connection.'
    }
    return
}
$pythonCommand = Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1
$pythonOutput = & $pythonCommand.Source -c 'import sys; print(sys.executable)'
if ($LASTEXITCODE -ne 0) { throw 'Python in the current environment is unavailable' }
$python = ($pythonOutput | Where-Object { $_.Trim() } | Select-Object -Last 1).Trim()
& $python -c 'import sqlite3; assert sqlite3.sqlite_version_info >= (3,51,3), sqlite3.sqlite_version'
if ($LASTEXITCODE -ne 0) { throw 'SQLite >= 3.51.3 required' }
$health = $null
try {
    $health = Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 2
} catch {}
if ($health.status -eq 'ok') {
    if (!(Test-Path (Join-Path $projectRoot 'runtime/process.json'))) { throw 'Unmanaged application on port 8765' }
    Register-Maintenance
    Write-Host 'FNote is already running: http://127.0.0.1:8765'
    return
}
if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8765 is occupied by another process; stop it or run deploy/local.ps1 --stop first'
}
$projectRoot = Split-Path -Parent $PSScriptRoot
$node = (Get-Command node -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source
if (!$node) {
    foreach ($candidate in @('C:\Program Files\nodejs\node.exe', "$env:LOCALAPPDATA\Programs\nodejs\node.exe", "$env:ProgramFiles\nodejs\node.exe")) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { $node = $candidate; break }
    }
}
if (!$node) { throw 'Node.js not found; install it or add node.exe to PATH' }
& {
    Push-Location (Join-Path $projectRoot 'frontend')
    try {
        $pnpm = (Get-Command pnpm -CommandType Application,ExternalScript -ErrorAction Stop | Select-Object -First 1).Source
        & $pnpm install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
        & $node node_modules/typescript/bin/tsc --noEmit
        if ($LASTEXITCODE -ne 0) { throw 'TypeScript failed' }
        & $node node_modules/vite/bin/vite.js build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
    } finally { Pop-Location }
}
Push-Location (Join-Path $projectRoot 'backend')
try {
    & $python -m pip install -r (Join-Path $projectRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed' }
    & $python -m scripts.local prepare
    if ($LASTEXITCODE -ne 0) { throw 'Database preparation failed' }
    $env:APP_ORIGIN = 'http://127.0.0.1:8765'
    $env:COOKIE_SECURE = 'false'
    $launched = $false
    try {
        Register-Maintenance
        $runtime = Join-Path $projectRoot 'runtime'
        New-Item -ItemType Directory -Path $runtime -Force | Out-Null
        $stateFile = Join-Path $runtime 'process.json'
        if (Test-Path -LiteralPath $stateFile) {
            $old = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
            $existing = Get-Process -Id $old.pid -ErrorAction SilentlyContinue
            if ($existing -and $existing.StartTime.ToUniversalTime().Ticks.ToString() -eq $old.started) { throw 'FNote is already running' }
        }
        $process = Start-Process -FilePath $python -ArgumentList @('-m','scripts.local','serve') -WorkingDirectory (Get-Location).Path -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'server.log') -RedirectStandardError (Join-Path $runtime 'server-error.log')
        $launched = $true
        @{pid=$process.Id;started=$process.StartTime.ToUniversalTime().Ticks.ToString();python=$python} | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding utf8
        $ready = $false
        for ($attempt=0; $attempt -lt 40; $attempt++) {
            Start-Sleep -Milliseconds 250
            $process.Refresh()
            if ($process.HasExited) {
                Remove-Item -LiteralPath $stateFile -ErrorAction SilentlyContinue
                Get-Content -LiteralPath (Join-Path $runtime 'server-error.log') -Tail 30
                throw 'Server exited; check runtime/server-error.log'
            }
            try {
                $health = Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 1
                if ($health.status -eq 'ok') { $ready=$true; break }
            } catch {}
        }
        if (!$ready) { throw 'Server did not become ready; check runtime logs' }
        Write-Host 'FNote is running: http://127.0.0.1:8765'
    } catch {
        if ($launched) {
            $process.Refresh()
            if (!$process.HasExited) { Stop-Process -Id $process.Id }
            Remove-Item -LiteralPath $stateFile -ErrorAction SilentlyContinue
        }
        Remove-Maintenance
        throw
    }
} finally { Pop-Location }
