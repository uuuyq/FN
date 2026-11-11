param([switch]$Background, [switch]$Prepare, [switch]$Build)
$ErrorActionPreference = 'Stop'
if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) {
    try {
        $health = Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 2
        if ($health.status -eq 'ok') { Write-Host 'FitPlan is already running: http://127.0.0.1:8765'; exit 0 }
    } catch {}
    throw 'Port 8765 is occupied by another process; stop it or run deploy/stop-local.ps1 first'
}
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonOutput = & conda run -n fitplan python -c 'import sys; print(sys.executable)'
if ($LASTEXITCODE -ne 0) { throw 'Conda fitplan environment is unavailable' }
$python = ($pythonOutput | Where-Object { $_.Trim() } | Select-Object -Last 1).Trim()
if ($Build) {
    Push-Location (Join-Path $projectRoot 'frontend')
    try {
        & node node_modules/typescript/bin/tsc -b
        if ($LASTEXITCODE -ne 0) { throw 'TypeScript failed' }
        & node node_modules/vite/bin/vite.js build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
    } finally { Pop-Location }
}
Push-Location (Join-Path $projectRoot 'backend')
try {
    if ($Prepare) {
        & $python -m scripts.local prepare
        if ($LASTEXITCODE -ne 0) { throw 'Database preparation failed' }
    }
    & (Join-Path $PSScriptRoot 'register-workout-cleanup.ps1') -Python $python | Out-Null
    Write-Host 'Workout cleanup task registered: daily 03:00'
    if ($Background) {
        $runtime = Join-Path $projectRoot 'runtime'
        New-Item -ItemType Directory -Path $runtime -Force | Out-Null
        $stateFile = Join-Path $runtime 'process.json'
        if (Test-Path -LiteralPath $stateFile) {
            $old = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
            $existing = Get-Process -Id $old.pid -ErrorAction SilentlyContinue
            if ($existing -and $existing.StartTime.ToUniversalTime().Ticks.ToString() -eq $old.started) { throw 'FitPlan is already running' }
        }
        $process = Start-Process -FilePath $python -ArgumentList @('-m','scripts.local','serve') -WorkingDirectory (Get-Location).Path -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'server.log') -RedirectStandardError (Join-Path $runtime 'server-error.log')
        @{pid=$process.Id;started=$process.StartTime.ToUniversalTime().Ticks.ToString();python=$python} | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding utf8
        $ready = $false
        for ($attempt=0; $attempt -lt 40; $attempt++) {
            Start-Sleep -Milliseconds 250
            $process.Refresh()
            if ($process.HasExited) { throw 'Server exited; check runtime/server-error.log' }
            try {
                $health = Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 1
                if ($health.status -eq 'ok') { $ready=$true; break }
            } catch {}
        }
        if (!$ready) { throw 'Server did not become ready; check runtime logs' }
        Write-Host 'FitPlan is running: http://127.0.0.1:8765'
    } else {
        & $python -m scripts.local serve
        if ($LASTEXITCODE -ne 0) { throw 'Server exited with an error' }
    }
} finally { Pop-Location }
