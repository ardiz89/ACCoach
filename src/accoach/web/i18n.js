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

    "tab.flow":        { en: `Lap explained`, it: `Il giro spiegato` },
    "tour.a9.t":       { en: `Start here`, it: `Parti da qui` },
    "tour.a9.x":       { en: `The lap, explained one thing at a time: what cost you the most, why, and what to do about it — with the chart that shows it. The other tabs are the same findings, laid out for you to read yourself.`,
                         it: `Il giro spiegato una cosa alla volta: cosa ti è costato di più, perché, e cosa farci — col grafico che lo mostra. Le altre schede sono gli stessi dati, messi lì perché te li legga da solo.` },
    "tab.session":     { en: `Session`, it: `Sessione` },
    "tab.compare":     { en: `Compare`, it: `Confronto` },
    // One run of laps, as it was driven.
    "ses.which":       { en: `Session`, it: `Sessione` },
    "ses.none":        { en: `No laps recorded for this car and track yet.`,
                         it: `Nessun giro registrato per questa auto e questa pista.` },
    "ses.sub":         { en: `{laps} laps · {valid} that count · {mins} min`,
                         it: `{laps} giri · {valid} che contano · {mins} min` },
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
    "chart.slip":      { en: `Lock &amp; spin <small>(slip ratio · cyan = front, amber = rear · below 0 = locking, above = spinning)</small>`,
                         it: `Bloccaggio e pattinamento <small>(slip ratio · ciano = ant, arancio = post · sotto 0 = bloccaggio, sopra = pattinamento)</small>` },
    "dyn.missing":     { en: `This lap has no dynamics data (G / slip were recorded from v6). Drive and record a new lap to see it here.`,
                         it: `Questo giro non ha dati di dinamica (G / slip registrati dalla v6). Guida e registra un nuovo giro per vederli qui.` },
    "dyn.coasting":    { en: `Coasting`, it: `In folle (coasting)` },
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
    "chart.lineoff":   { en: `Line deviation <small>(m off the reference line · above = one side, below = the other)</small>`,
                         it: `Scostamento traiettoria <small>(m dalla linea di riferimento · sopra = un lato, sotto = l'altro)</small>` },
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
                         it: `Giri motore e cambiate <small>(rpm lungo il giro · ▲ = scalata su, ▼ = scalata giù)</small>` },
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

    // ---- braking sheet (under the track map) ----
    // Your own braking points, measured. The wording carries the caveats the
    // static sheets going round the forums don't: how many laps, which asphalt
    // temperature, and that the metres are an approximation.
    "brk.title":       { en: `Your braking points`, it: `Le tue frenate` },
    "brk.sub":         { en: `measured on your last {laps} laps`,
                         it: `misurate sui tuoi ultimi {laps} giri` },
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

    "tyre.header":     { en: `Tyres over time <small>(core temp &amp; pressure across the stint · dashed = right side)</small>`,
                         it: `Gomme nel tempo <small>(temp mescola e pressione lungo lo stint · tratteggio = lato destro)</small>` },
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

    // The training plan (Trends). Deliberately spare: the goal, the number that
    // ends it, and how many laps you're into it.
    "plan.title":      { en: `Your plan`, it: `Il tuo piano` },
    "plan.none":       { en: `No systematic weakness to train — nothing worth putting in a plan yet.`,
                         it: `Nessun punto debole sistematico da allenare: per ora non c'è niente da mettere in un piano.` },
    "plan.proposed":   { en: `proposed from your recent laps — not started yet`,
                         it: `proposto dai tuoi ultimi giri — non ancora avviato` },
    "plan.since":      { en: `since {when}`, it: `dal {when}` },
    "plan.laps_since": { en: `{n} laps since`, it: `{n} giri da allora` },
    "plan.start":      { en: `Start this plan`, it: `Inizia questo piano` },
    "plan.change":     { en: `Change goal`, it: `Cambia obiettivo` },
    "plan.target":     { en: `you lose {from}s here · get it under {to}s`,
                         it: `qui perdi {from}s · portalo sotto {to}s` },
    "plan.hits":       { en: `{hits} of the {needed} laps it takes`,
                         it: `{hits} dei {needed} giri che servono` },
    "plan.now":        { en: `now ~{s}s`, it: `ora ~{s}s` },
    "plan.best":       { en: `best {s}s`, it: `migliore {s}s` },
    "plan.nolaps":     { en: `no laps since you started it — go and drive`,
                         it: `nessun giro da quando l'hai avviato — vai a guidare` },
    "plan.willmeasure":{ en: `start it and every lap from then on is measured against this`,
                         it: `avvialo e da lì in poi ogni giro viene misurato su questo` },
    "plan.done":       { en: `✓ done`, it: `✓ fatto` },

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
    "tour.a2.x": { en: `The same laps seen other ways: traces side by side in Compare, the racing line on the Map, corner by corner in Line, split times in Sectors, grip and slip in Dynamics, and where you're heading in Trends.`,
                   it: `Gli stessi giri visti in altri modi: le tracce affiancate in Confronto, la traiettoria sulla Mappa, curva per curva in Traiettoria, gli split nei Settori, aderenza e slittamenti in Dinamica, e dove stai andando in Andamento.` },
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

    "eng.hint":        { en: `The diagnosis comes from the coach in real time (start <b>Coach Live</b> or the <b>backend</b>). The changes on the right apply to the setup file: they must be <b>loaded in the pits</b>, they don't change the car while you drive.`,
                         it: `La diagnosi arriva dal coach in tempo reale (avvia <b>Coach Live</b> o il <b>backend</b>). Le modifiche a destra agiscono sul file di setup: vanno <b>caricate ai box</b>, non cambiano l'auto mentre guidi.` },

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
    "eng.lowConf":     { en: `Low confidence — based on little data. Gather a few more clean laps before applying.`,
                         it: `Confidenza bassa — pochi dati. Raccogli qualche altro giro pulito prima di applicare.` },
    "eng.dash":        { en: `—`, it: `—` },
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
    "eng.loadErr":     { en: `Setup loading error: `, it: `Errore caricamento setup: ` },

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
