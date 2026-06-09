@echo off
REM Run-and-go BDC Hygiene scraper. Make sure launch-chrome.bat is open and
REM you're logged into Booking.com first.
cd /d "%~dp0"

REM ── Locate Python (Anaconda first, then a plain PATH python) ───────────────
set "PY=%LOCALAPPDATA%\anaconda3\python.exe"
if not exist "%PY%" set "PY=%USERPROFILE%\anaconda3\python.exe"
if not exist "%PY%" set "PY=%USERPROFILE%\Anaconda3\python.exe"
if not exist "%PY%" set "PY=C:\ProgramData\Anaconda3\python.exe"
if not exist "%PY%" set "PY=python"

if not exist ".deps-installed" (
  echo Installing dependencies ^(first run only^)...
  "%PY%" -m pip install -r requirements.txt || ( echo pip install failed. & pause & exit /b 1 )
  echo ok> ".deps-installed"
)

REM Pass through any args, e.g.  run-hygiene.bat --limit 50
"%PY%" run_hygiene.py %*
pause
