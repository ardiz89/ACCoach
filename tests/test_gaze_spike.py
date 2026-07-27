"""Spike sguardo: la matematica dell'anticipo, verificata senza webcam.

Lo spike vive in ``tools/`` e non entra nel bundle, ma la parte che *risponde
alla domanda* è Python puro e va trattata come codice vero: se lo sfasamento lo
misuriamo male, la risposta ("l'occhio anticipa") è sbagliata in un modo che
nessuno noterebbe guardando un grafico.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import gaze_spike as gs


def test_resample_interpolates_and_holds_at_the_edges():
    times, values = [0.0, 1.0, 2.0], [0.0, 10.0, 20.0]
    out = gs.resample(times, values, [-1.0, 0.5, 1.5, 3.0])
    assert out[0] == 0.0            # prima del primo campione: tiene, non estrapola
    assert abs(out[1] - 5.0) < 1e-9
    assert abs(out[2] - 15.0) < 1e-9
    assert out[3] == 20.0           # dopo l'ultimo: tiene


def test_resample_without_data_does_not_invent_movement():
    assert gs.resample([], [], [0.0, 1.0]) == [0.0, 0.0]


def _wave(n, dt, phase_s=0.0):
    """Un segnale APERIODICO campionato a ``dt``, sfasato di ``phase_s``.

    Aperiodico di proposito: su un segnale periodico "anticipa di 0.4 s" e
    "ritarda di un periodo meno 0.4 s" sono la stessa cosa, e la domanda non ha
    una risposta sola — vedi
    ``test_a_periodic_signal_cannot_prove_an_anticipation``. Un giro vero non è
    periodico: le curve non sono equispaziate.
    """
    def f(t):
        return (math.sin(2 * math.pi * t / 3.0)
                + 0.7 * math.sin(2 * math.pi * t / 1.7 + 0.4)
                + 0.5 * math.sin(2 * math.pi * t / 0.9 + 1.1))
    return [f(i * dt + phase_s) for i in range(n)]


def test_lead_lag_recovers_a_known_shift_with_the_right_sign():
    dt = 1 / 60.0
    n = 60 * 60
    # `a` è `b` anticipato di 0.4 s: a(t) = b(t + 0.4)
    b = _wave(n, dt)
    a = _wave(n, dt, phase_s=0.4)
    res = gs.lead_lag(a, b, dt)
    assert res["significant"]
    assert abs(res["lag_s"] - 0.4) < 0.02        # positivo = `a` anticipa


def test_lead_lag_reports_a_lag_when_the_signal_follows():
    dt = 1 / 60.0
    n = 60 * 60
    b = _wave(n, dt)
    late = _wave(n, dt, phase_s=-0.3)
    assert gs.lead_lag(late, b, dt)["lag_s"] < 0


def test_lead_lag_stays_quiet_on_unrelated_signals():
    dt = 1 / 60.0
    n = 60 * 60
    a = [math.sin(i * dt * 5.0) for i in range(n)]
    b = [math.sin(i * dt * 0.37 + 1.1) for i in range(n)]
    res = gs.lead_lag(a, b, dt)
    # Può esistere un massimo, ma non deve superare il pavimento di rumore.
    assert not res["significant"] or res["r"] > res["floor_r"]


def test_a_periodic_signal_cannot_prove_an_anticipation():
    """Su un segnale periodico il ritardo è ambiguo modulo il periodo, quindi il
    pavimento di rumore deve rifiutarsi di dichiararlo significativo — anche se
    un massimo di correlazione bello alto esiste eccome."""
    dt, n, period = 1 / 60.0, 60 * 60, 3.0
    b = [math.sin(2 * math.pi * (i * dt) / period) for i in range(n)]
    a = [math.sin(2 * math.pi * (i * dt + 0.4) / period) for i in range(n)]
    res = gs.lead_lag(a, b, dt)
    assert res["r"] > 0.9              # il massimo c'è...
    assert not res["significant"]      # ...ma non dice niente che il rumore non dica


def test_lead_lag_refuses_a_series_too_short_to_mean_anything():
    res = gs.lead_lag([0.1, 0.2, 0.3], [0.1, 0.2, 0.3], 1 / 60.0)
    assert res["lag_s"] is None and not res["significant"]


def test_turn_ins_counts_each_corner_once():
    dt, times, steer = 0.02, [], []
    for i in range(1000):
        t = i * dt
        times.append(t)
        # due curve, con una correzione dentro la prima che non deve contare
        if 2.0 <= t < 5.0:
            steer.append(0.30 if not (3.0 <= t < 3.2) else 0.18)
        elif 10.0 <= t < 13.0:
            steer.append(-0.30)
        else:
            steer.append(0.0)
    found = gs.turn_ins(times, steer)
    assert len(found) == 2
    assert found[0][1] == 1 and found[1][1] == -1      # destra poi sinistra


def test_gaze_onset_finds_the_start_of_the_movement_before_turn_in():
    dt = 0.02
    times = [i * dt for i in range(500)]
    turn_t = 6.0
    # Lo sguardo parte a 5.0 s e sale fino all'ingresso curva a 6.0 s.
    gaze = [0.0 if t < 5.0 else min(1.0, (t - 5.0)) for t in times]
    onset = gs.gaze_onset(times, gaze, turn_t, side=1)
    assert onset is not None
    assert 4.9 < onset < 5.5                    # riconosce l'inizio, non il picco
    assert onset < turn_t                       # cioè: anticipa


def test_gaze_onset_is_none_when_the_eye_never_moves_that_way():
    dt = 0.02
    times = [i * dt for i in range(500)]
    gaze = [0.0] * len(times)
    assert gs.gaze_onset(times, gaze, 6.0, side=1) is None


def test_orient_to_steer_reads_the_sign_from_the_data():
    steer = [math.sin(i / 20.0) for i in range(400)]
    assert gs.orient_to_steer([s * 2.0 for s in steer], steer) == 1
    assert gs.orient_to_steer([-s for s in steer], steer) == -1
    assert gs.orient_to_steer([0.001] * 400, steer) == 0


def test_analyze_recovers_the_planted_lead_on_a_whole_session():
    res = gs.analyze(gs.synth(lead_s=0.4))
    assert "error" not in res
    assert res["vs_steer"]["significant"]
    assert abs(res["vs_steer"]["lag_s"] - 0.4) < 0.06
    # Lo yaw è segnato all'opposto dello sterzo (come nel gioco): se non venisse
    # riorientato, questa riga direbbe "nessuno sfasamento".
    assert res["vs_yaw"]["significant"]
    assert abs(res["vs_yaw"]["lag_s"] - 0.4) < 0.06
    assert res["corners"] > 5


def test_analyze_recovers_a_different_planted_lead():
    # Un solo caso non dimostra che stiamo misurando: dimostra che indovina 0.4.
    res = gs.analyze(gs.synth(lead_s=0.15))
    assert abs(res["vs_steer"]["lag_s"] - 0.15) < 0.06


def test_analyze_says_it_does_not_know_when_the_eye_is_elsewhere():
    rec = gs.synth(lead_s=0.4)
    rec["gaze"] = [[t, math.sin(t * 3.1) * 0.02] for t, _ in rec["gaze"]]
    res = gs.analyze(rec)
    assert "error" in res or not res["vs_steer"]["significant"]


def test_analyze_refuses_a_recording_without_overlap():
    rec = gs.synth()
    rec["gaze"] = [[t + 10_000.0, h] for t, h in rec["gaze"]]
    assert "error" in gs.analyze(rec)


def test_the_report_always_carries_the_latency_caveat():
    # Il numero assoluto contiene la latenza di cattura della webcam. Se qualcuno
    # ripulisce il report da quella riga, il numero comincia a sembrare assoluto.
    text = gs.report(gs.analyze(gs.synth(lead_s=0.4)))
    assert "latenza" in text.lower()
    assert "ANTICIPA" in text


def test_report_flags_a_capture_that_lost_the_face_too_often():
    # È il criterio con cui una cattura si butta: deve stare nel report, non solo
    # a schermo durante la registrazione (quando nessuno lo sta leggendo).
    rec = gs.synth(lead_s=0.4)
    rec["meta"]["frames_lost"] = 900        # 25% dei fotogrammi
    text = gs.report(gs.analyze(rec))
    assert "25%" in text and "da rifare" in text
    clean = gs.report(gs.analyze(gs.synth(lead_s=0.4)))
    assert "da rifare" not in clean
