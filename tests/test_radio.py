"""radio: pure-Python team-radio DSP (band-pass + squelch), no numpy/audioop."""
import io
import math
import wave
from array import array

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


def _middle(samples, fs):
    """Drop the leading/trailing squelch blip+gap, keep the speech region."""
    pad = int(fs * 0.1)
    return samples[pad:len(samples) - pad]


def test_output_is_mono_16bit_same_rate():
    out = radioize_wav(_wav(_tone(1000, _FS)))
    s, fs, nch, width = _read(out)
    assert nch == 1 and width == 2 and fs == _FS
    assert s


def test_squelch_blips_make_it_longer():
    n = _FS // 2
    out = radioize_wav(_wav(_tone(1000, n)))
    s, *_ = _read(out)
    assert len(s) > n            # blips + gaps bracket the phrase


def test_bandpass_removes_dc():
    # A constant (DC) input carries no audio: the high-pass must gut it, so the
    # speech region (between the blips) comes back near-silent.
    n = _FS // 2
    s, fs, *_ = _read(radioize_wav(_wav([15000] * n)))
    assert _rms(_middle(s, fs)) < 1500     # vs full-scale 32767


def test_high_freq_attenuated_more_than_midband():
    n = _FS // 2
    mid, fs, *_ = _read(radioize_wav(_wav(_tone(1000, n))))   # inside the band
    high, _f, *_ = _read(radioize_wav(_wav(_tone(8000, n))))  # above 3 kHz
    assert _rms(_middle(high, fs)) < _rms(_middle(mid, fs))


def test_stereo_input_is_downmixed():
    n = 8000
    inter = []
    for i in range(n):
        v = 10000 * math.sin(2 * math.pi * 1000 * i / _FS)
        inter += [v, v]
    _s, _fs, nch, _w = _read(radioize_wav(_wav(inter, nch=2)))
    assert nch == 1


def test_non_16bit_returned_unchanged():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)               # 8-bit: unsupported
        w.setframerate(_FS)
        w.writeframes(bytes([128] * 1000))
    src = buf.getvalue()
    assert radioize_wav(src) == src


def test_deterministic():
    src = _wav(_tone(1000, 4000))
    assert radioize_wav(src) == radioize_wav(src)
