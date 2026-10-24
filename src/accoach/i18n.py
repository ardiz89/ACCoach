"""Lightweight internationalisation — language state + spoken-cue translation.

The app is bilingual (English / Italian). English is the canonical interface
language; the neural coach **voice** is Italian (pre-rendered WAVs keyed by the
Italian cue phrases). The live coaching cues are authored in Italian in the
detectors (so the Italian WAVs match verbatim); for an English session this
module translates each cue phrase to English at the boundary — the spoken text
(via SAPI5) and the on-screen cue both become English, while the Italian neural
pipeline is left untouched.

This is the foundation for a full UI language switch; later phases move the rest
of the on-screen text (debrief, engineer, focus, …) into a keyed catalogue.
"""

from __future__ import annotations

import re

LANGUAGES = ("en", "it")
DEFAULT_LANGUAGE = "en"

_NAMES = {"en": "English", "it": "Italiano"}


def language_name(lang: str) -> str:
    return _NAMES.get(lang, lang)


def current_language() -> str:
    """The active app language, from config (falls back to the default)."""
    try:
        from .config import load_config
        lang = load_config().language
    except Exception:  # pragma: no cover - config must never break coaching
        return DEFAULT_LANGUAGE
    return lang if lang in LANGUAGES else DEFAULT_LANGUAGE


