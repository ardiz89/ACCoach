"""radio: effetto «team radio» in Python puro (niente numpy/audioop nell'app).

La banda si misura con Goertzel scritto qui, non solo con numpy: la CI installa
le dipendenze dell'app, e un test che in CI si salta non protegge niente.
"""
import io
import math
import random
import wave
from array import array

import pytest

from accoach.coaching.radio import radioize_wav

_FS = 22050


def _wav(samples, fs=_FS, nch=1) -> bytes:
    pcm = array("h", [int(s) for s in samples])
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(nch)
        w.setsampwidth(2)
        w.setframerate(fs)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def _read(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        pcm = array("h")
        pcm.frombytes(w.readframes(w.getnframes()))
        return list(pcm), w.getframerate(), w.getnchannels(), w.getsampwidth()


def _tone(freq, n, fs=_FS, amp=20000):
    return [amp * math.sin(2 * math.pi * freq * i / fs) for i in range(n)]


def _rms(xs):
    return (sum(x * x for x in xs) / len(xs)) ** 0.5 if xs else 0.0


def _ms(ms, fs=_FS):
    return int(fs * ms / 1000)


# Cornice attorno alla voce: scatto del tasto, pre-roll, post, coda di squelch.
_LEAD = _ms(6) + _ms(90)
_TRAIL = _ms(40) + _ms(150)


def _voice_region(samples, n_in):
    """Solo la parte dove c'era l'ingresso, con un margine per i transitori."""
    m = _ms(50)
    return samples[_LEAD + m:_LEAD + n_in - m]


def _goertzel_power(xs, freq, fs=_FS):
    """Potenza in un solo bin (finestra di Hann, perché il tono vicino non coli)."""
    n = len(xs)
    k = 2 * math.cos(2 * math.pi * freq / fs)
    s1 = s2 = 0.0
    for i, x in enumerate(xs):
        w = 0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1))
        s0 = x * w + k * s1 - s2
        s2, s1 = s1, s0
    return s1 * s1 + s2 * s2 - k * s1 * s2


def test_output_is_mono_16bit_same_rate():
    out = radioize_wav(_wav(_tone(1000, _FS)))
    s, fs, nch, width = _read(out)
    assert nch == 1 and width == 2 and fs == _FS
    assert s


def test_length_is_input_plus_preroll_post_click_and_tail():
    n = _FS // 2
    s, *_ = _read(radioize_wav(_wav(_tone(1000, n))))
    assert len(s) == n + _LEAD + _TRAIL


def test_band_cuts_lows_and_highs_relative_to_midband():
    # Tre toni di pari ampiezza: in uscita 100 Hz e 6 kHz devono stare almeno
    # 20 dB sotto il kHz (all'ingresso sono pari). Rapporti, non livelli: il
    # picco viene normalizzato e un livello assoluto non vorrebbe dire niente.
    n = _FS
    src = [a + b + c for a, b, c in zip(_tone(100, n, amp=6000),
                                        _tone(1000, n, amp=6000),
                                        _tone(6000, n, amp=6000))]
    s, *_ = _read(radioize_wav(_wav(src)))
    region = _voice_region(s, n)
    mid = _goertzel_power(region, 1000)
    assert _goertzel_power(region, 100) < mid / 100      # -20 dB
    assert _goertzel_power(region, 6000) < mid / 100


def test_band_with_fft_on_white_noise():
    np = pytest.importorskip("numpy")
    rnd = random.Random(3)
    n = _FS
    src = [rnd.uniform(-8000, 8000) for _ in range(n)]
    s, *_ = _read(radioize_wav(_wav(src)))

    def fractions(xs):
        spec = np.abs(np.fft.rfft(np.asarray(xs, float) * np.hanning(len(xs)))) ** 2
        f = np.fft.rfftfreq(len(xs), 1 / _FS)
        tot = spec.sum()
        return spec[f < 200].sum() / tot, spec[f > 4000].sum() / tot

    lo_in, hi_in = fractions(src)
    lo_out, hi_out = fractions(_voice_region(s, n))
    assert lo_out < lo_in / 20
    assert hi_out < hi_in / 20


def test_bandpass_removes_dc():
    # Una costante non porta audio: il passa-alto la svuota, e nella zona della
    # voce resta solo il fruscio di fondo.
    n = _FS // 2
    s, *_ = _read(radioize_wav(_wav([15000] * n)))
    assert _rms(_voice_region(s, n)) < 1500     # contro 32767 di fondo scala


def test_peak_is_normalised_without_clipping():
    n = _FS // 2
    s, *_ = _read(radioize_wav(_wav(_tone(1000, n, amp=32000))))
    peak = max(abs(x) for x in s)
    assert 0.80 * 32767 <= peak <= 0.85 * 32767 + 1
    assert 32767 not in s and -32768 not in s


