"""Spike: l'occhio anticipa la curva? — misura, non feature.

Sta in ``tools/`` e **non entra nel bundle** (`HONE.spec` non lo include, e
`requirements.txt` non guadagna una riga). Serve a rispondere a una domanda
prima di spendere sei settimane, non a spedire qualcosa.

La domanda
----------
Quando il pilota gira, lo sguardo si sposta **prima** dello sterzo? E di quanto?
Se sì, quel numero distingue un giro veloce da uno lento dello stesso pilota?

Perché questa domanda e non "dove guarda"
-----------------------------------------
Una webcam consumer sbaglia la direzione dello sguardo di 4-8°, che su un monitor
a 60 cm sono 4-8 cm: qualunque frase su *dove* guardi sullo schermo sarebbe una
diagnosi su un segnale non validato, e in questo progetto ne abbiamo già pagate
tre. Uno **scarto di tempo** fra due segnali è un'altra cosa: è change detection
su un segnale relativo a sé stesso. Non serve sapere dove guardi, serve sapere
*quando* ti sei mosso. Non richiede calibrazione, e un errore di 5° costante
sparisce nella differenza.

Il limite che resta, e va detto ogni volta
------------------------------------------
La cattura da webcam ha una latenza sconosciuta e non costante (40-120 ms su USB
UVC). Quindi il numero **assoluto** ("l'occhio anticipa di 380 ms") porta dentro
quella latenza come bias. Il **confronto** fra due giri della stessa sessione no:
lì il bias si semplifica. Questo spike serve a confrontare, e lo ripete nel
report per non farsi dimenticare.

Uso
---
La cattura ha bisogno di una webcam e di dipendenze di computer vision che il
prodotto non ha. Si installano **a parte**, in un venv dedicato, così il bundle
resta quello di prima::

    py -3.12 -m venv .venv-gaze
    .venv-gaze\\Scripts\\activate
    pip install opencv-python mediapipe

    python tools/gaze_spike.py record --seconds 300      # gioco avviato, in pista
    python tools/gaze_spike.py analyze <file.gaze.json>

L'analisi non importa nulla di esterno: gira con il Python del progetto (ed è
quella coperta dai test). Senza mediapipe la cattura ripiega su OpenCV puro, che
vede solo la posizione della testa: meno preciso, ma per uno scarto di tempo può
bastare — il report dice sempre con che backend è stato registrato.

    python tools/gaze_spike.py selftest    # verifica la matematica senza webcam
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# ANALISI — Python puro, nessuna dipendenza. È la parte che i test coprono.
# ---------------------------------------------------------------------------

# Sopra questo sterzo (rad) siamo in curva e non in correzione di rettilineo.
TURN_IN_STEER = 0.10
# Finestra in cui cercare lo spostamento dello sguardo attorno a un ingresso curva.
LOOK_BACK_S = 2.0
# Frazione del picco locale che conta come "lo sguardo si è mosso".
ONSET_FRAC = 0.25
# Quanto lontano cercare lo sfasamento fra i due segnali.
MAX_LAG_S = 1.5


def resample(times: list[float], values: list[float],
             grid: list[float]) -> list[float]:
    """``values`` (campionati a ``times``) interpolati linearmente su ``grid``.

    I due flussi arrivano a frequenze diverse — la telemetria a 60 Hz, la webcam
    a 30 e con jitter — e vanno messi sulla stessa griglia prima di confrontarli.
    Fuori dall'intervallo tiene il valore agli estremi: non inventa movimento
    dove non c'è dato.
    """
    if not times or not values:
        return [0.0] * len(grid)
    out, j, n = [], 0, len(times)
    for t in grid:
        while j + 1 < n and times[j + 1] < t:
            j += 1
        if t <= times[0]:
            out.append(values[0])
        elif t >= times[-1]:
            out.append(values[-1])
        else:
            k = min(j + 1, n - 1)
            span = times[k] - times[j]
            f = (t - times[j]) / span if span > 0 else 0.0
            out.append(values[j] + (values[k] - values[j]) * f)
    return out


def _pearson(a: list[float], b: list[float]) -> float:
    n = len(a)
    if n < 3:
        return 0.0
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return 0.0
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return cov / math.sqrt(va * vb)


def _zscore(xs: list[float]) -> list[float]:
    """Serie a media zero e deviazione uno. Fatto **una volta** per serie.

    La correlazione a ogni sfasamento diventa cosi' un solo prodotto scalare
    invece di un Pearson completo (quattro passate sui dati): la ricerca esplora
    ~180 sfasamenti per sei serie, e la differenza fra un secondo e un minuto e'
    tutta qui.
    """
    n = len(xs)
    if n == 0:
        return []
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs)
    if var <= 0:
        return [0.0] * n
    sd = math.sqrt(var / n)
    return [(x - m) / sd for x in xs]


def _shift_corr(za: list[float], zb: list[float], k: int) -> float:
    """Correlazione fra due serie **gia' normalizzate**, sfasate di ``k``.

    ``k`` positivo = ``za`` accade PRIMA di ``zb`` (za anticipa)."""
    if k >= 0:
        x, y = za[:len(za) - k], zb[k:]
    else:
        x, y = za[-k:], zb[:len(zb) + k]
    n = min(len(x), len(y))
    if n < 3:
        return 0.0
    return sum(p * q for p, q in zip(x, y)) / n


def lead_lag(a: list[float], b: list[float], dt: float,
             max_lag_s: float = MAX_LAG_S) -> dict:
    """Di quanto ``a`` anticipa ``b``, per correlazione incrociata.

    Restituisce il ritardo che massimizza la correlazione (positivo = ``a``
    anticipa), il valore di correlazione, e un **pavimento di rumore**: la
    stessa ricerca ripetuta su versioni ruotate ciclicamente di ``b``, dove per
    costruzione non c'è relazione. Se il picco vero non supera il pavimento, la
    risposta onesta è "non lo so", non un numero.
    """
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    kmax = int(max_lag_s / dt) if dt > 0 else 0
    if n < 4 * (kmax + 1) or kmax < 1:
        return {"lag_s": None, "r": 0.0, "floor_r": 0.0, "significant": False}

    a, b = _zscore(a), _zscore(b)
    best_k, best_r = 0, -2.0
    for k in range(-kmax, kmax + 1):
        r = _shift_corr(a, b, k)
        if r > best_r:
            best_k, best_r = k, r

    # Pavimento: rotazioni cicliche abbastanza grandi da distruggere la relazione
    # ma che conservano lo spettro dei due segnali (un rumore bianco darebbe un
    # pavimento troppo generoso). Deterministico: niente casualità da spiegare.
    floor = 0.0
    for frac in (0.2, 0.35, 0.5, 0.65, 0.8):
        off = int(n * frac)
        rot = b[off:] + b[:off]
        for k in range(-kmax, kmax + 1):
            floor = max(floor, _shift_corr(a, rot, k))

    return {
        "lag_s": best_k * dt,
        "r": best_r,
        "floor_r": floor,
        "significant": best_r > floor,
    }


def turn_ins(times: list[float], steer: list[float],
             threshold: float = TURN_IN_STEER) -> list[tuple[float, int]]:
    """Istanti di ingresso curva: quando |sterzo| supera la soglia salendo.

    Ogni ingresso si riarma solo dopo che lo sterzo è tornato sotto metà soglia,
    così una correzione dentro la curva non conta come una seconda curva.
    """
    out: list[tuple[float, int]] = []
    armed = True
    for t, s in zip(times, steer):
        if armed and abs(s) >= threshold:
            out.append((t, 1 if s > 0 else -1))
            armed = False
        elif not armed and abs(s) < threshold * 0.5:
            armed = True
    return out


def gaze_onset(times: list[float], gaze: list[float], turn_t: float, side: int,
               look_back_s: float = LOOK_BACK_S,
               frac: float = ONSET_FRAC) -> float | None:
    """Quando lo sguardo ha cominciato a muoversi verso il lato della curva.

    Cerca all'indietro dall'ingresso curva il picco dello sguardo *dalla parte
    giusta*, poi torna ancora indietro fino a dove valeva una frazione di quel
    picco: quello è l'inizio del movimento. ``None`` se in quella finestra lo
    sguardo non si è mosso da quella parte — che è una risposta, non un errore.
    """
    lo = turn_t - look_back_s
    idx = [i for i, t in enumerate(times) if lo <= t <= turn_t + look_back_s * 0.5]
    if len(idx) < 3:
        return None
    base = gaze[idx[0]]
    # Segno atteso: lo sguardo va dalla parte in cui si gira. Il segno del canale
    # dipende dal backend, quindi l'orientamento si stabilisce sui dati (vedi
    # `orient_gaze`) e qui si assume già concorde con lo sterzo.
    peak_i, peak_v = None, 0.0
    for i in idx:
        d = (gaze[i] - base) * side
        if d > peak_v:
            peak_i, peak_v = i, d
    if peak_i is None or peak_v <= 0:
        return None
    target = peak_v * frac
    onset = times[peak_i]
    for i in range(peak_i, idx[0] - 1, -1):
        if (gaze[i] - base) * side < target:
            onset = times[i]
            break
    return onset


def orient_to_steer(channel: list[float], steer: list[float]) -> int:
    """+1 se ``channel`` si muove nello stesso verso dello sterzo, -1 se
    all'opposto, 0 se non si capisce.

    Serve due volte. Per lo **sguardo**: il verso dipende dal backend e da come è
    montata la webcam (specchiata o no), ed è l'unica cosa che va stabilita dai
    dati prima di parlare di anticipo — se non si capisce, il resto non ha senso
    e il report lo dice. Per lo **yaw**: il gioco lo segna all'opposto dello
    sterzo (misurato su tre classi, `balance._YAW_SIGN = -1.0`), quindi senza
    orientarlo la ricerca del massimo di correlazione non troverebbe mai niente.
    """
    r = _pearson(channel, steer)
    if abs(r) < 0.1:
        return 0
    return 1 if r > 0 else -1


def analyze(rec: dict, dt: float = 1 / 60.0) -> dict:
    """Il conto completo su una registrazione. Nessun effetto collaterale."""
    g_t = [row[0] for row in rec["gaze"]]
    tele = rec["tele"]
    t_t = [row[0] for row in tele]
    if len(g_t) < 10 or len(t_t) < 10:
        return {"error": "troppi pochi campioni"}

    t0, t1 = max(g_t[0], t_t[0]), min(g_t[-1], t_t[-1])
    if t1 - t0 < 5.0:
        return {"error": "meno di 5 s di sovrapposizione fra webcam e telemetria"}
    steps = int((t1 - t0) / dt)
    grid = [t0 + i * dt for i in range(steps)]

    # Canale sguardo: occhio-nella-testa + testa, se il backend li distingue.
    gaze_raw = [row[1] for row in rec["gaze"]]
    steer_raw = [row[3] for row in tele]
    gaze = resample(g_t, gaze_raw, grid)
    steer = resample(t_t, steer_raw, grid)
    yaw = resample(t_t, [row[4] for row in tele], grid)
    speed = resample(t_t, [row[2] for row in tele], grid)

    sign = orient_to_steer(gaze, steer)
    if sign == 0:
        return {"error": "il canale sguardo non si correla con lo sterzo in nessun "
                         "verso: tracking troppo rumoroso o pilota fermo",
                "samples": len(grid)}
    gaze = [g * sign for g in gaze]

    # Solo dove si sta guidando: da fermi o ai box lo sguardo va ovunque e
    # correlerebbe con niente.
    moving = [i for i, v in enumerate(speed) if v > 40.0]
    if len(moving) > 100:
        lo, hi = moving[0], moving[-1] + 1
        gaze_m, steer_m, yaw_m = gaze[lo:hi], steer[lo:hi], yaw[lo:hi]
        grid_m = grid[lo:hi]
    else:
        gaze_m, steer_m, yaw_m, grid_m = gaze, steer, yaw, grid

    # Lo yaw è segnato all'opposto dello sterzo: allinealo o il confronto con
    # "la direzione dell'auto" cercherebbe un massimo dove c'è un minimo.
    yaw_sign = orient_to_steer(yaw_m, steer_m) or 1
    yaw_m = [y * yaw_sign for y in yaw_m]

    vs_steer = lead_lag(gaze_m, steer_m, dt)
    vs_yaw = lead_lag(gaze_m, yaw_m, dt)

    leads = []
    for turn_t, side in turn_ins(grid_m, steer_m):
        onset = gaze_onset(grid_m, gaze_m, turn_t, side)
        if onset is not None:
            leads.append(round(turn_t - onset, 3))

    # Quanto spesso il tracker ha perso il volto: e' il criterio con cui si
    # butta via una cattura, quindi deve stare nel report e non solo a schermo
    # durante la registrazione.
    lost = int(rec.get("meta", {}).get("frames_lost", 0) or 0)
    seen = len(rec["gaze"])
    return {
        "backend": rec.get("meta", {}).get("backend", "?"),
        "frames_lost": lost,
        "lost_frac": round(lost / (lost + seen), 3) if (lost + seen) else 0.0,
        "samples": len(grid_m),
        "seconds": round(grid_m[-1] - grid_m[0], 1) if grid_m else 0.0,
        "gaze_sign": sign,
        "vs_steer": vs_steer,
        "vs_yaw": vs_yaw,
        "corners": len(leads),
        "lead_median_s": _median(leads),
        "lead_per_corner_s": leads,
    }


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def report(res: dict) -> str:
    """Il verdetto in parole, con i limiti attaccati al numero."""
    if "error" in res:
        return f"Non rispondibile: {res['error']}"
    out = [
        f"Backend: {res['backend']} · {res['seconds']} s guidati "
        f"({res['samples']} campioni)",
        f"Volto perso: {res['frames_lost']} fotogrammi "
        f"({res['lost_frac']*100:.0f}%)"
        + ("  <-- sopra il 20%: cattura da rifare" if res["lost_frac"] > 0.2 else ""),
        "",
    ]
    st, yw = res["vs_steer"], res["vs_yaw"]
    for name, d in (("sterzo", st), ("direzione dell'auto (yaw)", yw)):
        if d["lag_s"] is None or not d["significant"]:
            out.append(f"  vs {name}: nessuno sfasamento distinguibile dal rumore "
                       f"(r={d['r']:.2f}, pavimento {d['floor_r']:.2f})")
        else:
            verso = "ANTICIPA" if d["lag_s"] > 0 else "SEGUE"
            out.append(f"  vs {name}: lo sguardo {verso} di "
                       f"{abs(d['lag_s'])*1000:.0f} ms "
                       f"(r={d['r']:.2f}, pavimento {d['floor_r']:.2f})")
    out.append("")
    if res["corners"]:
        out.append(f"  Per curva ({res['corners']} ingressi): anticipo mediano "
                   f"{res['lead_median_s']*1000:.0f} ms")
    else:
        out.append("  Per curva: nessun ingresso con uno spostamento dello sguardo "
                   "riconoscibile")
    out += [
        "",
        "  ⚠ Il numero assoluto contiene la latenza di cattura della webcam",
        "    (40-120 ms, sconosciuta): confronta giri fra loro, non questo",
        "    numero con lo zero.",
    ]
    return "\n".join(out)


# ---------------------------------------------------------------------------
# CATTURA — importa cv2/mediapipe solo qui, e solo quando serve.
# ---------------------------------------------------------------------------

def _make_tracker():
    """Il miglior backend disponibile. Restituisce (nome, funzione(frame)->h|None)."""
    try:                                        # preferito: iride + testa
        import mediapipe as mp                  # noqa: PLC0415
        mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1, refine_landmarks=True,
            min_detection_confidence=0.5, min_tracking_confidence=0.5)

        def track(frame):
            res = mesh.process(frame[:, :, ::-1])
            if not res.multi_face_landmarks:
                return None
            lm = res.multi_face_landmarks[0].landmark
            # Iride nell'orbita: quanto l'iride è spostata fra i due angoli
            # dell'occhio. Adimensionale, quindi indipendente dalla distanza.
            def eye(iris, c1, c2):
                w = lm[c2].x - lm[c1].x
                return ((lm[iris].x - (lm[c1].x + lm[c2].x) / 2) / w) if w else 0.0
            h_eye = (eye(468, 33, 133) + eye(473, 362, 263)) / 2
            # Testa: naso rispetto ai due bordi del viso (proxy dello yaw).
            span = lm[454].x - lm[234].x
            h_head = ((lm[1].x - (lm[234].x + lm[454].x) / 2) / span) if span else 0.0
            # Somma: dove guarda in tutto, che è ciò che anticipa la curva.
            return h_eye + h_head
        return "mediapipe(iris+head)", track
    except Exception:
        pass
    try:                                        # ripiego: solo posizione testa
        import cv2                              # noqa: PLC0415
        casc = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

        def track(frame):
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = casc.detectMultiScale(gray, 1.2, 5)
            if len(faces) == 0:
                return None
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            return (x + w / 2) / frame.shape[1] - 0.5
        return "opencv(head-only)", track
    except Exception as exc:
        raise SystemExit(
            "Serve almeno opencv-python per la cattura.\n"
            "  py -3.12 -m venv .venv-gaze && .venv-gaze\\Scripts\\activate\n"
            "  pip install opencv-python mediapipe\n"
            f"({exc})")


def record(seconds: float, out_dir: Path) -> Path:
    """Registra sguardo + telemetria su un orologio comune.

    Legge la shared memory **direttamente**, non tramite ``TelemetryFeed``: quel
    feed registra anche i giri su disco, e un secondo scrittore sui giri è
    esattamente l'invariante che il progetto ha stabilito di non rompere. Qui si
    legge e basta.
    """
    import cv2                                  # noqa: PLC0415
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from accoach.telemetry.reader import SharedMemoryReader   # noqa: PLC0415

    name, track = _make_tracker()
    cam = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cam.isOpened():
        raise SystemExit("webcam non apribile (in uso da un'altra app? "
                         "permesso fotocamera di Windows negato?)")
    reader = SharedMemoryReader()
    gaze: list[list[float]] = []
    tele: list[list[float]] = []
    lost = 0
    t0 = time.perf_counter()
    print(f"Cattura con {name}. La spia della webcam è accesa: è l'unico modo "
          f"onesto di dirtelo.\nCtrl+C per fermare.\n")
    try:
        while time.perf_counter() - t0 < seconds:
            ok, frame = cam.read()
            # Timbrato al fotogramma, non dopo l'elaborazione: la latenza USB
            # resta sconosciuta, ma almeno non ci aggiungiamo la nostra.
            t = time.perf_counter() - t0
            if ok:
                h = track(frame)
                if h is None:
                    lost += 1
                else:
                    gaze.append([round(t, 4), round(h, 5)])
            s = reader.read()
            if s.connected:
                tele.append([round(t, 4), round(s.lap_position, 5),
                             round(s.speed_kmh, 2), round(s.steer_angle, 4),
                             round(s.yaw_rate, 4), round(s.brake, 3)])
    except KeyboardInterrupt:
        pass
    finally:
        cam.release()
        reader.close()

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"gaze_{int(time.time())}.gaze.json"
    path.write_text(json.dumps({
        "meta": {"backend": name, "seconds": round(time.perf_counter() - t0, 1),
                 "frames_lost": lost,
                 "note": "nessun fotogramma è stato salvato: solo numeri"},
        "gaze": gaze, "tele": tele,
    }), encoding="utf-8")
    print(f"\n{len(gaze)} campioni sguardo, {len(tele)} telemetria "
          f"({lost} fotogrammi senza volto) -> {path}")
    return path


# ---------------------------------------------------------------------------
# SELFTEST — verifica la matematica senza webcam e senza gioco.
# ---------------------------------------------------------------------------

def synth(lead_s: float = 0.4, noise: float = 0.15, seconds: float = 90.0) -> dict:
    """Una sessione finta in cui lo sguardo anticipa lo sterzo di ``lead_s``.

    Rumore deterministico (niente RNG): il test deve dare lo stesso numero oggi
    e fra sei mesi, o non è un test.
    """
    dt_t, dt_g = 1 / 60.0, 1 / 30.0
    # Curve a distanza IRREGOLARE, di proposito: con curve equispaziate il
    # segnale è periodico, e una rotazione ciclica (il pavimento di rumore) resta
    # correlata con l'originale — il pavimento si gonfierebbe fino a coprire il
    # picco vero. Un giro vero non è periodico; il finto non deve esserlo.
    spacing = [4.5, 7.0, 3.5, 9.0, 5.0, 6.5, 3.0, 8.0]
    edges, acc = [], 0.0
    while acc < seconds + 10:
        acc += spacing[len(edges) % len(spacing)]
        edges.append(acc)

    def steer_at(t):
        lo = 0.0
        for i, hi in enumerate(edges):
            if t < hi:
                phase = (t - lo) / (hi - lo)
                return (0.35 if i % 2 == 0 else -0.35) * math.sin(math.pi * phase) ** 2
            lo = hi
        return 0.0
    def wobble(t, k):                   # pseudo-rumore riproducibile
        return noise * math.sin(t * k + math.cos(t * k * 0.7)) * 0.5
    tele = [[round(i * dt_t, 4), (i * dt_t / 60) % 1.0, 150.0,
             round(steer_at(i * dt_t) + wobble(i * dt_t, 11.0), 4),
             round(-steer_at(i * dt_t) * 2.0, 4), 0.0]
            for i in range(int(seconds / dt_t))]
    gaze = [[round(i * dt_g, 4),
             round(steer_at(i * dt_g + lead_s) + wobble(i * dt_g, 7.0), 5)]
            for i in range(int(seconds / dt_g))]
    return {"meta": {"backend": "synth"}, "gaze": gaze, "tele": tele}


def selftest() -> int:
    print("Selftest: sessione sintetica con anticipo noto di 400 ms.\n")
    res = analyze(synth(lead_s=0.4))
    print(report(res))
    lag = res["vs_steer"]["lag_s"]
    ok = lag is not None and abs(lag - 0.4) < 0.06 and res["vs_steer"]["significant"]
    print(f"\n{'OK' if ok else 'FALLITO'}: sfasamento recuperato {lag}")

    print("\nControllo negativo: sguardo che non guarda la strada.")
    flat = synth(lead_s=0.4)
    flat["gaze"] = [[t, math.sin(t * 3.1) * 0.02] for t, _ in flat["gaze"]]
    neg = analyze(flat)
    quiet = "error" in neg or not neg["vs_steer"]["significant"]
    print(report(neg))
    print(f"\n{'OK' if quiet else 'FALLITO'}: su segnale scorrelato deve tacere")
    return 0 if (ok and quiet) else 1


def _utf8() -> None:
    """La console di Windows è cp1252 e strozza gli accenti e i simboli."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")    # type: ignore[union-attr]
        except Exception:
            pass


def main(argv: list[str]) -> int:
    _utf8()
    cmd = argv[0] if argv else "selftest"
    if cmd == "record":
        secs = float(argv[argv.index("--seconds") + 1]) if "--seconds" in argv else 300.0
        record(secs, Path.home() / "Documents" / "ACCoach" / "gaze_runs")
        return 0
    if cmd == "analyze":
        if len(argv) < 2:
            print("uso: gaze_spike.py analyze <file.gaze.json>")
            return 2
        print(report(analyze(json.loads(Path(argv[1]).read_text(encoding="utf-8")))))
        return 0
    if cmd == "selftest":
        return selftest()
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
