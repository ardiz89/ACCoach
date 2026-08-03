"""Esci di pista, sbatti, torni ai box: guidando, o dal menu di gioco.

Domanda del pilota, e sono tre domande in una. Invalidare il giro è una cosa;
l'incidente è un'altra; e **tornare ai box guidando** non è come
**teletrasportarsi dal menu** — nel secondo caso il gioco fa sparire l'auto da
metà pista e la fa riapparire nel garage, cioè esattamente la discontinuità che
avvelena tutto ciò che tiene memoria di dove eri.

Written as a scenario rather than as unit tests because the failure modes are in
the *sequence*, not in any one frame.
"""
from dataclasses import replace

from accoach.engine import CoachEngine
from accoach.recording.storage import save_lap
from accoach.telemetry.snapshot import ACStatus

import synth


class _Reader:
    def __init__(self, frames):
        self._frames, self._i = frames, 0

    def read(self):
        s = self._frames[min(self._i, len(self._frames) - 1)]
        self._i += 1
        return s

    def close(self):
        pass


def _f(pos, **kw):
    return replace(synth.LIVE, lap_position=pos, **kw)


def _run(tmp_path, frames, entry_samples=()):
    """Drive `frames`; returns (engine, states) with ``states[i]`` for ``frames[i]``.

    The first frame is fed twice on purpose: the first tick on a new car/track
    rebuilds everything (engineer, focus, pit memory) and its state says more
    about that rebuild than about the frame. Duplicating it keeps the indices
    honest — the version that just swallowed a frame made an off-by-one that
    read as a passing test.
    """
    save_lap(synth.build_lap(), tmp_path)
    eng = CoachEngine(reader=_Reader([frames[0], *frames]), voice=None,
                      laps_dir=tmp_path)
    eng.tick(0.0)
    for pos in entry_samples:          # a track whose pit entry we already know
        eng.pitcall.note_pit_entry(pos)
    states = [eng.tick(0.05 * (i + 1)) for i in range(len(frames))]
    return eng, states


# The lap that goes wrong: over the line, then four wheels off, then a stop.
_FLYING = [
    _f(0.97, current_lap_ms=97_000, speed_kmh=250.0),
    _f(0.02, current_lap_ms=2_000, speed_kmh=250.0, completed_laps=1),
    _f(0.20, current_lap_ms=20_000, speed_kmh=200.0, completed_laps=1),
    _f(0.30, current_lap_ms=30_000, speed_kmh=180.0, completed_laps=1,
       tyres_out=4, lap_valid=False),
    _f(0.33, current_lap_ms=34_000, speed_kmh=2.0, completed_laps=1,
       lap_valid=False),
]

_DRIVE_BACK = _FLYING + [
    _f(0.90, current_lap_ms=90_000, speed_kmh=120.0, completed_laps=1, lap_valid=False),
    _f(0.94, current_lap_ms=92_000, speed_kmh=90.0, completed_laps=1, lap_valid=False),
    _f(0.96, current_lap_ms=94_000, speed_kmh=50.0, completed_laps=1,
       in_pit_lane=True, lap_valid=False),
    _f(0.97, current_lap_ms=96_000, speed_kmh=0.0, completed_laps=1,
       in_pit_lane=True, in_pit=True, lap_valid=False),
]

_TELEPORT = _FLYING + [
    # Il menu: il gioco non è più LIVE, e quando torna l'auto è nel garage.
    _f(0.33, current_lap_ms=34_000, speed_kmh=0.0, completed_laps=1,
       status=ACStatus.PAUSE, lap_valid=False),
    _f(0.01, current_lap_ms=0, speed_kmh=0.0, completed_laps=1,
       in_pit=True, in_pit_lane=True),
    _f(0.01, current_lap_ms=0, speed_kmh=0.0, completed_laps=1,
       in_pit=True, in_pit_lane=True),
]


# --- l'invalidazione ------------------------------------------------------

def test_the_game_calling_the_lap_off_is_reported_at_once(tmp_path):
    _, st = _run(tmp_path, _FLYING)
    assert st[2].lap_invalid is False, "prima dell'uscita il giro è ancora buono"
    assert st[3].lap_invalid is True, "quattro ruote fuori: il gioco lo dice, noi anche"
    assert st[4].lap_invalid is True, "e resta detto anche da fermi dopo il botto"


def test_an_abandoned_lap_is_never_saved(tmp_path):
    """Non è un giro: manca il pezzo fra l'incidente e il traguardo. Salvarlo
    metterebbe in archivio un tempo che non esiste."""
    eng, st = _run(tmp_path, _DRIVE_BACK)
    assert st[-1].saved_laps == 0


# --- rientro guidando -----------------------------------------------------

def test_the_delta_stops_in_the_pit_lane(tmp_path):
    """`normalizedCarPosition` avanza anche in corsia box e l'orologio del giro
    continua, quindi lì il delta è un numero che cresce mentre il pilota
    striscia al limitatore. Il gate `quiet` zittisce i **cue**, non il numero
    sull'overlay: era il numero a non tornare."""
    _, st = _run(tmp_path, _DRIVE_BACK)
    assert st[-2].quiet == "pit" and st[-2].delta is None, "in corsia"
    assert st[-1].quiet == "pit" and st[-1].delta is None, "fermo nel box"


def test_driving_in_teaches_the_pit_entry(tmp_path):
    """Rientrare dopo un incidente è comunque un ingresso vero: si impara."""
    eng, _ = _run(tmp_path, _DRIVE_BACK)
    assert eng.pitcall.pit_entry == 0.94


# --- rientro dal menu (teletrasporto) -------------------------------------

def test_teleporting_back_does_not_teach_a_false_pit_entry(tmp_path):
    """Il caso che rovina la memoria: l'ultimo frame in pista è a 0.33, in mezzo
    alla pista, e il primo nel garage è a 0.01. Preso per buono diventa un
    «ingresso box qui davanti» detto su un rettilineo."""
    eng, _ = _run(tmp_path, _TELEPORT, entry_samples=(0.94, 0.94, 0.94))
    assert eng.pitcall.pit_entry == 0.94, "la memoria vera non si è mossa"
    assert 0.33 not in eng.pitcall.samples()


def test_the_pause_frame_ends_the_flying_lap(tmp_path):
    """Fra il menu e il garage il giro non esiste più: dirlo ancora invalidato
    sarebbe vero e inutile, e il giro dopo non deve ereditarne niente."""
    _, st = _run(tmp_path, _TELEPORT)
    assert st[5].lap_invalid is False
    assert st[5].delta is None


def test_nothing_is_saved_after_a_teleport_either(tmp_path):
    _, st = _run(tmp_path, _TELEPORT)
    assert st[-1].saved_laps == 0


def test_the_lap_after_a_teleport_starts_from_scratch(tmp_path):
    """Riprendere a contare da dove si era interrotto darebbe un giro che
    comincia a metà pista con l'orologio del precedente."""
    frames = _TELEPORT + [
        _f(0.05, current_lap_ms=3_000, speed_kmh=120.0, completed_laps=1),
    ]
    _, st = _run(tmp_path, frames)
    assert st[-1].quiet == "out_lap", "non è un giro lanciato finché non passi al via"
