"use strict";
// HONE i18n — tiny, vanilla, 100% offline (no CDN, no libraries, no build step).
//
//   window.HoneI18n = { lang, t(key), set(lang) }
//
// `lang` is the app language, written into the page by the server as
// window.HONE_LANG (default "en" if the page was not served by HONE). The
// browser keeps no language of its own. `t(key)` returns the
// string in the active language, falling back EN -> key. Static UI is tagged in
// the HTML with data-i18n* attributes; applyStatic() walks the DOM and fills them.
// Strings injected by app.js / engineer.js / tour.js call HoneI18n.t(key) directly.
//
// IMPORTANT: this file only covers UI "chrome". Backend-generated content
// (debrief why/fix, engineer rationale, focus messages, level labels) is NOT
// translated here — it will be localised on the Python side; the pages already
// pass &lang=<lang> to /api so those land in the right language when ready.
(function () {
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
    "cb.label":        { en: `Colour-blind palette (blue and orange)`,
                         it: `Colori per daltonici (blu e arancio)` },
    "demo.banner":     { en: `These are sample laps made by HONE, not yours.`, it: `Questi sono giri di esempio generati da HONE, non i tuoi.` },

    // ---- analysis page (index.html) ----
    "title.analysis":  { en: `HONE · Analysis`, it: `HONE · Analisi` },
    "app.subtitle":    { en: `· Analysis`, it: `· Analisi` },
    "ctl.combo":       { en: `Car / Track`, it: `Auto / Pista` },
    "ctl.lap":         { en: `Lap to review`, it: `Giro da rivedere` },
    "ctl.baseline":    { en: `Compare with`, it: `Confronta con` },
    "ctl.export":      { en: `Export`, it: `Esporta` },


    // ---- la Pagella, la prima pagina del report ----
    // Il tono è quello deciso col pilota (spec «Il tono dei testi»): frasi
    // brevi col tu, i numeri con l'unità, niente slogan né due punti a
    // effetto, mai la stessa frase in due posti. Le frasi con i numeri del
    // pilota dentro (il verdetto, i nomi dei difetti) le scrive il backend
    // (coaching/howto.py); qui c'è solo quello che la pagina mette intorno.
    "tab.pagella":     { en: `Report card`, it: `Pagella` },
    // I tre gruppi della barra, nell'ordine deciso col pilota.
    "tabgroup.today":  { en: `How today went`, it: `Com'è andata oggi` },
    "tabgroup.why":    { en: `Why, in detail`, it: `Perché, nel dettaglio` },
    "tabgroup.time":   { en: `Over time`, it: `Nel tempo` },
    "load.pagella":    { en: `Reading your session…`, it: `Sto leggendo la sessione…` },
    // La seconda frase di ogni «non riesco a caricare»: una chiave sola, la
    // stessa domanda in quattro chiavi era la stessa frase in quattro posti.
    "err.backend":     { en: `Check that the analysis server is running.`,
                         it: `Controlla che il server di analisi sia acceso.` },
    "err.pagella":     { en: `Couldn't load the Report card.`,
                         it: `Non riesco a caricare la Pagella.` },
    "pag.nolaps":      { en: `You have no laps on this car and track yet.`,
                         it: `Per questa auto e questa pista non hai ancora giri registrati.` },
    "pag.laps":        { en: `{laps} {laps|lap|laps} ({valid} valid)`,
                         it: `{laps} {laps|giro|giri} ({valid} {valid|valido|validi})` },
    "pag.wet":         { en: `wet`, it: `bagnato` },
    "pag.ref":         { en: `Measured against your reference lap, {time} from {when}.`,
                         it: `Misurata sul tuo giro di riferimento, {time} del {when}.` },
    "pag.defects":     { en: `Your main faults`, it: `I tuoi difetti principali` },
    "pag.defects.none": { en: `No habit costs you time lap after lap in this session.`,
                          it: `In questa sessione nessuna abitudine ti costa tempo giro dopo giro.` },
    "pag.def.where":   { en: `In {n} {n|corner|corners}, on {w} of {l} {l|lap|laps}`,
                         it: `In {n} {n|curva|curve}, {w} {w|giro|giri} su {l}` },
    "pag.def.laps":    { en: `On {w} of {l} {l|lap|laps}`, it: `In {w} {w|giro|giri} su {l}` },
    "pag.def.perlap":  { en: `a lap`, it: `a giro` },
    // Il veleggio non è tempo perso, è tempo passato senza pedali: lo dice.
    "pag.def.coast":   { en: `of coasting a lap`, it: `di veleggio a giro` },
    "pag.trend.down":  { en: `Down on the previous session`, it: `In calo rispetto alla sessione prima` },
    "pag.trend.same":  { en: `Same as the previous session`, it: `Come nella sessione prima` },
    "pag.trend.up":    { en: `Up on the previous session`, it: `In crescita rispetto alla sessione prima` },
    "pag.spark":       { en: `Your last sessions, the oldest on the left`,
                         it: `Le tue ultime sessioni, la più vecchia a sinistra` },
    "pag.spark.cut":   { en: `{v}, off the scale`, it: `{v}, fuori scala` },
    "pag.worst":       { en: `Where you lose most`, it: `Dove sbagli di più` },
    "pag.worst.none":  { en: `No corner costs you time in this session.`,
                         it: `In questa sessione nessuna curva ti costa tempo.` },
    "pag.errors":      { en: `Most frequent mistakes`, it: `Errori più frequenti` },
    "pag.errors.none": { en: `No mistakes counted in this session.`,
                         it: `In questa sessione non ho contato errori.` },
    "pag.plan":        { en: `The plan for your next run`, it: `Il piano per la prossima uscita` },
    // La regola vale per tutta la lista: si dice una volta, sopra la lista.
    "pag.plan.rule":   { en: `Work on one tip at a time, in order.`,
                         it: `Lavora su un consiglio alla volta, nell'ordine.` },
    "pag.plan.none":   { en: `Nothing in the plan for now. No fault repeats often enough.`,
                         it: `Per ora nel piano non c'è niente. Nessun difetto si ripete abbastanza.` },
    // Le curve senza preposizione davanti: «da Variante Alta» suona sbagliato
    // come «In Rivazza» (la regola già presa per il «Come si fa»).
    "pag.adv.from":    { en: `{first}, then {rest}`, it: `{first}, poi {rest}` },
    "pag.adv.lap":     { en: `Across the whole lap`, it: `Su tutto il giro` },
    "pag.adv.target":  { en: `target under {v} a lap`, it: `obiettivo sotto {v} a giro` },
    "pag.adv.target.coast": { en: `target under {v} of coasting a lap`,
                              it: `obiettivo sotto {v} di veleggio a giro` },
    "pag.adv.active":  { en: `In progress`, it: `In corso` },
    "pag.adv.reached": { en: `Done`, it: `Raggiunto` },
    "pag.adv.progress": { en: `Under the target on {hits} of {laps} {laps|lap|laps}. It takes {needed} to close it.`,
                          it: `Sotto l'obiettivo in {hits} {hits|giro|giri} su {laps}. Per chiuderlo ne servono {needed}.` },
    "pag.adv.nolaps":  { en: `No laps yet since you started it.`,
                         it: `Da quando lo segui non hai ancora girato.` },
    "pag.adv.follow":  { en: `I'll follow it`, it: `Lo seguo` },
    "pag.adv.decline": { en: `Not for me`, it: `Non lo seguo` },
    "pag.adv.drop":    { en: `Drop it`, it: `Lascio stare` },
    "pag.adv.err":     { en: `Your choice wasn't saved. The plan below is as it stands now.`,
                         it: `La scelta non si è salvata. Il piano qui sotto è com'è adesso.` },
    // I rimandi dalle schede al consiglio che segui (spec: rimandi).
    // I nomi delle curve aprono la riga, fuori dalla frase.
    "adv.compare.brake_early": { en: `On the brake chart, look at where your trace starts compared with the reference. The “Your braking points” panel shows your braking point lap by lap.`,
                               it: `Nel grafico del freno guarda dove parte la tua traccia rispetto al riferimento. Il riquadro «Le tue frenate» ha il punto di stacco giro per giro.` },
    "adv.compare.brake_late": { en: `Read the brake and speed charts together. A later braking point that lowers your minimum speed doesn't pay off.`,
                              it: `Guarda freno e velocità insieme. Una staccata più tarda che abbassa la velocità minima non paga.` },
    "adv.compare.over_brake": { en: `Compare how high your brake trace goes, and how long it stays there, with the reference.`,
                              it: `Guarda quanto in alto arriva la tua traccia del freno e quanto ci resta, rispetto al riferimento.` },
    "adv.compare.throttle_late": { en: `On the throttle chart, look at when you get back on the power on the way out, compared with the reference.`,
                                 it: `Nel grafico del gas guarda quando torni a spingere in uscita, rispetto al riferimento.` },
    "adv.compare.min_speed": { en: `Look at the lowest point of the speed trace. The minimum speed table gives it in numbers.`,
                             it: `Guarda il punto più basso della velocità. La tabella delle velocità minime lo dà in numeri.` },
    "adv.compare.lift": { en: `The straight-line notes in the debrief show where you lift and what it costs you.`,
                        it: `Le note sul dritto nel debrief dicono dove alzi il gas e quanto ti costa.` },
    "adv.line.brake_early": { en: `The brake marker shows where you start braking and where the reference does.`,
                            it: `Il segno del freno mostra dove stacchi tu e dove stacca il riferimento.` },
    "adv.line.brake_late": { en: `Compare the braking point with the line through mid-corner. If you brake late and run wide, the line shows it.`,
                           it: `Confronta il punto di stacco con la linea a centro curva. Se stacchi tardi e allarghi, la linea lo mostra.` },
    "adv.line.throttle_late": { en: `The throttle marker shows where you get back on the power, you and the reference.`,
                              it: `Il segno del gas mostra dove torni a spingere, tu e il riferimento.` },
    "adv.line.min_speed": { en: `Look at where your minimum speed falls and how tight your line is compared with the reference.`,
                          it: `Guarda dove cade la velocità minima e quanto è stretta la tua linea rispetto al riferimento.` },
    "adv.sectors.one": { en: `It's in sector {n}. That sector's time tells you whether the work on the corner reaches your lap time.`,
                       it: `È nel settore {n}. Il tempo di quel settore ti dice se il lavoro sulla curva arriva al giro.` },
    "adv.sectors.same": { en: `They're in sector {n}. That sector's time tells you whether the work on these corners reaches your lap time.`,
                        it: `Sono nel settore {n}. Il tempo di quel settore ti dice se il lavoro su queste curve arriva al giro.` },
    "adv.sectors.many": { en: `They're in sectors {list}. Those sectors' times tell you whether the work on these corners reaches your lap time.`,
                        it: `Sono nei settori {list}. I tempi di quei settori ti dicono se il lavoro su queste curve arriva al giro.` },
    "adv.dynamics.coasting": { en: `The coasting box shows how long you spend off both pedals.`,
                             it: `Il riquadro del veleggio dice quanto tempo passi senza gas né freno.` },
    "adv.dynamics.throttle_late": { en: `On the way out, look at rear wheel slip. If it stays low and TC isn't working, you have room to get on the throttle earlier.`,
                                  it: `In uscita guarda lo slittamento delle ruote posteriori. Se resta basso e il TC non interviene, hai margine per tornare prima sul gas.` },
    "adv.progress.corners": { en: `In the fault history, the marked row is your tip. Further down, the cards for these corners show how it goes session by session.`,
                            it: `Nello storico dei difetti la riga segnata è il tuo consiglio. Più sotto, le schede di queste curve dicono come va sessione per sessione.` },
    "adv.progress.lap": { en: `In the fault history, the marked row is the tip you're following, session by session.`,
                        it: `Nello storico dei difetti la riga segnata è il consiglio che segui, sessione per sessione.` },
    "adv.and": { en: `and`, it: `e` },
    "adv.goto": { en: `Show me`,
                it: `Vai al punto` },
    "adv.mark.title": { en: `Corner in the tip you're following`,
                      it: `Curva del consiglio che segui` },
    "pag.howto":       { en: `How to do it →`, it: `Come si fa →` },
    "pag.declined":    { en: `You set these aside.`, it: `Hai messo da parte questi consigli.` },
    // Il suggerimento sul nome di un difetto nello storico: dove porta il clic.
    "dh.open":         { en: `Open “How to do it” for this fault`,
                         it: `Apri «Come si fa» per questo difetto` },
    "pag.undecline":   { en: `Take it back`, it: `Riprendi` },

    // ---- Andamento: i difetti sessione per sessione ----
    "dh.title":        { en: `Your faults, session by session`,
                         it: `I tuoi difetti, sessione per sessione` },
    "dh.ref":          { en: `Every session is measured against your reference lap, {time} from {when}. The lower the bar, the less the fault costs you.`,
                         it: `Ogni sessione è misurata contro il tuo giro di riferimento, {time} del {when}. Più bassa è la barra, meno ti costa il difetto.` },
    "dh.skipped.wet":  { en: `Your last session was in the wet, and there is no wet history here. Below are your dry sessions.`,
                         it: `La tua ultima sessione era sul bagnato, e qui non c'è uno storico sul bagnato. Sotto vedi le sessioni sull'asciutto.` },
    "dh.skipped.dry":  { en: `Your last session was in the dry, and the history here is all in the wet. Below are your wet sessions.`,
                         it: `La tua ultima sessione era sull'asciutto, e qui lo storico è tutto sul bagnato. Sotto vedi le sessioni sul bagnato.` },
    "dh.first":        { en: `There is one session measured here so far. The trend starts from the next one.`,
                         it: `Per ora qui c'è una sessione misurata. L'andamento parte dalla prossima.` },
    "dh.none":         { en: `No fault has cost you time lap after lap in these sessions.`,
                         it: `In queste sessioni nessun difetto ti è costato tempo giro dopo giro.` },
    "dh.nolaps":       { en: `You have no valid laps on this car and track yet.`,
                         it: `Per questa auto e questa pista non hai ancora giri validi.` },
    "dh.noref":        { en: `To measure your faults you need at least one more valid lap besides your reference.`,
                         it: `Per misurare i difetti serve almeno un altro giro valido oltre al tuo riferimento.` },
    "dh.valid":        { en: `{n} valid {n|lap|laps}`, it: `{n} {n|giro valido|giri validi}` },
    "load.dh":         { en: `Reading your sessions…`, it: `Sto leggendo le sessioni…` },
    "err.dh":          { en: `Couldn't load your faults.`,
                         it: `Non riesco a caricare i difetti.` },

    // ---- «Come si fa», la vista di un consiglio ----
    // Stesso tono della Pagella. Il problema, il come si fa e l'esercizio li
    // scrive il backend (coaching/howto.py); qui le cornici e le frasi che
    // prendono il posto di una figura quando manca un dato.
    "load.howto":      { en: `Reading your laps…`, it: `Sto leggendo i tuoi giri…` },
    "err.howto":       { en: `Couldn't load this page.`,
                         it: `Non riesco a caricare questa pagina.` },
    "howto.back":      { en: `← Back to the Report card`, it: `← Torna alla Pagella` },
    "howto.noproblem": { en: `In this session I don't have a number for this fault.`,
                         it: `In questa sessione non ho un numero per questo difetto.` },
    "howto.ref":       { en: `Everything here is measured against your best lap, {time} from {when}.`,
                         it: `Qui tutto è misurato sul tuo giro migliore, {time} del {when}.` },
    "howto.figs":      { en: `From your laps`, it: `Dai tuoi giri` },
    "howto.leg.you":   { en: `your usual lap in this session`, it: `il tuo giro solito di questa sessione` },
    "howto.leg.best":  { en: `your best lap`, it: `il tuo giro migliore` },
    "howto.nofig":     { en: `In this session there's no corner to show you for this fault.`,
                         it: `In questa sessione non ho curve da mostrarti per questo difetto.` },
    "howto.nofig.lap": { en: `This fault isn't in one corner, it adds up over the whole lap. There's no corner to draw.`,
                         it: `Questo difetto non sta in una curva, si somma su tutto il giro. Non c'è una curva da disegnare.` },
    "howto.corner":    { en: `Corner {n}`, it: `Curva {n}` },
    "howto.brakepts":  { en: `You usually start braking {t} m from the line, on your best lap at {b} m.`,
                         it: `Di solito cominci a frenare a {t} m dal traguardo, nel giro migliore a {b} m.` },
    "howto.nomap":     { en: `One of the two laps has no coordinates, so there's no map of this corner.`,
                         it: `Uno dei due giri non ha le coordinate, quindi la mappa della curva non c'è.` },
    "howto.notrace":   { en: `One of the two laps didn't record {what}, so there's no chart.`,
                         it: `Uno dei due giri non ha registrato {what}, quindi il grafico non c'è.` },
    "howto.nolap":     { en: `I can't read these two laps.`, it: `Non riesco a leggere questi due giri.` },
    "howto.ch.brake":  { en: `the brake`, it: `il freno` },
    "howto.ch.throttle": { en: `the throttle`, it: `il gas` },
    "howto.ch.speed":  { en: `the speed`, it: `la velocità` },
    "howto.tr.brake":  { en: `Brake pedal`, it: `Pedale del freno` },
    "howto.tr.throttle": { en: `Throttle pedal`, it: `Pedale del gas` },
    "howto.tr.speed":  { en: `Speed, km/h`, it: `Velocità, km/h` },
    "howto.how":       { en: `The technique`, it: `La tecnica` },
    "howto.drill":     { en: `The drill`, it: `L'esercizio` },
    "howto.laps":      { en: `{n} {n|lap|laps}.`, it: `{n} {n|giro|giri}.` },
    // Una frase intera, sulla riga sua: è il numero che il pilota porta in pista.
    "howto.target":    { en: `Aim for under {v} a lap.`,
                         it: `L'obiettivo è stare sotto {v} a giro.` },
    "howto.target.coast": { en: `Aim to coast for less than {v} a lap.`,
                            it: `L'obiettivo è veleggiare meno di {v} a giro.` },
    "howto.prog":      { en: `How it's going`, it: `Come sta andando` },
    "howto.gloss":     { en: `Glossary`, it: `Glossario` },
    "howto.prog.lead": { en: `This fault in each session since you started following it, the oldest first.`,
                         it: `Questo difetto in ogni sessione da quando lo segui, dalla più vecchia.` },
    "howto.prog.none": { en: `It shows here from the first session after you press “I'll follow it”.`,
                         it: `Qui lo vedi dalla prima sessione dopo che hai premuto «Lo seguo».` },

    "tab.flow":        { en: `Lap explained`, it: `Il giro spiegato` },
    // Il passo del giro guidato che apre Il giro spiegato: il titolo dice
    // cosa è («Parti da qui» sta su tour.a12, la Pagella).
    "tour.a9.t":       { en: `Lap explained`, it: `Il giro spiegato` },
    "tour.a9.x":       { en: `The lap explained one step at a time. It tells you what cost you most, why and what to do, and shows you the chart. The other tabs hold the same findings for you to read on your own.`,
                         it: `Il giro spiegato un passo alla volta. Ti dice cosa ti è costato di più, perché e cosa fare, e ti mostra il grafico. Nelle altre schede trovi gli stessi dati, da leggere per conto tuo.` },
    "tour.a12.t":      { en: `Start here`, it: `Parti da qui` },
    // Says what the tab IS, not what is on it right now. The tour can be
    // started on any run, and on a run with nothing measurable this step lands
    // on a panel holding one sentence — six of the seventeen real sessions are
    // like that, and so was every session of the demo until the demo grew a
    // measurable one. "Five numbers that add up" was therefore false at the
    // exact moment a first-time driver read it. The property is still stated,
    // as what the tab does when it can measure, and the empty case is named.
    "tour.a12.x":      { en: `How the session went, before you forget it. How much you lost to your reference lap, the habits that cost you time, where and how often you go wrong. Below that is the plan for your next run, one tip at a time. When a session can't be judged, this page says why.`,
                         it: `Com'è andata la sessione, prima di dimenticarla. Quanto hai perso sul tuo giro di riferimento, le abitudini che ti costano tempo, dove e quante volte sbagli. Sotto c'è il piano per la prossima uscita, un consiglio alla volta. Quando una sessione non si può giudicare, qui c'è scritto perché.` },
    "tab.session":     { en: `Session`, it: `Sessione` },
    "tab.compare":     { en: `Compare`, it: `Confronto` },
    // One run of laps, as it was driven.
    "ses.which":       { en: `Session`, it: `Sessione` },
    "ses.none":        { en: `No laps recorded for this car and track yet.`,
                         it: `Nessun giro registrato per questa auto e questa pista.` },
    "ses.sub":         { en: `{laps} {laps|lap|laps} · {valid} valid · {mins} min`,
                         it: `{laps} {laps|giro|giri} · {valid} {valid|valido|validi} · {mins} min` },
    "ses.sub_temp":    { en: `track {from} → {to}`, it: `asfalto {from} → {to}` },
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
    "ses.first":       { en: `This is your first session on this car and track. There's nothing to compare it with yet.`,
                         it: `È la prima sessione su questa auto e questa pista. Non c'è ancora niente con cui confrontarla.` },
    "ses.nomoves":     { en: `No corner moved enough to be worth reporting.`,
                         it: `Nessuna curva si è mossa abbastanza da valere una segnalazione.` },
    "ses.nobest":      { en: `No lap in this session could count, so there's nothing to measure.`,
                         it: `In questa sessione nessun giro poteva contare, quindi non c'è niente da misurare.` },
    // Race pace: one run on one tank. The wording is careful on purpose — every
    // number on this tab is the NET of fuel burning off and tyres giving up, so
    // nothing here is allowed to be called degradation.
    "tab.stint":       { en: `Race pace`, it: `Passo gara` },
    "st.which":        { en: `Stint`, it: `Stint` },
    "st.chart":        { en: `Pace across the stint <small>(each dot is a lap, the faded ones weren't at pace, the line is the measured drift)</small>`,
                         it: `Il passo lungo lo stint <small>(ogni punto è un giro, quelli sbiaditi non erano a passo, la retta è la deriva misurata)</small>` },
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
    "st.nopace":       { en: `No lap in this stint was at pace, so there's no pace to measure.`,
                         it: `Nessun giro di questo stint era a passo, quindi non ho un passo da misurare.` },
    // The guided flow: one finding at a time, with the chart that shows it.
    "flow.prev":       { en: `← Back`, it: `← Indietro` },
    "flow.next":       { en: `Next →`, it: `Avanti →` },
    "flow.whole":      { en: `Show the whole chart`, it: `Mostrami il grafico intero` },
    "flow.step":       { en: `Step {n} of {total}`, it: `Passo {n} di {total}` },
    "flow.cost":       { en: `You lose {s} s here, more than anywhere else.`,
                         it: `Qui perdi {s} s, più che in ogni altro punto.` },
    "flow.cost_more":  { en: `You lose {s} s here.`, it: `Qui perdi {s} s.` },
    "flow.fix":        { en: `What to do`, it: `Cosa fare` },
    "flow.empty":      { en: `Pick a lap to see it explained.`,
                         it: `Scegli un giro per vederlo spiegato.` },
    "flow.chart.speed":  { en: `Speed (white = you, cyan = reference)`,
                           it: `Velocità (bianco = tu, ciano = riferimento)` },
    "flow.chart.inputs": { en: `Throttle and brake (solid = you, dashed = reference)`,
                           it: `Gas e freno (pieno = tu, tratteggio = riferimento)` },
    "flow.chart.delta":  { en: `Gap across the lap (above the line = slower)`,
                           it: `Distacco sul giro (sopra la linea = più lento)` },
    "tab.sectors":     { en: `Sectors`, it: `Settori` },
    "tab.dynamics":    { en: `Dynamics`, it: `Dinamica` },
    "tab.trends":      { en: `Trends`, it: `Andamento` },

    // ---- dynamics tab (G-G, lock/spin, coasting) ----
    "dyn.readout":     { en: `Hover the charts to read G and slip at any point.`,
                         it: `Passa il mouse sui grafici per leggere G e slip in ogni punto.` },
    "chart.gg":        { en: `G-G diagram <small>(each dot is a moment, the further from the centre the more grip you're using, the ring is your peak)</small>`,
                         it: `Diagramma G-G <small>(ogni punto è un istante, più è lontano dal centro più grip stai usando, l'anello è il tuo picco)</small>` },
    "chart.slip":      { en: `Locking and wheelspin <small>(slip ratio, cyan for the fronts and amber for the rears. Below zero the wheel locks, above it spins. The bar underneath is ABS or TC stepping in.)</small>`,
                         it: `Bloccaggio e pattinamento <small>(slip ratio, ciano le anteriori e arancio le posteriori. Sotto lo zero la ruota blocca, sopra pattina. La barretta in basso è l'ABS o il TC che interviene.)</small>` },
    "dyn.missing":     { en: `This lap was recorded before HONE saved G and slip, so there's nothing to draw. Drive a new lap to see them.`,
                         it: `Questo giro è stato registrato prima che HONE salvasse i G e lo slip, quindi non c'è niente da disegnare. Guida un giro nuovo per vederli.` },
    // NON «in folle»: in italiano vuol dire cambio in posizione neutra, che è
    // un'altra cosa da quella che il canale misura (né gas né freno, marcia
    // inserita). «Veleggio» è la parola che usano la Pagella e il rimando
    // al riquadro («Il riquadro del veleggio»): una cosa sola, un nome solo.
    "dyn.coasting":    { en: `Coasting`, it: `Veleggio` },
    "dyn.trail":       { en: `Trail-braking`, it: `Trail-braking` },
    "dyn.gmax":        { en: `Peak grip`, it: `Grip di picco` },
    "dyn.ofLap":       { en: `of the lap`, it: `del giro` },
    "dyn.hint":        { en: `time on neither pedal`, it: `tempo senza gas né freno` },
    "dyn.gg.accel":    { en: `accel`, it: `accel.` },
    "dyn.gg.brake":    { en: `brake`, it: `freno` },
    "dyn.gg.lat":      { en: `lateral`, it: `laterale` },
    "dyn.slip.spin":   { en: `spins`, it: `pattina` },
    "dyn.slip.lock":   { en: `locks`, it: `blocca` },
    "dyn.ro.g":        { en: `G`, it: `G` },
    "dyn.ro.lat":      { en: `lat`, it: `lat` },
    "dyn.ro.lon":      { en: `lon`, it: `lon` },
    "dyn.ro.slipF":    { en: `Slip front`, it: `Slip ant` },
    "dyn.ro.slipR":    { en: `Slip rear`, it: `Slip post` },
    // Il grafico che stava in Dinamica è stato rimosso il 05/08: era lo
    // stesso canale della Traiettoria, con una didascalia che si rifiutava
    // di dire da che parte. Restano il rimando e il bottone.
    "lineoff.elsewhere": { en: `How far you stray from the line is in the Line tab, which also tells you on which side.`,
                           it: `Quanto ti allontani dalla linea lo trovi nella scheda Traiettoria, che ti dice anche da che parte.` },
    "lineoff.goto":    { en: `Open Line`, it: `Apri Traiettoria` },
    "dyn.tyre.header": { en: `Tyres across this lap <small>(core temperature and pressure corner by corner, dashed = right side)</small>`,
                         it: `Gomme lungo questo giro <small>(temperatura della mescola e pressione curva per curva, tratteggio = lato destro)</small>` },
    "chart.balance":   { en: `Balance <small>(the colour shows how the car behaves along the racing line)</small>`,
                         it: `Bilanciamento <small>(il colore dice come si comporta l'auto lungo la traiettoria)</small>` },
    "bal.under":       { en: `understeer`, it: `sottosterzo` },
    "bal.over":        { en: `oversteer`, it: `sovrasterzo` },
    "dyn.ro.off":      { en: `Off the line`, it: `Fuori linea` },

    "prog.consistency":{ en: `Corner consistency <small>(spread of your min speed per corner · wider = less repeatable)</small>`,
                         it: `Costanza per curva <small>(dispersione della velocità minima per curva · più larga = meno ripetibile)</small>` },
    "cons.none":       { en: `Not enough laps yet to measure how consistent you are in each corner.`,
                         it: `Hai ancora troppo pochi giri per misurare la costanza curva per curva.` },
    "cons.spread":     { en: `spread`, it: `dispersione` },

    "chart.yaw":       { en: `Rotation and steering <small>(orange = the car's yaw, white = steering, the two should move together)</small>`,
                         it: `Rotazione e sterzo <small>(arancio = imbardata dell'auto, bianco = sterzo, le due linee dovrebbero seguirsi)</small>` },
    // «Cambiata», non «scalata su»: in italiano scalare vuol già dire scendere
    // di marcia. I triangoli sono a parole perché ▲▼ nel testo sono simboli.
    "chart.rpm":       { en: `Revs and shifts <small>(rpm across the lap, the triangles pointing up are upshifts and those pointing down are downshifts)</small>`,
                         it: `Giri motore e cambiate <small>(rpm lungo il giro, i triangoli in su sono le cambiate e quelli in giù le scalate)</small>` },
    "wf.title":        { en: `Where the lap went <small>(time lost per corner, biggest first)</small>`,
                         it: `Dov'è finito il giro <small>(tempo perso per curva, dal peggiore)</small>` },
    "dyn.smooth":      { en: `Steering corrections`, it: `Correzioni di sterzo` },
    "dyn.smoothUnit":  { en: `direction changes`, it: `cambi di direzione` },

    "readout.hint":    { en: `Hover the charts to read the values point by point.`,
                         it: `Passa il mouse sui grafici per leggere i valori punto per punto.` },

    "chart.delta":     { en: `Lap delta, in seconds <small>(above the line = slower, below = faster)</small>`,
                         it: `Delta sul giro, in secondi <small>(sopra la linea = più lento, sotto = più veloce)</small>` },
    "chart.speed":     { en: `Speed <small>(km/h, white = reviewed lap, cyan = comparison)</small>`,
                         it: `Velocità <small>(km/h, bianco = giro in esame, ciano = confronto)</small>` },
    "chart.inputs":    { en: `Throttle and brake <small>(green = throttle, red = brake, dashed = reference)</small>`,
                         it: `Gas e freno <small>(verde = gas, rosso = freno, tratteggio = riferimento)</small>` },
    "chart.steer":     { en: `Steering <small>(white = reviewed lap, cyan = comparison, left is up and right is down)</small>`,
                         it: `Sterzo <small>(bianco = giro in esame, ciano = confronto, sinistra in su e destra in giù)</small>` },
    "steer.none":      { en: `This lap has no steering data.`, it: `In questo giro non c'è il dato dello sterzo.` },

    "map.readout":     { en: `Red marks where you're slower than the reference, green where you're faster. Hover the map for the values.`,
                         it: `Il rosso segna dove sei più lento del riferimento, il verde dove sei più veloce. Passa il mouse sulla mappa per i valori.` },
    "chart.map":       { en: `Track map <small>(solid line = reviewed lap, white dashes = reference)</small>`,
                         it: `Mappa della pista <small>(linea continua = giro in esame, tratteggio bianco = riferimento)</small>` },
    "map.grad.fast":   { en: `faster`, it: `più veloce` },
    "map.grad.slow":   { en: `slower`, it: `più lento` },
    "map.grad.note":   { en: `the line is thicker where the speed gap is bigger`,
                         it: `la linea è più spessa dove lo scarto di velocità è maggiore` },
    "map.leg.you":     { en: `your braking`, it: `la tua frenata` },
    "map.leg.ref":     { en: `reference braking`, it: `frenata di riferimento` },
    "map.missing":     { en: `One of the two laps has no coordinates, so the map can't be drawn. Drive a new lap and you'll see it here.`,
                         it: `Uno dei due giri non ha le coordinate, quindi la mappa non si può disegnare. Guida un giro nuovo e qui la vedrai.` },
    "rail.nomap":      { en: `Without the coordinates of one of the two laps there's no map. The corners below still work.`,
                         it: `Senza le coordinate di uno dei due giri la mappa non c'è. Le curve qui sotto funzionano lo stesso.` },
    "rail.whole":      { en: `Whole lap`, it: `Tutto il giro` },
    "rail.clean":      { en: `nothing lost here`, it: `qui non hai perso niente` },

    // ---- braking sheet (under the track map) ----
    // Your own braking points, measured. The wording carries the caveats the
    // static sheets going round the forums don't: how many laps, which asphalt
    // temperature, and that the metres are an approximation.
    "brk.title":       { en: `Your braking points`, it: `Le tue frenate` },
    "brk.sub":         { en: `measured on your last {laps} {laps|lap|laps}`,
                         it: `misurate sui tuoi ultimi {laps} {laps|giro|giri}` },
    "brk.temp1":       { en: `track {from}`, it: `asfalto {from}` },
    "brk.noTemp":      { en: `track temperature not recorded on these laps`,
                         it: `temperatura dell'asfalto non registrata su questi giri` },
    "brk.none":        { en: `I couldn't measure a braking point yet. Drive a couple of clean laps with this car on this track.`,
                         it: `Non ho ancora potuto misurare un punto di frenata. Fai un paio di giri puliti con questa auto su questa pista.` },
    "brk.repeatable":  { en: `same every lap`, it: `uguale ogni giro` },
    "brk.c.corner":    { en: `Corner`, it: `Curva` },
    "brk.c.speed":     { en: `You brake at`, it: `Freni a` },
    "brk.c.gear":      { en: `Gear`, it: `Marcia` },
    "brk.c.landmark":  { en: `Visual reference`, it: `Riferimento visivo` },
    "brk.c.zone":      { en: `Braking zone`, it: `Staccata` },
    "brk.c.vmin":      { en: `Min speed / gear`, it: `Minima / marcia` },
    "brk.c.spread":    { en: `Spread`, it: `Dispersione` },
    "brk.note":        { en: `Speed is a braking reference every car gives you, right on the dash. The spread is how far your braking point moves from lap to lap. The metres beside it turn that into distance in this braking zone.`,
                         it: `La velocità è un riferimento di frenata che hai su ogni auto, e la leggi sul cruscotto. La dispersione dice di quanto si sposta il tuo punto di frenata da un giro all'altro, e i metri accanto la traducono su questa staccata.` },
    "brk.csv.title":   { en: `Download this sheet as a spreadsheet`,
                         it: `Scarica questa scheda come foglio di calcolo` },
    "brk.print.title": { en: `Print just this sheet`, it: `Stampa solo questa scheda` },
    "brk.print":       { en: `Print`, it: `Stampa` },

    // ---- line / trajectory tab ----
    // The map beside Compare shows the whole lap and leaves the reading to the
    // eye; this one zooms one corner at a time and puts the geometry in metres.
    // Wording for the per-corner tags is NOT here — it lives next to the numbers in trajectory.py,
    // so a template and its value can't drift apart.
    "tab.line":        { en: `Line`, it: `Traiettoria` },
    "line.readout":    { en: `Hover the corner to read your speed and how far you were from the reference line.`,
                         it: `Passa il mouse sulla curva per leggere la velocità e la distanza dalla linea di riferimento.` },
    "line.missing":    { en: `These laps were recorded before HONE saved coordinates. Drive a new lap to see your line here.`,
                         it: `Questi giri sono stati registrati prima che HONE salvasse le coordinate. Guida un giro nuovo per vedere qui la tua traiettoria.` },
    "line.leg.you":    { en: `your line`, it: `la tua traiettoria` },
    "line.leg.ref":    { en: `reference`, it: `riferimento` },
    "line.leg.band":   { en: `the gap between them`, it: `lo scarto fra le due` },
    // "{m} m wide" was the MEDIAN width, printed under corners drawn far wider:
    // at Spa's La Source the game's data says 24.5 m, because the paved run-off
    // is asphalt too. The picture was right and the caption contradicted it.
    "line.leg.road":   { en: `the asphalt, usually {m} m wide, which counts paved run-off but not kerbs`,
                         it: `l'asfalto, di norma largo {m} m, che comprende le vie di fuga ma non i cordoli` },
    // Due frasi perche' sono due cose diverse. Quella sopra descrive un
    // corridoio ricavato allargando la linea dell'IA; questa descrive la
    // strada, presa dal modello con cui il gioco decide dove sei.
    "line.leg.mesh":   { en: `the track, its kerbs and what's beside it, as the game describes them`,
                         it: `la pista, i cordoli e cosa c'è di fianco, come li descrive il gioco` },
    "line.leg.apex":   { en: `your slowest point`, it: `il tuo punto più lento` },
    "line.leg.apexref":{ en: `the reference's`, it: `quello del riferimento` },
    "chart.offset":    { en: `Where you were on the road <small>(metres from the reference line, above = to its right, below = to its left)</small>`,
                         it: `Dove eri sulla strada <small>(metri dalla linea di riferimento, sopra = alla sua destra, sotto = alla sua sinistra)</small>` },
    "chart.curv":      { en: `How tight you are turning <small>(white = you, cyan = reference, further from the middle = tighter arc)</small>`,
                         it: `Quanto stai stringendo <small>(bianco = tu, ciano = riferimento, più lontano dal centro = arco più stretto)</small>` },
    "load.line":       { en: `Loading your line…`, it: `Caricamento traiettoria…` },
    "err.line":        { en: `Couldn't work out the line for these laps.`,
                         it: `Non riesco a calcolare la traiettoria di questi giri.` },
    "line.extra":      { en: `Extra distance`, it: `Strada in più` },
    "line.extraHint":  { en: `you drove {you} m, the reference {ref} m`,
                         it: `hai percorso {you} m, il riferimento {ref} m` },
    "line.mean":       { en: `Average off the line`, it: `Scarto medio dalla linea` },
    "line.worst":      { en: `Furthest from it`, it: `Punto più lontano` },
    "line.corners":    { en: `Corners measured`, it: `Curve misurate` },
    // Sides. "Inside/outside" is the only form a driver reads without translating
    // — which side of the road a plus sign means depends on which way the corner
    // goes, and that conversion is done server-side (see trajectory.py).
    "line.in":         { en: `inside`, it: `dentro` },
    "line.out":        { en: `outside`, it: `fuori` },
    "line.right":      { en: `right`, it: `destra` },
    "line.left":       { en: `left`, it: `sinistra` },
    "line.same":       { en: `on the line`, it: `sulla linea` },
    "line.sameSpot":   { en: `same place`, it: `stesso punto` },
    "line.apexFlat":   { en: `the bottom is flat for {m} m here`,
                         it: `qui il minimo è piatto per {m} m` },
    "line.apexOff":    { en: `no apex, because the car wasn't turning`,
                         it: `nessun apex, perché l'auto non stava curvando` },
    "map.leg.lost":    { en: `where the lap was lost`, it: `dove hai perso il giro` },
    "brk.mark.edit":   { en: `What do you look at when you brake here?`,
                         it: `Cosa guardi quando freni qui?` },
    "brk.mark.hint":   { en: `e.g. at the end of the green on the left`,
                         it: `es. alla fine del verde sulla sinistra` },
    "line.leg.brake":  { en: `braking starts (filled = you, hollow = reference)`,
                         it: `inizio frenata (pieno = tu, vuoto = riferimento)` },
    "line.leg.throttle": { en: `back on the power (filled = you, hollow = reference)`,
                           it: `riapertura del gas (pieno = tu, vuoto = riferimento)` },
    "line.name.edit":  { en: `Name this corner`, it: `Dai un nome a questa curva` },
    "line.name.hint":  { en: `What you call it. You'll see it everywhere and hear it from the coach.`,
                         it: `Il nome che usi tu. Lo vedrai ovunque e lo sentirai dal coach.` },
    "line.name.save":  { en: `Save`, it: `Salva` },
    "line.name.drop":  { en: `Remove`, it: `Togli` },
    "line.name.err":   { en: `couldn't save the name`, it: `il nome non si è salvato` },
    // Il primo chip della Traiettoria: lo stato di partenza, non l'assenza
    // di una selezione.
    "range.clear":     { en: `Back to the whole lap`, it: `Torna al giro intero` },
    "line.whole":      { en: `Whole lap`, it: `Tutto il giro` },
    "line.mag":        { en: `gap`, it: `scarto` },
    "line.mag.note":   { en: `gap drawn ×{n}, but the scale bar is real distance`,
                         it: `scarto ingrandito ×{n}, ma la barra di scala è reale` },
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
    "line.table":      { en: `Every corner, in metres <small>(+ = inside, − = outside the reference line)</small>`,
                         it: `Tutte le curve, in metri <small>(+ = dentro, − = fuori dalla linea di riferimento)</small>` },
    "line.csv":        { en: `CSV`, it: `CSV` },
    "line.csv.title":  { en: `Download this table as a spreadsheet`,
                         it: `Scarica questa tabella come foglio di calcolo` },
    "line.t.corner":   { en: `Corner`, it: `Curva` },
    "line.t.apex":     { en: `Apex`, it: `Apex` },
    "line.t.entry":    { en: `Entry`, it: `Ingresso` },
    "line.t.apexoff":  { en: `Apex`, it: `Apex` },
    "line.t.exit":     { en: `Exit`, it: `Uscita` },
    "line.t.radius":   { en: `Arc (m)`, it: `Arco (m)` },
    "line.t.extra":    { en: `Distance`, it: `Strada` },
    "line.t.vmin":     { en: `Min speed`, it: `Vel. min` },
    "line.none":       { en: `I couldn't measure any corner on these laps.`,
                         it: `Su questi giri non ho potuto misurare nessuna curva.` },
    "line.ro.off":     { en: `Off the line`, it: `Fuori linea` },
    "line.ro.radius":  { en: `Arc`, it: `Arco` },

    "sec.col.sector":  { en: `Sector`, it: `Settore` },
    "sec.col.time":    { en: `Time <small>(ref)</small>`, it: `Tempo <small>(rif)</small>` },
    "sec.col.delta":   { en: `Δ to the reference <small>(bars to the left = faster, to the right = slower)</small>`,
                         it: `Δ sul riferimento <small>(barre a sinistra = più veloce, a destra = più lento)</small>` },

    "prog.chart":      { en: `Lap times over time <small>(each dot is a lap, the green line is your best so far)</small>`,
                         it: `Tempi sul giro nel tempo <small>(ogni punto è un giro, la linea verde è il tuo migliore fino a lì)</small>` },
    "prog.weak":       { en: `Weak points <small>(corner by corner, train the systematic ones)</small>`,
                         it: `Punti deboli <small>(curva per curva, quelle sistematiche sono da allenare)</small>` },
    "prog.recurring":  { en: `Recurring mistakes`, it: `Errori ricorrenti` },

    "tyre.header":     { en: `Tyres across the stint <small>(core temperature and pressure, dashed = right side)</small>`,
                         it: `Le gomme lungo lo stint <small>(temperatura della mescola e pressione, tratteggio = lato destro)</small>` },
    "tyre.drift.temp": { en: `From first to last lap the temperature moved {f} at the front and {r} at the rear.`,
                         it: `Dal primo all'ultimo giro la temperatura cambia di {f} davanti e {r} dietro.` },
    "tyre.drift.press": { en: `From first to last lap the pressure moved {f} at the front and {r} at the rear.`,
                          it: `Dal primo all'ultimo giro la pressione cambia di {f} davanti e {r} dietro.` },
    "tyre.elsewhere":  { en: `Tyre temperatures and pressures are in Race pace, drawn over a single tank instead of your whole archive.`,
                         it: `Le temperature e le pressioni delle gomme le trovi in Passo gara, disegnate su un solo pieno invece che su tutto l'archivio.` },
    "tyre.goto":       { en: `Open Race pace`, it: `Apri Passo gara` },
    "tyre.temp":       { en: `Core temperature (°C)`, it: `Temperatura della mescola (°C)` },
    "tyre.press":      { en: `Pressure (psi)`, it: `Pressione (psi)` },
    "tyre.fl":         { en: `Front-left`, it: `Ant. sx` },
    "tyre.fr":         { en: `Front-right`, it: `Ant. dx` },
    "tyre.rl":         { en: `Rear-left`, it: `Post. sx` },
    "tyre.rr":         { en: `Rear-right`, it: `Post. dx` },

    "empty.title":     { en: `No laps yet`, it: `Ancora nessun giro` },
    "empty.step1":     { en: `Open HONE, go to <b>Drive</b> and press <b>Coach Live</b>.`,
                         it: `Apri HONE, vai su <b>In pista</b> e premi <b>Coach Live</b>.` },
    "empty.step2":     { en: `Drive a full, <b>valid</b> lap in AC or ACC.`,
                         it: `Guida un giro completo e <b>valido</b> in AC o ACC.` },
    "empty.step3":     { en: `Reload this page and your lap will be here, ready to analyse.`,
                         it: `Ricarica questa pagina e trovi qui il tuo giro da analizzare.` },
    "empty.hint":      { en: `Just want a look? From the source, <code>python accoach_main.py web --demo</code> shows sample laps.`,
                         it: `Vuoi solo dare un'occhiata? Dal sorgente, <code>python accoach_main.py web --demo</code> ti mostra giri di esempio.` },

    // ---- analysis page (app.js injected) ----
    "load.lap":        { en: `Loading lap…`, it: `Caricamento giro…` },
    "load.trends":     { en: `Loading trends…`, it: `Caricamento andamento…` },
    "load.sectors":    { en: `Loading sectors…`, it: `Caricamento settori…` },
    "combo.laps":      { en: `laps`, it: `giri` },
    "combo.best":      { en: `best`, it: `migliore` },
    "err.progress":    { en: `Couldn't load your trends.`,
                         it: `Non riesco a caricare l'andamento.` },
    "err.lap":         { en: `Couldn't load this lap.`, it: `Non riesco a caricare questo giro.` },

    "prog.validLaps":  { en: `Valid laps`, it: `Giri validi` },
    "prog.best":       { en: `Best`, it: `Migliore` },
    "prog.average":    { en: `Average`, it: `Media` },
    "prog.spread":     { en: `Spread`, it: `Escursione` },
    "prog.sigma":      { en: `σ`, it: `σ` },
    "prog.dash":       { en: `—`, it: `—` },
    "prog.noValid":    { en: `no valid lap`, it: `nessun giro valido` },

    "recur.none":      { en: `I found no mistakes in your recent laps.`,
                         it: `Nei tuoi ultimi giri non ho trovato errori.` },

    // The training plan. It lives on the Pagella now, one piece of advice at
    // a time; Trends only points there.
    "plan.elsewhere":  { en: `Your plan is on the Report card, one tip at a time.`,
                         it: `Il tuo piano sta nella Pagella, un consiglio alla volta.` },
    "plan.goto":       { en: `Open the Report card`, it: `Apri la Pagella` },


    "lvl.header":      { en: `Levels <small>(from your best to the ideal and the PRO lap, with the time that separates you)</small>`,
                         it: `Livelli <small>(dal tuo migliore all'ideale e al giro PRO, con il tempo che ti separa)</small>` },
    "lvl.yourRef":     { en: `your reference`, it: `il tuo riferimento` },
    "lvl.consistency": { en: `consistency on the table`, it: `costanza da recuperare` },
    "lvl.gapPro":      { en: `gap to PRO`, it: `gap dal PRO` },
    "lvl.beaten":      { en: `already beaten`, it: `già battuto` },
    "lvl.vsPro":       { en: `vs PRO`, it: `vs PRO` },

    "trends.none":     { en: `In your recent laps no corner is a weak point.`,
                         it: `Nei tuoi ultimi giri nessuna curva è un punto debole.` },
    "badge.systematic":{ en: `Systematic`, it: `Sistematico` },
    "badge.sporadic":  { en: `Sporadic`, it: `Sporadico` },
    "trends.toTrain":  { en: `to train`, it: `da allenare` },
    "trends.oneOff":   { en: `one-off`, it: `episodico` },
    "trends.median":   { en: `median`, it: `mediana` },

    "prog.sessions":   { en: `Corner by session <small>(median loss per session · each point = one run)</small>`,
                         it: `Curva per sessione <small>(perdita mediana per sessione · ogni punto è un'uscita)</small>` },
    // Chiavi sue: con lo stesso nome di quelle della scheda Sessione le
    // sovrascrivevano, e «nessun giro registrato» e «I tuoi giri» diventavano
    // queste frasi.
    "cornerses.none":  { en: `No corner has enough sessions for a trend yet.`,
                         it: `Nessuna curva ha ancora abbastanza sessioni per vederne l'andamento.` },
    "cornerses.laps":  { en: `laps`, it: `giri` },
    "ses.better":      { en: `better than the first session`,
                         it: `meglio della prima sessione` },
    "ses.worse":       { en: `worse than the first session`,
                         it: `peggio della prima sessione` },

    "lbl.comparison":  { en: `Comparison`, it: `Confronto` },
    "lbl.lap":         { en: `Lap`, it: `Giro` },
    "lbl.gap":         { en: `Gap`, it: `Gap` },
    "lbl.road":        { en: `Track temp`, it: `Asfalto` },
    "flow.map":        { en: `The highlighted stretch is where you lose time.`,
                         it: `Il tratto in evidenza è dove perdi tempo.` },
    "flow.map.all":    { en: `Where you lose time across the whole lap`,
                         it: `Dove perdi tempo, su tutto il giro` },
    "kbd.tab":         { en: `Key {k}`, it: `Tasto {k}` },
    "kbd.lap":         { en: `[ and ] step through the laps`,
                         it: `[ e ] scorrono i giri` },
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
    "sum.cond.unj":    { en: `Chosen because it was checked`, it: `Scelto perché verificato` },
    "sum.cond.unjt":   { en: `your {time} is faster, but nothing has checked it for track limits`,
                         it: `il tuo {time} è più veloce, ma nessuno ne ha verificato i limiti di pista` },
    "sum.cond.v":      { en: `track at {temp}, while your {time} was set at {ftemp}`,
                         it: `asfalto a {temp}, mentre il tuo {time} era a {ftemp}` },
    "sum.cond.vx":     { en: `track at {temp}, but your {time} has no recorded temperature`,
                         it: `asfalto a {temp}, ma il tuo {time} non ha la temperatura registrata` },
    // The tyre outranks the temperature: a different compound is a different
    // car. The strings are the sim's own — canonical on ACC, whatever the mod
    // decided on AC — and are shown, never translated.
    "sum.cond.tyre":   { en: `{tyre} tyres, while your {time} was on {ftyre}`,
                         it: `gomme {tyre}, mentre il tuo {time} era su {ftyre}` },
    "sum.cond.unknown":{ en: `an unrecorded compound`, it: `una mescola non registrata` },
    "sum.cond.grip":   { en: `track grip {grip}, while your {time} was set at {fgrip}`,
                         it: `grip della pista {grip}, mentre il tuo {time} era a {fgrip}` },
    "sum.cond.gripx":  { en: `track grip {grip}, but your {time} has no recorded grip`,
                         it: `grip della pista {grip}, ma il tuo {time} non ha il grip registrato` },

    "sec.t.title":     { en: `Every lap, sector by sector`,
                         it: `Ogni giro, settore per settore` },
    "sec.t.lap":       { en: `Lap`, it: `Giro` },
    "sec.t.hint":      { en: `Highlighted is your best in each sector. The ideal lap above is made of these times.`,
                         it: `In evidenza c'è il tuo migliore in ogni settore. Il giro ideale qui sopra è fatto di questi tempi.` },
    "sec.real":        { en: `(the track's own sectors)`, it: `(settori della pista)` },
    "sec.thirds":      { en: `(the lap in three parts)`, it: `(il giro in tre parti)` },
    "ideal.title":     { en: `Ideal lap`, it: `Giro ideale` },
    "ideal.potential": { en: `potential`, it: `potenziale` },
    "ideal.from":      { en: `It's your best sectors so far, added together.`,
                         it: `È la somma dei tuoi settori migliori finora.` },

    "vmin.header":     { en: `Min speed per corner <small>(km/h, + = faster than the reference)</small>`,
                         it: `Velocità minima per curva <small>(km/h, + = più veloce del riferimento)</small>` },
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
    "lap.offTrack.why": { en: `You went beyond the track limits on this lap, so it can't become your reference.`,
                          it: `In questo giro sei uscito dai limiti della pista, quindi non può diventare il tuo riferimento.` },
    // The four stretches of a corner. Same words the debrief uses for the cause
    // ("understeer at the apex"), so one word keeps meaning one place.
    "phase.entry":     { en: `entry`, it: `ingresso` },
    "phase.apex":      { en: `apex`, it: `apex` },
    "phase.exit":      { en: `exit`, it: `uscita` },
    "phase.after":     { en: `the run after`, it: `tratto dopo` },

    "debrief.title":   { en: `Where to improve`, it: `Dove migliorare` },
    "debrief.clean":   { en: `Clean lap. No corner lost you enough time to flag.`,
                         it: `Giro pulito. In nessuna curva hai perso abbastanza tempo da segnalarlo.` },

    "ro.pos":          { en: `Pos`, it: `Pos` },
    "ro.speed":        { en: `Speed`, it: `Velocità` },
    "ro.ref":          { en: `ref`, it: `rif` },
    "ro.throttle":     { en: `Throttle`, it: `Gas` },
    "ro.brake":        { en: `Brake`, it: `Freno` },
    "ro.gear":         { en: `Gear`, it: `Marcia` },

    // analysis tour
    "tour.a1.t": { en: `Pick a lap`, it: `Scegli un giro` },
    "tour.a1.x": { en: `Choose the car and track. HONE compares your laps with that car on that track.`,
                   it: `Scegli auto e pista. HONE confronta i tuoi giri con quell'auto su quella pista.` },
    // Counts nothing on purpose: this said "Four views" while there were five
    // tabs, and six the moment the guided flow landed. A number here is a
    // promise the tab bar keeps breaking.
    // Nor does it list them one by one, which is the same promise wearing
    // another coat: the roll call outlived the Map tab by a whole release and
    // kept sending drivers to a tab that no longer existed. Only Compare is
    // named here, because that step's whole point is where the drawing went.
    // Corto anche per un motivo meccanico: `test_every_tour_step_has_its_text_in
    // _both_languages` cerca `it:` nei primi 400 caratteri dopo la chiave, e una
    // frase inglese lunga spinge la riga italiana fuori dalla finestra.
    "tour.a2.t": { en: `The other views`, it: `Le altre viste` },
    "tour.a2.x": { en: `The same laps, seen other ways. Compare holds the most, with the traces and the drawing of the lap side by side. You see where you lost time in the chart and on the track at once. The other tabs zoom in on a corner or pull back to your history. Each tab opens with a key, left to right. Hover a tab to see its key.`,
                   it: `Gli stessi giri, visti in altri modi. Il Confronto è la scheda più ricca, con le tracce e il disegno del giro fianco a fianco. Vedi dove hai perso nel grafico e in pista insieme. Le altre schede stringono su una curva o allargano al tuo storico. Ogni scheda si apre con un tasto, da sinistra a destra. Passa il mouse su una scheda per vedere il suo tasto.` },
    "tour.a3.t": { en: `Delta`, it: `Delta` },
    "tour.a3.x": { en: `Where you're gaining or losing vs your reference, across the lap. Green (below the line) is faster.`,
                   it: `Dove guadagni o perdi rispetto al riferimento, lungo il giro. Verde (sotto la linea) è più veloce.` },
    "tour.a4.t": { en: `Min speed per corner`, it: `Velocità minima per curva` },
    "tour.a4.x": { en: `Apex speed in every corner against the reference. A positive delta means you carried more speed.`,
                   it: `La velocità all'apex di ogni curva, confrontata col riferimento. Un delta positivo vuol dire che hai portato più velocità.` },
    "tour.a5.t": { en: `Where to improve`, it: `Dove migliorare` },
    "tour.a5.x": { en: `Your biggest time losses, corner by corner, with the likely cause and a fix.`,
                   it: `Le tue perdite di tempo maggiori, curva per curva, con la causa probabile e una correzione.` },
    // Added when the debrief grew lap-wide findings and the lap list grew track
    // temperature: two things a driver sees before anyone explains them.
    "tour.a7.t": { en: `Whole-lap findings`, it: `Osservazioni sul giro` },
    "tour.a7.x": { en: `The blue-edged blocks above the corners are about the whole lap. For example, you lift where the reference stays flat out, or you're short on top speed. Read these first.`,
                   it: `I riquadri col bordo azzurro sopra le curve valgono per tutto il giro. Per esempio alzi il piede dove il riferimento tiene giù, o ti mancano km/h in velocità di punta. Guardali per primi.` },
    "tour.a8.t": { en: `Track temperature`, it: `Temperatura asfalto` },
    "tour.a8.x": { en: `The degrees next to each lap are the track, not the air. Braking points move 10-20 m between a cold track and a hot one. Two laps far apart in temperature are two different circuits.`,
                   it: `I gradi accanto a ogni giro sono dell'asfalto, non dell'aria. Fra pista fredda e calda i punti di frenata si spostano di 10-20 m. Due giri con temperature lontane sono due circuiti diversi.` },
    "tour.a10.t": { en: `Your line, corner by corner`, it: `La tua traiettoria, curva per curva` },
    "tour.a10.x": { en: `One corner at a time, zoomed in. The shaded band shows how far your line was from the reference's, in metres. Below, the same corner in numbers tells you where your slowest point is, how tight your arc was and how much extra road you covered.`,
                    it: `Una curva alla volta, ingrandita. La fascia colorata è quanto la tua traiettoria si è scostata da quella di riferimento, in metri. Sotto, i numeri della stessa curva dicono dov'è il tuo punto più lento, quanto è stretto l'arco e quanta strada in più fai.` },
    "tour.a6.t": { en: `Take it with you`, it: `Portalo con te` },
    "tour.a6.x": { en: `Export the lap as CSV or JSON and open it in a spreadsheet or another program.`,
                   it: `Esporta il giro in CSV o JSON e aprilo in un foglio di calcolo o in un altro programma.` },

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
    "tabs.aria":       { en: `Sections`, it: `Sezioni` },
    "trace.title":     { en: `Pedals and steering`, it: `Pedali e sterzo` },
    "trace.thr":       { en: `Throttle`, it: `Gas` },
    "trace.brk":       { en: `Brake`, it: `Freno` },
    "trace.steer":     { en: `Steering`, it: `Sterzo` },
    // Da che parte giri: il numero da solo non lo dice. Al posto delle frecce
    // di prima, la parola, come la direbbe il pilota.
    "trace.steerLeft":  { en: `{v} left`, it: `{v} a sinistra` },
    "trace.steerRight": { en: `{v} right`, it: `{v} a destra` },
    "eng.waiting":     { en: `Waiting for telemetry…`, it: `In attesa di telemetria…` },
    "g.speed":         { en: `Speed`, it: `Velocità` },
    "g.gear":          { en: `Gear`, it: `Marcia` },
    "g.tc":            { en: `TC`, it: `TC` },
    "g.abs":           { en: `ABS`, it: `ABS` },
    "g.map":           { en: `Map`, it: `Mappa` },

    "eng.tyres":       { en: `Tyres <span class="es-sub">(temp °C · pressure psi)</span>`,
                         it: `Gomme <span class="es-sub">(temp °C · pressione psi)</span>` },
    "eng.avNow":       { en: `Right now, in the car`, it: `Adesso, in macchina` },
    "eng.suggests":    { en: `The engineer suggests <span class="es-sub">(at the next pit stop)</span>`,
                         it: `L'ingegnere propone <span class="es-sub">(al prossimo rientro ai box)</span>` },
    "eng.prepare":     { en: `Prepare change in the editor →`, it: `Prepara la modifica nell'editor →` },
    "eng.restoredByHand": { en: `I've already restored it in the garage`,
                            it: `L'ho già ripristinato ai box` },

    "eng.focusTitle":  { en: `Focus · lesson`, it: `Focus · lezione` },
    "eng.focusSub":    { en: `(your driving, one weakness at a time)`,
                         it: `(la tua guida, una debolezza alla volta)` },
    "focus.warmup":    { en: `Drive a few complete laps to get started. Dirty ones count too.`,
                         it: `Fai qualche giro completo per cominciare. Valgono anche quelli sporchi.` },

    "eng.profile":     { en: `Engineer profile`, it: `Profilo ingegnere` },
    "eng.phases":      { en: `Phases`, it: `Fasi` },
    "eng.onfly":       { en: `At the wheel`, it: `Dal volante` },
    "eng.engPrefix":   { en: `Engineer `, it: `Ingegnere ` },

    // La pagina la alimenta Coach Live (`app._serve_engineer_page`, la pagina
    // Ingegnere in modalità spettatore) oppure il backend live. I due non possono
    // convivere: registrano entrambi, e insieme salverebbero ogni giro due volte.
    "eng.hint":        { en: `This page is fed by <b>Coach Live</b>, or by the <b>live backend</b>, which you start from the hub in <b>Devices</b> → Live backend. The two can't run together, because they'd both record. The changes in <b>Setup</b> go into the setup file. They must be <b>loaded in the pits</b> and don't change the car while you drive.`,
                         it: `Questa pagina la alimenta <b>Coach Live</b>, oppure il <b>backend live</b>, che accendi dall'hub in <b>Dispositivi</b> → Backend live. I due non possono stare accesi insieme, perché registrano entrambi. Le modifiche in <b>Setup</b> agiscono sul file di setup. Vanno <b>caricate ai box</b> e non cambiano l'auto mentre guidi.` },

    "setup.title":     { en: `Setup`, it: `Setup` },
    "legend2.click":   { en: `<b>click</b> = game step`, it: `<b>click</b> = scatto di gioco` },
    "legend2.est":     { en: `psi/% = estimate`, it: `psi/% = stima` },
    "setup.pick":      { en: `Pick a car and track above. HONE reads setups from <code>Documents/Assetto Corsa Competizione/Setups/&lt;car&gt;/&lt;track&gt;/</code> (ACC) and <code>Documents/Assetto Corsa/setups/</code> (AC).`,
                         it: `Scegli auto e pista qui sopra. HONE legge i setup da <code>Documents/Assetto Corsa Competizione/Setups/&lt;car&gt;/&lt;track&gt;/</code> (ACC) e <code>Documents/Assetto Corsa/setups/</code> (AC).` },

    "tray.pending":    { en: `Pending changes`, it: `Modifiche in sospeso` },
    "tray.reset":      { en: `Reset all`, it: `Azzera tutto` },
    // Two ways out of the tray. The primary one writes straight away under an
    // auto-numbered name, because the driver is sitting in the box with the
    // engine running: naming a file is not what that moment is for. The other
    // keeps the old road — a name you choose, and the physical diff (psi, mm)
    // in front of you before anything is written.
    "tray.write":      { en: `Name it…`, it: `Dai un nome…` },
    "tray.apply":      { en: `Apply →`, it: `Applica →` },
    "tray.applyTitle": { en: `Writes straight away as HONE_1, HONE_2 and so on, with no name to type`,
                         it: `Scrive subito come HONE_1, HONE_2 e così via, senza un nome da digitare` },

    "modal.title":     { en: `Confirm setup write`, it: `Conferma scrittura setup` },
    "modal.name":      { en: `Destination file name`, it: `Nome file di destinazione` },
    "modal.hint":      { en: `This creates a <b>new file</b> and leaves the original intact. After writing, go back to the pits, open the Setup screen and load the new setup.`,
                         it: `Verrà creato un <b>nuovo file</b> e l'originale resta intatto. Dopo la scrittura torna ai box, apri la schermata Setup e carica il nuovo setup.` },
    "modal.cancel":    { en: `Cancel`, it: `Annulla` },
    "modal.write":     { en: `Write`, it: `Scrivi` },

    // ---- engineer page (engineer.js injected) ----
    "eng.noSetupOpt":  { en: `(no setup found)`, it: `(nessun setup trovato)` },
    // Una riga per cartella: il `\n` dopo ogni `<br>` chiude la frase anche per
    // chi la conta (tests/tono.py), come la chiude l'a capo per chi la legge.
    "eng.noSetupBody": { en: `I found no setup files for this car and track.<br>
HONE reads setups from these folders.<br>
<code>Documents/Assetto Corsa Competizione/Setups/&lt;car&gt;/&lt;track&gt;/</code> (ACC)<br>
<code>Documents/Assetto Corsa/setups/&lt;car&gt;/&lt;track&gt;/</code> (AC)<br>
Save a setup in the game, then reload this page.`,
                         it: `Non ho trovato file di setup per questa auto e questa pista.<br>
HONE legge i setup da queste cartelle.<br>
<code>Documents/Assetto Corsa Competizione/Setups/&lt;car&gt;/&lt;track&gt;/</code> (ACC)<br>
<code>Documents/Assetto Corsa/setups/&lt;car&gt;/&lt;track&gt;/</code> (AC)<br>
Salva un setup nel gioco, poi ricarica questa pagina.` },

    // The car/track you are actually driving has no setup folder yet. ACC only
    // creates one when you save a setup from the garage, so this is the normal
    // state on a circuit you have never saved on — not an error, and above all
    // not a reason to show you another track's setup without saying so.
    "eng.miss.title":  { en: `No setup for this track yet`,
                         it: `Nessun assetto per questa pista` },
    "eng.miss.driving": { en: `You're driving`, it: `Stai guidando` },
    "eng.miss.why":    { en: `The game creates the setup folder only when you save one from the garage, so there is nothing here to edit yet.`,
                         it: `Il gioco crea la cartella degli assetti solo quando ne salvi uno dal garage, quindi qui non c'è ancora niente da modificare.` },
    "eng.miss.seedHead": { en: `You can start from one you already have.`,
                           it: `Puoi partire da uno che hai già.` },
    "eng.miss.seedBtn": { en: `Use as a base`, it: `Usa come base` },
    "eng.miss.caveat": { en: `Pressures and aero from another circuit are <b>not</b> a setup for this one. It's a starting point, not a proposal, and the engineer moves it from there on your laps.`,
                         it: `Pressioni e aero di un altro circuito <b>non</b> sono un assetto per questo. È un punto di partenza, non una proposta, e da lì lo muove l'ingegnere sui tuoi giri.` },
    "eng.miss.none":   { en: `You have no setups for this car on any track either. Save one in the game (garage → Setup → Save), then press “I've saved one, reload”.`,
                         it: `Non hai assetti di quest'auto nemmeno su altre piste. Salvane uno nel gioco (garage → Setup → Salva), poi premi «Ne ho salvato uno, ricarica».` },
    "eng.miss.reload": { en: `I've saved one, reload`, it: `Ne ho salvato uno, ricarica` },
    "eng.miss.optNone": { en: `no setup`, it: `nessun assetto` },
    "eng.miss.seeded": { en: `I copied the setup from {from}. Now edit it here, then write it.`,
                         it: `Ho copiato l'assetto di {from}. Ora modificalo qui e poi scrivilo.` },
    // I messaggi d'errore sono una frase intera: dopo arriva il dettaglio del server.
    "eng.miss.seedErr": { en: `I couldn't copy the setup. `, it: `Non sono riuscito a copiare l'assetto. ` },
    // Where car/track came from when there's no live telemetry: the archive.
    "eng.fromArchive": { en: `last recorded lap`, it: `ultimo giro registrato` },

    "eng.prepared.some": { en: `The change is ready, but some parameters aren't in this setup.`,
                           it: `Ho preparato la modifica, ma alcuni parametri non sono in questo setup.` },
    "eng.prepared.ok":   { en: `The change is ready in the editor. Check it and press “Apply”.`,
                           it: `Ho preparato la modifica nell'editor. Controllala e premi «Applica».` },
    "eng.prepared.none": { en: `The proposed parameter is not in this setup.`,
                           it: `Il parametro proposto non è in questo setup.` },

    "eng.click":       { en: `click`, it: `click` },
    // Il suggerimento dei bottoni − e +, dopo «−1 click.» / «+1 click.».
    "eng.stepHint":    { en: `Hold to repeat.`, it: `Tieni premuto per scorrere più in fretta.` },
    "eng.alvoloTag":   { en: `at the wheel`, it: `dal volante` },
    "eng.alvoloHint":  { en: `You can adjust it on track without pitting. The other settings only take effect when you reload the setup in the pits.`,
                         it: `Lo regoli in pista senza rientrare. Gli altri parametri hanno effetto solo ricaricando il setup ai box.` },
    "eng.previewErr":  { en: `I can't show the preview. `, it: `Non riesco a mostrare l'anteprima. ` },
    "eng.enterName":   { en: `Enter a file name.`, it: `Inserisci un nome file.` },
    "eng.exists":      { en: `A setup with this name already exists. Choose another one.`,
                         it: `Esiste già un setup con questo nome. Scegline un altro.` },
    "eng.writeErr":    { en: `I couldn't write the setup. `, it: `Non sono riuscito a scrivere il setup. ` },
    "eng.writeErrName": { en: `I couldn't write the setup, the names up to {name} are already taken.`,
                          it: `Non sono riuscito a scrivere il setup, i nomi fino a {name} sono già presi.` },
    "eng.restored":    { en: `I've restored the setup from the last backup.`,
                         it: `Ho ripristinato il setup dall'ultimo backup.` },
    "eng.noBackup":    { en: `No backup to restore for this setup.`,
                         it: `Nessun backup da ripristinare per questo setup.` },
    "eng.restoreErr":  { en: `I couldn't restore the setup. `, it: `Non sono riuscito a ripristinare il setup. ` },
    "eng.corners":     { en: `Corners `, it: `Curve ` },
    // Il grado di fiducia della proposta: arriva dal motore come parola inglese
    // («medium»), e su una pagina in italiano restava inglese.
    "eng.conf.high":   { en: `high confidence`, it: `fiducia alta` },
    "eng.conf.medium": { en: `medium confidence`, it: `fiducia media` },
    "eng.conf.low":    { en: `low confidence`, it: `fiducia bassa` },
    // The verdict, after the re-test laps. The words are short because the
    // sentence that explains it is written server-side, next to the rule.
    "eng.oc.kept":     { en: `change kept`, it: `modifica tenuta` },
    "eng.oc.reverted": { en: `change rejected`, it: `modifica bocciata` },
    "eng.oc.laps":     { en: `over {n} {n|lap|laps}`, it: `su {n} {n|giro|giri}` },
    // Seguita dall'elenco dei sintomi, separati da «·».
    "eng.oc.side":     { en: `Also moved`, it: `Si sono mossi anche` },
    "eng.lowConf":     { en: `Confidence is low because I have little data. Drive a few more clean laps before you apply it.`,
                         it: `La fiducia è bassa perché ho pochi dati. Fai qualche altro giro pulito prima di applicarla.` },
    "eng.dash":        { en: `—`, it: `—` },
    "eng.warmup":      { en: `I need 3 clean laps for a baseline, so for now I'm watching.`,
                         it: `Servono 3 giri puliti per avere una base, quindi per ora guardo.` },
    // What to do in the current setup phase — persistent guidance so "phase done →
    // moving to X" is always followed by a concrete instruction.
    "eng.phaseNow":    { en: `“{label}” phase.`, it: `Fase «{label}».` },
    "eng.do.pressures":  { en: `Drive a few laps to bring the tyres up to temperature. I judge the pressures hot.`,
                           it: `Guida qualche giro per portare le gomme in temperatura. Le pressioni le giudico a caldo.` },
    "eng.do.mechanical": { en: `Keep driving clean laps. I'm looking for understeer and oversteer at low speed, and I work on springs, bars and the differential. Any change here is a pit job, so prepare it, write the setup and reload it.`,
                           it: `Continua con giri puliti. Cerco sottosterzo e sovrasterzo a bassa velocità e lavoro su molle, barre e differenziale. Ogni modifica qui si fa ai box, quindi preparala, scrivi il setup e ricaricalo.` },
    "eng.do.aero":       { en: `Drive clean laps at pace. Now I work on high-speed balance with wing, rake and ride height, all pit jobs.`,
                           it: `Guida giri puliti a ritmo. Ora lavoro sull'equilibrio ad alta velocità con ala, rake e altezze, tutte modifiche da box.` },
    "eng.do.brake_bias": { en: `Brake like in a race. I tune the brake bias, which you change from the wheel without pitting.`,
                           it: `Frena come in gara. Regolo il bilanciamento freni, che cambi dal volante senza rientrare.` },
    "eng.do.electronics":{ en: `Push on corner exit. I tune TC, ABS and engine maps, which you change from the wheel.`,
                           it: `Spingi in uscita. Regolo TC, ABS e mappe motore, che cambi dal volante.` },
    "eng.do.traction":   { en: `Focus on corner exit. I work on mechanical traction, meaning the differential and rear grip, with changes made in the pits.`,
                           it: `Concentrati sull'uscita. Lavoro sulla trazione meccanica, cioè differenziale e grip posteriore, con modifiche da fare ai box.` },
    "eng.do.diff":       { en: `Drive entry and exit consistently. I tune the differential, which is a pit job.`,
                           it: `Guida ingresso e uscita in modo costante. Regolo il differenziale, una modifica da fare ai box.` },
    "eng.do.default":    { en: `Keep driving clean, consistent laps. I'm gathering data for this phase.`,
                           it: `Continua con giri puliti e costanti. Sto raccogliendo dati per questa fase.` },
    "eng.pit":         { en: `You're in the pits. In the MFD open <b>Setup</b>, load <b>{name}</b> and head out to apply it.`,
                         it: `Sei ai box. Nell'MFD apri <b>Setup</b>, carica <b>{name}</b> ed esci per applicarlo.` },
    // Shown while stopped in the box with a garage change still unwritten —
    // the screen half of the spoken briefing (coaching/pitcall.py). The voice
    // sends you to this page; arriving to no instructions would waste the trip.
    "eng.pitTodo":     { en: `You're in the pits with a change waiting. Press <b>Prepare change</b> above, then <b>Apply</b> at the bottom, and load the setup from the garage before you go out.`,
                         it: `Sei ai box e c'è una modifica in attesa. Premi <b>Prepara la modifica</b> qui sopra, poi <b>Applica</b> in fondo, e ricarica il setup dal garage prima di uscire.` },
    "eng.loadErr":     { en: `I can't load the setups. `, it: `Non riesco a caricare i setup. ` },

    // --- il registro dell'ingegnere -----------------------------------------
    // Presentato a CONTEGGI, non a percentuali, finché le prove non sono
    // abbastanza: un tasso di successo su tre campioni è rumore travestito da
    // percentuale, e il modulo che lo calcola lo dice per primo.
    "rec.title":       { en: `Test log`, it: `Registro delle prove` },
    "rec.none":        { en: `No test finished yet on this car and track. The engineer proposes a change, you drive it, and the verdict lands here, even when the change didn't work.`,
                         it: `Nessuna prova ancora conclusa su questa auto e questa pista. L'ingegnere propone una modifica, tu la guidi e il verdetto finisce qui, anche quando la modifica non ha funzionato.` },
    "rec.counts":      { en: `<b>{kept}</b> kept out of <b>{tests}</b> tested`,
                         it: `<b>{kept}</b> tenute su <b>{tests}</b> provate` },
    "rec.rate":        { en: ` · {rate} % hit rate`, it: ` · {rate} % di riuscita` },
    // La variazione del tempo sul giro delle modifiche tenute: col segno, e
    // negativa vuol dire più veloce (ledger.Summary.median_gain_ms).
    "rec.gain":        { en: ` · median lap-time change {gain}`,
                         it: ` · variazione mediana del giro {gain}` },
    "rec.thin":        { en: `Too few tests for a percentage yet. Over a handful of samples a hit rate is just noise. The counts are above.`,
                         it: `Le prove sono ancora troppo poche per una percentuale. Su una manciata di campioni il tasso di riuscita è solo rumore. I conteggi sono qui sopra.` },
    "rec.byparam":     { en: `Which levers earn their place`, it: `Quali leve si guadagnano il posto` },
    "rec.byrank":      { en: `Does "most effective first" hold up?`,
                         it: `Regge il «prima il rimedio più efficace»?` },
    "rec.rank":        { en: `remedy #{n}`, it: `rimedio n.{n}` },
    "rec.side":        { en: `Side effects seen (never predicted)`,
                         it: `Effetti collaterali visti (mai predetti)` },
    "rec.kept_of":     { en: `{kept}/{tests} kept`, it: `{kept}/{tests} tenute` },
    "rec.seen":        { en: `{n}×`, it: `{n}×` },
    "eng.avDone":      { en: `I've changed it`, it: `L'ho cambiato` },

    // ---- tablet view (tablet.html): the rest it borrows from the engineer page
    "tablet.title":    { en: `HONE · Tablet`, it: `HONE · Tablet` },
    "tablet.off":      { en: `The coach isn't running. This page reconnects by itself.`,
                         it: `Il coach non è acceso. La pagina si ricollega da sola.` },
    "tablet.waiting":  { en: `The coach is on and waiting for data from the game.`,
                         it: `Il coach è acceso e aspetta i dati del gioco.` },
    "tablet.call":     { en: `Pit at the end of this lap. There's a setup change to make.`,
                         it: `Rientra ai box a fine giro. C'è una modifica da fare all'assetto.` },
    "tablet.callRestore": { en: `Come back to the pits to put the last change back as it was.`,
                            it: `Torna ai box per rimettere l'ultima modifica com'era.` },
    "tablet.full":     { en: `Full page`, it: `Pagina completa` },
    "tablet.tab.track": { en: `Telemetry`, it: `Telemetria` },
    "tablet.tab.setup": { en: `Setup`, it: `Assetto` },
    "tablet.base":     { en: `Starting setup`, it: `Il file di partenza` },
    "tablet.noBase":   { en: `I can't find a setup for this car on this track. Save one from the game's garage.`,
                         it: `Non trovo un assetto di questa auto per questa pista. Salvane uno dal garage del gioco.` },
    "tablet.write":    { en: `Write the change`, it: `Scrivi la modifica` },
    "tablet.writeRestore": { en: `Write the restore`, it: `Scrivi il ripristino` },
    "tablet.confirm":  { en: `I'll write these changes to a new file, {name}.`,
                         it: `Scrivo queste modifiche in un file nuovo, {name}.` },
    "tablet.writeErr": { en: `The file wasn't written. `, it: `Il file non è stato scritto. ` },
    "tablet.restored": { en: `I've already put it back`, it: `L'ho già rimesso com'era` },

    // engineer tour
    "tour.e1.t": { en: `Live diagnosis`, it: `Diagnosi live` },
    "tour.e1.x": { en: `Speed, gear and aids come straight from the car while Coach Live or the live backend is running.`,
                   it: `Velocità, marcia e aiuti arrivano dall'auto quando è acceso Coach Live o il backend live.` },
    "tour.e2.t": { en: `Tyres`, it: `Gomme` },
    "tour.e2.x": { en: `Temperatures and pressures are colour-coded. Keep them in the green.`,
                   it: `Temperature e pressioni hanno un colore. Tienile nel verde.` },
    "tour.e3.t": { en: `The engineer`, it: `L'ingegnere` },
    "tour.e3.x": { en: `Here the engineer proposes a setup change worked out from your telemetry. Press “Prepare change” to load it into the editor.`,
                   it: `Qui l'ingegnere propone una modifica di setup ricavata dalla tua telemetria. Premi «Prepara la modifica» per caricarla nell'editor.` },
    "tour.e4.t": { en: `Focus · lesson`, it: `Focus · lezione` },
    "tour.e4.x": { en: `Here the coach works on your driving, one weakness at a time, while you lap.`,
                   it: `Qui il coach lavora sulla tua guida, una debolezza alla volta, mentre giri.` },
    "tour.e5.t": { en: `Setup editor`, it: `Editor setup` },
    "tour.e5.x": { en: `Adjust in game clicks. Then “Apply” saves a new file to load in the pits.`,
                   it: `Regola a click, come nel gioco. Poi «Applica» salva un nuovo file da caricare ai box.` },
    "tour.e6.t": { en: `Change it now, from the wheel`, it: `Cambiala adesso, dal volante` },
    "tour.e6.x": { en: `It's a dial you turn on the straight, with no pit stop and no lap lost. On ACC there's nothing to confirm, because HONE reads the level live and sees it move. On AC those levels aren't published, so use the button.`,
                   it: `È una manopola che giri sul rettilineo, senza sosta e senza perdere un giro. Su ACC non devi confermare nulla, perché HONE legge il livello dal vivo e si accorge da solo che si è mosso. Su AC quei livelli non sono leggibili, quindi usa il pulsante.` },
  };

  // ---- core ---------------------------------------------------------------
  // A number as the page's language writes it: «0,18 s» in Italian, «0.18 s» in
  // English, a space before the unit, and a value that rounds to nothing is "0",
  // never "-0,00". Python twin: accoach.textfmt.fmt_num. Reads the language from
  // HoneI18n.lang, which set() keeps current (app.js and engineer.js both use it).
  function fmtNum(v, decimals, unit) {
    var s = (Math.abs(v) < 0.5 * Math.pow(10, -decimals) ? 0 : v).toFixed(decimals);
    if (window.HoneI18n.lang === "it") s = s.replace(".", ",");
    s = s.replace("-", "−");   // il meno dei tempi persi, non il trattino
    return unit ? s + " " + unit : s;
  }

  function readLang() {
    var l = window.HONE_LANG;
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
  //   data-i18n-label       -> data-label + aria-label (a group's caption,
  //                            drawn by CSS from `attr(data-label)`)
  // Safari 9 (l'iPad del pilota) non ha .forEach sulle NodeList.
  function each(list, fn) { Array.prototype.forEach.call(list, fn); }

  function applyStatic(root) {
    root = root || document;
    try {
      each(root.querySelectorAll("[data-i18n]"), function (el) {
        var v = t(el.getAttribute("data-i18n"));
        if (v != null) el.textContent = v;
      });
      each(root.querySelectorAll("[data-i18n-html]"), function (el) {
        var v = t(el.getAttribute("data-i18n-html"));
        if (v != null) el.innerHTML = v;
      });
      each(root.querySelectorAll("[data-i18n-title]"), function (el) {
        var v = t(el.getAttribute("data-i18n-title"));
        if (v != null) el.title = v;
      });
      each(root.querySelectorAll("[data-i18n-aria]"), function (el) {
        var v = t(el.getAttribute("data-i18n-aria"));
        if (v != null) el.setAttribute("aria-label", v);
      });
      each(root.querySelectorAll("[data-i18n-placeholder]"), function (el) {
        var v = t(el.getAttribute("data-i18n-placeholder"));
        if (v != null) el.placeholder = v;
      });
      each(root.querySelectorAll("[data-i18n-label]"), function (el) {
        var v = t(el.getAttribute("data-i18n-label"));
        if (v != null) {
          el.setAttribute("data-label", v);
          el.setAttribute("aria-label", v);
        }
      });
    } catch (e) { /* defensive: never break the page over a missing node */ }
    try { document.documentElement.lang = lang; } catch (e) {}
  }

  // Niente fetch: su Safari 9 non esiste e il selettore non funzionerebbe.
  function set(l) {
    if (SUPPORTED.indexOf(l) === -1) l = "en";
    // The selector changes the language of the whole app, not of this browser:
    // the server writes it to the config, where the hub reads it too. The page
    // changes only once the server has accepted it; if not, the selector goes
    // back and the language stays what it was.
    var xhr;
    try {
      xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/language");
      xhr.setRequestHeader("Content-Type", "application/json");
      xhr.onload = function () {
        if (xhr.status >= 200 && xhr.status < 300) apply(l);
        else syncSelectors();
      };
      xhr.onerror = function () { syncSelectors(); };
      xhr.send(JSON.stringify({ lang: l }));
    } catch (e) { syncSelectors(); }
  }

  function apply(l) {
    lang = l;
    window.HoneI18n.lang = l;
    applyStatic();
    syncSelectors();
    // Re-render the dynamic views without a reload when the page provides a
    // hook; otherwise fall back to a full reload (the language is in the config).
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
      each(document.querySelectorAll("select.lang-select"), function (s) {
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

  window.HoneI18n = { lang: lang, t: t, set: set, applyStatic: applyStatic, fmtNum: fmtNum };

  // Script lives at the end of <body>, after the header — the DOM we need is
  // already parsed, so boot immediately (and also catch the event, defensively).
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
