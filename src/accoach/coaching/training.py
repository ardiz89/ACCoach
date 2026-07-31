"""From "here is what you lose" to "here is what to do at the wheel tonight".

Everything else in this app answers *what* and *why*: the debrief names the
corner and the cause, the trends say which of those repeat, the plan turns the
worst of them into a number to get under, the benchmark ladder says your ideal
lap is eight tenths quicker than your best. All of it is true, and all of it
assumes the reader can do the last step alone — the one that turns "you lose
0.31 s at turn 4, mostly on entry" into *what to actually do for the next twenty
laps*. Someone who reads telemetry does that step without noticing. Everybody
else reads a page of correct numbers and drives the same lap again.

This module is that last step, and it is deliberately a small one:

* **it never invents a finding.** What to work on comes from the training plan
  (``plan.py``) — the same goals, the same targets, the same notion of "done".
  There is no second opinion about which corner matters here, because two
  surfaces disagreeing about that is worse than either answer alone;
* **it selects, it does not generate.** The drills below are a written library.
  Which one you get is decided by the diagnosis the rest of the app already
  made — *where inside the corner* the time went (``phases.py``) first, the loss
  category second — and the driver's own measured numbers are dropped into it.
  A line whose number we don't have is not printed with a blank in it: it is not
  printed;
* **it refuses to run on thin evidence.** Under :data:`MIN_LAPS` valid laps the
  section does not open at all. A training programme built on three laps is a
  programme that changes every time you drive, and a plan that moves is not a
  plan — the same reason ``plan.py`` freezes its goals on the day you accept
  them.

The one number the whole section hangs off is the **theoretical ideal**: your
best sector times stitched together. It is the right target to organise training
around precisely because it is not aspirational — you have already driven every
piece of it. The gap to it is not skill you lack, it is repetition you haven't
done, and that is a thing a drill can attack.

Two gaps, never added together
------------------------------
The section states two numbers and keeps them apart on purpose:

* **best → ideal** is measured by stitching your own best sectors, so it is what
  repeating yourself is worth;
* **what you bleed per lap at the plan's corners** is measured on your recent
  laps against your best one.

They overlap — some of the sector gap *is* those corners — and summing them
would report time twice. Nothing here sums them, and the wording says why.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field

from ..telemetry.snapshot import format_lap_time
from .cue import CueCategory as _C
from .debrief import LapDebrief
from .plan import GoalProgress, TrainingPlan
from .plan import _target as _take_back
from .thresholds import SIGNIF_LOSS_MS

#: Valid laps on this car and track before the section opens. Six, because six
#: laps leave five to compare against your best one, and the rest of the app
#: only calls a weakness *systematic* when it recurs in half of those — three of
#: five. Below that the word "systematic" is being applied to two laps, and a
#: programme aimed at what two laps happened to do is a coin toss with a heading.
MIN_LAPS = 6

#: How many steps the programme carries. Three, matching the guided flow's cap
#: and for the same reason: past three, "one thing at a time" stops being true
#: and the page has quietly become the list of weak points it was meant to
#: replace. Only the first is ever expanded into a session.
MAX_STEPS = 3

#: A sector has to hold at least this much of the consistency gap before the
#: programme points at it. Under a tenth, "most of it is in sector 2" is a
#: sentence about rounding.
_SECTOR_FLOOR_MS = 100.0

#: Lap-to-lap spread of your minimum speed at a corner, under which that corner
#: counts as repeatable. Three km/h is the floor ``chain.py`` already uses for
#: "this speed difference is not noise" — one driver's own spread across a
#: handful of laps runs to several km/h on a normal corner, and a drill that
#: asked for less would be asking the driver to chase the measurement error.
_REPEATABLE_KMH = 3.0


# --- what the caller measures for us ---------------------------------------

@dataclass(slots=True)
class CornerFacts:
    """Numbers about one corner that the report already computes elsewhere.

    Passed in rather than derived here so this module stays a pure function over
    things that have exactly one definition in the codebase: the braking figures
    are the braking sheet's (``braking_points.py``), the minimum speeds are the
    debrief's, the spread is the Trends tab's per-corner consistency. Anything
    left at its default is simply absent from the drill.
    """

    min_speed_kmh: float = 0.0
    min_speed_ref_kmh: float = 0.0
    spread_kmh: float = 0.0          # your own min speed, lap to lap
    brake_speed_kmh: float = 0.0
    brake_gear: str = ""
    brake_distance_m: float = 0.0    # pedal to the slowest point
    brake_spread_m: float = 0.0      # how much your braking point moves
    # The same wobble in km/h. Kept alongside the metres because the metres need
    # coordinates and plenty of real laps don't have them (every ACC lap in our
    # own archive reads 0 m), while the speed is there on all of them — and a
    # drill that drops the whole line because one of two numbers is missing
    # throws away the half it does have.
    brake_spread_kmh: float = 0.0
    landmark: str = ""               # something you can see, when we know one


# --- what the section says --------------------------------------------------

@dataclass(slots=True)
class Readiness:
    """Whether there is enough evidence to write a programme, and what's missing."""

    ready: bool
    laps: int
    laps_needed: int
    missing: list[str] = field(default_factory=list)   # "laps" | "weakness"
    reason: str = ""


@dataclass(slots=True)
class SectorGap:
    """One sector: your best lap's time there vs the best you've ever done there."""

    number: int          # 1-based, as the Sectors tab numbers them
    your_ms: int
    best_ms: int
    gap_ms: int


@dataclass(slots=True)
class Gap:
    """The distance to the theoretical ideal, and where it sits."""

    best_ms: int
    ideal_ms: int
    consistency_ms: int              # best - ideal, never negative
    sectors: list[SectorGap] = field(default_factory=list)
    worst_sector: int = 0            # 1-based; 0 when none dominates
    worst_sector_ms: int = 0
    per_lap_ms: float = 0.0          # typical bleed at the programme's corners
    pro_ms: int = 0
    pro_gap_ms: int = 0
    headline: str = ""
    note: str = ""


@dataclass(slots=True)
class Drill:
    """One exercise: what to do, for how many laps, and what to look at."""

    key: str
    title: str
    laps: int
    steps: list[str] = field(default_factory=list)
    watch: str = ""
    ignore: str = ""


