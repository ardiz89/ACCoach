"""Cross-lap analysis: systematic vs sporadic losses + the benchmark ladder."""
from accoach.coaching.cue import CueCategory
from accoach.coaching.debrief import CornerLoss, LapDebrief
from accoach.coaching.trends import (
    benchmark_levels,
    classify_losses,
    session_recap,
    session_series,
)
from accoach.coaching.phases import PHASES, lap_time_split
from accoach.comparison import Reference
from accoach.track import detect_corners

import pytest

import synth


def _loss(index: int, ms: float, category: CueCategory = CueCategory.BRAKE_LATER) -> CornerLoss:
    return CornerLoss(index=index, entry_pos=0.2, apex_pos=0.3, exit_pos=0.4,
                      lost_ms=ms, category=category, message="m")


def _debrief(*losses: CornerLoss) -> LapDebrief:
    return LapDebrief("car", "track", 101000, 100000, losses=list(losses))


# --- systematic vs sporadic ------------------------------------------------

def test_recurring_loss_is_systematic():
    debriefs = [_debrief(_loss(0, 300)) for _ in range(4)]
    trends = classify_losses(debriefs)
    assert len(trends) == 1
    assert trends[0].corner_index == 0
    assert trends[0].systematic is True
    assert trends[0].kind == "systematic"
    assert trends[0].occurrences == 4


def test_one_off_loss_is_sporadic():
    # Big loss, but only once in four laps → not a weakness to train.
    debriefs = [_debrief(_loss(0, 900)), _debrief(), _debrief(), _debrief()]
    trends = classify_losses(debriefs)
    assert trends[0].systematic is False
    assert trends[0].kind == "sporadic"


def test_small_recurring_loss_is_not_systematic():
    debriefs = [_debrief(_loss(0, 50)) for _ in range(4)]   # recurs but trivial
    trends = classify_losses(debriefs)
    assert trends[0].systematic is False


def test_half_the_laps_really_means_half():
    """A loss in 2 laps out of 5 is 40% — it must not read as "systematic".

    Regression: recur_min used round(), and Python rounds half to even, so
    round(0.5 * 5) == 2 and the promised >=50% quietly became 40%. Same at n=9,
    where round(4.5) == 4 gave 44%.
    """
    for n, occurrences in ((5, 2), (9, 4)):
        debriefs = ([_debrief(_loss(0, 300))] * occurrences
                    + [_debrief()] * (n - occurrences))
        trends = classify_losses(debriefs)
        assert trends[0].occurrences == occurrences
        assert trends[0].systematic is False, f"{occurrences}/{n} is under half"


def test_exactly_half_the_laps_is_systematic():
    # The boundary itself stays inclusive: 3/6 is >= 50% and still counts.
    debriefs = [_debrief(_loss(0, 300))] * 3 + [_debrief()] * 3
    trends = classify_losses(debriefs)
    assert trends[0].systematic is True


def test_trends_sorted_by_total_cost():
    debriefs = [
        _debrief(_loss(0, 150), _loss(1, 400)),
        _debrief(_loss(0, 150), _loss(1, 400)),
        _debrief(_loss(0, 150), _loss(1, 400)),
    ]
    trends = classify_losses(debriefs)
    assert [t.corner_index for t in trends] == [1, 0]       # corner 1 costs more
    assert all(t.systematic for t in trends)


def test_dominant_category_wins():
    debriefs = [
        _debrief(_loss(0, 300, CueCategory.BRAKE_LATER)),
        _debrief(_loss(0, 300, CueCategory.BRAKE_LATER)),
        _debrief(_loss(0, 300, CueCategory.CARRY_SPEED)),
    ]
    assert classify_losses(debriefs)[0].category is CueCategory.BRAKE_LATER


def test_empty_debriefs():
    assert classify_losses([]) == []


# --- benchmark levels ------------------------------------------------------

def test_levels_best_only():
    levels = benchmark_levels(90000)
    assert [lv.key for lv in levels] == ["best"]
    assert levels[0].gain_ms == 0


def test_levels_with_ideal_and_pro():
    levels = benchmark_levels(90000, ideal_ms=89000, pro_ms=88000)
    keys = {lv.key: lv for lv in levels}
    assert set(keys) == {"best", "ideal", "pro"}
    assert keys["ideal"].gain_ms == 1000        # 1.0s of consistency available
    assert keys["pro"].gain_ms == 2000          # 2.0s to the PRO ceiling


