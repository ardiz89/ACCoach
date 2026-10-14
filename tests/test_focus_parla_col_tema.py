"""Col focus acceso il coach non resta muto in cambio di niente.

Trovato in pista il 14/10 al Red Bull Ring, e riprodotto rigiocando quei giri
veri dentro il motore. Due focus, due silenzi:

* **«linea» sulla Curva 7**: in tre giri il coach ha detto due lodi e due
  sottosterzi, mai una parola di tecnica. «Linea» e' il nome che diamo a
  ``TIME_LOSS``, cioe' a *una perdita senza una causa trovata*: non c'e' un
  rilevatore di linea, e l'unica parola del tema e' «qui perdi», che non dice
  cosa fare. In cambio il filtro zittiva veleggio, rilascio del freno e gas a
  meta'.
* **«frenata» sulla Curva 5**: un giro intero con zero frasi. Il giro prima il
  pilota aveva perso tempo proprio li', l'analyzer l'aveva messo da parte per
  dirlo all'avvicinamento — ma l'aveva classificato «tempo perso», non
  «frenata», e il filtro l'ha buttato. Il focus e la voce misurano la stessa
  curva con due giudizi diversi (il focus la *peggiore* della finestra, la voce
  il giro appena chiuso), e quando dissentono vinceva il silenzio proprio nella
  curva che il focus aveva detto di lavorare.

Quanto offre ogni tema, misurato sui 60 giri di cinque sessioni vere col filtro
spento (giri con almeno un consiglio proposto su quel tema): trazione 53,
linea 33, frenata 27, percorrenza 17. Trazione e frenata hanno rilevatori che
parlano in qualunque punto del giro (veleggio, gas a meta', rilascio del
freno); percorrenza e linea esistono **solo** come verdetto su una curva gia'
persa.
"""
from accoach.coaching.analyzer import CornerStats, classify_corner
from accoach.coaching.cue import (CORNER_CATEGORIES, Cue, CueCategory,
                                  gates_voice)
from accoach.coaching.focus import _brief_pact
from accoach.coaching.scheduler import CueScheduler

import synth
from test_engine_giro_salvato import _Sessione


def _cue(category, segment, priority=300.0):
    return Cue(category=category, message=category.value, priority=priority,
               segment=segment, pos=0.0)


# --- la curva del focus parla sempre ---------------------------------------

def test_nella_curva_del_focus_il_consiglio_di_curva_passa_anche_fuori_tema():
    """Il focus misura la perdita in quella curva qualunque ne sia la causa
    (`debrief.loss_at`): una perdita li' e' il focus, comunque la si chiami."""
    sch = CueScheduler()
    sch.set_focus("braking")
    sch.set_focus_corner(5)
    sch.submit(_cue(CueCategory.TIME_LOSS, segment=5))
    chosen = sch.poll(now=100.0)
    assert chosen is not None and chosen.category is CueCategory.TIME_LOSS


def test_fuori_dalla_curva_del_focus_il_fuori_tema_resta_zitto():
    sch = CueScheduler()
    sch.set_focus("braking")
    sch.set_focus_corner(5)
    sch.submit(_cue(CueCategory.TIME_LOSS, segment=6))
    assert sch.poll(now=100.0) is None


def test_la_curva_del_focus_apre_solo_i_consigli_di_curva():
    """`segment` vuol dire due cose: per l'analyzer e' la curva, per i
    rilevatori dal vivo e' un ventesimo di pista. Un veleggio nel ventesimo 5
    non e' la curva 5."""
    sch = CueScheduler()
    sch.set_focus("braking")
    sch.set_focus_corner(5)
    sch.submit(_cue(CueCategory.COASTING, segment=5))
    assert sch.poll(now=100.0) is None


def test_togliere_il_focus_dimentica_anche_la_curva():
    """Altrimenti il cambio d'auto si porterebbe dietro la curva dell'altra pista."""
    sch = CueScheduler()
    sch.set_focus("braking")
    sch.set_focus_corner(5)
    sch.set_focus(None)
    assert sch.focus_corner is None
    sch.set_focus("braking")
    sch.submit(_cue(CueCategory.TIME_LOSS, segment=5))
    assert sch.poll(now=100.0) is None


