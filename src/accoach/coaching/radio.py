"""Fa suonare una frase del coach come una trasmissione radio box-pilota.

DSP in Python puro: l'app non dipende da numpy/scipy, e ``audioop`` non c'è più
da Python 3.13. Si legge un WAV PCM 16 bit, si porta a mono e si passa per la
catena di una «team radio» vera:

1. 90 ms di pre-roll e 40 ms dopo la voce (il tasto si preme prima di parlare);
2. passa-banda Butterworth del 4° ordine 420-3000 Hz (due biquad per lato);
3. compressore 4:1 con inviluppo (la radio schiaccia la dinamica);
4. saturazione tanh (il microfono del casco che satura);
5. codec: μ-law 8 bit su un segnale portato a 8 kHz e riportato su;
6. fruscio e un filo di motore, filtrati nella stessa banda;
7. lo scatto del tasto all'inizio e la coda di squelch alla fine.

I valori sono la via di mezzo fra la «team radio» e la «sporca, col motore»
che il pilota ha scelto all'ascolto (spike in ``.superpowers/sdd/radio``).

Gira sul thread della voce, fuori dal percorso caldo della telemetria; i WAV
pre-registrati vengono messi in cache dal chiamante, ma la frase SAPI5 passa
di qui ogni volta: per questo i cicli sono scritti stretti (variabili locali,
un solo passaggio dove si può) e il motore si legge da una tabella d'onda.
"""

from __future__ import annotations

import io
import math
import random
import wave
from array import array

# Banda della radio. Il passa-alto toglie il petto della voce (e la continua),
# il passa-basso dà il tetto «di latta» delle comunicazioni.
_BAND_LO_HZ = 420.0
_BAND_HI_HZ = 3000.0
# Q delle due sezioni di un Butterworth del 4° ordine (poli a 22,5° e 67,5°).
_BUTTER4_Q = (0.5412, 1.3066)

# Compressore: soglia sull'ingresso normalizzato a 1, rapporto, tempi.
_COMP_THR = 0.12
_COMP_RATIO = 4.0
_COMP_ATT_S = 0.003
_COMP_REL_S = 0.080

_DRIVE = 2.6             # saturazione tanh, poi riportata a 1 di picco

# Codec: la radio digitale campiona a 8 kHz e quantizza a 8 bit μ-law.
_CODEC_FS = 8000.0
_CODEC_LP_HZ = 3400.0    # anti-alias prima della decimazione (Nyquist 4 kHz)
_MU = 255.0

_HISS = 0.018            # fruscio di fondo (frazione del picco della voce)
_ENGINE = 0.025          # motore che entra nel microfono del casco
_ENGINE_F0 = 150.0       # fondamentale, oscillante di ±25 Hz a 0,7 Hz
_ENGINE_WOBBLE = 25.0
_ENGINE_WOBBLE_HZ = 0.7

_PRE_MS = 90
_POST_MS = 40
_CLICK_MS = 6            # scatto del tasto: rumore che decade
_CLICK_AMP = 0.8
_TAIL_MS = 150           # coda di squelch: rumore filtrato che decade
_TAIL_AMP = 0.35

_TARGET_PEAK = 0.85      # picco finale, frazione del fondo scala
_FULL = 32767.0
# Rumore uniforme con la stessa potenza di una gaussiana a varianza 1: costa una
# frazione di ``gauss`` e, dopo il passa-banda, all'orecchio è lo stesso.
_UNIFORM_TO_UNIT_RMS = math.sqrt(3.0)


def _lpf_coeffs(fs: float, fc: float, q: float):
    """Biquad passa-basso (RBJ cookbook), coefficienti divisi per a0."""
    w0 = 2.0 * math.pi * fc / fs
    cw, sw = math.cos(w0), math.sin(w0)
    alpha = sw / (2.0 * q)
    a0 = 1.0 + alpha
    b0 = (1.0 - cw) / 2.0
    return (b0 / a0, (1.0 - cw) / a0, b0 / a0, -2.0 * cw / a0, (1.0 - alpha) / a0)


def _hpf_coeffs(fs: float, fc: float, q: float):
    """Biquad passa-alto (RBJ cookbook), coefficienti divisi per a0."""
    w0 = 2.0 * math.pi * fc / fs
    cw, sw = math.cos(w0), math.sin(w0)
    alpha = sw / (2.0 * q)
    a0 = 1.0 + alpha
    b0 = (1.0 + cw) / 2.0
    return (b0 / a0, -(1.0 + cw) / a0, b0 / a0, -2.0 * cw / a0, (1.0 - alpha) / a0)


