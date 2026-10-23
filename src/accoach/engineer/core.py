"""The class-agnostic race-engineer state machine.

Drives one evaluation per completed lap. The contract is turn-based and
side-effect free, which makes it deterministic and easy to test:

    eng = RaceEngineer(GT3_PROFILE)
    decision = eng.observe(lap_stats)        # feed a lap, get the next move
    if decision.kind is DecisionKind.PROPOSE:
        # show decision.change to the driver; when they WRITE that setup:
        eng.mark_applied()                   # start the re-test window

The engine proposes a change, the driver applies it (via the setup editor /
file), then drives a few laps; the engine measures the effect and decides to
**keep** it (continue) or **revert** it (try the next remedy). It works through
ordered phases (pressures → aero → mechanical → … per the profile), advancing
only when a phase's gate is satisfied.

Safety guards (it moves real setup, so a false positive is costly):

* a symptom drives a change only when it is **both** spread across ≥3 distinct
  corners (setup, not a one-corner driving error) **and** persistent across the
  recent stable laps;
* on a *plateau* (a symptom change that neither helps nor hurts) the change is
  **reverted**, not kept, so the setup can't drift under a blind meter;
* a per-parameter **click budget** caps how far any one lever is pushed in a
  session.

It consumes :class:`LapStats` (the diagnosis) and never touches telemetry.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from enum import Enum

from ..i18n import current_language
from ..textfmt import fmt_num
from .steps import AccSteps, Steps


# --- diagnosis vocabulary (the discilli taxonomy) --------------------------

class Balance(Enum):
    UNDERSTEER = "understeer"
    OVERSTEER = "oversteer"


class Phase(Enum):
    ENTRY = "entry"
    APEX = "apex"
    EXIT = "exit"


class Speed(Enum):
    LOW = "low"
    HIGH = "high"


@dataclass(frozen=True)
class Symptom:
    """One handling problem: balance × corner-phase × speed band."""

    balance: Balance
    phase: Phase
    speed: Speed

    def __str__(self) -> str:
        return f"{self.balance.value} {self.phase.value} {self.speed.value}"


# Wheel-indexed setup arrays are FL, FR, RL, RR.
FRONT = (0, 1)
REAR = (2, 3)
ALL = (0, 1, 2, 3)


@dataclass
class LapStats:
    """The diagnosis for a single completed lap (produced by the coaching layer).

    ``symptom_scores`` maps a :class:`Symptom` to an intensity in roughly 0..1
    (0 == absent). ``symptom_corners`` maps a :class:`Symptom` to the number of
    **distinct corners** that showed it this lap — the engine only acts on a
    symptom seen in several corners (setup), not one (driving). ``pressures_hot``
    is per-axle hot pressure in psi (``{"front": .., "rear": ..}``) when known.
    ``stable`` flags a clean lap (no off/pit, lap time within the recent band) —
    only stable laps count.
    """

    lap_time_ms: int
    stable: bool = True
    warmed_up: bool = True
    symptom_scores: dict = field(default_factory=dict)
    symptom_corners: dict = field(default_factory=dict)
    # Symptom -> list of corner indices where it showed (so a proposal can be
    # anchored to "Corners 7, 9" instead of a faceless symptom).
    symptom_corner_idx: dict = field(default_factory=dict)
    pressures_hot: dict | None = None
    lock_segments: int = 0
    spin_segments: int = 0
    #: Mean litres in the tank across the lap (v11 laps; 0.0 = not recorded).
    #: How heavy the car was, which is why a lap time from before a setup change
    #: and one from after may not be comparable at all — see `_fuel_gap`.
    fuel_l: float = 0.0
    #: Quando ``stable`` e' False, quale delle due meta' e' caduta: ``"invalid"``
    #: (il gioco non ha completato il giro) o ``"cut"`` (fuori pista). Vuoto su
    #: un giro che sta in piedi. Non duplica ``stable`` — lo spiega: il pilota in
    #: macchina ha bisogno di sapere QUALE dei due, perche' i due si correggono
    #: in modi opposti.
    unstable_why: str = ""
    #: Dove il giro ha smesso di contare, gia' in parole («Variante Ascari»).
    #: Vuoto quando non si sa, e non si prova a indovinare.
    lost_where: str = ""
    #: Su un giro tagliato: il sintomo che l'auto mostrava nella curva in cui
    #: e' uscita, prima del punto in cui il gioco l'ha annullato, e quella
    #: curva. ``None`` quando l'auto era in equilibrio — un taglio, che
    #: l'assetto non spiega. E' un indizio sul COME, mai un tempo: il giro resta
    #: fuori dalla finestra (vedi `RaceEngineer._off_tail`).
    off_symptom: "Symptom | None" = None
    off_corner: int | None = None
    #: Whether this lap was driven on wet tyres. ``None`` means the lap doesn't
    #: say — which is not the same as "dry", and is treated differently.
    #:
    #: It comes from the compound the driver fitted, not from a grip reading:
    #: ``surface_grip`` is **0.0 on all 39 laps in our archive**, on both games,
    #: so it is not a signal at all. The compound is the driver's own decision
    #: about the conditions, and it is measured.
    wet: bool | None = None


# --- recommendations -------------------------------------------------------

@dataclass(frozen=True)
class AtomicChange:
    param: str          # a SETUP_PARAMS key, e.g. "aRBFront", "tyrePressure"
    slot: int | None    # wheel/axle index, or None for a scalar
    delta_clicks: int
    #: Di quanto si muove il numero NEL FILE per un click. 1 su ACC, dove il
    #: file e' fatto di click; su Assetto Corsa lo dichiara l'auto (una barra
    #: con ``STEP=200`` salvata in N/m: 200). Lo mette il motore quando propone
    #: (`RaceEngineer._sized`), non chi scrive la tabella dei rimedi: e' una
    #: proprieta' dell'auto, e la tabella vale per una classe intera.
    units: int = 1


@dataclass(frozen=True)
class ProposedChange:
    """A concrete, ready-to-apply setup change with its rationale."""

    changes: tuple[AtomicChange, ...]
    rationale: str
    phase_label: str
    tag: str            # "AV" (al volo) or "BOX" (garage)
    symptom: Symptom | None = None
    #: La sola azione, senza il sintomo che la motiva («Ammorbidisci la barra
    #: antirollio anteriore di 1 click»): e' quella che si cita fra virgolette
    #: quando la modifica si nomina dentro un'altra frase (il ripristino, il
    #: sospetto sulle uscite, la modifica che non sappiamo scrivere). Vuota
    #: quando chi costruisce la modifica non la separa: si cita `rationale`.
    lever: str = ""

    @property
    def param(self) -> str:
        return self.changes[0].param if self.changes else ""

    @property
    def named(self) -> str:
        """La modifica come si cita dentro un'altra frase, senza il punto finale."""
        return (self.lever or self.rationale).rstrip(". ")

    def reversed(self) -> "ProposedChange":
        """The change that undoes this one (used to revert a rejected remedy).

        La frase nomina fra virgolette la modifica provata invece di ripeterla:
        ripetuta, «Ammorbidisci la barra» sotto un ripristino direbbe al pilota
        il contrario di quello che fanno i click preparati."""
        lang = current_language()
        undo = _REVERT_TEXT.get(lang) or _REVERT_TEXT["en"]
        return ProposedChange(
            changes=tuple(AtomicChange(c.param, c.slot, -c.delta_clicks, c.units)
                          for c in self.changes),
            rationale=undo.format(what=self.named),
            phase_label=self.phase_label, tag=self.tag, symptom=self.symptom,
            lever=self.lever)

    def as_setup_payload(self) -> list[dict]:
        """Shape accepted by ``/api/setup/preview|apply``.

        Qui ``delta_clicks`` e' il nome che la rotta da' a «di quanto cambia il
        numero nel file», ed e' quello che esce: i click per il loro passo. Su
        ACC le due cose coincidono. Tutto il resto del motore — il budget, il
        registro, la frase detta al pilota — resta in click veri.
        """
        return [{"param": c.param, "slot": c.slot,
                 "delta_clicks": c.delta_clicks * c.units}
                for c in self.changes]


