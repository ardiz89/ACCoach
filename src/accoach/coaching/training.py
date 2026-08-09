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
from .tuning import tuning_for_car

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
    # Come sta la curva contro l'inviluppo di aderenza del riferimento, così
    # com'è misurato dal debrief (``debrief.GripState``). Non serve a stampare
    # una riga: serve a **non prescrivere** l'esercizio sbagliato. Lasciato a
    # ``None`` quando il giro è anteriore ai canali G, e in quel caso il
    # cancello non scatta — che è la scelta giusta: si torna al comportamento
    # di prima invece di bloccare un esercizio su un dato che non c'è.
    grip: object | None = None


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
class GlossaryEntry:
    """One word the driver will hear other people use, and what it means."""

    term: str
    definition: str


@dataclass(slots=True)
class Programme:
    """The whole section, ready or not."""

    readiness: Readiness
    gap: Gap | None = None
    steps: list[Step] = field(default_factory=list)
    session: Session | None = None
    glossary: list[GlossaryEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ready": self.readiness.ready,
            "readiness": asdict(self.readiness),
            "gap": asdict(self.gap) if self.gap else None,
            "steps": [asdict(s) for s in self.steps],
            "session": asdict(self.session) if self.session else None,
            "glossary": [asdict(g) for g in self.glossary],
        }


# --- words ------------------------------------------------------------------
# Same arrangement as flow.py: user-facing prose lives next to the rule that
# decides whether to say it, so a rule and its sentence can't drift apart.
#
# **Who is reading.** This tab exists because the rest of the app assumes a
# reader who can already do the last step alone. So the rule for every sentence
# below is: a word only a sim-racer of some years would know either goes, or is
# explained where it stands. Concretely:
#
# * plain words win where they lose nothing — "il punto in cui inizi a frenare"
#   rather than "la staccata", "inizia a frenare" rather than "stacca";
# * a term the rest of the app uses (*settore*, *ideale teorico*, *apex*) stays,
#   because a driver who learns it here will meet it on the other tabs — but it
#   is glossed the first time it appears **inside the drill you have open**.
#   That is the right unit: only one drill is ever expanded on screen, so a
#   gloss repeated across drills is not repetition to any reader;
# * no term is introduced only to be defined later. "Ideale teorico" is
#   *defined and then named* ("i tuoi settori migliori messi insieme — è quello
#   che qui si chiama ideale teorico"), never the other way round;
# * one word, one meaning. *Riferimento* used to mean both the comparison lap
#   and a thing you look at out of the window; the second sense is now "un punto
#   che vedi con gli occhi", and *curva* is never also the line on a chart.
#
# These strings are inserted as HTML (the page builds `<li>` from them), so `&`
# is written `&amp;` and no other markup belongs here.