# --- un tema che si dice solo a curva persa non chiude la voce --------------

def test_percorrenza_e_linea_non_chiudono_la_voce():
    assert not gates_voice(CueCategory.CARRY_SPEED)
    assert not gates_voice(CueCategory.TIME_LOSS)


def test_frenata_e_trazione_la_chiudono():
    for cat in (CueCategory.BRAKE_LATER, CueCategory.BRAKE_EARLIER,
                CueCategory.LESS_BRAKE, CueCategory.MORE_THROTTLE):
        assert gates_voice(cat), cat


def test_le_categorie_di_curva_sono_esattamente_quelle_di_classify_corner():
    """La regola sopra si regge su questo insieme: una categoria nuova in
    `classify_corner` che mancasse qui farebbe chiudere la voce a un tema che si
    dice solo a curva persa, e una categoria qui che classify_corner non emette
    aprirebbe la curva del focus a un ventesimo di pista."""
    seen = set()
    for lost in (-400.0, 0.0, 300.0):
        for early in (False, True):
            for late in (False, True):
                for dthr in (0.0, 0.3):
                    for dbrk in (0.0, 0.3):
                        for dspd in (0.0, 10.0):
                            cue = classify_corner(CornerStats(
                                lost_ms=lost, throttle_live=0.5 - dthr,
                                throttle_ref=0.5, brake_live=0.2 + dbrk,
                                brake_ref=0.2, min_speed_live=100.0 - dspd,
                                min_speed_ref=100.0, braking_early=early,
                                braking_late=late), 0, 0.5)
                            if cue is not None:
                                seen.add(cue.category)
    assert seen == set(CORNER_CATEGORIES)


def test_nessun_patto_per_un_tema_che_non_chiude_la_voce():
    """Il patto promette «solo parole sulla linea»: se la voce resta aperta, la
    promessa sarebbe falsa al primo veleggio."""
    assert _brief_pact(CueCategory.TIME_LOSS, "it") == ""
    assert _brief_pact(CueCategory.CARRY_SPEED, "it") == ""
    assert _brief_pact(CueCategory.MORE_THROTTLE, "it")


# --- dal motore, con giri consegnati come dal vivo --------------------------

def _gas_basso(lap, quota=0.5):
    """Lo stesso giro lento, ma col gas a meta' nella prima curva: per la voce e
    per il focus diventa una perdita di trazione invece che di percorrenza."""
    lo, hi = synth._ZONES[0]
    for s in lap.samples:
        if lo <= s.pos <= hi:
            s.throttle *= quota
    return lap


class _SessioneCheParla(_Sessione):
    """La sessione di `test_engine_giro_salvato`, che tiene anche cio' che e'
    stato DETTO: qui la domanda e' proprio se il filtro lascia passare."""

    def __init__(self, tmp_path) -> None:
        super().__init__(tmp_path)
        self.detti: list[tuple[int, CueCategory]] = []

    def _tick(self, **kw) -> None:
        self.feed.snap = synth.snap(completed_laps=self.completed, is_acc=True, **kw)
        st = self.eng.tick(self.now)
        if st.spoken is not None:
            self.detti.append((self.completed, st.spoken.category))
        self.now += 0.5


def test_la_curva_del_focus_si_sente_anche_quando_la_voce_la_chiama_in_un_altro_modo(tmp_path):
    """Il caso della Curva 5, dal motore: il focus e' la trazione nella prima
    curva, poi il pilota ci perde di nuovo ma per la voce e' «percorrenza»."""
    s = _SessioneCheParla(tmp_path)
    s.avvicinamento()
    gas = _gas_basso(synth.build_lap(slow_corner=0, amt=30, clean=True))
    s.giro(gas)
    s.giro(gas, salva=gas)
    s.giro(gas, salva=gas)
    velocita = synth.build_lap(slow_corner=0, amt=30, clean=True)
    s.giro(velocita, salva=gas)        # qui nasce il focus; la voce vede «percorrenza»
    assert s.eng.scheduler.focus_theme == "traction", "fixture: il focus non e' la trazione"
    s.giro(velocita, salva=velocita)   # all'avvicinamento della prima curva
    assert s.eng.scheduler.focus_theme == "traction", "fixture: il focus e' cambiato"
    detti = [c for g, c in s.detti if g == 5]
    assert CueCategory.CARRY_SPEED in detti, (
        f"il pilota ha riperso tempo nella curva del focus e non gli e' stato "
        f"detto niente: {detti}")
    s.eng.close()


