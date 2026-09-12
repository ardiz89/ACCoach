@echo off
rem Build HONE.exe with PyInstaller (one-dir, windowed).
rem Requires: pip install pyinstaller
rem
rem DAL .spec, non da una riga di comando. Questa riga di comando c'era, ed era
rem la QUARTA copia dell'elenco dei payload: ne aveva quattro su sei. Mancavano
rem `tracks` (le linee centrali dei circuiti, quindi niente pista disegnata per
rem chi non ha AC installato) e `voice_cues_male` (voce maschile robotica invece
rem dei cue neurali gia' in repo). Nessuna delle due fa cadere il build: degradano
rem in silenzio, e te ne accorgi da utente.
rem
rem E' lo stesso difetto che il 04/08 era stato tolto dal workflow di release e
rem che il 12/09 e' stato tolto anche di li' una seconda volta: due fonti di
rem verita' per la stessa lista, e a spedire e' sempre quella che nessuno apre.
rem Il .spec e' la sola.
cd /d "%~dp0"
python -m PyInstaller --noconfirm HONE.spec
if errorlevel 1 ( echo. & echo Build failed. & pause & exit /b 1 )

rem Lo stesso guardiano che gira in CI: un payload perso non fa cadere il build,
rem quindi qualcuno deve guardare.
python tools\verify_bundle.py dist\HONE HONE.spec
if errorlevel 1 ( echo. & echo Il pacchetto e' incompleto. & pause & exit /b 1 )
echo.
echo Done.  -^>  dist\HONE\HONE.exe
pause
