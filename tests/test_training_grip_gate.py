"""«Frena più tardi» non si prescrive dove il debrief ha appena detto il contrario.

Il difetto, trovato da un panel di revisione il 2026-08-05 e vivo sul giro della
demo: per la **stessa curva**, con lo **stesso titolo** «Porta più velocità in
ingresso», il debrief scriveva che l'aderenza è già tutta impegnata e la scheda
Allenamento prescriveva otto giri di «sposta il punto di frenata più avanti».

Il meccanismo era banale: `drill_key` guardava solo la *fase* e per «ingresso»
aveva come ripiego `brake_move_later`. Il segnale che smentiva l'esercizio
esisteva già ed era misurato — non attraversava il confine fra i due moduli.

È la stessa classe di errore contro cui il docstring di `drill_key` metteva già
in guardia per il trail braking: «le due metà di questa app che danno consigli
opposti allo stesso pilota». Ramo diverso, stessa trappola.
"""
import pytest

from accoach.coaching.cue import CueCategory as _C
from accoach.coaching.debrief import GripState
from accoach.coaching.training import (
    CornerFacts,
    brake_later_is_blocked,
    build_drill,
    drill_key,
)


def _satura(coast_s=0.0):
    """Una curva in cui la gomma è già impegnata dove il freno morde."""
    return GripState(ratio=1.0, saturated_early=True, coast_s=coast_s)


# --- il cancello ------------------------------------------------------------

def test_all_three_conditions_are_needed():
    """Nessuna delle tre da sola basta: è il motivo per cui il debrief manda tre
    numeri e non un booleano."""
    assert brake_later_is_blocked(_satura())
    # al limite, ma non dove si frena → la staccata più tarda c'è
    assert not brake_later_is_blocked(
        GripState(ratio=1.0, saturated_early=False))
    # al limite e presto, ma con veleggio prima del freno → la gomma è satura
    # quando la usi, non la usi abbastanza presto
    assert not brake_later_is_blocked(_satura(coast_s=0.5))
    # sotto il limite → niente da bloccare
    assert not brake_later_is_blocked(
        GripState(ratio=0.6, saturated_early=True))


def test_no_grip_data_never_blocks():
    """Sui giri anteriori ai canali G si torna al comportamento di prima, invece
    di bloccare un esercizio su un dato che non c'è."""
    assert not brake_later_is_blocked(None)
    assert not brake_later_is_blocked(GripState())


# --- la scelta dell'esercizio ----------------------------------------------

def test_the_two_halves_no_longer_contradict_each_other():
    """Il difetto, nella sua forma più corta."""
    assert drill_key(_C.CARRY_SPEED.value, "entry") == "brake_move_later"
    assert drill_key(_C.CARRY_SPEED.value, "entry",
                     brake_later_blocked=True) != "brake_move_later"


@pytest.mark.parametrize("trail_brake,atteso", [
    # Chi trail-braina lavora sulla FORMA del rilascio: stesso |g|, ripartizione
    # diversa lungo il bordo dell'ellisse.
    (True, "brake_release"),
    # Chi non lo fa sposta DOVE FINISCE la frenata. Stessa fisica — riallocare
    # invece di chiedere più aderenza totale — due gesti diversi.
    (False, "brake_straight"),
])
def test_the_saturated_drill_depends_on_the_car_class(trail_brake, atteso):
    assert drill_key(_C.CARRY_SPEED.value, "entry", trail_brake=trail_brake,
                     brake_later_blocked=True) == atteso


def test_the_blocked_drill_never_asks_for_more_total_grip():
    """`brake_move_later` è l'unico dei tre esercizi d'ingresso che chiede più
    aderenza *totale*; gli altri due chiedono la stessa aderenza spesa meglio.
    A saturazione solo i secondi hanno senso fisico."""
    for trail in (True, False):
        assert drill_key(_C.BRAKE_LATER.value, "entry", trail_brake=trail,
                         brake_later_blocked=True) != "brake_move_later"


def test_build_drill_reads_the_gate_from_the_corner_itself():
    """Il ponte end-to-end: il fatto misurato dal debrief viaggia con la curva e
    arriva fino all'esercizio, senza che il chiamante debba saperlo."""
    facts = CornerFacts(min_speed_kmh=90.0, min_speed_ref_kmh=120.0,
                        grip=_satura())
    assert build_drill(_C.CARRY_SPEED.value, "entry", facts).key == "brake_release"

    libera = CornerFacts(min_speed_kmh=90.0, min_speed_ref_kmh=120.0)
    assert build_drill(_C.CARRY_SPEED.value, "entry",
                       libera).key == "brake_move_later"


def test_the_other_phases_are_untouched():
    """Il cancello vale per l'ingresso: apex e uscita non c'entrano, e una
    correzione che si allargasse da sola sarebbe la stessa specie di difetto."""
    for phase, atteso in (("apex", "apex_speed"), ("exit", "exit_throttle"),
                          ("after", "exit_throttle")):
        assert drill_key(_C.CARRY_SPEED.value, phase,
                         brake_later_blocked=True) == atteso
