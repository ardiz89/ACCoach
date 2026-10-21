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
    # overlay
    "overlay.waiting": {"en": "waiting for the game…", "it": "in attesa del gioco…"},
    "overlay.rec": {"en": "REC ● learning the reference lap…",
                    "it": "REC ● sto imparando il giro di riferimento…"},
    # Why the coach is quiet. One per EngineState.quiet value: a gate that says
    # nothing is indistinguishable from a broken app, so each one names itself.
    "quiet.pit": {"en": "In the pits — I start at the line",
                  "it": "Ai box — parto dal traguardo"},
    "quiet.out_lap": {"en": "Out lap — I start at the line",
                      "it": "In ricognizione — parto dal traguardo"},
    "quiet.no_reference": {"en": "No reference yet — complete one clean lap",
                           "it": "Nessun riferimento — completa un giro pulito"},
    "quiet.off_pace": {"en": "Off-pace lap — I'll resume at the line",
                       "it": "Giro fuori ritmo — riprendo dal traguardo"},
    "quiet.green": {"en": "Green — flying lap", "it": "Via — giro lanciato"},
    # Not a quiet reason: the coach keeps working, only the delta goes away.
    # Says what happened AND that the lap is still worth driving, because the
    # instinct on seeing "invalidated" is to abort and go back to the pits.
    "overlay.lap_invalid": {"en": "Lap invalidated — keep driving, no delta",
                            "it": "Giro invalidato — continua, niente delta"},
    "overlay.brake": {"en": "BRAKE", "it": "FRENA"},
    "overlay.pit_due": {"en": "▶ BOX THIS LAP", "it": "▶ RIENTRA AI BOX"},
    "overlay.focus": {"en": "FOCUS", "it": "FOCUS"},
    "overlay.throttle_pedal": {"en": "THR", "it": "GAS"},
    "overlay.brake_pedal": {"en": "BRK", "it": "FRENO"},
    "overlay.trail": {"en": "TRAIL", "it": "TRAIL"},
    "overlay.coast": {"en": "COAST", "it": "COAST"},
    # terminal coach
    "coach.title": {"en": "voice coach", "it": "coach vocale"},
    "coach.no_ref": {"en": "no reference yet — drive a clean lap",
                     "it": "nessun riferimento — fai un giro pulito"},
    "coach.listening": {"en": "listening… drive and I'll coach you",
                        "it": "in ascolto… guida e ti seguo"},
    "coach.waiting": {"en": "waiting for game…", "it": "in attesa del gioco…"},
    "coach.warming": {"en": "warming up… drive a few clean laps",
                      "it": "scaldando… fai qualche giro pulito"},
    "coach.delta_title": {"en": "Delta vs reference", "it": "Delta vs riferimento"},
    "coach.delta_none": {"en": "no reference yet — drive a clean lap",
                         "it": "nessun riferimento — fai un giro pulito"},
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
    "state.waiting_game": {"en": "waiting for game…", "it": "in attesa del gioco…"},
    "voice.on": {"en": "voice", "it": "voce"},
    "voice.off": {"en": "text", "it": "testo"},
    # launcher
    "ui.language": {"en": "Language", "it": "Lingua"},
    "ui.tip_borderless": {
        "en": "Tip: set the game to Borderless so the overlay draws over it.",
        "it": "Suggerimento: imposta il gioco in Borderless così l'overlay ci si disegna sopra."},
    "btn.coach_live": {"en": "▶  Coach Live  (overlay + voice)",
                       "it": "▶  Coach Live  (overlay + voce)"},
    "btn.coach_live_demo": {"en": "▶  Coach Live — DEMO (no game)",
                            "it": "▶  Coach Live — DEMO (senza gioco)"},
    "btn.analysis": {"en": "📊  Analysis & Report (browser)",
                     "it": "📊  Analisi & Report (browser)"},
    "btn.engineer": {"en": "🔧  Race engineer (browser)",
                     "it": "🔧  Ingegnere di pista (browser)"},
    "btn.server": {"en": "📡  Live backend (second screen)",
                   "it": "📡  Backend live (secondo schermo)"},
    "btn.debrief": {"en": "📈  Last-lap debrief", "it": "📈  Debrief ultimo giro"},
    "btn.monitor": {"en": "📈  Telemetry monitor", "it": "📈  Monitor telemetria"},
    "btn.coach_term": {"en": "🎙  Voice coach (terminal)",
                       "it": "🎙  Coach vocale (terminale)"},
    "btn.verify_g": {"en": "🔧  Verify G axes", "it": "🔧  Verifica assi G"},
    "btn.get_started": {"en": "✨  Get started", "it": "✨  Come iniziare"},
    "btn.settings": {"en": "⚙  Settings", "it": "⚙  Impostazioni"},
    "btn.mobile": {"en": "📱  Phone / tablet", "it": "📱  Telefono / tablet"},
    # First-run wizard. Was hardcoded English in a bilingual app: the very first
    # screen a new driver sees ignored the language they had just chosen.
    "wiz.title": {"en": "Welcome to HONE", "it": "Benvenuto in HONE"},
    "wiz.sub": {"en": "Know why you're slow. Here's how to get going:",
                "it": "Scopri perché sei lento. Ecco come si comincia:"},
    "wiz.dont_show": {"en": "Don't show this again",
                      "it": "Non mostrarlo più"},
    "wiz.open_guide": {"en": "Open full guide", "it": "Apri la guida completa"},
    "wiz.go": {"en": "Get started", "it": "Cominciamo"},
    "wiz.s1": {
        "en": "Set your game (AC / ACC) to <b>Borderless</b> — the overlay cannot "
              "draw over exclusive fullscreen.",
        "it": "Metti il gioco (AC / ACC) in <b>Borderless</b> — sul fullscreen "
              "esclusivo l'overlay non si disegna."},
    "wiz.s2": {
        "en": "Open <b>Drive</b> in the sidebar and press <b>Coach Live</b>. The "
              "panel walks you through it: the tablet with a QR code first, "
              "then the game. When you're done, <b>I'm done</b> opens the "
              "report card.",
        "it": "Apri <b>In pista</b> nella barra laterale e premi <b>Coach "
              "Live</b>. Il pannello ti accompagna: prima il tablet col codice "
              "QR, poi il gioco. Quando hai finito, <b>Ho finito</b> apre la "
              "Pagella."},
    "wiz.s3": {
        "en": "Drive one complete lap. It becomes your <b>reference</b>, and the "
              "delta appears from the next lap on. Until then the coach still "
              "calls locks, slides and tyres — everything that doesn't need a "
              "lap to compare against.",
        "it": "Fai un giro completo. Diventa il tuo <b>riferimento</b>, e il delta "
              "compare dal giro dopo. Fino a lì il coach ti dice comunque "
              "bloccaggi, scivolate e gomme — tutto ciò che non ha bisogno di un "
              "giro con cui confrontarsi."},
    "wiz.s4": {
        "en": "After the session open <b>Analysis</b> for the corner-by-corner "
              "debrief, and <b>Setup</b> for the race engineer.",
        "it": "A fine sessione apri <b>Analisi</b> per il debrief curva per curva, "
              "e <b>Setup</b> per l'ingegnere di pista."},
    "wiz.s5": {
        "en": "No game handy? <b>Coach Live — DEMO</b> runs it all on a synthetic lap.",
        "it": "Non hai il gioco sottomano? <b>Coach Live — DEMO</b> fa girare "
              "tutto su un giro finto."},
    "btn.import_pro": {"en": "⬇  Import a PRO reference lap",
                       "it": "⬇  Importa un giro di riferimento PRO"},
    # Says what it's FOR, not what it does. The feature only makes sense once you
    # know the default reference is yourself.
    "import.hint": {
        "en": "Your reference is normally your own best lap. Import a faster "
              "one and the coach measures you against that instead.",
        "it": "Il riferimento è normalmente il tuo giro migliore. Importane uno "
              "più veloce e il coach ti misura su quello."},
    "import.done": {"en": "✓ Imported: {car} / {track} ({time})",
                    "it": "✓ Importato: {car} / {track} ({time})"},
    "import.failed": {"en": "Could not read that lap: {err}",
                      "it": "Giro illeggibile: {err}"},
    "btn.guide": {"en": "❓  Guide — how to use", "it": "❓  Guida — come si usa"},
    "btn.overlay": {"en": "🖥  Overlay only", "it": "🖥  Solo overlay"},
    # hub — sidebar navigation
    "nav.home": {"en": "  Home", "it": "  Home"},
    # "In pista" e non "Guida": in italiano collideva con «❓ Guida — come si
    # usa», e chi cercava il manuale finiva sui pulsanti di Coach Live. In
    # inglese la collisione non c'era mai stata (Drive / Guide).
    "nav.live": {"en": "  Drive", "it": "  In pista"},
    "nav.analysis": {"en": "  Analysis", "it": "  Analisi"},
    "nav.setup": {"en": "  Setup", "it": "  Setup"},
    "nav.devices": {"en": "  Devices", "it": "  Dispositivi"},
    "nav.settings": {"en": "  Settings", "it": "  Impostazioni"},
    # hub — section intros
    "sec.devtools": {"en": "Advanced tools", "it": "Strumenti avanzati"},
    # hub — Home (last session)
    "home.loading": {"en": "Loading your last session…",
                     "it": "Carico l'ultima sessione…"},
    # Terzo stato accanto a "vuoto" e "nessun riferimento": l'archivio non si
    # legge. Prima finiva su "vuoto", cioè si diceva «non hai mai guidato» a chi
    # aveva appena finito una sessione — che manda a guidare di più invece che a
    # guardare i log.
    "home.error_title": {"en": "I can't read your laps",
                         "it": "Non riesco a leggere i tuoi giri"},
    "home.error_body": {
        "en": "The lap archive didn't open — another HONE window may be using "
              "it, or a file is damaged. Settings → Logs has the details. Your "
              "laps are still on disk.",
        "it": "L'archivio dei giri non si è aperto — può usarlo un'altra "
              "finestra di HONE, o un file è danneggiato. I dettagli sono in "
              "Impostazioni → Log. I tuoi giri sono ancora sul disco."},
    "home.empty_title": {"en": "No sessions yet",
                         "it": "Nessuna sessione ancora"},
    "home.empty_body": {"en": "Get on track and drive two laps — I'll listen and "
                              "tell you where you lose time.",
                        "it": "Sali in pista e fai due giri — io ascolto e ti dico "
                              "dove perdi tempo."},
    "home.no_ref_title": {"en": "Almost there", "it": "Ci siamo quasi"},
    "home.no_ref_body": {"en": "Drive one clean, valid lap so I have a reference to "
                               "compare against.",
                         "it": "Fai un giro pulito e valido, così ho un riferimento "
                               "con cui confrontare."},
    "home.clean_title": {"en": "Clean lap", "it": "Giro pulito"},
    "home.clean_body": {"en": "Slower than your reference, but no single corner cost "
                              "you much — work on consistency to close the gap.",
                        "it": "Più lento del riferimento, ma nessuna curva ti è "
                              "costata molto — lavora sulla costanza per recuperare."},
    "home.is_reference": {"en": "This is your reference lap — nothing faster to "
                                "compare against. Nice one.",
                          "it": "Questo è il tuo giro di riferimento — niente di più "
                                "veloce da confrontare. Ottimo."},
    "home.cta_analysis": {"en": "📊  Analyze", "it": "📊  Analizza"},
    "home.cta_debrief": {"en": "📈  Full debrief", "it": "📈  Debrief completo"},
    "home.cta_setup": {"en": "🔧  Try a setup", "it": "🔧  Prova un setup"},
    "home.stat_best": {"en": "Best lap", "it": "Miglior giro"},
    "home.stat_gap": {"en": "Gap to ref", "it": "Distacco rif."},
    "home.stat_laps": {"en": "Valid laps", "it": "Giri validi"},
    "home.stat_consistency": {"en": "Spread", "it": "Costanza"},
    # phone / tablet (LAN) dialog
    "mob.title": {"en": "Open on phone / tablet", "it": "Apri su telefono / tablet"},
    "mob.lan": {"en": "Allow access from other devices on my network",
                "it": "Consenti l'accesso dagli altri dispositivi in rete"},
    "mob.report": {"en": "Report", "it": "Report"},
    "mob.engineer": {"en": "Engineer", "it": "Ingegnere"},
    "mob.test": {"en": "On-track test", "it": "Test in pista"},
    "mob.test_live": {"en": "For live cue capture on the test page, also start the "
                            "Live backend (second screen).",
                      "it": "Per la cattura dei cue dal vivo nella pagina test, avvia "
                            "anche il Backend live (secondo schermo)."},
    "mob.scan": {"en": "Scan with your phone's camera, or type the address.",
                 "it": "Inquadra col telefono, oppure digita l'indirizzo."},
    "mob.off": {"en": "Turn on the option above to open these pages from your phone.",
                "it": "Attiva l'opzione qui sopra per aprire le pagine dal telefono."},
    "mob.no_ip": {"en": "No network address found — connect this PC to Wi-Fi or LAN.",
                  "it": "Nessun indirizzo di rete — collega il PC a Wi-Fi o LAN."},
    "mob.same_net": {"en": "Your phone must be on the same Wi-Fi / network as this PC.",
                     "it": "Il telefono dev'essere sulla stessa Wi-Fi / rete del PC."},
    "mob.firewall": {"en": "If Windows asks, allow access on Private networks.",
                     "it": "Se Windows lo chiede, consenti l'accesso su reti private."},
    "mob.restart": {"en": "After changing this, (re)start Coach Live or Analysis.",
                    "it": "Dopo la modifica, (ri)avvia Coach Live o Analisi."},
    "mob.no_qr": {"en": "(QR unavailable — install 'segno')",
                  "it": "(QR non disponibile — installa 'segno')"},
    "mob.server_on": {"en": "Analysis server is running — these pages will open.",
                      "it": "Server analisi acceso: queste pagine si aprono."},
    "mob.server_off": {"en": "Analysis server is off — these pages will not load. "
                             "Start it from Analysis.",
                       "it": "Server analisi spento: queste pagine non si aprono. "
                             "Avvialo da Analisi."},
    # settings dialog
    "ui.settings": {"en": "Settings", "it": "Impostazioni"},
    "set.voice": {"en": "Coach voice", "it": "Voce del coach"},
    "set.engineer_voice": {"en": "Speak engineer proposals",
                           "it": "Annuncia proposte ingegnere"},
    "set.male_voice": {"en": "Male voice", "it": "Voce maschile"},
    "set.radio": {"en": "Team-radio effect", "it": "Effetto radio di pista"},
    "set.rate": {"en": "Reading speed (wpm)", "it": "Velocità lettura (ppm)"},
    "set.scale": {"en": "Overlay scale", "it": "Scala overlay"},
    # One "?" per setting. Reported by the user: a field named "Overlay scale"
    # or "Reading speed" means nothing to someone who didn't build it, and the
    # panel had no help text of any kind. Each answers WHAT it does and WHEN to
    # touch it — a definition alone ("scales the overlay") helps nobody.
    "set.voice.help": {
        "en": "Speaks the coaching cues out loud. Turn it off to keep the "
              "on-screen overlay only — useful in a race, or on a headset "
              "you're sharing with a voice chat.",
        "it": "Legge i consigli ad alta voce. Spegnila per tenere solo "
              "l'overlay a schermo — utile in gara, o se le cuffie le stai "
              "usando anche per parlare con qualcuno."},
    "set.engineer_voice.help": {
        "en": "Whether the race engineer's setup proposals are spoken too. "
              "They arrive between laps, not while you're driving a corner. "
              "Off means you'll still find them in the Setup section.",
        "it": "Se anche le proposte di assetto dell'ingegnere vengono dette a "
              "voce. Arrivano fra un giro e l'altro, non mentre sei in curva. "
              "Se la spegni le trovi comunque nella sezione Assetto."},
    "set.male_voice.help": {
        "en": "Picks the male voice instead of the female one. Same words, "
              "same timing — it only changes who says them.",
        "it": "Sceglie la voce maschile invece di quella femminile. Stesse "
              "parole, stessi tempi: cambia solo chi le dice."},
    "set.radio.help": {
        "en": "Filters the voice to sound like a pit-to-car radio. Purely "
              "cosmetic: it costs nothing in lap time and changes nothing in "
              "the advice. Off is the clearest.",
        "it": "Filtra la voce perché suoni come una radio di pista. È solo "
              "estetica: non cambia una virgola dei consigli. Spenta è la più "
              "comprensibile."},
    "set.rate.help": {
        "en": "How fast the voice talks, in words per minute. Around 165 is "
              "normal speech. Raise it if cues arrive too late in fast "
              "corners; lower it if you're missing words.",
        "it": "Quanto in fretta parla la voce, in parole al minuto. Intorno a "
              "165 è il parlato normale. Alzala se nelle curve veloci i "
              "consigli arrivano tardi, abbassala se ti perdi delle parole."},
    # Auto-record: the only setting that makes HONE do something without being
    # pressed, so the help says exactly what starts (and what doesn't).
    "set.autorecord": {"en": "Record by itself when the game starts",
                       "it": "Registra da solo quando parte il gioco"},
    "set.autorecord.help": {
        "en": "With the hub open, HONE notices AC/ACC appearing and starts "
              "recording your laps on its own — so a session you forgot to arm "
              "isn't a session you lost. It starts the silent recorder only: "
              "the voice and the overlay stay off until you press Coach Live. "
              "Off by default.",
        "it": "Con l'hub aperto, HONE si accorge che AC/ACC è partito e comincia "
              "a registrare i tuoi giri da solo — così una sessione che hai "
              "dimenticato di avviare non è una sessione persa. Parte solo la "
              "registrazione silenziosa: voce e overlay restano spenti finché "
              "non premi Coach Live. Di default è spenta.",
    },
    "watch.waiting": {"en": "listening — waiting for the game",
                      "it": "in ascolto — aspetto il gioco"},
    "watch.recording": {"en": "the game is here — starting the recorder",
                        "it": "il gioco c'è — avvio la registrazione"},
    "watch.busy": {"en": "already recording", "it": "sto già registrando"},
    "set.wean": {"en": "Retire braking markers", "it": "Ritira i segnali di frenata"},
    "set.wean.help": {
        "en": "As you master a corner, the braking countdown stops appearing "
              "there — the way you peel the racing line and braking boards away "
              "one at a time once you know a track. Off keeps them at every "
              "corner forever.",
        "it": "Man mano che domini una curva, il conto alla rovescia della "
              "frenata smette di comparire lì — come togli la traiettoria e i "
              "cartelli di frenata uno alla volta quando impari un tracciato. "
              "Spento li tiene a ogni curva per sempre."},
    # Un pulsante spento senza motivo si legge come un guasto. Questo compare
    # come suggerimento su tutto ciò che registra, quando qualcos'altro già lo fa.
    "btn.busy_recording": {
        "en": "Something is already recording this session. Two recorders save "
              "every lap twice, and the copy looks exactly like a real extra lap "
              "— stop the one that's running first.",
        "it": "Qualcosa sta già registrando questa sessione. Due registratori "
              "salvano ogni giro due volte, e la copia è identica a un giro vero "
              "in più — ferma prima quello acceso."},
    # --- lo scambio Coach Live → Backend live ------------------------------
    # Il Backend live non può stare acceso insieme a Coach Live. Finché queste
    # frasi non c'erano, il bottone era spento e muto. Dal 24/09 la pagina
    # Ingegnere la alimenta anche Coach Live, quindi le frasi dicono pure
    # questo: chi è arrivato qui cercando la pagina non ha bisogno dello scambio.
    "swap.title": {
        "en": "The live backend can't run next to Coach Live",
        "it": "Il Backend live non può girare insieme a Coach Live"},
    "swap.why": {
        "en": "The live backend records laps exactly like Coach Live does. "
              "With both of them running, every lap you drive is saved twice — "
              "and the copy looks exactly like a real extra lap, so afterwards "
              "there is no telling them apart. If you're here for the Engineer "
              "page you don't need it: while Coach Live runs, Coach Live feeds "
              "that page itself.",
        "it": "Il Backend live registra i giri esattamente come fa Coach Live. "
              "Accesi tutti e due, ogni giro che guidi viene salvato due volte "
              "— e la copia è identica a un giro vero in più, quindi dopo non "
              "si distinguono. Se sei qui per la pagina Ingegnere non ti "
              "serve: finché Coach Live è acceso, quella pagina la alimenta "
              "lui."},
    "swap.warn": {
        "en": "Swapping stops Coach Live and starts the live backend in its "
              "place: the coach still talks and the Engineer page stays fed, "
              "but the overlay closes with Coach Live — no HUD on track. The "
              "live backend is three separate pieces (backend, overlay, web "
              "page), not one package: you can bring the overlay back from "
              "Devices, on its own.",
        "it": "Lo scambio ferma Coach Live e avvia al suo posto il Backend "
              "live: il coach parla lo stesso e la pagina Ingegnere resta "
              "alimentata, ma l'overlay si spegne insieme a Coach Live — in "
              "pista niente HUD. Il Backend live sono tre pezzi separati "
              "(backend, overlay, pagina web), non un pacchetto solo: "
              "l'overlay lo riaccendi da Dispositivi, per conto suo."},
    # Senza glifo: `⇄` (U+21C4) non c'è nei font del brand né nel ripiego di
    # sistema, e a schermo usciva come un rettangolo vuoto davanti alla frase.
    "swap.confirm": {"en": "Stop Coach Live and switch",
                     "it": "Ferma Coach Live e passa"},
    # Etichette corte di proposito: tre bottoni con frasi intere spingevano la
    # finestra a 685 px in italiano, cioè righe lunghe e faticose. Cosa fa
    # ciascuna uscita lo dicono i paragrafi sopra, non il bottone.
    "swap.cancel": {"en": "Cancel", "it": "Annulla"},
    "swap.failed": {
        "en": "Coach Live is still running, so the live backend was NOT "
              "started — two recorders would have saved every lap twice. Press "
              "“Stop without opening the report”, wait for its window to close, "
              "and try again.",
        "it": "Coach Live sta ancora girando, quindi il Backend live NON è "
              "stato avviato — due registratori avrebbero salvato ogni giro "
              "due volte. Premi «Ferma senza aprire il report», aspetta che la "
              "sua finestra si chiuda, e riprova."},
    "swap.tooltip": {
        "en": "Coach Live is running. Click to read why this can't start "
              "alongside it — and to swap over in one step.",
        "it": "Coach Live è acceso. Premi per leggere perché questo non può "
              "partirgli accanto — e per fare lo scambio in un passo."},
    "set.pedals": {"en": "Show the pedal trace", "it": "Mostra la traccia dei pedali"},
    "set.pedals.help": {
        "en": "A strip under the overlay with your throttle (green) and brake "
              "(red) as they happen. The ribbon under it turns amber while both "
              "pedals are down — that's trail braking — and grey while neither "
              "is, which is time you're giving away. It's the only place you "
              "can watch your brake release as you do it, instead of being told "
              "about it afterwards.",
        "it": "Una striscia sotto l'overlay col tuo gas (verde) e il tuo freno "
              "(rosso) mentre succedono. Il nastro sotto diventa ambra finché "
              "premi tutti e due i pedali — è il trail braking — e grigio "
              "quando non ne premi nessuno, che è tempo regalato. È l'unico "
              "posto dove vedi il rilascio del freno **mentre** lo fai, invece "
              "di sentirtelo raccontare dopo."},
    "set.pedals_hint": {
        "en": "Makes the overlay taller. Applies on the next Coach Live start.",
        "it": "Allunga l'overlay. Attivo al prossimo avvio di Coach Live."},
    "set.scale.help": {
        "en": "How big the overlay is drawn on screen. 1.0 is the design size; "
              "raise it on a 4K monitor or if you sit far from the screen, "
              "lower it if it covers too much track.",
        "it": "Quanto è grande l'overlay a schermo. 1.0 è la dimensione di "
              "progetto: alzala su un monitor 4K o se stai lontano, abbassala "
              "se ti copre troppa pista."},
    "set.scale_hint": {"en": "Applies on the next Coach Live start.",
                       "it": "Attivo al prossimo avvio di Coach Live."},
    "btn.save": {"en": "Save", "it": "Salva"},
    "btn.cancel": {"en": "Cancel", "it": "Annulla"},
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
    "live.s2": {"en": "Connect your tablet to the engineer",
                "it": "Collega il tablet all'ingegnere"},
    "live.s2_scan": {"en": "Scan the code with the tablet's camera, or open {addr}.",
                     "it": "Inquadra il codice con la fotocamera del tablet, "
                           "oppure apri {addr}."},
    "live.s2_lan_off": {
        "en": "The tablet can only connect with network access on.",
        "it": "Il tablet si collega solo con la rete locale attiva."},
    "live.s2_to_devices": {"en": "Turn on network access",
                           "it": "Attiva la rete locale"},
    "live.s2_no_ip": {
        "en": "This PC has no network address. Connect it to Wi-Fi or a cable.",
        "it": "Questo PC non ha un indirizzo di rete. Collegalo al Wi-Fi o al cavo."},
    "live.s2_web_down": {
        "en": "The Engineer page isn't answering. Open it on this PC, or "
              "restart Coach Live.",
        "it": "La pagina Ingegnere non risponde. Aprila su questo PC, o "
              "riavvia Coach Live."},
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
    "live.following": {"en": "You're working on: {name}",
                       "it": "Stai seguendo: {name}"},
    "live.following_sub": {
        "en": "The coach reminds you in the corners of this advice.",
        "it": "Il coach te lo ricorda nelle curve di questo consiglio."},
    "live.finish": {"en": "I'm done, show me how it went",
                    "it": "Ho finito, mostrami com'è andata"},
    "live.finish_sub": {"en": "Stops the coach and opens the report card.",
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
    "live.closed": {
        "en": "The game has been closed for a minute. The coach stays on until "
              "you stop it, in case you're only changing track.",
        "it": "Il gioco è chiuso da un minuto. Il coach resta acceso finché non "
              "lo fermi tu, nel caso tu stia solo cambiando pista."},
    "live.show": {"en": "Show me how it went", "it": "Mostrami com'è andata"},
    "live.stay": {"en": "I'm staying on track", "it": "Resto in pista"},
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
    # events.py
    "Bloccaggio, alleggerisci il freno": "Lock-up — ease off the brake",
    "Pattini in uscita, meno gas": "Wheelspin on exit — less throttle",
    # balance.py
    "Sovrasterzo, sii più dolce col gas in uscita":
        "Oversteer — smoother on the throttle out",
    "L'anteriore scivola, entra più piano": "Front washing out — slower on entry",
    # braking.py
    "Stai veleggiando: riduci il tempo morto fra freno e gas":
        "Coasting — close the gap between brake and throttle",
    "Rilasci il freno troppo presto: portane un filo fino all'inserimento":
        "Releasing the brake too early — trail a little to turn-in",
    # gears.py
    "Sei sul limitatore, cambia prima": "On the limiter — shift earlier",
    "Marcia troppo lunga, scala per avere più spinta":
        "Gear too tall — drop one for more drive",
    # advisor.py (brake-bias, static)
    "Blocchi l'anteriore in più curve e l'ABS è già alto: "
    "prova a spostare il bilanciamento freni verso il posteriore.":
        "Locking the fronts in several corners and ABS is already high: "
        "try moving brake bias rearward.",
    # analyzer.py (corner cues)
    "Bel tratto, continua così": "Good through there, keep it up",
    "Puoi frenare più tardi": "You can brake later",
    "Più gas qui": "More throttle here",
    "Stai frenando troppo, alleggerisci": "Braking too much — ease off",
    "Porta più velocità in curva": "Carry more speed through the corner",
    # fuel.py
    "Ultimo giro di benzina, rientra ai box!": "Last lap of fuel — box now!",
    # pitcall.py
    "Modifica pronta: rientra ai box a fine giro":
        "Change ready — box this lap",
    "Ingresso box qui davanti, rientra": "Pit entry just ahead — come in",
    "Sei ai box. Apri la pagina Ingegnere nel browser: applica la "
    "proposta, scrivi il setup e ricaricalo dal garage prima di uscire":
        "You're in the box. Open the Engineer page in the browser: apply the "
        "proposal, write the setup, and load it from the garage before you go out",
}

