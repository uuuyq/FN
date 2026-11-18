@echo off
setlocal
title FNote

rem Resolve the launcher relative to this file, including paths with spaces.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0domain.ps1" %*
if errorlevel 1 goto failed

set "FNOTE_PUBLIC_URL_FILE=%~dp0..\runtime\public-url.txt"
powershell.exe -NoLogo -NoProfile -Command "if (Test-Path -LiteralPath $env:FNOTE_PUBLIC_URL_FILE) { Start-Process ((Get-Content -LiteralPath $env:FNOTE_PUBLIC_URL_FILE -Raw).Trim()) }"
exit /b 0

:failed
echo.
echo FNote failed to start. See the error above.
pause
exit /b 1