# --- UI chrome catalogue (keyed; both languages equal) -----------------------
# Fixed interface strings for the Python surfaces (overlay, terminal, launcher),
# so they follow the selected language like the voice and cues do.
_UI: dict[str, dict[str, str]] = {
    # Il tono di tutto il catalogo è quello deciso col pilota il 21/10: frasi
    # brevi col tu, prima il fatto e poi cosa fare, niente emoji né due punti o
    # lineette a effetto, mai la stessa frase in due chiavi. `tests/tono.py` lo
    # controlla (superficie «hub»).
    # overlay: si legge guidando, quindi poche parole.
    "overlay.waiting": {"en": "Waiting for the game…", "it": "Aspetto il gioco…"},
    "overlay.rec": {"en": "Learning the reference lap…",
                    "it": "Sto imparando il giro di riferimento…"},
    # Why the coach is quiet. One per EngineState.quiet value: a gate that says
    # nothing is indistinguishable from a broken app, so each one names itself.
    "quiet.pit": {"en": "In the pits. I start at the line.",
                  "it": "Sei ai box. Parto dal traguardo."},
    "quiet.out_lap": {"en": "Out lap. I'll start at the line.",
                      "it": "Giro di lancio. Comincio dal traguardo."},
    "quiet.no_reference": {"en": "No reference yet. Drive one clean lap.",
                           "it": "Ancora nessun riferimento. Fai un giro pulito."},
    "quiet.off_pace": {"en": "Off-pace lap. I'll pick up at the line.",
                       "it": "Giro fuori ritmo. Riprendo dal traguardo."},
    "quiet.green": {"en": "Flying lap", "it": "Giro lanciato"},
    # Not a quiet reason: the coach keeps working, only the delta goes away.
    # Says what happened AND that the lap is still worth driving, because the
    # instinct on seeing "invalidated" is to abort and go back to the pits.
    "overlay.lap_invalid": {"en": "Lap invalidated. Keep going, no delta.",
                            "it": "Giro invalidato. Continua, senza delta."},
    "overlay.brake": {"en": "BRAKE", "it": "FRENA"},
    "overlay.pit_due": {"en": "BOX THIS LAP", "it": "RIENTRA AI BOX"},
    "overlay.focus": {"en": "FOCUS", "it": "FOCUS"},
    # Il delta di questo tratto, sotto il numero grande.
    "overlay.now": {"en": "now", "it": "ora"},
    "overlay.throttle_pedal": {"en": "THR", "it": "GAS"},
    "overlay.brake_pedal": {"en": "BRK", "it": "FRENO"},
    "overlay.steer": {"en": "STEER", "it": "STERZO"},
    # Da che parte e' girato il volante, accanto alla percentuale dello sterzo.
    "overlay.steer_left": {"en": "L", "it": "SX"},
    "overlay.steer_right": {"en": "R", "it": "DX"},
    "overlay.trail": {"en": "TRAIL", "it": "TRAIL"},
    "overlay.coast": {"en": "COAST", "it": "COAST"},
    # terminal coach
    "coach.title": {"en": "voice coach", "it": "coach vocale"},
    "coach.listening": {"en": "Listening. Drive and I'll coach you.",
                        "it": "Ti ascolto. Guida e ti seguo."},
    "coach.warming": {"en": "I'm getting your measure. Drive a few complete laps.",
                      "it": "Sto prendendo le misure. Fai qualche giro completo."},
    "coach.delta_title": {"en": "Delta to reference", "it": "Delta sul riferimento"},
    "coach.delta_none": {"en": "The delta appears after your first clean lap.",
                         "it": "Il delta arriva dopo il primo giro pulito."},
    "coach.focus_title": {"en": "Focus · lesson", "it": "Focus · lezione"},
    "coach.coach_panel": {"en": "Coach", "it": "Coach"},
    "lbl.delta": {"en": "Delta", "it": "Delta"},
    "lbl.predicted": {"en": "Predicted", "it": "Previsto"},
    "lbl.reference": {"en": "Reference", "it": "Riferimento"},
    "lbl.state": {"en": "State", "it": "Stato"},
    "lbl.car_track": {"en": "Car @ Track", "it": "Auto @ Pista"},
    "lbl.current": {"en": "Current", "it": "Attuale"},
    "lbl.last": {"en": "Last", "it": "Ultimo"},
    "lbl.best": {"en": "Best", "it": "Migliore"},
    "lbl.laps_saved": {"en": "Laps saved", "it": "Giri salvati"},
    "voice.on": {"en": "voice", "it": "voce"},
    "voice.off": {"en": "text", "it": "testo"},
    # launcher
    "ui.language": {"en": "Language", "it": "Lingua"},
    "ui.tip_borderless": {
        "en": "Set the game to Borderless so the overlay can draw over it.",
        "it": "Metti il gioco in Borderless, così l'overlay compare sopra."},
    # I bottoni sono nomi corti, senza emoji e senza note fra parentesi: dove la
    # differenza conta (si apre nel browser, serve a un secondo schermo) lo dice
    # il suggerimento del bottone, con una frase.
    "btn.coach_live": {"en": "Coach Live", "it": "Coach Live"},
    "btn.coach_live_demo": {"en": "Demo without a game",
                            "it": "Demo senza gioco"},
    "btn.analysis": {"en": "Analysis and report", "it": "Analisi e report"},
    "btn.engineer": {"en": "Race engineer", "it": "Ingegnere di pista"},
    "btn.server": {"en": "Coach without overlay", "it": "Coach senza overlay"},
    "btn.debrief": {"en": "Last-lap debrief", "it": "Debrief dell'ultimo giro"},
    "btn.monitor": {"en": "Telemetry monitor", "it": "Monitor della telemetria"},
    "btn.coach_term": {"en": "Voice coach in a terminal",
                       "it": "Coach vocale nel terminale"},
    "btn.verify_g": {"en": "Check the G axes", "it": "Verifica gli assi G"},
    "btn.get_started": {"en": "Getting started", "it": "Come iniziare"},
    "tip.browser": {"en": "Opens in your browser.", "it": "Si apre nel browser."},
    "tip.server": {"en": "The coach talks and feeds the tablet, with nothing "
                         "drawn over the game.",
                   "it": "Il coach parla e alimenta il tablet, senza niente "
                         "disegnato sopra il gioco."},
    "tip.overlay": {"en": "Draws the overlay over the game, for a coach that "
                          "is already running without one.",
                    "it": "Disegna l'overlay sopra il gioco, per un coach già "
                          "acceso senza."},
    # First-run wizard. Was hardcoded English in a bilingual app: the very first
    # screen a new driver sees ignored the language they had just chosen.
    "wiz.title": {"en": "Welcome to HONE", "it": "Benvenuto in HONE"},
    "wiz.sub": {"en": "Here's how to get going.",
                "it": "Ecco come si comincia."},
    "wiz.dont_show": {"en": "Don't show this again",
                      "it": "Non mostrarlo più"},
    "wiz.open_guide": {"en": "Open full guide", "it": "Apri la guida completa"},
    "wiz.go": {"en": "Get started", "it": "Cominciamo"},
    "wiz.s1": {
        "en": "Set AC or ACC to <b>Borderless</b>. The overlay can't draw over "
              "exclusive fullscreen.",
        "it": "Metti AC o ACC in <b>Borderless</b>. Sullo schermo intero "
              "esclusivo l'overlay non compare."},
    "wiz.s2": {
        "en": "Open <b>Drive</b> in the sidebar and press <b>Coach Live</b>. The "
              "panel walks you through it. A tablet is optional, and if you "
              "have one you connect it with a QR code. When you're done, "
              "<b>I'm done</b> opens the Report card.",
        "it": "Apri <b>In pista</b> nella barra laterale e premi <b>Coach "
              "Live</b>. Il pannello ti accompagna passo per passo. Il tablet è "
              "facoltativo, e se ce l'hai lo colleghi col codice QR. Quando hai "
              "finito, <b>Ho finito</b> apre la Pagella."},
    "wiz.s3": {
        "en": "Drive one clean, complete lap. It becomes your <b>reference</b>, and the "
              "delta appears from the next lap on. Until then the coach still "
              "calls locks, slides and tyres, everything that doesn't need a "
              "lap to compare against.",
        "it": "Fai un giro pulito completo. Diventa il tuo <b>riferimento</b>, e il delta "
              "compare dal giro dopo. Fino ad allora il coach ti segnala comunque "
              "bloccaggi, scivolate e gomme, cioè tutto quello che non ha "
              "bisogno di un giro con cui confrontarti."},
    "wiz.s4": {
        "en": "After the session open <b>Analysis</b> for the corner-by-corner "
              "debrief, and <b>Setup</b> for the race engineer.",
        "it": "A fine sessione apri <b>Analisi</b> per il debrief curva per curva, "
              "e <b>Setup</b> per l'ingegnere di pista."},
    "wiz.s5": {
        "en": "No game handy? <b>Demo without a game</b> runs it all on a "
              "synthetic lap.",
        "it": "Non hai il gioco sottomano? <b>Demo senza gioco</b> fa girare "
              "tutto su un giro finto."},
    "btn.import_pro": {"en": "Import a PRO reference lap",
                       "it": "Importa un giro di riferimento PRO"},
    # Says what it's FOR, not what it does. The feature only makes sense once you
    # know the default reference is yourself.
    "import.hint": {
        "en": "Your reference is usually your own best lap. Import a faster "
              "one and the coach measures you against that instead.",
        "it": "Di solito il riferimento è il tuo giro migliore. Se ne importi "
              "uno più veloce, il coach ti misura su quello."},
    "import.done": {"en": "Imported the {car} lap at {track}, {time}.",
                    "it": "Ho importato il giro di {car} a {track}, {time}."},
    "import.failed": {"en": "I can't read that lap. {err}",
                      "it": "Non riesco a leggere questo giro. {err}"},
    "btn.guide": {"en": "User guide", "it": "Guida all'uso"},
    "btn.overlay": {"en": "Add the overlay", "it": "Aggiungi l'overlay"},
    # hub — sidebar navigation
    "nav.home": {"en": "Home", "it": "Home"},
    # "In pista" e non "Guida": in italiano collideva con la guida all'uso, e
    # chi cercava il manuale finiva sui pulsanti di Coach Live. In inglese la
    # collisione non c'era mai stata (Drive / Guide).
    "nav.live": {"en": "Drive", "it": "In pista"},
    "nav.analysis": {"en": "Analysis", "it": "Analisi"},
    "nav.setup": {"en": "Setup", "it": "Setup"},
    "nav.devices": {"en": "Devices", "it": "Dispositivi"},
    "nav.settings": {"en": "Settings", "it": "Impostazioni"},
    # hub — section intros
    "sec.devtools": {"en": "Advanced tools", "it": "Strumenti avanzati"},
    # hub — Home (last session)
    "home.loading": {"en": "Loading your last session…",
                     "it": "Carico l'ultima sessione…"},
    # Terzo stato accanto a "vuoto" e "nessun riferimento": l'archivio non si
    # legge. Prima finiva su "vuoto", cioè si diceva «non hai mai guidato» a chi
    # aveva appena finito una sessione, e lo si mandava a guidare di più invece
    # che a guardare i log. Il file di log e non «Impostazioni → Log»: nelle
    # Impostazioni una voce Log non c'è.
    "home.error_title": {"en": "I can't read your laps",
                         "it": "Non riesco a leggere i tuoi giri"},
    "home.error_body": {
        "en": "The lap archive didn't open. Another HONE window may be using "
              "it, or a file is damaged. The log file has the details, and "
              "your laps are still on disk.",
        "it": "L'archivio dei giri non si è aperto. Forse lo usa un'altra "
              "finestra di HONE, o un file è danneggiato. I dettagli sono nel "
              "file di log, e i tuoi giri sono ancora sul disco."},
    "home.empty_title": {"en": "No sessions yet",
                         "it": "Ancora nessuna sessione"},
    "home.empty_body": {"en": "Get on track and drive two laps. I'll listen and "
                              "tell you where you lose time.",
                        "it": "Sali in pista e fai due giri. Io ascolto e ti dico "
                              "dove perdi tempo."},
    "home.no_ref_title": {"en": "Almost there", "it": "Ci siamo quasi"},
    "home.no_ref_body": {"en": "Drive one clean, valid lap so I have a reference to "
                               "compare against.",
                         "it": "Fai un giro pulito e valido, così ho un riferimento "
                               "con cui confrontarti."},
    "home.clean_title": {"en": "Clean lap", "it": "Giro pulito"},
    "home.clean_body": {"en": "You're slower than your reference, but no single "
                              "corner cost you much. Work on consistency to close "
                              "the gap.",
                        "it": "Sei più lento del riferimento, ma nessuna curva ti è "
                              "costata molto. Per recuperare, lavora sulla "
                              "costanza."},
    "home.is_reference": {"en": "This is your reference lap. I have nothing faster "
                                "to compare it with.",
                          "it": "Questo è il tuo giro di riferimento. Non ho un "
                                "giro più veloce con cui confrontarlo."},
    "home.cta_analysis": {"en": "Analyze", "it": "Analizza"},
    "home.cta_drive": {"en": "Go to Drive", "it": "Vai in pista"},
    "home.cta_demo": {"en": "Try the demo", "it": "Prova la demo"},
    "home.config_bad": {
        "en": "config.toml can't be read, so HONE is using the default settings. "
              "Fix the file or delete it, and HONE writes a new one on the next "
              "start.",
        "it": "config.toml non si legge, quindi HONE usa le impostazioni "
              "predefinite. Correggi il file o cancellalo, e HONE ne scrive uno "
              "nuovo al prossimo avvio."},
    "home.cta_debrief": {"en": "Full debrief", "it": "Debrief completo"},
    "home.cta_setup": {"en": "Try a setup", "it": "Prova un setup"},
    "home.stat_best": {"en": "Best lap", "it": "Miglior giro"},
    "home.stat_gap": {"en": "Gap to ref", "it": "Distacco rif."},
    "home.stat_laps": {"en": "Valid laps", "it": "Giri validi"},
    "home.stat_consistency": {"en": "Typical spread", "it": "Scarto tipico"},
    # phone / tablet (LAN) dialog
    "mob.title": {"en": "Open on a phone or tablet",
                  "it": "Apri su telefono o tablet"},
    "mob.lan": {"en": "Allow access from other devices on my network",
                "it": "Consenti l'accesso dagli altri dispositivi in rete"},
    "mob.report": {"en": "Report", "it": "Report"},
    "mob.engineer": {"en": "Engineer", "it": "Ingegnere"},
    "mob.test": {"en": "On-track test", "it": "Test in pista"},
    "mob.test_live": {"en": "To capture the coach's cues on the test page, start "
                            "the Coach without overlay too.",
                      "it": "Per registrare gli avvisi del coach nella pagina di "
                            "prova, avvia anche il Coach senza overlay."},
    "mob.scan": {"en": "Scan the code, or type the address under it into the "
                       "browser, key included.",
                 "it": "Inquadra il codice, oppure scrivi nel browser "
                       "l'indirizzo che c'è sotto, chiave compresa."},
    # La chiave sta in Documenti\ACCoach: con l'Accesso controllato alle
    # cartelle di Windows non si crea, e un QR senza chiave porta al 401.
    # Windows blocca un eseguibile, non «HONE»: il pacchetto scrive come
    # HONE.exe, chi parte da HONE.bat come python.exe. Una frase sola per tutti e
    # due, perche' il programma non lo sa dire con certezza (pythonw.exe a parte).
    "mob.no_key": {"en": "HONE can't save the network key in its folder, so "
                         "there's no code. In Windows Security settings, allow "
                         "HONE.exe to write to the Documents folder, or "
                         "python.exe if you start HONE from HONE.bat.",
                   "it": "HONE non riesce a salvare la chiave di rete nella sua "
                         "cartella, quindi il codice non c'è. Nelle "
                         "impostazioni di Sicurezza di Windows consenti a "
                         "HONE.exe di scrivere nella cartella Documenti, o a "
                         "python.exe se avvii HONE da HONE.bat."},
    "mob.off": {"en": "Turn on the option above to open these pages from your phone.",
                "it": "Attiva l'opzione qui sopra per aprire le pagine dal telefono."},
    "mob.no_ip": {"en": "No network address found. Connect this PC to Wi-Fi or "
                        "Ethernet.",
                  "it": "Non trovo un indirizzo di rete. Collega il PC al Wi-Fi o "
                        "al cavo di rete."},
    "mob.same_net": {"en": "Your phone must be on the same Wi-Fi network as this PC.",
                     "it": "Il telefono deve stare sulla stessa rete Wi-Fi del PC."},
    "mob.firewall": {"en": "If Windows asks, allow access on Private networks.",
                     "it": "Se Windows lo chiede, consenti l'accesso su reti private."},
    "mob.restart": {"en": "If you change this, restart Coach Live or Analysis.",
                    "it": "Se cambi questa opzione, riavvia Coach Live o Analisi."},
    "mob.no_qr": {"en": "No QR code. Install the segno package.",
                  "it": "Il codice QR non c'è. Installa il pacchetto segno."},
    "mob.server_on": {"en": "The analysis server is running. These pages will open.",
                      "it": "Il server dell'analisi è acceso. Queste pagine si "
                            "aprono."},
    "mob.server_off": {"en": "The analysis server is off, so these pages won't "
                             "load. Start it from Analysis.",
                       "it": "Il server dell'analisi è spento e queste pagine non "
                             "si aprono. Avvialo da Analisi."},
    # settings
    "set.voice": {"en": "Coach voice", "it": "Voce del coach"},
    "set.engineer_voice": {"en": "Speak the engineer's proposals",
                           "it": "Annuncia a voce le proposte dell'ingegnere"},
    # Una scelta fra due voci, non una casella: «Voce maschile» spenta non
    # diceva quale voce restava (24/10). La chiave del config resta `male`.
    "set.male_voice": {"en": "Voice", "it": "Voce"},
    "set.voice_male": {"en": "Male", "it": "Maschile"},
    "set.voice_female": {"en": "Female", "it": "Femminile"},
    "set.rate_unit": {"en": " words/min", "it": " parole/min"},
    "set.radio": {"en": "Team-radio effect", "it": "Effetto radio di pista"},
    "set.rate": {"en": "Voice speed", "it": "Velocità della voce"},
    "set.scale": {"en": "Overlay size", "it": "Grandezza dell'overlay"},
    # One "?" per setting. Reported by the user: a field named "Overlay scale"
    # or "Reading speed" means nothing to someone who didn't build it, and the
    # panel had no help text of any kind. Each answers WHAT it does and WHEN to
    # touch it, because a definition alone ("scales the overlay") helps nobody.
    "set.voice.help": {
        "en": "Speaks the coaching cues out loud. Turn it off to keep only the "
              "on-screen overlay. It comes in handy in a race, or on a headset "
              "you share with a voice chat.",
        "it": "Legge i consigli ad alta voce. Spegnila per tenere solo "
              "l'overlay a schermo. Ti torna utile in gara, o se usi le cuffie "
              "anche per parlare con qualcuno."},
    # «Setup» e non «Assetto»: è il nome della sezione nella barra laterale.
    "set.engineer_voice.help": {
        "en": "Whether the race engineer's setup proposals are spoken too. "
              "They arrive between laps, not while you're in a corner. If "
              "you turn it off, you still find them in the Setup section.",
        "it": "Decide se anche le proposte di assetto dell'ingegnere si sentono "
              "a voce. Arrivano fra un giro e l'altro, non mentre sei in curva. "
              "Se la spegni, le trovi comunque nella sezione Setup."},
    "set.male_voice.help": {
        "en": "Who speaks the cues. The words and the timing stay the same, "
              "only the speaker changes.",
        "it": "Chi dice i consigli. Le parole e i tempi restano gli stessi, "
              "cambia solo chi parla."},
    "set.radio.help": {
        "en": "Filters the voice to sound like a pit-to-car radio. It's only an "
              "effect, and it changes nothing the coach says. Off is the clearest.",
        "it": "Filtra la voce perché suoni come una radio di pista. È solo un "
              "effetto e non cambia niente nei consigli. Spenta si capisce "
              "meglio."},
    "set.rate.help": {
        "en": "How fast the voice talks, in words per minute. Normal speech is "
              "around 165. Raise it if cues arrive too late in fast corners, "
              "lower it if you're missing words.",
        "it": "Quanto in fretta parla la voce, in parole al minuto. Il parlato "
              "normale è intorno a 165. Alzala se nelle curve veloci i consigli "
              "arrivano tardi, abbassala se ti perdi delle parole."},
    # Auto-record: the only setting that makes HONE do something without being
    # pressed, so the help says exactly what starts (and what doesn't).
    "set.autorecord": {"en": "Record by itself when the game starts",
                       "it": "Registra da solo quando parte il gioco"},
    "set.autorecord.help": {
        "en": "With the hub open, HONE notices AC or ACC starting and records "
              "your laps on its own. A session you forgot to start isn't lost. "
              "Only the silent recorder starts, and the voice and the overlay "
              "stay off until you press Coach Live. It's off by default.",
        "it": "Con l'hub aperto, HONE si accorge che AC o ACC è partito e "
              "registra i tuoi giri da solo. Così non perdi una sessione che hai "
              "dimenticato di avviare. Parte solo la registrazione silenziosa, e "
              "voce e overlay restano spenti finché non premi Coach Live. "
              "All'inizio è spenta.",
    },
    "watch.waiting": {"en": "Waiting for the game to start.",
                      "it": "Aspetto che parta il gioco."},
    "watch.recording": {"en": "The game is running. Starting the recorder.",
                        "it": "Il gioco è partito, avvio la registrazione."},
    "watch.busy": {"en": "Already recording.", "it": "Sto già registrando."},
    "set.wean": {"en": "Retire braking markers", "it": "Ritira i segnali di frenata"},
    "set.wean.help": {
        "en": "Once you master a corner, the braking countdown stops appearing "
              "there. It's like taking the racing line and the braking boards "
              "away one at a time as you learn a track. Off keeps them at every "
              "corner.",
        "it": "Quando domini una curva, lì il conto alla rovescia della frenata "
              "smette di comparire. È come togliere una alla volta traiettoria e "
              "cartelli quando impari una pista. Se lo spegni, restano in ogni "
              "curva."},
    # Un pulsante spento senza motivo si legge come un guasto. Questo compare
    # come suggerimento su tutto ciò che registra, quando qualcos'altro già lo fa.
    "btn.busy_recording": {
        "en": "Something is already recording this session. With two recorders "
              "every lap is saved twice, and the copy looks like a real extra "
              "lap. Stop the running one first.",
        "it": "Qualcosa sta già registrando questa sessione. Con due "
              "registratori ogni giro si salva due volte, e la copia sembra un "
              "giro vero in più. Ferma prima quello acceso."},
    # --- lo scambio Coach Live → Coach senza overlay ------------------------------
    # Il Coach senza overlay non può stare acceso insieme a Coach Live. Finché queste
    # frasi non c'erano, il bottone era spento e muto. Dal 24/09 la pagina
    # Ingegnere la alimenta anche Coach Live, quindi le frasi dicono pure
    # questo: chi è arrivato qui cercando la pagina non ha bisogno dello scambio.
    "swap.title": {
        "en": "The coach without overlay can't run next to Coach Live",
        "it": "Il Coach senza overlay non può girare insieme a Coach Live"},
    "swap.why": {
        "en": "The coach without overlay records laps just like Coach Live. With both "
              "running, every lap you drive is saved twice, and afterwards the "
              "copy can't be told apart from a real lap. If you're here for the "
              "Engineer page you don't need it. While Coach Live runs, Coach "
              "Live feeds that page itself.",
        "it": "Il Coach senza overlay registra i giri proprio come Coach Live. Con tutti "
              "e due accesi ogni giro che guidi si salva due volte, e dopo la "
              "copia non si distingue da un giro vero. Se sei qui per la pagina "
              "Ingegnere non ti serve. Finché Coach Live è acceso, quella pagina "
              "la alimenta lui."},
    "swap.warn": {
        "en": "Swapping stops Coach Live and starts the coach without overlay. "
              "The coach keeps talking and the Engineer page stays fed. "
              "The overlay, though, closes with Coach Live, so you have no HUD "
              "on track. The coach, the overlay and the web page are three "
              "separate pieces. You can bring the overlay back on its own "
              "from Settings, under Advanced tools.",
        "it": "Lo scambio ferma Coach Live e al suo posto avvia il Coach senza overlay. "
              "Il coach continua a parlare e la pagina Ingegnere resta "
              "alimentata. L'overlay però si spegne insieme a Coach Live, e in "
              "pista resti senza HUD. Coach, overlay e pagina web sono tre "
              "pezzi separati, e l'overlay si riaccende a parte da "
              "Impostazioni, in Strumenti avanzati."},
    # Senza glifo: `⇄` (U+21C4) non c'è nei font del brand né nel ripiego di
    # sistema, e a schermo usciva come un rettangolo vuoto davanti alla frase.
    "swap.confirm": {"en": "Stop Coach Live and switch",
                     "it": "Ferma Coach Live e passa"},
    # Etichette corte di proposito: tre bottoni con frasi intere spingevano la
    # finestra a 685 px in italiano, cioè righe lunghe e faticose. Cosa fa
    # ciascuna uscita lo dicono i paragrafi sopra, non il bottone.
    "swap.cancel": {"en": "Cancel", "it": "Annulla"},
    "swap.failed": {
        "en": "Coach Live is still running, so the coach without overlay didn't start. "
              "Two recorders would have saved every lap twice. Press “Stop "
              "without opening the report”, wait for its window to close and "
              "try again.",
        "it": "Coach Live è ancora acceso, quindi il Coach senza overlay non è partito. "
              "Con due registratori ogni giro si sarebbe salvato due volte. "
              "Premi «Ferma senza aprire il report», aspetta che la sua finestra "
              "si chiuda e riprova."},
    "swap.tooltip": {
        "en": "Coach Live is running. Click to read why this can't run "
              "alongside Coach Live, and to swap over in one step.",
        "it": "Coach Live è acceso. Premi per leggere perché non può girare "
              "insieme a Coach Live, e per fare lo scambio in un passo."},
    "set.pedals": {"en": "Show the pedal trace", "it": "Mostra la traccia dei pedali"},
    "set.pedals.help": {
        "en": "A strip under the overlay shows your throttle (green) and brake "
              "(red) as you use them. The ribbon under it turns amber while both "
              "pedals are down, which is trail braking. It turns grey while "
              "neither is, and that's time you're giving away. It's the only "
              "place where you watch your brake release as you do it, instead "
              "of being told about it afterwards.",
        "it": "Una striscia sotto l'overlay mostra il gas (verde) e il freno "
              "(rosso) mentre li usi. Il nastro sotto diventa ambra quando premi "
              "tutti e due i pedali, cioè quando fai trail braking. Diventa "
              "grigio quando non ne premi nessuno, e quello è tempo regalato. È "
              "l'unico posto dove vedi il rilascio del freno mentre lo fai, "
              "invece di sentirtelo raccontare dopo."},
    "set.pedals_hint": {
        "en": "The pedal trace makes the overlay taller.",
        "it": "La traccia dei pedali allunga l'overlay."},
    "set.scale.help": {
        "en": "How big the overlay is on screen. At 1.0 it has its design size. "
              "Raise it on a 4K monitor or if you sit far from the screen, lower "
              "it if it covers too much track.",
        "it": "Quanto è grande l'overlay sullo schermo. A 1,0 ha la grandezza di "
              "progetto. Alzala su un monitor 4K o se stai lontano dallo schermo, "
              "abbassala se ti copre troppa pista."},
    "set.scale_hint": {
        "en": "The pedal trace and the overlay size apply from the next Coach "
              "Live start.",
        "it": "Traccia dei pedali e grandezza dell'overlay valgono dal prossimo "
              "avvio di Coach Live."},
    "btn.save": {"en": "Save", "it": "Salva"},
    "set.saved": {"en": "Saved.", "it": "Salvato."},
    "set.save_failed": {
        "en": "config.toml has an error. Fix it or delete it, then save again.",
        "it": "config.toml contiene un errore. Correggilo o cancellalo, poi salva di nuovo."},
    "btn.close": {"en": "Close", "it": "Chiudi"},
    # Il pannello «In pista» (`livepanel_ui.py`): dal via di Coach Live alla
    # Pagella. Il tono e' quello deciso col pilota il 21/10: frasi brevi col tu,
    # prima il fatto e poi cosa fare, mai la stessa frase in due posti (un test
    # lo controlla).
    "live.preview": {"en": "What happens when you start it",
                     "it": "Cosa succede quando lo avvii"},
    "live.before": {"en": "Before you go", "it": "Prima di partire"},
    "live.driving": {"en": "You're driving", "it": "Stai guidando"},
    "live.finished": {"en": "Session over", "it": "Sessione finita"},
    "live.s1": {"en": "Coach Live is on", "it": "Coach Live acceso"},
    "live.s1_sub": {"en": "Voice and overlay are ready.",
                    "it": "Voce e overlay sono pronti."},
    # Facoltativo, e lo dice il titolo: senza, chi non ha un tablet credeva di
    # non poter partire (24/10).
    "live.s2": {"en": "Connect a tablet, if you have one",
                "it": "Collega un tablet, se ce l'hai"},
    "live.s2_scan": {"en": "Scan the code with the tablet's camera, or type "
                           "this address, key included.",
                     "it": "Inquadra il codice con la fotocamera del tablet, "
                           "oppure scrivi questo indirizzo, chiave compresa."},
    "live.s2_lan_off": {
        "en": "The tablet can only connect with network access on. Turn it on "
              "in Devices, then restart Coach Live.",
        "it": "Il tablet si collega solo con la rete locale attiva. Attivala in "
              "Dispositivi, poi riavvia Coach Live."},
    # Coach Live apre la rete solo se la LAN era accesa quando e' partito:
    # accenderla a corsa iniziata non basta.
    "live.s2_lan_restart": {
        "en": "Coach Live started with network access off. Restart it to "
              "connect the tablet.",
        "it": "Coach Live è partito con la rete locale spenta. Riavvialo per "
              "collegare il tablet."},
    "live.s2_to_devices": {"en": "Turn on network access",
                           "it": "Attiva la rete locale"},
    "live.s2_no_ip": {
        "en": "This PC has no network address. Connect it to Wi-Fi or Ethernet.",
        "it": "Questo PC non ha un indirizzo di rete. Collegalo al Wi-Fi o al "
              "cavo di rete."},
    # Non «aprila su questo PC»: e' la stessa pagina che non risponde.
    "live.s2_web_down": {
        "en": "The Engineer page isn't answering yet. If the tablet can't open "
              "it, skip this step and drive without.",
        "it": "La pagina Ingegnere non risponde ancora. Se il tablet non la "
              "apre, salta questo passo e guida senza."},
    "live.open_here": {"en": "Open on this PC", "it": "Apri su questo PC"},
    "live.skip": {"en": "Skip, I'll drive without", "it": "Salta, guido senza"},
    # «il gioco» e non «ACC»: HONE segue anche AC, e il passo vale per tutti e due.
    "live.s3": {"en": "Start the game and leave the pits",
                "it": "Avvia il gioco ed esci dai box"},
    "live.s3_sub": {"en": "This ticks itself when the telemetry arrives.",
                    "it": "Si spunta da solo quando arriva la telemetria."},
    "live.tablet_on": {"en": "Tablet connected.", "it": "Tablet collegato."},
    "live.tablet_off": {
        "en": "The tablet disconnected. Wake its screen or reload the page.",
        "it": "Il tablet si è scollegato. Riaccendi lo schermo o ricarica la "
              "pagina."},
    "live.tablet_skipped": {"en": "Driving without the tablet.",
                            "it": "Guidi senza tablet."},
    "live.tablet_none": {"en": "No tablet connected.",
                         "it": "Nessun tablet collegato."},
    "live.laps_one": {"en": "1 lap completed", "it": "1 giro completato"},
    "live.laps": {"en": "{n} laps completed", "it": "{n} giri completati"},
    "live.no_lap_yet": {"en": "No lap completed yet",
                        "it": "Ancora nessun giro completato"},
    "live.best": {"en": "best {time}", "it": "migliore {time}"},
    "live.following": {"en": "You're working on “{name}”.",
                       "it": "Stai seguendo il consiglio «{name}»."},
    "live.following_sub": {
        "en": "The coach reminds you in the corners of this tip.",
        "it": "Il coach te lo ricorda nelle curve di questo consiglio."},
    "live.finish": {"en": "I'm done, show me how it went",
                    "it": "Ho finito, mostrami com'è andata"},
    "live.finish_sub": {"en": "Stops the coach and opens the Report card.",
                        "it": "Ferma il coach e apre la Pagella."},
    "live.stop_quiet": {"en": "Stop without opening the report",
                        "it": "Ferma senza aprire il report"},
    "live.no_laps": {
        "en": "No laps saved in this run. The report opens on your last session.",
        "it": "Nessun giro salvato in questa corsa. Il report si apre "
              "sull'ultima sessione."},
    "live.saved_one": {"en": "1 lap saved", "it": "1 giro salvato"},
    "live.saved": {"en": "{n} laps saved", "it": "{n} giri salvati"},
    "live.valid_one": {"en": "1 valid", "it": "1 valido"},
    "live.valid": {"en": "{n} valid", "it": "{n} validi"},
    "live.minute_one": {"en": "1 minute", "it": "1 minuto"},
    "live.minutes": {"en": "{n} minutes", "it": "{n} minuti"},
    # Senza «da un minuto»: dopo «Resto in pista» la scheda puo' tornare dopo
    # molto di piu'.
    "live.closed": {
        "en": "The game is closed. The coach stays on until you stop it, in "
              "case you're only changing track.",
        "it": "Il gioco è chiuso. Il coach resta acceso finché non lo fermi tu, "
              "nel caso tu stia solo cambiando pista."},
    "live.show": {"en": "Show me how it went", "it": "Mostrami com'è andata"},
    "live.stay": {"en": "I'm staying on track", "it": "Resto in pista"},
    # Prima della prima risposta di /health: non e' «muto» (vedi STARTING_S).
    "live.starting": {"en": "The coach is starting…",
                      "it": "Il coach si sta avviando…"},
    "live.unreachable": {
        "en": "Coach Live is on but isn't answering. This panel updates by "
              "itself as soon as it does.",
        "it": "Coach Live è acceso ma non risponde. Il pannello si aggiorna da "
              "solo appena risponde."},
    "live.silent": {
        "en": "The coach isn't answering. If it doesn't come back in a few "
              "seconds, stop it and start it again.",
        "it": "Il coach non risponde. Se non torna fra qualche secondo, "
              "fermalo e riavvialo."},
    "live.stop_late": {
        "en": "The coach didn't stop within 5 s. The report opens anyway.",
        "it": "Il coach non si è fermato entro 5 s. Il report si apre lo stesso."},
    "live.report_wait": {"en": "Opening the report…",
                         "it": "Sto aprendo il report…"},
    "live.report_late": {
        "en": "The report didn't answer within 5 s. If the page stays blank, "
              "reload it.",
        "it": "Il report non ha risposto entro 5 s. Se la pagina resta vuota, "
              "ricaricala."},
    # Il rifiuto di un nome curva o di un riferimento di frenata con dentro un
    # carattere che apre un tag nelle pagine (sicurezza, 23/10). Due frasi:
    # un riferimento non è un nome.
    "names.forbidden": {"en": "The name can't contain < or >.",
                        "it": "Il nome non può contenere < o >."},
    "marks.forbidden": {"en": "The reference can't contain < or >.",
                        "it": "Il riferimento non può contenere < o >."},
    # La fascia della modalità demo sulle pagine che non caricano i18n.js
    # (oggi solo /test): le altre usano `demo.banner` del catalogo JS.
    "demo.bannerPlain": {"en": "Demo mode. Laps and alerts here are samples.",
                         "it": "Modalità demo. Giri e avvisi qui sono di esempio."},
}