_T = {
    "it": {
        "need_laps": "Servono {n} giri validi su questa auto e questa pista "
                     "prima che allenarsi voglia dire qualcosa: ne hai {have}. "
                     "Con meno, quello che sembra un punto debole è solo quello "
                     "che è successo in due giri.",
        "need_weakness": "Hai giri a sufficienza, ma nessun errore si ripete "
                         "abbastanza da chiamarsi punto debole: quello che perdi "
                         "cambia curva da un giro all'altro. Guida ancora un "
                         "po' — oppure guarda «Punti deboli» in Andamento per "
                         "vedere cosa manca a poco.",
        "gap_head": "Il tuo miglior giro è {best}. Prendendo i tuoi tempi "
                    "migliori — uno per ognuno dei tre settori in cui è diviso "
                    "il giro — e mettendoli insieme viene fuori {ideal}: è "
                    "quello che qui si chiama ideale teorico, e sono {gap}s che "
                    "hai già guidato, ma mai tutti nello stesso giro.",
        "gap_head_tight": "Il tuo miglior giro è {best}. Prendendo i tuoi tempi "
                          "migliori — uno per ognuno dei tre settori in cui è "
                          "diviso il giro — e mettendoli insieme viene fuori "
                          "{ideal}: praticamente lo stesso giro. Vuol dire che "
                          "sei già costante, e quel poco che resta non lo prendi "
                          "ripetendoti: lo prendi nelle curve.",
        "gap_worst": " Il grosso — {ws}s — sta nel settore {n}.",
        "gap_note": "Questi due numeri non si sommano. I {gap}s dicono quanto ti "
                    "costa non ripeterti: sono i tuoi settori migliori contro il "
                    "tuo miglior giro. I {lap}s dicono quanto perdi nelle curve "
                    "del piano: sono i tuoi ultimi giri contro quello stesso "
                    "giro migliore. In parte è lo stesso tempo, contato da due "
                    "parti.",
        "gap_pro": " Il giro veloce che hai importato è {pro}, altri {pg}s più "
                   "in là: quello sì è tempo che non hai ancora guidato.",
        "why_first": "Si comincia da qui: è la perdita più grande che si "
                     "ripete ({occ} giri su {laps}).",
        "why_chain": "Si comincia da qui anche se non è la perdita più grande: "
                     "il tempo che perdi a {victim} nasce in questa curva. Un "
                     "esercizio solo, due curve sistemate.",
        "why_later": "Poi questa, che si ripete in {occ} giri su {laps}. Una "
                     "cosa alla volta: due esercizi nella stessa sessione si "
                     "annullano a vicenda.",
        "why_done": "Fatto: l'obiettivo è stato centrato nei giri dopo l'avvio "
                    "del piano.",
        "why_cons_first": "Si comincia da qui: quello che ti costa di più non è "
                          "una curva, è che non rifai due volte lo stesso giro.",
        "why_cons_last": "Per ultimo, quando le curve qui sopra sono entrate: "
                         "questo passo serve a incollarle in un giro solo.",
        "target": "in questa curva perdi {from_}s: portali sotto {to}s",
        "target_cons": "metti insieme i tuoi settori migliori: {ideal}",
        "done_when": "Fatto quando centri l'obiettivo in {needed} dei giri che "
                     "guidi da qui in poi. È la stessa quota di giri che ha reso "
                     "questa curva un punto debole.",
        "done_when_plain": "Fatto quando centri l'obiettivo in metà dei giri che "
                           "guidi da qui in poi.",
        "done_when_cons": "Fatto quando fra il tuo miglior giro e i tuoi settori "
                          "migliori messi insieme restano meno di {s}s. È metà "
                          "di quello che c'è adesso: la stessa metà che il piano "
                          "chiede in curva.",
        "ses_warm": "3 giri di riscaldamento. Gomme e freni in temperatura, "
                    "cronometro spento: un giro freddo non dice niente, e nei "
                    "primi giri l'auto cambia sotto di te.",
        "ses_drill": "{n} giri di esercizio: {title} — {where}.",
        "ses_drill_lap": "{n} giri di esercizio, sul giro intero: {title}.",
        "ses_free": "3 giri liberi, guidati normale. Servono a vedere se "
                    "l'esercizio è entrato quando smetti di pensarci.",
        "ses_fuel": "Falli con lo stesso carico di benzina e sullo stesso treno "
                    "di gomme: dieci giri di fila abbassano il tempo da soli, e "
                    "non saresti stato tu.",
        "ses_back": "Poi torna qui: contano solo i giri che guidi da adesso in "
                    "poi.",
        "ses_back_plan": "Poi torna qui: contano solo i giri guidati dopo il "
                         "{when}.",
        # --- gli esercizi ---
        "d.brake_move_later.title": "Sposta il punto di frenata più avanti, "
                                    "una lunghezza d'auto per volta",
        "d.brake_move_later.watch": "la velocità minima in curva, cioè la più "
                                    "bassa che tocchi (scheda Confronto → Velocità)",
        "d.brake_move_later.ignore": "il tempo sul giro: in questi giri non conta",
        "d.brake_move_later.s0": "Guarda dov'è adesso il punto in cui inizi a "
                                 "frenare: lo tocchi a {v} km/h in {g}ª, {d} m "
                                 "prima del punto più lento della curva.",
        "d.brake_move_later.s0b": "Guarda dov'è adesso il punto in cui inizi a "
                                  "frenare: la scheda «Le tue frenate», sotto la "
                                  "mappa nel Confronto, dice a che velocità e in "
                                  "che marcia lo tocchi.",
        "d.brake_move_later.s0d": "Guarda dov'è adesso il punto in cui inizi a "
                                  "frenare: lo tocchi a {v} km/h in {g}ª.",
        "d.brake_move_later.s0c": "Un punto che vedi con gli occhi, invece di un "
                                  "numero: {lm}.",
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
        "d.brake_move_later.s2": "Poi spostalo più avanti — cioè frena più "
                                 "tardi — di una lunghezza d'auto per giro. "
                                 "Cinque metri, non venti: cinque metri li "
                                 "guidi, venti li subisci.",
        "d.brake_move_later.s2b": "Frenare più tardi non vuol dire frenare più a "
                                  "lungo: il colpo forte va dato subito, nel "
                                  "primo mezzo secondo, e poi si scarica man "
                                  "mano che rallenti. Se una ruota si blocca non "
                                  "si blocca all'inizio, si blocca in fondo, "
                                  "proprio dove stai girando.",
        "d.brake_move_later.s3": "Sei andato oltre quando cominci a bloccare le "
                                 "ruote dove prima non bloccavi — e se l'auto ha "
                                 "l'ABS non si bloccheranno affatto: sentirai il "
                                 "pedale vibrare sotto il piede e l'auto andare "
                                 "dritta invece di girare — oppure quando passi "
                                 "lontano dal bordo interno. Torna al punto di "
                                 "prima e restaci due giri: quello giusto è "
                                 "l'ultimo che sai ripetere, non il punto più "
                                 "estremo che hai provato.",
        "d.brake_move_later.s4": "Tieni d'occhio la velocità minima, la più "
                                 "bassa che tocchi in curva: adesso è {v} km/h. "
                                 "Se scende mentre freni più tardi, hai "
                                 "guadagnato in frenata e restituito dentro la "
                                 "curva — non è un guadagno, è uno spostamento.",
        "d.brake_release.title": "Scarica il freno, non la velocità",
        "d.brake_release.watch": "il grafico Gas / Freno (scheda Confronto): la "
                                 "tua linea del freno deve scendere in diagonale "
                                 "verso la curva, non restare alta e poi cadere "
                                 "a picco",
        "d.brake_release.ignore": "il punto in cui inizi a frenare: in questi "
                                  "giri non si tocca",
        "d.brake_release.s0": "Qui il problema non è quando cominci a frenare, è "
                              "quanto ci resti sopra mentre giri: in gergo si "
                              "chiama trail braking. Lascia il punto dov'è.",
        "d.brake_release.s1": "Due giri esagerando da un lato: appena giri il "
                              "volante, il freno è già a zero. Uscirai largo e "
                              "lento — va bene, è metà della misura.",
        "d.brake_release.s2": "Due giri esagerando dall'altro: tieni un filo di "
                              "freno fino al punto in cui passi più vicino al "
                              "bordo interno (l'apex). Sentirai l'anteriore "
                              "mordere di più e l'auto girare di più, ma anche "
                              "fermarsi troppo.",
        "d.brake_release.s2b": "Fallo in una curva lenta, mai in una veloce. Se "
                               "senti il posteriore che scappa non staccare il "
                               "piede di colpo: molla il freno piano e "
                               "raddrizza.",
        "d.brake_release.s3": "Il punto giusto sta in mezzo, e adesso lo hai "
                              "sentito da tutti e due i lati. Due giri lì.",
        "d.brake_release.s4": "Il giro di riferimento, quello con cui ti "
                              "confronti, passa qui a {vr} km/h e tu a {v}: se "
                              "lasci il freno al momento giusto, quel numero "
                              "sale da solo.",
        "d.apex_speed.title": "Trova la velocità minima, poi difendila",
        "d.apex_speed.watch": "la velocità minima in questa curva, cioè la più "
                              "bassa che tocchi",
        "d.apex_speed.ignore": "il tempo sul giro: questi giri servono a "
                               "misurare, non a essere veloci",
        "d.apex_speed.s0": "Il giro di riferimento, quello con cui ti confronti, "
                           "passa qui a {vr} km/h e tu a {v}: {diff} km/h. Prima "
                           "di inseguirlo devi sapere quanta velocità la "
                           "macchina regge davvero.",
        "d.apex_speed.s1": "Due giri di misura, senza togliere il freno: stesso "
                           "punto di frenata, e ogni giro premi un filo meno — "
                           "un decimo di pedale, non metà. Vai avanti finché la "
                           "macchina comincia ad allargare, oppure finché il "
                           "retro si alleggerisce: quella è la velocità che "
                           "regge davvero.",
        "d.apex_speed.s1b": "Se arrivi troppo forte non alzare il piede di "
                            "scatto e non frenare in mezzo alla curva: tieni il "
                            "gas fermo dov'è, apri il volante e accetta di "
                            "uscire largo. È il piede alzato di colpo che manda "
                            "il posteriore, non la velocità in sé.",
        "d.apex_speed.s2": "Adesso rimetti il freno con un obiettivo solo: non "
                           "scendere sotto quella velocità. Il grosso della "
                           "frenata sta prima di girare; quello che resta lo "
                           "scarichi poco alla volta, mai staccando il piede di "
                           "colpo.",
        "d.apex_speed.s3": "Allarga l'ingresso di un paio di metri. In curva la "
                           "velocità dipende da quanto è largo l'arco che "
                           "disegni, non dal coraggio: la stessa curva, presa "
                           "più larga, si fa più veloce.",
        "d.apex_speed.s3b": "Un'eccezione: se dopo questa curva c'è un "
                            "rettilineo lungo, la velocità minima più alta non è "
                            "per forza il giro più veloce — lì conta di più "
                            "uscire dritti presto.",
        "d.apex_speed.s4": "Nella scheda Traiettoria vedi dove passi rispetto al "
                           "giro di riferimento. Se entri più stretto di quel "
                           "giro, la velocità minima non sale, per quanto "
                           "insisti.",
        "d.exit_throttle.title": "L'uscita si prepara prima, non dopo",
        "d.exit_throttle.watch": "il gas in uscita (scheda Confronto → Gas / "
                                 "Freno): deve solo salire — se scende e poi "
                                 "risale, l'avevi aperto troppo presto",
        "d.exit_throttle.ignore": "la parte iniziale della curva: qui accetti di "
                                  "perderci qualcosa",
        "d.exit_throttle.s0": "Scegli un punto d'uscita che vedi — un cordolo, "
                              "una riga — e decidi che da lì in poi il gas sale "
                              "e non torna più indietro. Non «tutto a fondo»: da "
                              "lì in poi si apre e basta. Lo stesso punto per "
                              "tutti i giri dell'esercizio.",
        "d.exit_throttle.s1": "Due giri per capire cosa ti impedisce di aprirlo. "
                              "Se devi ancora sterzare, ci sei arrivato troppo "
                              "forte. Se le ruote motrici girano più veloci di "
                              "quanto l'auto avanza — o se senti il controllo di "
                              "trazione entrare, con il motore che si strozza e "
                              "i giri che non salgono — sei arrivato al punto "
                              "più vicino al bordo interno (l'apex) con l'auto "
                              "ancora piegata e le ruote ancora sterzate.",
        "d.exit_throttle.s1b": "Prova la stessa uscita con una marcia più alta: "
                               "la stessa apertura di gas spinge meno di colpo, "
                               "e spesso il pattinamento sparisce senza cambiare "
                               "altro.",
        "d.exit_throttle.s2": "Rimedia prima, non dopo: entra un filo più piano "
                              "e più largo, e arriva all'apex con la macchina "
                              "già quasi dritta. Perdi qualcosa in ingresso e lo "
                              "riprendi con gli interessi sul dritto che segue.",
        "d.exit_throttle.s3": "Apri il gas poco alla volta e continua ad aprire, "
                              "non tutto in una volta come un interruttore.",
        "d.exit_throttle.s4": "Nella scheda Dinamica, il grafico «Bloccaggio e "
                              "pattinamento»: la riga arancione è il posteriore, "
                              "e in uscita deve restare quasi piatta. Ma se "
                              "l'auto ha il controllo di trazione resterà piatta "
                              "comunque, perché è lui a tenerla: lì il segnale "
                              "vero è l'orecchio, il motore che si strozza.",
        "d.repeat.title": "Prima ripetibile, poi veloce",
        "d.repeat.watch": "quanto si somigliano due giri di fila",
        "d.repeat.ignore": "il tempo sul giro",
        "d.repeat.s0": "Qui non c'è una causa dominante: perdi un po' "
                       "dappertutto. Quasi sempre è un problema di ripetizione, "
                       "non di tecnica.",
        "d.repeat.s1": "Scegli tre punti fissi per questa curva — dove inizi a "
                       "frenare, dove giri il volante, dove riapri il gas — e "
                       "dilli ad alta voce mentre ci passi. Detti a voce "
                       "diventano decisioni; pensati restano sensazioni.",
        "d.repeat.s2": "Cinque giri con una regola sola: non cercare il tempo, "
                       "cerca di fare due giri uguali.",
        "d.repeat.s3": "Adesso la tua velocità minima qui — la più bassa che "
                       "tocchi — balla di {s} km/h da un giro all'altro. Sotto i "
                       "{r} km/h la curva è tua: scendere ancora vuol dire "
                       "rincorrere differenze che non dipendono da te.",
        "d.repeat.s4": "Solo quando riesci a ripeterla, prova a spostare uno dei "
                       "tre punti. Uno.",
        "d.consistency.title": "Il giro che hai già fatto, tutto insieme",
        "d.consistency.watch": "i tre settori, non il tempo sul giro",
        "d.consistency.ignore": "il tempo sul giro — è l'unica cosa qui che si "
                                "sistema da sola",
        "d.consistency.s0": "Non è un tempo inventato: è il tuo tempo migliore "
                            "in ogni settore, messo insieme. Fa {ideal}, e l'hai "
                            "già guidato tutto — solo mai nello stesso giro.",
        "d.consistency.s1": "Ti mancano {gap}s per metterlo insieme, e {ws}s "
                            "stanno nel settore {n}: è lì che vai a lavorare.",
        "d.consistency.s1b": "Ti mancano {gap}s per metterlo insieme, e sono "
                             "sparsi: nessun settore te li tiene tutti.",
        "d.consistency.s2": "Cinque giri in cui non cerchi il tempo: cerchi di "
                            "ripetere. Stessa traiettoria, stessi punti, stesso "
                            "ordine.",
        "d.consistency.s3": "Regola per questi giri: se sbagli una curva, "
                            "finisci lo stesso il giro senza altri errori. "
                            "Quello che costa davvero è il pezzo di giro dopo "
                            "l'errore, ed è l'unico che puoi ancora salvare.",
        "d.consistency.s3b": "Non guardare se il tempo sul giro scende giro dopo "
                             "giro: con la benzina che cala e le gomme che si "
                             "consumano cambia comunque. Guarda se due giri di "
                             "fila si somigliano.",
        "d.consistency.s4": "Guarda «Settori»: l'obiettivo è che il settore {n} "
                            "smetta di essere il tuo peggiore, non che il tempo "
                            "sul giro scenda. Il tempo scende dopo.",
        "d.consistency.s4b": "Guarda «Settori»: l'obiettivo è che i tuoi tre "
                             "settori vengano dallo stesso giro, non che il "
                             "tempo sul giro scenda. Il tempo scende dopo.",
        "d.brake_straight.title": "Frena dritto, poi gira",
        "d.brake_straight.watch": "il grafico Gas / Freno (scheda Confronto): il "
                                  "freno deve essere finito prima che lo sterzo "
                                  "si muova",
        "d.brake_straight.ignore": "la velocità minima: qui sale da sola se "
                                   "l'ingresso è pulito",
        "d.brake_straight.s0": "Su un'auto senza carico aerodinamico si rallenta "
                               "dritti e poi si gira. Un filo di freno mentre "
                               "sterzi alleggerisce il posteriore proprio mentre "
                               "gli stai chiedendo di tenere.",
        "d.brake_straight.s1": "Due giri con tutta la frenata prima, forte e "
                               "corta, finita prima di girare il volante. "
                               "L'auto entrerà lenta e piatta: va bene, è il "
                               "punto di partenza.",
        "d.brake_straight.s2": "Metti la marcia della curva prima di girare: una "
                               "scalata fatta dentro la curva frena le ruote "
                               "posteriori da sola, e per l'auto è la stessa "
                               "cosa che alzare il piede di colpo.",
        "d.brake_straight.s3": "Adesso sposta la fine della frenata un metro "
                               "alla volta verso la curva, senza mai arrivare a "
                               "sterzare col freno ancora premuto forte.",
        "d.brake_straight.s4": "Se senti il retro alleggerirsi mentre giri, sei "
                               "andato oltre: torna al punto di prima. Su questa "
                               "auto il margine è più corto di quanto sembri.",
    },
    "en": {
        "need_laps": "You need {n} valid laps on this car and track before "
                     "training means anything, and you have {have}. Below that, "
                     "what looks like a weak point is just what happened on two "
                     "laps.",
        "need_weakness": "You have the laps, but nothing repeats often enough to "
                         "be called a weak point: what you lose moves from corner "
                         "to corner. Drive a little more — or open Weak points "
                         "under Trends to see what's close.",
        "gap_head": "Your best lap is {best}. Take your best time in each of the "
                    "three sectors the lap is split into and put them together "
                    "and you get {ideal}: that's what's called the theoretical "
                    "ideal, and it's {gap}s you have already driven, just never "
                    "all on the same lap.",
        "gap_head_tight": "Your best lap is {best}. Take your best time in each "
                          "of the three sectors the lap is split into and put "
                          "them together and you get {ideal} — practically the "
                          "same lap. That means you are already consistent, and "
                          "the little that's left isn't taken by repeating "
                          "yourself: it's taken in the corners.",
        "gap_worst": " Most of it — {ws}s — sits in sector {n}.",
        "gap_note": "These two numbers don't add up. The {gap}s say what not "
                    "repeating yourself costs: your best sectors against your "
                    "best lap. The {lap}s say what you lose in the plan's "
                    "corners: your recent laps against that same best lap. Part "
                    "of it is the same time, counted from two sides.",
        "gap_pro": " The fast lap you imported is {pro}, another {pg}s further "
                   "on: that one is time you have never driven.",
        "why_first": "Start here: it's the biggest loss that keeps coming back "
                     "({occ} laps out of {laps}).",
        "why_chain": "Start here even though it isn't the biggest loss: the time "
                     "you lose at {victim} is made in this corner. One exercise, "
                     "two corners fixed.",
        "why_later": "Then this one, which repeats on {occ} laps out of {laps}. "
                     "One at a time: two exercises in the same session cancel "
                     "each other out.",
        "why_done": "Done: you hit the target on the laps you drove after "
                    "starting the plan.",
        "why_cons_first": "Start here: what costs you most isn't a corner, it's "
                          "that you don't drive the same lap twice.",
        "why_cons_last": "Last, once the corners above have sunk in: this step "
                         "is what glues them into a single lap.",
        "target": "you lose {from_}s in this corner: get it under {to}s",
        "target_cons": "put your best sectors together: {ideal}",
        "done_when": "Done when you hit the target on {needed} of the laps you "
                     "drive from here. That's the same share of laps that made "
                     "this corner a weak point.",
        "done_when_plain": "Done when you hit the target on half the laps you "
                           "drive from here.",
        "done_when_cons": "Done when less than {s}s is left between your best "
                          "lap and your best sectors put together. That's half "
                          "of what's there now — the same half the plan asks for "
                          "in a corner.",
        "ses_warm": "3 warm-up laps. Tyres and brakes up to temperature, clock "
                    "off: a cold lap tells you nothing, and for the first few "
                    "laps the car changes under you.",
        "ses_drill": "{n} exercise laps: {title} — {where}.",
        "ses_drill_lap": "{n} exercise laps, over the whole lap: {title}.",
        "ses_free": "3 free laps, driven normally. They're there to show whether "
                    "the exercise sunk in once you stop thinking about it.",
        "ses_fuel": "Run them on the same fuel load and the same set of tyres: "
                    "ten laps in a row bring the time down on their own, and "
                    "that wouldn't have been you.",
        "ses_back": "Then come back here: only the laps you drive from now on "
                    "count.",
        "ses_back_plan": "Then come back here: only laps driven after {when} "
                         "count.",
        # --- the exercises ---
        "d.brake_move_later.title": "Move the braking point later, one car "
                                    "length at a time",
        "d.brake_move_later.watch": "your minimum speed in the corner, the lowest "
                                    "you touch (Compare tab → Speed)",
        "d.brake_move_later.ignore": "the lap time: it doesn't count on these laps",
        "d.brake_move_later.s0": "First, see where your braking point is now: you "
                                 "hit the brakes at {v} km/h in gear {g}, {d} m "
                                 "before the slowest point of the corner.",
        "d.brake_move_later.s0b": "First, see where your braking point is now: "
                                  "the «Your braking points» sheet, under the map "
                                  "in the Compare tab, says at what speed and in "
                                  "which gear you hit them.",
        "d.brake_move_later.s0d": "First, see where your braking point is now: "
                                  "you hit the brakes at {v} km/h in gear {g}.",
        "d.brake_move_later.s0c": "Something you can see with your eyes instead "
                                  "of a number: {lm}.",
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
        "d.brake_move_later.s2": "Then move it later — brake further on — one "
                                 "car length per lap. Five metres, not twenty: "
                                 "five metres you drive, twenty drive you.",
        "d.brake_move_later.s2b": "Braking later doesn't mean braking longer: the "
                                  "hard hit goes in straight away, in the first "
                                  "half second, then bleeds off as you slow. If a "
                                  "wheel locks it won't lock at the start, it'll "
                                  "lock at the end, right where you're turning.",
        "d.brake_move_later.s3": "You've gone past it when you start locking the "
                                 "wheels where you didn't before — and if the car "
                                 "has ABS they won't lock at all: you'll feel the "
                                 "pedal buzz under your foot and the car run "
                                 "straight instead of turning — or when you pass "
                                 "wide of the inside edge. Go back to the previous "
                                 "point and stay there two laps: the right one is "
                                 "the last you can repeat, not the most extreme "
                                 "you tried.",
        "d.brake_move_later.s4": "Keep an eye on your minimum speed — the lowest "
                                 "you touch in the corner — which is {v} km/h "
                                 "now. If it drops as you brake later, you gained "
                                 "under braking and gave it back inside the "
                                 "corner: that's a move, not a gain.",
        "d.brake_release.title": "Bleed the brake off, don't shed the speed",
        "d.brake_release.watch": "the Throttle / Brake chart (Compare tab): your "
                                 "brake line should slope down towards the "
                                 "corner, not stay high and then fall off a cliff",
        "d.brake_release.ignore": "where you start braking: leave it alone on "
                                  "these laps",
        "d.brake_release.s0": "The problem here isn't when you start braking, it's "
                              "how long you carry it while you turn: that's what's "
                              "called trail braking. Leave the point where it is.",
        "d.brake_release.s1": "Two laps overdoing it one way: the moment you turn "
                              "the wheel, the brake is already at zero. You'll run "
                              "wide and slow — good, that's half the measurement.",
        "d.brake_release.s2": "Two laps overdoing it the other way: carry a sliver "
                              "of brake all the way to the point where you pass "
                              "closest to the inside edge (the apex). You'll feel "
                              "the front grip harder and the car turn in more, but "
                              "also stop too much.",
        "d.brake_release.s2b": "Do this in a slow corner, never a fast one. If the "
                               "rear starts to step out, don't snap off the pedal: "
                               "bleed the brake off and straighten up.",
        "d.brake_release.s3": "The right release is in between, and you've now felt "
                              "both edges of it. Two laps there.",
        "d.brake_release.s4": "The reference lap, the one you're compared against, "
                              "goes through here at {vr} km/h and you at {v}: let "
                              "the brake go at the right moment and that number "
                              "climbs on its own.",
        "d.apex_speed.title": "Find the minimum speed, then defend it",
        "d.apex_speed.watch": "your minimum speed in this corner — the lowest "
                              "you touch",
        "d.apex_speed.ignore": "the lap time: these laps are for measuring, not "
                               "for being fast",
        "d.apex_speed.s0": "The reference lap, the one you're compared against, "
                           "goes through here at {vr} km/h and you at {v}: {diff} "
                           "km/h. Before chasing it you need to know how much "
                           "speed the car actually holds.",
        "d.apex_speed.s1": "Two measuring laps, without taking the brake away: "
                           "same braking point, and each lap press a shade less — "
                           "a tenth of the pedal, not half. Keep going until the "
                           "car starts running wide, or until the rear goes "
                           "light: that's the speed it actually holds.",
        "d.apex_speed.s1b": "If you arrive too fast, don't snap off the throttle "
                            "and don't brake mid-corner: hold the throttle where "
                            "it is, open the steering and accept running wide. "
                            "It's the sudden lift that sends the rear round, not "
                            "the speed itself.",
        "d.apex_speed.s2": "Now put the brake back with one goal: don't go below "
                           "that speed. The bulk of the braking happens before "
                           "you turn; what's left you bleed off gradually, never "
                           "lifting off in one go.",
        "d.apex_speed.s3": "Open the entry by a couple of metres. Corner speed "
                           "comes from how wide an arc you draw, not from "
                           "courage: the same corner taken wider is taken faster.",
        "d.apex_speed.s3b": "One exception: if a long straight follows this "
                            "corner, the highest minimum speed isn't necessarily "
                            "the fastest lap — there, getting straight early "
                            "matters more.",
        "d.apex_speed.s4": "The Line tab shows where you run against the "
                           "reference lap. Enter tighter than it and your minimum "
                           "speed won't come up, however hard you push.",
        "d.exit_throttle.title": "The exit is set up before, not after",
        "d.exit_throttle.watch": "the throttle on exit (Compare tab → Throttle / "
                                 "Brake): it should only ever go up — if it drops "
                                 "and climbs again, you opened it too early",
        "d.exit_throttle.ignore": "the first part of the corner: you're accepting "
                                  "a loss there",
        "d.exit_throttle.s0": "Pick an exit point you can see — a kerb, a line — "
                              "and decide that from there the throttle only goes "
                              "up and never comes back down. Not «flat out»: from "
                              "there it only opens. The same point on every lap "
                              "of the exercise.",
        "d.exit_throttle.s1": "Two laps to find out what stops you opening it. "
                              "Still steering means you got there too fast. If "
                              "the driven wheels spin faster than the car is "
                              "going — or if you feel the traction control cut "
                              "in, the engine bogging and the revs not climbing — "
                              "you reached the point where you pass closest to "
                              "the inside edge (the apex) with the car still "
                              "leaned over and the wheels still turned.",
        "d.exit_throttle.s1b": "Try the same exit one gear higher: the same "
                               "throttle opening arrives less abruptly, and the "
                               "wheelspin often disappears without changing "
                               "anything else.",
        "d.exit_throttle.s2": "Fix it earlier, not later: enter slightly slower "
                              "and wider, and reach the apex with the car already "
                              "nearly straight. You lose something on entry and "
                              "take it back with interest on the straight that "
                              "follows.",
        "d.exit_throttle.s3": "Open the throttle a bit at a time and keep opening, "
                              "not all at once like a switch.",
        "d.exit_throttle.s4": "In the Dynamics tab, the «Lock &amp; spin» chart: "
                              "the amber line is the rear, and on exit it should "
                              "stay almost flat. But if the car has traction "
                              "control it will stay flat anyway, because the TC "
                              "is holding it there: then the real signal is your "
                              "ear, the engine bogging.",
        "d.repeat.title": "Repeatable first, fast second",
        "d.repeat.watch": "how alike two consecutive laps are",
        "d.repeat.ignore": "the lap time",
        "d.repeat.s0": "There's no dominant cause here: you lose a little "
                       "everywhere. That's almost always a repetition problem, not "
                       "a technique one.",
        "d.repeat.s1": "Pick three fixed points for this corner — where you start "
                       "braking, where you turn the wheel, where you get back on "
                       "the throttle — and say them out loud as you go through. "
                       "Said out loud they become decisions; kept in your head "
                       "they stay feelings.",
        "d.repeat.s2": "Five laps with one rule: don't chase the time, chase two "
                       "laps that look the same.",
        "d.repeat.s3": "Right now your minimum speed here — the lowest you touch "
                       "— swings {s} km/h from lap to lap. Under {r} km/h the "
                       "corner is yours: going lower means chasing differences "
                       "that aren't down to you.",
        "d.repeat.s4": "Only once you can repeat it, move one of the three "
                       "points. One.",
        "d.consistency.title": "The lap you've already driven, all at once",
        "d.consistency.watch": "the three sectors, not the lap time",
        "d.consistency.ignore": "the lap time — it's the one thing here that fixes "
                                "itself",
        "d.consistency.s0": "It isn't an invented time: it's your best time in "
                            "each sector, put together. It comes to {ideal}, and "
                            "you've driven all of it — just never on the same lap.",
        "d.consistency.s1": "You're {gap}s off putting it together, and {ws}s of "
                            "that sits in sector {n}: that's where you work.",
        "d.consistency.s1b": "You're {gap}s off putting it together, and it's "
                             "spread out: no single sector holds it.",
        "d.consistency.s2": "Five laps where you don't chase the time, you chase "
                            "the repeat. Same line, same points, same order.",
        "d.consistency.s3": "Rule for these laps: if you get a corner wrong, still "
                            "finish the lap without another mistake. What really "
                            "costs you is the rest of the lap after the mistake — "
                            "and it's the only part you can still save.",
        "d.consistency.s3b": "Don't watch whether the lap time drops lap after "
                             "lap: with fuel burning off and tyres wearing it "
                             "moves anyway. Watch whether two consecutive laps "
                             "look alike.",
        "d.consistency.s4": "Watch «Sectors»: the goal is for sector {n} to stop "
                            "being your worst, not for the lap time to drop. The "
                            "time drops afterwards.",
        "d.consistency.s4b": "Watch «Sectors»: the goal is for your three sectors "
                             "to come from the same lap, not for the lap time to "
                             "drop. The time drops afterwards.",
        "d.brake_straight.title": "Brake in a straight line, then turn",
        "d.brake_straight.watch": "the Throttle / Brake chart (Compare tab): the "
                                  "brake should be finished before the steering "
                                  "moves",
        "d.brake_straight.ignore": "your minimum speed: it comes up on its own "
                                   "here if the entry is clean",
        "d.brake_straight.s0": "On a car with no downforce you slow in a straight "
                               "line and then turn. A sliver of brake while you "
                               "steer unloads the rear just as you're asking it "
                               "to hold.",
        "d.brake_straight.s1": "Two laps with all the braking done first, hard and "
                               "short, finished before you turn the wheel. The car "
                               "will go in slow and flat: that's fine, it's the "
                               "starting point.",
        "d.brake_straight.s2": "Select the corner's gear before you turn: a "
                               "downshift taken inside the corner brakes the rear "
                               "wheels on its own, and to the car that's the same "
                               "thing as a sudden lift.",
        "d.brake_straight.s3": "Now move the end of the braking a metre at a time "
                               "towards the corner, without ever getting to the "
                               "point where you steer with the brake still hard on.",
        "d.brake_straight.s4": "If you feel the rear go light as you turn, you've "
                               "gone past it: go back to the previous point. On "
                               "this car the margin is shorter than it looks.",
    },
}