@dataclass(frozen=True)
class Prediction:
    """What this change is expected to do, said *before* the laps are driven.

    Be clear about what this is and isn't. The bar below is the engine's own
    acceptance rule — the symptom has to drop by at least ``_EPS_SCORE`` and the
    lap time must not fall outside the noise band — so a prediction that "hits"
    is, by construction, a change that was kept. It is **not** a second,
    independent test, and this docstring exists so nobody later reads it as one.

    Its value is the order in which the driver learns things. Until now the loop
    said "try this", took the car away for three laps and came back with a
    verdict; the driver had no way to disagree, because they never knew what was
    being measured. Stating the bar first turns that into something checkable
    from the cockpit: you are told the number to beat, and afterwards you are
    told whether you beat it.

    Where a *real* prediction can eventually come from is the ledger
    (``ledger.py``): what a lever does to the symptoms nobody was aiming at is
    measured there and asserted nowhere, until there is enough of it to mean
    something.
    """

    symptom: Symptom | None
    score_now: float          # the symptom's typical score before the change
    score_below: float        # the bar it has to get under for this to count
    time_band_ms: float       # how much lap time it may cost and still count
    text: str = ""            # the sentence the driver reads before driving


@dataclass(frozen=True)
class Outcome:
    """What actually happened, next to what was said would happen."""

    prediction: Prediction
    score_after: float
    time_before_ms: float
    time_after_ms: float
    laps: int
    kept: bool
    remedy_rank: int = 0
    fuel_before_l: float = 0.0
    fuel_after_l: float = 0.0
    #: True when the two windows were driven at fuel loads too far apart for
    #: their lap times to be compared. The verdict then rests on the symptom
    #: score, which doesn't care what the car weighs — and says so.
    time_confounded: bool = False
    #: {Symptom: score change} for symptoms this change was *not* aiming at, and
    #: which the verdict therefore never looked at. Measured, never predicted.
    side_effects: tuple = ()


class DecisionKind(Enum):
    COLLECT = "collect"          # not enough stable laps yet — keep driving
    EVALUATING = "evaluating"    # a change is applied; gathering re-test laps
    PROPOSE = "propose"          # apply this change next
    ACCEPTED = "accepted"        # the last change helped — kept
    REVERTED = "reverted"        # the last change didn't help — undo proposed
    PHASE_DONE = "phase_done"    # this phase's gate is satisfied
    DONE = "done"                # nothing left to improve
    STAND_DOWN = "stand_down"    # it *could* advise here, and refuses to


@dataclass(frozen=True)
class Decision:
    kind: DecisionKind
    message: str
    change: ProposedChange | None = None
    confidence: str = ""         # "high" / "medium" on a PROPOSE, else ""
    #: On a PROPOSE: the bar this change will be judged against, so the driver
    #: reads it before driving instead of after.
    prediction: Prediction | None = None
    #: On an ACCEPTED / REVERTED: what happened, with the numbers on both sides.
    #: This is what `ledger.py` writes down.
    outcome: Outcome | None = None
    #: Su un COLLECT o un EVALUATING col contatore: la parte del messaggio che
    #: il contatore non dice (perche' l'ultimo giro non conta, il sospetto
    #: sulle uscite), "" se non c'e'. La strada della pagina i giri li conta
    #: gia' (`progress`): senza questa coda separata la pagina ripeteva lo
    #: stesso numero due volte con due frasi diverse, o perdeva il perche'.
    #: None su tutto il resto: il messaggio va letto intero.
    tail: str | None = None


# --- the profile contract --------------------------------------------------

class WorkPhase:
    """A phase of setup work: which symptoms it owns and when it's complete.

    A plain class (not a dataclass) so profile-specific phases can subclass it
    and carry extra state (e.g. a pressure window) without dataclass ceremony.
    """

    def __init__(self, key: str, label: str, tag: str) -> None:
        self.key = key
        self.label = label
        self.tag = tag                    # default tag for this phase's advice

    def owns(self, symptom: Symptom) -> bool:    # pragma: no cover - overridden
        raise NotImplementedError

    def gate(self, window: list[LapStats]) -> bool:  # pragma: no cover
        raise NotImplementedError

    def reconfigure(self, **kw) -> "WorkPhase":
        """Return a variant tuned by ``kw`` (default: unchanged)."""
        return self

    def blind(self) -> str:
        """Perche' questa fase su quest'auto non puo' giudicare niente, o "".

        Una fase cieca non e' una fase completata: il motore la salta, ma lo
        dice con le sue parole invece di scrivere «completata».
        """
        return ""


#: «Quest'auto non ha una finestra pressioni che conosciamo», detto al motore.
#: Non e' ``None``: ``None`` vuol dire «tieni quella del profilo», ed e' cosi'
#: che un'auto mai classificata si ritrovava la finestra di una stradale.
NO_WINDOW: tuple = (None, None)


@dataclass
class Profile:
    name: str
    phases: list[WorkPhase]
    # symptom -> ordered remedies; each remedy is a callable(symptom)->ProposedChange
    remedy_table: dict
    # knobs the driver can change at the wheel (shown by the class-specific UI)
    al_volo: list[str] = field(default_factory=list)


# --- tuning constants ------------------------------------------------------

_MIN_STABLE = 3                  # laps needed for a baseline / a re-test verdict
_WINDOW = 6                      # rolling stable-lap buffer
_SYMPTOM_THRESH = 0.30           # a symptom counts as "present" above this
_MIN_CORNERS = 3                 # a symptom must span ≥ this many corners to be setup
_EPS_SCORE = 0.10                # min symptom-score drop to call it an improvement
_TIME_BAND_FRAC = 0.0015         # lap-time noise band (0.15%)
_REMEDY_CAP = 5                  # max remedies tried per symptom before giving up
_CLICK_BUDGET = 6                # max net clicks a single parameter may accumulate

#: Litres of difference between the before and after windows past which their
#: lap times are not comparable. Two litres is about one lap's worth of fuel for
#: a GT3: at that point the two windows were driven with a different car, not a
#: different setup.
#:
#: What this deliberately does **not** do is convert litres into seconds. That
#: needs a per-car, per-track weight sensitivity we have never measured, and a
#: made-up coefficient here would quietly become the thing that decides whether
#: a setup change is kept. So the rule is the one this project keeps reaching
#: for: when the evidence isn't comparable, say so and lean on the evidence that
#: is — the symptom score, which doesn't care what the car weighs.
_FUEL_BIAS_L = 2.0


