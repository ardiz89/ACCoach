@echo off
rem Double-click to install (first run) and start HONE — no command line needed.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo First run: setting up HONE ^(this happens once^)...
  python -m venv .venv
  if errorlevel 1 (
    echo.
    echo Python 3.11+ is required but was not found.
    echo Install it from https://www.python.org/downloads/  ^(tick "Add Python to PATH"^),
    echo then double-click HONE.bat again.
    pause
    exit /b 1
  )
  call ".venv\Scripts\activate.bat"
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  if errorlevel 1 ( echo. & echo Dependency install failed. & pause & exit /b 1 )
) else (
  call ".venv\Scripts\activate.bat"
)

python run_launcher.py
if errorlevel 1 pause
