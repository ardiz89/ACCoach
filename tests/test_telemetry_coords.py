"""Player world-coordinate extraction for the track map.

The graphics page lays carCoordinates out differently on the two games:
ACC has an ``activeCars`` int then ``carCoordinates[60][3]`` (player at
``playerCarID``); AC1 has no ``activeCars`` and just the player's own
``float[3]``, sitting 4 bytes earlier. ``_car_xz`` must read X/Z correctly on
both. (Regression: on AC1 the old code returned (elevation, 0).)"""
import struct

import pytest

from accoach.telemetry.reader import SharedMemoryReader
from accoach.telemetry.structs import SPageFileGraphics


def test_car_xz_acc_layout():
    g = SPageFileGraphics()
    g.activeCars = 1                 # ACC fills a real car count
    g.playerCarID = 3
    g.carCoordinates[3][0] = 10.0    # x
    g.carCoordinates[3][1] = 5.0     # y (elevation, ignored)
    g.carCoordinates[3][2] = 20.0    # z
    out = SharedMemoryReader._car_xz(g)
    assert out["car_x"] == pytest.approx(10.0)
    assert out["car_z"] == pytest.approx(20.0)


def test_car_xz_ac1_layout():
    g = SPageFileGraphics()
    # AC1: the player's (x, y, z) starts at the activeCars offset, so x lands in
    # the activeCars int slot (here as raw float bits) and (y, z) in
    # carCoordinates[0][0..1]. activeCars reinterpreted as int is far outside
    # 1..60, which is how we detect AC1.
    g.activeCars = struct.unpack("<i", struct.pack("<f", -202.98))[0]
    g.carCoordinates[0][0] = -123.0      # AC1 y (elevation) — must be ignored
    g.carCoordinates[0][1] = -710.14     # AC1 z
    out = SharedMemoryReader._car_xz(g)
    assert out["car_x"] == pytest.approx(-202.98, abs=1e-2)
    assert out["car_z"] == pytest.approx(-710.14, abs=1e-2)
