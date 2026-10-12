"""Un giro salvato non azzera il coach.

Trovato il 12/10 rigiocando i giri veri dentro il motore, non leggendolo:
`_rebuild_reference` gira dopo **ogni** giro salvato (per inseguire il nuovo
miglior giro) e insieme al riferimento buttava via tutto quello che il coach
aveva imparato nel giro appena chiuso — i consigli di curva, il conto della
benzina, i cooldown di pressioni e TC. Il risultato, misurato sul log di pista
dal 31/08: i consigli di curva detti **zero volte su 24** dopo un giro salvato e
26 volte dopo un giro *non* salvato, cioe' dopo il giro d'uscita, che e' l'unico
giro da cui non andrebbero presi. E l'avviso benzina non poteva arrivare mai:
ogni traguardo era «il primo».

Ogni modulo, provato da solo, era verde. Il difetto stava fra il motore e i
moduli, quindi questi test passano **dal motore**, con un giro salvato consegnato
come lo consegna il feed dal vivo: un paio di tick dopo la linea.
"""
from accoach.coaching.cue import CueCategory
from accoach.engine import CoachEngine
from accoach.recording.storage import save_lap
from accoach.telemetry.snapshot import TelemetrySnapshot

import synth

#: Quello che l'analyzer mette da parte a fine curva e dice al giro dopo.
_DI_CURVA = {CueCategory.CARRY_SPEED, CueCategory.TIME_LOSS,
             CueCategory.MORE_THROTTLE, CueCategory.LESS_BRAKE,
             CueCategory.BRAKE_LATER, CueCategory.BRAKE_EARLIER}

#: Sotto la finestra GT3 (27.5 ± 0.7), a gomme in temperatura.
_GOMME_BASSE = dict(tyre_pressure=(25.0,) * 4, tyre_core_temp=(85.0,) * 4)


class _Feed:
    """Il feed dal vivo, guidato a mano: l'ultimo frame e i giri appena salvati."""

    def __init__(self) -> None:
        self.snap = TelemetrySnapshot.disconnected()
        self.saved: list = []

    def latest(self):
        return self.snap

    def drain_saved(self):
        out, self.saved = self.saved, []
        return out


class _Sessione:
    """Un motore vero con un riferimento su disco, e la lista di cio' che propone.

    Si guarda cosa il motore **consegna allo scheduler**, non cosa lo scheduler
    poi pronuncia: lo scheduler ha il diritto di scartare, e un test che passasse
    di li' proverebbe i suoi tempi invece della cosa che qui si e' rotta.
    """

    def __init__(self, tmp_path) -> None:
        save_lap(synth.build_lap(clean=True), tmp_path)        # il riferimento
        self.feed = _Feed()
        self.eng = CoachEngine(feed=self.feed, voice=None, laps_dir=tmp_path)
        self.now = 0.0
        self.completed = 0
        self.proposti: list[tuple[int, CueCategory]] = []      # (giro, categoria)
        submit = self.eng.scheduler.submit_all

        def spia(cues, now):
            self.proposti.extend((self.completed, c.category) for c in cues)
            return submit(cues, now)

        self.eng.scheduler.submit_all = spia

    def _tick(self, **kw) -> None:
        self.feed.snap = synth.snap(completed_laps=self.completed, is_acc=True, **kw)
        self.eng.tick(self.now)
        self.now += 0.5

    def avvicinamento(self) -> None:
        """Gli ultimi metri prima della linea: serve vederla attraversare perche'
        il giro dopo conti come lanciato."""
        for i in range(10):
            self._tick(pos=0.90 + i * 0.01, speed_kmh=200.0, current_lap_ms=90000 + i * 1000)

    def giro(self, lap, *, salva=None, fuel=(30.0, 30.0), corsia_box=False, **kw) -> None:
        """Guida `lap` dal traguardo al traguardo.

        `salva`: il giro che il feed consegna **due tick dopo la linea**, come
        dal vivo (il registratore aspetta la risposta del gioco sul tempo).
        `corsia_box`: i primi metri sono in corsia box, cioe' e' un giro d'uscita.
        """
        self.completed += 1
        da, a = fuel
        for i, s in enumerate(lap.samples[:-1:2]):
            if i == 2 and salva is not None:
                self.feed.saved.append(salva)
            self._tick(pos=s.pos, speed_kmh=s.speed_kmh, throttle=s.throttle,
                       brake=s.brake, current_lap_ms=s.t_ms,
                       fuel=da + (a - da) * s.pos,
                       in_pit_lane=corsia_box and s.pos < 0.05, **kw)

    def detti_nel_giro(self, giro: int, categorie) -> list[CueCategory]:
        return [c for g, c in self.proposti if g == giro and c in categorie]


def _lento_alla_prima(amt: int = 30):
    """Un giro che perde tempo alla prima curva, e quindi non batte il riferimento."""
    return synth.build_lap(slow_corner=0, amt=amt, clean=True)


# --- i consigli di curva ----------------------------------------------------

