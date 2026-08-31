"""The Focus/Lesson layer — the driver's twin of the race engineer.

It runs over per-lap debriefs (where you lost time vs the reference), picks the
single recurring weakness and coaches it: assess → brief → drill → improved/stuck.
These tests drive it with hand-built debriefs (cheap, exact) and then check the
engine wires a real debrief→focus path into the payload.
"""
import pytest

from accoach import config
from accoach.coaching.cue import CueCategory
from accoach.coaching.debrief import CornerLoss, LapDebrief
from accoach.coaching.focus import (
    FocusCoach,
    FocusKind,
    FocusReport,
    format_focus,
)
from accoach.engine import CoachEngine
from accoach.comparison.reference import Reference
from accoach.track import detect_corners

import synth


@pytest.fixture
def it_lang(tmp_path, monkeypatch):
    """Switch the app language to Italian, resetting the config cache after."""
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    config.load_config(reload=True)
    config.set_language("it")
    yield
    config._cache = None


def _loss(index: int, ms: float, category: CueCategory = CueCategory.BRAKE_LATER,
          cause: str = "") -> CornerLoss:
    return CornerLoss(
        index=index, entry_pos=0.2, apex_pos=0.3, exit_pos=0.4, lost_ms=ms,
        category=category, message="m", detail="d",
        fix="Ritarda la staccata.", cause=cause)


def _debrief(*losses: CornerLoss, lap_ms: int = 101000, ref_ms: int = 100000) -> LapDebrief:
    return LapDebrief("ferrari_488_gt3", "monza", lap_ms, ref_ms, losses=list(losses))


def _feed(coach: FocusCoach, debrief: LapDebrief, times: int, *, stable: bool = True):
    report = None
    for _ in range(times):
        report = coach.observe(debrief, stable=stable)
    return report


# --- weakness selection ----------------------------------------------------

def test_assess_until_min_laps():
    coach = FocusCoach()
    r1 = coach.observe(_debrief(_loss(0, 300)))
    r2 = coach.observe(_debrief(_loss(0, 300)))
    assert r1.kind is FocusKind.ASSESS and r2.kind is FocusKind.ASSESS


def test_brief_on_recurring_loss():
    coach = FocusCoach()
    report = _feed(coach, _debrief(_loss(0, 300)), 3)
    assert report.kind is FocusKind.BRIEF
    assert report.focus.corner_index == 0
    assert report.focus.theme == "braking"             # BRAKE_LATER → braking
    assert report.drill                                # a concrete instruction
    assert "0.30s" in report.message                   # measured baseline


def test_picks_worst_recurring_not_a_one_off():
    """A single huge loss in c1 must not beat a recurring loss in c0."""
    coach = FocusCoach()
    coach.observe(_debrief(_loss(0, 300)))
    coach.observe(_debrief(_loss(0, 300), _loss(1, 900)))   # c1 spikes once
    report = coach.observe(_debrief(_loss(0, 300)))
    assert report.kind is FocusKind.BRIEF
    assert report.focus.corner_index == 0                   # recurring beats one-off


def test_baseline_uses_full_window_denominator():
    # A corner that's a loss in only some laps must get a baseline measured over
    # the WHOLE window (good laps = 0), the same denominator the drill uses — else
    # IMPROVED would fire without real progress.
    coach = FocusCoach()
    coach.observe(_debrief())                      # good
    coach.observe(_debrief())                      # good
    coach.observe(_debrief(_loss(0, 300)))         # loss, not yet recurring
    r = coach.observe(_debrief(_loss(0, 300)))     # 2/4 -> systematic -> BRIEF
    assert r.kind is FocusKind.BRIEF
    assert r.focus.baseline_ms == 150.0            # median([0,0,300,300]), not 300


def test_no_focus_when_losses_insignificant():
    coach = FocusCoach()
    report = _feed(coach, _debrief(_loss(0, 50)), 3)         # below the threshold
    assert report.kind is FocusKind.CLEAN


# --- the drill → verdict loop ----------------------------------------------

def test_focus_improved_promotes_and_praises():
    coach = FocusCoach()
    _feed(coach, _debrief(_loss(0, 300)), 3)                 # BRIEF on c0 (baseline 300)
    report = _feed(coach, _debrief(_loss(0, 50)), 3)         # then nail it
    assert report.kind is FocusKind.IMPROVED
    assert 0 in coach.mastered
    assert coach.focus is None                               # ready for the next one
    assert "0.30s" in report.message and "0.05s" in report.message  # measured praise


