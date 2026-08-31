"""A lap must not contradict its own clock.

At the start/finish line the sim resets `normalizedCarPosition`, `iCurrentTime`
and `iLastTime` on **different frames**. The codebase already knew this about
position (`crossed_start_line`, `strip_leading_wrap`); it did not know it about
the two clocks, and the archive shows what that cost:

* four laps opening with the previous lap's elapsed time at pos≈0.000 — one of
  them producing a *negative* measured duration;
* a Monza lap whose samples span 224.4 s filed as a 1:55.902, which is the
  previous lap's time. It sits in the catalogue as an identical twin of the real
  1:55.902 — two laps, one time, one of them a fiction.

The driver's report: numbers on screen that didn't match the game.
"""
from accoach.recording.lap import (
    LapSample,
    strip_stale_open,
    strip_trailing_wrap,
    trusted_lap_ms,
)
from accoach.recording.recorder import LapRecorder

import synth


def _s(t_ms, pos):
    return LapSample(t_ms, pos, 200.0, 1.0, 0.0, 0.0, "5", 8000, 0.0, 0.0)


def _lap(*pairs):
    return [_s(t, p) for t, p in pairs]


# --- the opening frame that still holds the previous lap's clock -----------

def test_a_lap_opening_with_the_previous_clock_is_trimmed():
    """Measured: laps opening at 69.6 s and 189.2 s, at pos 0.000."""
    samples = _lap((69639, 0.000), (120, 0.003), (2000, 0.02))
    assert [s.t_ms for s in strip_stale_open(samples)] == [120, 2000]


def test_an_inlap_that_really_starts_mid_lap_is_left_alone():
    """A partial lap legitimately opens with a big clock — but it RISES. That
    is the whole discriminator, exactly as `strip_leading_wrap` uses a falling
    position."""
    samples = _lap((40000, 0.40), (41000, 0.42), (42000, 0.44))
    assert len(strip_stale_open(samples)) == 3


def test_an_ordinary_lap_is_untouched():
    samples = _lap((30, 0.001), (140, 0.004), (250, 0.008))
    assert len(strip_stale_open(samples)) == 3


def test_the_recorder_does_not_write_that_frame_in_the_first_place():
    """The load-side guard exists for the archive; new laps shouldn't need it."""
    rec = LapRecorder()
    for i in range(30):                     # a partial lap, to prime the counter
        rec.update(synth.snap(pos=i / 30, completed_laps=0,
                              current_lap_ms=i * 2900, last_lap_ms=89000))
    # The crossing: position has wrapped, the lap timer hasn't.
    rec.update(synth.snap(pos=0.0004, completed_laps=1, current_lap_ms=88980,
                          last_lap_ms=89000, speed_kmh=150.0))
    rec.update(synth.snap(pos=0.004, completed_laps=1, current_lap_ms=120,
                          last_lap_ms=89000, speed_kmh=150.0))
    assert rec._buf is not None and rec._buf.samples
    assert rec._buf.samples[0].t_ms < 1000, "the stale clock never got in"


# --- the closing frame that already belongs to the next lap ---------------

def test_a_trailing_frame_past_the_line_is_trimmed():
    samples = _lap((100, 0.01), (99000, 0.998), (9, 0.0005))
    assert [round(s.pos, 4) for s in strip_trailing_wrap(samples)] == [0.01, 0.998]


def test_trailing_trim_does_not_eat_a_normal_ending():
    samples = _lap((100, 0.01), (50000, 0.5), (99000, 0.998))
    assert len(strip_trailing_wrap(samples)) == 3


# --- the declared lap time vs the lap's own clock -------------------------

def test_a_time_that_matches_the_samples_is_believed():
    assert trusted_lap_ms(100_000, _lap((0, 0.0), (99_940, 0.999))) == 100_000


def test_the_usual_shortfall_is_not_a_contradiction():
    """The last sample lands just before the line, so the measured span always
    runs a little short. Across 59 real laps that shortfall is at most 1.36 s;
    the failures this catches are 104, 108 and 118 s."""
    assert trusted_lap_ms(70_849, _lap((108, 0.002), (69_597, 0.999))) == 70_849


def test_a_time_belonging_to_another_lap_is_replaced_by_the_measured_one():
    """The Monza twin: samples spanning 224.4 s, filed as a 1:55.902.

    The replacement is the lap's clock projected to the line, not the samples'
    raw span: the span drops the sliver at BOTH ends and so understates by more.
    Same defect, same answer, whichever half of it we caught."""
    got = trusted_lap_ms(115_902, _lap((30, 0.000), (224_385, 0.999)))
    assert got == 224_610


