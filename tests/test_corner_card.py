"""Il blocco `corner`: il consuntivo muto dell'ultima curva chiusa.

Tre casi in cui non deve esserci — senza riferimento, su un giro non
rappresentativo, e prima della prima curva — e uno in cui deve esserci anche se
il coach non ha niente da dire. Quest'ultimo è il punto di tutta la feature.
"""
from dataclasses import replace

from accoach.coaching.analyzer import _LOSS_MS
from accoach.engine import CoachEngine
from accoach.recording.storage import save_lap

import synth


class _StubReader:
    def __init__(self, frames):
        self._frames = frames
        self._i = 0

    def read(self):
        s = self._frames[min(self._i, len(self._frames) - 1)]
        self._i += 1
        return s

    def close(self):
        pass


#: Millisecondi persi per frame dentro la curva 0 quando `slow=True`. Sui ~15
#: frame che cadono nella zona rilevata fanno ~0,45 s: sopra `_LOSS_MS` (la
#: soglia con cui il coach apre bocca) e ben sotto i 3 s del gate `off_pace`,
#: che renderebbe il giro non rappresentativo e butterebbe la carta.
_SLOW_MS_PER_FRAME = 30

#: Durata del giro guidato. `synth.build_lap()` — il riferimento su disco — dura
#: 100.000 ms: questi 200 ms in più, spalmati su tutto il giro, servono a farne
#: un giro **più lento**, così il motore non lo elegge nuovo riferimento a metà
#: corsa e i giri successivi non finiscono a confrontarsi con se stessi. Spalmati
#: e non concentrati: dentro una curva valgono ~36 ms, sotto `_LOSS_MS`, quindi
#: un giro "normale" resta verde.
_LAP_MS = 100200


def _reference_lap():
    """Il giro su disco contro cui si misura.

    `clean=True` non è un dettaglio: un giro **giudicato pulito** batte uno mai
    giudicato *a prescindere dal tempo* (`_find_reference_by_scan`), e con
    `clean=None` il primo giro guidato — più lento — si prendeva comunque il
    posto di riferimento. Da lì in poi ogni giro si confrontava con se stesso e
    tutti i `lost_ms` erano 0,0.
    """
    return synth.build_lap(clean=True)


def _lap_frames(completed, n=80, slow=False, in_pit=False):
    """I frame di un giro. `slow` perde velocità **e tempo** nella curva 0.

    Il tempo va perso davvero, e sulla scala del riferimento. Prima il
    cronometro era `i * 100` — un giro di 8 s contro un riferimento di 100 s,
    quindi il delta esplodeva, il giro usciva `off_pace` e il primo giro pieno
    guidato finiva per diventare lui il riferimento (più «veloce»). Da lì in poi
    ogni giro era confrontato con se stesso: `lost_ms` valeva 0,0 con `slow` e
    senza, e un test che chiedeva «porta i decimi misurati» passava lo stesso.
    Adesso il cronometro segue la scala di `synth.build_lap` (vedi `_LAP_MS`),
    così un giro guidato è davvero un po' più lento del riferimento e non se lo
    mangia.
    """
    frames = []
    lost = 0
    for i in range(n):
        pos = i / (n - 1)
        spd, brake, thr, steer = synth._profile(pos)
        if slow and 0.16 <= pos <= 0.40:
            spd = max(spd - 30.0, 90.0)
            lost += _SLOW_MS_PER_FRAME
        frames.append(synth.snap(
            pos=pos, completed_laps=completed,
            current_lap_ms=int(pos * _LAP_MS) + lost,
            last_lap_ms=_LAP_MS + lost, speed_kmh=spd, throttle=thr, brake=brake,
            steer_angle=steer, in_pit=in_pit,
        ))
    return frames


def _run(tmp_path, frames, reference=True):
    """Guida `frames` col riferimento già su disco; torna (engine, ultimo stato)."""
    if reference:
        save_lap(_reference_lap(), tmp_path)
    eng = CoachEngine(reader=_StubReader(frames), voice=None, laps_dir=tmp_path)
    st = None
    for _ in range(len(frames)):
        st = eng.tick(0.0)
    return eng, st


def _trace(tmp_path, frames, reference=True):
    """Come `_run`, ma tiene *tutti* i tick: torna (engine, [(pos, corner)]).

    Guardare solo l'ultimo stato è quello che ha nascosto per nove task un
    riquadro assente sul 39% di ogni giro.
    """
    if reference:
        save_lap(_reference_lap(), tmp_path)
    eng = CoachEngine(reader=_StubReader(frames), voice=None, laps_dir=tmp_path)
    out = []
    for f in frames:
        out.append((f.lap_position, eng.tick(0.0).corner))
    return eng, out


def _three_laps(**kw):
    return _lap_frames(0, **kw) + _lap_frames(1, **kw) + _lap_frames(2, **kw)