def test_focus_stuck_is_parked():
    coach = FocusCoach()
    _feed(coach, _debrief(_loss(0, 300, cause="L'auto sottosterza in ingresso.")), 3)
    report = _feed(coach, _debrief(_loss(0, 300)), 6)        # never improves
    assert report.kind is FocusKind.STUCK
    assert 0 in coach.parked
    assert coach.focus is None
    assert "setup" in report.message.lower()                # hints it may be the car


def test_next_focus_after_promotion():
    coach = FocusCoach()
    # c0 is worse; coach it, solve it, then c1 should become the focus.
    base = _debrief(_loss(0, 300), _loss(1, 200))
    _feed(coach, base, 3)                                    # BRIEF on c0
    _feed(coach, _debrief(_loss(0, 40), _loss(1, 200)), 3)   # solve c0 (IMPROVED)
    report = _feed(coach, _debrief(_loss(0, 40), _loss(1, 200)), 1)
    assert report.kind is FocusKind.BRIEF
    assert report.focus.corner_index == 1                   # moved on to the next


# --- robustness ------------------------------------------------------------

def test_unstable_lap_does_not_move_the_plan():
    coach = FocusCoach()
    coach.observe(_debrief(_loss(0, 300)))
    coach.observe(_debrief(_loss(0, 300)))
    before = len(coach.window)
    report = coach.observe(_debrief(_loss(0, 9000)), stable=False)   # an off
    assert report.kind is FocusKind.ASSESS                  # last report stands
    assert len(coach.window) == before                      # excursion ignored


def test_brief_theme_and_message_are_italian(it_lang):
    coach = FocusCoach()
    report = _feed(coach, _debrief(_loss(0, 300)), 3)
    assert report.kind is FocusKind.BRIEF
    assert report.focus.theme == "frenata"             # BRAKE_LATER → frenata (IT)
    assert "Nuovo focus" in report.message
    assert "lavoriamo la frenata" in report.message


def test_stuck_message_is_italian(it_lang):
    coach = FocusCoach()
    _feed(coach, _debrief(_loss(0, 300, cause="L'auto sottosterza in ingresso.")), 3)
    report = _feed(coach, _debrief(_loss(0, 300)), 6)
    assert report.kind is FocusKind.STUCK
    assert "parcheggio" in report.message.lower()
    assert "causa setup" in report.message.lower()


def test_format_focus_is_a_line():
    r = FocusReport(FocusKind.CLEAN, "Guida costante.")
    assert "Guida costante." in format_focus(r)


# --- engine wiring (real debrief → focus → payload) ------------------------

def test_engine_focus_block_from_real_debriefs(tmp_path):
    class _Dummy:
        def read(self): ...
        def close(self): ...

    eng = CoachEngine(reader=_Dummy(), laps_dir=tmp_path)
    ref_lap = synth.build_lap(n=300, clean=True)
    eng._reference = Reference(ref_lap)
    eng._corners = detect_corners(ref_lap.samples)
    eng._focus = FocusCoach()

    # Three clean laps that lose time in corner 0 → a recurring weakness.
    slow = synth.build_lap(slow_corner=0, amt=30, n=300, clean=True)
    for _ in range(3):
        eng._observe_lap(slow)

    block = eng._focus_block()
    assert block is not None
    assert block["kind"] in ("brief", "drill", "assess")
    if block["kind"] == "brief":
        assert block["focus"]["theme"]
    eng.close()


# --- un focus, un solo metro ----------------------------------------------
#
# Il motore rifa' il riferimento a ogni personal best, quindi la perdita a una
# curva e' misurata contro un metro che si muove. Misurato sui 16 giri veri del
# 14/08 (3 cambi di riferimento), le due letture della stessa curva **cambiano
# verso**, non solo entita':
#
#     Variante della Roggia   metro che rincorre  0 -> 280 ms
#                             metro fisso       519 -> 190 ms
#
# Nei primi giri il riferimento e' il giro lento del pilota, quindi non si perde
# niente contro nessuno e una base misurata li' nasce piccola; poi il
# riferimento accelera e la stessa curva "peggiora" mentre il pilota migliora.
# Cosi' com'era, «0.49 -> 0.00» non era una misura di quanto sei migliorato.

def test_a_new_reference_makes_the_focus_start_measuring_again():
    """La finestra e' fatta di misure contro un metro: cambiato il metro, quelle
    misure non si mediano piu' con le nuove. Si ricomincia a guardare — che e'
    quello che il coach dice gia' quando non ha abbastanza giri."""
    fc = FocusCoach(min_laps=3)
    for _ in range(2):
        fc.observe(_debrief(_loss(0, 500)), reference="giro-A")
    assert len(fc.window) == 2
    r = fc.observe(_debrief(_loss(0, 500)), reference="giro-B")
    assert r.kind is FocusKind.ASSESS
    assert len(fc.window) == 1