def _band_sections(fs: float):
    """Il passa-banda come cascata: due passa-alto e due passa-basso Butterworth.

    Se 3 kHz è troppo vicino a Nyquist (un WAV a 8 kHz) il passa-basso si salta:
    la banda la chiude già il file.
    """
    secs = [_hpf_coeffs(fs, _BAND_LO_HZ, q) for q in _BUTTER4_Q]
    if _BAND_HI_HZ < 0.45 * fs:
        secs += [_lpf_coeffs(fs, _BAND_HI_HZ, q) for q in _BUTTER4_Q]
    return secs


def _biquad(sig: list[float], coeffs) -> list[float]:
    """Una sezione biquad in forma diretta II trasposta (due stati invece di quattro)."""
    b0, b1, b2, a1, a2 = coeffs
    z1 = z2 = 0.0
    out = [0.0] * len(sig)
    for i, x in enumerate(sig):
        y = b0 * x + z1
        z1 = b1 * x - a1 * y + z2
        z2 = b2 * x - a2 * y
        out[i] = y
    return out


def _biquad_pair(sig: list[float], c1, c2) -> list[float]:
    """Due sezioni in cascata nello stesso ciclo.

    Matematicamente è ``_biquad(_biquad(sig, c1), c2)``; in Python puro buona
    parte del costo è il giro sulla lista, e fonderle risparmia ~15 % per coppia
    (misurato: 15,5 → 13,2 ms su 70 000 campioni).
    """
    b0, b1, b2, a1, a2 = c1
    d0, d1, d2, e1, e2 = c2
    z1 = z2 = w1 = w2 = 0.0
    out = [0.0] * len(sig)
    for i, x in enumerate(sig):
        y = b0 * x + z1
        z1 = b1 * x - a1 * y + z2
        z2 = b2 * x - a2 * y
        v = d0 * y + w1
        w1 = d1 * y - e1 * v + w2
        w2 = d2 * y - e2 * v
        out[i] = v
    return out


def _cascade(sig: list[float], sections) -> list[float]:
    secs = list(sections)
    for k in range(0, len(secs) - 1, 2):
        sig = _biquad_pair(sig, secs[k], secs[k + 1])
    if len(secs) % 2:
        sig = _biquad(sig, secs[-1])
    return sig


def _compress_and_drive(sig: list[float], fs: float) -> list[float]:
    """Compressore a inviluppo seguito dalla saturazione, in un solo passaggio.

    L'ingresso si normalizza a 1 di picco prima, così la soglia non dipende da
    quanto forte era registrata la frase.
    """
    peak = max(map(abs, sig), default=0.0) or 1.0
    inv_peak = 1.0 / peak
    att = math.exp(-1.0 / (_COMP_ATT_S * fs))
    rel = math.exp(-1.0 / (_COMP_REL_S * fs))
    thr, inv_ratio = _COMP_THR, 1.0 / _COMP_RATIO
    drive, inv_tanh = _DRIVE, 1.0 / math.tanh(_DRIVE)
    tanh = math.tanh
    env = 0.0
    out = [0.0] * len(sig)
    for i, x in enumerate(sig):
        x *= inv_peak
        v = x if x >= 0.0 else -x
        if v > env:
            env = att * env + (1.0 - att) * v
        else:
            env = rel * env + (1.0 - rel) * v
        if env > thr:
            x *= (thr + (env - thr) * inv_ratio) / env
        out[i] = tanh(drive * x) * inv_tanh
    return out


def _mulaw_table() -> list[float]:
    """I 255 livelli del μ-law 8 bit già espansi: si quantizza per indice."""
    return [math.copysign(((1.0 + _MU) ** (abs(k) / 127.0) - 1.0) / _MU, k)
            for k in range(-127, 128)]


def _codec(sig: list[float], fs: float) -> list[float]:
    """Porta a 8 kHz, quantizza μ-law 8 bit, riporta alla frequenza d'ingresso.

    Andata e ritorno per interpolazione lineare, col passa-basso prima a
    limitare l'aliasing: l'interpolazione lascia un filo d'immagine sopra i
    4 kHz che il codec vero non avrebbe, ma resta sotto il fruscio. Se il file
    è già a 8 kHz o meno si quantizza e basta.
    """
    n = len(sig)
    table = _mulaw_table()
    log_mu = math.log1p(_MU)
    log1p = math.log1p

    def q(y: float) -> float:
        if y > 1.0:
            y = 1.0
        elif y < -1.0:
            y = -1.0
        c = log1p(_MU * (y if y >= 0.0 else -y)) / log_mu
        k = int(c * 127.0 + 0.5)
        return table[127 + k] if y >= 0.0 else table[127 - k]

    if fs <= _CODEC_FS:
        return [q(y) for y in sig]

    sig = _cascade(sig, [_lpf_coeffs(fs, _CODEC_LP_HZ, qq) for qq in _BUTTER4_Q])
    step = fs / _CODEC_FS                # campioni d'ingresso per campione a 8 kHz
    m = int((n - 1) / step) + 1
    low = [0.0] * (m + 1)
    for j in range(m):
        p = j * step
        i = int(p)
        a = sig[i]
        b = sig[i + 1] if i + 1 < n else a
        low[j] = q(a + (b - a) * (p - i))
    low[m] = low[m - 1]

    back = _CODEC_FS / fs
    out = [0.0] * n
    for i in range(n):
        p = i * back
        j = int(p)
        a = low[j]
        out[i] = a + (low[j + 1] - a) * (p - j)
    return out