def test_levels_pro_slower_than_you_is_negative_gain():
    levels = benchmark_levels(88000, pro_ms=90000)   # you beat the imported PRO
    pro = next(lv for lv in levels if lv.key == "pro")
    assert pro.gain_ms == -2000


def test_levels_empty_without_best():
    assert benchmark_levels(0) == []


def test_level_labels_translate():
    en = {lv.key: lv.label for lv in benchmark_levels(90000, ideal_ms=89000, lang="en")}
    it = {lv.key: lv.label for lv in benchmark_levels(90000, ideal_ms=89000, lang="it")}
    assert en["best"] == "Your best lap" and it["best"] == "Tuo miglior giro"
    assert it["ideal"] == "Ideale teorico"


# --- la serie per sessione -------------------------------------------------

_T = "2026-08-0{d}T{h}:{m}:00+00:00"


def _deb(lost_ms):
    """Un giro: con una perdita alla curva 0, oppure preso bene (lost_ms = 0)."""
    return _debrief(_loss(0, lost_ms)) if lost_ms else _debrief()


def _evening(day, hour, losses):
    """Una sessione: giri a due minuti l'uno dall'altro."""
    return [(_T.format(d=day, h=hour, m=f"{2 * i:02d}"), _deb(v))
            for i, v in enumerate(losses)]


def test_three_sessions_that_improve_read_as_a_falling_series():
    dated = (_evening(1, "18", [400, 380, 420]) +
             _evening(2, "18", [250, 230, 270]) +
             _evening(3, "18", [120, 100, 140]))
    pts = session_series(dated, 0)
    assert [p.median_ms for p in pts] == [400.0, 250.0, 120.0]
    assert pts[0].started < pts[-1].started        # dal più vecchio al più recente


def test_two_runs_the_same_afternoon_stay_two_points():
    """Se cambi qualcosa fra l'una e l'altra, lo devi poter vedere."""
    dated = _evening(1, "15", [400, 400, 400]) + _evening(1, "18", [200, 200, 200])
    assert len(session_series(dated, 0)) == 2


def test_a_session_without_that_corner_is_absent_not_a_zero():
    """Il buco a zero direbbe 'curva perfetta' dove invece non c'è il dato."""
    dated = _evening(1, "18", [400, 400, 400]) + _evening(2, "18", [0, 0])
    pts = session_series(dated, 0)
    assert len(pts) == 1                     # la seconda ha solo 2 giri: sotto min_laps
    dated2 = _evening(1, "18", [400, 400, 400]) + _evening(2, "18", [0, 0, 0])
    pts2 = session_series(dated2, 0)
    assert [p.median_ms for p in pts2] == [400.0, 0.0]   # tre giri buoni SONO un dato


def test_a_good_lap_counts_as_zero_not_as_missing():
    """Migliorare vuol dire anche sbagliare quella curva meno spesso."""
    dated = _evening(1, "18", [400, 0, 0])
    assert session_series(dated, 0)[0].median_ms == 0.0


def test_a_session_below_the_minimum_is_dropped():
    assert session_series(_evening(1, "18", [400, 400]), 0) == []


def test_undated_laps_are_dropped_not_guessed_into_a_session():
    dated = [("", _deb(400))] + _evening(1, "18", [200, 200, 200])
    pts = session_series(dated, 0)
    assert len(pts) == 1 and pts[0].median_ms == 200.0


# --- il recap di una sessione ----------------------------------------------


def _recap(amts):
    ref_lap = synth.build_lap()
    corners = detect_corners(ref_lap.samples)
    laps = [synth.build_lap(slow_corner=0, amt=a) for a in amts]
    return session_recap(laps, Reference(ref_lap), corners).recap


def test_the_families_add_up_to_the_average_gap():
    """Con i float pieni la media delle somme È la somma delle medie: nessun
    margine largo qui, solo il rumore in virgola mobile (misurato: 0.0 su
    diverse combinazioni di giri e griglie, vedi il report)."""
    r = _recap([10, 20, 30])
    total = sum(r.by_phase.values()) + r.launch_ms
    assert abs(total - r.gain_avg_ms) < 1e-6


def test_one_row_per_lap_with_its_worst_corner():
    r = _recap([10, 20, 30])
    assert len(r.laps) == 3
    assert all(l.worst_index >= 0 for l in r.laps)
    assert r.laps[2].gap_ms > r.laps[0].gap_ms  # amt=30 perde più di amt=10