# Decision messages, per language; resolved with the active app language at the
# moment a Decision is built (the engine runs in the engine = config.language).
# Il sintomo ({sym}) arriva gia' in parole (`_symptom_words`) e i numeri gia'
# scritti per la lingua (`textfmt.fmt_num`): nessun modello qui sotto ha una
# specifica di formato, perche' `{a:.2f}` stampa «0.63» anche su una pagina
# italiana. La fase arriva tradotta (profiles/_common.tr).
_DECISION_MSG = {
    "collect": {
        "en": "I need {n} clean laps for a baseline, and I have {have} so far.",
        "it": "Servono {n} giri puliti per avere una base e per ora ne ho {have}.",
    },
    "done": {
        "en": "The setup is sorted, I can't find anything else to gain. It's a "
              "good baseline.",
        "it": "Il setup è a posto, non trovo altro da guadagnare. È una buona "
              "base.",
    },
    "phase_done": {
        "en": "The “{label}” phase is done.{tail}",
        "it": "La fase «{label}» è completata.{tail}",
    },
    "phase_tail_next": {
        "en": " Moving on to “{nxt}”.",
        "it": " Passo a «{nxt}».",
    },
    "phase_tail_complete": {
        "en": " The setup is complete.",
        "it": " Il setup è completo.",
    },
    "phase_nothing": {
        "en": "I found nothing to correct in the “{label}” phase.",
        "it": "Nella fase «{label}» non ho trovato nulla da correggere.",
    },
    "remedies_exhausted": {
        "en": "I've run out of setup remedies for the {sym}. It's probably a "
              "driving issue.",
        "it": "Per il {sym} ho finito i rimedi di setup. Probabilmente è una "
              "questione di guida.",
    },
    "evaluating": {
        "en": "I'm still testing the change. {laps}",
        "it": "Sto valutando la modifica. {laps}",
    },
    # Quanti giri mancano, con la frase intera: «serve 1 giro», «servono 2 giri».
    "laps_one": {
        "en": "I need 1 more clean lap.",
        "it": "Serve ancora 1 giro pulito.",
    },
    "laps_many": {
        "en": "I need {n} more clean laps.",
        "it": "Servono ancora {n} giri puliti.",
    },
    # Perche' l'ultimo giro non e' entrato nel conto. Senza questa coda un
    # contatore fermo e un motore rotto si leggono allo stesso modo — e in
    # macchina la domanda che nasce e' «sta funzionando?», non «cosa sbaglio?».
    "skip_cut_where": {
        "en": " That last lap didn't count because you went off at {where}.",
        "it": " L'ultimo giro non conta perché sei uscito di pista in {where}.",
    },
    "skip_cut": {
        "en": " That last lap didn't count because you went off track.",
        "it": " L'ultimo giro non conta perché sei uscito di pista.",
    },
    "skip_invalid": {
        "en": " That last lap didn't count because the game never completed it.",
        "it": " L'ultimo giro non conta perché il gioco non l'ha completato.",
    },
    # Una modifica scritta sulla macchina e mai giudicata, perche' la sessione e'
    # finita in mezzo. Detta una volta sola, all'inizio della sessione dopo.
    "unjudged": {
        "en": "Last time's change, “{why}”, was left without a verdict. It's on "
              "the car, so it's the new starting point and I'm measuring from here.",
        "it": "La modifica dell'altra volta, «{why}», è rimasta senza verdetto. È "
              "sulla macchina, quindi è il nuovo punto di partenza e misuro da qui.",
    },
    # Le uscite che si ripetono con lo stesso schema: un sospetto sull'assetto,
    # detto in coda al contatore. Mai una modifica scritta — vedi `_off_tail`.
    "off_pattern": {
        "en": " But {k} of {n} offs share one pattern, {what}, in {c} different "
              "corners{where}. That could be the setup, not your driving.",
        "it": " Però {k} uscite su {n} hanno lo stesso schema, {what}, in {c} "
              "curve diverse{where}. Può essere l'assetto e non la guida.",
    },
    # …e la leva che il motore proverebbe, quando ne ha ancora una.
    "off_lever": {
        "en": " The first thing I'd try is “{lever}”. I'm not writing it, because "
              "an off lap can't judge a setup change. I can only measure it on "
              "clean laps.",
        "it": " Per prima cosa proverei «{lever}». Non lo scrivo, perché un giro "
              "fuori pista non può giudicare una modifica. Lo misuro solo sui "
              "giri puliti.",
    },
    "skip_cold": {
        "en": " That last lap didn't count because the tyres were still cold.",
        "it": " L'ultimo giro non conta perché le gomme erano ancora fredde.",
    },
    "accepted_structural": {
        "en": "I'm keeping the change and moving on.",
        "it": "Tengo la modifica e vado avanti.",
    },
    "revert_structural": {
        "en": "The change made the lap time worse, so it comes off.",
        "it": "La modifica ha peggiorato il tempo sul giro, quindi va tolta.",
    },
    "accepted_resolved": {
        "en": "The {sym} is fixed. It was {a}, now it's {b}.",
        "it": "Il {sym} è risolto. Era {a}, ora è {b}.",
    },
    "accepted_improving": {
        "en": "The {sym} is improving, from {a} to {b}. I'm keeping the change "
              "and carrying on.",
        "it": "Il {sym} migliora, da {a} a {b}. Tengo la modifica e continuo.",
    },
    "revert_reason": {
        "en": "{reason}. It comes off, then I'll try another lever for the {sym}.",
        "it": "{reason}. Va tolta, poi provo un'altra leva per il {sym}.",
    },
    "reason_worse": {
        "en": "The change made things worse",
        "it": "La modifica ha peggiorato le cose",
    },
    "predict": {
        "en": "To keep this change, the {sym} has to drop from {a} to under {b} "
              "over {n} clean laps. The lap time must not get worse by more than "
              "{ms} ms. If not, it comes off.",
        "it": "Per tenere la modifica, in {n} giri puliti il {sym} deve scendere "
              "da {a} a meno di {b}. Il tempo sul giro non deve peggiorare più di "
              "{ms} ms. Se non succede, va tolta.",
    },
    "predict_structural": {
        "en": "To keep this change, the lap time must not get worse by more than "
              "{ms} ms over {n} clean laps. If it does, it comes off.",
        "it": "Per tenere la modifica, in {n} giri puliti il tempo non deve "
              "peggiorare più di {ms} ms. Se peggiora, va tolta.",
    },
    "wet_stand_down": {
        "en": "You're on wet tyres, and I don't touch the setup in the wet. Every "
              "remedy I have was worked out in the dry, and in the rain several "
              "of them point the other way. Pressures aside, what I'd tell you "
              "would be a guess, not a measurement.",
        "it": "Hai le gomme da bagnato, e sul bagnato il setup non lo tocco. Ogni "
              "rimedio che ho è stato ricavato sull'asciutto, e con la pioggia "
              "più d'uno punta dalla parte opposta. Pressioni a parte, quello che "
              "ti direi sarebbe un'ipotesi, non una misura.",
    },
    "conditions_changed": {
        "en": "Conditions changed during the test, from dry to wet or the other "
              "way round. I'm dropping this verdict instead of reading it, "
              "because those laps can't be compared.",
        "it": "Le condizioni sono cambiate durante la prova, da asciutto a "
              "bagnato o viceversa. Butto via questo verdetto invece di leggerlo, "
              "perché quei giri non sono confrontabili.",
    },
    "accepted_unjudged": {
        "en": "I'm keeping the change, but I couldn't judge it on lap time. The "
              "tank wasn't the same weight before and after, so the phase target "
              "decides and I'm moving on.",
        "it": "Tengo la modifica, ma sul tempo non ho potuto giudicarla. Prima e "
              "dopo il serbatoio non pesava uguale, quindi decide l'obiettivo "
              "della fase e vado avanti.",
    },
    "fuel_confounded": {
        "en": " I left the lap time out of this, because the tank had {a} L "
              "before and {b} L after. That's not the same car.",
        "it": " Il tempo sul giro l'ho lasciato fuori, perché nel serbatoio "
              "c'erano {a} L prima e {b} L dopo. Non è la stessa macchina.",
    },
    "side_effect": {
        "en": " We weren't aiming at it, but the {items} moved too.",
        "it": " Non lo cercavamo, ma si è mosso anche il {items}.",
    },
    # Due o più: «si sono mossi anche il X e il Y».
    "side_effects": {
        "en": " We weren't aiming at them, but the {items} moved too.",
        "it": " Non li cercavamo, ma si sono mossi anche il {items}.",
    },
    "side_effect_and": {"en": " and the ", "it": " e il "},
    # Sa cosa proverebbe e non sa quanto vale un click di quella leva su
    # quest'auto. Lo dice, col nome della leva, e non lo scrive.
    "no_step": {
        "en": "For the {sym} I'd try “{what}”. I'm not writing it, because {why}. "
              "If you make that change by hand, I can't follow it.",
        "it": "Per il {sym} proverei «{what}». Non lo scrivo, perché {why}. Se "
              "lo fai tu a mano, io non riesco a seguirlo.",
    },
    "no_step_plain": {
        "en": "{what} I won't write it myself, because {why}.",
        "it": "{what} Non la scrivo, perché {why}.",
    },
    "reason_noeffect": {
        "en": "The change had no measurable effect",
        "it": "La modifica non ha avuto un effetto misurabile",
    },
}

# Il ripristino nomina la modifica provata fra virgolette (`ProposedChange.named`).
# Ne' «Annulla» (e' il bottone che chiude la finestra) ne' «Togli» (e' spesso la
# prima parola della modifica citata: «Togli la modifica… «Togli 1 click…»»).
_REVERT_TEXT = {"en": "Set the car back to before the change you tried, “{what}”.",
                "it": "Riporta l'assetto a prima della modifica che hai provato, «{what}»."}

# Un sintomo detto come lo direbbe un ingegnere al pilota, non come la stringa
# tecnica «oversteer exit low» che resta nei messaggi del ciclo di prova.
_BALANCE_WORDS = {
    Balance.UNDERSTEER: {"en": "understeer", "it": "sottosterzo"},
    Balance.OVERSTEER: {"en": "oversteer", "it": "sovrasterzo"},
}
# In inglese l'ordine e' fase + bilanciamento + velocita' («mid-corner understeer
# in slow corners»), in italiano bilanciamento + fase + velocita'; `{bal}` e'
# il sottosterzo o il sovrasterzo.
_PLACE_WORDS = {
    (Phase.ENTRY, Speed.LOW): {"en": "entry {bal} in slow corners",
                               "it": "{bal} in ingresso alle curve lente"},
    (Phase.ENTRY, Speed.HIGH): {"en": "entry {bal} in fast corners",
                                "it": "{bal} in ingresso alle curve veloci"},
    (Phase.APEX, Speed.LOW): {"en": "mid-corner {bal} in slow corners",
                              "it": "{bal} in percorrenza nelle curve lente"},
    (Phase.APEX, Speed.HIGH): {"en": "mid-corner {bal} in fast corners",
                               "it": "{bal} in percorrenza nelle curve veloci"},
    (Phase.EXIT, Speed.LOW): {"en": "exit {bal} in slow corners",
                              "it": "{bal} in uscita dalle curve lente"},
    (Phase.EXIT, Speed.HIGH): {"en": "exit {bal} in fast corners",
                               "it": "{bal} in uscita dalle curve veloci"},
}