def test_a_lap_with_no_usable_clock_keeps_what_the_sim_said():
    """One sample, or a span that came out negative: nothing to appeal to, so
    the sim's answer stands rather than being replaced by a worse guess."""
    assert trusted_lap_ms(104_598, _lap((33, 0.0008))) == 104_598
    assert trusted_lap_ms(104_598, _lap((33, 0.0008), (9, 0.0005))) == 104_598


def test_the_tolerance_scales_with_the_lap():
    """5 s of slack on a one-minute lap is generous; on a three-minute lap it
    would be mean. Same fraction either way."""
    assert trusted_lap_ms(200_000, _lap((0, 0.0), (185_000, 0.999))) == 200_000
    assert trusted_lap_ms(200_000, _lap((0, 0.0), (100_000, 0.999))) == 100_100


# --- what it buys, end to end --------------------------------------------

def test_the_reference_no_longer_thinks_it_took_a_minute_to_reach_the_line():
    """The cost of the stale opening frame, in the place the driver sees it: a
    reference indexed at pos≈0 with t≈70 s puts every live delta out by that
    much, for the whole lap."""
    from accoach.comparison import Reference
    from accoach.recording.lap import Lap
    from accoach.telemetry.snapshot import SessionType

    good = synth.build_lap()
    poisoned = Lap("ferrari_488_gt3", "monza", SessionType.PRACTICE,
                   good.lap_time_ms, True,
                   samples=[_s(69_639, 0.0)] + list(good.samples[1:]))
    # Straight through the same sanitiser the loader runs.
    poisoned.samples = strip_stale_open(poisoned.samples)
    assert Reference(poisoned).time_at(0.001) < 1000


# --- the same defect, the size of the gap between two laps ----------------
#
# The Monza twin above is the loud version: an error of a hundred seconds, which
# a tolerance of 5 s or 10 % of the lap cannot miss. The quiet version is the
# common one, and it went unnoticed for a month. When you are lapping on the pace
# two consecutive laps differ by tenths, so the SAME stale read puts the lap out
# by tenths — and 5 s of slack sails straight past it.
#
# Measured over the whole real archive on 20/08/2026 (99 laps). Comparing each
# declared time against the lap's own clock projected to the line:
#
#     91 healthy laps          -68 .. +113 ms
#     7 laps whose declared time repeats the previous lap's
#                              -108546, -654, -266, -232, -175, +440, +2734 ms
#
# Every duplicate is outside the healthy band and no healthy lap is inside the
# defect's — but the two nearest neighbours are 113 and 175, so magnitude alone
# is not enough to separate them, and a second family (a lap whose SAMPLES have
# the hole, not its declared time — `clock_covers_lap` in coaching/trends.py)
# lives in the same range with the opposite repair. So the discriminator is the
# defect's own signature: the sim is still publishing the number it was already
# publishing before the crossing.

def test_a_time_the_sim_never_republished_is_replaced():
    """Monza 14/08, the lap that cost the least and mattered the most: filed as
    a 1:55.185 — to the millisecond the lap before — while its own clock reads
    115.360 s at the line. 175 ms, against an engineer that accepts or reverts a
    setup change on a band of 173."""
    got = trusted_lap_ms(115_185, _lap((32, 0.0), (115_130, 0.998), (115_360, 1.0)),
                         previous=115_185)
    assert got == 115_360


def test_and_the_loud_one_from_the_same_night():
    """The other of the two, 2.75 s out: the previous lap was simply slower."""
    got = trusted_lap_ms(117_855, _lap((20, 0.0), (115_000, 0.9989), (115_105, 0.9998)),
                         previous=117_855)
    # The samples' own answer, plus the sliver of track left to the line.
    assert 115_100 <= got <= 115_200


def test_two_laps_that_really_took_the_same_time_are_both_believed():
    """Repeating a lap time to the millisecond is rare, not impossible, and the
    signature alone cannot tell it from the defect. The lap's own clock can: here
    it agrees, so the sim's answer stands."""
    got = trusted_lap_ms(115_185, _lap((20, 0.0), (115_120, 0.9995), (115_150, 0.9999)),
                         previous=115_185)
    assert got == 115_185


def test_a_lap_whose_time_the_sim_did_republish_is_left_alone():
    """The shortfall of a healthy lap is the same size as the defect. What tells
    them apart is that the sim answered with a different number than before."""
    got = trusted_lap_ms(115_185, _lap((32, 0.0), (115_130, 0.998), (115_360, 1.0)),
                         previous=117_855)
    assert got == 115_185


def test_without_the_sim_s_previous_answer_the_quiet_version_is_invisible():
    """Which is the honest limit of the load path: a file on disk carries no
    record of what the sim was saying a frame earlier, so an archived lap is
    still judged by the loud rule alone."""
    got = trusted_lap_ms(115_185, _lap((32, 0.0), (115_130, 0.998), (115_360, 1.0)))
    assert got == 115_185