def test_the_worst_corner_is_the_one_that_cost_most():
    r = _recap([30])
    assert r.laps[0].worst_index == 0           # synth rallenta la curva 0


def test_no_laps_no_recap():
    ref_lap = synth.build_lap()
    out = session_recap([], Reference(ref_lap), detect_corners(ref_lap.samples))
    assert out.recap is None
    # Non è l'orologio: la frase specifica non deve uscire di qui.
    assert out.reference_clock_broken is False


def test_a_lap_the_split_cannot_read_is_skipped_not_faked():
    """Un giro senza abbastanza campioni non entra: meglio due righe vere che
    tre con una inventata. ``len(r.laps) == 1`` da solo non basta a provarlo:
    il giro scartato potrebbe restare dentro i denominatori delle medie senza
    comparire in ``laps``. Il confronto con una sessione che contiene SOLO il
    giro leggibile chiude anche quel buco."""
    ref_lap = synth.build_lap()
    corners = detect_corners(ref_lap.samples)
    readable = synth.build_lap(slow_corner=0, amt=20)
    short = synth.build_lap()
    short.samples = short.samples[:2]
    reference = Reference(ref_lap)

    r = session_recap([readable, short], reference, corners).recap
    solo = session_recap([readable], reference, corners).recap

    assert len(r.laps) == 1
    assert r.gain_avg_ms == solo.gain_avg_ms
    assert r.launch_ms == solo.launch_ms
    assert r.by_phase == solo.by_phase


# --- l'orologio che non chiude ---------------------------------------------


def _shortfall(lap) -> float:
    """Quanto l'orologio di un giro manca il giro che dichiara.

    Ricalcolata qui a mano, non importata dalla guardia: un fixture che dice
    «questo giro ha l'orologio rotto» deve dimostrarlo con un'aritmetica sua,
    altrimenti sta solo ripetendo quello che il codice ha già deciso.
    """
    ss = lap.samples
    return abs((ss[-1].t_ms - ss[0].t_ms)
               - lap.lap_time_ms * (ss[-1].pos - ss[0].pos))


#: I due numeri che tengono ferma ``_CLOCK_TOL_FRAC``, presi dove sono stati
#: misurati e non un po' più in là.
#:
#: ``_WORST_HEALTHY`` è il **massimo d'archivio** di ``1 − copertura`` (59 giri
#: veri, 07/08/2026): il rumore più forte che la guardia non deve prendere. È il
#: numero che il commento di ``trends.py`` cita come pavimento della frazione.
#: ``_REAL_DEFECT_FRAC`` è il difetto vero: il metro del Red Bull Ring del
#: 02/08, 694 ms di scarto su un giro da 68.369 s.
#:
#: Fra i due c'è un corridoio di 2.2×, e i fixture stanno esattamente sui suoi
#: due bordi. Costruirli più larghi — un giro sano a 0.0025 e uno rotto a 0.015
#: — lasciava la frazione libera fra 0.0026 e 0.0145 con la suite tutta verde:
#: 5.6× di corridoio dove ne è stato misurato 2.2, cioè valori che l'archivio
#: sa già essere sbagliati (a 0.003 la guardia scarta il giro sano 3:09/70608 e
#: nomina una causa che non c'è; a 0.012 il metro rotto del Red Bull Ring, il
#: giro per cui la guardia esiste, torna a passare) e che nessun test vedeva.
_WORST_HEALTHY = 0.00462
_REAL_DEFECT_FRAC = 694 / 68_369          # 0.010151


