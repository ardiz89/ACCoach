"""Quanto vale un click, per quest'auto su questo gioco — o che non lo sappiamo.

L'Ingegnere ragiona in click e scrive numeri in un file. Fra le due cose c'e'
una conversione, e fino al 13/10 non c'era: valeva la regola di ACC (un click di
pressione = 0.1 psi, un click = +1 nel file) per tutti. Su Assetto Corsa il file
porta psi interi, quindi «−8 click» per togliere 0.8 psi ne toglieva otto:
riprodotto sui giri veri di Spa con la SF25, 15 psi a freddo diventavano 7.

Tre risposte possibili, e la terza e' una risposta:

* :class:`AccSteps` — il formato di ACC e' fatto di click, per definizione;
* :class:`AcSteps` — lo dichiara l'auto (vedi ``setup/ac_steps.py``);
* «non lo so» (``None``), col perche'. Chi riceve ``None`` **non scrive**: un
  numero sbagliato in un setup lo si scopre in pista, alla prima staccata.
"""

from __future__ import annotations

from ..setup import ac_steps
from ..setup.ac_format import AC_PARAMS
from ..setup.acc_format import SETUP_PARAMS

_PRESSURE = "tyrePressure"

#: Leve di AC di cui sappiamo il passo ma non il verso (vedi ``AcSteps.units``).
_VERSO_IGNOTO = frozenset({"toe"})

# Perche' non scrivo, detto al pilota. Una frase che regge dopo «Non lo scrivo,
# perché» e prima di un punto.
_WHY = {
    "no_game_id": {
        "en": "nobody told me which game this is, so I don't know what a click "
              "is worth",
        "it": "nessuno mi ha detto che gioco è, quindi non so quanto vale un "
              "click",
    },
    ac_steps.NO_GAME: {
        "en": "I can't find Assetto Corsa's car folder, which is where a car "
              "says what a click is worth",
        "it": "non trovo la cartella delle auto di Assetto Corsa, che è dove "
              "un'auto dichiara quanto vale un click",
    },
    ac_steps.NO_CAR: {
        "en": "I can't find this car among the installed ones, so I don't know "
              "what a click is worth on it",
        "it": "non trovo quest'auto fra quelle installate, quindi non so quanto "
              "vale un suo click",
    },
    ac_steps.PACKED: {
        "en": "this car's data is packed (data.acd) and I can't read what a "
              "click is worth on it",
        "it": "i dati di quest'auto sono impacchettati (data.acd) e non posso "
              "leggere quanto vale un suo click",
    },
    ac_steps.AMBIGUOUS: {
        "en": "this car has both a data folder and a data.acd, and I don't know "
              "which one the game is using",
        "it": "quest'auto ha sia la cartella data sia data.acd, e non so quale "
              "dei due il gioco stia usando",
    },
    ac_steps.NO_FILE: {
        "en": "this car has no setup.ini saying what a click is worth",
        "it": "quest'auto non ha un setup.ini che dica quanto vale un click",
    },
    "toe_geometry": {
        "en": "on Assetto Corsa which way a toe click goes depends on each "
              "car's suspension",
        "it": "su Assetto Corsa il verso di un click di convergenza dipende "
              "dalla sospensione di ogni auto",
    },
    "no_section": {
        "en": "this car doesn't declare a step for that setting",
        "it": "quest'auto non dichiara un passo per quella regolazione",
    },
}


class Steps:
    """Il contratto. Di suo non sa niente, e lo dice."""

    #: Codice del perche' non si sa (chiave di ``_WHY``).
    reason = "no_game_id"

    def units(self, param: str, slot: int | None) -> int | None:
        """Di quanto si muove il numero nel file per UN click, o None."""
        return None

    def psi_per_click(self, slots: tuple) -> float | None:
        """Quanti psi vale un click di pressione su queste ruote, o None."""
        return None

    def why(self, lang: str, param: str | None = None) -> str:
        """Perche' non si scrive; ``param`` e' la leva bloccata, se si sa."""
        entry = _WHY.get(self.reason) or _WHY["no_section"]
        return entry.get(lang) or entry["en"]


class UnknownSteps(Steps):
    """Non sappiamo che gioco e': non si scrive."""


class AccSteps(Steps):
    """ACC: ogni valore del file e' gia' un numero di click."""

    reason = ""

    def units(self, param: str, slot: int | None) -> int | None:
        return 1

    def psi_per_click(self, slots: tuple) -> float | None:
        # Dal registro del formato, non da una seconda costante: la copia che
        # stava in `profiles/_common.py` e' il difetto che questo modulo cura.
        spec = next(s for s in SETUP_PARAMS if s.key == _PRESSURE)
        return spec.step


class AcSteps(Steps):
    """Assetto Corsa: lo dichiara l'auto, sezione per sezione."""

    def __init__(self, car_model: str) -> None:
        self._sections, self.reason = ac_steps.car_steps(car_model)
        if self._sections is not None:
            # L'auto e' leggibile: se manca qualcosa, manca quella sezione.
            self.reason = "no_section"
        self._specs = {s.key: s for s in AC_PARAMS}

    def _section(self, param: str, slot: int | None):
        spec = self._specs.get(param)
        if spec is None or self._sections is None:
            return None
        i = 0 if slot is None else slot
        if not 0 <= i < len(spec.sections):
            return None
        return self._sections.get(spec.sections[i])

    def units(self, param: str, slot: int | None) -> int | None:
        # Il passo c'e', il verso no. Misurato il 23/10 sulla SF25: dieci click
        # in piu' abbassano la convergenza letta davanti e la alzano dietro. Nel
        # file e' la lunghezza del braccio dello sterzo, e dove sta il braccio
        # lo decide la sospensione dell'auto: un click scritto potrebbe fare il
        # contrario di quello che la frase promette.
        if param in _VERSO_IGNOTO:
            return None
        sec = self._section(param, slot)
        return sec.units if sec is not None else None

    def why(self, lang: str, param: str | None = None) -> str:
        if param in _VERSO_IGNOTO and self._sections is not None:
            entry = _WHY["toe_geometry"]
            return entry.get(lang) or entry["en"]
        return super().why(lang, param)

    def psi_per_click(self, slots: tuple) -> float | None:
        steps = set()
        for slot in slots:
            sec = self._section(_PRESSURE, slot)
            # Una pressione salvata come numero di click non l'abbiamo mai
            # vista (0 auto su 12): non e' qui che si scopre come si legge.
            if sec is None or not sec.physical:
                return None
            steps.add(sec.step)
        # Due ruote dello stesso asse con passi diversi: un solo numero di click
        # non le muoverebbe uguale.
        return steps.pop() if len(steps) == 1 else None


def steps_for(car_model: str, is_acc: bool | None) -> Steps:
    """Il passo per quest'auto. ``is_acc=None`` vuol dire «non so che gioco e'»."""
    if is_acc is None:
        return UnknownSteps()
    return AccSteps() if is_acc else AcSteps(car_model)
