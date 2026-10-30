"""Il coach dice che il giro e' invalidato, e perche', a curva finita."""
from types import SimpleNamespace

import pytest

from accoach.coaching.cue import CueCategory, CueTier, tier_of
from accoach.coaching.lapvalid import LapValidityCoach, lap_lost_reason
from accoach.coaching.spoken import spoken_phrases
from accoach.engine import _SAFETY_CATEGORIES, _name_the_corner
from accoach.i18n import cue_text
from accoach.telemetry.snapshot import ACStatus

import synth
from test_focus_parla_col_tema import _SessioneCheParla

CORNER = SimpleNamespace(index=1, entry_pos=0.40, exit_pos=0.50, kind="corner",
                         direction="right")
# Rettilineo verso +z: per la convenzione di `lateral_offsets` la destra e' -x (coordinate mancine).
REF = SimpleNamespace(samples=[])


def frame(pos, valid=True, x=0.0, z=None, **kw):
    base = dict(connected=True, status=ACStatus.LIVE, in_pit=False, in_pit_lane=False,
                lap_position=pos, lap_valid=valid, tyres_out=0, speed_kmh=120.0,
                car_x=x, car_z=pos * 1000.0 if z is None else z)
    return SimpleNamespace(**{**base, **kw})


@pytest.fixture
def ref_line(monkeypatch):
    from accoach.coaching import lapvalid
    from accoach.trajectory import LinePoint
    points = [LinePoint(pos=i / 200, x=0.0, z=i * 5.0, speed_kmh=120.0, brake=0.0)
              for i in range(200)]
    monkeypatch.setattr(lapvalid, "line_points", lambda _ref: points)
    return REF


def run(coach, frames, corner=CORNER, ref=None, flying=True):
    said = []
    for i, f in enumerate(frames):
        said += coach.update(f, flying, i * 0.1, [corner], ref)
    return [c.message for c in said]


def lose_at(x):
    return [frame(0.42), frame(0.44, x=x), frame(0.45, valid=False, x=x),
            frame(0.48, valid=False, x=x), frame(0.51, valid=False, x=x)]


def test_the_reason_comes_from_the_side_of_the_line():
    assert lap_lost_reason(None) == "limits"
    assert lap_lost_reason(1.0) == lap_lost_reason(-1.0) == "limits"
    assert lap_lost_reason(3.0) == "cut"
    assert lap_lost_reason(-3.0) == "wide"


def test_it_waits_for_the_end_of_the_corner(ref_line):
    c = LapValidityCoach()
    assert run(c, lose_at(-5.0)[:4], ref=ref_line) == []


def test_wide_of_the_line_says_wide(ref_line):
    said = run(LapValidityCoach(), lose_at(5.0), ref=ref_line)
    assert len(said) == 1 and "uscito largo" in said[0]


def test_inside_of_the_line_says_cut(ref_line):
    said = run(LapValidityCoach(), lose_at(-5.0), ref=ref_line)
    assert len(said) == 1 and "tagliato" in said[0]


def test_on_the_line_or_without_a_reference_it_only_knows_the_limits(ref_line):
    assert "limiti" in run(LapValidityCoach(), lose_at(0.5), ref=ref_line)[0]
    assert "limiti" in run(LapValidityCoach(), lose_at(-5.0), ref=None)[0]


def test_a_chicane_has_no_inside(ref_line):
    chicane = SimpleNamespace(**{**vars(CORNER), "kind": "chicane"})
    assert "limiti" in run(LapValidityCoach(), lose_at(-5.0), chicane, ref_line)[0]


def test_unknown_coordinates_are_not_a_side(ref_line):
    frames = [frame(0.42, x=0.0, z=0.0), frame(0.45, valid=False, x=0.0, z=0.0),
              frame(0.51, valid=False, x=0.0, z=0.0)]
    assert "limiti" in run(LapValidityCoach(), frames, ref=ref_line)[0]


def test_once_a_lap_and_the_second_time_it_says_it_is_the_same(ref_line):
    c = LapValidityCoach()
    assert "largo" in run(c, lose_at(5.0), ref=ref_line)[0]
    assert run(c, [frame(0.6, valid=False, x=5.0)], ref=ref_line) == []
    c.new_lap()
    assert "stesso errore" in run(c, lose_at(5.0), ref=ref_line)[0]


def test_a_different_mistake_is_not_the_same_mistake(ref_line):
    c = LapValidityCoach()
    run(c, lose_at(5.0), ref=ref_line)
    c.new_lap()
    assert "tagliato" in run(c, lose_at(-5.0), ref=ref_line)[0]


def test_the_flag_still_down_at_the_line_is_not_a_new_invalidation():
    """Su ACC il flag e' 0 tutto il giro d'uscita e risale al traguardo."""
    c = LapValidityCoach()
    assert run(c, [frame(0.001, valid=False), frame(0.45, valid=False),
                   frame(0.6, valid=False)]) == []


def test_silent_on_the_out_lap_and_in_the_pits():
    assert run(LapValidityCoach(), lose_at(-5.0), flying=False) == []
    c = LapValidityCoach()
    frames = lose_at(-5.0)
    frames[-1].in_pit_lane = True
    assert run(c, frames) == []


def test_ac_counts_the_wheels_out():
    frames = [frame(0.42, valid=None), frame(0.45, valid=None, tyres_out=3),
              frame(0.51, valid=None)]
    assert "limiti" in run(LapValidityCoach(), frames)[0]


def test_it_does_not_wait_forever_outside_a_corner():
    c = LapValidityCoach()
    assert c.update(frame(0.2), True, 0.0, [], None) == []
    # Fuori curva la frase parte dal primo fotogramma dopo il punto.
    assert c.update(frame(0.2, valid=False), True, 1.0, [], None) == []
    assert c.update(frame(0.21, valid=False), True, 1.1, [], None) != []


def test_it_passes_every_gate():
    assert tier_of(CueCategory.LAP_INVALID) == CueTier.ACUTE
    assert CueCategory.LAP_INVALID in _SAFETY_CATEGORIES


def test_the_screen_names_the_corner_where_it_happened(ref_line):
    c = LapValidityCoach()
    said = []
    for i, f in enumerate(lose_at(5.0)):
        said += c.update(f, True, i * 0.1, [CORNER], ref_line)
    text = _name_the_corner(said[0], said[0].message, [CORNER], {1: "Curva 2"})
    assert text.startswith("Curva 2. Giro invalidato")


def test_every_phrase_is_recorded_and_translated():
    frasi = [p for p in spoken_phrases() if p.startswith("Giro invalidato")]
    assert len(frasi) == 4
    assert all(cue_text(p, "en") != p for p in frasi)
    for p in frasi:
        assert all(len(s.split()) <= 8 for s in p.replace(",", ".").split(".") if s.strip())


class _Cade(_SessioneCheParla):
    """Dal motore: il flag di ACC cade a meta' del terzo giro."""

    def _tick(self, **kw) -> None:
        kw["lap_valid"] = not (self.completed == 2 and kw.get("pos", 0.0) > 0.5)
        super()._tick(**kw)


def test_from_the_engine_it_is_said_once(tmp_path):
    s = _Cade(tmp_path)
    s.avvicinamento()
    lap = synth.build_lap(clean=True)
    for _ in range(4):
        s.giro(lap)
    detti = [g for g, c in s.detti if c is CueCategory.LAP_INVALID]
    assert detti == [2], f"giro invalidato detto ai giri {detti}"
    s.eng.close()
