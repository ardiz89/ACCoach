"""La misura nel giro: velocita' minima per curva e manopole sul LapStats."""
from __future__ import annotations

from accoach.coaching.diagnosis import build_lap_stats
from accoach.track import detect_corners

from synth import build_lap


def test_lap_stats_carry_min_speed_per_corner():
    lap = build_lap()
    corners = detect_corners(lap.samples)
    stats = build_lap_stats(lap, corners)
    assert [round(v) for _, v, _ in stats.corner_vmin] == [120, 95]
    assert [a for a, _, _ in stats.corner_vmin] == [c.apex_pos for c in corners]


def test_corner_names_ride_along():
    lap = build_lap()
    corners = detect_corners(lap.samples)
    stats = build_lap_stats(lap, corners, {corners[0].index: "Tosa"})
    assert [n for _, _, n in stats.corner_vmin] == ["Tosa", ""]


def test_lap_stats_carry_the_dials():
    lap = build_lap()
    assert build_lap_stats(lap).dials == (-1, -1, -1, -1.0)
    lap.tc_level, lap.abs_level, lap.engine_map, lap.brake_bias = 3, 4, 0, 0.64
    assert build_lap_stats(lap).dials == (3, 4, 0, 0.64)
