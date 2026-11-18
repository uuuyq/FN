param([switch]$Background, [switch]$Prepare, [switch]$NoBuild)
$ErrorActionPreference = 'Stop'
try {
    $health = Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 2
    if ($health.status -eq 'ok') { Write-Host 'FNote is already running: http://127.0.0.1:8765'; exit 0 }
} catch {}
if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8765 is occupied by another process; stop it or run deploy/stop-local.ps1 first'
}
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonOutput = & conda run -n fitplan python -c 'import sys; print(sys.executable)'
if ($LASTEXITCODE -ne 0) { throw 'Conda fitplan environment is unavailable' }
$python = ($pythonOutput | Where-Object { $_.Trim() } | Select-Object -Last 1).Trim()
$node = (Get-Command node -ErrorAction SilentlyContinue).Source
if (!$node) {
    foreach ($candidate in @('C:\Program Files\nodejs\node.exe', "$env:LOCALAPPDATA\Programs\nodejs\node.exe", "$env:ProgramFiles\nodejs\node.exe")) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { $node = $candidate; break }
    }
}
if (!$node) { throw 'Node.js not found; install it or add node.exe to PATH' }
if (!$NoBuild -or !(Test-Path -LiteralPath (Join-Path $projectRoot 'frontend/dist/index.html'))) {
    Push-Location (Join-Path $projectRoot 'frontend')
    try {
        & $node node_modules/typescript/bin/tsc --noEmit
        if ($LASTEXITCODE -ne 0) { throw 'TypeScript failed' }
        & $node node_modules/vite/bin/vite.js build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
    } finally { Pop-Location }
}
Push-Location (Join-Path $projectRoot 'backend')
try {
    if (!$Prepare) {
        $checkDatabase = @'
from pathlib import Path
import sqlite3
from alembic.config import Config
from alembic.script import ScriptDirectory
path = Path('data/fitplan.db')
if not path.exists():
    raise SystemExit(10)
with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as db:
    revision = db.execute('SELECT version_num FROM alembic_version').fetchone()[0]
raise SystemExit(0 if revision == ScriptDirectory.from_config(Config('alembic.ini')).get_current_head() else 10)
'@
        & $python -c $checkDatabase
        if ($LASTEXITCODE -eq 10) {
            Write-Host 'Preparing database for the current application version'
            $Prepare = $true
        } elseif ($LASTEXITCODE -ne 0) {
            throw 'Database version check failed'
        }
    }
    if ($Prepare) {
        & $python -m scripts.local prepare
        if ($LASTEXITCODE -ne 0) { throw 'Database preparation failed' }
    }
    try {
        & (Join-Path $PSScriptRoot 'register-workout-cleanup.ps1') -Python $python | Out-Null
        Write-Host 'Workout cleanup task registered: daily 03:00'
    } catch {
        Write-Warning ('Workout cleanup task registration failed: ' + $_.Exception.Message)
    }
    if ($Background) {
        $runtime = Join-Path $projectRoot 'runtime'
        New-Item -ItemType Directory -Path $runtime -Force | Out-Null
        $stateFile = Join-Path $runtime 'process.json'
        if (Test-Path -LiteralPath $stateFile) {
            $old = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
            $existing = Get-Process -Id $old.pid -ErrorAction SilentlyContinue
            if ($existing -and $existing.StartTime.ToUniversalTime().Ticks.ToString() -eq $old.started) { throw 'FNote is already running' }
        }
        $process = Start-Process -FilePath $python -ArgumentList @('-m','scripts.local','serve') -WorkingDirectory (Get-Location).Path -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'server.log') -RedirectStandardError (Join-Path $runtime 'server-error.log')
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
    } else {
        & $python -m scripts.local serve
        if ($LASTEXITCODE -ne 0) { throw 'Server exited with an error' }
    }
} finally { Pop-Location }
