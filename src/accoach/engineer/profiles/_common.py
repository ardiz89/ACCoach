"""Shared building blocks for the per-class engineer profiles.

Symptom/phase aliases, the remedy-builder factory, and a generic tyre-pressure
phase parameterised by the class's hot-pressure window.
"""

from __future__ import annotations

from ...i18n import current_language
from ..core import (
    ALL,
    FRONT,
    REAR,
    _SYMPTOM_THRESH,
    _median_score,
    AtomicChange,
    Balance,
    LapStats,
    Phase,
    ProposedChange,
    Speed,
    Symptom,
    WorkPhase,
)
from ..steps import Steps, UnknownSteps

# Short aliases used throughout the remedy tables.
U, O = Balance.UNDERSTEER, Balance.OVERSTEER
EN, AP, EX = Phase.ENTRY, Phase.APEX, Phase.EXIT
LO, HI = Speed.LOW, Speed.HIGH

_SEG_LIMIT = 3                 # lock/spin segments that count as "recurring"
# Quanta pressione al massimo in un solo passaggio ai box. Viene dall'import
# iniziale del progetto (erano «8 click», scritti pensando ad ACC) e non e' mai
# stato misurato; una gomma un paio di psi fuori finestra si prende in tre
# soste. Che il passo sia corto va bene: fra un passo e il successivo
# l'Ingegnere MISURA, ed e' l'unico motivo per cui il suo registro vale
# qualcosa. Tacerlo no, ed e' quello che questo modulo faceva.
#
# E' in psi e non in click perche' un click non vale uguale dappertutto: 0.1 psi
# su ACC, 1 psi su quasi tutte le auto di Assetto Corsa. Quanti click sono lo
# dice `engineer/steps.py`, auto per auto. Dove un solo click supera gia' questo
# tetto (AC) il passo e' un click: meno di cosi' l'auto non si muove.
_MAX_PSI_PER_STOP = 0.8

_SLOTS = {"front": FRONT, "rear": REAR, "all": ALL, None: (None,)}


