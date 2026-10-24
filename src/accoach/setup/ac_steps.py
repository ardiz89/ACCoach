"""Quanto vale un click su un'auto di Assetto Corsa: lo dice l'auto, non noi.

Un setup salvato di AC (``.ini``) porta solo ``VALUE=<intero>`` e non dice in
che unita' e'. Lo dice il ``data/setup.ini`` **dell'auto**, sezione per sezione:

    [PRESSURE_LF]
    SHOW_CLICKS=0
    MIN=15
    MAX=40
    STEP=1

Misurato il 13/10 sulle 12 auto installate che hanno quel file in chiaro,
contro i setup salvati di 8 di loro (141 valori):

* ``SHOW_CLICKS=0`` — ``VALUE`` e' la grandezza stessa (psi, N/m, %) e un click
  del gioco la muove di ``STEP``. 69 valori su 87 stanno sulla griglia
  ``MIN + k*STEP``; dei 18 che non ci stanno, 12 sono camber (``MIN``/``MAX``
  si leggono come gradi e ``VALUE`` come decimi di grado) e 6 sono valori di
  una mod fuori dalla sua stessa griglia. Che anche li' un click valga ``STEP``
  e' la lettura coerente col resto, **non** una misura: un valore salvato da
  solo non dice di quanto si muove.
* ``SHOW_CLICKS=1`` o ``2`` — ``VALUE`` e' il **numero** del click, e un click
  vale 1 qualunque sia ``STEP``. 54 valori su 54, e 48 di questi non possono
  essere letti in nessun altro modo (uno smorzatore con ``MIN=100 STEP=800``
  salvato a ``6``).

La pressione e' ``SHOW_CLICKS=0`` su tutte e 12, con ``STEP=1`` su 11 e
``STEP=2`` su una (``seat_leon_cupra_r``): un click vale un psi o due, mai il
decimo di psi di ACC.

**Cosa NON si legge, di proposito.** Quasi tutte le auto (237 su 249 su questa
macchina, tutte quelle di Kunos) hanno i dati impacchettati in ``data.acd`` e
nessuna cartella ``data``. Li' il passo non lo sappiamo, e questo modulo
risponde «non lo so» invece di supporre ``STEP=1`` dalle dodici che ha visto.
Quando ci sono **tutt'e due**, cartella e pacchetto, risponde ancora «non lo
so»: non abbiamo mai verificato quale dei due il gioco carichi, e la cartella
potrebbe essere un avanzo di chi ha fatto la mod.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .. import trackedges

#: Perche' il passo non si sa. Sono codici, non frasi: le frasi le scrive chi
#: parla al pilota (``engineer/steps.py``), nella sua lingua.
NO_GAME = "no_game"        # AC non e' installato dove sappiamo cercarlo
NO_CAR = "no_car"          # l'auto non e' fra quelle installate
PACKED = "packed"          # solo data.acd
AMBIGUOUS = "ambiguous"    # data.acd E cartella data: quale vale?
NO_FILE = "no_file"        # ne' l'uno ne' l'altra


@dataclass(frozen=True)
class SectionStep:
    """Come una sezione del setup risponde a un click del gioco."""

    #: Di quanto si muove ``VALUE`` nel file per UN click.
    units: int
    #: Il ``STEP`` dichiarato, nell'unita' della sezione (psi per la pressione).
    step: float
    #: True quando ``VALUE`` e' la grandezza stessa e non il numero del click.
    physical: bool


def cars_dir() -> Path | None:
    """``content/cars`` di Assetto Corsa, o None se il gioco qui non c'e'.

    Passa da ``trackedges.tracks_dir`` invece di cercare Steam una seconda
    volta: e' li' che ``HONE_NO_AC=1`` finge una macchina senza il gioco, e una
    seconda strada per arrivarci sarebbe una strada che quel finto non chiude.
    """
    tracks = trackedges.tracks_dir()
    if tracks is None:
        return None
    cars = tracks.parent / "cars"
    return cars if cars.is_dir() else None


def _car_folder(root: Path, car_model: str) -> Path | None:
    # Come `spline_path`: il nome dell'auto viene dal gioco, non puo' risalire.
    if any(ch in car_model for ch in "/\\:") or car_model in (".", ".."):
        return None
    folder = root / car_model
    if folder.is_dir():
        return folder
    # Il gioco non riporta sempre il nome con le stesse maiuscole della cartella.
    low = car_model.lower()
    return next((p for p in root.iterdir()
                 if p.is_dir() and p.name.lower() == low), None)


def parse(text: str) -> dict[str, SectionStep]:
    """Le sezioni di un ``data/setup.ini`` di cui si sa leggere il passo.

    Una sezione che non dichiara ``STEP`` e ``SHOW_CLICKS`` in un modo che
    abbiamo gia' visto resta fuori, e per chi chiede e' «non lo so»: un
    ``SHOW_CLICKS=3`` o uno ``STEP=0.5`` su un ``VALUE`` intero non sono mai
    comparsi, e non e' qui che si decide cosa vorrebbero dire.
    """
    raw: dict[str, dict[str, str]] = {}
    cur: dict[str, str] | None = None
    for line in text.splitlines():
        s = line.split(";", 1)[0].split("//", 1)[0].strip()
        if s.startswith("[") and s.endswith("]"):
            cur = raw.setdefault(s[1:-1].strip(), {})
        elif "=" in s and cur is not None:
            k, v = s.split("=", 1)
            cur[k.strip().upper()] = v.strip()

    out: dict[str, SectionStep] = {}
    for name, kv in raw.items():
        try:
            step = float(kv["STEP"])
            show = int(kv["SHOW_CLICKS"])
        except (KeyError, ValueError):
            continue
        if step <= 0:
            continue
        if show == 0:
            # VALUE nel file e' un intero: un passo che non lo e' non si scrive.
            if step != int(step):
                continue
            out[name] = SectionStep(units=int(step), step=step, physical=True)
        elif show in (1, 2):
            out[name] = SectionStep(units=1, step=step, physical=False)
    return out


def car_steps(car_model: str) -> tuple[dict[str, SectionStep] | None, str]:
    """``(sezioni, "")`` per un'auto leggibile, ``(None, perche')`` altrimenti."""
    root = cars_dir()
    if root is None:
        return None, NO_GAME
    folder = _car_folder(root, car_model) if car_model else None
    if folder is None:
        return None, NO_CAR
    clear = folder / "data" / "setup.ini"
    packed = (folder / "data.acd").is_file()
    if not clear.is_file():
        return None, PACKED if packed else NO_FILE
    if packed:
        return None, AMBIGUOUS
    try:
        text = clear.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, NO_FILE
    return parse(text), ""