# --- the glossary -----------------------------------------------------------
# The words the driver will hear other people use. Three rules decide whether
# this is useful or just a block everyone scrolls past, and all three are about
# behaviour rather than wording:
#
# * **it is never the only place a word is explained.** Every term here is still
#   glossed where it is used, inside the drill. The glossary is the *second*
#   explanation — which is exactly why skipping it costs nothing, and why the
#   driver who does open it opens it on purpose;
# * **it shows only the words the open exercise actually uses.** One drill is
#   expanded at a time, so a glossary defining trail braking next to the exit
#   drill is ballast. In practice that leaves four to six entries, and the list
#   never goes stale;
# * **the order is the page's, not the alphabet's.** An entry that needs another
#   term must sit below it. An alphabetical glossary is a reference book, and
#   reference books get skipped.
#
# One sentence each, second person, no numbers, no cross-references to other
# tabs — the tab that sends you somewhere is the drill, not the definition.

MAX_GLOSSARY = 8

#: Terms every reader of this tab meets before reaching a drill: they are in the
#: gap band at the top and in the gate.
_ALWAYS_TERMS = ("valid_lap", "sector", "ideal")

#: Which terms each drill puts in front of the driver.
_DRILL_TERMS = {
    "brake_move_later": ("brake_point", "apex", "min_speed", "lockup"),
    "brake_release": ("brake_point", "apex", "trail_braking"),
    "brake_straight": ("brake_point", "apex", "downforce"),
    "apex_speed": ("apex", "min_speed", "reference"),
    "exit_throttle": ("apex", "wheelspin"),
    "repeat": ("brake_point", "min_speed"),
    "consistency": (),
}

