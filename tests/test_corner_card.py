"""Il blocco `corner`: il consuntivo muto dell'ultima curva chiusa.

Tre casi in cui non deve esserci — senza riferimento, su un giro non
rappresentativo, e prima della prima curva — e uno in cui deve esserci anche se
il coach non ha niente da dire. Quest'ultimo è il punto di tutta la feature.
"""
from accoach.coaching.analyzer import _LOSS_MS
from accoach.engine import CoachEngine
from accoach.recording.storage import save_lap

import synth


class _StubReader:
    def __init__(self, frames):
        self._frames = frames
        self._i = 0

    def read(self):
        s = self._frames[min(self._i, len(self._frames) - 1)]
        self._i += 1
        return s

    def close(self):
        pass


def _lap_frames(completed, n=80, slow=False, in_pit=False):
    """I frame di un giro. `slow` perde velocità (e tempo) nella curva 0."""
    frames = []
    for i in range(n):
        pos = i / n
        spd, brake, thr, steer = synth._profile(pos)
        if slow and 0.16 <= pos <= 0.40:
            spd = max(spd - 30.0, 90.0)
        frames.append(synth.snap(
            pos=pos, completed_laps=completed, current_lap_ms=i * 100,
            last_lap_ms=95000, speed_kmh=spd, throttle=thr, brake=brake,
            steer_angle=steer, in_pit=in_pit,
        ))
    return frames


def _run(tmp_path, frames, reference=True):
    """Guida `frames` col riferimento già su disco; torna (engine, ultimo stato)."""
    if reference:
        save_lap(synth.build_lap(), tmp_path)
    eng = CoachEngine(reader=_StubReader(frames), voice=None, laps_dir=tmp_path)
    st = None
    for _ in range(len(frames)):
        st = eng.tick(0.0)
    return eng, st


def _three_laps(**kw):
    return _lap_frames(0, **kw) + _lap_frames(1, **kw) + _lap_frames(2, **kw)


def test_no_card_without_a_reference(tmp_path):
    """Prima sessione su auto o pista nuova: non c'è niente contro cui misurare.

    Solo due giri, non tre: `_lap_frames` azzera `pos` a ogni giro, e quello è
    lo stesso segnale di «passaggio dal traguardo» che il registratore guarda
    per chiudere un giro. Con tre giri il primo giro pieno (il secondo blocco)
    si chiude e si salva DENTRO questo test, e il motore lo rincorre subito
    come nuovo riferimento (comportamento esistente, corretto in generale) —
    il che smentirebbe proprio il «senza riferimento» che il test vuole
    provare. Due giri bastano per uscire dall'out-lap (`quiet` diventa
    "no_reference") senza mai chiudere un giro intero.
    """
    eng, st = _run(tmp_path, _lap_frames(0) + _lap_frames(1), reference=False)
    assert eng.saved_laps == 0
    assert st.quiet == "no_reference"
    assert st.corner is None
    eng.close()


def test_a_corner_taken_well_still_shows_a_card(tmp_path):
    """Il caso che oggi non arriva mai a schermo: la curva presa bene."""
    eng, st = _run(tmp_path, _three_laps())
    assert st.corner is not None
    assert st.corner["level"] == "ok"
    assert abs(st.corner["lost_ms"]) < _LOSS_MS
    assert st.corner["name"]              # un nome c'è sempre, almeno "Curva 2"
    assert st.corner["index"] == 1        # l'ultima curva chiusa del giro
    eng.close()


def test_the_card_carries_the_measured_tenths(tmp_path):
    eng, st = _run(tmp_path, _three_laps(slow=True))
    assert st.corner is not None
    assert isinstance(st.corner["lost_ms"], float)
    assert st.corner["level"] in ("ok", "warn", "bad")
    eng.close()


def test_the_card_is_dropped_on_an_unrepresentative_lap(tmp_path):
    """Box, ricognizione, giro fuori ritmo: non nascosta, buttata — o
    riapparirebbe identica dopo il pit stop, col numero di dieci minuti fa.

    Che dopo tre giri buoni la carta ci fosse lo dice il test qui sopra: qui
    si guidano gli stessi tre giri e poi si entra ai box."""
    eng, st = _run(tmp_path, _three_laps() + _lap_frames(3, in_pit=True))
    assert st.quiet == "pit"
    assert st.corner is None
    assert eng.analyzer.last_corner is None
    eng.close()