def _healthy_long_lap(ms: int, **kw):
    """Un giro **lungo** e **sano**, con la copertura *peggiore* d'archivio.

    Serve perché la tolleranza non è più un numero fisso: la parte di scarto
    dovuta alla copertura cresce col giro, quindi un giro da otto minuti deve
    avere la stessa generosità di uno da uno. Il fixture riproduce il caso
    peggiore *sano*: l'ultimo campione cade prima della linea, a
    ``1 − copertura = _WORST_HEALTHY``, che è il massimo dell'archivio vero —
    non il p90, non un valore comodo: il bordo. E l'orologio non ha **nessun**
    errore, perché ``retime`` gli dà uno span esattamente pari a
    ``lap_time_ms`` — che è letteralmente ciò che succede a un giro il cui
    tempo è stato sostituito da ``trusted_lap_ms``, e due dei 59 giri veri sono
    già così.

    Quindi tutto lo scarto che questo giro mostra è **fabbricato dalla
    correzione per copertura**, non misurato: ``ms × _WORST_HEALTHY``. Ed è
    questo fixture a tenere la frazione da sotto: sotto 0.00462 lo scarta.
    """
    lap = synth.build_lap(**kw)
    lap.samples = lap.samples[:-1]
    # La griglia di ``build_lap`` è a passi di 1/400, che 0.00462 non lo
    # centra: l'ultimo campione lo si porta lì a mano. Resta ordinato — il
    # penultimo sta a 0.995 — e ``retime`` lavora sui tempi, non sulle
    # posizioni, quindi lo span resta esattamente ``ms``.
    lap.samples[-1].pos = 1.0 - _WORST_HEALTHY
    return synth.retime(lap, ms)


def _broken_lap(*, sign: int = 1, **kw):
    """Un giro con l'orologio rotto **quanto lo era quello vero**.

    ``skew_clock`` di 1500 ms su un giro da ~100 s metteva il fixture a 0.015
    di giro, mezzo corridoio oltre il difetto misurato: la frazione poteva
    salire fino a 0.0145 senza che niente diventasse rosso, e a 0.012 il metro
    del Red Bull Ring — l'unico giro per cui questa guardia esiste — sarebbe
    già tornato a passare. Il fixture sta al difetto vero, 0.0102 di giro, così
    la frazione è chiusa da sopra dove è stata misurata.

    Lo scarto è preso come **frazione** del giro, non come millisecondi fissi,
    perché è così che la soglia è costruita: un valore in ms non direbbe niente
    su un giro di durata diversa.
    """
    lap = synth.build_lap(**kw)
    return synth.skew_clock(lap, sign * round(lap.lap_time_ms * _REAL_DEFECT_FRAC))


def test_a_lap_whose_clock_does_not_cover_it_leaves_the_averages_too():
    """Un giro con l'orologio rotto non è un giro lento: è una registrazione
    con un buco, e il buco finisce tutto sul suo gap. Esce dalle righe **e**
    dai denominatori — controllato sulle medie, non sul conteggio: le righe
    potrebbero sparire mentre il giro resta dentro ``gain_avg_ms`` e
    ``by_phase``, ed è esattamente l'errore che un conteggio non vede."""
    ref_lap = synth.build_lap()
    corners = detect_corners(ref_lap.samples)
    reference = Reference(ref_lap)
    readable = synth.build_lap(slow_corner=0, amt=20)
    broken = _broken_lap(slow_corner=0, amt=40)
    # Il fixture dice *contro cosa* è rotto, e lo dice in frazione di giro
    # perché è quella la forma della soglia: 0.0102, il difetto vero, contro
    # 0.007 di tolleranza. Non un multiplo comodo — il bordo misurato.
    assert _shortfall(broken) / broken.lap_time_ms == \
        pytest.approx(_REAL_DEFECT_FRAC, rel=1e-3), "il fixture non ha rotto niente"
    assert _shortfall(readable) / readable.lap_time_ms < _WORST_HEALTHY, \
        "il giro sano deve restare sano"

    # Il canarino che rende il confronto capace di fallire: se il giro rotto
    # entrasse nelle medie, le sposterebbe. Senza questo, le uguaglianze sotto
    # passerebbero anche con la guardia inerte.
    good, bad = (lap_time_split(l, reference, corners) for l in (readable, broken))
    assert abs(good.gap_ms - bad.gap_ms) > 1.0
    assert good.by_phase() != bad.by_phase()

    r = session_recap([readable, broken], reference, corners).recap
    solo = session_recap([readable], reference, corners).recap
    assert [row.source_index for row in r.laps] == [0]
    assert r.gain_avg_ms == solo.gain_avg_ms
    assert r.by_phase == solo.by_phase
    assert r.launch_ms == solo.launch_ms