#: Page order, and therefore glossary order: a definition may only lean on a
#: term that appears above it.
_TERM_ORDER = ("valid_lap", "sector", "ideal", "brake_point", "apex",
               "min_speed", "reference", "lockup", "wheelspin", "downforce",
               "trail_braking")

_GLOSSARY = {
    "it": {
        "valid_lap": ("Giro valido",
                      "Un giro che il gioco conta buono: non hai tagliato, non "
                      "sei finito troppo fuori, non sei passato dai box."),
        "sector": ("Settore",
                   "Uno dei tre tratti in cui ogni pista è divisa: il cronometro "
                   "prende un tempo alla fine di ognuno."),
        "ideal": ("Ideale teorico",
                  "Il giro che verrebbe fuori mettendo insieme il tuo tempo "
                  "migliore in ogni settore: l'hai già guidato a pezzi, mai "
                  "tutto di fila."),
        "brake_point": ("Punto di frenata",
                        "Il punto della pista in cui il tuo piede tocca il freno "
                        "arrivando in curva."),
        "apex": ("Apex",
                 "Il punto in cui passi più vicino al bordo interno della curva."),
        "min_speed": ("Velocità minima",
                      "La velocità più bassa che tocchi dentro una curva, cioè "
                      "quando hai finito di rallentare e non hai ancora ripreso."),
        "reference": ("Giro di riferimento",
                      "Il giro con cui HONE confronta il tuo: ogni differenza "
                      "che leggi è misurata contro quello."),
        "lockup": ("Bloccaggio",
                   "Quando il freno ferma una ruota mentre l'auto va ancora "
                   "avanti: la gomma striscia e girare il volante non serve più."),
        "wheelspin": ("Pattinamento",
                      "Quando il motore fa girare le ruote motrici più veloci di "
                      "quanto l'auto stia davvero avanzando."),
        "downforce": ("Carico aerodinamico",
                      "La spinta verso il basso che l'aria esercita sull'auto "
                      "quando va forte, e che la fa tenere di più."),
        "trail_braking": ("Trail braking",
                          "Restare un filo sul freno dopo aver già cominciato a "
                          "girare, invece di mollarlo tutto insieme."),
    },
    "en": {
        "valid_lap": ("Valid lap",
                      "A lap the game counts: you didn't cut, you didn't run too "
                      "far off, you didn't go through the pits."),
        "sector": ("Sector",
                   "One of the three stretches every track is split into; the "
                   "clock takes a time at the end of each."),
        "ideal": ("Theoretical ideal",
                  "The lap you'd get by putting together your best time in each "
                  "sector: you've driven it in pieces, never in one go."),
        "brake_point": ("Braking point",
                        "The point on the track where your foot touches the "
                        "brake coming into a corner."),
        "apex": ("Apex",
                 "The point where you pass closest to the inside edge of the "
                 "corner."),
        "min_speed": ("Minimum speed",
                      "The lowest speed you touch inside a corner — where you've "
                      "finished slowing and haven't picked up yet."),
        "reference": ("Reference lap",
                      "The lap HONE compares yours against: every difference you "
                      "read is measured against it."),
        "lockup": ("Lock-up",
                   "When the brake stops a wheel while the car is still moving: "
                   "the tyre scrubs and turning the wheel stops doing anything."),
        "wheelspin": ("Wheelspin",
                      "When the engine turns the driven wheels faster than the "
                      "car is actually travelling."),
        "downforce": ("Downforce",
                      "The downward push the air exerts on the car when it's "
                      "going fast, which makes it grip harder."),
        "trail_braking": ("Trail braking",
                          "Staying a sliver on the brake after you've already "
                          "started turning, instead of letting it all go at once."),
    },
}