@dataclass(slots=True)
class Step:
    """One rung of the programme."""

    order: int
    kind: str                # "corner" | "consistency"
    corner_index: int        # -1 for the lap-wide consistency step
    where: str
    what: str                # the debrief's own words for the problem
    why: str                 # why this one, in this position
    target: str              # the number that says when it's done
    done_when: str
    status: str              # "now" | "later" | "done"
    drill: Drill | None = None


@dataclass(slots=True)
class Session:
    """The next time you sit down: what to run, in order."""

    laps: int
    lines: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Programme:
    """The whole section, ready or not."""

    readiness: Readiness
    gap: Gap | None = None
    steps: list[Step] = field(default_factory=list)
    session: Session | None = None

    def to_dict(self) -> dict:
        return {
            "ready": self.readiness.ready,
            "readiness": asdict(self.readiness),
            "gap": asdict(self.gap) if self.gap else None,
            "steps": [asdict(s) for s in self.steps],
            "session": asdict(self.session) if self.session else None,
        }


# --- words ------------------------------------------------------------------
# Same arrangement as flow.py: user-facing prose lives next to the rule that
# decides whether to say it, so a rule and its sentence can't drift apart.

_T = {
    "it": {
        "need_laps": "Servono {n} giri validi su questa auto e questa pista "
                     "prima che un programma significhi qualcosa: ne hai {have}. "
                     "Con meno, quello che sembra una debolezza è quello che "
                     "hanno fatto due giri.",
        "need_weakness": "Hai giri a sufficienza, ma nessuna debolezza si "
                         "ripete abbastanza da chiamarsi tale: quello che perdi "
                         "cambia curva da un giro all'altro. Guida ancora un "
                         "po' — oppure guarda «Punti deboli» in Tendenze per "
                         "vedere cosa manca a poco.",
        "gap_head": "Il tuo miglior giro è {best}. Il tuo ideale teorico è "
                    "{ideal}: {gap}s che hai già guidato, ma a pezzi.",
        "gap_head_tight": "Il tuo miglior giro è {best} e il tuo ideale teorico "
                          "è {ideal}: praticamente lo stesso giro. Ripetendoti "
                          "non c'è più niente da prendere — quello che resta si "
                          "prende in curva.",
        "gap_worst": " Il grosso — {ws}s — sta nel settore {n}.",
        "gap_note": "Questi {gap}s non si sommano ai {lap}s che perdi in media "
                    "ogni giro nelle curve qui sotto: sono la stessa strada "
                    "misurata in due modi (i tuoi settori migliori contro il "
                    "tuo miglior giro, e i tuoi giri recenti contro lo stesso "
                    "giro). Sommarli conterebbe due volte lo stesso tempo.",
        "gap_pro": " Il riferimento PRO è {pro}, altri {pg}s oltre il tuo "
                   "ideale: quello sì è tempo che non hai ancora guidato.",
        "why_first": "Si comincia da qui: è la perdita più grande che si "
                     "ripete ({occ} giri su {laps}).",
        "why_chain": "Si comincia da qui anche se non è la perdita più grande: "
                     "il tempo che perdi a {victim} nasce in questa curva. Un "
                     "esercizio solo, due curve sistemate.",
        "why_later": "Poi questa, che si ripete in {occ} giri su {laps}. Una "
                     "cosa alla volta: due esercizi nella stessa sessione si "
                     "annullano a vicenda.",
        "why_done": "Fatta. Il bersaglio è stato centrato nei giri dopo l'avvio "
                    "del piano.",
        "why_cons_first": "Si comincia da qui: quello che ti costa di più non è "
                          "una curva, è che non rifai due volte lo stesso giro.",
        "why_cons_last": "Alla fine, quando le curve qui sopra sono entrate: "
                         "serve a incollarle in un giro solo.",
        "target": "porta la perdita qui sotto {to}s (adesso {from_}s)",
        "target_cons": "metti insieme i tuoi settori migliori: {ideal}",
        "done_when": "Fatto quando ci riesci in {needed} giri su quelli che "
                     "guidi da qui in poi — è la stessa frazione che l'ha resa "
                     "una debolezza.",
        "done_when_plain": "Fatto quando ci riesci in metà dei giri che guidi "
                           "da qui in poi.",
        "done_when_cons": "Fatto quando fra il tuo miglior giro e l'ideale "
                          "teorico restano meno di {s}s: metà di quello che "
                          "c'è adesso, la stessa metà che il piano chiede in "
                          "curva.",
        "ses_warm": "3 giri di riscaldamento. Gomme e freni in temperatura, "
                    "cronometro spento: un giro freddo non dice niente.",
        "ses_drill": "{n} giri di esercizio: {title} — {where}.",
        "ses_drill_lap": "{n} giri di esercizio, sul giro intero: {title}.",
        "ses_free": "3 giri liberi, guidati normale. Servono a vedere se "
                    "l'esercizio è entrato quando smetti di pensarci.",
        "ses_back": "Poi torna qui: si misura solo su quello che guidi da "
                    "adesso in poi.",
        "ses_back_plan": "Poi torna qui: si misura solo sui giri dopo il {when}.",
        # --- the drills ---
        "d.brake_move_later.title": "Sposta la staccata, un'auto per volta",
        "d.brake_move_later.watch": "la velocità minima in curva "
                                    "(Confronto → Velocità)",
        "d.brake_move_later.ignore": "il tempo sul giro: in questi giri non conta",
        "d.brake_move_later.s0": "Guarda dov'è il tuo punto adesso: stacchi a "
                                 "{v} km/h in {g}ª, {d} m prima del punto più "
                                 "lento della curva.",
        "d.brake_move_later.s0b": "Guarda dov'è il tuo punto adesso: la scheda "
                                  "frenate in fondo alla Mappa dice a che "
                                  "velocità e in che marcia stacchi qui.",
        "d.brake_move_later.s0d": "Guarda dov'è il tuo punto adesso: stacchi a "
                                  "{v} km/h in {g}ª.",
        "d.brake_move_later.s0c": "Un riferimento che vedi, non un numero: {lm}.",
        "d.brake_move_later.s1": "Due giri senza cambiare niente, solo per "
                                 "ripetere quel punto. Adesso si sposta di {m} m "
                                 "da un giro all'altro: un punto che non sai "
                                 "ripetere non lo puoi spostare.",
        "d.brake_move_later.s1b": "Due giri senza cambiare niente, solo per "
                                  "ripetere quel punto: un punto che non sai "
                                  "ripetere non lo puoi spostare.",
        "d.brake_move_later.s1c": "Due giri senza cambiare niente, solo per "
                                  "ripetere quel punto. Adesso ci arrivi a una "
                                  "velocità che balla di {k} km/h da un giro "
                                  "all'altro: un punto che non sai ripetere non "
                                  "lo puoi spostare.",
        "d.brake_move_later.s2": "Poi spostalo di una lunghezza d'auto per giro. "
                                 "Cinque metri, non venti: cinque metri li "
                                 "guidi, venti li subisci.",
        "d.brake_move_later.s3": "Se blocchi o arrivi lungo all'apex, sei andato "
                                 "oltre: torna al punto di prima e restaci due "
                                 "giri. Il punto giusto è l'ultimo che sai "
                                 "ripetere, non il più tardi che hai provato.",
        "d.brake_move_later.s4": "Tieni d'occhio la minima: adesso è {v} km/h. "
                                 "Se scende mentre stacchi più tardi, hai preso "
                                 "in staccata e restituito all'apex — non è un "
                                 "guadagno, è uno spostamento.",
        "d.brake_release.title": "Molla il freno, non la velocità",
        "d.brake_release.watch": "il grafico Gas / Freno (Confronto): la tua "
                                 "curva del freno deve finire prima, non più tardi",
        "d.brake_release.ignore": "il punto di frenata: in questi giri non si tocca",
        "d.brake_release.s0": "Qui il problema non è quando cominci a frenare, "
                              "è quanto ci resti sopra. Lascia il punto dov'è.",
        "d.brake_release.s1": "Due giri esagerando da un lato: appena giri il "
                              "volante, il freno è già a zero. Uscirai largo e "
                              "lento — va bene, è metà della misura.",
        "d.brake_release.s2": "Due giri esagerando dall'altro: tieni un filo di "
                              "freno fino all'apex. Sentirai il muso chiudere di "
                              "più e la macchina fermarsi troppo.",
        "d.brake_release.s3": "Il punto giusto sta in mezzo, e adesso lo hai "
                              "sentito da tutti e due i lati. Due giri lì.",
        "d.brake_release.s4": "La minima del riferimento qui è {vr} km/h contro "
                              "i tuoi {v}: se il rilascio è giusto, quel numero "
                              "sale da solo.",
        "d.apex_speed.title": "Trova la minima, poi difendila",
        "d.apex_speed.watch": "la velocità minima in questa curva",
        "d.apex_speed.ignore": "il tempo sul giro: due di questi giri sono "
                               "volutamente lenti",
        "d.apex_speed.s0": "Il riferimento passa qui a {vr} km/h, tu a {v}: "
                           "{diff} km/h. Prima di inseguirlo devi sapere quanto "
                           "la macchina ne regge davvero.",
        "d.apex_speed.s1": "Due giri di misura: entra in questa curva senza "
                           "toccare il freno, o con un accenno appena, e senti a "
                           "che velocità smette di girare. Non sono giri veloci, "
                           "sono una misura.",
        "d.apex_speed.s2": "Adesso rimetti il freno con un obiettivo solo: non "
                           "scendere sotto quella velocità. Il freno serve a "
                           "fermarsi prima dell'apex, non all'apex.",
        "d.apex_speed.s3": "Allarga l'ingresso di un paio di metri. La velocità "
                           "in curva la fa il raggio, non il coraggio: la stessa "
                           "curva, presa più larga, si percorre più veloce.",
        "d.apex_speed.s4": "Controlla in Traiettoria dove passi rispetto al "
                           "riferimento: se entri più stretto di lui, la minima "
                           "non salirà comunque.",
        "d.exit_throttle.title": "L'uscita si costruisce prima dell'apex",
        "d.exit_throttle.watch": "il gas in uscita (Confronto → Gas / Freno): "
                                 "deve salire e basta, mai risalire dopo essere "
                                 "sceso",
        "d.exit_throttle.ignore": "l'ingresso: qui accetti di perderci qualcosa",
        "d.exit_throttle.s0": "Scegli un punto d'uscita che vedi — un cordolo, "
                              "una riga — e decidi che da lì in poi il gas è a "
                              "fondo. Lo stesso punto per tutti i giri "
                              "dell'esercizio.",
        "d.exit_throttle.s1": "Due giri per capire cosa te lo impedisce. Se "
                              "pattini, sei arrivato all'apex girato male; se "
                              "devi ancora sterzare, sei arrivato troppo forte.",
        "d.exit_throttle.s2": "Rimedia prima, non dopo: entra un filo più piano "
                              "e più largo e arriva all'apex con la macchina già "
                              "dritta. Perdi un decimo in ingresso e ne prendi "
                              "due sul dritto che segue.",
        "d.exit_throttle.s3": "Gas progressivo, non digitale: apri e continua ad "
                              "aprire. Un gas che sale e poi torna giù è un gas "
                              "aperto troppo presto.",
        "d.exit_throttle.s4": "In Dinamica, «Blocchi e pattinamenti»: in uscita "
                              "la traccia posteriore deve restare vicina allo zero.",
        "d.repeat.title": "Prima ripetibile, poi veloce",
        "d.repeat.watch": "quanto si somigliano due giri di fila",
        "d.repeat.ignore": "il cronometro",
        "d.repeat.s0": "Qui non c'è una causa dominante: perdi un po' "
                       "dappertutto. Quasi sempre è un problema di ripetizione, "
                       "non di tecnica.",
        "d.repeat.s1": "Scegli tre riferimenti fissi per questa curva — dove "
                       "stacchi, dove giri, dove riapri — e dilli ad alta voce "
                       "mentre ci passi. Detti a voce diventano decisioni; "
                       "pensati restano sensazioni.",
        "d.repeat.s2": "Cinque giri con una regola sola: non cercare il tempo, "
                       "cerca di fare due giri uguali.",
        "d.repeat.s3": "Adesso la tua minima qui balla di {s} km/h fra un giro e "
                       "l'altro. Sotto i {r} la curva è tua — più giù di così "
                       "staresti inseguendo l'errore di misura.",
        "d.repeat.s4": "Solo quando la ripeti, prova a spostare un riferimento. "
                       "Uno.",
        "d.consistency.title": "Il giro che hai già fatto, tutto insieme",
        "d.consistency.watch": "i tre settori, non il tempo sul giro",
        "d.consistency.ignore": "il tempo sul giro — è l'unica cosa qui che si "
                                "sistema da sola",
        "d.consistency.s0": "L'ideale teorico non è un tempo inventato: è la "
                            "somma dei tuoi settori migliori. {ideal}, e l'hai "
                            "già guidato tutto — solo mai nello stesso giro.",
        "d.consistency.s1": "Ti mancano {gap}s per metterlo insieme, e {ws}s "
                            "stanno nel settore {n}: è lì che vai a lavorare.",
        "d.consistency.s1b": "Ti mancano {gap}s per metterlo insieme, e sono "
                             "sparsi: nessun settore te li tiene tutti.",
        "d.consistency.s2": "Cinque giri in cui non cerchi il tempo: cerchi di "
                            "ripetere. Stessa traiettoria, stessi punti, stesso "
                            "ordine.",
        "d.consistency.s3": "Regola per questi giri: se sbagli una curva, finisci "
                            "comunque il giro pulito. Il giro dopo l'errore è "
                            "quello che costa davvero, ed è l'unico che puoi "
                            "ancora salvare.",
        "d.consistency.s4": "Guarda «Settori»: l'obiettivo è che il settore {n} "
                            "smetta di essere il tuo peggiore, non che il giro "
                            "scenda. Il giro scende dopo.",
        "d.consistency.s4b": "Guarda «Settori»: l'obiettivo è che i tuoi tre "
                             "settori vengano dallo stesso giro, non che il "
                             "tempo scenda. Il tempo scende dopo.",
    },
    "en": {
        "need_laps": "A programme needs {n} valid laps on this car and track "
                     "before it means anything, and you have {have}. Below that, "
                     "what looks like a weakness is just what two laps did.",
        "need_weakness": "You have the laps, but nothing repeats often enough to "
                         "be called a weakness: what you lose moves from corner "
                         "to corner. Drive a little more — or open Weak points "
                         "under Trends to see what's close.",
        "gap_head": "Your best lap is {best}. Your theoretical ideal is {ideal}: "
                    "{gap}s you have already driven, but in pieces.",
        "gap_head_tight": "Your best lap is {best} and your theoretical ideal is "
                          "{ideal} — practically the same lap. There is nothing "
                          "left to take by repeating yourself; what's left is "
                          "taken in the corners.",
        "gap_worst": " Most of it — {ws}s — sits in sector {n}.",
        "gap_note": "These {gap}s do not add to the {lap}s you bleed on an "
                    "average lap in the corners below: it is the same road "
                    "measured two ways (your best sectors against your best lap, "
                    "and your recent laps against that same lap). Adding them "
                    "would count the same time twice.",
        "gap_pro": " The PRO reference is {pro}, another {pg}s beyond your ideal "
                   "— that one is time you have never driven.",
        "why_first": "Start here: it's the biggest loss that keeps coming back "
                     "({occ} laps out of {laps}).",
        "why_chain": "Start here even though it isn't the biggest loss: the time "
                     "you lose at {victim} is made in this corner. One drill, "
                     "two corners fixed.",
        "why_later": "Then this one, which repeats on {occ} laps out of {laps}. "
                     "One at a time: two drills in the same session cancel each "
                     "other out.",
        "why_done": "Done. You hit the target on the laps you drove after "
                    "starting the plan.",
        "why_cons_first": "Start here: what costs you most isn't a corner, it's "
                          "that you don't drive the same lap twice.",
        "why_cons_last": "Last, once the corners above have sunk in: this is what "
                         "glues them into a single lap.",
        "target": "get the loss here under {to}s (it's {from_}s now)",
        "target_cons": "put your best sectors together: {ideal}",
        "done_when": "Done when you manage it on {needed} of the laps you drive "
                     "from here — the same fraction that made it a weakness.",
        "done_when_plain": "Done when you manage it on half the laps you drive "
                           "from here.",
        "done_when_cons": "Done when less than {s}s is left between your best "
                          "lap and your theoretical ideal: half of what's there "
                          "now, the same half the plan asks for in a corner.",
        "ses_warm": "3 warm-up laps. Tyres and brakes up to temperature, clock "
                    "off: a cold lap tells you nothing.",
        "ses_drill": "{n} drill laps: {title} — {where}.",
        "ses_drill_lap": "{n} drill laps, over the whole lap: {title}.",
        "ses_free": "3 free laps, driven normally. They're there to show whether "
                    "the drill stuck once you stop thinking about it.",
        "ses_back": "Then come back here: only what you drive from now on counts.",
        "ses_back_plan": "Then come back here: only the laps after {when} count.",
        "d.brake_move_later.title": "Move the braking point, one car length at a time",
        "d.brake_move_later.watch": "your minimum speed in the corner "
                                    "(Compare → Speed)",
        "d.brake_move_later.ignore": "the lap time: it doesn't count on these laps",
        "d.brake_move_later.s0": "First, see where your point is now: you hit the "
                                 "brakes at {v} km/h in {g}, {d} m before the "
                                 "slowest point of the corner.",
        "d.brake_move_later.s0b": "First, see where your point is now: the braking "
                                  "sheet at the bottom of the Map tab says at what "
                                  "speed and in which gear you brake here.",
        "d.brake_move_later.s0d": "First, see where your point is now: you hit the "
                                  "brakes at {v} km/h in {g}.",
        "d.brake_move_later.s0c": "Something you can see, not a number: {lm}.",
        "d.brake_move_later.s1": "Two laps changing nothing, just repeating that "
                                 "point. Right now it moves {m} m from lap to lap: "
                                 "a point you can't repeat is a point you can't move.",
        "d.brake_move_later.s1b": "Two laps changing nothing, just repeating that "
                                  "point: a point you can't repeat is a point you "
                                  "can't move.",
        "d.brake_move_later.s1c": "Two laps changing nothing, just repeating that "
                                  "point. Right now you arrive at a speed that "
                                  "swings {k} km/h from lap to lap: a point you "
                                  "can't repeat is a point you can't move.",
        "d.brake_move_later.s2": "Then move it one car length per lap. Five metres, "
                                 "not twenty: five you drive, twenty you survive.",
        "d.brake_move_later.s3": "Lock a wheel or run wide at the apex and you've "
                                 "gone past it: go back to the previous point and "
                                 "stay there two laps. The right point is the last "
                                 "one you can repeat, not the latest one you tried.",
        "d.brake_move_later.s4": "Keep an eye on your minimum speed: {v} km/h now. "
                                 "If it drops as you brake later, you took time in "
                                 "the braking zone and gave it back at the apex — "
                                 "that's a move, not a gain.",
        "d.brake_release.title": "Release the brake, not the speed",
        "d.brake_release.watch": "the Throttle / Brake chart (Compare): your brake "
                                 "trace has to finish earlier, not later",
        "d.brake_release.ignore": "the braking point: leave it alone on these laps",
        "d.brake_release.s0": "The problem here isn't when you start braking, it's "
                              "how long you stay on it. Leave the point where it is.",
        "d.brake_release.s1": "Two laps overdoing it one way: the moment you turn "
                              "the wheel, the brake is already at zero. You'll run "
                              "wide and slow — good, that's half the measurement.",
        "d.brake_release.s2": "Two laps overdoing it the other way: carry a sliver "
                              "of brake all the way to the apex. You'll feel the "
                              "nose bite more and the car stop too much.",
        "d.brake_release.s3": "The right release is in between, and you've now felt "
                              "both edges of it. Two laps there.",
        "d.brake_release.s4": "The reference's minimum here is {vr} km/h against "
                              "your {v}: get the release right and that number "
                              "climbs on its own.",
        "d.apex_speed.title": "Find the minimum, then defend it",
        "d.apex_speed.watch": "your minimum speed in this corner",
        "d.apex_speed.ignore": "the lap time: two of these laps are slow on purpose",
        "d.apex_speed.s0": "The reference goes through here at {vr} km/h, you at "
                           "{v}: {diff} km/h. Before chasing it you need to know "
                           "how much the car actually holds.",
        "d.apex_speed.s1": "Two measuring laps: take this corner without touching "
                           "the brake at all, or barely, and feel where it stops "
                           "turning. These aren't fast laps, they're a measurement.",
        "d.apex_speed.s2": "Now put the brake back with one goal: don't go below "
                           "that speed. The brake is there to slow you down before "
                           "the apex, not at it.",
        "d.apex_speed.s3": "Open the entry by a couple of metres. Corner speed "
                           "comes from radius, not courage: the same corner taken "
                           "wider is taken faster.",
        "d.apex_speed.s4": "Check the Line tab for where you go against the "
                           "reference: enter tighter than it and the minimum won't "
                           "come up anyway.",
        "d.exit_throttle.title": "The exit is built before the apex",
        "d.exit_throttle.watch": "the throttle on exit (Compare → Throttle / "
                                 "Brake): it should only ever go up",
        "d.exit_throttle.ignore": "the entry: you're accepting a loss there",
        "d.exit_throttle.s0": "Pick an exit point you can see — a kerb, a line — "
                              "and decide that from there the throttle is pinned. "
                              "The same point on every lap of the drill.",
        "d.exit_throttle.s1": "Two laps to find out what stops you. Wheelspin means "
                              "you got to the apex badly rotated; still steering "
                              "means you got there too fast.",
        "d.exit_throttle.s2": "Fix it earlier, not later: enter slightly slower and "
                              "wider and reach the apex with the car already "
                              "straight. Lose a tenth on entry, take two back on "
                              "the straight that follows.",
        "d.exit_throttle.s3": "Progressive, not digital: open and keep opening. A "
                              "throttle that rises then drops is a throttle opened "
                              "too early.",
        "d.exit_throttle.s4": "In Dynamics, «Lock & spin»: on exit the rear trace "
                              "should stay near zero.",
        "d.repeat.title": "Repeatable first, fast second",
        "d.repeat.watch": "how alike two consecutive laps are",
        "d.repeat.ignore": "the clock",
        "d.repeat.s0": "There's no dominant cause here: you lose a little "
                       "everywhere. That's almost always a repetition problem, not "
                       "a technique one.",
        "d.repeat.s1": "Pick three fixed references for this corner — where you "
                       "brake, where you turn, where you get back on it — and say "
                       "them out loud as you go through. Said out loud they become "
                       "decisions; thought, they stay feelings.",
        "d.repeat.s2": "Five laps with one rule: don't chase the time, chase two "
                       "laps that look the same.",
        "d.repeat.s3": "Right now your minimum here swings {s} km/h from lap to "
                       "lap. Under {r} the corner is yours — below that you'd be "
                       "chasing the measurement error.",
        "d.repeat.s4": "Only once you can repeat it, move one reference. One.",
        "d.consistency.title": "The lap you've already driven, all at once",
        "d.consistency.watch": "the three sectors, not the lap time",
        "d.consistency.ignore": "the lap time — it's the one thing here that fixes "
                                "itself",
        "d.consistency.s0": "The theoretical ideal isn't an invented time: it's "
                            "your best sectors added up. {ideal}, and you've driven "
                            "all of it — just never on the same lap.",
        "d.consistency.s1": "You're {gap}s off putting it together, and {ws}s of "
                            "that sits in sector {n}: that's where you work.",
        "d.consistency.s1b": "You're {gap}s off putting it together, and it's "
                             "spread out: no single sector holds it.",
        "d.consistency.s2": "Five laps where you don't chase the time, you chase "
                            "the repeat. Same line, same points, same order.",
        "d.consistency.s3": "Rule for these laps: if you get a corner wrong, still "
                            "finish the lap cleanly. The lap after the mistake is "
                            "the expensive one, and it's the only one you can still "
                            "save.",
        "d.consistency.s4": "Watch «Sectors»: the goal is for sector {n} to stop "
                            "being your worst, not for the lap time to drop. The "
                            "time drops afterwards.",
        "d.consistency.s4b": "Watch «Sectors»: the goal is for your three sectors "
                             "to come from the same lap, not for the time to drop. "
                             "The time drops afterwards.",
    },
}