def _axle_en(it: str) -> str:
    return "Front" if it == "anteriori" else "Rear"


# Templated cues (f-strings in the detectors) → English. ``repl`` is either a
# regex replacement string or a callable(match) -> str for cases that remap words.
_CUE_EN_PATTERNS: list[tuple[re.Pattern, object]] = [
    # analyzer.py / fuel.py
    # Il singolare non e' un caso di bordo in nessuna delle due: il coach parla
    # da 120 ms, che si arrotondano a un decimo, e il serbatoio passa da 1 giro
    # prima di arrivare all'ultimo. Prima la tabella conosceva solo il plurale,
    # quindi «1 giro» restava in italiano e «1 decimi» diventava «1 tenths».
    (re.compile(r"^Stai perdendo (\d+) decim[oi] qui$"),
     lambda m: f"Losing {m.group(1)} tenth{'' if m.group(1) == '1' else 's'} here"),
    (re.compile(r"^Benzina per circa (\d+) gir[oi]\.$"),
     lambda m: f"Fuel for about {m.group(1)} lap{'' if m.group(1) == '1' else 's'}."),
    # advisor.py — ABS / TC, with or without the "(dal N al N+1)" detail
    (re.compile(r"^Blocchi l'anteriore in più curve: prova ad alzare l'ABS"
                r"(?: \(dal (\d+) al (\d+)\))?\.$"),
     lambda m: ("Locking the fronts in several corners: try raising the ABS"
                + (f" (from {m.group(1)} to {m.group(2)})." if m.group(1) else "."))),
    (re.compile(r"^Pattini in uscita in più punti del giro: prova ad alzare il TC"
                r"(?: \(dal (\d+) al (\d+)\))?\.$"),
     lambda m: ("Spinning up on exit in several places: try raising the TC"
                + (f" (from {m.group(1)} to {m.group(2)})." if m.group(1) else "."))),
    # pressure.py
    (re.compile(r"^Gomme (anteriori|posteriori) a ([\d.]+) psi, troppo alte: "
                r"cala circa ([\d.]+) psi a freddo\.$"),
     lambda m: f"{_axle_en(m.group(1))} tyres at {m.group(2)} psi, too high: "
               f"drop about {m.group(3)} psi cold."),
    (re.compile(r"^Gomme (anteriori|posteriori) a ([\d.]+) psi, troppo basse: "
                r"alza circa ([\d.]+) psi a freddo\.$"),
     lambda m: f"{_axle_en(m.group(1))} tyres at {m.group(2)} psi, too low: "
               f"add about {m.group(3)} psi cold."),
    # tyretemp.py
    (re.compile(r"^Gomme troppo calde \((\d+)°C\): stai forzando, "
                r"cerca di essere più fluido\.$"),
     lambda m: f"Tyres too hot ({m.group(1)}°C): you're overdriving — be smoother."),
    (re.compile(r"^Gomme fredde \((\d+)°C\): puoi spingere di più "
                r"per portarle in temperatura\.$"),
     lambda m: f"Tyres cold ({m.group(1)}°C): push harder to bring them up to temperature."),
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