def trail_brake_for(car_model: str | None) -> bool:
    """Whether this car is one the app coaches trail braking on at all.

    A thin wrapper on purpose: the answer lives in ``tuning.py``, which is the
    single place those per-class decisions are retuned, and the caller shouldn't
    have to know that a drill and a live cue are asking the same question.
    """
    return tuning_for_car(car_model).trail_brake_cue


def glossary_for(drill_key_: str, lang: str = "it") -> list[GlossaryEntry]:
    """The words on screen right now, in the order the page uses them.

    Built from the *open* drill, not from the whole programme: the tab expands
    one exercise at a time, and a definition for a word that isn't on the page
    is the thing that makes a glossary skippable.
    """
    table = _GLOSSARY.get(lang, _GLOSSARY["en"])
    wanted = set(_ALWAYS_TERMS) | set(_DRILL_TERMS.get(drill_key_, ()))
    out = [GlossaryEntry(term=table[k][0], definition=table[k][1])
           for k in _TERM_ORDER if k in wanted and k in table]
    return out[:MAX_GLOSSARY]


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


#: Sotto questa finestra di gas-e-freno chiusi, prima della staccata, non c'è
#: veleggio da recuperare: è il passaggio di consegne fra i due pedali.
_COAST_BLOCKS_S = 0.2