def _s(lang: str) -> dict:
    return _T.get(lang, _T["en"])


def _sec(ms: float) -> str:
    return f"{ms / 1000.0:.2f}"


# --- the gate ---------------------------------------------------------------

def assess(valid_laps: int, goals: int, lang: str = "it") -> Readiness:
    """Whether the section opens, and — when it doesn't — what is missing.

    "Not enough data" is said as a number with a target, never as an empty
    panel: a driver who can see they are two laps away goes and drives two laps,
    and one who sees a blank box assumes the feature is broken.
    """
    s = _s(lang)
    missing: list[str] = []
    reason = ""
    if valid_laps < MIN_LAPS:
        missing.append("laps")
        reason = s["need_laps"].format(n=MIN_LAPS, have=valid_laps)
    elif goals <= 0:
        missing.append("weakness")
        reason = s["need_weakness"]
    return Readiness(ready=not missing, laps=valid_laps,
                     laps_needed=max(0, MIN_LAPS - valid_laps),
                     missing=missing, reason=reason)


# --- where the time is ------------------------------------------------------

def build_gap(best_ms: int, ideal_ms: int, your_sectors: list[int],
              best_sectors: list[int], *, per_lap_ms: float = 0.0,
              pro_ms: int = 0, lang: str = "it") -> Gap | None:
    """The distance to the theoretical ideal, and which sector holds it.

    ``your_sectors`` is your best lap cut into sectors; ``best_sectors`` is the
    best you have ever done in each — the two the Sectors tab already shows side
    by side. The per-sector gaps sum to the lap gap by construction, which is
    why this can name a sector without estimating anything.
    """
    if best_ms <= 0 or ideal_ms <= 0:
        return None
    s = _s(lang)
    consistency = max(0, best_ms - ideal_ms)

    sectors: list[SectorGap] = []
    if len(your_sectors) == len(best_sectors) and your_sectors:
        sectors = [SectorGap(number=i + 1, your_ms=int(y), best_ms=int(b),
                             gap_ms=int(y) - int(b))
                   for i, (y, b) in enumerate(zip(your_sectors, best_sectors))]

    worst_n, worst_ms = 0, 0
    if sectors:
        w = max(sectors, key=lambda x: x.gap_ms)
        # Only named when it is actually a place: a sector holding four
        # hundredths of an eight-tenth gap is not where the time is.
        if w.gap_ms >= _SECTOR_FLOOR_MS:
            worst_n, worst_ms = w.number, w.gap_ms

    # A gap of five thousandths is not "time you have already driven, in
    # pieces" — it is your best lap, and saying otherwise sends the driver to
    # practise repeating a lap they already repeat.
    if consistency < SIGNIF_LOSS_MS:
        head = s["gap_head_tight"].format(best=format_lap_time(best_ms),
                                          ideal=format_lap_time(ideal_ms))
        worst_n = worst_ms = 0
    else:
        head = s["gap_head"].format(best=format_lap_time(best_ms),
                                    ideal=format_lap_time(ideal_ms),
                                    gap=_sec(consistency))
        if worst_n:
            head += s["gap_worst"].format(ws=_sec(worst_ms), n=worst_n)
    pro_gap = max(0, ideal_ms - pro_ms) if pro_ms > 0 else 0
    if pro_gap:
        head += s["gap_pro"].format(pro=format_lap_time(pro_ms), pg=_sec(pro_gap))

    # The note only makes sense once there are two numbers to keep apart, and
    # both have to be big enough to be worth keeping apart.
    note = (s["gap_note"].format(gap=_sec(consistency), lap=_sec(per_lap_ms))
            if per_lap_ms >= SIGNIF_LOSS_MS and consistency >= SIGNIF_LOSS_MS
            else "")

    return Gap(best_ms=best_ms, ideal_ms=ideal_ms, consistency_ms=consistency,
               sectors=sectors, worst_sector=worst_n, worst_sector_ms=worst_ms,
               per_lap_ms=round(per_lap_ms, 1), pro_ms=pro_ms,
               pro_gap_ms=pro_gap, headline=head, note=note)


