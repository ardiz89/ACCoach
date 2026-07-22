"""An invalidated lap loses its delta, and nothing else.

Two separate rules, and the distinction is the whole point.

The delta is a stopwatch reading. On a lap the game has already thrown away there
is no stopwatch, so a number telling the driver they're 0.3 up on the reference is
measuring a race that won't happen. It goes.

Everything else stays. An invalidated lap is a free lap: braking points, lock-ups,
tyre temperatures and setup all read the same as on a counting one, and the panel's
position was explicit — you switch off what has the clock as its metric, not the
coaching. So this must NOT become another `quiet` reason.
"""
from accoach.engine import CoachEngine
from accoach.recording.storage import save_lap
from accoach.serialize import state_to_dict

import synth

from test_engine_gate import _StubReader, _crossing, _run


def _engine(tmp_path, frames):
    save_lap(synth.build_lap(), tmp_path)
    eng = CoachEngine(reader=_StubReader(frames), voice=None, laps_dir=tmp_path)
    return eng


def _last_state(tmp_path, frames):
    eng = _engine(tmp_path, frames)
    st = None
    now = 0.0
    for _ in range(len(frames)):
        st = eng.tick(now)
        now += 0.05
    eng.close()
    return st


def test_a_flying_lap_the_game_invalidated_is_flagged(tmp_path):
    frames = [synth.snap(pos=0.5)] + _crossing()
    frames += [synth.snap(pos=0.3, completed_laps=1, lap_valid=False)] * 3
    assert _last_state(tmp_path, frames).lap_invalid is True


def test_a_valid_flying_lap_is_not(tmp_path):
    frames = [synth.snap(pos=0.5)] + _crossing()
    frames += [synth.snap(pos=0.3, completed_laps=1, lap_valid=True)] * 3
    assert _last_state(tmp_path, frames).lap_invalid is False


def test_ac_never_claims_a_lap_is_invalidated(tmp_path):
    """On AC the flag is ``None`` — the page ends before that offset.

    Absence of evidence, so the delta stays. Treating ``None`` as False here would
    blank the delta on every AC lap ever driven.
    """
    frames = [synth.snap(pos=0.5)] + _crossing()
    frames += [synth.snap(pos=0.3, completed_laps=1, lap_valid=None)] * 3
    assert _last_state(tmp_path, frames).lap_invalid is False


def test_the_out_lap_does_not_report_itself_as_invalidated(tmp_path):
    """ACC holds the flag at 0 for the whole out lap — true, and useless.

    The driver saw exactly this and read it as "I've been penalised". The out lap
    has its own message, and it's the one that answers the question.
    """
    frames = [synth.snap(pos=0.5, lap_valid=False)] * 6
    st = _last_state(tmp_path, frames)
    assert st.lap_invalid is False
    assert st.quiet == "out_lap"


def test_it_is_not_a_gate_the_coach_keeps_talking(tmp_path):
    """The distinction that matters: no delta, but still coaching.

    If `lap_invalid` ever turns into a `quiet` reason this fails, which is the
    point — a cut corner would silence the lap's other twenty corners.
    """
    save_lap(synth.build_lap(), tmp_path)
    from accoach.comparison import Reference
    ontime = int(Reference(synth.build_lap()).time_at(0.5))
    frames = [synth.snap(pos=0.5)] + _crossing()
    frames += [synth.snap(pos=0.5, completed_laps=1, current_lap_ms=ontime,
                          speed_kmh=150.0, throttle=0.0, brake=0.0,
                          lap_valid=False) for _ in range(25)]
    eng = CoachEngine(reader=_StubReader(frames), voice=None, laps_dir=tmp_path)
    spoken = _run(eng, frames)
    assert any(c.category.value == "coasting" for c in spoken), \
        "an invalidated lap is a free lap, not a silent one"
    eng.close()


def test_the_frontend_is_told(tmp_path):
    frames = [synth.snap(pos=0.5)] + _crossing()
    frames += [synth.snap(pos=0.3, completed_laps=1, lap_valid=False)] * 3
    assert state_to_dict(_last_state(tmp_path, frames))["lap_invalid"] is True


def test_the_overlay_has_words_for_it():
    """A blanked delta with no explanation is the silent gate all over again."""
    from accoach.i18n import t
    for lang in ("en", "it"):
        assert t("overlay.lap_invalid", lang=lang) != "overlay.lap_invalid"
