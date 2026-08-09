"""FuelEngineer: burn-rate tracking and laps-remaining warnings."""
from dataclasses import replace

from accoach.coaching.fuel import FuelEngineer
from accoach.coaching.cue import CueCategory
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

_BASE = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.RACE,
)


def _lap(eng, fuel, now=0.0, in_pit=False, frames=10, in_pit_lane=False):
    out = []
    for i in range(frames):
        pos = i / frames + 0.001
        out += eng.update(replace(_BASE, lap_position=pos, fuel=fuel,
                                  in_pit=in_pit, in_pit_lane=in_pit_lane), now)
        now += 0.1
    out += eng.update(replace(_BASE, lap_position=0.01, fuel=fuel,
                              in_pit=in_pit, in_pit_lane=in_pit_lane), now)
    return out, now + 0.1


def test_warning_sequence():
    eng = FuelEngineer()
    out, now = _lap(eng, 12.0)          # baseline
    assert out == []
    out, now = _lap(eng, 9.5, now)      # burn 2.5; remaining 3.8 -> none
    assert out == []
    out, now = _lap(eng, 7.0, now)      # remaining 2.8 -> floor "2 giri"
    assert any("2 giri" in c.message for c in out)
    out, now = _lap(eng, 4.5, now)      # remaining 1.8 -> floor "1 giro"
    assert any("1 giro" in c.message for c in out)
    out, now = _lap(eng, 2.0, now)      # remaining 0.8 -> last lap
    assert any(c.category is CueCategory.FUEL and "Ultimo giro" in c.message for c in out)


def test_each_warning_once():
    eng = FuelEngineer()
    out, now = _lap(eng, 12.0)
    out, now = _lap(eng, 9.5, now)
    out, now = _lap(eng, 7.0, now)      # remaining 2.8 -> floor "2 giri", once
    assert sum("2 giri" in c.message for c in out) == 1
    out2, now = _lap(eng, 6.0, now)     # remaining 2.4: no new threshold crossed
    assert not any("2 giri" in c.message for c in out2)


def test_refuel_resets():
    eng = FuelEngineer()
    out, now = _lap(eng, 12.0)
    out, now = _lap(eng, 9.5, now)
    out, now = _lap(eng, 7.0, now)      # remaining 2.8 -> floor "2 giri"
    assert any("2 giri" in c.message for c in out)
    out, now = _lap(eng, 30.0, now, in_pit=True)   # refuel
    assert out == []
    out, now = _lap(eng, 27.5, now)
    f, fired = 27.5, False
    while f > 5.0:
        f -= 2.5
        out, now = _lap(eng, f, now)
        if any("3 giri" in c.message for c in out):
            fired = True
            break
    assert fired


def test_pit_lap_not_counted():
    eng = FuelEngineer()
    out, now = _lap(eng, 12.0)
    out, now = _lap(eng, 11.8, now, in_pit=True)
    assert out == []


# I tre test qui sotto misurano la stessa cosa da tre lati: un giro che ha
# toccato la corsia box non entra nella media dei consumi. La sequenza di
# benzina e' la stessa in tutti e tre, e i numeri sono scelti perche' la
# differenza si veda:
#   12.0 -> baseline
#   11.7 -> il giro dei box: dietro al limitatore si consuma poco (0.3 L)
#    9.2 -> giro normale, 2.5 L
#    6.7 -> giro normale, 2.5 L
# Se lo 0.3 finisce nella media, il consumo medio scende a 1.77 L/giro e la
# stima dice 3.8 giri rimasti: l'ingegnere tace. Contando solo i due giri veri
# la media e' 2.5 L/giro, restano 2.7 giri e l'avviso parte.
def _stint_with_a_pit_lap(**pit_flags):
    eng = FuelEngineer()
    out, now = _lap(eng, 12.0)
    out, now = _lap(eng, 11.7, now, **pit_flags)
    out, now = _lap(eng, 9.2, now)
    out, now = _lap(eng, 6.7, now)
    return out


def test_pit_lane_lap_not_counted():
    # La riga misurata in pista il 07/08 con l'auto ferma nella piazzola su ACC:
    # in_pit=False, in_pit_lane=True. In tutto cio' che si e' potuto osservare
    # su ACC, isInPit non si accende mai: se il giro dei box lo marcasse solo
    # `in_pit`, su ACC finirebbe dritto nella media.
    out = _stint_with_a_pit_lap(in_pit=False, in_pit_lane=True)
    assert any("2 giri" in c.message for c in out)


def test_ac1_in_pit_lap_still_not_counted():
    # AC1 puo' accendere davvero isInPit: quel termine resta, e da solo deve
    # continuare a tenere il giro fuori dalla media.
    out = _stint_with_a_pit_lap(in_pit=True, in_pit_lane=False)
    assert any("2 giri" in c.message for c in out)


def test_normal_lap_still_counted():
    # Il contrappeso: senza nessuno dei due flag i giri entrano nella media.
    # Se la cura marcasse tutto, qui non parlerebbe piu' nessuno.
    eng = FuelEngineer()
    out, now = _lap(eng, 12.0)
    out, now = _lap(eng, 9.5, now)
    out, now = _lap(eng, 7.0, now)
    assert any("2 giri" in c.message for c in out)


def test_out_lap_is_not_counted():
    # Il giro d'uscita parte dentro la corsia e poi ne esce: se toccare la
    # corsia marca il giro, anche questo resta fuori dalla media. E' voluto —
    # un giro lanciato dai box non e' un giro rappresentativo di consumo.
    eng = FuelEngineer()
    out, now = _lap(eng, 12.0)
    for i in range(10):
        pos = i / 10 + 0.001
        eng.update(replace(_BASE, lap_position=pos, fuel=11.7,
                           in_pit_lane=pos < 0.3), now)
        now += 0.1
    eng.update(replace(_BASE, lap_position=0.01, fuel=11.7), now)
    now += 0.1
    out, now = _lap(eng, 9.2, now)
    out, now = _lap(eng, 6.7, now)
    assert any("2 giri" in c.message for c in out)