# --- which drill ------------------------------------------------------------

def dominant_phase(debriefs: list[LapDebrief], corner_index: int) -> str:
    """Where inside this corner the time typically goes, across recent laps.

    The median across laps, not the worst lap's: a drill is chosen for what the
    driver *usually* does, and one dramatic entry mistake shouldn't send them to
    practise braking for a corner they normally lose on exit. Empty when no
    phase carries enough of the loss — ``phases.py`` already refuses to name a
    place in that case, and so does this.
    """
    per_phase: dict[str, list[float]] = {}
    totals: list[float] = []
    for d in debriefs:
        for loss in d.losses:
            if loss.index != corner_index or not loss.phases:
                continue
            totals.append(loss.lost_ms)
            for p in loss.phases:
                per_phase.setdefault(p.phase, []).append(p.lost_ms)
    if not totals or not per_phase:
        return ""
    typical = statistics.median(totals)
    if typical <= 0:
        return ""
    phase, share = max(((k, statistics.median(v)) for k, v in per_phase.items()),
                       key=lambda kv: kv[1])
    # Same bar phases.phase_note uses: under it the loss is spread around the
    # corner, and pointing at one part would send the driver to the wrong place.
    return phase if share >= 0.4 * typical else ""


_BY_CATEGORY = {
    _C.BRAKE_LATER: "brake_move_later",
    _C.BRAKE_EARLIER: "brake_release",
    _C.LESS_BRAKE: "brake_release",
    _C.CARRY_SPEED: "apex_speed",
    _C.MORE_THROTTLE: "exit_throttle",
}


