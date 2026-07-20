"""Track grip extraction, which the two games keep at different offsets.

Same layout split as ``_car_xz``: our struct declares the ACC page, where
``surfaceGrip`` sits at 1240 — past ``activeCars``, ``carCoordinates[60][3]``,
``carID[60]``, ``playerCarID`` and ``penalty``. AC1 has none of those, so its
``surfaceGrip`` is at 280, 28 bytes past ``activeCars``.

(Regression: reading AC-recorded laps ACC-style landed 960 bytes past the end of
the AC1 page, so every lap on disk carried ``grip = 0.0``.)"""
import ctypes
import struct

import pytest

from accoach.telemetry.reader import SharedMemoryReader
from accoach.telemetry.structs import SPageFileGraphics


def _as_ac1(g: SPageFileGraphics, grip: float) -> None:
    """Lay the AC1 graphics page out inside our ACC-shaped struct.

    AC1 order from ``activeCars`` on: x, y, z, penaltyTime, flag, idealLineOn,
    isInPitLane, surfaceGrip — so grip lands 28 bytes in. ``activeCars`` itself
    holds the X coordinate as float bits, which is how the reader spots AC1.
    """
    g.activeCars = struct.unpack("<i", struct.pack("<f", -202.98))[0]
    base = ctypes.addressof(g) + SPageFileGraphics.activeCars.offset
    ctypes.c_float.from_address(base + 28).value = grip


def test_offsets_match_the_two_layouts():
    # Guards the constant in _surface_grip: if the struct ever grows a field
    # before surfaceGrip, this catches it instead of silently reading garbage.
    assert SPageFileGraphics.surfaceGrip.offset == 1240
    assert SPageFileGraphics.activeCars.offset + 28 == 280


def test_grip_acc_layout():
    g = SPageFileGraphics()
    g.activeCars = 1                     # ACC fills a real car count
    g.surfaceGrip = 0.97
    assert SharedMemoryReader._surface_grip(g) == pytest.approx(0.97, abs=1e-6)


def test_grip_ac1_layout():
    g = SPageFileGraphics()
    _as_ac1(g, 0.85)
    # The ACC slot stays empty: reading it there is exactly the old bug.
    assert g.surfaceGrip == 0.0
    assert SharedMemoryReader._surface_grip(g) == pytest.approx(0.85, abs=1e-6)


def test_grip_out_of_range_reads_as_no_data():
    # Grip is a fraction; anything else means we're reading the wrong bytes and
    # must not reach the reference picker as if it were a real measurement.
    g = SPageFileGraphics()
    g.activeCars = 1
    for bogus in (-3.0, 42.0, 1.5):
        g.surfaceGrip = bogus
        assert SharedMemoryReader._surface_grip(g) == 0.0


def test_grip_ac1_out_of_range_reads_as_no_data():
    g = SPageFileGraphics()
    _as_ac1(g, 12345.0)
    assert SharedMemoryReader._surface_grip(g) == 0.0
