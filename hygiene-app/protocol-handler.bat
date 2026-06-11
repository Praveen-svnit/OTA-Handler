@echo off
REM Invoked by the bdchygiene:// link from the website.
REM Argument looks like:  bdchygiene://launch   or   bdchygiene://quit

echo %* | find /I "quit" >nul
if not errorlevel 1 (
  REM Stop: tell the running app to shut down
  powershell -NoProfile -WindowStyle Hidden -Command "try{[void](Invoke-WebRequest -UseBasicParsing -Method POST -Uri 'http://localhost:8765/api/quit' -TimeoutSec 3)}catch{}"
  exit /b
)

REM Launch: if already running, just open the panel; otherwise start the app
powershell -NoProfile -Command "try{(New-Object Net.Sockets.TcpClient('localhost',8765)).Close();exit 0}catch{exit 1}" >nul 2>&1
if not errorlevel 1 (
  start "" "http://localhost:8765"
) else (
  start "" "%~dp0Start Hygiene App.bat"
)
exit /b