def drill_key(category: str, phase: str) -> str:
    """Which exercise this corner gets.

    Phase first, category second, and that order is the point: *where in the
    corner* the clock ran is a measurement, while the category is a label put on
    the dominant symptom. A corner tagged "carry more entry speed" whose time
    actually goes on exit needs the exit drill — practising entry speed there
    would be training the label instead of the problem.
    """
    if phase == "entry":
        return ("brake_release"
                if category in (_C.LESS_BRAKE.value, _C.BRAKE_EARLIER.value)
                else "brake_move_later")
    if phase == "apex":
        return "apex_speed"
    if phase in ("exit", "after"):
        return "exit_throttle"
    for cat, key in _BY_CATEGORY.items():
        if cat.value == category:
            return key
    return "repeat"


# --- the drills themselves --------------------------------------------------
# One builder per drill. They take the measured facts and drop the ones they
# don't have: a step that would read "your point moves  m from lap to lap" is
# worse than the same drill with four steps instead of five.

def _speed_gain(f: CornerFacts) -> int:
    """How much minimum speed there is to find here, as whole km/h — 0 if none.

    Rounded before the comparison so the sentence and its own arithmetic agree,
    and floored at the corner's own repeatability: telling a driver to find two
    km/h at a corner where their own laps already swing by five is telling them
    to chase their own noise, and it read as a target ("+0 km/h") on a real lap.
    """
    if f.min_speed_kmh <= 0 or f.min_speed_ref_kmh <= 0:
        return 0
    gain = round(f.min_speed_ref_kmh) - round(f.min_speed_kmh)
    return int(gain) if gain >= _REPEATABLE_KMH else 0


