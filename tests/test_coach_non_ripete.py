"""Il coach non ripete la stessa frase e lascia stare il giro di uscita.

Misurato l'08/11 (153 frasi in un'ora, 11 in 60 s): «Pattini in uscita» due volte
a 1,5 e 1,6 s di distanza, e a ogni uscita dai box con le gomme fredde.
"""
from accoach.coaching.cue import TRIGGER, Cue, CueCategory, trigger_text
from accoach.coaching.scheduler import CueScheduler
from accoach.engine import _focus_log_line

import synth
from test_engine_gate import _crossing, _engine_with_reference, _run


def _cue(category, segment=0):
    return Cue(category=category, message=category.value, priority=300.0,
               segment=segment, pos=0.0)


def test_stessa_categoria_a_1_5_secondi_in_un_altro_tratto_non_si_ripete():
    sch = CueScheduler()
    sch.submit(_cue(CueCategory.WHEELSPIN, segment=4), now=100.0)
    assert sch.poll(100.0) is not None
    # L'auto ha cambiato tratto in uscita di curva: stessa frase, altro dedup_key.
    sch.submit(_cue(CueCategory.WHEELSPIN, segment=5), now=101.5)
    assert sch.poll(101.5) is None


def _parla_fino_a(sch, start, end, step=0.1):
    detti = []
    t = start
    while t <= end + 1e-9:
        c = sch.poll(round(t, 2))
        if c is not None:
            detti.append((round(t, 2), c.category))
        t += step
    return detti


def test_la_ripetizione_fermata_si_butta_non_si_rimanda():
    # La revisione finale: rimandata, l'urgente vive 5,5 s e usciva a 105,1.
    for cat in (CueCategory.WHEELSPIN, CueCategory.LOCKED):
        sch = CueScheduler()
        sch.submit(_cue(cat, segment=4), now=100.0)
        assert sch.poll(100.0) is not None
        sch.submit(_cue(cat, segment=5), now=101.5)
        assert _parla_fino_a(sch, 100.1, 106.0) == []


def test_stessa_categoria_a_5_1_secondi_si_dice():
    sch = CueScheduler()
    sch.submit(_cue(CueCategory.WHEELSPIN, segment=4), now=100.0)
    assert sch.poll(100.0) is not None
    sch.submit(_cue(CueCategory.WHEELSPIN, segment=5), now=105.1)
    assert sch.poll(105.1) is not None


def test_il_tetto_vale_anche_per_le_urgenti_e_non_blocca_le_altre_categorie():
    sch = CueScheduler()
    sch.submit(_cue(CueCategory.LOCKED, segment=1), now=100.0)
    assert sch.poll(100.0).category is CueCategory.LOCKED
    sch.submit(_cue(CueCategory.LOCKED, segment=2), now=101.6)
    assert sch.poll(101.6) is None
    sch.submit(_cue(CueCategory.WHEELSPIN, segment=2), now=101.7)
    assert sch.poll(101.7).category is CueCategory.WHEELSPIN


def test_time_loss_non_e_piu_una_parola_innesco():
    assert CueCategory.TIME_LOSS not in TRIGGER
    assert trigger_text(CueCategory.TIME_LOSS, "it") is None


def test_il_log_del_focus_dice_base_non_perdi():
    import inspect
    src = inspect.getsource(_focus_log_line)
    assert "| base " in src and "| perdi " not in src


def _spin_frames(n, **kw):
    return [synth.snap(pos=0.5, throttle=0.9, tc_active=0.6, speed_kmh=120.0,
                       gear="3", slip_ratio=(0.0, 0.0, 0.4, 0.4), **kw)
            for _ in range(n)]


def test_niente_pattinamento_sul_giro_di_uscita(tmp_path):
    eng, _ = _engine_with_reference(tmp_path)
    frames = [synth.snap(pos=0.5)] + _spin_frames(30)     # mai passato la linea
    eng.reader._frames = frames
    spoken = _run(eng, frames)
    assert not any(c.category is CueCategory.WHEELSPIN for c in spoken)
    eng.close()


def test_il_pattinamento_si_dice_dopo_la_linea(tmp_path):
    eng, _ = _engine_with_reference(tmp_path)
    frames = [synth.snap(pos=0.5)] + _crossing() + _spin_frames(30, completed_laps=1)
    eng.reader._frames = frames
    spoken = _run(eng, frames)
    assert any(c.category is CueCategory.WHEELSPIN for c in spoken)
    eng.close()
