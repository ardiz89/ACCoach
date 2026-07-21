"""Knowing which title is on the other end, once, instead of four times.

Four places re-derived "is this ACC?" from ``0 < activeCars <= 60``, and the
reason they need it isn't only the diverging page layout: some fields are
*declared* by both games and *filled* by one. ``brakeTemp`` is the live example —
measured at Spa on AC it sat frozen at [16.2, 16.2, 16.5, 16.5] for seconds at
315 km/h while the tyre core temps moved every single frame. Shown as a number it
reads as a measurement, which is worse than showing nothing.
"""
import ctypes

from accoach.telemetry.reader import SharedMemoryReader
from accoach.telemetry.structs import SPageFileGraphics


def _graphics(active_cars: int) -> SPageFileGraphics:
    g = SPageFileGraphics()
    g.activeCars = active_cars
    return g


def test_a_real_car_count_means_acc():
    for n in (1, 20, 60):
        assert SharedMemoryReader._is_acc(_graphics(n)) is True


def test_ac1_puts_a_float_in_that_slot():
    """On AC1 the slot holds the player's X as a float — never 1..60 as an int."""
    g = _graphics(0)
    base = ctypes.addressof(g) + SPageFileGraphics.activeCars.offset
    for x in (-412.5, 0.0, 1873.25):
        ctypes.c_float.from_address(base).value = x
        assert SharedMemoryReader._is_acc(g) is False


def test_out_of_range_counts_are_not_acc():
    for n in (0, -1, 61, 1130392598):      # the value measured live on AC1
        assert SharedMemoryReader._is_acc(_graphics(n)) is False


def test_the_layout_readers_all_agree_with_it():
    """Whatever _is_acc says, the fields that branch on it must follow."""
    for n, acc in ((20, True), (0, False)):
        g = _graphics(n)
        g.isInPitLane = 1
        g.penalty = 3
        assert SharedMemoryReader._is_acc(g) is acc
        assert SharedMemoryReader._in_pit_lane(g) is acc
        assert (SharedMemoryReader._penalty(g) == 3) is acc
