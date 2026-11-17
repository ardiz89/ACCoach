"""Costanza del pilota: quali giri di un gruppo sono incostanti (modulo puro)."""

from accoach.engineer.consistency import inconsistent, same_dials, slow_corners
from accoach.engineer.core import LapStats

APICI = (0.10, 0.25, 0.45, 0.65, 0.85)


def giro(velocita, apici=APICI):
    nomi = ("A", "B", "C", "D", "E")
    return LapStats(
        lap_time_ms=90000,
        corner_vmin=tuple((a, v, n) for a, v, n in zip(apici, velocita, nomi)),
    )


BASE = (100.0, 80.0, 120.0, 90.0, 70.0)


def meno(delta, quante):
    return tuple(v - delta if i < quante else v for i, v in enumerate(BASE))


def test_lento_in_tre_curve_e_incostante():
    laps = [giro(BASE), giro(BASE), giro(meno(6, 3))]
    r = inconsistent(laps)
    assert list(r) == [2]
    assert len(r[2]) == 3
    assert r[2][0][1] == 6.0


def test_lento_in_due_curve_no():
    assert inconsistent([giro(BASE), giro(BASE), giro(meno(6, 2))]) == {}


def test_lento_di_poco_no():
    assert inconsistent([giro(BASE), giro(BASE), giro(meno(4.9, 5))]) == {}


def test_piu_veloce_no():
    assert inconsistent([giro(BASE), giro(BASE), giro(meno(-10, 5))]) == {}


def test_due_giri_soli():
    assert inconsistent([giro(BASE), giro(meno(6, 5))]) == {}


def test_apici_spostati_si_accoppiano():
    spostati = tuple(a + 0.004 for a in APICI)
    altro = LapStats(
        lap_time_ms=1,
        corner_vmin=tuple(reversed(giro(meno(6, 3), spostati).corner_vmin)),
    )
    r = inconsistent([giro(BASE), giro(BASE), altro])
    assert list(r) == [2] and len(r[2]) == 3


def _uno(a, b):
    lap = LapStats(lap_time_ms=1, corner_vmin=((a, 50.0, "X"),))
    altri = [LapStats(lap_time_ms=1, corner_vmin=((b, 60.0, "X"),))] * 2
    return slow_corners(lap, altri)


def test_apice_sul_cerchio():
    assert _uno(0.998, 0.002) == [("X", 10.0)]


def test_apici_lontani_non_si_accoppiano():
    assert _uno(0.30, 0.32) == []


def test_servono_due_altri():
    lap = LapStats(lap_time_ms=1, corner_vmin=((0.3, 50.0, "X"),))
    uno = [LapStats(lap_time_ms=1, corner_vmin=((0.3, 60.0, "X"),))]
    assert slow_corners(lap, uno) == []


def test_same_dials():
    assert same_dials((3, 4, 0, 0.64), (4, 4, 0, 0.64)) is False
    assert same_dials((3, 4, 0, 0.64), (-1, -1, -1, -1.0)) is True
    assert same_dials((3, 4, 0, 0.64), (3, 4, 0, 0.642)) is False
    assert same_dials((3, 4, 0, 0.64), (3, 4, 0, 0.6405)) is True
