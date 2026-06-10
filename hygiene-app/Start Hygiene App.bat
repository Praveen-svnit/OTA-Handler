@echo off
REM ── Single-click launcher for the BDC Hygiene control panel ───────────────
cd /d "%~dp0"

set "PY=%LOCALAPPDATA%\anaconda3\python.exe"
if not exist "%PY%" set "PY=%USERPROFILE%\anaconda3\python.exe"
if not exist "%PY%" set "PY=%USERPROFILE%\Anaconda3\python.exe"
if not exist "%PY%" set "PY=C:\ProgramData\Anaconda3\python.exe"
if not exist "%PY%" set "PY=python"

if not exist ".deps-installed" (
  echo Setting up dependencies ^(first run only, ~1-2 min^)...
  "%PY%" -m pip install -r requirements.txt || ( echo Setup failed. & pause & exit /b 1 )
  echo ok> ".deps-installed"
)

echo Starting BDC Hygiene... a browser tab will open. Keep this window open while you work.
"%PY%" app.py
pause
