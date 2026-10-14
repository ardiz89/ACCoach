"""La stessa frase non si ripete nello stesso giro, salvo che sia il focus.

«Stai veleggiando» e' il 30% di tutto quello che il coach ha detto in pista
(211 frasi su 694 nel log, al 14/10), e il 14/10 a Imola e' uscito tre volte in un
giro solo, alle 22:05-22:06. Lo scheduler non lo fermava perche' non sapeva
cosa fosse un giro: il suo «gia' detto» e' la stessa categoria **nello stesso
ventesimo di pista** entro 20 secondi, e un veleggio in tre punti diversi sono
tre consigli diversi. Il budget di attenzione la accorciava («veleggi») ma non
la diradava.

La regola sta dove si decide cosa dire, non nel rilevatore del veleggio: vale
per ogni consiglio di tecnica. Gli eventi acuti (bloccaggio, pattinamento) e le
chiamate box non c'entrano: sono eventi, ognuno e' suo. Il tema del focus e la
sua curva invece si possono ripetere: sono quello che si sta allenando.
"""
from accoach.coaching.cue import Cue, CueCategory
from accoach.coaching.scheduler import CueScheduler

import synth
from test_focus_parla_col_tema import _SessioneCheParla


def _cue(category, segment, priority=300.0):
    return Cue(category=category, message=category.value, priority=priority,
               segment=segment, pos=0.0)


def _di(sch, category, segment, now):
    sch.submit(_cue(category, segment), now=now)
    return sch.poll(now)


def test_la_stessa_frase_di_tecnica_non_si_ripete_nello_stesso_giro():
    sch = CueScheduler()
    assert _di(sch, CueCategory.COASTING, 3, 100.0) is not None
    # Un altro punto della pista, ben oltre i 20 secondi del «gia' detto».
    assert _di(sch, CueCategory.COASTING, 9, 140.0) is None


def test_al_giro_dopo_si_puo_ridire():
    sch = CueScheduler()
    assert _di(sch, CueCategory.COASTING, 3, 100.0) is not None
    sch.new_lap()
    assert _di(sch, CueCategory.COASTING, 9, 140.0) is not None


def test_una_frase_diversa_nello_stesso_giro_passa():
    sch = CueScheduler()
    assert _di(sch, CueCategory.COASTING, 3, 100.0) is not None
    assert _di(sch, CueCategory.TRAIL_BRAKE, 9, 140.0) is not None


def test_anche_la_lode_si_dice_una_volta_per_giro():
    sch = CueScheduler()
    assert _di(sch, CueCategory.GOOD, 3, 100.0) is not None
    assert _di(sch, CueCategory.GOOD, 7, 140.0) is None


def test_il_tema_del_focus_si_puo_ripetere():
    sch = CueScheduler()
    sch.set_focus("traction")
    assert _di(sch, CueCategory.COASTING, 3, 100.0) is not None
    assert _di(sch, CueCategory.COASTING, 9, 140.0) is not None


def test_la_curva_del_focus_si_puo_ripetere_anche_se_il_tema_non_chiude_la_voce():
    """Il focus sulla linea non restringe la voce, ma la sua curva resta sua."""
    sch = CueScheduler()
    sch.set_focus(None)
    sch.set_focus_corner(5)
    assert _di(sch, CueCategory.TIME_LOSS, 2, 100.0) is not None
    assert _di(sch, CueCategory.TIME_LOSS, 5, 140.0) is not None
    assert _di(sch, CueCategory.TIME_LOSS, 7, 180.0) is None


def test_gli_eventi_acuti_non_hanno_tetto_per_giro():
    sch = CueScheduler()
    assert _di(sch, CueCategory.LOCKED, 3, 100.0) is not None
    assert _di(sch, CueCategory.LOCKED, 9, 140.0) is not None


def test_conta_cio_che_e_stato_detto_non_cio_che_e_stato_proposto():
    """Un veleggio scartato perche' fuori tema non brucia il giro: se il focus
    se ne va, il prossimo si dice."""
    sch = CueScheduler()
    sch.set_focus("braking")
    assert _di(sch, CueCategory.COASTING, 3, 100.0) is None
    sch.set_focus(None)
    assert _di(sch, CueCategory.COASTING, 9, 140.0) is not None


# --- dal motore: il giro e' quello del traguardo -----------------------------

def _veleggia_due_volte(lap):
    """Due tratti a pedali sollevati sui rettilinei, 40 secondi l'uno dall'altro."""
    for s in lap.samples:
        if 0.45 <= s.pos <= 0.50 or 0.88 <= s.pos <= 0.93:
            s.throttle = 0.0
            s.brake = 0.0
    return lap


def test_dal_motore_il_veleggio_esce_una_volta_per_giro_e_torna_al_giro_dopo(tmp_path):
    s = _SessioneCheParla(tmp_path)
    s.avvicinamento()
    lap = _veleggia_due_volte(synth.build_lap(clean=True))
    s.giro(lap)
    s.giro(lap)
    proposti = [g for g, c in s.proposti if c is CueCategory.COASTING]
    assert proposti.count(1) == 2 and proposti.count(2) == 2, (
        f"fixture: il veleggio doveva essere proposto due volte a giro: {proposti}")
    detti = [g for g, c in s.detti if c is CueCategory.COASTING]
    assert detti == [1, 2], f"veleggio detto ai giri {detti}: una volta per giro"
    s.eng.close()