# --- EN→IT catalogue -------------------------------------------------------
# The remedy rationales, phase labels and al-volo lever names are authored in
# English (the canonical interface language); when the app language is Italian we
# look them up here. Strings are FIXED (the numeric click, e.g. "(−1)", is part of
# the phrase), so a static map suffices — no templating needed. The setup param
# keys, AV/BOX tags and Symptom enums are technical identifiers and stay as-is.
_IT: dict[str, str] = {
    # --- remedy rationales (GT3 + Formula + Road) ---
    "Understeer on slow entry: softer front anti-roll bar (−1)":
        "Sottosterzo in entrata lenta: barra anteriore più morbida (−1)",
    "Understeer on entry: more front toe-out (+1)":
        "Sottosterzo in entrata: più toe-out anteriore (+1)",
    "Understeer on entry: brake bias slightly rearward (−1)":
        "Sottosterzo in entrata: bias freni un filo indietro (−1)",
    "Understeer on entry: softer front anti-roll bar (−1)":
        "Sottosterzo in entrata: barra anteriore più morbida (−1)",
    "Understeer on fast entry: raise the rear, more rake (+2)":
        "Sottosterzo in entrata veloce: alza il posteriore, più rake (+2)",
    "Understeer on fast entry: more front splitter (+1)":
        "Sottosterzo in entrata veloce: più splitter anteriore (+1)",
    "Understeer on fast entry: softer front anti-roll bar (−1)":
        "Sottosterzo in entrata veloce: barra anteriore più morbida (−1)",
    "Understeer on fast entry: more front wing (+1)":
        "Sottosterzo in entrata veloce: più ala anteriore (+1)",
    "Understeer on fast entry: more rake, raise the rear (+2)":
        "Sottosterzo in entrata veloce: più rake, alza il posteriore (+2)",
    "Understeer on fast entry: less rear wing (−1)":
        "Sottosterzo in entrata veloce: meno ala posteriore (−1)",
    "Understeer at slow apex: less differential preload (−1)":
        "Sottosterzo all'apex lento: meno precarico differenziale (−1)",
    "Understeer at apex: softer front anti-roll bar (−1)":
        "Sottosterzo all'apex: barra anteriore più morbida (−1)",
    "Understeer at apex: softer front springs (−1)":
        "Sottosterzo all'apex: molle anteriori più morbide (−1)",
    "Understeer at apex: more front negative camber (−1)":
        "Sottosterzo all'apex: più camber negativo anteriore (−1)",
    "Understeer at fast apex: less rear wing (−1)":
        "Sottosterzo all'apex veloce: meno ala posteriore (−1)",
    "Understeer at fast apex: more front splitter (+1)":
        "Sottosterzo all'apex veloce: più splitter anteriore (+1)",
    "Understeer at fast apex: more rake (+1)":
        "Sottosterzo all'apex veloce: più rake (+1)",
    "Understeer at fast apex: more front wing (+1)":
        "Sottosterzo all'apex veloce: più ala anteriore (+1)",
    "Understeer on slow exit (traction): less diff preload (−1)":
        "Sottosterzo in uscita lenta (trazione): meno precarico diff (−1)",
    "Understeer on exit: softer rear anti-roll bar (−1)":
        "Sottosterzo in uscita: barra posteriore più morbida (−1)",
    "Understeer on exit (power): less locked differential (−1)":
        "Sottosterzo in uscita (power): differenziale meno bloccato (−1)",
    "Understeer on exit: less locked differential on power (−1)":
        "Sottosterzo in uscita: differenziale meno bloccato in power (−1)",
    "Understeer on fast exit: less rear wing (−1)":
        "Sottosterzo in uscita veloce: meno ala posteriore (−1)",
    "Understeer on fast exit: more splitter (+1)":
        "Sottosterzo in uscita veloce: più splitter (+1)",
    "Understeer on fast exit: more front wing (+1)":
        "Sottosterzo in uscita veloce: più ala anteriore (+1)",
    "Oversteer on slow entry: brake bias more forward (+1)":
        "Sovrasterzo in entrata lenta: bias freni più avanti (+1)",
    "Oversteer on entry: brake bias more forward (+1)":
        "Sovrasterzo in entrata: bias freni più avanti (+1)",
    "Oversteer on entry: softer rear anti-roll bar (−1)":
        "Sovrasterzo in entrata: barra posteriore più morbida (−1)",
    "Oversteer on entry: more rear toe-in (+1)":
        "Sovrasterzo in entrata: più toe-in posteriore (+1)",
    "Lift-off oversteer: more locked differential on coast (+1)":
        "Sovrasterzo in rilascio: differenziale più chiuso in coast (+1)",
    "Oversteer on fast entry: more rear wing (+1)":
        "Sovrasterzo in entrata veloce: più ala posteriore (+1)",
    "Oversteer on fast entry: lower the rear (−2)":
        "Sovrasterzo in entrata veloce: abbassa il posteriore (−2)",
    "Oversteer on fast entry: softer rear anti-roll bar (−1)":
        "Sovrasterzo in entrata veloce: barra posteriore più morbida (−1)",
    "Oversteer at slow apex: softer rear anti-roll bar (−1)":
        "Sovrasterzo all'apex lento: barra posteriore più morbida (−1)",
    "Oversteer at apex: more differential preload (+1)":
        "Sovrasterzo all'apex: più precarico differenziale (+1)",
    "Oversteer at apex: softer rear anti-roll bar (−1)":
        "Sovrasterzo all'apex: barra posteriore più morbida (−1)",
    "Oversteer at apex: more rear toe-in (+1)":
        "Sovrasterzo all'apex: più toe-in posteriore (+1)",
    "Oversteer at fast apex: more rear wing (+1)":
        "Sovrasterzo all'apex veloce: più ala posteriore (+1)",
    "Oversteer at fast apex: softer rear anti-roll bar (−1)":
        "Sovrasterzo all'apex veloce: barra posteriore più morbida (−1)",
    "Oversteer on exit (traction): more traction control (+1)":
        "Sovrasterzo in uscita (trazione): più controllo di trazione (+1)",
    "Oversteer on exit: softer rear anti-roll bar (−1)":
        "Sovrasterzo in uscita: barra posteriore più morbida (−1)",
    "Oversteer on exit: softer rear springs (−1)":
        "Sovrasterzo in uscita: molle posteriori più morbide (−1)",
    "Oversteer on exit (traction, no TC): softer differential on power (−1)":
        "Sovrasterzo in uscita (trazione, no TC): differenziale più dolce in power (−1)",
    "Oversteer on exit (traction): softer differential on power (−1)":
        "Sovrasterzo in uscita (trazione): differenziale più dolce in power (−1)",
    "Oversteer on fast exit: more rear wing (+1)":
        "Sovrasterzo in uscita veloce: più ala posteriore (+1)",
    "Oversteer on fast exit: more traction control (+1)":
        "Sovrasterzo in uscita veloce: più controllo di trazione (+1)",
    "Oversteer on fast exit: softer differential on power (−1)":
        "Sovrasterzo in uscita veloce: differenziale più dolce in power (−1)",
    # --- road-car lift-off / pressure remedies ---
    "Understeer on entry: less front pressure (−2)":
        "Sottosterzo in entrata: meno pressione anteriore (−2)",
    "Lift-off oversteer: more rear toe-in (+1)":
        "Sovrasterzo in rilascio: più toe-in posteriore (+1)",
    "Lift-off oversteer: softer rear rebound (−1)":
        "Sovrasterzo in rilascio: estensione posteriore più morbida (−1)",
    "Lift-off oversteer: softer rear anti-roll bar (−1)":
        "Sovrasterzo in rilascio: barra posteriore più morbida (−1)",
    "Lift-off oversteer: brake bias more forward (+1)":
        "Sovrasterzo in rilascio: bias freni più avanti (+1)",
    # --- phase labels ---
    "Pressures": "Pressioni",
    "Mechanical grip": "Grip meccanico",
    "Brake bias": "Bilanciamento freni",
    "Electronics": "Elettronica",
    "Differential": "Differenziale",
    "Traction": "Trazione",
    # --- al-volo lever names (not already covered above) ---
    "Engine map": "Mappa motore",
    "Engine map / ERS": "Mappa motore / ERS",
    "Engine braking": "Freno motore",
}


