@echo off
REM Starts the BDC hygiene worker. Make sure launch-chrome.bat has been run and
REM you're logged into Booking.com in that window.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo First-time setup: creating virtual environment and installing dependencies...
  python -m venv .venv || ( echo Python not found in PATH. Install Python 3.11+ and retry. & pause & exit /b 1 )
  call ".venv\Scripts\activate.bat"
  python -m pip install --upgrade pip
  pip install -r requirements.txt
  python -m playwright install chromium
) else (
  call ".venv\Scripts\activate.bat"
)

python worker.py
pause
