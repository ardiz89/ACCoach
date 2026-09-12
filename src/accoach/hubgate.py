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
"""

from __future__ import annotations

from typing import Iterable, NamedTuple, Sequence

from .i18n import t

# Sentinelle: bottoni che fanno qualcosa di diverso dall'avviare un comando.
GUIDE = "__guide__"
STOP_LIVE = "__stop_live__"
WIZARD = "__wizard__"
IMPORT_PRO = "__import_pro__"

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
                  ("web",), ("web", "--engineer")}

# I due bottoni su cui il briefing ai box manda il pilota, e che durante Coach
# Live non possono dare quello che promettono: il Backend live perché non si
# accende, la pagina Ingegnere perché si apre su un feed che non esiste. Invece
# di restare muti offrono lo scambio. Sono cliccabili di proposito: il click non
# avvia niente, apre la spiegazione.
SWAP_OFFER_KEYS = frozenset({("server",), ("web", "--engineer")})

# …ma i due non perdono la stessa cosa, e il dialogo non offre le stesse uscite.
#
# La pagina Ingegnere è **due cose in una**: la diagnosi dal vivo, che arriva dal
# websocket del Backend live (`engineer.js`, porta 8777), e l'editor assetti col
# registro delle prove e i setup salvati, che stanno tutti sul REST `/api/setup/*`
# servito dall'app di analisi sulla 8778 — nessun backend di mezzo. La pagina è
# progettata apposta per reggere a telemetria ferma (`engineer.js:142`, «L'ultimo
# giro registrato, per quando la telemetria è spenta»). Toglierla durante Coach
# Live costerebbe più di quanto lo scambio restituisce, quindi resta un'uscita
# «apri comunque»: metà pagina è meglio di nessuna pagina, se si dice quale metà.
#
# Il Backend live non ha una metà da aprire lo stesso: o si accende, o niente.
# Da qui l'asimmetria — che è una regola, non un `if` nel codice di disegno.
OPEN_ANYWAY_KEYS = frozenset({("web", "--engineer")})


def opens_anyway(key: object) -> bool:
    """Questo bottone ha ancora qualcosa da dare senza il Backend live?

    L'uscita di comodo può essere offerta **solo** a ciò che durante Coach Live
    era già sicuro e non registra niente: aprirla non deve poter diventare, per
    distrazione, il secondo motore che salva ogni giro due volte.
    """
    return key in OPEN_ANYWAY_KEYS


# Le tre uscite del dialogo. `CANCEL` è anche quella di sicurezza: Esc, la X
# della finestra, e qualunque modo di chiudere senza scegliere.
SWAP = "swap"
OPEN_ANYWAY = "open_anyway"
CANCEL = "cancel"

# I tre stati di un bottone. `EXPLAIN` è il nuovo: acceso ma non fa la sua cosa.
CLICKABLE = "clickable"
EXPLAIN = "explain"
BLOCKED = "blocked"


def button_state(key: object, *, live: bool, busy: bool) -> str:
    """Che cosa fa questo bottone adesso.

    `live` = Coach Live sta girando; `busy` = qualcosa di nostro sta già
    registrando (che è vero anche mentre gira Coach Live).

    L'ordine dei rami conta: `SWAP_OFFER_KEYS` viene guardato **prima** di
    `LIVE_SAFE_KEYS`, perché la pagina Ingegnere sta in tutte e due — è sicura
    da aprire, ma durante Coach Live è sicura e inutile, e mandare il pilota su
    una pagina vuota senza dirglielo è il difetto, non la cura.
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
                  "swap.cancel", "swap.failed", "swap.tooltip",
                  "swap.open_anyway", "swap.open_anyway_why")


def swap_text(lang: str | None = None) -> dict[str, str]:
    """Le frasi dello scambio, già tradotte, senza il prefisso ``swap.``."""
    return {key.split(".", 1)[1]: t(key, lang) for key in SWAP_TEXT_KEYS}
