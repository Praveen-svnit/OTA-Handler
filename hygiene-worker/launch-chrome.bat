@echo off
REM Opens Chrome with a DevTools debug port and a dedicated, persistent
REM "bdc-profile". Log into Booking.com ONCE in this window — the worker rides
REM this trusted session. Keep this window/profile open while scraping.

set "CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" (
  echo Could not find chrome.exe. Edit launch-chrome.bat and set the CHROME path.
  pause
  exit /b 1
)

start "" "%CHROME%" --remote-debugging-port=9222 --user-data-dir="%USERPROFILE%\bdc-profile" https://admin.booking.com
echo Chrome launched on debug port 9222 with profile "%USERPROFILE%\bdc-profile".
echo Log into Booking.com if prompted, then run start-worker.bat.
