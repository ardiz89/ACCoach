"""The braking sheet: your own points, measured, never generalised.

The value of this feature is entirely in what it refuses to do — invent a row for
a corner you don't brake for, average away a mistake, or report a number as a
reference when it was measured once. So that's what's pinned here.
"""
import pytest

from accoach.braking_points import (
    _MIN_BRAKE_PEAK,
    BrakingSheet,
    brake_points_of_lap,
    build_sheet,
)
from accoach.track import detect_corners

import synth


def _corners():
    return detect_corners(synth.build_lap().samples)


def test_it_finds_a_braking_point_for_each_braking_corner():
    lap = synth.build_lap()
    pts = brake_points_of_lap(lap, _corners())
    assert len(pts) == 2, "the synthetic lap brakes for both its corners"
    for p in pts:
        assert p.speed_kmh > p.vmin_kmh, "you brake before you're slow"
        assert p.peak_brake >= _MIN_BRAKE_PEAK


def test_the_braking_zone_is_measured_along_the_road():
    """Metres from the pedal to the slowest point — the thing that changes when
    you brake later, and the only distance on the sheet."""
    pts = brake_points_of_lap(synth.build_lap(), _corners())
    assert all(p.distance_m > 0 for p in pts)


def test_a_lap_without_coordinates_still_gives_a_speed_but_no_distance():
    """Pre-v3 laps have no map. The speed on the dash is still a braking
    reference; the length of the zone can't be measured, so it isn't reported."""
    lap = synth.build_lap()
    for s in lap.samples:
        s.car_x = s.car_z = 0.0
    pts = brake_points_of_lap(lap, _corners())
    assert pts and all(p.distance_m == 0.0 for p in pts)
    assert all(p.speed_kmh > 0 for p in pts)


def test_a_corner_you_do_not_brake_for_gets_no_row():
    """A brush of the pedal on a flat-out kink is not a braking point, and a
    sheet that lists it teaches a reference that doesn't exist."""
    lap = synth.build_lap()
    for s in lap.samples:
        s.brake = min(s.brake, 0.10)
    assert brake_points_of_lap(lap, _corners()) == []


def test_the_sheet_reports_the_median_not_the_mean():
    """One aborted braking must not move the number the driver is told to aim
    for. Four laps braking at the same speed, one panicking 60 km/h earlier."""
    corners = _corners()
    laps = [synth.build_lap() for _ in range(4)]
    odd = synth.build_lap()
    for s in odd.samples:
        s.speed_kmh += 60.0          # braked from far higher speed, once
    sheet = build_sheet(laps + [odd], corners)
    normal = brake_points_of_lap(laps[0], corners)[0].speed_kmh
    assert sheet.rows[0].speed_kmh == pytest.approx(normal, abs=1)


def test_the_spread_says_whether_you_have_a_braking_point_at_all():
    corners = _corners()
    same = build_sheet([synth.build_lap() for _ in range(3)], corners)
    assert same.rows[0].speed_spread_kmh == 0

    laps = [synth.build_lap() for _ in range(3)]
    for s in laps[2].samples:
        s.speed_kmh += 25.0
    varied = build_sheet(laps, corners)
    assert varied.rows[0].speed_spread_kmh >= 20


def test_a_corner_braked_for_in_a_minority_of_laps_is_left_out():
    """Braking once in five laps for a corner is a mistake, not a reference."""
    corners = _corners()
    laps = [synth.build_lap() for _ in range(4)]
    for lap in laps[1:]:
        for s in lap.samples:
            if 0.55 <= s.pos <= 0.80:      # never brake for the second corner
                s.brake = 0.0
    sheet = build_sheet(laps, corners)
    assert [r.index for r in sheet.rows] == [0]


