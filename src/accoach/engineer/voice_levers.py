"""Le leve dell'Ingegnere come le dice la voce: l'azione, senza i click.

Il pilota ha deciso (22/10) che la voce non dice i numeri di dettaglio: quanti
click li vede sulla pagina Ingegnere e nel setup quando entra ai box. Ogni frase
italiana detta in pista diventa un WAV registrato una volta; una leva senza la
sua frase cadrebbe sulla voce di Windows, quindi le frasi stanno in una tabella
chiusa che il catalogo delle frasi (`all_voice_levers`) puo' leggere.

Le frasi sono scritte a mano e non ricavate dalla leva dello schermo togliendo
il numero: il numero sta in mezzo alla frase, e toglierlo a macchina da'
«Togli di ala posteriore». La chiave e' quello che la modifica FA (parametro,
asse, segno del passo), non il testo: cosi' una frase non puo' dire una
direzione diversa dai click che la pagina prepara.
"""

from __future__ import annotations

from .core import ALL, FRONT, REAR, ProposedChange

#: (parametro, asse, segno del passo) → la frase. L'asse e' "front"/"rear"/"all"
#: per le leve per ruota, None per quelle scalari (barre, ala, ripartitore).
#: Una riga per ogni leva che un profilo puo' proporre (`profiles/gt3.py`,
#: `formula.py`, `road.py`) e per le quattro della pressione
#: (`PressurePhase.pressure_remedy`). Manca la direzione che nessun profilo
#: propone (irrigidire una barra): senza frase vera, meglio nessuna.
_LEVERS: dict[tuple[str, str | None, int], str] = {
    # barre antirollio
    ("aRBFront", None, -1): "Ammorbidisci la barra antirollio anteriore.",
    ("aRBRear", None, -1): "Ammorbidisci la barra antirollio posteriore.",
    # molle e ammortizzatori
    ("wheelRate", "front", -1): "Ammorbidisci le molle anteriori.",
    ("wheelRate", "rear", -1): "Ammorbidisci le molle posteriori.",
    ("reboundSlow", "rear", -1): "Ammorbidisci l'estensione posteriore.",
    # geometria: il +1 di `toe` e' toe-out davanti e toe-in dietro, come dicono
    # i rimedi che lo propongono
    ("toe", "front", +1): "Aumenta il toe-out anteriore.",
    ("toe", "rear", +1): "Aumenta il toe-in posteriore.",
    ("camber", "front", -1): "Aumenta il camber negativo anteriore.",
    # altezze e aerodinamica
    ("rideHeight", "rear", +1): "Alza il posteriore per avere più rake.",
    ("rideHeight", "rear", -1): "Abbassa il posteriore.",
    ("splitter", None, +1): "Aumenta lo splitter anteriore.",
    ("frontWing", None, +1): "Aumenta l'ala anteriore.",
    ("rearWing", None, +1): "Aumenta l'ala posteriore.",
    ("rearWing", None, -1): "Riduci l'ala posteriore.",
    # freni, differenziale, elettronica
    ("brakeBias", None, +1): "Sposta il bilanciamento freni in avanti.",
    ("brakeBias", None, -1): "Sposta il bilanciamento freni indietro.",
    ("preload", None, +1): "Aumenta il precarico del differenziale.",
    ("preload", None, -1): "Riduci il precarico del differenziale.",
    ("diffPower", None, -1): "Riduci il bloccaggio del differenziale in accelerazione.",
    ("diffCoast", None, +1): "Aumenta il bloccaggio del differenziale in rilascio.",
    ("tC1", None, +1): "Aumenta il controllo di trazione.",
    # pressioni: anche il rimedio stradale «togli 2 click di pressione alle
    # gomme anteriori» cade sulla riga anteriore in giu'
    ("tyrePressure", "front", +1): "Alza la pressione delle gomme anteriori.",
    ("tyrePressure", "front", -1): "Abbassa la pressione delle gomme anteriori.",
    ("tyrePressure", "rear", +1): "Alza la pressione delle gomme posteriori.",
    ("tyrePressure", "rear", -1): "Abbassa la pressione delle gomme posteriori.",
}

_AXES = {FRONT: "front", REAR: "rear", ALL: "all", (None,): None}


def _key(change: ProposedChange) -> tuple[str, str | None, int] | None:
    """Cosa fa la modifica: un parametro, un asse, una direzione. None se la
    modifica non ha questa forma (vuota, parametri misti, segni discordi)."""
    atoms = change.changes
    if not atoms:
        return None
    params = {a.param for a in atoms}
    signs = {(a.delta_clicks > 0) - (a.delta_clicks < 0) for a in atoms}
    if len(params) != 1 or len(signs) != 1 or 0 in signs:
        return None
    slots = tuple(sorted(a.slot for a in atoms)) if None not in {
        a.slot for a in atoms} else (None,)
    axis = _AXES.get(slots, "?")
    if axis == "?":
        return None
    return params.pop(), axis, signs.pop()


def voice_lever(change: ProposedChange) -> str | None:
    """La frase italiana che la voce dice per questa leva, senza numeri.

    None se la tabella non la conosce: chi chiama ripiega e lo scrive nel log
    (non deve succedere, lo impedisce `tests/test_voce_leve.py`)."""
    key = _key(change)
    return _LEVERS.get(key) if key is not None else None


def all_voice_levers() -> list[str]:
    """Tutte le frasi della tabella, per il catalogo di quello che si registra."""
    return list(_LEVERS.values())