def test_a_reference_whose_clock_does_not_cover_it_voids_the_whole_run():
    """Se a non chiudere è il metro non è storta una riga, è storta l'uscita:
    ogni riga si misura contro di lui. Nessun recap, e il motivo torna dalla
    funzione che ha applicato la guardia — non lo ricava il chiamante."""
    ref_lap = _broken_lap(sign=-1)
    corners = detect_corners(ref_lap.samples)
    reference = Reference(ref_lap)
    # Rotto nell'altro verso — il criterio è simmetrico — ma della stessa
    # misura: il difetto vero d'archivio, 0.0102 di giro.
    assert _shortfall(ref_lap) / ref_lap.lap_time_ms == \
        pytest.approx(_REAL_DEFECT_FRAC, rel=1e-3), "il fixture non ha rotto il metro"
    laps = [synth.build_lap(slow_corner=0, amt=a) for a in (10, 20)]
    assert all(_shortfall(l) / l.lap_time_ms < _WORST_HEALTHY for l in laps), \
        "i giri sono sani: è il metro a non esserlo"

    out = session_recap(laps, reference, corners)
    assert out.recap is None
    assert out.reference_clock_broken is True


def test_the_guard_emptying_every_lap_still_does_not_blame_the_yardstick():
    """L'altro modo di restare senza recap per colpa della guardia: il metro è
    sano, ma la guardia scarta **tutti** i giri. Il recap è vuoto — e il motivo
    resta **falso**, perché quella frase parla solo del metro. Se un giorno
    l'uscita vuota di ``splits`` cominciasse a inoltrare il motivo, la
    schermata direbbe al pilota che il suo miglior giro è rotto quando l'unica
    cosa rotta sono gli altri: la causa sbagliata, affermata con sicurezza."""
    ref_lap = synth.build_lap()
    corners = detect_corners(ref_lap.samples)
    reference = Reference(ref_lap)
    assert _shortfall(ref_lap) / ref_lap.lap_time_ms < _WORST_HEALTHY, \
        "il metro deve essere sano"
    laps = [_broken_lap(slow_corner=0, amt=a) for a in (10, 20)]
    assert all(_shortfall(l) / l.lap_time_ms == pytest.approx(_REAL_DEFECT_FRAC, rel=1e-3)
               for l in laps), "i giri devono essere rotti"

    out = session_recap(laps, reference, corners)
    assert out.recap is None
    assert out.reference_clock_broken is False


def test_a_short_lap_just_inside_the_floor_stays_and_stays_counted():
    """Il **pavimento** dei 250 ms, cioè l'unico regime in cui vale ancora un
    numero fisso: sotto i 250/0.007 = 36 s di giro la frazione diventa più
    stretta del rumore, e su un giro da 25 s varrebbe 175 ms. Un giro a 200 ms
    di scarto — sopra la frazione, sotto il pavimento — resta nelle righe e
    resta nella media, che qui è ricalcolata a mano dai due split invece di
    essere confrontata con se stessa.

    È questo test che tiene fermo il numero 250: abbassarlo lo fa diventare
    rosso, mentre ogni giro di lunghezza normale è governato dalla frazione e
    non se ne accorgerebbe."""
    ref_lap = synth.retime(synth.build_lap(), 25_000)
    corners = detect_corners(ref_lap.samples)
    reference = Reference(ref_lap)
    readable = synth.retime(synth.build_lap(slow_corner=0, amt=20), 25_000)
    near = synth.skew_clock(synth.retime(synth.build_lap(slow_corner=0, amt=40),
                                         25_000), 200)
    assert _shortfall(near) == pytest.approx(200, abs=2)
    assert _shortfall(near) > 25_000 * 0.007, "la frazione da sola lo scarterebbe"
    assert _shortfall(near) < 250, "il fixture deve stare dentro, ma di poco"

    splits = [lap_time_split(l, reference, corners) for l in (readable, near)]
    r = session_recap([readable, near], reference, corners).recap
    assert [row.source_index for row in r.laps] == [0, 1]
    assert r.gain_avg_ms == pytest.approx(sum(s.gap_ms for s in splits) / 2, abs=1e-6)