def test_il_consiglio_di_curva_arriva_al_giro_dopo_un_giro_salvato(tmp_path):
    s = _Sessione(tmp_path)
    lento = _lento_alla_prima()
    s.avvicinamento()
    s.giro(lento)                                   # giro 1: perde alla prima curva
    s.giro(lento, salva=lento)                      # giro 2: il giro 1 arriva salvato
    assert s.eng._reference.lap_time_ms == 100000, "il riferimento e' cambiato: fixture sbagliato"
    assert s.detti_nel_giro(2, _DI_CURVA), (
        "il giro 1 ha perso tempo alla prima curva e il giro 2 non se l'e' sentito "
        "dire: il giro salvato ha svuotato la memoria dell'analyzer")
    s.eng.close()


def test_il_giro_d_uscita_non_insegna_niente(tmp_path):
    """L'altra meta', ed e' quella che in pista si sentiva: 26 consigli su 26.

    Sul giro d'uscita la voce e' gia' zitta (`quiet=out_lap`), ma l'analyzer
    continuava a prendere appunti — a gomme fredde, uscendo dalla corsia — e li
    leggeva sul primo giro lanciato.
    """
    s = _Sessione(tmp_path)
    s.giro(_lento_alla_prima(), corsia_box=True)    # giro d'uscita, lento ovunque conti
    s.giro(synth.build_lap(clean=True))             # primo giro lanciato
    assert not s.detti_nel_giro(2, _DI_CURVA), (
        "consigli misurati sul giro d'uscita, detti sul primo giro lanciato")
    s.eng.close()


# --- la benzina -------------------------------------------------------------

def test_l_avviso_benzina_arriva_anche_se_ogni_giro_viene_salvato(tmp_path):
    s = _Sessione(tmp_path)
    lento = _lento_alla_prima()
    s.avvicinamento()
    livello = 15.0
    for _ in range(5):
        s.giro(lento, salva=lento, fuel=(livello, livello - 3.0))
        livello -= 3.0
    assert s.eng._reference.lap_time_ms == 100000, "il riferimento e' cambiato: fixture sbagliato"
    assert CueCategory.FUEL in [c for _g, c in s.proposti], (
        "da 15 litri a zero bruciandone 3 a giro, e nessun avviso benzina")
    s.eng.close()


# --- le pressioni -----------------------------------------------------------

def test_le_pressioni_si_dicono_una_volta_non_a_ogni_giro(tmp_path):
    """Le pressioni si cambiano solo ai box: il cooldown e' di cinque giri."""
    s = _Sessione(tmp_path)
    lento = _lento_alla_prima()
    s.avvicinamento()
    for _ in range(4):
        s.giro(lento, salva=lento, **_GOMME_BASSE)
    dette = [g for g, c in s.proposti if c is CueCategory.TYRE_PRESSURE]
    assert len(dette) == 1, f"pressioni dette ai giri {dette}: una volta basta"
    s.eng.close()


def test_le_pressioni_non_si_giudicano_sul_giro_d_uscita(tmp_path):
    """In pista, quattro volte su quattro: la prima frase del coach era «gomme
    anteriori a 25.1 psi, alza 2.4» letta sul giro d'uscita, e a regime lo stesso
    treno diceva 26.2. La media prende tutta la rampa di riscaldamento.
    """
    s = _Sessione(tmp_path)
    veloce = synth.build_lap(clean=True)
    s.giro(veloce, corsia_box=True, **_GOMME_BASSE)     # giro d'uscita
    s.giro(veloce, **_GOMME_BASSE)                      # qui si chiude l'uscita
    assert not s.detti_nel_giro(2, {CueCategory.TYRE_PRESSURE}), (
        "pressione giudicata sul giro d'uscita")
    s.giro(veloce, **_GOMME_BASSE)                      # qui si chiude un giro vero
    assert s.detti_nel_giro(3, {CueCategory.TYRE_PRESSURE}), (
        "controllo: sul giro lanciato le stesse pressioni vanno dette, "
        "altrimenti il test sopra non prova niente")
    s.eng.close()


# --- le staccate imparate ---------------------------------------------------

def test_le_staccate_imparate_restano_spente_quando_il_riferimento_cambia(tmp_path):
    """`overlay.wean` toglie il conto alla rovescia dove il pilota ha imparato.

    Non ha mai avuto effetto: i tratti spenti stanno sul comparatore, e il
    comparatore veniva rifatto dopo ogni giro salvato, un istante dopo che
    `_update_wean` li aveva scritti. Qui il caso che resta delicato: un nuovo
    miglior giro, cioe' un comparatore nuovo davvero.
    """
    s = _Sessione(tmp_path)
    s.avvicinamento()
    eng = s.eng
    eng._wean = True
    eng._focus.mastered.add(eng._corners[0].index)
    eng._update_wean()
    assert eng._comparator._muted_spans, "fixture: nessun tratto spento in partenza"
    save_lap(synth.retime(synth.build_lap(clean=True), 99000), tmp_path)
    eng._rebuild_reference(*eng._key)
    assert eng._reference.lap_time_ms == 99000, "il riferimento non e' cambiato: fixture sbagliato"
    assert eng._comparator._muted_spans, "il comparatore nuovo ha riacceso le staccate imparate"
    eng.close()