def brake_later_is_blocked(grip) -> bool:
    """Se «frena più tardi» sia l'esercizio sbagliato per questa curva.

    Tre condizioni insieme, e nessuna delle tre da sola basta — è il motivo per
    cui il debrief manda tre numeri invece di un booleano (vedi
    ``debrief.GripState``):

    1. il picco di questa curva è al livello dell'inviluppo del riferimento;
    2. **e** lo è già dove il freno morde, non solo nei metri di rotazione. Un
       p95 su tutta la curva è dominato dalla parte laterale: un pilota può
       stare al soffitto lì e all'80% nei primi metri della staccata, e in quel
       caso una frenata più tarda c'è eccome;
    3. **e** non c'è veleggio prima del freno. Se il pilota alza il gas e
       aspetta, la gomma è satura *quando la usa* ma non la usa abbastanza
       presto: lì «frena più tardi» è proprio il consiglio giusto.

    Non implementata la quarta guardia suggerita in revisione — «il punto di
    stacco non è già più tardi di quello del riferimento» — perché la scheda
    curva porta la distanza di frenata del pilota e non quella del riferimento,
    e inventarla qui significherebbe ricavare un fatto in un secondo posto.
    """
    return bool(grip and grip.at_limit and grip.saturated_early
                and grip.coast_s < _COAST_BLOCKS_S)