def test_il_motore_dice_allo_scheduler_qual_e_la_curva_del_focus(tmp_path):
    s = _Sessione(tmp_path)
    s.avvicinamento()
    lento = synth.build_lap(slow_corner=0, amt=30, clean=True)
    s.giro(lento)
    for _ in range(3):
        s.giro(lento, salva=lento)
    focus = s.eng._focus_report.focus
    assert focus is not None, "fixture: nessun focus eletto"
    corner = next(c for c in s.eng._corners if c.index == focus.corner_index)
    assert s.eng.scheduler.focus_corner == s.eng.analyzer.zone_at(corner.apex_pos)
    s.eng.close()


class _NoReader:
    def read(self): ...
    def close(self): ...


def _motore_con_due_numerazioni(tmp_path, voce):
    """Il focus conta le curve sul metro fermo, la voce su quello di adesso, e il
    metro di adesso ha una curva in piu' in testa: lo stesso indice e' un'altra
    curva."""
    from dataclasses import replace

    from accoach.coaching.focus import Focus, FocusKind, FocusReport
    from accoach.comparison import Reference
    from accoach.engine import CoachEngine
    from accoach.track import Corner, detect_corners

    eng = CoachEngine(reader=_NoReader(), voice=None, laps_dir=tmp_path)
    ref = synth.build_lap(n=300, clean=True)
    del_focus = detect_corners(ref.samples)                     # indici 0, 1
    extra = Corner(index=0, entry_pos=0.02, apex_pos=0.05, exit_pos=0.08)
    di_adesso = [extra] + [replace(c, index=c.index + 1) for c in del_focus]
    eng._focus_ref = (Reference(ref), del_focus)
    eng._corners = di_adesso
    eng.analyzer.set_corners(voce(di_adesso))
    eng._focus_report = FocusReport(
        FocusKind.DRILL, "", focus=Focus(
            corner_index=1, name="Curva 2", theme="trazione",
            category=CueCategory.MORE_THROTTLE, baseline_ms=300.0, drill=""))
    return eng, del_focus[1]


def test_la_curva_del_focus_si_cerca_sul_metro_del_focus(tmp_path):
    eng, curva = _motore_con_due_numerazioni(tmp_path, lambda cs: cs)
    assert eng._focus_zone() == eng.analyzer.zone_at(curva.apex_pos)
    eng.close()


def test_una_curva_del_focus_che_non_cade_in_nessuna_zona_non_apre_niente(tmp_path):
    """Meglio nessuna curva aperta che quella accanto."""
    eng, curva = _motore_con_due_numerazioni(
        tmp_path, lambda cs: [c for c in cs if not c.contains(0.709)])
    assert eng.analyzer.zone_at(curva.apex_pos) == -1, "fixture: l'apex cade in una zona"
    assert eng._focus_zone() is None
    eng.close()


def test_un_focus_su_una_curva_che_non_esiste_non_apre_niente(tmp_path):
    eng, _curva = _motore_con_due_numerazioni(tmp_path, lambda cs: cs)
    eng._focus_ref = (eng._focus_ref[0], [])
    assert eng._focus_zone() is None
    eng.close()


def test_un_focus_sulla_percorrenza_lascia_parlare_il_resto(tmp_path):
    """Il focus resta (pannello, verdetti, curva): cambia solo che la voce non
    viene ristretta a un tema che non avrebbe parole da darle."""
    s = _Sessione(tmp_path)
    s.avvicinamento()
    lento = synth.build_lap(slow_corner=0, amt=30, clean=True)
    s.giro(lento)
    for _ in range(3):
        s.giro(lento, salva=lento)
    focus = s.eng._focus_report.focus
    assert focus is not None and focus.category is CueCategory.CARRY_SPEED, (
        "fixture: il focus doveva essere la percorrenza")
    assert s.eng.scheduler.focus_theme is None
    s.eng.close()