def test_a_long_healthy_lap_is_not_judged_broken_by_a_flat_millisecond_count():
    """Un giro da otto minuti (Nordschleife su AC) con la copertura peggiore
    d'archivio **non** è una registrazione rotta, e la tolleranza deve crescere
    col giro perché la parte di scarto dovuta alla copertura cresce col giro.

    Il fixture non ha nessun errore d'orologio: il suo span è esattamente
    ``lap_time_ms``. Tutto il suo scarto — 480 s × 0.00462 = 2218 ms, più del
    doppio del difetto vero in millisecondi ma su un giro sette volte più
    lungo — è **fabbricato** dalla correzione per copertura che applichiamo
    noi. Con una tolleranza in millisecondi fissi questo giro sarebbe scartato
    quasi nove volte sopra la soglia, l'uscita perderebbe il recap e la
    schermata affermerebbe una causa che lì non esiste: il falso positivo che
    *parla*, il peggiore.

    È questo test a tenere la frazione da sotto: la sua tolleranza vale
    480 000 × frazione, e sotto 0.00462 diventa più stretta dello scarto che il
    fixture ha per costruzione. Provato su tutt'e due i rami della guardia —
    come metro e come riga — perché è il ramo del metro quello che fa comparire
    la frase."""
    ref_lap = _healthy_long_lap(480_000)
    corners = detect_corners(ref_lap.samples)
    reference = Reference(ref_lap)
    slower = _healthy_long_lap(486_000, slow_corner=0, amt=20)
    assert _shortfall(ref_lap) == pytest.approx(480_000 * _WORST_HEALTHY, abs=5)
    assert _shortfall(ref_lap) > 250, "senza frazione questo metro sarebbe scartato"
    assert _shortfall(slower) > 250, "e questa riga con lui"

    out = session_recap([slower], reference, corners)
    assert out.reference_clock_broken is False
    assert out.recap is not None
    assert [row.source_index for row in out.recap.laps] == [0]


def test_a_lap_simply_not_recorded_end_to_end_is_not_a_broken_lap():
    """La forma del criterio, non la sua soglia. Un giro vero non comincia a
    pos 0.000 e non finisce a 1.000: i campioni ne coprono un pezzo, e il loro
    orologio dura di meno *per quel motivo lì*. Misurato contro il giro intero
    (``|span − lap_time_ms|``) questo giro sembrerebbe rotto di cinque secondi
    e sparirebbe; misurato contro la frazione che i campioni coprono è sano.

    Nell'archivio vero la differenza è la stessa: nella forma assoluta mediana
    102 ms e p90 168, senza nessun vuoto dove mettere una soglia; nella forma
    corretta mediana 34 e p90 86.5, e il primo giro rotto a 326. I due p90 sono
    ricalcolati col metodo che ``trends.py`` dichiara accanto ai suoi
    (``statistics.quantiles(n=10)``): le due copie di questa misura, in due
    file dello stesso ramo, portavano 167 e 72 contro 168 e 86.5."""
    ref_lap = synth.build_lap()
    corners = detect_corners(ref_lap.samples)
    reference = Reference(ref_lap)
    partial = synth.build_lap(slow_corner=0, amt=20)
    partial.samples = partial.samples[10:-10]          # né dalla linea né fino alla linea

    naive = abs((partial.samples[-1].t_ms - partial.samples[0].t_ms)
                - partial.lap_time_ms)
    assert naive > 1000, "il fixture non distingue le due forme del criterio"
    assert _shortfall(partial) < 250

    r = session_recap([partial], reference, corners).recap
    assert r is not None
    assert [row.source_index for row in r.laps] == [0]


def test_source_index_survives_a_drop_reason_that_does_not_exist_yet(monkeypatch):
    """A caller must be able to pair a ``RecapLap`` back to the lap it came
    from without knowing *why* any other lap was dropped — today that reason
    is "too few samples", but the contract (``source_index`` = position in
    the exact list passed in) cannot depend on that being the only reason.

    There is no second drop rule to reach for today, so this stands one up
    with a monkeypatch on ``lap_time_split`` (the drop is decided by identity,
    nothing about sample count) and checks ``source_index`` still points every
    surviving row at its true position in ``laps`` — including the positions
    that shift once an EARLIER lap is the one dropped, which a naive "count
    from the front" would get wrong.
    """
    from accoach.coaching import phases as phases_mod

    ref_lap = synth.build_lap()
    corners = detect_corners(ref_lap.samples)
    reference = Reference(ref_lap)
    laps = [synth.build_lap(slow_corner=0, amt=a) for a in (10, 20, 30, 40)]
    real_split = phases_mod.lap_time_split

    def _fake_split(lap, ref, corns):
        if lap is laps[1]:            # a rule with nothing to do with length
            return None
        return real_split(lap, ref, corns)

    monkeypatch.setattr(phases_mod, "lap_time_split", _fake_split)

    r = session_recap(laps, reference, corners).recap

    assert [row.source_index for row in r.laps] == [0, 2, 3]
    for row in r.laps:
        assert row.lap_time_ms == laps[row.source_index].lap_time_ms