def _engine_wavetable(size: int = 2048) -> list[float]:
    """Un giro di motore: armoniche dalla 2 alla 11 della fondamentale, in 1/k.

    Una tabella invece di dieci seni a campione: è la differenza fra qualche
    millisecondo e un decimo di secondo su una frase di tre secondi.
    """
    return [sum(math.sin(k * 2.0 * math.pi * i / size) / k for k in range(2, 12))
            for i in range(size)]


def _noise_bed(n: int, fs: float, rnd: random.Random) -> list[float]:
    """Fruscio + motore, ancora da filtrare (si filtrano insieme: il filtro è lineare)."""
    table = _engine_wavetable()
    size = len(table)
    mask = size - 1
    hiss = _HISS * _UNIFORM_TO_UNIT_RMS
    eng = _ENGINE
    rand = rnd.random
    sin = math.sin
    w = 2.0 * math.pi * _ENGINE_WOBBLE_HZ / fs
    f0, wob, inv_fs = _ENGINE_F0, _ENGINE_WOBBLE, 1.0 / fs
    phase = 0.0                                  # in giri, non in radianti
    out = [0.0] * n
    for i in range(n):
        phase += (f0 + wob * sin(w * i)) * inv_fs
        out[i] = hiss * (2.0 * rand() - 1.0) + eng * table[int(phase * size) & mask]
    return out


def _read_mono(wav_bytes: bytes):
    """(campioni mono in -1..1, frequenza) oppure (None, 0) se non supportato."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        nch = w.getnchannels()
        width = w.getsampwidth()
        fs = w.getframerate()
        raw = w.readframes(w.getnframes())
    if width != 2:                                   # solo PCM 16 bit
        return None, 0
    pcm = array("h")
    pcm.frombytes(raw)
    if nch > 1:
        mono = [sum(pcm[i:i + nch]) / nch / _FULL for i in range(0, len(pcm), nch)]
    else:
        mono = [s / _FULL for s in pcm]
    return mono, fs


def radioize_wav(wav_bytes: bytes, *, seed: int = 12345) -> bytes:
    """Restituisce ``wav_bytes`` come trasmissione radio (WAV mono 16 bit).

    Gli ingressi non supportati (non 16 bit, illeggibili) tornano invariati,
    così il chiamante può ancora suonare l'originale. Lo stesso ``seed`` dà
    sempre gli stessi byte: il rumore è deterministico.
    """
    try:
        sig, fs = _read_mono(wav_bytes)
    except (wave.Error, EOFError, ValueError):
        return wav_bytes
    if sig is None or not sig:
        return wav_bytes

    rnd = random.Random(seed)
    band = _band_sections(fs)

    sig = [0.0] * int(fs * _PRE_MS / 1000) + sig + [0.0] * int(fs * _POST_MS / 1000)
    sig = _cascade(sig, band)
    sig = _compress_and_drive(sig, fs)
    sig = _codec(sig, fs)

    bed = _cascade(_noise_bed(len(sig), fs, rnd), band)
    sig = [a + b for a, b in zip(sig, bed)]

    n_click = int(fs * _CLICK_MS / 1000)
    k = _CLICK_AMP * _UNIFORM_TO_UNIT_RMS
    click = [k * (2.0 * rnd.random() - 1.0) * (1.0 - i / n_click) for i in range(n_click)]

    n_tail = int(fs * _TAIL_MS / 1000)
    tail = _cascade([_UNIFORM_TO_UNIT_RMS * (2.0 * rnd.random() - 1.0) for _ in range(n_tail)],
                    band)
    tail = [x * _TAIL_AMP * (1.0 - i / n_tail) ** 1.5 for i, x in enumerate(tail)]

    full = click + sig + tail

    # Normalizza: il campione più forte finisce al picco voluto, mai al fondo
    # scala. Per costruzione nessun campione supera 0,85: niente clamp a campione.
    peak = max(map(abs, full), default=1.0) or 1.0
    g = _TARGET_PEAK / peak * _FULL
    pcm = array("h", [int(x * g) for x in full])

    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fs)
        w.writeframes(pcm.tobytes())
    return out.getvalue()