def tr(text: str, lang: str | None = None) -> str:
    """Translate a fixed engineer string into ``lang`` (EN→IT).

    English is canonical; for any other language a missing entry passes through
    unchanged (a safe fallback). Strings with no Italian variant (e.g. "Aero /
    rake", "TC", "ABS", "Brake migration") simply map to themselves.

    ``lang`` is for callers that know the language of the *request* — the web
    page's own selector. Without it we fall back to ``config.language``, which is
    right for the in-process callers (the coach's voice, the overlay) but wrong
    for a browser that may be set to something else."""
    if (lang or current_language()) == "it":
        return _IT.get(text, text)
    return text


def all_symptoms(window: list[LapStats]) -> set[Symptom]:
    out: set[Symptom] = set()
    for s in window:
        out.update(s.symptom_scores.keys())
    return out


def none_present(window: list[LapStats], owns) -> bool:
    """True if no symptom this phase owns is present across the window."""
    for sym in all_symptoms(window):
        if owns(sym) and _median_score(window, sym) >= _SYMPTOM_THRESH:
            return False
    return True


def remedy(param: str, target, step: int, why: str, tag: str = "BOX"):
    """Factory: returns a builder(symptom, phase) -> ProposedChange.

    The rationale (``why``) and the phase label are translated to the active
    language when the change is built, so the live engineer page / coach follow
    ``config.language``."""
    def build(symptom: Symptom, phase: WorkPhase) -> ProposedChange:
        slots = _SLOTS[target]
        atomics = tuple(AtomicChange(param, s, step) for s in slots)
        return ProposedChange(atomics, tr(why), tr(phase.label), tag, symptom)
    return build


