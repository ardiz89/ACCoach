"""Make a voice clip sound like a pit-to-car radio transmission.

Pure-Python DSP — no numpy/scipy, and no ``audioop`` (removed in Python 3.13+).
We read a 16-bit PCM WAV, downmix to mono, push it through a telephone/radio
band-pass (~300-3000 Hz), add a little drive (soft clip) and tape hiss, and
bracket the phrase with the short squelch blips you hear when someone keys the
mic. The result is a WAV byte-string ready for
``winsound.PlaySound(data, SND_MEMORY)``.

It runs on the Voice worker thread, off the telemetry hot path: a ~1.3 s clip at
22 kHz is ~28k samples and only a few milliseconds of work, and per-cue results
are cached by the caller so each fixed cue is processed once.
"""

from __future__ import annotations

import io
import math
import random
import wave
from array import array

# Radio passband and character.
_BAND_LO_HZ = 300.0      # high-pass: kill the chesty low end (and any DC)
_BAND_HI_HZ = 3000.0     # low-pass: the classic comms "tinny" top
_DRIVE = 1.8             # pre-clip gain -> radio compression / grit
_HISS = 0.006            # background hiss amplitude (fraction of full scale)
_BLIP_HZ = 1100.0        # squelch blip tone (mic key-up / key-down)
_BLIP_MS = 55
_GAP_MS = 20             # silence between blip and speech
_TARGET_PEAK = 0.85      # normalise output to this fraction of full scale

_FULL = 32767.0


def _lpf_coeffs(fs: float, fc: float, q: float = 0.707):
    """RBJ cookbook low-pass biquad, coefficients normalised by a0."""
    w0 = 2.0 * math.pi * fc / fs
    cw, sw = math.cos(w0), math.sin(w0)
    alpha = sw / (2.0 * q)
    a0 = 1.0 + alpha
    b0 = (1.0 - cw) / 2.0
    b1 = 1.0 - cw
    b2 = (1.0 - cw) / 2.0
    a1 = -2.0 * cw
    a2 = 1.0 - alpha
    return (b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)


def _hpf_coeffs(fs: float, fc: float, q: float = 0.707):
    """RBJ cookbook high-pass biquad, coefficients normalised by a0."""
    w0 = 2.0 * math.pi * fc / fs
    cw, sw = math.cos(w0), math.sin(w0)
    alpha = sw / (2.0 * q)
    a0 = 1.0 + alpha
    b0 = (1.0 + cw) / 2.0
    b1 = -(1.0 + cw)
    b2 = (1.0 + cw) / 2.0
    a1 = -2.0 * cw
    a2 = 1.0 - alpha
    return (b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)


def _biquad(sig: list[float], coeffs) -> list[float]:
    """Direct-form-I biquad over a float list."""
    b0, b1, b2, a1, a2 = coeffs
    x1 = x2 = y1 = y2 = 0.0
    out = [0.0] * len(sig)
    for i, x0 in enumerate(sig):
        y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        out[i] = y0
        x2, x1 = x1, x0
        y2, y1 = y1, y0
    return out


def _blip(fs: int) -> list[float]:
    """A short squelch tone with a smooth bell envelope (no clicks at the edges)."""
    n = max(1, int(fs * _BLIP_MS / 1000.0))
    out = [0.0] * n
    for i in range(n):
        env = math.sin(math.pi * i / n)              # 0 -> 1 -> 0
        out[i] = 0.5 * env * math.sin(2.0 * math.pi * _BLIP_HZ * i / fs)
    return out


def _read_mono(wav_bytes: bytes):
    """(mono float samples in -1..1, frame rate) or (None, 0) if unsupported."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        nch = w.getnchannels()
        width = w.getsampwidth()
        fs = w.getframerate()
        raw = w.readframes(w.getnframes())
    if width != 2:                                   # only 16-bit PCM
        return None, 0
    pcm = array("h")
    pcm.frombytes(raw)
    if nch > 1:
        mono = [sum(pcm[i:i + nch]) / nch / _FULL for i in range(0, len(pcm), nch)]
    else:
        mono = [s / _FULL for s in pcm]
    return mono, fs


def _clamp16(x: float) -> int:
    v = int(x * _FULL)
    if v > 32767:
        return 32767
    if v < -32768:
        return -32768
    return v


def radioize_wav(wav_bytes: bytes, *, seed: int = 12345) -> bytes:
    """Return ``wav_bytes`` re-rendered as a radio transmission (mono 16-bit WAV).

    Unsupported inputs (non-16-bit, unreadable) are returned unchanged so the
    caller can still play the original clip.
    """
    try:
        sig, fs = _read_mono(wav_bytes)
    except (wave.Error, EOFError, ValueError):
        return wav_bytes
    if sig is None or not sig:
        return wav_bytes

    # Band-pass: high-pass (drop DC/low end) then low-pass (comms top end).
    sig = _biquad(sig, _hpf_coeffs(fs, _BAND_LO_HZ))
    sig = _biquad(sig, _lpf_coeffs(fs, _BAND_HI_HZ))

    # Drive into a soft clip for that compressed, slightly broken-up radio grit.
    sig = [math.tanh(_DRIVE * x) for x in sig]

    # A whisper of constant hiss under the whole transmission.
    rnd = random.Random(seed)
    sig = [x + _HISS * (rnd.random() * 2.0 - 1.0) for x in sig]

    # Bracket with squelch blips (mic key-up / key-down).
    gap = [0.0] * int(fs * _GAP_MS / 1000.0)
    blip = _blip(fs)
    full = blip + gap + sig + gap + blip

    # Normalise so the loudest sample lands at the target peak.
    peak = max((abs(x) for x in full), default=1.0) or 1.0
    g = _TARGET_PEAK / peak
    pcm = array("h", (_clamp16(x * g) for x in full))

    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fs)
        w.writeframes(pcm.tobytes())
    return out.getvalue()
