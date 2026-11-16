param(
    [string]$Hostname = 'uuuf.online',
    [switch]$Stop
)
$ErrorActionPreference = 'Stop'

$Hostname = $Hostname.Trim()
if ($Hostname -match '^https?://') { $Hostname = $Hostname -replace '^https?://', '' }
$Hostname = $Hostname.TrimEnd('/')
if ($Hostname -notmatch '^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$') {
    throw 'Pass a hostname such as uuuf.online, without a path.'
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $projectRoot 'runtime'
$localUrl = 'http://127.0.0.1:8765'
$healthUrl = "$localUrl/api/health"
$localStateFile = Join-Path $runtime 'process.json'
$urlFile = Join-Path $runtime 'public-url.txt'
$quickTunnelStateFile = Join-Path $runtime 'quick-tunnel.json'
$publicUrl = "https://$Hostname"
$localScript = Join-Path $PSScriptRoot 'start-local.ps1'
$stopLocalScript = Join-Path $PSScriptRoot 'stop-local.ps1'
$previousAppOrigin = [Environment]::GetEnvironmentVariable('APP_ORIGIN', 'Process')
$previousCookieSecure = [Environment]::GetEnvironmentVariable('COOKIE_SECURE', 'Process')
$startedTunnelService = $false

New-Item -ItemType Directory -Path $runtime -Force | Out-Null

if ($Stop) {
    if (Test-Path -LiteralPath $quickTunnelStateFile) {
        $quickState = Get-Content -LiteralPath $quickTunnelStateFile -Raw | ConvertFrom-Json
        $quickProcess = Get-Process -Id $quickState.pid -ErrorAction SilentlyContinue
        if ($quickProcess) {
            if ($quickProcess.StartTime.ToUniversalTime().Ticks.ToString() -ne $quickState.started -or
                $quickProcess.Path -ne $quickState.executable) {
                throw 'Recorded Quick Tunnel process identity does not match; refusing to stop it.'
            }
            Stop-Process -Id $quickProcess.Id
            $quickProcess.WaitForExit(10000) | Out-Null
        }
        Remove-Item -LiteralPath $quickTunnelStateFile -Force
    }

    $localAlreadyRunning = $false
    try {
        $health = Invoke-RestMethod $healthUrl -TimeoutSec 2
        $localAlreadyRunning = $health.status -eq 'ok'
    } catch {}

    try {
        if ($localAlreadyRunning) {
            if (Test-Path -LiteralPath $localStateFile) {
                & $stopLocalScript
            } else {
                Write-Warning 'FitPlan is running without a managed process record; stop it manually.'
            }
        } else {
            Write-Host 'FitPlan is not running.'
        }
    } finally {
        $tunnelService = Get-Service -Name 'cloudflared' -ErrorAction SilentlyContinue
        if ($tunnelService -and $tunnelService.Status -ne 'Stopped') {
            try { Stop-Service -Name 'cloudflared' }
            catch { throw 'Could not stop cloudflared. Run this script from an Administrator PowerShell.' }
            Write-Host 'Cloudflare Tunnel service stopped.'
        } elseif ($tunnelService) {
            Write-Host 'Cloudflare Tunnel service is already stopped.'
        } else {
            Write-Host 'Cloudflare Tunnel service is not installed.'
        }
        Remove-Item -LiteralPath $urlFile -Force -ErrorAction SilentlyContinue
    }
    return
}

# Stop a previously-created temporary Quick Tunnel during the move to the fixed domain.
if (Test-Path -LiteralPath $quickTunnelStateFile) {
    $quickState = Get-Content -LiteralPath $quickTunnelStateFile -Raw | ConvertFrom-Json
    $quickProcess = Get-Process -Id $quickState.pid -ErrorAction SilentlyContinue
    if ($quickProcess) {
        if ($quickProcess.StartTime.ToUniversalTime().Ticks.ToString() -ne $quickState.started -or
            $quickProcess.Path -ne $quickState.executable) {
            throw 'Recorded Quick Tunnel process identity does not match; refusing to stop it.'
        }
        Stop-Process -Id $quickProcess.Id
        $quickProcess.WaitForExit(10000) | Out-Null
    }
    Remove-Item -LiteralPath $quickTunnelStateFile -Force
    Remove-Item -LiteralPath $urlFile -Force -ErrorAction SilentlyContinue
}

$tunnelService = Get-Service -Name 'cloudflared' -ErrorAction SilentlyContinue
if (!$tunnelService) {
    throw 'The Cloudflare Tunnel service is not installed. Install it once using the Windows command shown for your Tunnel in Cloudflare.'
}

$localAlreadyRunning = $false
try {
    $health = Invoke-RestMethod $healthUrl -TimeoutSec 2
    $localAlreadyRunning = $health.status -eq 'ok'
} catch {}
if ($localAlreadyRunning) {
    if (!(Test-Path -LiteralPath $localStateFile)) {
        throw 'Port 8765 is serving an unmanaged process. Stop it manually before starting this deployment.'
    }
    & $stopLocalScript
}
if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8765 is occupied. Stop the process using it, then retry.'
}

try {
    $env:APP_ORIGIN = $publicUrl
    $env:COOKIE_SECURE = 'true'
    & $localScript -Prepare -Background

    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        try {
            $health = Invoke-RestMethod $healthUrl -TimeoutSec 1
            if ($health.status -eq 'ok') { $ready = $true; break }
        } catch {}
        Start-Sleep -Milliseconds 500
    }
    if (!$ready) { throw 'FitPlan did not become ready. Check runtime/server-error.log.' }

    $tunnelService = Get-Service -Name 'cloudflared' -ErrorAction Stop
    if ($tunnelService.Status -ne 'Running') {
        try { Start-Service -Name 'cloudflared' }
        catch { throw 'Could not start cloudflared. Run this script from an Administrator PowerShell.' }
        $startedTunnelService = $true
    }

    Set-Content -LiteralPath $urlFile -Value $publicUrl -Encoding utf8
    Write-Host "FitPlan is available at: $publicUrl"
    Write-Host "Local health check: $healthUrl"
    Write-Host 'To stop FitPlan and its Cloudflare Tunnel service, run: .\deploy\domain.ps1 -Stop'
} catch {
    if (Test-Path -LiteralPath $localStateFile) {
        try { & $stopLocalScript } catch {}
    }
    if ($startedTunnelService) {
        try { Stop-Service -Name 'cloudflared' -ErrorAction SilentlyContinue } catch {}
    }
    throw
} finally {
    if ($null -eq $previousAppOrigin) { Remove-Item Env:APP_ORIGIN -ErrorAction SilentlyContinue }
    else { $env:APP_ORIGIN = $previousAppOrigin }
    if ($null -eq $previousCookieSecure) { Remove-Item Env:COOKIE_SECURE -ErrorAction SilentlyContinue }
    else { $env:COOKIE_SECURE = $previousCookieSecure }
}
