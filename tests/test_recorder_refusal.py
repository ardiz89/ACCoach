"""When the recorder refuses a car that's plainly driving, it says so.

Every silent gate in this codebase has turned into a report of the form "I drove
and nothing happened". The recorder is the one where that costs the most: the
session can't be repeated. The flags it trusts (`in_pit`, `in_pit_lane`) live in
the half of the shared-memory page that AC1 and ACC lay out differently, and a
misread there is exactly how `surfaceGrip` sat at zero for months.

So a refusal that lasts while the car is at speed leaves one line naming which
flag was set. It is not a fix for a misread — it's what turns a lost session into
a diagnosable one.
"""
import logging
from dataclasses import replace

from accoach.recording.recorder import (
    _DRIVING_KMH,
    _REFUSAL_WARN_FRAMES,
    LapRecorder,
)
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

_DRIVING = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.PRACTICE,
    car_model="car", track="track", speed_kmh=_DRIVING_KMH + 60.0,
)


def _feed(rec: LapRecorder, frame, n: int) -> None:
    for _ in range(n):
        rec.update(frame)


def test_a_long_refusal_at_speed_is_logged(caplog):
    stuck = replace(_DRIVING, in_pit_lane=True)     # e.g. a misread flag
    rec = LapRecorder()
    with caplog.at_level(logging.WARNING):
        _feed(rec, stuck, _REFUSAL_WARN_FRAMES)
    assert any("not recording" in r.message for r in caplog.records)
    assert any("in_pit_lane=True" in r.getMessage() for r in caplog.records)


def test_it_warns_once_not_every_frame(caplog):
    stuck = replace(_DRIVING, in_pit_lane=True)
    rec = LapRecorder()
    with caplog.at_level(logging.WARNING):
        _feed(rec, stuck, _REFUSAL_WARN_FRAMES * 3)
    hits = [r for r in caplog.records if "not recording" in r.message]
    assert len(hits) == 1


def test_a_real_pit_stop_never_trips_it(caplog):
    """Standing in the box is a refusal, but the car isn't driving."""
    parked = replace(_DRIVING, speed_kmh=0.0, in_pit=True)
    rec = LapRecorder()
    with caplog.at_level(logging.WARNING):
        _feed(rec, parked, _REFUSAL_WARN_FRAMES * 2)
    assert not caplog.records


def test_crawling_down_the_pit_lane_never_trips_it(caplog):
    """Pit-lane speed limiters sit well under the driving threshold."""
    crawling = replace(_DRIVING, speed_kmh=_DRIVING_KMH - 10.0, in_pit_lane=True)
    rec = LapRecorder()
    with caplog.at_level(logging.WARNING):
        _feed(rec, crawling, _REFUSAL_WARN_FRAMES * 2)
    assert not caplog.records


def test_the_counter_resets_when_recording_resumes(caplog):
    stuck = replace(_DRIVING, in_pit_lane=True)
    rec = LapRecorder()
    with caplog.at_level(logging.WARNING):
        _feed(rec, stuck, _REFUSAL_WARN_FRAMES - 1)   # one short of warning
        _feed(rec, _DRIVING, 5)                       # back on track
        _feed(rec, stuck, _REFUSAL_WARN_FRAMES - 1)   # short again
    assert not caplog.records, "two near-misses must not add up to a warning"
