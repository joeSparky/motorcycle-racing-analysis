@echo off
setlocal
cd /d "%~dp0"
echo Race Analysis Setup
echo Keep this window open until setup finishes.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" echo Setup needs attention. See the message above and setup-log.txt.
pause
exit /b %RESULT%