def _brake_move_later(f: CornerFacts, s: dict) -> Drill:
    steps: list[str] = []
    # Three versions of the same opening line, because the braking sheet gives
    # a different amount depending on the lap: metres need coordinates and older
    # laps (and every ACC lap in our own archive) don't have them, while speed
    # and gear are always there.
    if f.brake_speed_kmh > 0 and f.brake_distance_m > 0:
        steps.append(s["d.brake_move_later.s0"].format(
            v=f"{f.brake_speed_kmh:.0f}", g=f.brake_gear or "?",
            d=f"{f.brake_distance_m:.0f}"))
    elif f.brake_speed_kmh > 0:
        steps.append(s["d.brake_move_later.s0d"].format(
            v=f"{f.brake_speed_kmh:.0f}", g=f.brake_gear or "?"))
    else:
        steps.append(s["d.brake_move_later.s0b"])
    if f.landmark:
        steps.append(s["d.brake_move_later.s0c"].format(lm=f.landmark))
    if f.brake_spread_m >= 1.0:
        steps.append(s["d.brake_move_later.s1"].format(m=f"{f.brake_spread_m:.0f}"))
    elif f.brake_spread_kmh >= 1.0:
        steps.append(s["d.brake_move_later.s1c"].format(k=f"{f.brake_spread_kmh:.0f}"))
    else:
        steps.append(s["d.brake_move_later.s1b"])
    steps.append(s["d.brake_move_later.s2"])
    steps.append(s["d.brake_move_later.s3"])
    if f.min_speed_kmh > 0:
        steps.append(s["d.brake_move_later.s4"].format(v=f"{f.min_speed_kmh:.0f}"))
    return Drill(key="brake_move_later", title=s["d.brake_move_later.title"],
                 laps=8, steps=steps, watch=s["d.brake_move_later.watch"],
                 ignore=s["d.brake_move_later.ignore"])


