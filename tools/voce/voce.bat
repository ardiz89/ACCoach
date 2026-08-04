@echo off
rem Avvia e ferma l'assistente vocale da sviluppo.
rem
rem   voce            avvia (in una finestra ridotta a icona)
rem   voce stop       ferma
rem   voce stato      dice se sta girando
rem
rem Esiste per due motivi, e nessuno dei due e' la comodita'. Il primo: il
rem comando giusto usa il python del VENV, e quello di sistema qui non ha vosk
rem ne' sounddevice — sbagliarlo da' un ModuleNotFoundError che leggi quando sei
rem gia' seduto in macchina. Il secondo: due assistenti accesi si contendono il
rem microfono e nessuno dei due sente bene, quindi qui c'e' un solo posto e non
rem si parte due volte.
rem
rem Ricorda: questo apre il microfono, non l'ascolto. E' Claude che deve leggere
rem le righe con `Monitor` in modalita' `persistent` — se nessuno lo sta
rem leggendo, il microfono e' aperto per niente. Chiediglielo PRIMA di salire.

setlocal
cd /d "%~dp0"
set "ROOT=%~dp0..\.."
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "PIDFILE=%~dp0assistente.pid"

if /i "%~1"=="stop"  goto :stop
if /i "%~1"=="stato" goto :stato
goto :avvia


:avvia
rem Gia' acceso? Non ne serve un secondo: si toglierebbero l'audio a vicenda.
rem
rem Fuori dai blocchi ( ) di proposito: dentro un blocco cmd sostituisce %ALIVE%
rem quando LEGGE il blocco, cioe' prima che `:vivo` lo abbia calcolato, e il
rem messaggio esce con un PID vuoto. Sembra un dettaglio di stile e non lo e'.
call :vivo
if not errorlevel 1 goto :gia_acceso

if not exist "%PY%" (
  echo Manca il venv: %PY%
  echo Fallo una volta con HONE.bat, oppure:
  echo   python -m venv .venv ^&^& .venv\Scripts\pip install vosk sounddevice pyttsx3
  exit /b 1
)

rem Il modello vocale non sta in git — 88 MB — quindi puo' mancare su una
rem macchina appena clonata. Dirlo qui costa una riga; scoprirlo dallo stack
rem trace di vosk costa la sessione.
if not exist "%~dp0vosk-model-small-it-0.22\" (
  echo Manca il modello vocale in tools\voce\vosk-model-small-it-0.22\
  echo Si scarica da https://alphacephei.com/vosk/models e si scompatta qui.
  exit /b 1
)

rem Un lucchetto rimasto da una sessione uccisa mentre Claude parlava rende
rem l'assistente sordo. Si ripulisce da solo dopo 30 s, ma quei 30 s cadono
rem esattamente all'inizio, che e' quando provi se funziona.
if exist "%~dp0parla.lock" del /q "%~dp0parla.lock"

rem Due cose in un colpo solo, e la seconda e' quella che fa funzionare tutto.
rem
rem -PassThru per avere il PID: senza, fermarlo vorrebbe dire uccidere "un
rem python qualsiasi", e su questa macchina di python ne girano altri.
rem
rem -RedirectStandardOutput perche' Claude legge lo STDOUT DI UN COMANDO CHE
rem LANCIA LUI (`Monitor`), e un processo avviato da qui, in una finestra sua,
rem sarebbe muto per lui. Scrivendo su file i due pezzi diventano indipendenti:
rem l'assistente sopravvive a un `Monitor` fermato, e `Monitor` puo' attaccarsi
rem a un assistente gia' acceso. Il file si riscrive a ogni avvio — `tail -f`
rem parte comunque dalla fine, quindi non e' per evitare i doppioni: e' perche'
rem "l'ultima sessione" resti una cosa sola.
rem Il PID lo scrive PowerShell da se' sul file, invece di stamparlo e farlo
rem catturare da un `for /f`. Con la pipe, cmd resta appeso a leggerla finche'
rem non si chiude — e con un figlio appena avviato non si chiudeva: l'avvio
rem non tornava piu', pur avendo gia' acceso l'assistente.
powershell -NoProfile -Command ^
  "(Start-Process -FilePath '%PY%' -ArgumentList '\"%~dp0assistente.py\"' %* -PassThru -WindowStyle Hidden -RedirectStandardOutput '%~dp0voce.log' -RedirectStandardError '%~dp0voce.err.log').Id | Set-Content -Encoding ascii '%PIDFILE%'"

set "NEWPID="
if exist "%PIDFILE%" set /p NEWPID=< "%PIDFILE%"

if not defined NEWPID (
  echo Avvio fallito.
  exit /b 1
)
echo Assistente avviato ^(PID %NEWPID%^). Parola: «ehi copilota».
echo Sta scrivendo in tools\voce\voce.log — chiedi a Claude di leggerlo,
echo altrimenti il microfono e' aperto per niente.
exit /b 0


:stop
call :vivo || (
  echo Non sta girando.
  if exist "%PIDFILE%" del /q "%PIDFILE%"
  exit /b 0
)
taskkill /PID %ALIVE% /T /F >nul 2>&1
del /q "%PIDFILE%" 2>nul
if exist "%~dp0parla.lock" del /q "%~dp0parla.lock"
echo Assistente fermato.
exit /b 0


:stato
call :vivo
if errorlevel 1 goto :fermo
echo In ascolto ^(PID %ALIVE%^).
exit /b 0

:fermo
echo Fermo.
exit /b 1

:gia_acceso
echo L'assistente sta gia' girando ^(PID %ALIVE%^). Per fermarlo: voce stop
exit /b 0


rem Vivo davvero, non "c'e' un file". Un PID rimasto da un processo morto e' la
rem differenza fra "e' acceso" e "credevo fosse acceso", ed e' anche il modo in
rem cui un avvio rifiutato ti lascia senza assistente e convinto di averlo.
:vivo
set "ALIVE="
if not exist "%PIDFILE%" exit /b 1
set /p ALIVE=< "%PIDFILE%"
if not defined ALIVE exit /b 1
rem findstr per percorso pieno, non per nome. Su questa macchina `find` nel
rem PATH e' quello di Git Bash, che di un PID non sa cosa fare: il controllo
rem diceva "Fermo" su un assistente vivo, cioe' falliva nel modo peggiore.
tasklist /FI "PID eq %ALIVE%" /NH 2>nul | %SystemRoot%\System32\findstr.exe /c:"%ALIVE%" >nul || (
  set "ALIVE="
  exit /b 1
)
exit /b 0