def t(key: str, lang: str | None = None, **fmt) -> str:
    """Translate a UI key into the active (or given) language; format with ``fmt``.

    Falls back to English, then to the key itself, so a missing entry is visible
    rather than crashing."""
    lang = lang or current_language()
    entry = _UI.get(key, {})
    text = entry.get(lang) or entry.get("en") or key
    return text.format(**fmt) if fmt else text


# --- spoken/displayed coaching cues: Italian (canonical) -> English ----------
# Keys MUST match the exact strings the detectors emit (they also key the Italian
# neural WAVs). Keep them verbatim.
_CUE_EN: dict[str, str] = {
    # La voce italiana dei consigli con un valore (`Cue.voice`): in inglese si
    # parla con la traduzione di `message`, queste servono solo a non lasciare
    # la frase senza controparte (`test_every_coach_phrase_has_its_english`).
    "Blocchi davanti in più curve. Alza l'ABS di uno.":
        "You're locking the fronts in several corners. Raise the ABS by one.",
    "Pattini in uscita in più punti. Alza il TC di uno.":
        "You're spinning up on exit in several places. Raise the TC by one.",
    "Gomme troppo calde. Guida più fluido.": "Tyres too hot. Be smoother.",
    "Gomme troppo fredde. Spingi per scaldarle.":
        "Tyres too cold. Push to warm them up.",
    # events.py
    "Blocchi le ruote, alleggerisci il freno": "You're locking up, ease off the brake",
    "Pattini in uscita, dosa il gas": "Wheelspin on exit, ease the throttle",
    # balance.py
    "Sovrasterzo, in uscita apri il gas piano":
        "Oversteer, open the throttle gently on exit",
    "L'anteriore scivola, entra più piano": "The front is sliding, go in slower",
    # braking.py
    "Veleggi, passa subito dal freno al gas":
        "You're coasting, go straight from brake to throttle",
    "Resti a metà gas, aspetta e apri tutto":
        "Half throttle too long, wait then go full",
    "Molli presto il freno, tienine un filo all'inserimento":
        "Releasing too early, trail the brake to turn-in",
    # gears.py
    "Sei sul limitatore, cambia prima": "You're on the limiter, shift earlier",
    "Marcia troppo lunga, scala per avere più spinta":
        "Gear too tall, drop one for more drive",
    # advisor.py (brake-bias, static)
    "ABS già alto, blocchi davanti in più curve. "
    "Sposta il bilanciamento freni indietro.":
        "ABS already high, fronts lock in several corners. "
        "Move the brake bias rearward.",
    # analyzer.py (corner cues)
    "Qui guadagni, rifalla così": "You're gaining here, same again next lap",
    "Qui hai margine, frena più tardi": "There's room here, brake later",
    "Arrivi lungo, frena prima": "You're running deep, brake earlier",
    "Dai più gas qui": "Use more throttle here",
    "Freni troppo qui, alleggerisci": "Too much brake here, ease off",
    "Porta più velocità in curva": "Carry more speed through the corner",
    # fuel.py
    "Ultimo giro di benzina, rientra ai box": "Last lap of fuel, box now",
    # pitcall.py
    "Modifica pronta, rientra ai box a fine giro":
        "Setup change ready, box this lap",
    "Ingresso box qui davanti, rientra": "Pit entry just ahead, come in",
    "Sei ai box. Apri la pagina Ingegnere nel browser. "
    "Prepara la modifica e applicala. "
    "Ricarica il setup dal garage prima di uscire.":
        "You're in the box. Open the Engineer page in the browser. "
        "Prepare the change and apply it. "
        "Reload the setup in the garage before leaving.",
}