def _brake_release(f: CornerFacts, s: dict) -> Drill:
    steps = [s["d.brake_release.s0"], s["d.brake_release.s1"],
             s["d.brake_release.s2"], s["d.brake_release.s3"]]
    if _speed_gain(f):
        steps.append(s["d.brake_release.s4"].format(
            vr=f"{f.min_speed_ref_kmh:.0f}", v=f"{f.min_speed_kmh:.0f}"))
    return Drill(key="brake_release", title=s["d.brake_release.title"], laps=6,
                 steps=steps, watch=s["d.brake_release.watch"],
                 ignore=s["d.brake_release.ignore"])


def _apex_speed(f: CornerFacts, s: dict) -> Drill:
    steps: list[str] = []
    gain = _speed_gain(f)
    if gain:
        # The difference is taken between the *printed* numbers, not the raw
        # ones: 80.4 against 76.8 prints "80 km/h" and "77 km/h" and then said
        # "+4", which is a subtraction the reader can see is wrong.
        steps.append(s["d.apex_speed.s0"].format(
            vr=f"{f.min_speed_ref_kmh:.0f}", v=f"{f.min_speed_kmh:.0f}",
            diff=f"{gain:+.0f}"))
    steps += [s["d.apex_speed.s1"], s["d.apex_speed.s2"], s["d.apex_speed.s3"],
              s["d.apex_speed.s4"]]
    return Drill(key="apex_speed", title=s["d.apex_speed.title"], laps=6,
                 steps=steps, watch=s["d.apex_speed.watch"],
                 ignore=s["d.apex_speed.ignore"])


def _exit_throttle(_f: CornerFacts, s: dict) -> Drill:
    return Drill(key="exit_throttle", title=s["d.exit_throttle.title"], laps=6,
                 steps=[s["d.exit_throttle.s0"], s["d.exit_throttle.s1"],
                        s["d.exit_throttle.s2"], s["d.exit_throttle.s3"],
                        s["d.exit_throttle.s4"]],
                 watch=s["d.exit_throttle.watch"],
                 ignore=s["d.exit_throttle.ignore"])


def _repeat(f: CornerFacts, s: dict) -> Drill:
    steps = [s["d.repeat.s0"], s["d.repeat.s1"], s["d.repeat.s2"]]
    if f.spread_kmh > 0:
        steps.append(s["d.repeat.s3"].format(s=f"{f.spread_kmh:.0f}",
                                             r=f"{_REPEATABLE_KMH:.0f}"))
    steps.append(s["d.repeat.s4"])
    return Drill(key="repeat", title=s["d.repeat.title"], laps=10, steps=steps,
                 watch=s["d.repeat.watch"], ignore=s["d.repeat.ignore"])


def _consistency(gap: Gap, s: dict) -> Drill:
    steps = [s["d.consistency.s0"].format(ideal=format_lap_time(gap.ideal_ms))]
    if gap.worst_sector:
        steps.append(s["d.consistency.s1"].format(
            gap=_sec(gap.consistency_ms), ws=_sec(gap.worst_sector_ms),
            n=gap.worst_sector))
    else:
        steps.append(s["d.consistency.s1b"].format(gap=_sec(gap.consistency_ms)))
    steps += [s["d.consistency.s2"], s["d.consistency.s3"]]
    steps.append(s["d.consistency.s4"].format(n=gap.worst_sector)
                 if gap.worst_sector else s["d.consistency.s4b"])
    return Drill(key="consistency", title=s["d.consistency.title"], laps=10,
                 steps=steps, watch=s["d.consistency.watch"],
                 ignore=s["d.consistency.ignore"])


_BUILDERS = {
    "brake_move_later": _brake_move_later,
    "brake_release": _brake_release,
    "apex_speed": _apex_speed,
    "exit_throttle": _exit_throttle,
    "repeat": _repeat,
}


def build_drill(category: str, phase: str, facts: CornerFacts,
                lang: str = "it") -> Drill:
    """The exercise for one corner, filled with that corner's own numbers."""
    key = drill_key(category, phase)
    return _BUILDERS[key](facts, _s(lang))