def _drive_lap(rec, *, completed, dur_ms, last_ms, n=400):
    """One lap's worth of frames; returns the lap emitted at its crossing.

    Dense on purpose (n=400): the projection to the line only speaks for the
    sliver of track past the last sample, and a 40-frame lap leaves 2.5 % of the
    circuit there — a fixture coarser than anything the recorder ever sees.
    """
    finished = None
    for i in range(n):
        out = rec.update(synth.snap(
            pos=i / n, completed_laps=completed, current_lap_ms=int(i / n * dur_ms),
            last_lap_ms=last_ms, speed_kmh=150.0,
        ))
        if out is not None:
            finished = out
    return finished


def test_the_recorder_does_not_stamp_a_lap_with_the_time_of_the_one_before():
    """End to end, the shape of the two Monza laps of 14/08: the sim is still
    publishing 1:57.855 when the next lap closes, and that lap took 1:55.1.

    Questo fixture e' il caso in cui il gioco **non risponde mai** — 400 frame
    con lo stesso numero — quindi da qui in poi l'esito giusto non e' piu' la
    ricostruzione dai campioni ma «questo giro non ha un tempo». Il caso in cui
    il gioco risponde (sei volte su sei, al primo frame, il 23/08) e prende il
    suo numero esatto sta in
    `test_the_lap_takes_the_time_the_sim_publishes_a_frame_later`.
    """
    rec = LapRecorder()
    _drive_lap(rec, completed=0, dur_ms=117_855, last_ms=117_855)   # partial
    _drive_lap(rec, completed=1, dur_ms=115_100, last_ms=117_855)
    lap = _drive_lap(rec, completed=2, dur_ms=115_000, last_ms=117_855)
    assert lap is not None
    assert lap.lap_time_ms != 117_855, "the previous lap's time, read again"
    assert lap.lap_time_ms == 0, "e nemmeno un numero ricostruito al suo posto"


def test_and_believes_the_sim_the_moment_it_answers_with_a_new_number():
    rec = LapRecorder()
    _drive_lap(rec, completed=0, dur_ms=117_855, last_ms=117_855)
    _drive_lap(rec, completed=1, dur_ms=115_100, last_ms=117_855)
    lap = _drive_lap(rec, completed=2, dur_ms=115_000, last_ms=115_100)
    assert lap.lap_time_ms == 115_100


# --- aspettare un frame invece di ricostruire ------------------------------
#
# Verita' a terra, sessione del 23/08 (Brands Hatch + Imola, 21 giri, la riga
# `orologio del giro:` in `Documenti/ACCoach/logs/accoach.log`):
#
#   6 giri  il gioco ha risposto **dopo 1 frame**, sempre 1, mai di piu';
#           e il numero salvato era corto di -18 -14 -17 -13 -15 -15 ms
#   12 giri il tempo alla linea era gia' quello giusto (scarto +0)
#   2 giri  il gioco non ha mai risposto, e sono i due che non hanno un tempo:
#           il sentinella 2147483.647s diventato 260.062s, e il giro coi box
#           diventato 183.140s da un dichiarato di 110.392
#
# Cioe' la ricostruzione dai campioni non serve mai: dove il gioco risponde e'
# corta di ~15 ms sistematici, e dove non risponde inventa un numero che non
# esiste. La cura e' aspettare la sua risposta, e non inventarne una quando non
# arriva.

def _drive(rec, *, completed, dur_ms, last_ms, n=400, from_frame=None,
           then_last_ms=None):
    """Come `_drive_lap`, ma `last_lap_ms` puo' cambiare a meta' del giro.

    Denso come lui, e per la stessa ragione (n=400): a 40 frame l'ultimo
    campione resta al 2.5% dalla linea, `clock_at_line` non proietta e la firma
    «il gioco non ha ancora risposto» non puo' nemmeno formarsi — un fixture
    cosi' non tocca il codice che dice di provare.

    `from_frame`/`then_last_ms` sono il gioco che pubblica il tempo qualche
    frame **dopo** la linea, che e' il caso che questa cura prende.
    """
    finished = None
    for i in range(n):
        lm = last_ms if (from_frame is None or i < from_frame) else then_last_ms
        out = rec.update(synth.snap(
            pos=i / n, completed_laps=completed, current_lap_ms=int(i / n * dur_ms),
            last_lap_ms=lm, speed_kmh=150.0,
        ))
        if out is not None:
            finished = out
    return finished