def test_stereo_input_is_downmixed():
    n = 8000
    inter = []
    for i in range(n):
        v = 10000 * math.sin(2 * math.pi * 1000 * i / _FS)
        inter += [v, v]
    s, _fs, nch, _w = _read(radioize_wav(_wav(inter, nch=2)))
    assert nch == 1
    assert len(s) == n + _LEAD + _TRAIL


def test_non_16bit_returned_unchanged():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)               # 8 bit: non supportato
        w.setframerate(_FS)
        w.writeframes(bytes([128] * 1000))
    src = buf.getvalue()
    assert radioize_wav(src) == src


def test_garbage_returned_unchanged():
    assert radioize_wav(b"not a wav") == b"not a wav"


def test_deterministic_with_same_seed_and_seed_matters():
    src = _wav(_tone(1000, 4000))
    assert radioize_wav(src) == radioize_wav(src)
    assert radioize_wav(src, seed=1) == radioize_wav(src, seed=1)
    assert radioize_wav(src, seed=1) != radioize_wav(src, seed=2)


def test_fused_pair_equals_two_sections():
    # La coppia fusa esiste solo per la velocità: deve dare gli stessi numeri.
    from accoach.coaching import radio
    rnd = random.Random(5)
    sig = [rnd.uniform(-1, 1) for _ in range(3000)]
    c = radio._band_sections(_FS)
    two = radio._biquad(radio._biquad(sig, c[0]), c[1])
    assert radio._biquad_pair(sig, c[0], c[1]) == two
    three = radio._biquad(two, c[2])
    assert radio._cascade(sig, c[:3]) == three


def test_band_top_edge_end_to_end_at_3700hz():
    # Sopra i 4 kHz taglia già il codec a 8 kHz, quindi il tono a 6 kHz non
    # vede il passa-basso: il bordo alto si prova fra 3 e 4 kHz, dove passa
    # solo se il filtro c'è. Misurato -22 dB; si chiede -15.
    n = _FS
    src = [a + b for a, b in zip(_tone(1000, n, amp=8000), _tone(3700, n, amp=8000))]
    s, *_ = _read(radioize_wav(_wav(src)))
    region = _voice_region(s, n)
    assert _goertzel_power(region, 3700) < _goertzel_power(region, 1000) / 30


def test_band_filter_response_is_butterworth_420_3000():
    # Il filtro da solo, a regime: -3 dB ai due bordi (lo fissano i Q di
    # Butterworth), piatto al kHz, ripido fuori.
    from accoach.coaching import radio
    band = radio._band_sections(_FS)

    def gain_db(f):
        n = _FS
        x = _tone(f, n, amp=1.0)
        y = radio._cascade(x, band)[n // 2:]
        return 20 * math.log10(_rms(y) / _rms(x[n // 2:]))

    assert abs(gain_db(1000)) < 0.5
    assert abs(gain_db(420) + 3.0) < 0.5
    assert abs(gain_db(3000) + 3.0) < 0.5
    assert gain_db(100) < -40
    assert gain_db(6000) < -25


def _speech_like(n, fs=_FS):
    """Ronzio a 140 Hz ricco di armoniche, modulato a sillabe (4 al secondo)."""
    return [6000 * math.sin(math.pi * 4 * i / fs) ** 2
            * sum(math.sin(2 * math.pi * 140 * k * i / fs) / k for k in range(1, 21))
            for i in range(n)]


# RMS della voce col filtro di prima (3b4a565) su ``_speech_like(2 * _FS)``,
# misurato sulla stessa finestra (dopo bip + pausa): il filtro vecchio non c'è
# più nel codice, il numero resta qui come metro.
_OLD_VOICE_RMS_DBFS = -18.50


def test_voice_at_least_as_loud_as_old_filter():
    n = 2 * _FS
    s, *_ = _read(radioize_wav(_wav(_speech_like(n))))
    voice = s[_LEAD:_LEAD + n]
    db = 20 * math.log10(_rms(voice) / 32767)
    assert db >= _OLD_VOICE_RMS_DBFS - 0.5


def test_voice_sets_the_level_not_click_or_tail():
    n = _FS
    s, *_ = _read(radioize_wav(_wav(_speech_like(n))))
    voice_peak = max(abs(x) for x in s[_LEAD:_LEAD + n])
    assert abs(voice_peak - 0.85 * 32767) <= 2
    assert max(abs(x) for x in s[:_ms(6)]) < voice_peak
    assert max(abs(x) for x in s[len(s) - _ms(150):]) < voice_peak


def test_noise_bed_cache_does_not_change_the_output():
    from accoach.coaching import radio
    long_src = _wav(_speech_like(6 * _FS))          # più lunga del fondo minimo
    radio._BED_CACHE.clear()
    fresh = radioize_wav(long_src)
    radio._BED_CACHE.clear()
    radioize_wav(_wav(_speech_like(_FS // 2)))       # riempie la cache, corta
    assert radioize_wav(long_src) == fresh           # la cache cresce, stessi byte