def test_the_gear_is_the_most_common_one_not_an_average():
    """Gears are labels: "R", "N", "3". The mean of a gear is not a gear."""
    corners = _corners()
    laps = [synth.build_lap() for _ in range(3)]
    for s in laps[0].samples:
        s.gear = "5"
    sheet = build_sheet(laps, corners)
    assert sheet.rows[0].gear == "4"       # synth drives in 4th; 5 appears once


def test_the_sheet_carries_the_conditions_it_was_measured_in():
    """A braking point without its track temperature is the static cheat sheet
    all over again — the thing this is meant to replace."""
    sheet = build_sheet([synth.build_lap()], _corners(),
                        road_temps=[31.0, 34.5, 33.0])
    assert sheet.road_temp_from == 31.0 and sheet.road_temp_to == 34.5
    assert sheet.laps == 1


def test_no_laps_is_an_empty_sheet_not_a_crash():
    assert build_sheet([], _corners()) == BrakingSheet(laps=0)


def _lap_braking_at(pos_onset: float):
    """A lap that brakes hard starting exactly at ``pos_onset``.

    Hand-built rather than taken from synth: the point of the next test is that
    the landmark lands on the braking *point*, so the braking point has to be
    somewhere we choose, not wherever the synthetic circuit happens to put it.
    """
    from accoach.recording.lap import Lap, LapSample
    from accoach.telemetry.snapshot import SessionType

    s = []
    for i in range(400):
        pos = i / 399
        braking = pos_onset <= pos < pos_onset + 0.03
        s.append(LapSample(
            int(pos * 100000), pos,
            90.0 if pos >= pos_onset + 0.03 else 250.0,
            0.0 if braking else 1.0, 0.9 if braking else 0.0,
            0.2 if pos >= pos_onset else 0.0, "4", 8000, 0.0, 0.0,
            car_x=1000.0 * pos, car_z=0.0))
    return Lap("ferrari_488_gt3", "monza", SessionType.PRACTICE, 100000, True,
               samples=s)


def test_a_curated_landmark_describes_the_braking_point():
    """Monza's braking zones are measured and sourced (trackdata). Where a
    landmark exists it beats every number on the row, so it has to arrive — and
    it has to be looked up at the point the driver brakes, not at the apex."""
    from accoach.track import Corner
    from accoach.trackdata import _LANDMARKS

    it_text, _, pos = _LANDMARKS["monza"][1]        # Roggia, 0.337
    corner = Corner(index=0, entry_pos=pos - 0.02, apex_pos=pos + 0.03,
                    exit_pos=pos + 0.06)
    sheet = build_sheet([_lap_braking_at(pos)], [corner],
                        track="monza", lang="it")
    assert sheet.rows[0].landmark == it_text


def test_a_track_we_have_no_landmarks_for_stays_on_the_numbers():
    """No nearest-thing fallback: a landmark from another circuit, or the wrong
    corner of this one, is a confident wrong answer — worse here than silence."""
    from accoach.track import Corner

    corner = Corner(index=0, entry_pos=0.30, apex_pos=0.36, exit_pos=0.40)
    sheet = build_sheet([_lap_braking_at(0.337)], [corner],
                        track="not-a-real-track", lang="it")
    assert sheet.rows[0].landmark is None
    assert sheet.rows[0].speed_kmh > 0


def test_the_spread_is_also_given_in_metres_of_braking_point():
    """km/h is the reference you use in the car; metres is the unit the shared
    sheets are written in, and the one that makes 12 km/h stop sounding small."""
    from accoach.braking_points import _spread_metres

    # Braking from 250 to 100 over 180 m: a 15 km/h spread is a tenth of the
    # speed drop, so a tenth of the zone — 18 m of braking point.
    assert _spread_metres(15, 250, 100, 180) == 18
    # No coordinates on the lap: no distance to scale, so no metres invented.
    assert _spread_metres(15, 250, 100, 0) == 0.0
    # A corner you don't actually slow for can't produce a ratio.
    assert _spread_metres(15, 100, 100, 180) == 0.0