def drill_key(category: str, phase: str, *, trail_brake: bool = True,
              brake_later_blocked: bool = False) -> str:
    """Which exercise this corner gets.

    Phase first, category second, and that order is the point: *where in the
    corner* the clock ran is a measurement, while the category is a label put on
    the dominant symptom. A corner tagged "carry more entry speed" whose time
    actually goes on exit needs the exit drill — practising entry speed there
    would be training the label instead of the problem.

    ``trail_brake`` is ``ClassTuning.trail_brake_cue`` for the car being driven,
    and it is the one place where this module is not class-blind. It has to be:
    the live coach is *already* silent about trail braking on low-downforce road
    cars, and not on a hunch — the road audit (M3 E92 at Suzuka) fired six
    trail-brake cues, the driver called all six false, and none true. Teaching a
    twenty-lap drill on the technique the coach deliberately refuses to mention
    would be the two halves of this app giving opposite advice to the same
    driver. Those corners get "brake straight, then turn" instead, which is what
    the tuning table says is correct for them.
    """
    if phase == "entry":
        if category in (_C.LESS_BRAKE.value, _C.BRAKE_EARLIER.value):
            return "brake_release" if trail_brake else "brake_straight"
        # Con la gomma già impegnata, «frena più tardi» è l'unico dei tre
        # esercizi d'ingresso che chiede **più aderenza totale**: gli altri due
        # chiedono la stessa aderenza spesa meglio, che è l'unica leva che resta
        # a saturazione. Chi trail-braina lavora sulla forma del rilascio, chi
        # non lo fa sposta dove finisce la frenata — stessa fisica, due gesti.
        if brake_later_blocked:
            return "brake_release" if trail_brake else "brake_straight"
        return "brake_move_later"
    if phase == "apex":
        return "apex_speed"
    if phase in ("exit", "after"):
        return "exit_throttle"
    for cat, key in _BY_CATEGORY.items():
        if cat.value == category:
            return ("brake_straight" if key == "brake_release" and not trail_brake
                    else key)
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
    # Why the point can move at all, and where a lock-up actually happens. The
    # panel's finding: without this the driver moves the point while keeping the
    # same pedal shape, arrives long and slow, and concludes it doesn't work.
    steps.append(s["d.brake_move_later.s2b"])
    steps.append(s["d.brake_move_later.s3"])
    if f.min_speed_kmh > 0:
        steps.append(s["d.brake_move_later.s4"].format(v=f"{f.min_speed_kmh:.0f}"))
    return Drill(key="brake_move_later", title=s["d.brake_move_later.title"],
                 laps=8, steps=steps, watch=s["d.brake_move_later.watch"],
                 ignore=s["d.brake_move_later.ignore"])


