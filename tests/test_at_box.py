"""«Fermo ai box»: una regola sola, calcolata dal motore e mandata nel frame.

La pagina non deve rifare il conto da `in_pit`: su ACC quel campo non si accende
mai con l'auto ferma nella piazzola (vedi coaching/pitcall.py).
"""
import re
from dataclasses import replace
from pathlib import Path

import synth
from accoach.coaching.pitcall import stopped_in_box
from accoach.serialize import snapshot_to_dict

_ENGINEER_JS = (Path(__file__).resolve().parent.parent
                / "src" / "accoach" / "web" / "engineer.js")


def _s(**kw):
    return replace(synth.LIVE, **kw)


def test_acc_standing_in_the_box_is_at_box():
    s = _s(in_pit=False, in_pit_lane=True, speed_kmh=0.0)
    assert stopped_in_box(s) is True
    assert snapshot_to_dict(s)["at_box"] is True


def test_rolling_down_the_pit_lane_is_not_at_box():
    s = _s(in_pit=False, in_pit_lane=True, speed_kmh=60.0)
    assert stopped_in_box(s) is False
    assert snapshot_to_dict(s)["at_box"] is False


def test_in_pit_alone_is_at_box():
    assert stopped_in_box(_s(in_pit=True, in_pit_lane=False, speed_kmh=0.0)) is True


def test_stopped_on_track_is_not_at_box():
    assert stopped_in_box(_s(in_pit=False, in_pit_lane=False, speed_kmh=0.0)) is False


def test_threshold_is_the_briefing_one():
    assert stopped_in_box(_s(in_pit_lane=True, speed_kmh=1.0)) is True
    assert stopped_in_box(_s(in_pit_lane=True, speed_kmh=1.01)) is False


def test_pit_reminder_reads_at_box():
    src = _ENGINEER_JS.read_text(encoding="utf-8")
    start = src.index("function renderPitReminder")
    m = re.search(r"\n}\n", src[start:])
    body = src[start:start + m.end()]
    assert "st.at_box" in body
    assert "st.in_pit" not in body
