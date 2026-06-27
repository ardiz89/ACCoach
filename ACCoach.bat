@echo off
rem Double-click this to open the ACCoach launcher.
cd /d "%~dp0"
python run_launcher.py
if errorlevel 1 pause