def test_worst_ms_is_not_rounded_and_reference_is_the_sessions_best():
    """Stessa trappola del Task 1: sulla griglia condivisa (stesso ``n`` per
    riferimento e giro) i ritardi tornano interi e ``round(x, 1)`` sarebbe
    un'operazione nulla, incapace di rilevare una regressione. Uno scarto fra
    l'``n`` del riferimento e quello del giro rompe la griglia e rende i
    ritardi genuinamente frazionari, così un ``round`` reintrodotto nel
    calcolo si vede.

    ``reference_ms`` deve essere il tempo del MIGLIOR giro della sessione (il
    riferimento passato), non quello di uno dei giri della lista.
    """
    ref_lap = synth.build_lap(n=397)
    reference = Reference(ref_lap)
    corners = detect_corners(ref_lap.samples)
    lap = synth.build_lap(slow_corner=0, amt=17)          # n=401 di default
    split = lap_time_split(lap, reference, corners)
    expected_worst = max(c.lost_ms for c in split.corners)
    assert expected_worst != int(expected_worst), "il fixture deve dare un valore frazionario"

    r = session_recap([lap], reference, corners).recap
    assert r.reference_ms == reference.lap_time_ms
    assert r.laps[0].worst_ms == expected_worst


def test_by_phase_launch_and_gain_avg_are_not_rounded():
    """I restanti tre siti di ``round(...)`` del piano originale: ``by_phase``
    (4 valori), ``launch_ms`` e ``gain_avg_ms``.

    Un margine largo come ``< 0.5`` su "la somma delle famiglie torna alla
    media del gap" NON può rilevare un arrotondamento reintrodotto qui, con
    NESSUN fixture: arrotondare in modo indipendente 4 famiglie + launch (un
    lato della somma) e gain_avg_ms (l'altro lato) sposta il confronto di al
    più 5*0.05 + 0.05 = 0.3ms per disuguaglianza triangolare, sempre sotto
    0.5ms. Serve un confronto diretto col valore medio ricalcolato a mano dai
    float pieni di ``lap_time_split``, non una verifica di somma.
    """
    # amt=(10, 20, 30) would NOT do here: gap_ms is read at the anchored
    # endpoints (pos 0.0 / 1.0), which Reference pins exactly no matter the
    # grid mismatch (see the comment on LapSplit.gap_ms in phases.py) — so a
    # gap_ms average, unlike the interior cuts, stays a round number even
    # off-grid whenever the amounts are evenly spaced (194/388/582 average to
    # exactly 388.0). An IRREGULAR amt sequence is what makes the three gaps
    # not divide evenly, and that is what makes gain_avg_ms itself fractional
    # — checked below, not assumed.
    ref_lap = synth.build_lap(n=397)
    reference = Reference(ref_lap)
    corners = detect_corners(ref_lap.samples)
    laps = [synth.build_lap(slow_corner=0, amt=a) for a in (10, 17, 30)]
    splits = [lap_time_split(lap, reference, corners) for lap in laps]
    n = len(splits)

    raw = ([s.launch_ms for s in splits] + [s.gap_ms for s in splits] +
           [v for s in splits for v in s.by_phase().values()])
    assert any(v != int(v) for v in raw), "il fixture deve dare valori frazionari"

    expected_launch = sum(s.launch_ms for s in splits) / n
    expected_gain = sum(s.gap_ms for s in splits) / n
    expected_by_phase = {p: sum(s.by_phase()[p] for s in splits) / n for p in PHASES}

    # The canary that matters is on the AVERAGED quantity being asserted, not
    # on its raw per-lap components: a component can be fractional while the
    # mean of several of them still lands on a clean tenth (exactly the trap
    # amt=(10, 20, 30) fell into for gain_avg_ms). round(x, 1) == x is a
    # no-op and would let a reintroduced round() through undetected.
    for name, value in [("launch", expected_launch), ("gain", expected_gain),
                        *expected_by_phase.items()]:
        assert round(value, 1) != value, \
            f"expected_{name} == its own round(x, 1): il fixture non prova nulla qui"

    r = session_recap(laps, reference, corners).recap
    assert r.launch_ms == pytest.approx(expected_launch, abs=1e-6)
    assert r.gain_avg_ms == pytest.approx(expected_gain, abs=1e-6)
    for p in PHASES:
        assert r.by_phase[p] == pytest.approx(expected_by_phase[p], abs=1e-6)
