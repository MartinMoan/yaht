@echo off
rem Double-clickable wrapper around install.ps1 -- runs it with
rem -ExecutionPolicy Bypass so it works regardless of this machine's
rem PowerShell script policy, with no changes to system settings.
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
pause
