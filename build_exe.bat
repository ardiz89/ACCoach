@echo off
rem Build ACCoach.exe with PyInstaller (one-dir, windowed).
rem Requires: pip install pyinstaller
cd /d "%~dp0"
python -m PyInstaller --noconfirm --windowed --name ACCoach ^
  --icon accoach.ico ^
  --paths src ^
  --add-data "src/accoach/web;accoach/web" ^
  --add-data "src/accoach/voice_cues;accoach/voice_cues" ^
  --add-data "GUIDA.md;." ^
  --collect-submodules uvicorn ^
  --hidden-import pyttsx3.drivers ^
  --hidden-import pyttsx3.drivers.sapi5 ^
  --collect-all comtypes ^
  accoach_main.py
echo.
echo Done.  ->  dist\ACCoach\ACCoach.exe
pause
