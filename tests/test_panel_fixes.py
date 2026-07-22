"""Tre difetti trovati dal panel del 2026-07-22, uno per sezione.

Non sono bug di crash: sono tre modi diversi in cui il coach diceva una cosa
difendibile e sbagliata, che per un allenatore è il difetto peggiore di tutti.
"""
import pytest

from accoach.coaching.analyzer import _BRAKE_EARLY_POS, _braked_early
from accoach.coaching.cue import CueCategory
from accoach.coaching.debrief import build_lap_debrief
from accoach.comparison import Reference
from accoach.engine import CoachEngine
from accoach.recording.storage import save_lap
from accoach.track import detect_corners

import synth

from test_engine_gate import _StubReader, _crossing, _run


# --- 1. "Puoi frenare più tardi" aveva bisogno di un margine ----------------

def test_a_metre_early_is_not_braking_early():
    """Era la PRIMA branch della classificazione e l'unica senza margine: un
    metro d'anticipo bastava a scavalcare la causa vera."""
    assert _braked_early(0.5000, 0.5002, 0.0) is False


def test_braking_clearly_earlier_still_counts():
    assert _braked_early(0.500, 0.500 + _BRAKE_EARLY_POS * 2, 0.0) is True


def test_braking_where_the_reference_never_brakes_counts():
    """Curva che il riferimento fa in pieno: nessun margine può ridurre questo."""
    assert _braked_early(0.5, -1.0, 0.0) is True


def test_not_braking_at_all_is_not_braking_early():
    assert _braked_early(-1.0, 0.5, 0.0) is False


def test_braking_later_than_the_reference_is_not_early():
    assert _braked_early(0.52, 0.50, 0.0) is False


def test_the_margin_is_a_sane_distance_on_a_real_circuit():
    """~12 m a Monza (5793 m), ~17 m su un 7 km: sopra il rumore, sotto l'errore
    che vale la pena segnalare."""
    assert 8.0 <= _BRAKE_EARLY_POS * 5793 <= 20.0


# --- 2. "Nessun riferimento" non è un giro anomalo -------------------------

def _engine(tmp_path, frames, with_reference: bool):
    if with_reference:
        save_lap(synth.build_lap(), tmp_path)
    return CoachEngine(reader=_StubReader(frames), voice=None, laps_dir=tmp_path)


def test_absolute_cues_speak_even_without_a_reference(tmp_path):
    """Prima sessione su auto/pista nuova: il pilota sentiva solo bloccaggi e
    benzina. Veleggiamento, assetto, marce e gomme non hanno MAI avuto bisogno
    di un riferimento — erano zittiti per associazione."""
    frames = [synth.snap(pos=0.5)] + _crossing()
    frames += [synth.snap(pos=0.5, completed_laps=1, speed_kmh=150.0,
                          throttle=0.0, brake=0.0) for _ in range(25)]
    eng = _engine(tmp_path, frames, with_reference=False)
    spoken = _run(eng, frames)
    assert eng.tick(99.0).quiet == "no_reference", "il motivo resta dichiarato"
    assert any(c.category.value == "coasting" for c in spoken)
    eng.close()


def test_an_out_lap_is_still_silent_without_a_reference(tmp_path):
    """La correzione non deve riaprire il canale sui giri che NON contano: era
    un audit live vero a chiudere quel rubinetto."""
    frames = [synth.snap(pos=0.5, speed_kmh=150.0, throttle=0.0, brake=0.0)
              for _ in range(25)]
    eng = _engine(tmp_path, frames, with_reference=False)
    spoken = _run(eng, frames)
    assert all(c.category.value != "coasting" for c in spoken)
    eng.close()


def test_an_off_pace_lap_is_still_silent(tmp_path):
    from accoach.engine import _GATE_DELTA_MS
    huge = int(_GATE_DELTA_MS) + 500_000
    frames = [synth.snap(pos=0.5)] + _crossing()
    frames += [synth.snap(pos=0.5, completed_laps=1, current_lap_ms=huge,
                          speed_kmh=150.0, throttle=0.0, brake=0.0)
               for _ in range(25)]
    eng = _engine(tmp_path, frames, with_reference=True)
    spoken = _run(eng, frames)
    assert all(c.category.value != "coasting" for c in spoken)
    eng.close()


# --- 3. Le curve avevano un nome sul web e un numero inglese nella voce -----

def test_the_debrief_names_its_own_corners():
    """L'API lo faceva, il percorso live no: stesso giro, due nomi diversi."""
    lap = synth.build_lap(track="monza", slow_corner=0, amt=400)
    corners = detect_corners(lap.samples)
    d = build_lap_debrief(lap, Reference(synth.build_lap(track="monza")),
                          corners, "it")
    assert d.losses, "il giro sintetico perde tempo per costruzione"
    assert all(x.name for x in d.losses), "ogni curva deve avere un nome"


def test_an_unnamed_track_falls_back_in_the_session_language():
    """Su una pista senza tabella il ripiego dev'essere 'Curva N', non 'Corner N'."""
    lap = synth.build_lap(track="nordschleife", slow_corner=0, amt=400)
    corners = detect_corners(lap.samples)
    d = build_lap_debrief(lap, Reference(synth.build_lap(track="nordschleife")),
                          corners, "it")
    assert d.losses
    assert all(x.label.startswith("Curva") for x in d.losses)