def _axle_en(it: str) -> str:
    return "Front" if it == "anteriori" else "Rear"


def _num_en(it: str) -> str:
    """Un numero scritto in italiano («27,3») come si scrive in inglese («27.3»)."""
    return it.replace(",", ".")


# Templated cues (f-strings in the detectors) → English. ``repl`` is either a
# regex replacement string or a callable(match) -> str for cases that remap words.
_CUE_EN_PATTERNS: list[tuple[re.Pattern, object]] = [
    # analyzer.py / fuel.py
    # Il singolare non e' un caso di bordo in nessuna delle due: il coach parla
    # da 120 ms, che si arrotondano a un decimo, e il serbatoio passa da 1 giro
    # prima di arrivare all'ultimo. Prima la tabella conosceva solo il plurale,
    # quindi «1 giro» restava in italiano e «1 decimi» diventava «1 tenths».
    (re.compile(r"^Qui perdi (\d+) decim[oi]$"),
     lambda m: f"Losing {m.group(1)} tenth{'' if m.group(1) == '1' else 's'} here"),
    (re.compile(r"^Benzina per circa (\d+) gir[oi]\.$"),
     lambda m: f"Fuel for about {m.group(1)} lap{'' if m.group(1) == '1' else 's'}."),
    # advisor.py — ABS / TC, with or without the "dal N al N+1" detail
    (re.compile(r"^Blocchi davanti in più curve\. Prova ad alzare l'ABS"
                r"(?: dal (\d+) al (\d+))?\.$"),
     lambda m: ("You're locking the fronts in several corners. Try raising the ABS"
                + (f" from {m.group(1)} to {m.group(2)}." if m.group(1) else "."))),
    (re.compile(r"^Pattini in uscita in più punti\. Prova ad alzare il TC"
                r"(?: dal (\d+) al (\d+))?\.$"),
     lambda m: ("You're spinning up on exit in several places. Try raising the TC"
                + (f" from {m.group(1)} to {m.group(2)}." if m.group(1) else "."))),
    # pressure.py — the Italian numbers carry the decimal comma
    (re.compile(r"^Gomme (anteriori|posteriori) a ([\d,]+) psi, troppo alte\. "
                r"Togli circa ([\d,]+) psi a freddo\.$"),
     lambda m: f"{_axle_en(m.group(1))} tyres at {_num_en(m.group(2))} psi, too high. "
               f"Take about {_num_en(m.group(3))} psi off cold."),
    (re.compile(r"^Gomme (anteriori|posteriori) a ([\d,]+) psi, troppo basse\. "
                r"Aggiungi circa ([\d,]+) psi a freddo\.$"),
     lambda m: f"{_axle_en(m.group(1))} tyres at {_num_en(m.group(2))} psi, too low. "
               f"Add about {_num_en(m.group(3))} psi cold."),
    # tyretemp.py
    (re.compile(r"^Gomme a (\d+) °C, troppo calde\. Stai forzando, guida più fluido\.$"),
     lambda m: f"Tyres at {m.group(1)} °C, too hot. You're overdriving, be smoother."),
    (re.compile(r"^Gomme a (\d+) °C, troppo fredde\. Spingi di più per scaldarle\.$"),
     lambda m: f"Tyres at {m.group(1)} °C, too cold. Push harder to warm them up."),
]


def cue_text(italian: str, lang: str | None = None) -> str:
    """Render a coaching cue in ``lang`` (default: the active language).

    Italian is the source; for English we translate. Unknown phrases pass through
    unchanged (a safe fallback rather than a crash)."""
    lang = lang or current_language()
    if lang != "en":
        return italian
    if italian in _CUE_EN:
        return _CUE_EN[italian]
    for pat, repl in _CUE_EN_PATTERNS:
        m = pat.match(italian)
        if m:
            return repl(m) if callable(repl) else pat.sub(repl, italian)
    return italian
