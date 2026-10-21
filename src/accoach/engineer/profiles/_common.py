"""Shared building blocks for the per-class engineer profiles.

Symptom/phase aliases, the remedy-builder factory, and a generic tyre-pressure
phase parameterised by the class's hot-pressure window.
"""

from __future__ import annotations

from ...i18n import current_language
from ...textfmt import fmt_num
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

# La finestra a caldo della GT3 di ACC all'asciutto: 26.0-27.0 psi.
#
# Versione e fonte, perche' la patch che la invalida non ci avvisera':
#   - fino al 13/10/2026 qui c'era (27.5, 0.7), cioe' 26.8-28.2. Era centrata
#     sul 27.3-27.9 di Aris (Kunos, nov 2020, ACC 1.6);
#   - col modello gomme della 1.9 l'ottimo e' sceso. Kunos non ha pubblicato un
#     numero nuovo; la fonte e' la community, Coach Dave, che nella stessa
#     pagina scrive 26.0-27.0, 26.0-27.2 e 26.5-27.5 (COACHING-PRO.md, §6).
#     Le tre concordano su una cosa sola: 28 psi non e' piu' dentro.
# Quindi il numero NON e' misurato da noi ed e' il meno solido dei tre che
# questo profilo usa. Scelto col pilota il 13/10 perche' con quello vecchio
# l'Ingegnere aveva portato gli anteriori della 720S da 24.7 a 27.1 e a 26.6
# chiedeva ancora +8 click: spingeva verso l'alto una gomma che per ogni
# fonte post-1.9 era gia' a posto. La striscia contesa e' 27.0-27.5: li' oggi
# diciamo «cala», ed e' il primo posto da guardare se un verdetto non torna.
#
# Il nome e' pubblico perche' il numero aveva QUATTRO copie (`pressures.py`, il
# profilo GT3, `coaching/tuning.py`, `coaching/pressure.py`) e una copia di una
# regola e' un difetto che aspetta l'altra meta'. Ora si legge da qui: sta in
# questo modulo e non in `pressures.py` perche' quello importa i profili, e
# sarebbe un giro.
GT3_DRY_WINDOW: tuple[float, float] = (26.5, 0.5)

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
# look them up here. Strings are FIXED (the click count, «di 1 click», is part of
# the phrase), so a static map suffices — no templating needed. The setup param
# keys, AV/BOX tags and Symptom enums are technical identifiers and stay as-is.
#
# Ogni rimedio e' UNA frase, il sintomo e poi l'azione legati da «quindi» / «so»:
# due frasi avrebbero ripetuto «Hai sottosterzo in ingresso.» sotto dieci
# rimedi, e la stessa frase in dieci posti e' quello che il pilota ha bocciato.
# L'azione da sola (`_lever`) e' quella che si cita dentro un'altra frase.
_IT: dict[str, str] = {
    # --- remedy rationales (GT3 + Formula + Road) ---
    # Una frase sola: il sintomo, poi «quindi» e l'azione (vedi `_lever`).
    "The car understeers on entry to slow corners, so soften the front anti-roll bar by 1 click.":
        "Hai sottosterzo in ingresso alle curve lente, quindi ammorbidisci la barra antirollio anteriore di 1 click.",
    "The car understeers on entry, so add 1 click of front toe-out.":
        "Hai sottosterzo in ingresso, quindi aumenta il toe-out anteriore di 1 click.",
    "The car understeers on entry, so move the brake bias 1 click rearward.":
        "Hai sottosterzo in ingresso, quindi sposta il bilanciamento freni indietro di 1 click.",
    "The car understeers on entry, so soften the front anti-roll bar by 1 click.":
        "Hai sottosterzo in ingresso, quindi ammorbidisci la barra antirollio anteriore di 1 click.",
    "The car understeers on entry to fast corners, so raise the rear by 2 clicks for more rake.":
        "Hai sottosterzo in ingresso alle curve veloci, quindi alza il posteriore di 2 click per avere più rake.",
    "The car understeers on entry to fast corners, so add 1 click of front splitter.":
        "Hai sottosterzo in ingresso alle curve veloci, quindi aumenta lo splitter anteriore di 1 click.",
    "The car understeers on entry to fast corners, so soften the front anti-roll bar by 1 click.":
        "Hai sottosterzo in ingresso alle curve veloci, quindi ammorbidisci la barra antirollio anteriore di 1 click.",
    "The car understeers on entry to fast corners, so add 1 click of front wing.":
        "Hai sottosterzo in ingresso alle curve veloci, quindi aumenta l'ala anteriore di 1 click.",
    "The car understeers on entry to fast corners, so take 1 click of rear wing off.":
        "Hai sottosterzo in ingresso alle curve veloci, quindi togli 1 click di ala posteriore.",
    "The car understeers mid-corner in slow corners, so take 1 click of differential preload off.":
        "Hai sottosterzo in percorrenza nelle curve lente, quindi togli 1 click di precarico al differenziale.",
    "The car understeers mid-corner, so soften the front anti-roll bar by 1 click.":
        "Hai sottosterzo in percorrenza, quindi ammorbidisci la barra antirollio anteriore di 1 click.",
    "The car understeers mid-corner, so soften the front springs by 1 click.":
        "Hai sottosterzo in percorrenza, quindi ammorbidisci le molle anteriori di 1 click.",
    "The car understeers mid-corner, so add 1 click of negative front camber.":
        "Hai sottosterzo in percorrenza, quindi aumenta il camber negativo anteriore di 1 click.",
    "The car understeers mid-corner in fast corners, so take 1 click of rear wing off.":
        "Hai sottosterzo in percorrenza nelle curve veloci, quindi togli 1 click di ala posteriore.",
    "The car understeers mid-corner in fast corners, so add 1 click of front splitter.":
        "Hai sottosterzo in percorrenza nelle curve veloci, quindi aumenta lo splitter anteriore di 1 click.",
    "The car understeers mid-corner in fast corners, so raise the rear by 1 click for more rake.":
        "Hai sottosterzo in percorrenza nelle curve veloci, quindi alza il posteriore di 1 click per avere più rake.",
    "The car understeers mid-corner in fast corners, so add 1 click of front wing.":
        "Hai sottosterzo in percorrenza nelle curve veloci, quindi aumenta l'ala anteriore di 1 click.",
    "The car understeers on exit from slow corners under power, so take 1 click of differential preload off.":
        "Hai sottosterzo in uscita dalle curve lente quando dai gas, quindi togli 1 click di precarico al differenziale.",
    "The car understeers on exit, so soften the rear anti-roll bar by 1 click.":
        "Hai sottosterzo in uscita, quindi ammorbidisci la barra antirollio posteriore di 1 click.",
    "The car understeers on exit under power, so take 1 click of power locking off the differential.":
        "Hai sottosterzo in uscita quando dai gas, quindi togli 1 click di bloccaggio al differenziale in accelerazione.",
    "The car understeers on exit from fast corners, so take 1 click of rear wing off.":
        "Hai sottosterzo in uscita dalle curve veloci, quindi togli 1 click di ala posteriore.",
    "The car understeers on exit from fast corners, so add 1 click of splitter.":
        "Hai sottosterzo in uscita dalle curve veloci, quindi aumenta lo splitter di 1 click.",
    "The car understeers on exit from fast corners, so add 1 click of front wing.":
        "Hai sottosterzo in uscita dalle curve veloci, quindi aumenta l'ala anteriore di 1 click.",
    "The car oversteers on entry to slow corners, so move the brake bias 1 click forward.":
        "Hai sovrasterzo in ingresso alle curve lente, quindi sposta il bilanciamento freni in avanti di 1 click.",
    "The car oversteers on entry, so move the brake bias 1 click forward.":
        "Hai sovrasterzo in ingresso, quindi sposta il bilanciamento freni in avanti di 1 click.",
    "The car oversteers on entry, so soften the rear anti-roll bar by 1 click.":
        "Hai sovrasterzo in ingresso, quindi ammorbidisci la barra antirollio posteriore di 1 click.",
    "The car oversteers on entry, so add 1 click of rear toe-in.":
        "Hai sovrasterzo in ingresso, quindi aumenta il toe-in posteriore di 1 click.",
    "The car oversteers when you lift off, so add 1 click of coast locking to the differential.":
        "Hai sovrasterzo quando alzi il piede, quindi aggiungi 1 click di bloccaggio al differenziale in rilascio.",
    "The car oversteers on entry to fast corners, so add 1 click of rear wing.":
        "Hai sovrasterzo in ingresso alle curve veloci, quindi aumenta l'ala posteriore di 1 click.",
    "The car oversteers on entry to fast corners, so lower the rear by 2 clicks.":
        "Hai sovrasterzo in ingresso alle curve veloci, quindi abbassa il posteriore di 2 click.",
    "The car oversteers on entry to fast corners, so soften the rear anti-roll bar by 1 click.":
        "Hai sovrasterzo in ingresso alle curve veloci, quindi ammorbidisci la barra antirollio posteriore di 1 click.",
    "The car oversteers mid-corner in slow corners, so soften the rear anti-roll bar by 1 click.":
        "Hai sovrasterzo in percorrenza nelle curve lente, quindi ammorbidisci la barra antirollio posteriore di 1 click.",
    "The car oversteers mid-corner, so add 1 click of differential preload.":
        "Hai sovrasterzo in percorrenza, quindi aumenta il precarico del differenziale di 1 click.",
    "The car oversteers mid-corner, so soften the rear anti-roll bar by 1 click.":
        "Hai sovrasterzo in percorrenza, quindi ammorbidisci la barra antirollio posteriore di 1 click.",
    "The car oversteers mid-corner, so add 1 click of rear toe-in.":
        "Hai sovrasterzo in percorrenza, quindi aumenta il toe-in posteriore di 1 click.",
    "The car oversteers mid-corner in fast corners, so add 1 click of rear wing.":
        "Hai sovrasterzo in percorrenza nelle curve veloci, quindi aumenta l'ala posteriore di 1 click.",
    "The car oversteers mid-corner in fast corners, so soften the rear anti-roll bar by 1 click.":
        "Hai sovrasterzo in percorrenza nelle curve veloci, quindi ammorbidisci la barra antirollio posteriore di 1 click.",
    "The car oversteers on exit under power, so add 1 click of traction control.":
        "Hai sovrasterzo in uscita quando dai gas, quindi aumenta il controllo di trazione di 1 click.",
    "The car oversteers on exit, so soften the rear anti-roll bar by 1 click.":
        "Hai sovrasterzo in uscita, quindi ammorbidisci la barra antirollio posteriore di 1 click.",
    "The car oversteers on exit, so soften the rear springs by 1 click.":
        "Hai sovrasterzo in uscita, quindi ammorbidisci le molle posteriori di 1 click.",
    "With no TC, the car oversteers on exit under power, so take 1 click of power locking off the differential.":
        "Senza TC hai sovrasterzo in uscita quando dai gas, quindi togli 1 click di bloccaggio al differenziale in accelerazione.",
    "The car oversteers on exit under power, so take 1 click of power locking off the differential.":
        "Hai sovrasterzo in uscita quando dai gas, quindi togli 1 click di bloccaggio al differenziale in accelerazione.",
    "The car oversteers on exit from fast corners, so add 1 click of rear wing.":
        "Hai sovrasterzo in uscita dalle curve veloci, quindi aumenta l'ala posteriore di 1 click.",
    "The car oversteers on exit from fast corners, so add 1 click of traction control.":
        "Hai sovrasterzo in uscita dalle curve veloci, quindi aumenta il controllo di trazione di 1 click.",
    "The car oversteers on exit from fast corners, so take 1 click of power locking off the differential.":
        "Hai sovrasterzo in uscita dalle curve veloci, quindi togli 1 click di bloccaggio al differenziale in accelerazione.",
    "The car understeers on entry, so take 2 clicks of front tyre pressure off.":
        "Hai sottosterzo in ingresso, quindi togli 2 click di pressione alle gomme anteriori.",
    "The car oversteers when you lift off, so add 1 click of rear toe-in.":
        "Hai sovrasterzo quando alzi il piede, quindi aumenta il toe-in posteriore di 1 click.",
    "The car oversteers when you lift off, so soften the rear rebound by 1 click.":
        "Hai sovrasterzo quando alzi il piede, quindi ammorbidisci l'estensione posteriore di 1 click.",
    "The car oversteers when you lift off, so soften the rear anti-roll bar by 1 click.":
        "Hai sovrasterzo quando alzi il piede, quindi ammorbidisci la barra antirollio posteriore di 1 click.",
    "The car oversteers when you lift off, so move the brake bias 1 click forward.":
        "Hai sovrasterzo quando alzi il piede, quindi sposta il bilanciamento freni in avanti di 1 click.",
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


#: Quello che separa il sintomo dall'azione in una frase di rimedio.
_THEN = (", quindi ", ", so ")


def _lever(text: str) -> str:
    """L'azione di una frase di rimedio, senza il sintomo e senza il punto.

    «Hai sottosterzo in ingresso, quindi ammorbidisci la barra…» → «Ammorbidisci
    la barra…». Una frase senza il legame torna intera: si cita lei.
    """
    for sep in _THEN:
        if sep in text:
            act = text.split(sep, 1)[1].rstrip(". ")
            return act[:1].upper() + act[1:]
    return text.rstrip(". ")


def remedy(param: str, target, step: int, why: str, tag: str = "BOX"):
    """Factory: returns a builder(symptom, phase) -> ProposedChange.

    The rationale (``why``) and the phase label are translated to the active
    language when the change is built, so the live engineer page / coach follow
    ``config.language``."""
    def build(symptom: Symptom, phase: WorkPhase) -> ProposedChange:
        slots = _SLOTS[target]
        atomics = tuple(AtomicChange(param, s, step) for s in slots)
        text = tr(why)
        return ProposedChange(atomics, text, tr(phase.label), tag, symptom,
                              lever=_lever(text))
    return build


def _psi(v: float, lang: str) -> str:
    return fmt_num(v, 1, lang, "psi")



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
            return ("Non so che tipo di auto è questa, quindi non conosco la "
                    "finestra delle sue gomme. Le pressioni non le tocco, perché "
                    "la finestra di un'altra categoria sarebbe un numero sbagliato "
                    "detto con sicurezza. Vado avanti col resto.")
        return ("I don't know what kind of car this is, so I don't know its tyre "
                "window. I'm leaving the pressures alone, because another class's "
                "window would be a wrong number said with confidence. I'm moving "
                "on to the rest.")

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
            gap = fmt_num(self.target - cur, 1, lang, "psi")
            gap = gap if gap.startswith("−") else "+" + gap
            now, window = _psi(cur, lang), _psi(self.target, lang)
            why = self.steps.why(lang)
            if lang == "it":
                axis = "anteriore" if ax == "front" else "posteriore"
                return (f"La pressione {axis} è {now}, fuori dalla finestra di "
                        f"circa {window}. Servono circa {gap}. Non la scrivo io, "
                        f"perché {why}. Correggila tu dal garage e io rimisuro.")
            return (f"{ax.capitalize()} pressure is {now}, outside the window of "
                    f"about {window}. It wants about {gap}. I'm not writing this "
                    f"one, because {why}. Change it in the garage yourself and "
                    f"I'll measure again.")
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
            # Dove arriva QUESTO passo, che non e' dove vorremmo arrivare appena
            # il taglio morde: a 24.7 psi con finestra 27.5 il passo vale 25.5,
            # e la frase prometteva 27.5. Il pilota che ricarica il setup e
            # rimisura non aveva modo di capire se era andata come doveva.
            reached = cur + clicks * ppc
            short = clicks != wanted
            lang = current_language()
            n = fmt_num(abs(clicks), 0, lang)
            now, to = _psi(cur, lang), _psi(reached, lang)
            window = _psi(self.target, lang)
            up = clicks > 0
            if lang == "it":
                # …e in italiano l'asse ha un nome italiano: la frase diceva
                # "Pressione front", meta' tradotta, nell'unico punto dell'app
                # dove il pilota legge un numero e poi va a girare una manopola.
                axis = "anteriore" if ax == "front" else "posteriore"
                act = (f"aggiungi {n} click e sali a {to}" if up
                       else f"togli {n} click e scendi a {to}")
                why = (f"La pressione {axis} è {now}, fuori dalla finestra di "
                       f"circa {window}, quindi {act}.")
                if short:
                    why += " È il massimo per una sosta, il resto al prossimo rientro."
                lever = f"{n} click {'in più' if up else 'in meno'} alla pressione {axis}"
            else:
                word = "click" if abs(clicks) == 1 else "clicks"
                act = (f"add {n} {word} to bring it up to {to}" if up
                       else f"take {n} {word} off to bring it down to {to}")
                why = (f"{ax.capitalize()} pressure is {now}, outside the window "
                       f"of about {window}, so {act}.")
                if short:
                    why += " That's the most for one stop, the rest next time in."
                lever = (f"{n} {'more' if up else 'fewer'} {word} of {ax} "
                         f"pressure")
            return ProposedChange(atomics, why, tr(self.label), "BOX", lever=lever)
        return None