def test_the_same_reference_does_not_reset_anything():
    fc = FocusCoach(min_laps=3)
    for _ in range(4):
        fc.observe(_debrief(_loss(0, 500)), reference="giro-A")
    assert len(fc.window) == 4


def test_without_a_reference_token_nothing_changes():
    """Chi non lo passa si comporta esattamente come prima: un metro che non si
    dichiara e' un metro che si assume fermo."""
    fc = FocusCoach(min_laps=3)
    for _ in range(4):
        fc.observe(_debrief(_loss(0, 500)))
    assert len(fc.window) == 4


def test_a_reference_that_moves_under_an_elected_focus_drops_it():
    """Non dovrebbe succedere — il motore congela il riferimento finche' un
    focus e' aperto — ma se succede il verdetto non e' piu' difendibile, e un
    verdetto indifendibile non si da'."""
    fc = FocusCoach(min_laps=3)
    for _ in range(4):
        fc.observe(_debrief(_loss(0, 500)), reference="giro-A")
    assert fc.focus is not None
    fc.observe(_debrief(_loss(0, 500)), reference="giro-B")
    assert fc.focus is None


def test_the_engine_holds_the_reference_still_under_an_open_focus(tmp_path):
    """Il pezzo che il coach da solo non puo' provare: che il metro stia fermo.

    Il motore rifa' il riferimento dopo ogni giro salvato, quindi senza questo
    un personal best a meta' esercizio spazzerebbe via la base del focus e il
    verdetto — che e' esattamente la cosa che il pilota aspetta."""
    from accoach.telemetry.snapshot import TelemetrySnapshot

    class _Dead:
        def read(self):
            return TelemetrySnapshot.disconnected()

        def close(self):
            pass

    ref_a = synth.build_lap()
    eng = CoachEngine(reader=_Dead(), laps_dir=tmp_path)
    eng._focus = FocusCoach(min_laps=3)
    eng._reference = Reference(ref_a)
    eng._corners = detect_corners(ref_a.samples)
    for _ in range(4):
        eng._observe_lap(synth.build_lap(slow_corner=0, amt=30))
    assert eng._focus.focus is not None, "il fixture deve eleggere un focus"
    frozen = eng._focus_ref
    assert frozen is not None

    # Personal best a meta' esercizio: il resto dell'app passa al giro nuovo.
    ref_b = synth.build_lap(slow_corner=1, amt=10)
    eng._reference = Reference(ref_b)
    eng._corners = detect_corners(ref_b.samples)
    eng._observe_lap(synth.build_lap(slow_corner=0, amt=30))

    assert eng._focus.focus is not None, "il focus non deve cadere col riferimento"
    # Il metro, non la scatola che lo contiene: la tupla si ricostruisce a ogni
    # giro (e' l'atto di ri-appuntare quello che si e' appena usato), quindi
    # quello che deve stare fermo e' il riferimento dentro, e le sue curve.
    assert eng._focus_ref[0] is frozen[0], "e il metro deve essere ancora quello"
    assert eng._focus_ref[1] is frozen[1], "con le curve con cui era stato letto"
    eng.close()


