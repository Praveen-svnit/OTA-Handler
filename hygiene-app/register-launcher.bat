@echo off
REM === Run this ONCE on your PC ===============================================
REM Registers the bdchygiene:// link so the "Launch Scraper" / "Stop Scraper"
REM buttons on the OTA-Handler website can start and stop this app.
REM Per-user only (no admin rights). Run again only if you move the folder.

setlocal
echo Registering the BDC Hygiene launcher for this PC...

reg add "HKCU\Software\Classes\bdchygiene" /ve /d "URL:BDC Hygiene" /f >nul
reg add "HKCU\Software\Classes\bdchygiene" /v "URL Protocol" /t REG_SZ /d "" /f >nul
reg add "HKCU\Software\Classes\bdchygiene\shell\open\command" /ve /d "\"%~dp0protocol-handler.bat\" \"%%1\"" /f >nul

echo.
echo  Done. On the OTA-Handler site's "Scraper Set up" page, the
echo  "Launch Scraper" and "Stop Scraper" buttons will now work.
echo  (You only need to run this once on this PC.)
echo.
pause
