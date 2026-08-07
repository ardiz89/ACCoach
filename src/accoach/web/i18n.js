"use strict";
// HONE i18n — tiny, vanilla, 100% offline (no CDN, no libraries, no build step).
//
//   window.HoneI18n = { lang, t(key), set(lang) }
//
// `lang` is read from localStorage.hone_lang (default "en"). `t(key)` returns the
// string in the active language, falling back EN -> key. Static UI is tagged in
// the HTML with data-i18n* attributes; applyStatic() walks the DOM and fills them.
// Strings injected by app.js / engineer.js / tour.js call HoneI18n.t(key) directly.
//
// IMPORTANT: this file only covers UI "chrome". Backend-generated content
// (debrief why/fix, engineer rationale, focus messages, level labels) is NOT
// translated here — it will be localised on the Python side; the pages already
// pass &lang=<lang> to /api so those land in the right language when ready.
(function () {
  var STORE = "hone_lang";
  var SUPPORTED = ["en", "it"];

  // ---- catalogue: {key: {en, it}} -----------------------------------------
  // Values that contain markup use backticks so quotes/apostrophes are safe.
  var CAT = {
    // shared chrome
    "lang.label":      { en: `Language`, it: `Lingua` },
    "tour.help":       { en: `Guided tour`, it: `Visita guidata` },
    "nav.guide":       { en: `Guide`, it: `Guida` },
    // Buttons of the coachmark overlay itself (tour.js reads these directly).
    "tour.btn.skip":   { en: `Skip`, it: `Salta` },
    "tour.btn.back":   { en: `Back`, it: `Indietro` },
    "tour.btn.next":   { en: `Next`, it: `Avanti` },
    "tour.btn.done":   { en: `Done`, it: `Ho capito` },
    "tour.btn.step":   { en: `Step`, it: `Passo` },
    "cb.label":        { en: `Colour-blind palette (blue/orange)`, it: `Palette daltonici (blu/arancio)` },
    "demo.banner":     { en: `DEMO — synthetic laps, not your real data`, it: `DEMO — giri sintetici, non i tuoi dati reali` },

    // ---- analysis page (index.html) ----
    "title.analysis":  { en: `HONE · Analysis`, it: `HONE · Analisi` },
    "app.subtitle":    { en: `· Analysis`, it: `· Analisi` },
    "ctl.combo":       { en: `Car / Track`, it: `Auto / Pista` },
    "ctl.lap":         { en: `Lap to review`, it: `Giro da rivedere` },
    "ctl.baseline":    { en: `Compare with`, it: `Confronta con` },
    "ctl.export":      { en: `Export`, it: `Esporta` },

    // How the run went — the door onto the report. `gain_avg_s` is measured
    // against the best lap of THIS run, not the elected reference, and is not
    // the gap the timing screen publishes: it is the sum of its own parts.
    "tab.recap":       { en: `How it went`, it: `Com'è andata` },
    // "gap" is deliberately never used here: it's the word a driver checks
    // against the timing screen, and this number is not that (see the recap
    // spec — up to a tenth apart). It points at the total above it instead.
    "recap.where":     { en: `Where the time went <small>(average per lap · the parts add up to the number above)</small>`,
                         it: `Dove è finito il tempo <small>(media per giro · le parti sommano al numero qui sopra)</small>` },
    "recap.laps":      { en: `Lap by lap <small>(against your best lap of this run)</small>`,
                         it: `Giro per giro <small>(contro il tuo miglior giro di questa uscita)</small>` },
    "recap.best":      { en: `Best lap of this run`, it: `Miglior giro di questa uscita` },
    "recap.gain":      { en: `To gain, on average`, it: `Da guadagnare, in media` },
    "recap.yardstick": { en: `your yardstick`, it: `il tuo metro` },
    // `!cur`: no session at all for this car+track (or the fetch failed) —
    // same fact the Session tab states about the very same payload.
    "recap.nolaps":    { en: `No laps recorded for this car and track yet.`,
                         it: `Nessun giro registrato per questa auto e questa pista.` },
    // `cur` exists but `cur.recap` doesn't: `_recap_of` (api.py) returns None
    // for seven different reasons — a single valid lap is only one of them
    // (an unreadable best lap, a best lap the reference can't use, no lap
    // that could be cut into phases, ...). Naming "one valid lap" here would
    // often be naming the wrong cause, which is worse than a generic one.
    "recap.none":      { en: `Not enough in this run to measure yet.`,
                         it: `Non c'è ancora abbastanza in questa uscita per misurarlo.` },
    // The one cause of an empty recap that is measured rather than guessed
    // (`recap_clock_broken` in the payload, decided by the guard in trends.py):
    // the run's own best lap — the yardstick every row would be measured
    // against — carries a clock that doesn't account for the lap it drove, so
    // every gap taken against it would be wrong by that much.
    // No direction in the wording, on purpose: the criterion in trends.py is
    // symmetric, and the real yardstick that trips it (Red Bull Ring, 02/08)
    // has its clock running 694 ms LONG, not short. "Missing part of the lap"
    // would send the driver hunting a gap in the recording that isn't there.
    // And it says the recording doesn't line up, not that the driver did
    // anything.
    "recap.clock":     { en: `This run can't be measured: the recorded time of your best lap doesn't match the stretch of lap it covers, so every gap measured against it would be wrong.`,
                         it: `Questa uscita non si può misurare: il tempo registrato del tuo miglior giro non corrisponde al giro che copre, e ogni distacco misurato su di lui sarebbe sbagliato.` },
    "recap.phase.entry":  { en: `Entry`, it: `Entrata` },
    "recap.phase.apex":   { en: `Apex`, it: `Apice` },
    "recap.phase.exit":   { en: `Exit`, it: `Uscita` },
    "recap.phase.after":  { en: `After`, it: `Dopo` },
    "recap.phase.launch": { en: `Launch`, it: `Lancio` },

    "tab.flow":        { en: `Lap explained`, it: `Il giro spiegato` },
    // "Start here" moved to tour.a12 when the recap became the landing tab —
    // this step still opens Flow, so its own title now names what it is
    // rather than claiming to be the door.
    "tour.a9.t":       { en: `Lap explained`, it: `Il giro spiegato` },
    "tour.a9.x":       { en: `The lap, explained one thing at a time: what cost you the most, why, and what to do about it — with the chart that shows it. The other tabs are the same findings, laid out for you to read yourself.`,
                         it: `Il giro spiegato una cosa alla volta: cosa ti è costato di più, perché, e cosa farci — col grafico che lo mostra. Le altre schede sono gli stessi dati, messi lì perché te li legga da solo.` },
    "tour.a12.t":      { en: `Start here`, it: `Parti da qui` },
    "tour.a12.x":      { en: `How the run went, before it's forgotten: where you left time on average, and lap by lap against your own best of the day — not a score, five numbers that add back up to the one above them. The tabs after this go deeper, one lap at a time.`,
                         it: `Com'è andata l'uscita, prima di dimenticarla: dove hai lasciato tempo in media, e giro per giro contro il tuo stesso migliore di oggi — non un voto, cinque numeri che sommano al numero sopra di loro. Le schede dopo entrano nel dettaglio, un giro alla volta.` },
    "tab.session":     { en: `Session`, it: `Sessione` },
    "tab.compare":     { en: `Compare`, it: `Confronto` },
    // One run of laps, as it was driven.
    "ses.which":       { en: `Session`, it: `Sessione` },
    "ses.none":        { en: `No laps recorded for this car and track yet.`,
                         it: `Nessun giro registrato per questa auto e questa pista.` },
    "ses.sub":         { en: `{laps} {laps|lap|laps} · {valid} that {valid|counts|count} · {mins} min`,
                         it: `{laps} {laps|giro|giri} · {valid} che {valid|conta|contano} · {mins} min` },
    "ses.sub_temp":    { en: `track {from}° → {to}°`, it: `asfalto {from}° → {to}°` },
    "ses.best":        { en: `Best`, it: `Migliore` },
    "ses.mean":        { en: `Average`, it: `Media` },
    "ses.spread":      { en: `Consistency`, it: `Costanza` },
    "ses.vsprev":      { en: `vs previous session`, it: `vs sessione precedente` },
    "ses.fuel":        { en: `Fuel per lap`, it: `Benzina al giro` },
    "ses.laps":        { en: `Your laps`, it: `I tuoi giri` },
    "ses.lap_best":    { en: `best`, it: `migliore` },
    "ses.lap_out":     { en: `didn't count`, it: `non conta` },
    "ses.lap_cut":     { en: `off track`, it: `fuori pista` },
    "ses.open":        { en: `Open this lap in Compare`, it: `Apri questo giro in Confronto` },
    "ses.changed":     { en: `What changed since last time`, it: `Cosa è cambiato dall'ultima volta` },
    "ses.improved":    { en: `Faster here`, it: `Qui vai più forte` },
    "ses.regressed":   { en: `Slower here`, it: `Qui hai perso` },
    "ses.first":       { en: `This is the first session on this car and track — nothing to compare it with yet.`,
                         it: `È la prima sessione su questa auto e questa pista: non c'è ancora niente con cui confrontarla.` },
    "ses.nomoves":     { en: `No corner moved enough to be worth reporting.`,
                         it: `Nessuna curva si è mossa abbastanza da valere una segnalazione.` },
    "ses.nobest":      { en: `No lap of this session could count — nothing to measure.`,
                         it: `Nessun giro di questa sessione poteva contare: non c'è niente da misurare.` },
    // Race pace: one run on one tank. The wording is careful on purpose — every
    // number on this tab is the NET of fuel burning off and tyres giving up, so
    // nothing here is allowed to be called degradation.
    "tab.stint":       { en: `Race pace`, it: `Passo gara` },
    "st.which":        { en: `Stint`, it: `Stint` },
    "st.none":         { en: `No laps recorded for this car and track yet.`,
                         it: `Nessun giro registrato per questa auto e questa pista.` },
    "st.chart":        { en: `Pace across the stint <small>(each point = a lap · faded = not running pace · the line is the fitted drift)</small>`,
                         it: `Il passo lungo lo stint <small>(ogni punto è un giro · sbiaditi = non a passo · la retta è la deriva misurata)</small>` },
    "st.sub":          { en: `{laps} {laps|lap|laps} · {counted} at pace · {mins} min`,
                         it: `{laps} {laps|giro|giri} · {counted} a passo · {mins} min` },
    "st.sub_fuel":     { en: `{from} → {to} L`, it: `{from} → {to} L` },
    "st.pace":         { en: `Pace`, it: `Passo` },
    "st.best":         { en: `Best`, it: `Migliore` },
    "st.spread":       { en: `Spread`, it: `Dispersione` },
    "st.drift":        { en: `Drift`, it: `Deriva` },
    "st.flat":         { en: `flat`, it: `piatta` },
    "st.fuel":         { en: `Fuel per lap`, it: `Benzina al giro` },
    "st.range":        { en: `Laps left in the tank`, it: `Giri rimasti nel serbatoio` },
    "st.laps":         { en: `The laps of this stint`, it: `I giri di questo stint` },
    "st.lap_off":      { en: `not at pace`, it: `non a passo` },
    "st.notes":        { en: `What these numbers do and don't say`,
                         it: `Cosa dicono e cosa non dicono questi numeri` },
    "st.unverified":   { en: `unverified`, it: `non verificato` },
    "st.nopace":       { en: `No lap of this stint was running a pace — nothing to measure.`,
                         it: `Nessun giro di questo stint era a passo: non c'è niente da misurare.` },
    // The guided flow: one finding at a time, with the chart that shows it.
    "flow.prev":       { en: `← Back`, it: `← Indietro` },
    "flow.next":       { en: `Next →`, it: `Avanti →` },
    "flow.done":       { en: `That's all`, it: `Finito` },
    "flow.whole":      { en: `Show the whole chart`, it: `Mostrami il grafico intero` },
    "flow.step":       { en: `Step {n} of {total}`, it: `Passo {n} di {total}` },
    "flow.cost":       { en: `You lose {s} s here — more than anywhere else`,
                         it: `Qui perdi {s} s — più che in qualunque altro punto` },
    "flow.cost_more":  { en: `{s} s lost here`, it: `Qui perdi {s} s` },
    "flow.fix":        { en: `What to do`, it: `Cosa fare` },
    "flow.empty":      { en: `Pick a lap to see it explained.`,
                         it: `Scegli un giro per vederlo spiegato.` },
    "flow.chart.speed":  { en: `Speed — white = you, cyan = reference`,
                           it: `Velocità — bianco = tu, ciano = riferimento` },
    "flow.chart.inputs": { en: `Throttle and brake — solid = you, dashed = reference`,
                           it: `Gas e freno — pieno = tu, tratteggio = riferimento` },
    "flow.chart.delta":  { en: `Gap across the lap — above the line = slower`,
                           it: `Distacco sul giro — sopra la linea = più lento` },
    "tab.map":         { en: `Map`, it: `Mappa` },
    "tab.sectors":     { en: `Sectors`, it: `Settori` },
    "tab.dynamics":    { en: `Dynamics`, it: `Dinamica` },
    "tab.trends":      { en: `Trends`, it: `Andamento` },

    // ---- dynamics tab (G-G, lock/spin, coasting) ----
    "dyn.readout":     { en: `Hover the traces for point-by-point values…`,
                         it: `Passa il mouse sui grafici per i valori punto per punto…` },
    "chart.gg":        { en: `Grip usage · G-G <small>(each dot = a moment · far from centre = more grip used · the ring = your peak)</small>`,
                         it: `Uso del grip · G-G <small>(ogni punto = un istante · lontano dal centro = più grip usato · l'anello = il tuo picco)</small>` },
    "chart.slip":      { en: `Lock &amp; spin <small>(slip ratio · cyan = front, amber = rear · below 0 = locking, above = spinning · the bar underneath = ABS/TC working)</small>`,
                         it: `Bloccaggio e pattinamento <small>(slip ratio · ciano = ant, arancio = post · sotto 0 = bloccaggio, sopra = pattinamento · la barretta in basso = ABS/TC che intervengono)</small>` },
    "dyn.missing":     { en: `This lap has no dynamics data (G / slip were recorded from v6). Drive and record a new lap to see it here.`,
                         it: `Questo giro non ha dati di dinamica (G / slip registrati dalla v6). Guida e registra un nuovo giro per vederli qui.` },
    // NON «in folle»: in italiano vuol dire cambio in posizione neutra, che è
    // un'altra cosa da quella che il canale misura (né gas né freno, marcia
    // inserita). Il termine inglese resta perché è quello che il pilota sente
    // dire, con la glossa che dice cosa significa davvero.
    "dyn.coasting":    { en: `Coasting`, it: `Coasting (né gas né freno)` },
    "dyn.trail":       { en: `Trail-braking`, it: `Trail-braking` },
    "dyn.gmax":        { en: `Peak grip`, it: `Grip di picco` },
    "dyn.ofLap":       { en: `of the lap`, it: `del giro` },
    "dyn.hint":        { en: `time with neither brake nor throttle — dead time to reclaim`,
                         it: `tempo senza freno né gas — tempo morto da recuperare` },
    "dyn.gg.accel":    { en: `accel`, it: `accel.` },
    "dyn.gg.brake":    { en: `brake`, it: `freno` },
    "dyn.gg.lat":      { en: `lateral`, it: `laterale` },
    "dyn.slip.spin":   { en: `spin`, it: `spin` },
    "dyn.slip.lock":   { en: `lock`, it: `blocco` },
    "dyn.ro.g":        { en: `G`, it: `G` },
    "dyn.ro.lat":      { en: `lat`, it: `lat` },
    "dyn.ro.lon":      { en: `lon`, it: `lon` },
    "dyn.ro.slipF":    { en: `Slip front`, it: `Slip ant` },
    "dyn.ro.slipR":    { en: `Slip rear`, it: `Slip post` },
    // Il grafico che stava in Dinamica è stato rimosso il 05/08: era lo
    // stesso canale della Traiettoria, con una didascalia che si rifiutava
    // di dire da che parte. Restano il rimando e il bottone.
    "lineoff.elsewhere": { en: `Line deviation lives under Line, which also says which side.`,
                         it: `Lo scostamento dalla traiettoria vive sotto Traiettoria, che dice anche da che parte.` },
    "lineoff.goto":    { en: `Open Line`, it: `Apri Traiettoria` },
    "dyn.tyre.header": { en: `Tyres across this lap <small>(core temp &amp; pressure corner by corner · dashed = right side)</small>`,
                         it: `Gomme lungo questo giro <small>(temp mescola e pressione curva per curva · tratteggio = lato destro)</small>` },
    "chart.balance":   { en: `Balance ribbon <small>(racing line coloured by handling · blue = understeer, red = oversteer)</small>`,
                         it: `Nastro bilanciamento <small>(traiettoria colorata per comportamento · blu = sottosterzo, rosso = sovrasterzo)</small>` },
    "bal.under":       { en: `understeer`, it: `sottosterzo` },
    "bal.over":        { en: `oversteer`, it: `sovrasterzo` },
    "dyn.ro.off":      { en: `Off line`, it: `Fuori linea` },
    "dyn.ro.bal":      { en: `Balance`, it: `Bilanciamento` },

    "prog.consistency":{ en: `Corner consistency <small>(spread of your min speed per corner · wider = less repeatable)</small>`,
                         it: `Costanza per curva <small>(dispersione della velocità minima per curva · più larga = meno ripetibile)</small>` },
    "cons.none":       { en: `Not enough laps yet to measure corner consistency.`,
                         it: `Ancora troppi pochi giri per misurare la costanza per curva.` },
    "cons.spread":     { en: `spread`, it: `dispersione` },

    "chart.yaw":       { en: `Rotation vs steering <small>(orange = yaw/rotation, white = steering · they should track together)</small>`,
                         it: `Rotazione vs sterzo <small>(arancio = imbardata/rotazione, bianco = sterzo · dovrebbero seguirsi)</small>` },
    "chart.rpm":       { en: `Revs &amp; shift points <small>(rpm across the lap · ▲ = upshift, ▼ = downshift)</small>`,
                         // «scalata su» è una contraddizione: in italiano
                         // scalare vuol dire già scendere di marcia.
                         it: `Giri motore e cambiate <small>(rpm lungo il giro · ▲ = cambiata su, ▼ = scalata)</small>` },
    "wf.title":        { en: `Where the lap went <small>(time lost per corner, biggest first)</small>`,
                         it: `Dov'è finito il giro <small>(tempo perso per curva, dal peggiore)</small>` },
    "dyn.smooth":      { en: `Steering reversals`, it: `Correzioni sterzo` },
    "dyn.smoothUnit":  { en: `direction changes`, it: `cambi di direzione` },

    "readout.hint":    { en: `Hover over the charts for point-by-point values…`,
                         it: `Passa il mouse sui grafici per i valori punto per punto…` },

    "chart.delta":     { en: `Lap delta <small>(s · above the line = slower, below = faster)</small>`,
                         it: `Delta sul giro <small>(s · sopra la linea = più lento, sotto = più veloce)</small>` },
    "chart.speed":     { en: `Speed <small>(km/h · white = reviewed lap, cyan = comparison)</small>`,
                         it: `Velocità <small>(km/h · bianco = giro in esame, ciano = confronto)</small>` },
    "chart.inputs":    { en: `Throttle / Brake <small>(green = throttle, red = brake · dashed = reference)</small>`,
                         it: `Gas / Freno <small>(verde = gas, rosso = freno · tratteggio = riferimento)</small>` },
    "chart.steer":     { en: `Steering <small>(white = reviewed lap, cyan = comparison · left up / right down)</small>`,
                         it: `Sterzo <small>(bianco = giro in esame, ciano = confronto · sinistra su / destra giù)</small>` },

    "map.readout":     { en: `Racing line · colour = speed vs reference (red = slower here, green = faster) · thicker line = bigger gap · ▽ your braking · ○ reference braking`,
                         it: `Traiettoria · colore = velocità vs riferimento (rosso = qui più lento, verde = più veloce) · linea più spessa = scarto maggiore · ▽ tua frenata · ○ frenata di riferimento` },
    "chart.map":       { en: `Track map <small>(white dashed = reference · solid line = reviewed lap)</small>`,
                         it: `Mappa pista <small>(tratteggio bianco = riferimento · linea continua = giro in esame)</small>` },
    "map.grad.fast":   { en: `faster`, it: `più veloce` },
    "map.grad.slow":   { en: `slower`, it: `più lento` },
    "map.grad.note":   { en: `line thickens with the speed gap`,
                         it: `la linea si ispessisce con lo scarto di velocità` },
    "map.leg.you":     { en: `your braking`, it: `tua frenata` },
    "map.leg.ref":     { en: `reference braking`, it: `frenata di riferimento` },
    "map.missing":     { en: `This lap has no coordinates (recorded before the map update). Drive and record a new lap to see it here.`,
                         it: `Questo giro non ha coordinate (registrato prima dell'aggiornamento mappa). Guida e registra un nuovo giro per vederlo qui.` },
    "rail.nomap":      { en: `This lap has no map (recorded before the coordinates arrived). The corners below still work.`,
                         it: `Questo giro non ha mappa (registrato prima delle coordinate). Le curve qui sotto funzionano lo stesso.` },
    "rail.whole":      { en: `Whole lap`, it: `Tutto il giro` },
    "rail.clean":      { en: `nothing lost here`, it: `qui non hai perso niente` },

    // ---- braking sheet (under the track map) ----
    // Your own braking points, measured. The wording carries the caveats the
    // static sheets going round the forums don't: how many laps, which asphalt
    // temperature, and that the metres are an approximation.
    "brk.title":       { en: `Your braking points`, it: `Le tue frenate` },
    "brk.sub":         { en: `measured on your last {laps} {laps|lap|laps}`,
                         it: `misurate sui tuoi ultimi {laps} {laps|giro|giri}` },
    "brk.temp":        { en: `track {from}° → {to}°`, it: `asfalto {from}° → {to}°` },
    "brk.temp1":       { en: `track {from}°`, it: `asfalto {from}°` },
    "brk.noTemp":      { en: `track temperature not recorded on these laps`,
                         it: `temperatura asfalto non registrata su questi giri` },
    "brk.none":        { en: `No braking point could be measured yet — drive a couple of clean laps on this car and track.`,
                         it: `Nessun punto di frenata ancora misurabile — fai un paio di giri puliti su questa auto e questa pista.` },
    "brk.repeatable":  { en: `same every lap`, it: `uguale ogni giro` },
    "brk.c.corner":    { en: `Corner`, it: `Curva` },
    "brk.c.speed":     { en: `You brake at`, it: `Freni a` },
    "brk.c.gear":      { en: `Gear`, it: `Marcia` },
    "brk.c.landmark":  { en: `Visual reference`, it: `Riferimento visivo` },
    "brk.c.zone":      { en: `Braking zone`, it: `Staccata` },
    "brk.c.vmin":      { en: `Min speed / gear`, it: `Minima / marcia` },
    "brk.c.spread":    { en: `Spread`, it: `Dispersione` },
    "brk.note":        { en: `Speed is the braking reference every car gives you for free — it's on the dash. The spread is how much your braking point moves lap to lap; the metres next to it are what that works out to over this braking zone.`,
                         it: `La velocità è il riferimento di frenata che ogni auto ti dà gratis: è sul cruscotto. La dispersione è di quanto si sposta il tuo punto di frenata da un giro all'altro; i metri accanto sono quanto vale su questa staccata.` },
    "brk.csv.title":   { en: `Download this sheet as a spreadsheet`,
                         it: `Scarica questa scheda come foglio di calcolo` },
    "brk.print.title": { en: `Print just this sheet`, it: `Stampa solo questa scheda` },

    // ---- line / trajectory tab ----
    // The map tab shows the whole lap and leaves the reading to the eye; this one
    // zooms one corner at a time and puts the geometry in metres. Wording for the
    // per-corner tags is NOT here — it lives next to the numbers in trajectory.py,
    // so a template and its value can't drift apart.
    "tab.line":        { en: `Line`, it: `Traiettoria` },
    "line.readout":    { en: `Hover the corner to read speed and how far you were from the reference line…`,
                         it: `Passa il mouse sulla curva per velocità e distanza dalla linea di riferimento…` },
    "line.missing":    { en: `These laps have no coordinates (the track map arrived with schema v3). Drive and record a new lap to see your line here.`,
                         it: `Questi giri non hanno coordinate (la mappa pista è arrivata con lo schema v3). Guida e registra un nuovo giro per vedere qui la tua traiettoria.` },
    "line.leg.you":    { en: `your line`, it: `la tua traiettoria` },
    "line.leg.ref":    { en: `reference`, it: `riferimento` },
    "line.leg.band":   { en: `the gap between them`, it: `lo scarto fra le due` },
    // "{m} m wide" was the MEDIAN width, printed under corners drawn far wider:
    // at Spa's La Source the game's data says 24.5 m, because the paved run-off
    // is asphalt too. The picture was right and the caption contradicted it.
    "line.leg.road":   { en: `the asphalt (usually {m} m wide) — paved run-off counts, kerbs don't`,
                         it: `l'asfalto (di norma largo {m} m) — le vie di fuga contano, i cordoli no` },
    // Due frasi perche' sono due cose diverse. Quella sopra descrive un
    // corridoio ricavato allargando la linea dell'IA; questa descrive la
    // strada, presa dal modello con cui il gioco decide dove sei.
    "line.leg.mesh":   { en: `the track, its kerbs and what's beside it — from the game's own surface model`,
                         it: `la pista, i cordoli e cosa c'è di fianco — dal modello delle superfici del gioco` },
    "line.leg.apex":   { en: `your slowest point`, it: `il tuo punto più lento` },
    "line.leg.apexref":{ en: `the reference's`, it: `quello del riferimento` },
    "chart.offset":    { en: `Where you were on the road <small>(m from the reference line · above = to its right, below = to its left)</small>`,
                         it: `Dove eri sulla strada <small>(m dalla linea di riferimento · sopra = alla sua destra, sotto = alla sua sinistra)</small>` },
    "chart.curv":      { en: `How tight you are turning <small>(white = you, cyan = reference · further from the middle = tighter arc)</small>`,
                         it: `Quanto stai stringendo <small>(bianco = tu, ciano = riferimento · più lontano dal centro = arco più stretto)</small>` },
    "load.line":       { en: `Loading your line…`, it: `Caricamento traiettoria…` },
    "err.line":        { en: `Couldn't work out the line for these laps.`,
                         it: `Non è stato possibile calcolare la traiettoria di questi giri.` },
    "line.extra":      { en: `Extra distance`, it: `Strada in più` },
    "line.extraHint":  { en: `you drove {you} m, the reference {ref} m`,
                         it: `hai percorso {you} m, il riferimento {ref} m` },
    "line.mean":       { en: `Average off the line`, it: `Scarto medio dalla linea` },
    "line.worst":      { en: `Furthest from it`, it: `Punto più lontano` },
    "line.corners":    { en: `Corners measured`, it: `Curve misurate` },
    "line.pick":       { en: `Corner`, it: `Curva` },
    // Sides. "Inside/outside" is the only form a driver reads without translating
    // — which side of the road a plus sign means depends on which way the corner
    // goes, and that conversion is done server-side (see trajectory.py).
    "line.in":         { en: `inside`, it: `dentro` },
    "line.out":        { en: `outside`, it: `fuori` },
    "line.right":      { en: `right`, it: `destra` },
    "line.left":       { en: `left`, it: `sinistra` },
    "line.same":       { en: `on the line`, it: `sulla linea` },
    "line.sameSpot":   { en: `same place`, it: `stesso punto` },
    "line.apexFlat":   { en: `(the bottom is flat for {m} m here)`,
                         it: `(qui il minimo è piatto per {m} m)` },
    "line.apexOff":    { en: `no apex here — the car wasn't cornering`,
                         it: `qui non c'è un apex — l'auto non stava curvando` },
    "map.leg.lost":    { en: `where the lap was lost`, it: `dove hai perso il giro` },
    "brk.mark.edit":   { en: `What do you look at when you brake here?`,
                         it: `Cosa guardi quando freni qui?` },
    "brk.mark.hint":   { en: `e.g. at the end of the green on the left`,
                         it: `es. alla fine del verde sulla sinistra` },
    "line.leg.brake":  { en: `braking starts (● you · ○ reference)`,
                         it: `inizio frenata (● tu · ○ riferimento)` },
    "line.leg.throttle": { en: `back on the power (● you · ○ reference)`,
                           it: `riapertura gas (● tu · ○ riferimento)` },
    "line.name.edit":  { en: `Name this corner`, it: `Dai un nome a questa curva` },
    "line.name.hint":  { en: `what you call it — shown everywhere, including out loud`,
                         it: `come la chiami tu — compare ovunque, anche a voce` },
    "line.name.save":  { en: `Save`, it: `Salva` },
    "line.name.drop":  { en: `Remove`, it: `Togli` },
    "line.name.err":   { en: `couldn't save the name`, it: `il nome non si è salvato` },
    // Il primo chip della Traiettoria: lo stato di partenza, non l'assenza
    // di una selezione.
    "range.clear":     { en: `Back to the whole lap`, it: `Torna al giro intero` },
    "line.whole":      { en: `Whole lap`, it: `Tutto il giro` },
    "line.mag":        { en: `gap`, it: `scarto` },
    "line.mag.note":   { en: `gap shown ×{n} — the scale bar is still real ground`,
                         it: `scarto mostrato ×{n} — la barra di scala resta reale` },
    "line.earlier":    { en: `earlier`, it: `prima` },
    "line.later":      { en: `later`, it: `dopo` },
    "line.f.apex":     { en: `Your apex`, it: `Il tuo apex` },
    "line.f.entry":    { en: `Entry`, it: `Ingresso` },
    "line.f.apexoff":  { en: `At the apex`, it: `All'apex` },
    "line.f.exit":     { en: `Exit`, it: `Uscita` },
    "line.f.widest":   { en: `Widest point`, it: `Punto più largo` },
    "line.f.radius":   { en: `Arc driven`, it: `Arco percorso` },
    "line.f.extra":    { en: `Distance here`, it: `Strada qui` },
    "line.f.vmin":     { en: `Min speed`, it: `Velocità minima` },
    "line.f.vexit":    { en: `Speed at exit`, it: `Velocità in uscita` },
    "line.f.vs":       { en: `vs`, it: `contro` },
    "line.dir.left":   { en: `left-hander`, it: `curva a sinistra` },
    "line.dir.right":  { en: `right-hander`, it: `curva a destra` },
    "line.kind.hairpin": { en: `hairpin`, it: `tornante` },
    // Una variante NON e' un tornante, e non e' nemmeno "una curva a sinistra"
    // solo perche' il punto piu' lento casca nella seconda meta'. Il verso qui
    // e' quello in cui ci ENTRI, che e' l'unico che serve a chi guida.
    "line.kind.chicane": { en: `chicane`, it: `variante` },
    "line.kind.slow":  { en: `slow`, it: `lenta` },
    "line.kind.medium":{ en: `medium`, it: `media` },
    "line.kind.fast":  { en: `fast`, it: `veloce` },
    "line.table":      { en: `Every corner, in metres <small>(inside + / outside − of the reference line)</small>`,
                         it: `Tutte le curve, in metri <small>(dentro + / fuori − rispetto alla linea di riferimento)</small>` },
    "line.csv":        { en: `⬇ CSV`, it: `⬇ CSV` },
    "line.csv.title":  { en: `Download this table as a spreadsheet`,
                         it: `Scarica questa tabella come foglio di calcolo` },
    "line.t.corner":   { en: `Corner`, it: `Curva` },
    "line.t.apex":     { en: `Apex`, it: `Apex` },
    "line.t.entry":    { en: `Entry`, it: `Ingr.` },
    "line.t.apexoff":  { en: `Apex`, it: `Apex` },
    "line.t.exit":     { en: `Exit`, it: `Uscita` },
    "line.t.radius":   { en: `Arc (m)`, it: `Arco (m)` },
    "line.t.extra":    { en: `Distance`, it: `Strada` },
    "line.t.vmin":     { en: `Min speed`, it: `Vel. min` },
    "line.none":       { en: `No corner could be measured on these laps.`,
                         it: `Nessuna curva misurabile su questi giri.` },
    "line.ro.off":     { en: `Off the line`, it: `Fuori linea` },
    "line.ro.radius":  { en: `Arc`, it: `Arco` },

    "sec.col.sector":  { en: `Sector`, it: `Settore` },
    "sec.col.time":    { en: `Time <small>(ref)</small>`, it: `Tempo <small>(rif)</small>` },
    "sec.col.delta":   { en: `Δ vs reference <small>(bars left = faster, right = slower)</small>`,
                         it: `Δ vs riferimento <small>(barre a sinistra = più veloce, a destra = più lento)</small>` },

    "prog.chart":      { en: `Lap times over time <small>(each point = a lap · green line = running best)</small>`,
                         it: `Tempi sul giro nel tempo <small>(ogni punto = un giro · linea verde = miglior progressivo)</small>` },
    "prog.weak":       { en: `Weak points <small>(corner by corner · systematic = to train)</small>`,
                         it: `Punti deboli <small>(curva per curva · sistematico = da allenare)</small>` },
    "prog.recurring":  { en: `Recurring mistakes`, it: `Errori ricorrenti` },

    "tyre.header":     { en: `Tyres across the stint <small>(core temp &amp; pressure · dashed = right side)</small>`,
                         it: `Le gomme lungo lo stint <small>(temp mescola e pressione · tratteggio = lato destro)</small>` },
    "tyre.elsewhere":  { en: `Tyre temperatures and pressures live under Race pace, where they are drawn over one tank instead of your whole archive.`,
                         it: `Temperature e pressioni gomme stanno sotto Passo gara, dove sono disegnate su un pieno solo invece che su tutto l'archivio.` },
    "tyre.goto":       { en: `Open Race pace`, it: `Apri Passo gara` },
    "tyre.temp":       { en: `Core temperature (°C)`, it: `Temperatura mescola (°C)` },
    "tyre.press":      { en: `Pressure (psi)`, it: `Pressione (psi)` },
    "tyre.fl":         { en: `Front-left`, it: `Ant. sx` },
    "tyre.fr":         { en: `Front-right`, it: `Ant. dx` },
    "tyre.rl":         { en: `Rear-left`, it: `Post. sx` },
    "tyre.rr":         { en: `Rear-right`, it: `Post. dx` },
    "tyre.front":      { en: `Front`, it: `Ant.` },
    "tyre.rear":       { en: `Rear`, it: `Post.` },
    "tyre.driftLead":  { en: `Across the stint`, it: `Nello stint` },
    "tyre.tempLabel":  { en: `Temp`, it: `Temp` },
    "tyre.pressLabel": { en: `Pressure`, it: `Pressione` },
    "tyre.none":       { en: `No tyre data on these laps (recorded before per-wheel capture).`,
                         it: `Nessun dato gomme su questi giri (registrati prima della cattura per ruota).` },

    "empty.title":     { en: `No laps yet`, it: `Ancora nessun giro` },
    "empty.step1":     { en: `Start the coach: run <code>python -m accoach live</code> (or use the launcher).`,
                         it: `Avvia il coach: esegui <code>python -m accoach live</code> (o usa il launcher).` },
    "empty.step2":     { en: `Drive a full, <b>valid</b> lap in AC or ACC.`,
                         it: `Guida un giro completo e <b>valido</b> in AC o ACC.` },
    "empty.step3":     { en: `Reload this page — your lap shows up here for analysis.`,
                         it: `Ricarica questa pagina — il tuo giro compare qui per l'analisi.` },
    "empty.hint":      { en: `Just want a tour? Launch with <code>python -m accoach web --demo</code> for sample laps.`,
                         it: `Vuoi solo dare un'occhiata? Avvia con <code>python -m accoach web --demo</code> per giri di esempio.` },

    // ---- analysis page (app.js injected) ----
    "load.lap":        { en: `Loading lap…`, it: `Caricamento giro…` },
    "load.trends":     { en: `Loading trends…`, it: `Caricamento andamento…` },
    "load.sectors":    { en: `Loading sectors…`, it: `Caricamento settori…` },
    "combo.laps":      { en: `laps`, it: `giri` },
    "combo.best":      { en: `best`, it: `migliore` },
    "err.progress":    { en: `Couldn't load progress — is the analysis backend running?`,
                         it: `Impossibile caricare l'andamento — il backend di analisi è in esecuzione?` },
    "err.lap":         { en: `Couldn't load this lap.`, it: `Impossibile caricare questo giro.` },
    "load.training":   { en: `Building your programme…`, it: `Costruzione del programma…` },
    "err.training":    { en: `Couldn't load the programme — is the analysis backend running?`,
                         it: `Impossibile caricare il programma — il backend di analisi è in esecuzione?` },

    "prog.validLaps":  { en: `Valid laps`, it: `Giri validi` },
    "prog.best":       { en: `Best`, it: `Migliore` },
    "prog.average":    { en: `Average`, it: `Media` },
    "prog.spread":     { en: `Spread`, it: `Escursione` },
    "prog.sigma":      { en: `σ`, it: `σ` },
    "prog.dash":       { en: `—`, it: `—` },
    "prog.noValid":    { en: `no valid lap`, it: `nessun giro valido` },

    "recur.none":      { en: `No recurring mistakes — nice consistency!`,
                         it: `Nessun errore ricorrente — bella costanza!` },
    "recur.corners":   { en: `Corners: `, it: `Curve: ` },

    // The training plan. It lives on the Training tab now — the strip that says
    // since when and the one button; the goals themselves are the steps, each
    // with the drill that closes it.
    "plan.title":      { en: `Your plan`, it: `Il tuo piano` },
    "plan.elsewhere":  { en: `Working on a plan? It lives under Training, next to the drills that close it.`,
                         it: `Stai seguendo un piano? Sta nella scheda Allenamento, insieme agli esercizi che lo chiudono.` },
    "plan.goto":       { en: `Open Training`, it: `Apri Allenamento` },
    "plan.none":       { en: `No systematic weakness to train — nothing worth putting in a plan yet.`,
                         it: `Nessun punto debole sistematico da allenare: per ora non c'è niente da mettere in un piano.` },
    "plan.proposed":   { en: `proposed from your recent laps — not started yet`,
                         it: `proposto dai tuoi ultimi giri — non ancora avviato` },
    "plan.since":      { en: `since {when}`, it: `dal {when}` },
    "plan.laps_since": { en: `{n} {n|lap|laps} since`, it: `{n} {n|giro|giri} da allora` },
    "plan.start":      { en: `Start this plan`, it: `Inizia questo piano` },
    "plan.change":     { en: `Change target`, it: `Cambia obiettivo` },
    "plan.hits":       { en: `{hits} of the {needed} laps it takes`,
                         it: `{hits} dei {needed} giri che servono` },
    // Both used to render as bare numbers next to each other — "now ~0.31s ·
    // best 0.18s" — with nothing saying 0.31s *of what*.
    "plan.now":        { en: `you lose ~{s}s now`, it: `ora perdi ~{s}s` },
    "plan.best":       { en: `your best {s}s`, it: `il tuo meglio {s}s` },
    "plan.nolaps":     { en: `no laps since you started it — go and drive`,
                         it: `nessun giro da quando l'hai avviato — vai a guidare` },
    "plan.willmeasure":{ en: `start the plan and from then on every lap is measured against this target`,
                         it: `avvia il piano e da lì in poi ogni giro viene misurato su questo obiettivo` },

    // ---- the Training tab ----
    // Only the chrome is declared here. Every sentence with a number in it is
    // written server-side (coaching/training.py), in the language asked for,
    // because the wording and the rule that decides it belong together.
    "tab.training":    { en: `Training`, it: `Allenamento` },
    "train.locked":    { en: `Not enough laps yet`, it: `Non ci sono ancora abbastanza giri` },
    "train.countdown": { en: `{n} more valid {n|lap|laps} and this opens.`,
                         it: `Ancora {n} {n|giro valido|giri validi} e questa scheda si apre.` },
    // The last lap before it opens is the one the driver is most likely to be
    // looking at, and it is exactly the one the plural got wrong.
    "train.countdown1": { en: `One more valid lap and this opens.`,
                          it: `Ancora un giro valido e questa scheda si apre.` },
    "train.intro":     { en: `Here there is no more analysis: there is what to do on track, one exercise at a time, built from your own laps.`,
                         it: `Qui non c'è altra analisi: c'è cosa fare in pista, un esercizio alla volta, costruito sui tuoi giri.` },
    "train.gap.title": { en: `Where your time is going`, it: `Dove se ne va il tuo tempo` },
    "train.sector":    { en: `Sector {n}`, it: `Settore {n}` },
    "train.drill":     { en: `Exercise · {n} laps`, it: `Esercizio · {n} giri` },
    "train.watch":     { en: `Watch:`, it: `Guarda:` },
    "train.ignore":    { en: `Ignore:`, it: `Ignora:` },
    "train.wholelap":  { en: `The whole lap`, it: `Il giro intero` },
    "train.status.now":   { en: `now`, it: `adesso` },
    "train.status.later": { en: `later`, it: `dopo` },
    "train.status.done":  { en: `✓ done`, it: `✓ fatto` },
    "train.session":   { en: `Your next session`, it: `La tua prossima sessione` },
    "train.session.laps": { en: `({n} {n|lap|laps})`, it: `({n} {n|giro|giri})` },
    // Not "Glossary": that label tells the reader they don't know things, and
    // gets skipped by the people it exists for. The words themselves are the
    // invitation.
    "train.words":     { en: `The words you'll hear other people use:`,
                         it: `Le parole che sentirai dire dagli altri:` },

    "lvl.header":      { en: `Levels <small>(best → ideal → PRO · gap = time available)</small>`,
                         it: `Livelli <small>(migliore → ideale → PRO · gap = tempo disponibile)</small>` },
    "lvl.yourRef":     { en: `your reference`, it: `il tuo riferimento` },
    "lvl.consistency": { en: `consistency on the table`, it: `costanza da recuperare` },
    "lvl.gapPro":      { en: `gap to PRO`, it: `gap dal PRO` },
    "lvl.beaten":      { en: `✓ already beaten`, it: `✓ già battuto` },
    "lvl.vsPro":       { en: `vs PRO`, it: `vs PRO` },

    "trends.none":     { en: `No recurring weak points — nice consistency!`,
                         it: `Nessun punto debole ricorrente — bella costanza!` },
    "badge.systematic":{ en: `Systematic`, it: `Sistematico` },
    "badge.sporadic":  { en: `Sporadic`, it: `Sporadico` },
    "trends.toTrain":  { en: `to train`, it: `da allenare` },
    "trends.oneOff":   { en: `one-off`, it: `episodico` },
    "trends.median":   { en: `median`, it: `mediana` },

    "prog.sessions":   { en: `Corner by session <small>(median loss per session · each point = one run)</small>`,
                         it: `Curva per sessione <small>(perdita mediana per sessione · ogni punto è un'uscita)</small>` },
    "ses.none":        { en: `No corner has enough sessions yet — keep driving.`,
                         it: `Nessuna curva ha ancora abbastanza sessioni — continua a girare.` },
    "ses.laps":        { en: `laps`, it: `giri` },
    "ses.better":      { en: `better than the first session`,
                         it: `meglio della prima sessione` },
    "ses.worse":       { en: `worse than the first session`,
                         it: `peggio della prima sessione` },

    "lbl.comparison":  { en: `Comparison`, it: `Confronto` },
    "lbl.lap":         { en: `Lap`, it: `Giro` },
    "lbl.gap":         { en: `Gap`, it: `Gap` },
    "lbl.road":        { en: `Track temp`, it: `Asfalto` },
    "flow.map":        { en: `Where you are losing it — this stretch highlighted`,
                         it: `Dove stai perdendo — il tratto in evidenza` },
    "flow.map.all":    { en: `Where you are losing it, over the whole lap`,
                         it: `Dove stai perdendo, su tutto il giro` },
    "kbd.tab":         { en: `Keyboard:`, it: `Da tastiera:` },
    "kbd.lap":         { en: `[ and ] step through the laps`,
                         it: `[ e ] scorrono i giri` },
    "lbl.sectors":     { en: `Sectors`, it: `Settori` },
    "lbl.laps":        { en: `laps`, it: `giri` },
    "sum.consistency": { en: `Consistency`, it: `Costanza` },
    "sum.setup_diff":  { en: `Setup differs`, it: `Setup diverso` },
    // Why the benchmark can be slower than your best lap. Braking points move
    // 10-20 m between a cold track and a hot one, so your evening PB is the
    // wrong target for a cold morning - the coach has always known this, the
    // report used to ignore it.
    "sum.cond":        { en: `Chosen for conditions`, it: `Scelto per le condizioni` },
    // The other reason a slower lap is the benchmark: the faster one was never
    // checked for track limits. Its own label, because "chosen for conditions"
    // over a sentence about track limits would be a confident wrong answer —
    // the thing this whole note exists to avoid.
    "sum.cond.unj":    { en: `Chosen as the judged lap`, it: `Scelto perché verificato` },
    "sum.cond.unjt":   { en: `your {time} is faster but nothing ever checked it for track limits`,
                         it: `il tuo {time} è più veloce ma nessuno ne ha mai verificato i limiti di pista` },
    "sum.cond.v":      { en: `track {temp}° · your {time} was at {ftemp}°`,
                         it: `asfalto {temp}° · il tuo {time} era a {ftemp}°` },
    "sum.cond.vx":     { en: `track {temp}° · your {time} has no recorded temperature`,
                         it: `asfalto {temp}° · il tuo {time} non ha la temperatura registrata` },
    // The tyre outranks the temperature: a different compound is a different
    // car. The strings are the sim's own — canonical on ACC, whatever the mod
    // decided on AC — and are shown, never translated.
    "sum.cond.tyre":   { en: `tyres {tyre} · your {time} was on {ftyre}`,
                         it: `gomme {tyre} · il tuo {time} era su {ftyre}` },
    "sum.cond.unknown":{ en: `an unrecorded compound`, it: `una mescola non registrata` },
    "sum.cond.grip":   { en: `track grip {grip} · your {time} was at {fgrip}`,
                         it: `grip pista {grip} · il tuo {time} era a {fgrip}` },
    "sum.cond.gripx":  { en: `track grip {grip} · your {time} has no recorded grip`,
                         it: `grip pista {grip} · il tuo {time} non ha il grip registrato` },

    "sec.t.title":     { en: `Every lap, sector by sector`,
                         it: `Ogni giro, settore per settore` },
    "sec.t.lap":       { en: `Lap`, it: `Giro` },
    "sec.t.hint":      { en: `Highlighted = your best in that sector. The ideal lap above is these.`,
                         it: `In evidenza = il tuo migliore in quel settore. Il giro ideale qui sopra è fatto di questi.` },
    "sec.real":        { en: `real track sectors`, it: `settori reali pista` },
    "sec.thirds":      { en: `thirds (position)`, it: `terzi (posizione)` },
    "ideal.title":     { en: `Ideal lap`, it: `Giro ideale` },
    "ideal.potential": { en: `potential`, it: `potenziale` },
    "ideal.from":      { en: `Your best sectors so far, stitched together.`,
                         it: `I tuoi migliori settori finora, uniti insieme.` },

    "vmin.header":     { en: `Min speed per corner <small>(km/h · + = faster than reference)</small>`,
                         it: `Velocità minima per curva <small>(km/h · + = più veloce del riferimento)</small>` },
    "vmin.corner":     { en: `Corner`, it: `Curva` },
    "vmin.you":        { en: `You`, it: `Tu` },
    "vmin.ref":        { en: `Ref`, it: `Rif` },
    "vmin.delta":      { en: `Δ`, it: `Δ` },

    // "invalid" was a lie: `valid` means the lap was *complete* (it started at a
    // start/finish crossing), which has nothing to do with track limits. Nobody
    // has ever seen this label — every recorded lap is complete — so renaming it
    // costs nothing now and would cost a habit later.
    "lap.invalid":     { en: `(partial)`, it: `(incompleto)` },
    // Track limits. NOT "dirty/sporco": "clean lap / giro pulito" already means
    // "no significant time lost per corner" in the debrief and on the hub's Home,
    // and "drive a clean lap" means "a complete one" in the coach — three senses
    // of one word would be worse than the gap this fills.
    "lap.offTrack":    { en: `off track`, it: `fuori pista` },
    // Reads as "off track at Variante Ascari" / "fuori pista alla Variante Ascari".
    // Italian needs the article to agree with the corner's gender, and corner
    // names are proper nouns we don't inflect ("alla Tamburello" is wrong,
    // "al Tamburello" is right). A neutral preposition sidesteps the whole
    // problem and reads fine for every name in every table: "fuori pista in
    // Variante Ascari", "fuori pista in Tamburello".
    "lap.offTrack.at": { en: `at`, it: `in` },
    "lap.offTrack.why": { en: `You went off track on this lap (3 or more wheels off), so it can't become your reference.`,
                          it: `In questo giro sei uscito di pista (3+ ruote fuori), quindi non può diventare il tuo riferimento.` },
    // The four stretches of a corner. Same words the debrief uses for the cause
    // ("understeer at the apex"), so one word keeps meaning one place.
    "phase.entry":     { en: `entry`, it: `ingresso` },
    "phase.apex":      { en: `apex`, it: `apex` },
    "phase.exit":      { en: `exit`, it: `uscita` },
    "phase.after":     { en: `the run after`, it: `tratto dopo` },

    "debrief.title":   { en: `Where to improve`, it: `Dove migliorare` },
    "debrief.clean":   { en: `Clean lap — no significant time lost per corner.`,
                         it: `Giro pulito — nessuna perdita di tempo significativa per curva.` },

    "ro.pos":          { en: `Pos`, it: `Pos` },
    "ro.speed":        { en: `Speed`, it: `Velocità` },
    "ro.ref":          { en: `ref`, it: `rif` },
    "ro.throttle":     { en: `Throttle`, it: `Gas` },
    "ro.brake":        { en: `Brake`, it: `Freno` },
    "ro.gear":         { en: `Gear`, it: `Marcia` },

    // analysis tour
    "tour.a1.t": { en: `Pick a lap`, it: `Scegli un giro` },
    "tour.a1.x": { en: `Choose the car and track. HONE compares your laps for this combo.`,
                   it: `Scegli auto e pista. HONE confronta i tuoi giri per questa combo.` },
    // Counts nothing on purpose: this said "Four views" while there were five
    // tabs, and six the moment the guided flow landed. A number here is a
    // promise the tab bar keeps breaking.
    "tour.a2.t": { en: `The other views`, it: `Le altre viste` },
    "tour.a2.x": { en: `The same laps seen other ways: traces side by side in Compare, the racing line on the Map, corner by corner in Line, split times in Sectors, grip and slip in Dynamics, and where you're heading in Trends. Each tab has a key that opens it, left to right — hover a tab to see which one.`,
                   it: `Gli stessi giri visti in altri modi: le tracce affiancate in Confronto, la traiettoria sulla Mappa, curva per curva in Traiettoria, gli split nei Settori, aderenza e slittamenti in Dinamica, e dove stai andando in Andamento. Ogni scheda ha un tasto che la apre, da sinistra a destra — passa il mouse su una scheda per vedere qual è.` },
    "tour.a3.t": { en: `Delta`, it: `Delta` },
    "tour.a3.x": { en: `Where you're gaining or losing vs your reference, across the lap. Green (below the line) is faster.`,
                   it: `Dove guadagni o perdi rispetto al riferimento, lungo il giro. Verde (sotto la linea) è più veloce.` },
    "tour.a4.t": { en: `Min speed per corner`, it: `Velocità minima per curva` },
    "tour.a4.x": { en: `Apex speed in every corner vs the reference — a positive delta means you carried more speed.`,
                   it: `Velocità all'apice in ogni curva rispetto al riferimento — un delta positivo significa più velocità portata.` },
    "tour.a5.t": { en: `Where to improve`, it: `Dove migliorare` },
    "tour.a5.x": { en: `Your biggest time losses, corner by corner, with the likely cause and a fix.`,
                   it: `Le tue perdite di tempo maggiori, curva per curva, con la causa probabile e una correzione.` },
    // Added when the debrief grew lap-wide findings and the lap list grew track
    // temperature: two things a driver sees before anyone explains them.
    "tour.a7.t": { en: `Whole-lap findings`, it: `Osservazioni sul giro` },
    "tour.a7.x": { en: `The blue-edged blocks above the corners are lap-wide: a lift where the reference is flat, a top-speed deficit. Coaches say these first.`,
                   it: `I riquadri col bordo azzurro sopra le curve valgono per tutto il giro: un sollevamento dove il riferimento sta in pieno, dei km/h di punta che mancano. Un coach parte da qui.` },
    "tour.a8.t": { en: `Track temperature`, it: `Temperatura asfalto` },
    "tour.a8.x": { en: `The degrees next to each lap are the track, not the air. Braking points move 10-20 m between a cold track and a hot one, so two laps far apart in temperature are two different circuits.`,
                   it: `I gradi accanto a ogni giro sono dell'asfalto, non dell'aria. Fra pista fredda e calda i punti di frenata si spostano di 10-20 m: due giri con temperature lontane sono due circuiti diversi.` },
    "tour.a10.t": { en: `Your line, corner by corner`, it: `La tua traiettoria, curva per curva` },
    "tour.a10.x": { en: `One corner at a time, zoomed in: the shaded band is how far your line was from the reference's, in metres. Underneath, the same corner as numbers — where your slowest point sits, how tight an arc you drove, how much extra road you covered.`,
                    it: `Una curva alla volta, ingrandita: la fascia colorata è quanto la tua traiettoria si è scostata da quella di riferimento, in metri. Sotto, la stessa curva in numeri — dov'è il tuo punto più lento, quanto stretto è l'arco che hai fatto, quanta strada in più hai percorso.` },
    "tour.a11.t": { en: `And what do I do about it?`, it: `E adesso come mi alleno?` },
    "tour.a11.x": { en: `The rest of the app tells you what you lose and why. This tab turns it into a drill: one thing at a time, how many laps to run it for, what to watch and what to deliberately ignore — plus the number that says when you're done. It opens once you have enough laps on this car and track for it to mean something.`,
                    it: `Il resto dell'app ti dice cosa perdi e perché. Questa scheda lo trasforma in un esercizio: una cosa alla volta, per quanti giri farla, cosa guardare e cosa ignorare di proposito — più il numero che dice quando è fatta. Si apre quando hai abbastanza giri su questa auto e questa pista perché significhi qualcosa.` },
    "tour.a6.t": { en: `Take it with you`, it: `Portalo con te` },
    "tour.a6.x": { en: `Export the lap as CSV or JSON for deeper analysis.`,
                   it: `Esporta il giro in CSV o JSON per un'analisi più approfondita.` },

    // ---- engineer page (engineer.html) ----
    "title.engineer":  { en: `HONE · Engineer`, it: `HONE · Ingegnere` },
    "eng.subtitle":    { en: `· Race engineer`, it: `· Ingegnere di pista` },
    "ctl.setup":       { en: `Starting setup`, it: `Setup di partenza` },
    "btn.undo":        { en: `↶ Restore`, it: `↶ Ripristina` },
    "btn.undo.title":  { en: `Restore this setup from the last backup`,
                         it: `Ripristina questo setup dall'ultimo backup` },
    "live.offline":    { en: `telemetry offline`, it: `telemetria offline` },
    "live.inpit":      { en: `in pit`, it: `ai box` },
    "live.ontrack":    { en: `on track`, it: `in pista` },

    "eng.liveDiag":    { en: `Live diagnosis`, it: `Diagnosi live` },
    "eng.waiting":     { en: `Waiting for telemetry…`, it: `In attesa di telemetria…` },
    "g.speed":         { en: `Speed`, it: `Velocità` },
    "g.gear":          { en: `Gear`, it: `Marcia` },
    "g.tc":            { en: `TC`, it: `TC` },
    "g.abs":           { en: `ABS`, it: `ABS` },
    "g.map":           { en: `Map`, it: `Mappa` },

    "eng.tyres":       { en: `Tyres <span class="es-sub">(temp °C · pressure psi)</span>`,
                         it: `Gomme <span class="es-sub">(temp °C · pressione psi)</span>` },
    "eng.avNow":       { en: `⚡ Right now, in the car`, it: `⚡ Adesso, in macchina` },
    "eng.suggests":    { en: `🔧 The engineer suggests <span class="es-sub">(at the next pit stop)</span>`,
                         it: `🔧 L'ingegnere suggerisce <span class="es-sub">(al prossimo pit stop)</span>` },
    "eng.prepare":     { en: `Prepare change in the editor →`, it: `Prepara la modifica nell'editor →` },

    "eng.focusTitle":  { en: `Focus · lesson`, it: `Focus · lezione` },
    "eng.focusSub":    { en: `(your driving, one weakness at a time)`,
                         it: `(la tua guida, una debolezza alla volta)` },
    "focus.warmup":    { en: `Warming up… drive a few clean laps.`,
                         it: `Riscaldamento… fai qualche giro pulito.` },

    "eng.profile":     { en: `Engineer profile`, it: `Profilo ingegnere` },
    "eng.phases":      { en: `Phases:`, it: `Fasi:` },
    "eng.onfly":       { en: `On the fly:`, it: `Al volo:` },
    "eng.engPrefix":   { en: `Engineer `, it: `Ingegnere ` },

    // Diceva «avvia Coach Live **o** il backend». Falso: `live` è un processo
    // unico senza WebSocket, quindi non alimenta questa pagina — e chi lo aveva
    // acceso restava su «in attesa di telemetria» per sempre mentre il coach gli
    // parlava nelle cuffie. I due non possono nemmeno convivere: registrano
    // entrambi, e insieme salverebbero ogni giro due volte.
    "eng.hint":        { en: `This page is fed by the <b>live backend</b> — hub → <b>Devices</b> → 📡 Live backend. Coach Live does not feed it, and the two can't run together (they'd both record). The changes on the right apply to the setup file: they must be <b>loaded in the pits</b>, they don't change the car while you drive.`,
                         it: `Questa pagina la alimenta il <b>backend live</b> — hub → <b>Dispositivi</b> → 📡 Backend live. Coach Live non la alimenta, e i due non possono stare accesi insieme (registrano entrambi). Le modifiche a destra agiscono sul file di setup: vanno <b>caricate ai box</b>, non cambiano l'auto mentre guidi.` },

    "setup.title":     { en: `Setup`, it: `Setup` },
    "legend2.click":   { en: `<b>click</b> = game step`, it: `<b>click</b> = scatto di gioco` },
    "legend2.est":     { en: `psi/% = estimate`, it: `psi/% = stima` },
    "setup.pick":      { en: `Pick a car/track above. HONE reads setups from <code>Documents/Assetto Corsa Competizione/Setups/&lt;car&gt;/&lt;track&gt;/</code> (ACC) and <code>Documents/Assetto Corsa/setups/</code> (AC).`,
                         it: `Scegli auto/pista qui sopra. HONE legge i setup da <code>Documents/Assetto Corsa Competizione/Setups/&lt;car&gt;/&lt;track&gt;/</code> (ACC) e <code>Documents/Assetto Corsa/setups/</code> (AC).` },

    "tray.pending":    { en: `Pending changes`, it: `Modifiche in sospeso` },
    "tray.reset":      { en: `Reset all`, it: `Azzera tutto` },
    "tray.write":      { en: `Write setup…`, it: `Scrivi setup…` },

    "modal.title":     { en: `Confirm setup write`, it: `Conferma scrittura setup` },
    "modal.name":      { en: `Destination file name`, it: `Nome file di destinazione` },
    "modal.hint":      { en: `A <b>new file</b> will be created (the original stays intact). After writing: return to the pits → Setup screen → load the new setup.`,
                         it: `Verrà creato un <b>nuovo file</b> (l'originale resta intatto). Dopo la scrittura: torna ai box → schermata Setup → carica il nuovo setup.` },
    "modal.cancel":    { en: `Cancel`, it: `Annulla` },
    "modal.write":     { en: `Write`, it: `Scrivi` },

    // ---- engineer page (engineer.js injected) ----
    "eng.noSetupOpt":  { en: `(no setup found)`, it: `(nessun setup trovato)` },
    "eng.noSetupBody": { en: `No setup files found for this car/track.<br>HONE reads setups from:<br><code>Documents/Assetto Corsa Competizione/Setups/&lt;car&gt;/&lt;track&gt;/</code> (ACC)<br><code>Documents/Assetto Corsa/setups/&lt;car&gt;/&lt;track&gt;/</code> (AC)<br>Save a setup in the game, then reload this page.`,
                         it: `Nessun file di setup trovato per questa auto/pista.<br>HONE legge i setup da:<br><code>Documents/Assetto Corsa Competizione/Setups/&lt;car&gt;/&lt;track&gt;/</code> (ACC)<br><code>Documents/Assetto Corsa/setups/&lt;car&gt;/&lt;track&gt;/</code> (AC)<br>Salva un setup nel gioco, poi ricarica questa pagina.` },

    "eng.prepared.some": { en: `Change prepared (some parameters are not in this setup).`,
                           it: `Modifica preparata (alcuni parametri non sono in questo setup).` },
    "eng.prepared.ok":   { en: `Change prepared in the editor — review it and press “Write setup”.`,
                           it: `Modifica preparata nell'editor — controllala e premi “Scrivi setup”.` },
    "eng.prepared.none": { en: `The proposed parameter is not in this setup.`,
                           it: `Il parametro proposto non è in questo setup.` },

    "eng.click":       { en: `click`, it: `click` },
    "eng.alvoloTag":   { en: `live`, it: `al volo` },
    "eng.alvoloHint":  { en: `Adjustable on track without pitting (the rest take effect after reloading the setup at the box).`,
                         it: `Regolabile in pista senza rientrare ai box (gli altri hanno effetto ricaricando il setup ai box).` },
    "eng.previewErr":  { en: `Preview error: `, it: `Errore anteprima: ` },
    "eng.enterName":   { en: `Enter a file name.`, it: `Inserisci un nome file.` },
    "eng.exists":      { en: `A setup with this name already exists — choose another.`,
                         it: `Esiste già un setup con questo nome — scegline un altro.` },
    "eng.writeErr":    { en: `Write error: `, it: `Errore di scrittura: ` },
    "eng.restored":    { en: `✓ Setup restored from the last backup`,
                         it: `✓ Setup ripristinato dall'ultimo backup` },
    "eng.noBackup":    { en: `No backup to restore for this setup.`,
                         it: `Nessun backup da ripristinare per questo setup.` },
    "eng.restoreErr":  { en: `Restore error: `, it: `Errore ripristino: ` },
    "eng.corners":     { en: `Corners `, it: `Curve ` },
    // The verdict, after the re-test laps. The words are short because the
    // sentence that explains it is written server-side, next to the rule.
    "eng.oc.kept":     { en: `kept`, it: `tenuta` },
    "eng.oc.reverted": { en: `put back`, it: `rimessa com'era` },
    "eng.oc.laps":     { en: `over`, it: `su` },
    "eng.oc.side":     { en: `Also moved, unasked:`, it: `Si è mosso anche:` },
    "eng.lowConf":     { en: `Low confidence — based on little data. Gather a few more clean laps before applying.`,
                         it: `Confidenza bassa — pochi dati. Raccogli qualche altro giro pulito prima di applicare.` },
    "eng.dash":        { en: `—`, it: `—` },
    "eng.warmup":      { en: `I need 3 clean laps for a baseline — I'm watching.`,
                         it: `Servono 3 giri puliti per una base — sto guardando.` },
    // What to do in the current setup phase — persistent guidance so "phase done →
    // moving to X" is always followed by a concrete instruction.
    "eng.phaseNow":    { en: `Phase`, it: `Fase` },
    "eng.do.pressures":  { en: `Drive a few laps to bring the tyres up to temperature — I judge pressures hot.`,
                           it: `Guida qualche giro per portare le gomme in temperatura: giudico le pressioni a caldo.` },
    "eng.do.mechanical": { en: `Keep driving clean laps. I look for under/oversteer at LOW speed (springs, bars, differential). If I propose a change it's a pit job: prepare it, write the setup, reload it at the box.`,
                           it: `Continua a guidare giri puliti. Cerco sotto/sovrasterzo a BASSA velocità (molle, barre, differenziale). Se propongo una modifica è da BOX: preparala, scrivi il setup, ricaricalo al box.` },
    "eng.do.aero":       { en: `Drive clean laps at pace. Now I work on HIGH-speed balance (wing, rake / ride height) — a pit job.`,
                           it: `Guida giri puliti a ritmo. Ora lavoro sull'equilibrio ad ALTA velocità (ala, rake / altezze) — da BOX.` },
    "eng.do.brake_bias": { en: `Brake like in a race. I tune brake balance — adjustable on the fly, no pit needed.`,
                           it: `Frena come in gara. Regolo il bilanciamento freni — al volo, senza box.` },
    "eng.do.electronics":{ en: `Push on corner exit. I tune TC/ABS/engine maps — on the fly.`,
                           it: `Spingi in uscita. Regolo TC/ABS/mappe motore — al volo.` },
    "eng.do.traction":   { en: `Focus on corner exit. I work on mechanical traction (diff, rear grip) — a pit job.`,
                           it: `Concentrati sull'uscita. Lavoro sulla trazione meccanica (differenziale, grip posteriore) — da BOX.` },
    "eng.do.diff":       { en: `Drive entry and exit consistently. I tune the differential — a pit job.`,
                           it: `Guida entrata e uscita in modo costante. Regolo il differenziale — da BOX.` },
    "eng.do.default":    { en: `Keep driving clean, consistent laps — I'm gathering data for this phase.`,
                           it: `Continua a guidare giri puliti e costanti: sto raccogliendo dati per questa fase.` },
    "eng.pit1":        { en: `🅿️ You're in the pits: MFD → <b>Setup</b> → load <b>`,
                         it: `🅿️ Sei ai box: MFD → <b>Setup</b> → carica <b>` },
    "eng.pit2":        { en: `</b> → leave the pits to apply it.`,
                         it: `</b> → esci dai box per applicarlo.` },
    // Shown while stopped in the box with a garage change still unwritten —
    // the screen half of the spoken briefing (coaching/pitcall.py). The voice
    // sends you to this page; arriving to no instructions would waste the trip.
    "eng.pitTodo":     { en: `🅿️ You're in the box with a change waiting: click the proposal above, then <b>Prepare change</b> → <b>Write</b>, and load the setup from the garage before you go out.`,
                         it: `🅿️ Sei ai box e c'è una modifica in attesa: clicca la proposta qui sopra, poi <b>Prepara modifica</b> → <b>Scrivi</b>, e ricarica il setup dal garage prima di uscire.` },
    "eng.loadErr":     { en: `Setup loading error: `, it: `Errore caricamento setup: ` },

    // --- il registro dell'ingegnere -----------------------------------------
    // Presentato a CONTEGGI, non a percentuali, finché le prove non sono
    // abbastanza: un tasso di successo su tre campioni è rumore travestito da
    // percentuale, e il modulo che lo calcola lo dice per primo.
    "rec.title":       { en: `📒 Track record`, it: `📒 Registro` },
    "rec.none":        { en: `No test finished yet on this car and track. The engineer proposes a change, you drive it, and the verdict lands here — including the ones that didn't work.`,
                         it: `Nessuna prova ancora conclusa su questa auto e questa pista. L'ingegnere propone una modifica, tu la guidi, e il verdetto finisce qui — comprese quelle che non hanno funzionato.` },
    "rec.counts":      { en: `<b>{kept}</b> kept out of <b>{tests}</b> tested`,
                         it: `<b>{kept}</b> tenute su <b>{tests}</b> provate` },
    "rec.rate":        { en: ` · {rate}% hit rate`, it: ` · {rate}% di riuscita` },
    "rec.gain":        { en: ` · median {gain}s on the lap`,
                         it: ` · mediana {gain}s sul giro` },
    "rec.thin":        { en: `Too few tests to publish a percentage — a hit rate over a handful of samples is noise wearing a percent sign. The counts are above.`,
                         it: `Troppo poche prove per pubblicare una percentuale: un tasso di riuscita su una manciata di campioni è rumore travestito da percentuale. I conteggi sono qui sopra.` },
    "rec.byparam":     { en: `Which levers earn their place`, it: `Quali leve si guadagnano il posto` },
    "rec.byrank":      { en: `Does "most effective first" hold up?`,
                         it: `Regge il «prima il rimedio più efficace»?` },
    "rec.rank":        { en: `remedy #{n}`, it: `rimedio n.{n}` },
    "rec.side":        { en: `Side effects seen (never predicted)`,
                         it: `Effetti collaterali visti (mai predetti)` },
    "rec.kept_of":     { en: `{kept}/{tests} kept`, it: `{kept}/{tests} tenute` },
    "rec.seen":        { en: `{n}×`, it: `{n}×` },
    "eng.avDone":      { en: `Done — I've made it`, it: `Fatto — l'ho cambiato` },

    // engineer tour
    "tour.e1.t": { en: `Live diagnosis`, it: `Diagnosi live` },
    "tour.e1.x": { en: `Speed, gear and aids straight from the car when the coach is running live.`,
                   it: `Velocità, marcia e aiuti direttamente dall'auto quando il coach è in esecuzione live.` },
    "tour.e2.t": { en: `Tyres`, it: `Gomme` },
    "tour.e2.x": { en: `Temperatures and pressures, colour-coded — keep them in the green window.`,
                   it: `Temperature e pressioni, con codice colore — tienile nella finestra verde.` },
    "tour.e3.t": { en: `The engineer`, it: `L'ingegnere` },
    "tour.e3.x": { en: `A setup change proposed from your telemetry. Hit “Prepare change” to load it into the editor.`,
                   it: `Una modifica di setup proposta dalla tua telemetria. Premi “Prepara la modifica” per caricarla nell'editor.` },
    "tour.e4.t": { en: `Focus · lesson`, it: `Focus · lezione` },
    "tour.e4.x": { en: `Your driving coach, working one weakness at a time while you lap.`,
                   it: `Il tuo coach di guida, che lavora una debolezza alla volta mentre giri.` },
    "tour.e5.t": { en: `Setup editor`, it: `Editor setup` },
    "tour.e5.x": { en: `Adjust by game clicks, then “Write setup” saves a new file to load in the pits.`,
                   it: `Regola con i click di gioco, poi “Scrivi setup” salva un nuovo file da caricare ai box.` },
    "tour.e6.t": { en: `Change it now, at the wheel`, it: `Cambiala adesso, al volante` },
    "tour.e6.x": { en: `A dial you turn on the straight — no pit stop, no lap lost. On ACC there is nothing to confirm: HONE reads the level live and sees it move. On AC those levels aren't published, so use the button.`,
                   it: `Una manopola che giri sul rettilineo: niente sosta, niente giro perso. Su ACC non devi confermare nulla, HONE legge il livello dal vivo e si accorge da solo che si è mosso. Su AC quei livelli non sono leggibili: usa il pulsante.` },
  };

  // ---- core ---------------------------------------------------------------
  function readLang() {
    var l = "en";
    try { l = localStorage.getItem(STORE) || "en"; } catch (e) {}
    return SUPPORTED.indexOf(l) === -1 ? "en" : l;
  }

  var lang = readLang();

  function t(key) {
    var e = CAT[key];
    if (!e) return key;
    if (e[lang] != null) return e[lang];
    if (e.en != null) return e.en;
    return key;
  }

  // Translate the static elements tagged in the HTML.
  //   data-i18n             -> textContent
  //   data-i18n-html        -> innerHTML (value may contain markup)
  //   data-i18n-title       -> title attribute
  //   data-i18n-aria        -> aria-label attribute
  //   data-i18n-placeholder -> placeholder attribute
  function applyStatic(root) {
    root = root || document;
    try {
      root.querySelectorAll("[data-i18n]").forEach(function (el) {
        var v = t(el.getAttribute("data-i18n"));
        if (v != null) el.textContent = v;
      });
      root.querySelectorAll("[data-i18n-html]").forEach(function (el) {
        var v = t(el.getAttribute("data-i18n-html"));
        if (v != null) el.innerHTML = v;
      });
      root.querySelectorAll("[data-i18n-title]").forEach(function (el) {
        var v = t(el.getAttribute("data-i18n-title"));
        if (v != null) el.title = v;
      });
      root.querySelectorAll("[data-i18n-aria]").forEach(function (el) {
        var v = t(el.getAttribute("data-i18n-aria"));
        if (v != null) el.setAttribute("aria-label", v);
      });
      root.querySelectorAll("[data-i18n-placeholder]").forEach(function (el) {
        var v = t(el.getAttribute("data-i18n-placeholder"));
        if (v != null) el.placeholder = v;
      });
    } catch (e) { /* defensive: never break the page over a missing node */ }
    try { document.documentElement.lang = lang; } catch (e) {}
  }

  function set(l) {
    if (SUPPORTED.indexOf(l) === -1) l = "en";
    lang = l;
    window.HoneI18n.lang = l;
    try { localStorage.setItem(STORE, l); } catch (e) {}
    applyStatic();
    syncSelectors();
    // Re-render the dynamic views without a reload when the page provides a
    // hook; otherwise fall back to a full reload (state is in localStorage).
    try {
      if (typeof window.HoneI18nRerender === "function") {
        var r = window.HoneI18nRerender();
        // The hook may be async — the engineer re-fetches its backend-rendered
        // labels. A rejected promise never reaches the catch below, so route it
        // to the same fallback instead of leaving the page half-translated.
        if (r && typeof r.catch === "function") {
          r.catch(function () { try { location.reload(); } catch (e2) {} });
        }
      }
    } catch (e) {
      try { location.reload(); } catch (e2) {}
    }
  }

  // ---- language selector --------------------------------------------------
  var LANGS = [["en", "English"], ["it", "Italiano"]];

  function syncSelectors() {
    try {
      document.querySelectorAll("select.lang-select").forEach(function (s) {
        s.value = lang;
      });
    } catch (e) {}
  }

  function mountSelector() {
    // One selector per page, dropped right after the tour "?" button.
    if (document.querySelector("select.lang-select")) return;
    var help = document.querySelector(".tour-help");
    if (!help || !help.parentNode) return;
    var sel = document.createElement("select");
    sel.className = "lang-select";
    sel.setAttribute("aria-label", t("lang.label"));
    sel.title = t("lang.label");
    for (var i = 0; i < LANGS.length; i++) {
      var o = document.createElement("option");
      o.value = LANGS[i][0];
      o.textContent = LANGS[i][1];
      if (LANGS[i][0] === lang) o.selected = true;
      sel.appendChild(o);
    }
    sel.addEventListener("change", function () { set(sel.value); });
    help.parentNode.insertBefore(sel, help.nextSibling);
  }

  function boot() {
    mountSelector();
    applyStatic();
  }

  window.HoneI18n = { lang: lang, t: t, set: set, applyStatic: applyStatic };

  // Script lives at the end of <body>, after the header — the DOM we need is
  // already parsed, so boot immediately (and also catch the event, defensively).
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