def _brake_release(f: CornerFacts, s: dict) -> Drill:
    # `s2b` is the abort: overdoing the second half of this drill doesn't just
    # make the car stop too much, it can step the rear out. A drill that asks a
    # driver to find an edge has to say what to do when they find it.
    steps = [s["d.brake_release.s0"], s["d.brake_release.s1"],
             s["d.brake_release.s2"], s["d.brake_release.s2b"],
             s["d.brake_release.s3"]]
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
    # `s1b` is the abort. The drill deliberately asks the driver to arrive too
    # fast at least once, and the reflex it provokes — snapping off the throttle
    # mid-corner — is the classic way to spin a road car. Asking for the edge
    # without saying how to survive it is not an exercise, it's a dare.
    steps += [s["d.apex_speed.s1"], s["d.apex_speed.s1b"], s["d.apex_speed.s2"],
              s["d.apex_speed.s3"], s["d.apex_speed.s3b"], s["d.apex_speed.s4"]]
    return Drill(key="apex_speed", title=s["d.apex_speed.title"], laps=6,
                 steps=steps, watch=s["d.apex_speed.watch"],
                 ignore=s["d.apex_speed.ignore"])


def _exit_throttle(_f: CornerFacts, s: dict) -> Drill:
    return Drill(key="exit_throttle", title=s["d.exit_throttle.title"], laps=6,
                 steps=[s["d.exit_throttle.s0"], s["d.exit_throttle.s1"],
                        s["d.exit_throttle.s1b"], s["d.exit_throttle.s2"],
                        s["d.exit_throttle.s3"], s["d.exit_throttle.s4"]],
                 watch=s["d.exit_throttle.watch"],
                 ignore=s["d.exit_throttle.ignore"])


def _brake_straight(_f: CornerFacts, s: dict) -> Drill:
    """The entry drill for cars the tuning table says not to trail-brake.

    Same shape as `brake_release` — find the edge, then live just inside it —
    but it walks the *end* of the braking towards the corner instead of walking
    the brake into it. See `drill_key` for why the class matters here and
    nowhere else.
    """
    return Drill(key="brake_straight", title=s["d.brake_straight.title"], laps=6,
                 steps=[s["d.brake_straight.s0"], s["d.brake_straight.s1"],
                        s["d.brake_straight.s2"], s["d.brake_straight.s3"],
                        s["d.brake_straight.s4"]],
                 watch=s["d.brake_straight.watch"],
                 ignore=s["d.brake_straight.ignore"])


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
    # `s3b`: ten laps in a row burn fuel and wear tyres, and the sector times
    # this drill watches move with both. Without the warning the driver reads
    # the car getting lighter as themselves getting better.
    steps += [s["d.consistency.s2"], s["d.consistency.s3"],
              s["d.consistency.s3b"]]
    steps.append(s["d.consistency.s4"].format(n=gap.worst_sector)
                 if gap.worst_sector else s["d.consistency.s4b"])
    return Drill(key="consistency", title=s["d.consistency.title"], laps=10,
                 steps=steps, watch=s["d.consistency.watch"],
                 ignore=s["d.consistency.ignore"])


_BUILDERS = {
    "brake_move_later": _brake_move_later,
    "brake_release": _brake_release,
    "brake_straight": _brake_straight,
    "apex_speed": _apex_speed,
    "exit_throttle": _exit_throttle,
    "repeat": _repeat,
}


def build_drill(category: str, phase: str, facts: CornerFacts,
                lang: str = "it", *, trail_brake: bool = True) -> Drill:
    """The exercise for one corner, filled with that corner's own numbers."""
    key = drill_key(category, phase, trail_brake=trail_brake,
                    brake_later_blocked=brake_later_is_blocked(facts.grip))
    return _BUILDERS[key](facts, _s(lang))


# --- the programme ----------------------------------------------------------

def build_programme(plan: TrainingPlan, progress: list[GoalProgress],
                    debriefs: list[LapDebrief], gap: Gap | None,
                    facts: dict[int, CornerFacts] | None = None,
                    *, valid_laps: int = 0, lang: str = "it",
                    inherited_sources: set[int] | None = None,
                    trail_brake: bool = True) -> Programme:
    """The whole section: the gate, the gap, the ordered steps, the next session.

    ``plan`` decides *what* — this function only decides the order, the drill and
    the words. ``inherited_sources`` are corners the chain analysis blamed for a
    *later* corner's loss; they are promoted to the front, because fixing the
    corner that hands over the deficit fixes two, and doing it the other way
    round fixes neither. ``trail_brake`` is the car class's own setting from
    ``tuning.py``, and the only thing here that isn't class-blind — see
    :func:`drill_key`.
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
        # "Time lost here" is the debrief's label for a corner with no dominant
        # cause. On the other tabs it earns its place at the head of a list; on
        # a card that already carries the corner's name, the reason it is first
        # and a target in seconds, it is a heading that says nothing — and the
        # drill's own opening line says the same thing properly ("no dominant
        # cause here: you lose a little everywhere"). Every other category
        # ("Brake later", "More throttle on exit") is worth the line.
        generic = g.category == _C.TIME_LOSS.value
        step = Step(
            order=0, kind="corner", corner_index=g.corner_index,
            where=g.name, what="" if generic else g.what, why="",
            target=s["target"].format(to=_sec(g.target_ms),
                                      from_=_sec(g.baseline_ms)),
            done_when=(s["done_when"].format(needed=p.needed)
                       if p and p.needed else s["done_when_plain"]),
            status="done" if (p and p.done) else "later",
            drill=build_drill(g.category, phase, f, lang,
                              trail_brake=trail_brake),
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

    # The glossary follows the *open* drill, so it holds only words that are on
    # screen right now.
    open_drill = first_open.drill.key if (first_open and first_open.drill) else ""
    return Programme(readiness=readiness, gap=gap, steps=steps,
                     session=_session(first_open, plan, s),
                     glossary=glossary_for(open_drill, lang))


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
    # `ses_fuel` only where it can bite: a ten-lap repetition drill is long
    # enough for fuel burn and tyre wear to move the very times it asks you to
    # compare, and the driver reads the car getting lighter as themselves
    # getting better.
    lines = [s["ses_warm"], where]
    if step.drill.laps >= 10:
        lines.append(s["ses_fuel"])
    lines.append(s["ses_free"])
    lines.append(s["ses_back_plan"].format(when=plan.created_utc[:10])
                 if plan.created_utc else s["ses_back"])
    return Session(laps=warm + step.drill.laps + free, lines=lines)
