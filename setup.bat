@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  if exist .python\python.exe (
    .python\python.exe -m venv .venv
  ) else (
    py -3 -m venv .venv
  )
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo Setup complete. Double-click run.bat to start.
pause
exit /b 0
:failed
echo Setup failed. Install Python 3.11 or newer from python.org, including Tcl/Tk and the Python launcher, then try again.
pause
exit /b 1