def test_the_lap_takes_the_time_the_sim_publishes_a_frame_later(tmp_path):
    """Il numero esatto, non una ricostruzione corta di 15 ms.

    Sei giri su sei, il 23/08, il gioco ha risposto al primo frame dopo la
    linea. Quel numero e' il tempo del giro: prenderlo e' esatto, ricostruirlo
    dai campioni e' sempre corto (misurato: -13..-18 ms, tutti dello stesso
    segno, che e' una distorsione e non rumore).
    """
    rec = LapRecorder()
    _drive(rec, completed=0, dur_ms=117_855, last_ms=117_855)      # parziale
    _drive(rec, completed=1, dur_ms=115_100, last_ms=117_855)
    # I due numeri devono essere DIVERSI, o il test non prova niente: su campioni
    # sintetici perfettamente lineari la proiezione cade esattamente sul numero
    # vero (misurato: 115_100), quindi un fixture che li fa coincidere passa
    # identico anche senza la cura. Nella realta' non coincidono mai — la
    # proiezione arriva corta di 13..18 ms — e questi 15 ms sono quello scarto.
    lap = _drive(rec, completed=2, dur_ms=115_000, last_ms=117_855,
                 from_frame=1, then_last_ms=115_115)
    assert lap is not None, "il giro deve arrivare, solo un frame piu' tardi"
    assert lap.lap_time_ms == 115_115, (
        "il numero del gioco, esatto — non la proiezione dai campioni (115_100)")


def test_a_lap_the_sim_never_times_is_not_given_an_invented_one():
    """«Invariato» non vuol dire «il tempo e' quello»: vuol dire che non c'e'.

    E' il giro d'uscita e il giro coi box del 23/08. Oggi la ricostruzione dai
    campioni ne fabbrica uno (260 s, 183 s) e il tetto a valle e' un'ora, quindi
    ci passa. Un numero inventato e' peggio di un numero assente: su quello
    l'Ingegnere accetta o annulla un assetto con una banda di 173 ms.
    """
    rec = LapRecorder()
    # Il giro coi box e' quello di MEZZO: e' lui che chiude all'inizio della
    # terza chiamata, ed e' li' che il gioco dice ancora 110.392 — il tempo del
    # giro prima — per non cambiarlo mai piu'.
    _drive(rec, completed=0, dur_ms=115_000, last_ms=110_392)
    _drive(rec, completed=1, dur_ms=183_140, last_ms=110_392)
    lap = _drive(rec, completed=2, dur_ms=115_000, last_ms=110_392)
    assert lap is not None, "il giro arriva lo stesso: e' il suo tempo che non c'e'"
    assert lap.lap_time_ms == 0, (
        "il gioco non ha mai dato un tempo a questo giro: non se ne inventa uno")
    assert lap.valid is False, "e senza tempo non entra in archivio"


def test_the_out_lap_sentinel_is_not_a_time_either():
    """ACC dice 2147483647 = «non ho ancora un tempo». Il 23/08 e' diventato
    260.062 s, e a salvarci e' stata una regola che parla d'altro."""
    rec = LapRecorder()
    # Tre giri, perche' il difetto va isolato: il PRIMO buffer non e' mai un
    # giro intero, quindi un giro d'uscita in prima posizione risulterebbe
    # invalido per un motivo che non c'entra col suo orologio — ed e'
    # esattamente il motivo sbagliato per cui il 23/08 non ha fatto danno.
    _drive(rec, completed=0, dur_ms=260_000, last_ms=2_147_483_647)
    _drive(rec, completed=1, dur_ms=260_031, last_ms=2_147_483_647)
    lap = _drive(rec, completed=2, dur_ms=260_062, last_ms=2_147_483_647)
    assert lap is not None
    assert lap.lap_time_ms == 0, "«non ho un tempo» non diventa «ho un tempo»"
    assert lap.valid is False


def test_a_healthy_lap_is_not_held_back(tmp_path):
    """La rete di sicurezza, e nasce da un buco nell'evidenza.

    Il log non dice se sui giri sani il dichiarato coincide col frame prima:
    quando coincide **e** il tempo e' giusto, la riparazione non scatta e la riga
    non lo distingue. Se il gioco pubblicasse prima del nostro incrocio, un giro
    sano avrebbe la stessa firma di uno in ritardo — e trattenerlo per poi non
    vederlo cambiare lo butterebbe via. Percio' si trattiene solo quando la firma
    scatta **e** il dichiarato contraddice l'orologio del giro: esattamente
    l'insieme che oggi viene riparato, ne' uno di piu'.
    """
    rec = LapRecorder()
    _drive(rec, completed=0, dur_ms=115_000, last_ms=115_000)
    # Il gioco dice lo stesso numero del frame prima, ma e' anche il numero
    # giusto: i campioni lo confermano. Non c'e' niente da aspettare.
    lap = _drive(rec, completed=1, dur_ms=115_000, last_ms=115_000)
    assert lap is not None
    assert lap.lap_time_ms == 115_000
