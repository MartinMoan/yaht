@echo off
rem One-command setup + launch: creates a venv on first run and installs
rem dependencies, then starts the app. Safe to re-run any time -- the
rem venv/install step only happens once (delete the .venv folder to force
rem a clean reinstall). Double-clickable: calls venv's python.exe
rem directly instead of "activate", so it works with no PowerShell
rem execution-policy changes.
setlocal
cd /d "%~dp0.."

if not exist .venv (
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\python.exe -m pip install -r requirements.txt
)

.venv\Scripts\python.exe src\run.py %*