def test_no_card_without_a_reference(tmp_path):
    """Prima sessione su auto o pista nuova: non c'è niente contro cui misurare.

    Solo due giri, non tre: `_lap_frames` azzera `pos` a ogni giro, e quello è
    lo stesso segnale di «passaggio dal traguardo» che il registratore guarda
    per chiudere un giro. Con tre giri il primo giro pieno (il secondo blocco)
    si chiude e si salva DENTRO questo test, e il motore lo rincorre subito
    come nuovo riferimento (comportamento esistente, corretto in generale) —
    il che smentirebbe proprio il «senza riferimento» che il test vuole
    provare. Due giri bastano per uscire dall'out-lap (`quiet` diventa
    "no_reference") senza mai chiudere un giro intero.
    """
    eng, st = _run(tmp_path, _lap_frames(0) + _lap_frames(1), reference=False)
    assert eng.saved_laps == 0
    assert st.quiet == "no_reference"
    assert st.corner is None
    eng.close()


def test_a_corner_taken_well_still_shows_a_card(tmp_path):
    """Il caso che oggi non arriva mai a schermo: la curva presa bene."""
    eng, st = _run(tmp_path, _three_laps())
    assert st.corner is not None
    assert st.corner["level"] == "ok"
    assert abs(st.corner["lost_ms"]) < _LOSS_MS
    assert st.corner["name"]              # un nome c'è sempre, almeno "Curva 2"
    assert st.corner["index"] == 1        # l'ultima curva chiusa del giro
    eng.close()


def test_the_card_carries_the_measured_tenths(tmp_path):
    """I decimi sono quelli misurati, non un segnaposto.

    Si guarda la curva **0**, che è quella che `slow=True` rallenta: guardare la
    curva 1 (l'ultima chiusa a fine corsa) dava lo stesso identico blocco con
    `slow=False`, e con `lost_ms` inchiodato a 0.0 il test passava lo stesso.
    Quindi si campiona lo stato al tick in cui la curva 0 si chiude, e si chiede
    un valore sopra la soglia della voce — l'unica cosa che un segnaposto non
    può produrre.
    """
    eng, trace = _trace(tmp_path, _three_laps(slow=True))
    zero = [c for _, c in trace if c and c["index"] == 0]
    assert zero, "la curva 0 deve chiudersi almeno una volta"
    card = zero[-1]
    assert card["lost_ms"] > _LOSS_MS
    assert card["level"] in ("warn", "bad")
    eng.close()


def test_the_card_survives_the_finish_line(tmp_path):
    """Il riquadro resta finché non chiudi la curva dopo — traguardo compreso.

    È quello che promettono la spec e GUIDA.md, e il modo per verificarlo è
    guardare *ogni* tick di più giri: il difetto che questo test copre viveva
    tutto fra `pos` 0.000 e la prima curva, cioè in una finestra che nessun
    controllo a fine corsa avrebbe mai visto. `_rebuild_reference` (che il
    motore chiama a ogni giro salvato, per rincorrere il nuovo miglior giro)
    passava per `set_corners` + `reset`, e tutte e due azzeravano la carta.
    """
    eng, trace = _trace(tmp_path, _three_laps() + _lap_frames(3) + _lap_frames(4))
    firsts = [i for i, (_, c) in enumerate(trace) if c is not None]
    assert firsts, "prima o poi una curva si chiude"
    born = firsts[0]
    blank = [(i, trace[i][0]) for i in range(born, len(trace)) if trace[i][1] is None]
    assert blank == [], f"la carta si è spenta dopo essere comparsa: {blank[:5]}"

    # E c'è davvero passata, per il traguardo: almeno un giro intero comincia
    # (pos ~ 0) con la carta ancora addosso.
    starts = [c for pos, c in trace[born:] if pos < 0.02]
    assert starts, "il tracciato deve contenere almeno un passaggio dal traguardo"
    assert all(c is not None for c in starts)
    eng.close()


def test_a_new_car_on_the_same_track_blanks_the_card(tmp_path):
    """Cambio auto: stesse curve, altra sessione — il numero di prima non vale.

    `set_corners` da sola non basterebbe: due auto sulla stessa pista hanno lo
    stesso layout di zone, quindi qui a buttare la carta è il cambio di chiave.
    """
    frames = _three_laps()
    other = [replace(f, car_model="porsche_991ii_gt3_r") for f in _lap_frames(3)]
    eng, trace = _trace(tmp_path, frames + other[:1])
    assert trace[len(frames) - 1][1] is not None, "prima del cambio la carta c'era"
    assert trace[-1][1] is None
    assert eng.analyzer.last_corner is None
    eng.close()


def test_the_card_is_dropped_on_an_unrepresentative_lap(tmp_path):
    """Box, ricognizione, giro fuori ritmo: non nascosta, buttata — o
    riapparirebbe identica dopo il pit stop, col numero di dieci minuti fa.

    Che dopo tre giri buoni la carta ci fosse lo dice il test qui sopra: qui
    si guidano gli stessi tre giri e poi si entra ai box."""
    eng, st = _run(tmp_path, _three_laps() + _lap_frames(3, in_pit=True))
    assert st.quiet == "pit"
    assert st.corner is None
    assert eng.analyzer.last_corner is None
    eng.close()
