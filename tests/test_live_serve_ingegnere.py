"""Coach Live alimenta la pagina Ingegnere col proprio motore.

Il difetto, visto in pista il 2026-09-24: il coach dice «modifica pronta,
rientra ai box e apri la pagina Ingegnere», il pilota rientra, apre, e legge
«telemetria offline». La pagina la alimentava solo il Backend live, che non
poteva girare insieme a Coach Live perche' due motori salvano ogni giro due
volte. Non c'era **nessuna** strada per vedere la modifica.

Qui si prova la meta' lato Coach Live: un solo motore, fatto avanzare una sola
volta per giro di giostra, e lo stesso stato dato all'overlay **e** alla pagina.
"""
from accoach.app import make_step


class _MotoreFinto:
    def __init__(self) -> None:
        self.ticks = 0

    def tick(self, now: float):
        self.ticks += 1
        return {"n": self.ticks}          # basta un oggetto riconoscibile


class _OverlayFinto:
    def __init__(self) -> None:
        self.ricevuti = []

    def apply_state(self, d) -> None:
        self.ricevuti.append(d)


def _passo(publish=None, conv=lambda s: s):
    m, o = _MotoreFinto(), _OverlayFinto()
    return m, o, make_step(m, o, publish=publish, to_dict=conv)


def test_un_giro_di_giostra_fa_avanzare_il_motore_una_volta_sola():
    """**Il test che giustifica il file.**

    Se il motore avanzasse due volte per passo — una per l'overlay e una per la
    pagina — ogni giro verrebbe visto due volte, e la copia e' indistinguibile
    da un giro vero in piu'. E' l'incidente del 22/07 da un'altra porta.
    """
    m, _o, step = _passo(publish=lambda s: None)
    step()
    step()
    assert m.ticks == 2, f"due passi, {m.ticks} tick: qualcuno lo fa avanzare due volte"


def test_overlay_e_pagina_ricevono_lo_STESSO_stato():
    """Non due letture: la stessa. Due letture divergono, e il pilota vedrebbe
    sull'HUD un numero e sulla pagina un altro."""
    visti = []
    m, o, step = _passo(publish=visti.append)
    step()
    assert len(visti) == 1 and len(o.ricevuti) == 1
    assert visti[0] == {"n": 1}
    assert o.ricevuti[0] == {"n": 1}


def test_senza_pagina_da_alimentare_il_passo_funziona_uguale():
    """La pagina e' un di piu': se la porta e' occupata Coach Live deve girare
    come ha sempre fatto, non rifiutarsi di partire."""
    m, o, step = _passo(publish=None)
    step()
    assert m.ticks == 1 and len(o.ricevuti) == 1


def test_se_la_pagina_esplode_il_coach_continua():
    """Un errore nel trasmettere non deve fermare il coach che guida il pilota:
    l'overlay e la voce vengono prima della pagina."""
    def esplode(_s):
        raise RuntimeError("websocket morto")

    m, o, step = _passo(publish=esplode)
    step()
    step()
    assert m.ticks == 2, "un errore di trasmissione ha fermato il motore"
    assert len(o.ricevuti) == 2, "un errore di trasmissione ha spento l'overlay"


def test_la_pagina_riceve_lo_stato_grezzo_non_quello_impacchettato():
    """L'overlay vuole il dizionario, la pagina vuole lo stato: la conversione
    e' dell'overlay, e farla due volte sarebbe lavoro doppio a 60 Hz."""
    visti = []
    m, o, step = _passo(publish=visti.append, conv=lambda s: {"impacchettato": s})
    step()
    assert o.ricevuti[0] == {"impacchettato": {"n": 1}}
    assert visti[0] == {"n": 1}


# --- chi puo' arrivare al feed ----------------------------------------------
#
# Trovato il 13/10 rigiocando i giri del 24/09 dentro il passo vero di Coach
# Live, con un client sull'indirizzo di rete del PC: la pagina arrivava (l'app
# di analisi in LAN ascolta su tutte le interfacce), il feed no — connessione
# rifiutata, perche' lo spettatore si legava a `server.host` e basta. Sul
# tablet, che e' dove il pilota la guarda, sarebbe stato «telemetria offline»
# come prima della cura.

class _Cfg:
    class server:
        host = "127.0.0.1"
        port = 8777
        hz = 15.0

    lan = False


def test_in_lan_il_feed_ascolta_dove_arriva_il_tablet():
    from accoach.server import listen_host

    cfg = _Cfg()
    assert listen_host(cfg) == "127.0.0.1"
    cfg.lan = True
    assert listen_host(cfg) == "0.0.0.0"
    cfg.lan = False
    assert listen_host(cfg, ["--lan"]) == "0.0.0.0"


def test_coach_live_serve_il_feed_sulla_stessa_interfaccia_del_backend(monkeypatch):
    """La regola ha due chiamanti, e il secondo l'aveva persa. Si guarda
    l'effetto: l'indirizzo che arriva a uvicorn quando la config dice LAN."""
    import uvicorn

    from accoach import app as live
    from accoach import netinfo

    cfg = _Cfg()
    cfg.lan = True
    visti = []

    class _Server:
        def __init__(self, config):
            visti.append(config.host)

        def run(self):
            pass

    monkeypatch.setattr(live, "load_config", lambda: cfg)
    monkeypatch.setattr(netinfo, "port_open", lambda port: False)
    monkeypatch.setattr(uvicorn, "Server", _Server)

    publish = live._serve_engineer_page(object())
    assert visti == ["0.0.0.0"]
    assert callable(publish)