class PressurePhase(WorkPhase):
    """Tyre-pressure phase, parameterised by the class's hot-pressure window.

    Owns no symptom (it gates on the pressures themselves); proposes a click
    nudge on whichever axle is out of the window.
    """

    def __init__(self, target_psi: float, tol: float,
                 key: str = "pressures", label: str = "Pressures",
                 tag: str = "BOX", steps: Steps | None = None) -> None:
        super().__init__(key, label, tag)
        self.target = target_psi
        self.tol = tol
        #: Quanto vale un click di pressione su quest'auto. Senza, la fase non
        #: lo sa — e non propone: i profili la costruiscono cosi', e' il motore
        #: che gliela da' (`RaceEngineer.__init__`).
        self.steps: Steps = steps if steps is not None else UnknownSteps()

    def reconfigure(self, **kw) -> "PressurePhase":
        pw = kw.get("pressure_window") or (self.target, self.tol)
        return PressurePhase(pw[0], pw[1], self.key, self.label, self.tag,
                             kw.get("steps") or self.steps)

    def owns(self, symptom: Symptom) -> bool:
        return False

    def blind(self) -> str:
        """Senza finestra (``core.NO_WINDOW``) non c'e' niente da confrontare.

        E' l'auto che il nome non ci dice cos'e'. La misura c'e', ma dire «27
        psi» senza sapere se per quest'auto sono tanti o pochi non aiuta
        nessuno: si dice che non lo sappiamo, e perche' non si tira a indovinare.
        """
        if self.target is not None:
            return ""
        if current_language() == "it":
            return ("Pressioni: non so che tipo di auto e' questa, quindi non so "
                    "che finestra hanno le sue gomme. Non le tocco: la finestra "
                    "di un'altra categoria sarebbe un numero sbagliato detto con "
                    "sicurezza. Vado avanti col resto.")
        return ("Pressures: I don't know what kind of car this is, so I don't "
                "know its tyre window. I'm leaving them alone: another class's "
                "window would be a wrong number said with confidence. Moving on "
                "to the rest.")

    def _tol(self, psi_per_click: float | None) -> float:
        """La tolleranza che quest'auto puo' davvero raggiungere.

        Con un click da 1 psi una finestra di ±0.4 non si centra: da 21.5 il
        click porta a 22.5, e da li' indietro, per sempre. Entro mezzo click dal
        bersaglio nessun click avvicina, quindi li' si e' arrivati. Su ACC mezzo
        click e' 0.05 psi e non cambia niente.
        """
        return max(self.tol, psi_per_click / 2) if psi_per_click else self.tol

    def _out(self, pressures: dict):
        """Gli assi fuori finestra: (nome, ruote, psi, psi per click o None)."""
        if self.target is None:
            return                            # nessuna finestra: vedi `blind`
        for ax, slots in (("front", FRONT), ("rear", REAR)):
            cur = pressures.get(ax)
            if cur is None:
                continue
            ppc = self.steps.psi_per_click(slots)
            if abs(cur - self.target) > self._tol(ppc):
                yield ax, slots, cur, ppc

    def gate(self, window: list[LapStats]) -> bool:
        recent = [s for s in window if s.pressures_hot]
        if not recent:
            return True                       # no pressure data → can't act, move on
        return next(self._out(recent[-1].pressures_hot), None) is None

    def pressure_by_hand(self, stats: LapStats) -> str:
        """Una pressione fuori finestra su un'auto di cui non sappiamo il passo.

        La misura e' buona lo stesso e il pilota la puo' usare: si dice quanti
        psi mancano, non quanti click, e si dice perche' non la scriviamo noi.
        Vuota quando non c'e' niente da dire.
        """
        for ax, _slots, cur, ppc in self._out(stats.pressures_hot or {}):
            if ppc is not None:
                continue
            lang = current_language()
            gap = self.target - cur
            if lang == "it":
                axis = "anteriore" if ax == "front" else "posteriore"
                return (f"Pressione {axis} {cur:.1f} psi, finestra ~{self.target}: "
                        f"servono circa {gap:+.1f} psi. Non la scrivo io: "
                        f"{self.steps.why(lang)}. Correggila tu dal garage e io "
                        f"rimisuro.")
            return (f"{ax.capitalize()} pressure {cur:.1f} psi, window "
                    f"~{self.target}: it wants about {gap:+.1f} psi. I'm not "
                    f"writing this one: {self.steps.why(lang)}. Change it in the "
                    f"garage yourself and I'll measure again.")
        return ""

    def pressure_remedy(self, stats: LapStats) -> ProposedChange | None:
        if not stats.pressures_hot:
            return None
        for ax, slots, cur, ppc in self._out(stats.pressures_hot):
            if ppc is None:
                continue                      # vedi `pressure_by_hand`
            # Fuori finestra vuol dire piu' di mezzo click dal bersaglio, quindi
            # `wanted` non e' mai zero.
            wanted = round((self.target - cur) / ppc)
            cap = max(1, int(_MAX_PSI_PER_STOP / ppc))
            clicks = max(-cap, min(cap, wanted))
            atomics = tuple(AtomicChange("tyrePressure", s, clicks) for s in slots)
            sign = "+" if clicks > 0 else ""
            # Dove arriva QUESTO passo, che non e' dove vorremmo arrivare appena
            # il taglio morde: a 24.7 psi con finestra 27.5 il passo vale 25.5,
            # e la frase prometteva 27.5. Il pilota che ricarica il setup e
            # rimisura non aveva modo di capire se era andata come doveva.
            reached = cur + clicks * ppc
            short = clicks != wanted
            if current_language() == "it":
                # …e in italiano l'asse ha un nome italiano: la frase diceva
                # "Pressione front", meta' tradotta, nell'unico punto dell'app
                # dove il pilota legge un numero e poi va a girare una manopola.
                axis = "anteriore" if ax == "front" else "posteriore"
                why = (f"Pressione {axis} fuori finestra "
                       f"({cur:.1f}→{reached:.1f} psi, finestra ~{self.target}): "
                       f"{sign}{clicks} click")
                if short:
                    why += " — il massimo per sosta, il resto al prossimo box"
            else:
                why = (f"{ax.capitalize()} pressure out of window "
                       f"({cur:.1f}→{reached:.1f} psi, window ~{self.target}): "
                       f"{sign}{clicks} clicks")
                if short:
                    why += " — the most per stop, the rest next time in"
            return ProposedChange(atomics, why, tr(self.label), "BOX")
        return None
