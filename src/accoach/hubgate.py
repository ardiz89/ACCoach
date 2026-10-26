"""Le decisioni dell'hub: chi è cliccabile, cosa dice il rifiuto, come si scambia.

Qui non c'è Qt. Il launcher disegna; questo modulo decide — perché un bottone
grigio non si interroga in un test headless, mentre la regola che lo rende
grigio sì. Il perché di ogni regola sta nei commenti qui sotto, e non nel
codice di disegno, così la prossima persona che tocca l'interfaccia trova la
regola prima del pulsante.

Il fatto da cui nasce tutto (pista, 2026-09-01): il briefing ai box dice al
pilota «apri la pagina Ingegnere», ma quella pagina la alimenta **solo** il
Backend live (`engineer.js` parla col websocket sulla porta 8777, che è
`server`), e sotto Coach Live il bottone del Backend live era spento **e muto**.
Il coach mandava l'utente contro un muro e il muro non diceva niente.

Dal 24/09 la premessa e' cambiata: Coach Live serve lui il feed della pagina
Ingegnere, col proprio motore (`app._serve_engineer_page`, backend spettatore).
La pagina quindi durante Coach Live **si apre e basta**, e la spiegazione resta
a un bottone solo — il Backend live, che accanto a Coach Live continua a non
poter partire.
"""

from __future__ import annotations

from typing import Iterable, NamedTuple, Sequence

from .i18n import t

# Sentinelle: bottoni che fanno qualcosa di diverso dall'avviare un comando.
GUIDE = "__guide__"
STOP_LIVE = "__stop_live__"
WIZARD = "__wizard__"
IMPORT_PRO = "__import_pro__"
CENTER_OVERLAY = "__center_overlay__"
# «Sposta l'overlay»: la copia trascinabile (overlay_place.py). Non legge la
# telemetria e non registra niente, quindi resta premibile con Coach Live
# acceso, ed e' proprio li' che serve: si sistema l'overlay col gioco aperto.
PLACE_OVERLAY = ("overlay", "--place")

# Tutto ciò che apre un `CoachEngine` o un `LapRecorder`. `server` ci è arrivato
# tardi: il suo motore (server.py:97) registra come gli altri, ma non essendo
# elencato il watcher poteva accendergli accanto il registratore silenzioso.
RECORDING_CMDS = ("recorder", "live", "coach", "compare", "server")

# Mentre Coach Live gira, questi restano premibili; tutto il resto si spegne,
# così non ci si impila sopra un secondo coach o un secondo lettore di
# telemetria. (La barra laterale resta comunque navigabile.)
# NOTA: `("server",)` NON è qui, e non deve tornarci. Il backend live istanzia un
# `CoachEngine` suo (server.py:97) che registra i giri come chiunque altro, quindi
# acceso insieme a Coach Live **salva ogni giro due volte** — e la copia è
# indistinguibile da un giro vero in più. È lo stesso incidente del 22/07 («il mio
# fix del traguardo contava ogni giro due volte») da un'altra porta, reso più
# probabile dal fatto che la pagina Ingegnere chiede proprio quel bottone.
LIVE_SAFE_KEYS = {STOP_LIVE, GUIDE, WIZARD, IMPORT_PRO,
                  ("web",), ("web", "--engineer"),
                  PLACE_OVERLAY, CENTER_OVERLAY}

# Il bottone che durante Coach Live non puo' fare la sua cosa: il Backend live
# non si accende, perche' sarebbe il secondo motore. Invece di restare muto
# offre lo scambio. E' cliccabile di proposito: il click non avvia niente, apre
# la spiegazione.
#
# La pagina Ingegnere **non e' piu' qui**. Ci stava finche' durante Coach Live
# si apriva su un feed che non esisteva; ora il feed lo da' Coach Live stesso,
# e spiegare al pilota che la pagina «resta vuota» mentre funziona sarebbe il
# difetto di prima a rovescio: non un muro muto, un cartello che mente.
SWAP_OFFER_KEYS = frozenset({("server",)})


# Le due uscite del dialogo. `CANCEL` è anche quella di sicurezza: Esc, la X
# della finestra, e qualunque modo di chiudere senza scegliere.
SWAP = "swap"
CANCEL = "cancel"

# I tre stati di un bottone. `EXPLAIN` è il nuovo: acceso ma non fa la sua cosa.
CLICKABLE = "clickable"
EXPLAIN = "explain"
BLOCKED = "blocked"


def button_state(key: object, *, live: bool, busy: bool) -> str:
    """Che cosa fa questo bottone adesso.

    `live` = Coach Live sta girando; `busy` = qualcosa di nostro sta già
    registrando (che è vero anche mentre gira Coach Live).

    Durante Coach Live la pagina Ingegnere è un bottone come gli altri sicuri:
    il suo feed lo serve Coach Live stesso.
    """
    if live:
        if key in SWAP_OFFER_KEYS:
            return EXPLAIN
        return CLICKABLE if key in LIVE_SAFE_KEYS else BLOCKED
    records = isinstance(key, tuple) and bool(key) and key[0] in RECORDING_CMDS
    return BLOCKED if (busy and records) else CLICKABLE


class SwapStep(NamedTuple):
    """Un passo dello scambio: fermare o avviare, con che argomenti."""

    action: str                  # "stop" | "start"
    args: tuple[str, ...]
    console: bool = False        # il backend vuole la sua finestra, come sempre


def swap_plan() -> tuple[SwapStep, ...]:
    """Lo scambio, nell'ordine che lo rende sicuro.

    Prima si ferma, poi si avvia — e mai il contrario. Avviare il backend prima
    di fermare Coach Live vorrebbe dire due motori accesi insieme anche solo per
    un istante, cioè esattamente il giro salvato due volte che questa regola
    esiste per evitare.

    Il piano è un dato, non una sequenza di chiamate, così l'ordine si può
    leggere in un test senza avviare nessun processo.
    """
    return (
        SwapStep("stop", ("live",)),
        SwapStep("start", ("server",), console=True),
        SwapStep("start", ("web", "--engineer")),
    )


def swap_is_safe(running: Iterable[Sequence[str]]) -> bool:
    """Si può avviare il Backend live adesso?

    Solo se **niente** di nostro sta ancora registrando. Si chiama dopo lo stop
    e prima del primo avvio: `taskkill` torna prima che il processo sia morto, e
    un `poll()` ottimista qui sarebbe la coesistenza che stiamo escludendo.
    """
    return not any(args and args[0] in RECORDING_CMDS for args in running)


# Le chiavi del catalogo che compongono la spiegazione. Elencate qui e non
# sparse nel launcher perché il test che controlla «esiste in tutte le lingue»
# deve poterle leggere senza aprire Qt.
SWAP_TEXT_KEYS = ("swap.title", "swap.why", "swap.warn", "swap.confirm",
                  "swap.cancel", "swap.failed", "swap.tooltip")


def swap_text(lang: str | None = None) -> dict[str, str]:
    """Le frasi dello scambio, già tradotte, senza il prefisso ``swap.``."""
    return {key.split(".", 1)[1]: t(key, lang) for key in SWAP_TEXT_KEYS}