def test_the_engine_holds_the_reference_still_while_it_is_still_assessing(tmp_path):
    """La regressione del 23/08, a Imola: il focus non elegge se il pilota migliora.

    Il congelamento del metro c'era gia' ma partiva **troppo tardi** — solo dopo
    che un focus era stato eletto. In fase di valutazione il metro restava quello
    vivo, che `_rebuild_reference` rifa' dopo ogni giro salvato per inseguire il
    nuovo migliore: 1:51 -> 1:49 -> 1:48 -> 1:47 sono quattro metri diversi,
    quindi la finestra si svuotava quattro volte e non arrivava mai ai tre giri
    che servono per eleggere. Cioe' il focus si spegneva **proprio mentre il
    pilota migliora**, che e' lo scopo di una sessione di prove.

    A Brands Hatch era passato inosservato solo perche' li' c'erano stati quattro
    giri senza migliorare, e la finestra aveva fatto in tempo a riempirsi.
    """
    from accoach.telemetry.snapshot import TelemetrySnapshot

    class _Dead:
        def read(self):
            return TelemetrySnapshot.disconnected()

        def close(self):
            pass

    eng = CoachEngine(reader=_Dead(), laps_dir=tmp_path)
    eng._focus = FocusCoach(min_laps=3)
    ref = synth.build_lap()
    eng._reference = Reference(ref)
    eng._corners = detect_corners(ref.samples)

    for i in range(4):
        eng._observe_lap(synth.build_lap(slow_corner=0, amt=30))
        # Personal best: il resto dell'app passa al giro nuovo, come fa il motore
        # dopo ogni giro salvato. Ogni ricostruzione e' un metro diverso.
        # I passi da 5 sono quello che serve perche' i quattro giri abbiano
        # davvero quattro tempi diversi: sotto quel passo `synth.build_lap`
        # arrotonda allo stesso `lap_time_ms` e il motore vedrebbe un metro solo
        # (misurato: amt 4, 6 e 8 danno tutti 100089).
        better = synth.build_lap(slow_corner=1, amt=5 * (i + 1))
        eng._reference = Reference(better)
        eng._corners = detect_corners(better.samples)

    assert eng._focus.focus is not None, (
        "quattro giri puliti con la stessa perdita devono eleggere un focus, "
        "anche se il pilota ha migliorato a ogni giro")
    eng.close()


def test_a_closed_focus_lets_the_reference_go(tmp_path):
    """Il metro sta fermo per la durata di un ciclo, non per sempre.

    Dato un verdetto (migliorata o parcheggiata) il ciclo e' finito: il prossimo
    si pesa su oggi, non sul giro con cui misuravamo mezz'ora fa. Lo stato
    «nessun punto debole ricorrente» invece **non** e' un verdetto e non libera
    niente: liberarlo li' rifarebbe la regressione, perche' quello stato si
    ripete a ogni giro e ogni volta ributterebbe la finestra.
    """
    from accoach.telemetry.snapshot import TelemetrySnapshot
    from accoach.coaching.focus import FocusKind

    class _Dead:
        def read(self):
            return TelemetrySnapshot.disconnected()

        def close(self):
            pass

    eng = CoachEngine(reader=_Dead(), laps_dir=tmp_path)
    eng._focus = FocusCoach(min_laps=3)
    ref = synth.build_lap()
    eng._reference = Reference(ref)
    eng._corners = detect_corners(ref.samples)

    kinds = []
    for _ in range(12):
        eng._observe_lap(synth.build_lap(slow_corner=0, amt=30))
        kinds.append(eng._focus_report.kind)
        if eng._focus_report.kind in (FocusKind.IMPROVED, FocusKind.STUCK):
            break

    assert kinds[-1] in (FocusKind.IMPROVED, FocusKind.STUCK), (
        f"il fixture deve arrivare a un verdetto, non a {kinds}")
    assert eng._focus_ref is None, "dato il verdetto, il metro si libera"
    eng.close()


def test_no_recurring_weakness_does_not_let_the_reference_go(tmp_path):
    """«Nessun punto debole ricorrente» non e' un verdetto: non libera il metro.

    E' la trappola gemella della regressione, ed e' il motivo per cui la
    liberazione guarda il *verdetto* e non `focus is None`: CLEAN si ripete a
    ogni giro, quindi liberare li' rimetterebbe il metro vivo sotto la finestra e
    ogni personal best la ributterebbe — il coach resterebbe a «valuto 0/3» per
    tutta la sessione, che e' esattamente il difetto che questa cura chiude.
    """
    from accoach.telemetry.snapshot import TelemetrySnapshot
    from accoach.coaching.focus import FocusKind

    class _Dead:
        def read(self):
            return TelemetrySnapshot.disconnected()

        def close(self):
            pass

    eng = CoachEngine(reader=_Dead(), laps_dir=tmp_path)
    eng._focus = FocusCoach(min_laps=3)
    ref = synth.build_lap()
    eng._reference = Reference(ref)
    eng._corners = detect_corners(ref.samples)

    # Un pilota costante che non perde niente di ricorrente, e che migliora.
    for i in range(5):
        eng._observe_lap(synth.build_lap())
        better = synth.build_lap(slow_corner=1, amt=5 * (i + 1))
        eng._reference = Reference(better)
        eng._corners = detect_corners(better.samples)

    assert eng._focus_report.kind is FocusKind.CLEAN
    assert len(eng._focus.window) == 5, (
        "la finestra deve continuare a riempirsi: nessun giro e' stato buttato")
    assert eng._focus_ref is not None, "e il metro deve essere ancora appuntato"
    eng.close()
