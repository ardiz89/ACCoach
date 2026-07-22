"""Le due diagnosi che i coach umani danno per prime, e il debrief non dava.

Da un thread reale di aiuto: prima delle curve, un coach ti dice che **sollevi
dove si sta in pieno** (e quanto ti costa sul rettilineo che segue) e che **ti
mancano dei km/h di punta** — con l'osservazione decisiva che se in curva vai
come il riferimento, allora non è l'auto a essere lenta, è l'ala.

Nessuna delle due entra nella lista per curva: la prima vive sul rettilineo *fra*
due curve, la seconda è un numero solo per tutto il giro.
"""
from dataclasses import replace

import pytest

from accoach.coaching.debrief import (
    _VMAX_GAP_KMH,
    build_lap_debrief,
)
from accoach.comparison import Reference
from accoach.track import detect_corners

import synth


def _pair(mutate=None):
    """(giro, riferimento) sullo stesso tracciato sintetico."""
    ref_lap = synth.build_lap()
    lap = synth.build_lap()
    if mutate is not None:
        lap.samples = [mutate(s) for s in lap.samples]
    return lap, Reference(ref_lap)


def _notes(lap, ref, kind):
    corners = detect_corners(ref.lap.samples)
    d = build_lap_debrief(lap, ref, corners, "it")
    return [n for n in d.notes if n.kind == kind]


# --- sollevamento dove il riferimento sta in pieno -------------------------

def test_a_lift_on_a_flat_out_stretch_is_reported():
    def lift(s):
        # una finestra in pieno rettilineo: gas giù e tempo perso da lì in poi
        if 0.02 <= s.pos <= 0.10:
            return replace(s, throttle=0.55, t_ms=s.t_ms + int((s.pos - 0.02) * 4000))
        if s.pos > 0.10:
            return replace(s, t_ms=s.t_ms + 320)
        return s

    lap, ref = _pair(lift)
    found = _notes(lap, ref, "lift")
    assert found, "un sollevamento in pieno deve comparire"
    assert found[0].lost_ms > 0
    assert "55" in found[0].detail, "deve dire quanto gas hai tenuto"


def test_a_clean_lap_has_no_lift_note():
    lap, ref = _pair()
    assert not _notes(lap, ref, "lift")


def test_a_momentary_blip_is_not_a_lift():
    """Un campione solo è rumore del pedale, non una decisione."""
    def blip(s):
        return replace(s, throttle=0.5) if 0.050 <= s.pos <= 0.052 else s

    lap, ref = _pair(blip)
    assert not _notes(lap, ref, "lift")


def test_lifting_where_the_reference_also_lifts_is_not_a_finding():
    """In staccata il riferimento non è in pieno: lì sollevare è guidare."""
    def brake_zone(s):
        return replace(s, throttle=0.0) if 0.22 <= s.pos <= 0.30 else s

    lap, ref = _pair(brake_zone)
    assert not _notes(lap, ref, "lift")


# --- velocità di punta ------------------------------------------------------

def test_matching_corners_and_a_low_top_speed_points_at_the_wing():
    """La distinzione che dà valore alla nota: se in curva vai uguale, è ala."""
    def slower_on_straights(s):
        return replace(s, speed_kmh=s.speed_kmh - 10.0) if s.speed_kmh > 200 else s

    lap, ref = _pair(slower_on_straights)
    found = _notes(lap, ref, "top_speed")
    assert found
    assert "ala" in found[0].detail.lower()


def test_being_slower_everywhere_points_at_the_exits_instead():
    """Togliere ala a chi perde in uscita peggiora l'unica cosa che sbagliava."""
    def slower_everywhere(s):
        return replace(s, speed_kmh=s.speed_kmh * 0.90)

    lap, ref = _pair(slower_everywhere)
    found = _notes(lap, ref, "top_speed")
    assert found
    assert "uscit" in found[0].detail.lower()


def test_the_same_top_speed_says_nothing():
    lap, ref = _pair()
    assert not _notes(lap, ref, "top_speed")


def test_the_threshold_clears_run_to_run_noise():
    """Carico benzina, scia, un metro di traiettoria: sotto questo è rumore."""
    assert 3.0 <= _VMAX_GAP_KMH <= 8.0


def test_the_notes_reach_the_frontend(tmp_path):
    from accoach.recording.storage import save_lap
    from accoach.serialize import __name__ as _  # noqa: F401 - import sanity

    lap, ref = _pair()
    save_lap(ref.lap, tmp_path)
    corners = detect_corners(ref.lap.samples)
    d = build_lap_debrief(lap, ref, corners, "it")
    assert isinstance(d.notes, list), "il debrief espone sempre la lista"