def _symptom_words(sym: Symptom, lang: str) -> str:
    bal = _BALANCE_WORDS[sym.balance]
    place = _PLACE_WORDS[(sym.phase, sym.speed)]
    return (place.get(lang) or place["en"]).format(bal=bal.get(lang) or bal["en"])


# --- la memoria fra una sessione e l'altra ---------------------------------

def _sym_key(sym: Symptom) -> str:
    """Un sintomo come stringa stabile, che e' gia' come lo si legge a schermo."""
    return str(sym)


def _sym_from_key(key: str) -> Symptom | None:
    """Il contrario, o None se la stringa non e' un sintomo.

    Il file su disco lo scrive questa app e lo rilegge questa app, ma un file su
    disco sopravvive a un cambio di enum e a un editor di testo: quello che non
    si riconosce si butta, non si indovina.
    """
    parts = str(key).split()
    if len(parts) != 3:
        return None
    try:
        return Symptom(Balance(parts[0]), Phase(parts[1]), Speed(parts[2]))
    except ValueError:
        return None


def symptom_words(sym: "Symptom | str", lang: str | None = None) -> str:
    """Un sintomo in parole, per una pagina: l'oggetto o la sua chiave di registro
    («oversteer exit low»). Una chiave che non si riconosce torna com'e'."""
    lang = lang or current_language()
    found = sym if isinstance(sym, Symptom) else _sym_from_key(sym)
    return _symptom_words(found, lang) if found is not None else str(sym)


def _msg(key: str, lang: str | None = None, **kw) -> str:
    lang = lang or current_language()
    entry = _DECISION_MSG[key]
    return (entry.get(lang) or entry["en"]).format(**kw)


def _score(v: float, lang: str) -> str:
    """Un punteggio di sintomo (0..1) come lo legge il pilota: «0,63»."""
    return fmt_num(v, 2, lang)


def _signed(v: float, lang: str) -> str:
    """Una variazione col suo segno: «+0,36», «−0,12»."""
    text = fmt_num(v, 2, lang)
    return text if text.startswith("−") or text == fmt_num(0, 2, lang) else "+" + text


def _laps_left(n: int, lang: str) -> str:
    """«Serve ancora 1 giro pulito.» / «Servono ancora 2 giri puliti.»"""
    return _msg("laps_one", lang) if n == 1 else _msg("laps_many", lang, n=n)


def _skip_tail(stats: "LapStats | None", lang: str | None = None) -> str:
    """Perche' l'ultimo giro non e' entrato nel conto, o "" se e' entrato.

    Una riga sola, in coda al contatore, e nessuna se non c'e' niente da dire.
    Il taglio viene prima delle gomme fredde quando valgono entrambi: e' quello
    su cui il pilota puo' fare qualcosa nel giro che sta guidando.
    """
    if stats is None:
        return ""
    if stats.unstable_why == "invalid":
        return _msg("skip_invalid", lang)
    if stats.unstable_why == "cut":
        return (_msg("skip_cut_where", lang, where=stats.lost_where)
                if stats.lost_where else _msg("skip_cut", lang))
    if not stats.warmed_up:
        return _msg("skip_cold", lang)
    return ""


def _fuel_tail(outcome: "Outcome", lang: str) -> str:
    """Say when the lap-time half of the verdict couldn't be used.

    A driver who is told "the handling improved" while the clock says something
    else deserves to know why we ignored the clock.
    """
    if not outcome.time_confounded:
        return ""
    return _msg("fuel_confounded", lang,
                a=fmt_num(outcome.fuel_before_l, 0, lang),
                b=fmt_num(outcome.fuel_after_l, 0, lang))


def _side_effect_tail(outcome: "Outcome", lang: str) -> str:
    """Name what moved that nobody was aiming at — after the verdict, never before.

    The engine judged one symptom; this is the rest of the car answering. It is
    appended to the message rather than replacing it because it does not change
    the verdict: a change is kept or reverted on its target, and a side effect
    the driver isn't told about is one they'll meet in the next corner instead.
    """
    if not outcome.side_effects:
        return ""
    parts = [f"{_symptom_words(sym, lang)} ({_signed(delta, lang)})"
             for sym, delta in outcome.side_effects]
    items = _msg("side_effect_and", lang).join(
        [", ".join(parts[:-1]), parts[-1]] if len(parts) > 1 else parts)
    return _msg("side_effects" if len(parts) > 1 else "side_effect", lang, items=items)


def _median_time(window: list[LapStats]) -> float:
    return statistics.median([s.lap_time_ms for s in window]) if window else 0.0


def _median_score(window: list[LapStats], symptom: Symptom) -> float:
    if not window:
        return 0.0
    return statistics.median([s.symptom_scores.get(symptom, 0.0) for s in window])


def _median_fuel(window: list[LapStats]) -> float:
    """Typical tank load over a window; 0.0 when the laps predate v11."""
    vals = [s.fuel_l for s in window if s.fuel_l > 0]
    return statistics.median(vals) if vals else 0.0


# --- the engine ------------------------------------------------------------

@dataclass
class _Active:
    change: ProposedChange
    symptom: Symptom
    base_time: float
    base_score: float
    laps_seen: int = 0
    prediction: "Prediction | None" = None
    remedy_rank: int = 0
    base_fuel: float = 0.0
    #: Every symptom's score at the moment the change was applied, so the
    #: verdict can also report what moved that nobody was aiming at.
    base_scores: dict = field(default_factory=dict)


