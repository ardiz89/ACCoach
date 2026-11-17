"""L'Ingegnere misura tutti i giri di una serata sulle stesse curve.

Il controllo di costanza confronta i giri curva per curva. Fino al 17/11
l'Ingegnere riceveva le curve del riferimento del coach, che il motore rifà a
ogni nuovo miglior giro: la chiave delle curve cambiava e il gruppo ricominciava,
quindi mentre il pilota migliorava non si giudicava niente; senza riferimento
ogni giro trovava le sue curve e non si giudicava mai. Ora le curve
dell'Ingegnere si fissano quando nasce (quelle del riferimento di quel momento)
o, senza riferimento, sul primo giro pulito e valido.
"""
import dataclasses

import pytest

import synth
from accoach.coaching.diagnosis import build_lap_stats
from accoach.engine import CoachEngine
from accoach.telemetry.snapshot import TelemetrySnapshot
from accoach.track import detect_corners


class _Reader:
    def __init__(self):
        self.snap = TelemetrySnapshot.disconnected()

    def read(self):
        return self.snap

    def close(self):
        pass


def _corners_a():
    return detect_corners(synth.build_lap().samples)


def _shifted(corners, d):
    return [dataclasses.replace(c, entry_pos=c.entry_pos + d,
                                apex_pos=c.apex_pos + d, exit_pos=c.exit_pos + d)
            for c in corners]


def _key(corners):
    return build_lap_stats(synth.build_lap(), corners).corners_key


class _Bench:
    """Un motore vero; il riferimento lo decide il test."""

    def __init__(self, tmp_path):
        (tmp_path / "laps").mkdir()
        self.reader = _Reader()
        self.eng = CoachEngine(reader=self.reader, laps_dir=tmp_path / "laps",
                               engineer_voice=False)
        self.ref_corners: list = []
        self.ref_names: dict = {}
        self.eng._rebuild_reference = self._fake_rebuild
        self.seen = []
        self._t = 0.0

    def _fake_rebuild(self, car, track):
        self.eng._corners = list(self.ref_corners)
        self.eng._corner_names = dict(self.ref_names)

    def arrive(self, track="monza"):
        """Il motore vede auto e pista: nasce l'Ingegnere della serata."""
        self.reader.snap = synth.snap(pos=0.1, track=track)
        self._t += 0.1
        self.eng.tick(self._t)
        engineer = self.eng._engineer
        original = engineer.observe

        def spy(stats):
            self.seen.append(stats)
            return original(stats)

        engineer.observe = spy

    def lap(self, **kw):
        self.eng._observe_lap(synth.build_lap(**kw))
        return self.seen[-1]

    def close(self):
        self.eng.close()


@pytest.fixture
def bench(tmp_path):
    b = _Bench(tmp_path)
    try:
        yield b
    finally:
        b.close()


def test_a_new_best_does_not_move_the_engineers_corners(bench):
    a = _corners_a()
    bench.ref_corners = a
    bench.arrive()
    b = _shifted(a, 0.05)
    bench.eng._corners = b                     # nuovo miglior giro, curve rifatte
    stats = bench.lap(clean=True)
    assert stats.corners_key == _key(a)
    assert stats.corners_own is False
    assert bench.eng._corners == b             # il coach insegue il riferimento


def test_without_a_reference_the_first_clean_lap_fixes_the_corners(bench):
    bench.arrive()
    dirty = bench.lap(clean=False)
    assert dirty.corners_own is True
    assert bench.eng._engineer_corners == []
    first = bench.lap(clean=True)
    assert first.corners_own is False
    assert bench.eng._engineer_corners
    # Un giro che, cercandole da solo, troverebbe l'apice della seconda curva
    # altrove (0,7025 invece di 0,71): misurato sulle curve della serata.
    third = bench.lap(clean=True, slow_corner=1, amt=40)
    assert third.corners_key == first.corners_key
    assert third.corners_own is False
    assert [a for a, _, _ in third.corner_vmin] == [a for a, _, _ in first.corner_vmin]


def test_an_incomplete_lap_does_not_fix_the_corners(bench):
    bench.arrive()
    bench.lap(valid=False, clean=True)
    assert bench.eng._engineer_corners == []


def test_a_reference_arriving_later_does_not_replace_fixed_corners(bench):
    bench.arrive()
    first = bench.lap(clean=True)
    bench.eng._corners = _shifted(_corners_a(), 0.05)
    later = bench.lap(clean=True)
    assert later.corners_key == first.corners_key


def test_a_new_track_fixes_the_corners_again(bench):
    a = _corners_a()
    bench.ref_corners = a
    bench.arrive("monza")
    c = _shifted(a, 0.05)
    bench.ref_corners = c
    bench.arrive("imola")
    assert bench.eng._engineer_corners == c


def test_a_new_track_without_a_reference_starts_empty(bench):
    bench.arrive("monza")
    bench.lap(clean=True)
    assert bench.eng._engineer_corners
    bench.arrive("imola")
    assert bench.eng._engineer_corners == []


def test_a_reference_from_another_layout_gives_way_to_the_first_clean_lap(bench):
    """Su Assetto Corsa la pista non dice il layout: il riferimento puo' essere
    un giro del GP mentre si gira sull'Indy. Se le curve del primo giro pulito
    non stanno su quelle del riferimento, la serata si misura sulle sue."""
    a = _corners_a()
    bench.ref_corners = _shifted(a, 0.2)       # nessun apice in comune
    bench.arrive()
    first = bench.lap(clean=True)
    assert first.corners_key == _key(a)
    later = bench.lap(clean=True)
    assert later.corners_key == _key(a)


def test_a_reference_that_fits_the_first_clean_lap_is_kept(bench):
    a = _corners_a()
    near = _shifted(a, 0.004)                  # stesse curve, rilevate un poco diverse
    bench.ref_corners = near
    bench.arrive()
    first = bench.lap(clean=True)
    assert first.corners_key == _key(near)


def test_names_follow_the_catalog_for_the_evening_corners(bench, monkeypatch):
    """Le curve restano quelle della serata, i nomi no: un nome scritto dal
    pilota a meta' serata, o un cambio di lingua, arrivano al giro dopo."""
    import accoach.engine as engine_mod
    catalog = {"names": ("Tosa", "Rivazza")}
    monkeypatch.setattr(engine_mod, "_corner_labels",
                        lambda car, track, corners, laps_dir: {
                            c.index: n for c, n in zip(corners, catalog["names"])})
    a = _corners_a()
    bench.ref_corners = a
    bench.arrive()
    stats = bench.lap(clean=True)
    assert {name for _, _, name in stats.corner_vmin} == {"Tosa", "Rivazza"}
    catalog["names"] = ("Tosa", "Piratella")
    stats = bench.lap(clean=True)
    assert {name for _, _, name in stats.corner_vmin} == {"Tosa", "Piratella"}
    assert stats.corners_key == _key(a)


def test_corners_fixed_from_a_lap_take_their_names_from_the_catalog(bench, monkeypatch):
    import accoach.engine as engine_mod
    monkeypatch.setattr(engine_mod, "_corner_labels",
                        lambda car, track, corners, laps_dir: {
                            c.index: n for c, n in zip(corners, ("Tosa", "Rivazza"))})
    bench.arrive()
    stats = bench.lap(clean=True)
    assert {name for _, _, name in stats.corner_vmin} == {"Tosa", "Rivazza"}
