"""Map a car model id to its engineer class (and thus its :class:`Profile`).

The class drives which engineer profile (GT3 / Formula / Road) and which
dedicated UI the driver gets. Detection is from the AC/ACC car model id (e.g.
``mclaren_720s_gt3_evo`` → GT3, ``f1_1990_mclaren`` → Formula), with an explicit
table for the cars whose id says nothing — or says the wrong thing.

**Il nome non basta, e questo modulo lo dice in due modi.**

:func:`known_class` risponde solo dove il nome lo dice davvero, e altrimenti
``None``: *non lo sappiamo*. E' quella che usa chi, sbagliando classe, scrive un
numero sbagliato — la finestra pressioni dell'Ingegnere (``pressures.py``).

:func:`classify` risponde sempre, e dove non si sa risponde ``ROAD``. E' quella
che usa il coach per le sue soglie di guida (wheelspin, trail-brake,
sottosterzo), dove una soglia ci vuole comunque. ``ROAD`` li' non vuol dire «e'
una stradale»: vuol dire «la taratura piu' prudente delle tre», ed e' quella che
queste auto avevano gia'.

Riguardato il 13/10 sulle 249 auto installate col ``ui_car.json`` del gioco a
fare da controprova: senza un pezzo di nome riconosciuto finivano «stradali» le
F1 (``ks_ferrari_f2004``, tutta la griglia ``gp_2000_*``), le LMP1, una GT3
(``ks_audi_r8_lms``) e la ``lamborghini_huracan_st`` di ACC — 189 nomi su 252
fra auto installate, cartelle setup e archivio giri.
Le auto di AC sono mod: l'elenco non si finisce, quindi la cura e' il default.
"""

from __future__ import annotations

import re
from enum import Enum

from .core import Profile
from .profiles import FORMULA_PROFILE, GT3_PROFILE, ROAD_PROFILE


class CarClass(Enum):
    GT3 = "GT3"
    FORMULA = "Formula"
    ROAD = "Road"


# I nomi si leggono a **pezzi** (separati da ``_`` o ``-``), non a sottostringhe.
# A sottostringhe ``ks_ford_gt40`` era una GT3 (contiene ``gt4``) e la McLaren F1
# GTR una monoposto (contiene ``_f1``).

# Pezzi che dicono «monoposto» ovunque stiano nel nome.
_FORMULA_TOKENS = {"f3000", "312t", "98t"}
# …e quelli che lo dicono solo **in testa**: ``f1_1990_mclaren`` e' una F1,
# ``ks_mclaren_f1_gtr`` e' una McLaren che di modello fa F1.
_FORMULA_LEADING = {"f1", "f2", "f3"}
# Pezzi piu' lunghi di un nome, o attaccati ad altro (``tatuusfa1``).
_FORMULA_SUBSTRINGS = ("formula", "indycar", "open_wheel", "tatuus", "dallara_f",
                       "lotus_exos")
# I pacchetti stagione di F1 si chiamano ``gp_<anno>_<telaio>``. Prima c'erano
# solo 2023, 2024 e 2025, scritti uno per uno: la griglia del 2000 (11 auto
# installate, tutte ``singleseater`` per il gioco) restava fuori.
_SEASON_PACK = re.compile(r"^gp_(19|20)\d\d_")

# GT racing classes (gt4/gt2/gte) ride along with the GT3 profile as the closest
# fit until they get their own.
_GT_TOKENS = {"gt3", "gt4", "gt2", "gte"}

# Cars whose id gives no hint — set the class explicitly. Solo F1 con le ali,
# cioe' la famiglia su cui la classe Formula e' stata tarata: una F1 del 1967
# (``ks_ferrari_312_67``) e' una monoposto ma non e' quella macchina, e resta
# fra quelle che non sappiamo.
_OVERRIDES: dict[str, CarClass] = {
    "ks_ferrari_f138": CarClass.FORMULA,
    "ks_ferrari_f2004": CarClass.FORMULA,
    "ks_ferrari_sf15t": CarClass.FORMULA,
    "ks_ferrari_sf70h": CarClass.FORMULA,
}
# La MP4/4 del 1988 esiste in piu' varianti (``_r02``, ``_r04``, …).
_OVERRIDE_PREFIXES: dict[str, CarClass] = {
    "vrc_1988_mclaren_mp4-4": CarClass.FORMULA,
}

# Stradali il cui **allestimento** si chiama come una categoria da corsa. Per il
# gioco sono ``class=street``; il nome da solo le manderebbe sulla slick.
_NOT_WHAT_THE_NAME_SAYS = {
    "ks_porsche_911_gt3_rs",
    "ks_porsche_cayman_gt4_std",
    "lotus_evora_gte",
    "lotus_evora_gte_carbon",
}

_PROFILES: dict[CarClass, Profile] = {
    CarClass.GT3: GT3_PROFILE,
    CarClass.FORMULA: FORMULA_PROFILE,
    CarClass.ROAD: ROAD_PROFILE,
}


def known_class(car_model: str) -> CarClass | None:
    """La classe, **solo se il nome la dice**. Altrimenti ``None``.

    ``None`` e' una risposta e chi la riceve la deve trattare da risposta: non
    c'e' una classe «di solito giusta» da metterci al posto. Non restituisce mai
    ``ROAD``: nessun nome dice «stradale», lo dice solo l'assenza di tutto il
    resto, che e' esattamente l'inferenza che questo modulo ha smesso di fare.
    """
    key = (car_model or "").strip().lower()
    if key in _NOT_WHAT_THE_NAME_SAYS:
        return None
    if key in _OVERRIDES:
        return _OVERRIDES[key]
    for prefix, car_class in _OVERRIDE_PREFIXES.items():
        if key.startswith(prefix):
            return car_class
    tokens = re.split(r"[_\-]+", key)
    if (tokens[0] in _FORMULA_LEADING
            or _FORMULA_TOKENS.intersection(tokens)
            or any(m in key for m in _FORMULA_SUBSTRINGS)
            or _SEASON_PACK.match(key)):
        return CarClass.FORMULA
    if _GT_TOKENS.intersection(tokens):
        return CarClass.GT3
    return None


def classify(car_model: str) -> CarClass:
    """La classe per le **soglie del coach**: risponde sempre.

    Dove il nome non dice niente risponde ``ROAD``, com'era. Non usarla per
    decidere un numero che finisce in un setup: per quello c'e'
    :func:`known_class`, che sa dire «non lo so».
    """
    return known_class(car_model) or CarClass.ROAD


def profile_for(car_class: CarClass) -> Profile:
    return _PROFILES[car_class]


def profile_for_car(car_model: str) -> Profile:
    """Convenience: model id → its engineer Profile."""
    return profile_for(classify(car_model))