# --- the programme ----------------------------------------------------------

def build_programme(plan: TrainingPlan, progress: list[GoalProgress],
                    debriefs: list[LapDebrief], gap: Gap | None,
                    facts: dict[int, CornerFacts] | None = None,
                    *, valid_laps: int = 0, lang: str = "it",
                    inherited_sources: set[int] | None = None) -> Programme:
    """The whole section: the gate, the gap, the ordered steps, the next session.

    ``plan`` decides *what* — this function only decides the order, the drill and
    the words. ``inherited_sources`` are corners the chain analysis blamed for a
    *later* corner's loss; they are promoted to the front, because fixing the
    corner that hands over the deficit fixes two, and doing it the other way
    round fixes neither.
    """
    s = _s(lang)
    facts = facts or {}
    inherited_sources = inherited_sources or set()

    readiness = assess(valid_laps, len(plan.goals), lang)
    if not readiness.ready:
        return Programme(readiness=readiness, gap=gap)

    by_index = {p.corner_index: p for p in progress}

    corner_steps: list[tuple[int, Step]] = []
    for g in plan.goals:
        p = by_index.get(g.corner_index)
        phase = dominant_phase(debriefs, g.corner_index)
        f = facts.get(g.corner_index, CornerFacts())
        chained = g.corner_index in inherited_sources
        step = Step(
            order=0, kind="corner", corner_index=g.corner_index,
            where=g.name, what=g.what, why="",
            target=s["target"].format(to=_sec(g.target_ms),
                                      from_=_sec(g.baseline_ms)),
            done_when=(s["done_when"].format(needed=p.needed)
                       if p and p.needed else s["done_when_plain"]),
            status="done" if (p and p.done) else "later",
            drill=build_drill(g.category, phase, f, lang),
        )
        # Sort key: chained sources first, then the plan's own order (which is
        # the trend order — worst total first).
        corner_steps.append((0 if chained else 1, step))

    corner_steps.sort(key=lambda x: x[0])
    steps = [st for _, st in corner_steps]

    cons = _consistency_step(gap, s, lang)
    if cons is not None:
        # First when repeating yourself is worth more than the corners are: a
        # driver who leaves half a second on the table by never stringing two
        # laps together is not short of technique.
        bleed = sum(g.baseline_ms for g in plan.goals)
        first = bool(gap and gap.consistency_ms > bleed)
        cons.why = s["why_cons_first"] if first else s["why_cons_last"]
        steps.insert(0, cons) if first else steps.append(cons)

    steps = steps[:MAX_STEPS]
    for i, st in enumerate(steps):
        st.order = i + 1
    first_open = next((st for st in steps if st.status != "done"), None)
    if first_open is not None:
        first_open.status = "now"

    # The "why" is written last, because it is entirely about *position* — and
    # the position isn't settled until the consistency step has taken its place.
    # Filling it earlier is how two steps both came out saying "start here".
    for st in steps:
        if st.kind != "corner":
            continue
        if st.status == "done":
            st.why = s["why_done"]
            continue
        rec = _recurrence(debriefs, st.corner_index)
        if st is first_open:
            victim = _chain_victim(debriefs, st.corner_index)
            st.why = (s["why_chain"].format(victim=victim) if victim
                      else s["why_first"].format(**rec))
        else:
            st.why = s["why_later"].format(**rec)

    return Programme(readiness=readiness, gap=gap, steps=steps,
                     session=_session(first_open, plan, s))


def _consistency_step(gap: Gap | None, s: dict, lang: str) -> Step | None:
    """The lap-wide step, when there is a gap to the ideal worth naming."""
    if gap is None or gap.consistency_ms < SIGNIF_LOSS_MS:
        return None
    return Step(
        order=0, kind="consistency", corner_index=-1,
        where="", what="", why="",
        target=s["target_cons"].format(ideal=format_lap_time(gap.ideal_ms)),
        # Half the gap back, floored where the app stops calling a loss
        # significant — plan.py's own rule, imported rather than restated so a
        # corner target and a lap target can never ask for different things.
        done_when=s["done_when_cons"].format(s=_sec(_take_back(gap.consistency_ms))),
        status="later", drill=_consistency(gap, s),
    )


def _recurrence(debriefs: list[LapDebrief], corner_index: int) -> dict:
    """How often this corner cost significant time, for the "why this first"."""
    laps = len(debriefs)
    occ = sum(1 for d in debriefs
              for loss in d.losses
              if loss.index == corner_index and loss.lost_ms >= SIGNIF_LOSS_MS)
    return {"occ": occ, "laps": laps}


def _chain_victim(debriefs: list[LapDebrief], corner_index: int) -> str:
    """The corner that pays for this one, when the chain analysis found a link.

    The name, not the debrief's own chain sentence — that sentence is written
    from the *victim's* point of view ("you arrive 5 km/h down, and you had them
    at the exit of Acque Minerali"), so printing it on the card of the corner
    that causes the loss reads as if the corner inherits from itself. Which
    corners are linked at all is still entirely ``chain.py``'s call: it is
    written as a list of reasons to stay silent, and nothing here second-guesses
    a link it refused to make.
    """
    for d in debriefs:
        for loss in d.losses:
            if loss.inherited_from == corner_index and loss.inherited:
                return loss.label
    return ""


def _session(step: Step | None, plan: TrainingPlan, s: dict) -> Session | None:
    """The next time you sit down, as laps to run.

    Only the current step gets a session. Two drills in one run is how a
    programme becomes a list again — and the drills contradict each other on
    purpose (one says leave the braking point alone, another says move it).
    """
    if step is None or step.drill is None:
        return None
    warm, free = 3, 3
    # The consistency step has no corner, and the line used to end in a dash
    # standing where a corner name should be.
    where = s["ses_drill"].format(n=step.drill.laps, title=step.drill.title,
                                  where=step.where) if step.where else \
        s["ses_drill_lap"].format(n=step.drill.laps, title=step.drill.title)
    lines = [s["ses_warm"], where, s["ses_free"]]
    lines.append(s["ses_back_plan"].format(when=plan.created_utc[:10])
                 if plan.created_utc else s["ses_back"])
    return Session(laps=warm + step.drill.laps + free, lines=lines)
