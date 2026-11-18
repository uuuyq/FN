@echo off
setlocal
title FNote

rem Resolve the launcher relative to this file, including paths with spaces.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-local.ps1" -Background %*
if errorlevel 1 goto failed

start "" "http://127.0.0.1:8765"
exit /b 0

:failed
echo.
echo FNote failed to start. See the error above.
pause
exit /b 1