class RaceEngineer:
    """Deterministic convergence engine for one car-class :class:`Profile`."""

    def __init__(self, profile: Profile, *, min_stable: int = _MIN_STABLE,
                 pressure_window: tuple[float, float] | None = None,
                 steps: Steps | None = None) -> None:
        self.profile = profile
        self.min_stable = min_stable
        #: Quanto vale un click su quest'auto. Costruito a mano, il motore
        #: ragiona come ACC — i profili sono nati li' e i test lo usano cosi'.
        #: Chi lo costruisce per un'auto vera passa da `engineer_for`, che il
        #: gioco lo deve sapere e altrimenti risponde «non lo so».
        self.steps: Steps = steps if steps is not None else AccSteps()
        # Engine-local phase list, so a car/track-specific pressure window can be
        # applied without mutating the shared profile singleton.
        self.phases = [
            p.reconfigure(pressure_window=pressure_window, steps=self.steps)
            for p in profile.phases
        ]
        self.phase_idx = 0
        self.window: list[LapStats] = []
        self.active: _Active | None = None
        self.remedy_idx: dict[Symptom, int] = {}     # next remedy to try
        self.exhausted: set[Symptom] = set()         # no remedy helped
        self.history: list[ProposedChange] = []      # accepted changes
        self.applied_clicks: dict[str, int] = {}     # net clicks per parameter
        self._pending: ProposedChange | None = None  # proposed, awaiting mark_applied
        self._pending_is_revert = False              # the pending change is a restore
        self._pending_prediction: Prediction | None = None
        #: Il verdetto REVERTED ancora da eseguire, tenuto intero (messaggio,
        #: ripristino e numeri) finche' `mark_applied` non dice che la macchina
        #: e' tornata com'era. E' quello che `observe` ripete a ogni giro.
        self._held_revert: Decision | None = None
        #: Symptoms whose remedies all failed — the engine's own "this is you,
        #: not the car" call. Recorded because it is a claim we make and have
        #: never checked (see ledger.py).
        self.exhausted_calls: list[Symptom] = []
        #: L'ultimo giro che NON e' entrato nella finestra, tenuto solo per
        #: poterlo spiegare. Si azzera al primo giro buono: una spiegazione che
        #: sopravvive al giro che la smentisce e' peggio di nessuna spiegazione.
        self._skipped: LapStats | None = None
        #: La modifica che l'altra sessione ha scritto sulla macchina e non ha
        #: fatto in tempo a giudicare, in attesa di essere detta una volta sola.
        self._unjudged: str = ""
        #: Il primo rimedio saltato perche' non se ne conosce il passo, durante
        #: l'ultima ricerca. Serve a distinguere «ho finito le leve» da «le leve
        #: le ho, ma non le so scrivere»: la prima e' un'accusa al pilota.
        self._blocked: ProposedChange | None = None
        #: I sintomi gia' dichiarati non scrivibili in questa sessione. Non va
        #: su disco: domani l'auto puo' essere leggibile.
        self._unwritable: set[Symptom] = set()
        #: I giri tagliati (a gomme in temperatura) dall'ultimo cambio di
        #: assetto, gli ultimi `_WINDOW`. Non sono la finestra e non lo
        #: diventano: di loro si legge solo COME e' uscita l'auto, mai il tempo.
        #: Come la finestra non va su disco, e si svuota quando cambia la
        #: macchina (assetto o asciutto/bagnato): un'uscita fatta con un'altra
        #: macchina non accusa questa.
        self._offs: list[LapStats] = []
        #: Le fasi che `_advance` ha passato senza chiuderle: cieche su
        #: quest'auto, o senza niente da correggere col cancello ancora chiuso.
        #: La strada non le spunta come fatte, perche' nessuno le ha
        #: controllate. Va su disco con `phase_idx`, che le ha gia' superate.
        self.skipped_phases: set[int] = set()

    # -- memoria fra sessioni ----------------------------------------------
    def state(self) -> dict:
        """Cosa e' gia' stato provato, in una forma che va su disco.

        **Cosa c'e'**: a che fase eravamo, quale rimedio tocca per ogni sintomo,
        quali sintomi hanno esaurito i rimedi, e i click gia' spesi su ogni leva
        (che e' un budget: senza, l'assetto puo' scivolare via una sessione alla
        volta). E il nome di una modifica applicata e mai giudicata.

        **Cosa NON c'e', di proposito**: la finestra di giri. Sono misure, e due
        sessioni non sono confrontabili — asfalto, benzina e gomme sono altri.
        Un verdetto dato su una base di ieri contro una prova di oggi sarebbe
        peggio di nessun verdetto, ed e' esattamente il difetto che questo
        progetto ha gia' pagato altrove (il verdetto del focus attraverso un
        cambio di riferimento). Nemmeno `history`, che in questo modulo non la
        rilegge nessuno: il registro delle modifiche accettate e' `ledger.py`,
        su file, e averne due sarebbe averne zero.
        """
        pending = self.active.change if self.active is not None else None
        return {
            "phase_idx": self.phase_idx,
            "skipped_phases": sorted(self.skipped_phases),
            "remedy_idx": {_sym_key(k): v for k, v in self.remedy_idx.items()},
            "exhausted": [_sym_key(s) for s in self.exhausted],
            # Le chiavi sono coppie (parametro, slot) e JSON vuole stringhe:
            # una lista di triple invece di inventare un separatore dentro una
            # chiave, che e' il modo classico di romperlo su un nome con un
            # trattino dentro.
            "applied_clicks": [[p, slot, n]
                               for (p, slot), n in self.applied_clicks.items()],
            # La modifica per nome, che e' come la cita il messaggio di domani.
            "unjudged": pending.named if pending is not None else "",
        }

    def restore(self, state: dict | None) -> None:
        """Rimette la memoria dell'altra sessione, saltando quello che non torna.

        Best-effort in ogni riga: la persistenza e' una comodita', e un file
        rovinato non deve costare al pilota la sessione. Quello che non si
        riconosce si scarta in silenzio e il motore riparte da li'.
        """
        if not isinstance(state, dict):
            return
        idx = state.get("phase_idx")
        if isinstance(idx, int) and 0 <= idx < len(self.phases):
            self.phase_idx = idx
        for i in state.get("skipped_phases") or []:
            if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(self.phases):
                self.skipped_phases.add(i)
        tried = state.get("remedy_idx")
        for key, val in (tried.items() if isinstance(tried, dict) else ()):
            sym = _sym_from_key(key)
            if sym is not None and isinstance(val, int):
                self.remedy_idx[sym] = val
        for key in state.get("exhausted") or []:
            sym = _sym_from_key(key)
            if sym is not None:
                self.exhausted.add(sym)
        for row in state.get("applied_clicks") or []:
            if (isinstance(row, (list, tuple)) and len(row) == 3
                    and isinstance(row[2], int)):
                self.applied_clicks[(row[0], row[1])] = row[2]
        why = state.get("unjudged")
        self._unjudged = why if isinstance(why, str) else ""

    # -- public API --------------------------------------------------------
    @property
    def phase(self) -> WorkPhase | None:
        return self.phases[self.phase_idx] if self.phase_idx < len(self.phases) else None

    def progress(self, lang: str | None = None) -> dict:
        """Dove e' il lavoro: le fasi, quella in corso e che punto del suo ciclo.

        Lo legge la pagina per disegnare la strada e il contatore di giri; sta
        qui e non nel browser perche' lo stato (`_pending`, `_held_revert`,
        `active`) e' privato del motore e il browser lo indovinerebbe dal testo
        dei messaggi. L'ordine dei casi e' quello di `observe`: un ripristino
        da rimettere viene prima di tutto, poi il test in corso, poi la
        proposta in attesa, poi la raccolta di giri. «Finito» viene dopo i
        primi tre: a fasi chiuse `_advance` ricontrolla ancora le pressioni e
        puo' proporre, e quella modifica va fatta e provata come le altre.
        """
        from .profiles._common import tr
        phases = [{"key": p.key, "label": tr(p.label, lang), "tag": p.tag}
                  for p in self.phases]
        out = {"phases": phases, "index": min(self.phase_idx, len(self.phases)),
               "skipped": sorted(self.skipped_phases),
               "stage": "diagnose", "have": None, "need": None}
        if self._held_revert is not None or (
                self._pending is not None and self._pending_is_revert):
            out["stage"] = "restore"
        elif self.active is not None:
            out.update(stage="test", have=self.active.laps_seen,
                       need=self.min_stable)
        elif self._pending is not None:
            out["stage"] = "change"
        elif self.phase is None:
            out["stage"] = "done"
        elif len(self.window) < self.min_stable:
            out.update(stage="baseline", have=len(self.window),
                       need=self.min_stable)
        return out

    def observe(self, stats: LapStats) -> Decision:
        """Feed one completed lap; return the next recommendation."""
        # Un ripristino non ancora confermato viene prima di tutto, pioggia
        # compresa: e' un fatto sulla macchina, non una misura. Finche' il
        # pilota non dice di aver rimesso l'assetto di prima, la modifica
        # bocciata e' ancora montata — e questo giro e' stato guidato con lei.
        # Quindi non entra nella finestra (sarebbe la base del prossimo rimedio,
        # misurata sull'assetto appena scartato) e la risposta resta quella di
        # prima: lo STESSO oggetto, cosi' chi sta a valle distingue «te lo sto
        # ripetendo» da «e' un verdetto nuovo» senza indovinare.
        # Fino al 13/10 qui non c'era niente: il giro dopo rispondeva COLLECT,
        # il ripristino spariva dallo schermo, e tre giri piu' tardi `_propose`
        # metteva in attesa il rimedio successivo SOPRA quello bocciato.
        if self._held_revert is not None:
            return self._held_revert

        # A dry↔wet switch invalidates everything measured either side of it: a
        # baseline driven on slicks and a re-test driven on wets are two
        # different cars on two different circuits. Checked before the lap is
        # banked, so the abandoned test isn't judged on a mixed window.
        changed = self._conditions_changed(stats)

        if stats.stable and stats.warmed_up:
            self.window.append(stats)
            self.window = self.window[-_WINDOW:]
            if self.active is not None:
                self.active.laps_seen += 1
            self._skipped = None
        else:
            self._skipped = stats
            # Fuori con le gomme fredde il sospettato e' la gomma: non conta.
            if stats.unstable_why == "cut" and stats.warmed_up:
                self._offs = (self._offs + [stats])[-_WINDOW:]

        if changed:
            return Decision(DecisionKind.STAND_DOWN,
                            _msg("conditions_changed", current_language()))

        # Wet: the remedy tables are dry-derived and several of them invert in
        # the rain (less wing for understeer at a fast apex is exactly wrong on
        # a wet track). Nothing here has ever seen a wet lap — the archive
        # contains none — so this is a refusal, not a gap waiting for a switch.
        if stats.wet is True:
            return Decision(DecisionKind.STAND_DOWN,
                            _msg("wet_stand_down", current_language()))

        # An applied change under evaluation takes priority.
        if self.active is not None:
            return self._evaluate_active()

        # …e una rimasta in sospeso dall'altra sessione non lo e': la sua base di
        # confronto e' rimasta di la'. Si dice e si chiude, una volta sola.
        pendente, self._unjudged = self._unjudged, ""
        if pendente:
            return Decision(DecisionKind.COLLECT,
                            _msg("unjudged", current_language(), why=pendente))

        if len(self.window) < self.min_stable:
            tail = _skip_tail(self._skipped) + self._off_tail()
            return Decision(DecisionKind.COLLECT,
                            _msg("collect", n=self.min_stable,
                                 have=len(self.window)) + tail,
                            tail=tail)
        return self._advance()

    def mark_applied(self) -> None:
        """Tell the engine the last PROPOSE (or revert) was written to the setup."""
        if self._pending is None:
            return
        # Sulla macchina c'e' un altro assetto (nuovo o rimesso): le uscite
        # fatte con quello di prima non dicono niente di questo.
        self._offs = []
        if self._pending_is_revert:
            # The driver restored the previous setup. Don't evaluate the revert or
            # bank it: the bad change was never recorded, so undoing it must not
            # touch the click budget. Just resume collecting fresh laps so the next
            # remedy's baseline is measured on the restored setup, not the bad one.
            self.active = None
            self.window = []
            self._pending = None
            self._pending_is_revert = False
            self._held_revert = None
            self._pending_prediction = None
            return
        sym = self._pending.symptom
        self.active = _Active(
            change=self._pending,
            symptom=sym,
            base_time=_median_time(self.window),
            base_score=_median_score(self.window, sym) if sym else 0.0,
            prediction=self._pending_prediction,
            remedy_rank=self.remedy_idx.get(sym, 0) if sym else 0,
            base_fuel=_median_fuel(self.window),
            # Every symptom on the books, not just the target: the verdict is
            # about one of them, the ledger is about all of them.
            base_scores=self._all_scores(),
        )
        # The reference shifts when the setup changes — restart the window so the
        # verdict is measured only on post-change laps.
        self.window = []
        self._pending = None
        self._pending_prediction = None

    def _conditions_changed(self, stats: LapStats) -> bool:
        """Did the track flip dry↔wet since the laps already in hand?

        Only a *known* flip counts. A lap that doesn't say which tyres were on
        (sixteen of the thirty-nine in our archive) can't contradict anything,
        and treating "unknown" as a change would throw away good windows every
        time an older lap turned up.

        On a real flip everything in flight is dropped: the window, and any test
        under evaluation. The alternative is a verdict computed across a rain
        shower, which is a number with no meaning presented as one with one.
        """
        if stats.wet is None:
            return False
        known = [s.wet for s in self.window if s.wet is not None]
        if not known or known[-1] == stats.wet:
            return False
        self.window = []
        self._offs = []
        self.active = None
        self._pending = None
        self._pending_is_revert = False
        self._pending_prediction = None
        return True

    # -- the prediction ----------------------------------------------------
    def _all_scores(self) -> dict:
        """Every symptom's typical score over the current window."""
        seen: set[Symptom] = set()
        for s in self.window:
            seen.update(s.symptom_scores.keys())
        return {sym: _median_score(self.window, sym) for sym in seen}

    def _predict(self, change: ProposedChange) -> Prediction:
        """The bar this change will be judged against, stated in advance.

        Nothing here is a guess: every number is the rule ``_evaluate_active``
        is about to apply. That is the point — the driver is told the test
        before sitting the exam, not the grade afterwards.
        """
        lang = current_language()
        sym = change.symptom
        base_time = _median_time(self.window)
        band = max(base_time * _TIME_BAND_FRAC, 1.0)
        if sym is None:
            return Prediction(
                symptom=None, score_now=0.0, score_below=0.0, time_band_ms=band,
                text=_msg("predict_structural", lang, n=self.min_stable,
                          ms=fmt_num(band, 0, lang)))
        now = _median_score(self.window, sym)
        bar = round(now - _EPS_SCORE, 3)
        return Prediction(
            symptom=sym, score_now=round(now, 3), score_below=bar,
            time_band_ms=band,
            text=_msg("predict", lang, sym=_symptom_words(sym, lang),
                      a=_score(now, lang), b=_score(bar, lang),
                      n=self.min_stable, ms=fmt_num(band, 0, lang)))

    def _sized(self, change: ProposedChange) -> ProposedChange | None:
        """La stessa modifica col passo di quest'auto, o None se non si sa.

        Vale per quello che finisce in un file (``BOX``). Una leva al volante
        (``AV``) la gira il pilota, un click alla volta, e il click li' e' il
        suo: non c'e' niente da convertire.
        """
        if change.tag != "BOX":
            return change
        atoms = []
        for c in change.changes:
            units = self.steps.units(c.param, c.slot)
            if units is None:
                return None
            atoms.append(AtomicChange(c.param, c.slot, c.delta_clicks, units))
        return ProposedChange(tuple(atoms), change.rationale, change.phase_label,
                              change.tag, change.symptom, change.lever)

    def _cannot_write(self, change: ProposedChange) -> Decision:
        """Dire cosa si proverebbe, e perche' non lo si scrive."""
        lang = current_language()
        why = self.steps.why(lang)
        if change.symptom is None:
            return Decision(DecisionKind.STAND_DOWN,
                            _msg("no_step_plain", lang, what=change.rationale,
                                 why=why))
        return Decision(DecisionKind.STAND_DOWN,
                        _msg("no_step", lang,
                             sym=_symptom_words(change.symptom, lang),
                             what=change.named, why=why))

    def _propose(self, change: ProposedChange, confidence: str) -> Decision:
        """Hold a change as pending and hand it over with its acceptance bar."""
        # L'unica porta da cui una modifica esce verso il setup. Chi la chiama
        # ha gia' scartato quello che non sa scrivere; questo e' il controllo
        # che resta se domani nasce una strada che non lo fa.
        sized = self._sized(change)
        if sized is None:
            return self._cannot_write(change)
        change = sized
        self._pending = change
        self._pending_is_revert = False
        self._pending_prediction = self._predict(change)
        return Decision(DecisionKind.PROPOSE, change.rationale, change,
                        confidence, prediction=self._pending_prediction)

    def _side_effects(self, a: "_Active") -> tuple:
        """Symptoms that moved and weren't the target, worst first.

        Only what cleared the same bar the verdict uses for the target: below it
        the engine already refuses to call a change an improvement, so calling
        it a side effect would be a stricter claim made on weaker evidence.
        """
        after = self._all_scores()
        out = []
        for sym, before in a.base_scores.items():
            if sym == a.symptom:
                continue
            delta = after.get(sym, 0.0) - before
            if abs(delta) >= _EPS_SCORE:
                out.append((sym, round(delta, 3)))
        out.sort(key=lambda kv: abs(kv[1]), reverse=True)
        return tuple(out)

    def _fuel_gap(self, a: "_Active") -> tuple[float, bool]:
        """(litres of difference, whether that breaks the time comparison).

        The baseline laps are driven before the change and the re-test laps
        after — and in between the driver goes to the garage to load the setup,
        which on most sessions refuels the car. So the two windows are routinely
        driven at different weights, in a direction that isn't predictable: the
        post-change laps can be *heavier* (fresh tank) or *lighter* (long first
        stint). This is not an edge case, it is the normal shape of the loop.

        Returns 0.0 / False when either window predates v11 — no fuel recorded
        is "we don't know", not "the loads matched".
        """
        after = _median_fuel(self.window)
        if a.base_fuel <= 0 or after <= 0:
            return 0.0, False
        gap = after - a.base_fuel
        return round(gap, 2), abs(gap) >= _FUEL_BIAS_L

    def _outcome(self, a: "_Active", *, kept: bool, score_after: float) -> Outcome:
        gap, confounded = self._fuel_gap(a)
        return Outcome(
            prediction=a.prediction or self._predict(a.change),
            score_after=round(score_after, 3),
            time_before_ms=round(a.base_time, 1),
            time_after_ms=round(_median_time(self.window), 1),
            laps=a.laps_seen, kept=kept, remedy_rank=a.remedy_rank,
            fuel_before_l=round(a.base_fuel, 2),
            fuel_after_l=round(a.base_fuel + gap, 2) if gap else round(
                _median_fuel(self.window), 2),
            time_confounded=confounded,
            side_effects=self._side_effects(a),
        )

    def _revert(self, change: ProposedChange, message: str,
                outcome: "Outcome | None" = None) -> Decision:
        """Reject a change: propose its reversal AND hold it as a *pending revert*.

        Resets the window, and the decision is *held*: :meth:`observe` keeps
        returning it, lap after lap, until the driver has applied the restore.
        Only then does the engine go back to COLLECT, so the next baseline is
        measured on the restored setup, not on the rejected one. :meth:`mark_applied` recognises the revert and just
        acknowledges it (no re-test cycle, no click-budget change)."""
        rev = change.reversed()
        self._pending = rev
        self._pending_is_revert = True
        # The outcome has to be built by the caller, before this line: the window
        # it is measured from is cleared right here.
        self.window = []
        self._held_revert = Decision(DecisionKind.REVERTED, message, rev,
                                     outcome=outcome)
        return self._held_revert

    # -- internals ---------------------------------------------------------
    def handles_pressures(self) -> bool:
        """L'Ingegnere sa giudicare le pressioni di quest'auto?

        Vero quando il profilo ha una fase pressioni e quella fase conosce la
        finestra. E' la domanda che il motore fa per decidere chi parla delle
        gomme: se la risposta e' si', parla lui, perche' e' lui che sa chiamare
        ai box e preparare la modifica.
        """
        pp = self._pressure_phase()
        return pp is not None and not pp.blind()

    def _pressure_phase(self) -> WorkPhase | None:
        for ph in self.phases:
            if getattr(ph, "pressure_remedy", None) is not None:
                return ph
        return None

    def _advance(self) -> Decision:
        """No active change: check the gate, else propose the next remedy."""
        # Lazy import avoids a module-level cycle (profiles import from core).
        from .profiles._common import tr
        lang = current_language()
        phase = self.phase
        # Le pressioni si ricontrollano anche dopo la loro fase. Fino al 14/10
        # la fase pressioni si chiudeva una volta e basta; se poi la gomma
        # usciva di finestra (pista che si scalda, stint lungo) lo diceva solo
        # il coach, con un numero da sistemare «a freddo» e nessuna chiamata ai
        # box, nessuna modifica pronta sulla pagina. Il pilota l'ha chiesto in
        # pista: se le gomme sono da sistemare, chiamami dentro e prepara il
        # cambio. Le pressioni sono la base di tutto il resto, quindi vengono
        # prima della fase in corso, e solo quando nessuna prova e' aperta
        # (`_advance` non gira mentre una modifica si valuta).
        pp = self._pressure_phase()
        if (pp is not None and phase is not pp and not pp.blind()
                and not pp.gate(self.window)):
            change = self._pressure_remedy(pp)
            if change is not None:
                return self._propose(change, "high")
        if phase is None:
            return Decision(DecisionKind.DONE, _msg("done", lang))
        blind = phase.blind()
        if blind:
            # Prima del cancello, non dopo: un cancello che non sa cosa guardare
            # risponderebbe «a posto», e il pilota leggerebbe «fase completata»
            # su una cosa che nessuno ha controllato.
            self.skipped_phases.add(self.phase_idx)
            self.phase_idx += 1
            return Decision(DecisionKind.STAND_DOWN, blind)
        if phase.gate(self.window):
            self.phase_idx += 1
            nxt = self.phase
            tail = (_msg("phase_tail_next", lang, nxt=tr(nxt.label)) if nxt
                    else _msg("phase_tail_complete", lang))
            return Decision(DecisionKind.PHASE_DONE,
                            _msg("phase_done", lang, label=tr(phase.label),
                                 tail=tail))

        symptom = self._dominant_symptom(phase)
        if symptom is None:
            # Gate not met but no symptom we can act on (e.g. pressures out of
            # window is handled by the gate's own remedy path below).
            change = self._pressure_remedy(phase)
            if change is not None:
                return self._propose(change, "high")
            # Fuori finestra, ma su quest'auto non sappiamo quanto vale un
            # click di pressione: si dice la misura e si resta qui. Passare alla
            # fase dopo sarebbe lavorare di barre su gomme sbagliate.
            by_hand = self._pressure_by_hand(phase)
            if by_hand:
                return Decision(DecisionKind.STAND_DOWN, by_hand)
            # Nothing actionable here; move on to avoid a stall. Il cancello pero'
            # non e' passato: per la strada e' saltata, non fatta.
            self.skipped_phases.add(self.phase_idx)
            self.phase_idx += 1
            return Decision(DecisionKind.PHASE_DONE,
                            _msg("phase_nothing", lang, label=tr(phase.label)))

        change = self._remedy_for(symptom, phase)
        if change is None and self._blocked is not None:
            # Le leve ci sono, e' il passo che manca: non e' «rimedi esauriti,
            # probabile questione di guida», e non va nel conto di quante volte
            # lo diciamo. Detto una volta; poi il sintomo si lascia stare.
            self._unwritable.add(symptom)
            return self._cannot_write(self._blocked)
        if change is None:
            self.exhausted.add(symptom)
            # "Setup can't fix this, so it's you" is a claim, and one we have
            # never checked. Kept so the ledger can count how often we make it.
            self.exhausted_calls.append(symptom)
            return Decision(DecisionKind.PHASE_DONE,
                            _msg("remedies_exhausted", lang,
                                 sym=_symptom_words(symptom, lang)))
        return self._propose(change, self._confidence(symptom))

    def _evaluate_active(self) -> Decision:
        a = self.active
        lang = current_language()
        if a.laps_seen < self.min_stable:
            need = self.min_stable - a.laps_seen
            tail = _skip_tail(self._skipped, lang)
            return Decision(DecisionKind.EVALUATING,
                            _msg("evaluating", lang, laps=_laps_left(need, lang))
                            + tail, tail=tail)

        new_time = _median_time(self.window)
        new_score = _median_score(self.window, a.symptom)
        d_time = new_time - a.base_time
        d_score = new_score - a.base_score
        band = max(a.base_time * _TIME_BAND_FRAC, 1.0)

        self.active = None
        band_ok = d_time <= band

        _gap, fuel_confounded = self._fuel_gap(a)
        if fuel_confounded:
            # The two windows weren't driven at the same weight, so their times
            # aren't comparable. Suspending the veto rather than guessing at a
            # correction: converting litres to seconds needs a sensitivity we
            # have never measured, and a made-up number would end up deciding
            # whether a setup change is kept.
            band_ok = True

        # Structural changes (e.g. tyre pressures) carry no symptom: judge them on
        # lap time alone and let the phase gate re-check the real target.
        if a.symptom is None:
            if not band_ok:
                out = self._outcome(a, kept=False, score_after=0.0)
                return self._revert(a.change, _msg("revert_structural", lang), out)
            out = self._outcome(a, kept=True, score_after=0.0)
            self._record(a.change)
            # With no symptom to fall back on there is nothing left to judge this
            # on, so it is kept and *said* — the phase gate (the pressure window)
            # remains the real authority, exactly as it is when the time is
            # usable. Reverting instead would put the gate straight back into
            # proposing the same change, forever.
            key = ("accepted_unjudged" if fuel_confounded
                   else "accepted_structural")
            return Decision(DecisionKind.ACCEPTED, _msg(key, lang), outcome=out)

        improved = d_score <= -_EPS_SCORE and band_ok

        if improved:
            out = self._outcome(a, kept=True, score_after=new_score)
            self._record(a.change)
            key = ("accepted_resolved" if new_score < _SYMPTOM_THRESH
                   else "accepted_improving")
            msg = _msg(key, lang, sym=_symptom_words(a.symptom, lang),
                       a=_score(a.base_score, lang), b=_score(new_score, lang))
            return Decision(DecisionKind.ACCEPTED,
                            msg + _fuel_tail(out, lang) + _side_effect_tail(out, lang),
                            outcome=out)

        # Not an improvement (worse OR plateau): revert and try the next lever.
        # Reverting on a plateau too is deliberate — keeping changes a blind meter
        # reads as "harmless" is exactly how setup drift creeps in.
        out = self._outcome(a, kept=False, score_after=new_score)
        self.remedy_idx[a.symptom] = self.remedy_idx.get(a.symptom, 0) + 1
        reason = (_msg("reason_worse", lang) if not band_ok or d_score > _EPS_SCORE
                  else _msg("reason_noeffect", lang))
        return self._revert(a.change,
                            _msg("revert_reason", lang, reason=reason,
                                 sym=_symptom_words(a.symptom, lang)), out)

    # -- symptom selection with safety gates -------------------------------
    def _corners(self, sym: Symptom) -> int:
        return max((s.symptom_corners.get(sym, 0) for s in self.window), default=0)

    def corners_for(self, sym: Symptom | None) -> list[int]:
        """Distinct corner indices where ``sym`` showed across the window — the
        evidence to anchor a proposal to (e.g. 'Corners 7, 9')."""
        if sym is None:
            return []
        out: set[int] = set()
        for s in self.window:
            out.update(s.symptom_corner_idx.get(sym, []))
        return sorted(out)

    def _persistence(self, sym: Symptom) -> int:
        return sum(1 for s in self.window
                   if s.symptom_scores.get(sym, 0.0) >= _SYMPTOM_THRESH)

    def _confidence(self, sym: Symptom) -> str:
        return ("high" if self._corners(sym) >= 4
                and _median_score(self.window, sym) >= 0.5 else "medium")

    def _dominant_symptom(self, phase: WorkPhase) -> Symptom | None:
        seen: set[Symptom] = set()
        for s in self.window:
            seen.update(s.symptom_scores.keys())
        best, best_score = None, _SYMPTOM_THRESH
        for sym in seen:
            if (sym in self.exhausted or sym in self._unwritable
                    or not phase.owns(sym)):
                continue
            score = _median_score(self.window, sym)
            if score < best_score:
                continue
            # Setup, not driving: must span several corners AND persist over laps.
            if self._corners(sym) < _MIN_CORNERS:
                continue
            if self._persistence(sym) < self.min_stable:
                continue
            best, best_score = sym, score
        return best

    # -- le uscite di pista come indizio ------------------------------------
    def _off_pattern(self) -> tuple[Symptom, list[LapStats]] | None:
        """Lo schema che si ripete nelle uscite, se il setup puo' spiegarlo.

        Lo STESSO cancello che separa l'assetto dalla guida sui giri puliti
        (`_dominant_symptom`): almeno ``min_stable`` uscite con lo stesso
        sintomo e almeno ``_MIN_CORNERS`` curve diverse. Un'uscita isolata, o
        quattro nella stessa curva, restano guida.

        Nessun numero nuovo, ed e' una scelta: sui giri veri non c'era niente
        con cui tararne uno. Delle 38 uscite in archivio nessuna porta un
        sintomo (`diagnosis._off_symptom`), quindi la regola su quelle serate
        non scatta mai — e non esiste, nell'archivio, una serata in cui il
        pilota uscisse per colpa dell'assetto, cioe' il caso che dovrebbe far
        scattare. La soglia giusta non si puo' misurare; questa e' la piu'
        prudente che avessimo gia', quella che il motore chiede ai giri buoni.
        """
        by_sym: dict[Symptom, list[LapStats]] = {}
        for s in self._offs:
            if s.off_symptom is not None:
                by_sym.setdefault(s.off_symptom, []).append(s)
        # Il primo schema che passa, non «il piu' numeroso»: con `_WINDOW` (6)
        # uscite in tutto, due schemi che passano entrambi sono per forza tre e
        # tre, e fra due pari non c'e' niente da scegliere.
        for sym, laps in by_sym.items():
            # Gia' dichiarato «e' guida» (rimedi finiti) o non scrivibile su
            # quest'auto: le uscite non riaprono quello che il motore ha chiuso.
            if sym in self.exhausted or sym in self._unwritable:
                continue
            if len(laps) < self.min_stable:
                continue
            if len({s.off_corner for s in laps}) < _MIN_CORNERS:
                continue
            return sym, laps
        return None

    def _first_lever(self, sym: Symptom) -> str:
        """La leva che il motore proverebbe per ``sym``, in parole, o ""."""
        remedies = self.profile.remedy_table.get(sym) or []
        idx = self.remedy_idx.get(sym, 0)
        phase = next((p for p in self.phases if p.owns(sym)), None)
        if phase is None or idx >= min(len(remedies), _REMEDY_CAP):
            return ""
        return remedies[idx](sym, phase).named

    def _off_tail(self) -> str:
        """Il sospetto sull'assetto, in coda al contatore, o "".

        **Perche' un sospetto e non una proposta.** Una modifica il motore la
        scrive solo se poi sa giudicarla, e qui non saprebbe. Il tempo dei giri
        tagliati non entra mai in un verdetto (sei su tredici erano piu' veloci
        tagliando la Variante). E il sintomo misurato sui giri puliti non e' un
        metro onesto per questa modifica: i giri puliti sono per costruzione
        quelli in cui l'auto NON e' uscita, quindi il confronto «prima: le
        uscite, dopo: i giri puliti» darebbe ragione alla modifica comunque.
        Contare le uscite prima e dopo, infine, misura soprattutto il pilota,
        che nel frattempo impara la curva. Un verdetto senza metro e' quello
        che il registro (`ledger.py`) esiste per non avere.

        Quindi si dice — perche', quante, dove, e quale leva proverebbe — e il
        motore resta quello di prima: appena ci sono i giri puliti, se il
        sintomo si vede anche li', lo propone e lo misura come tutti gli altri.
        Solo in raccolta: quando la finestra c'e', parla il ciclo normale.
        """
        found = self._off_pattern()
        if found is None:
            return ""
        sym, laps = found
        lang = current_language()
        names: list[str] = []
        for s in laps:
            if s.lost_where and s.lost_where not in names:
                names.append(s.lost_where)
        where = f" ({', '.join(names)})" if names else ""
        kw = dict(k=len(laps), n=len(self._offs), what=_symptom_words(sym, lang),
                  c=len({s.off_corner for s in laps}), where=where)
        lever = self._first_lever(sym)
        tail = _msg("off_lever", lang, lever=lever) if lever else ""
        return _msg("off_pattern", lang, **kw) + tail

    def _remedy_for(self, symptom: Symptom, phase: WorkPhase) -> ProposedChange | None:
        self._blocked = None
        remedies = self.profile.remedy_table.get(symptom)
        if not remedies:
            return None
        start = idx = self.remedy_idx.get(symptom, 0)
        while idx < len(remedies) and idx < _REMEDY_CAP:
            change = remedies[idx](symptom, phase)
            if self._over_budget(change):
                idx += 1
                continue
            if self._sized(change) is None:
                # Non si sa quanto vale un click di questa leva su quest'auto:
                # si prova la successiva, e ci si ricorda di averla saltata.
                self._blocked = self._blocked or change
                idx += 1
                continue
            self.remedy_idx[symptom] = idx
            return change
        # Il punto a cui si era arrivati va su disco. Se la ricerca e' finita
        # per un passo che manca, resta dov'era: il giorno che l'auto e'
        # leggibile quelle leve sono ancora da provare.
        self.remedy_idx[symptom] = start if self._blocked is not None else idx
        return None

    def _over_budget(self, change: ProposedChange) -> bool:
        # Budget per (param, slot): toe-front and toe-rear (or front/rear pressure)
        # are different physical levers and must not share — or cancel — one budget.
        for c in change.changes:
            projected = self.applied_clicks.get((c.param, c.slot), 0) + c.delta_clicks
            if abs(projected) > _CLICK_BUDGET:
                return True
        return False

    def _record(self, change: ProposedChange) -> None:
        """Bank an accepted change: history + per-(param, slot) click budget."""
        self.history.append(change)
        for c in change.changes:
            key = (c.param, c.slot)
            self.applied_clicks[key] = self.applied_clicks.get(key, 0) + c.delta_clicks

    def _pressure_remedy(self, phase: WorkPhase) -> ProposedChange | None:
        """If this phase gates on tyre pressure, nudge the off-target axle."""
        builder = getattr(phase, "pressure_remedy", None)
        if builder is None or not self.window:
            return None
        return builder(self.window[-1])

    def _pressure_by_hand(self, phase: WorkPhase) -> str:
        """La frase per una pressione fuori finestra che non sappiamo scrivere."""
        builder = getattr(phase, "pressure_by_hand", None)
        if builder is None or not self.window:
            return ""
        return builder(self.window[-1])
