@echo off
REM Starts the BDC hygiene worker. Make sure launch-chrome.bat has been run and
REM you're logged into Booking.com in that window first.
cd /d "%~dp0"

REM ── Locate Python (Anaconda first, then a plain PATH python) ───────────────
set "PY=%LOCALAPPDATA%\anaconda3\python.exe"
if not exist "%PY%" set "PY=%USERPROFILE%\anaconda3\python.exe"
if not exist "%PY%" set "PY=%USERPROFILE%\Anaconda3\python.exe"
if not exist "%PY%" set "PY=C:\ProgramData\Anaconda3\python.exe"
if not exist "%PY%" set "PY=%USERPROFILE%\miniconda3\python.exe"
if not exist "%PY%" set "PY=python"
echo Using Python: %PY%

REM ── First run only: install the 3 Python deps (no browser download needed —
REM    the worker attaches to your real Chrome, not a Playwright-managed one) ──
if not exist ".deps-installed" (
  echo Checking dependencies ^(first run only^)...
  "%PY%" -m pip install -r requirements.txt || ( echo pip install failed. & pause & exit /b 1 )
  echo ok> ".deps-installed"
)

"%PY%" worker.py
pause
