"""Misura cosa il modello scrive quando sente la parola di attivazione.

La lista `_VARIANTI` in `assistente.py` e' nata come **previsione**: «dev» non e'
italiano, quindi il modello italiano scrivera' qualcos'altro, e ho tirato a
indovinare cosa. Questo script smette di indovinare: sintetizza la frase, la
da' in pasto a vosk, e stampa quello che ne esce.

Limite dichiarato, perche' conta: **la voce sintetica non e' la voce del
pilota**. Un risultato buono qui non garantisce niente in macchina; un
risultato *cattivo* qui, invece, e' una condanna — se il modello non ci arriva
nemmeno con una dizione perfetta e senza rumore, in abitacolo non ci arriva di
sicuro. Serve a bocciare, non a promuovere.

Uso:
    python taratura_sveglia.py
    python taratura_sveglia.py "ehi ingegnere" "ehi capo"
"""

from __future__ import annotations

import json
import sys
import tempfile
import wave
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "src"))
MODEL = HERE / "vosk-model-small-it-0.22"
RATE = 16000

DA_PROVARE = ["hey dev", "ehi dev", "hey dev come va", "ehi ingegnere",
              "ehi capo", "ehi coach"]


def _sintetizza(frase: str, out: Path) -> bool:
    import pyttsx3

    from accoach.coaching.voice import _pick_voice_id

    eng = pyttsx3.init()
    eng.setProperty("rate", 165)
    try:
        vid = _pick_voice_id(eng.getProperty("voices"), "it", male=True)
        if vid is not None:
            eng.setProperty("voice", vid)
    except Exception:                                   # noqa: BLE001
        pass
    eng.save_to_file(frase, str(out))
    eng.runAndWait()
    return out.exists() and out.stat().st_size > 44


def _a_16k_mono(path: Path) -> bytes:
    """PCM 16 bit mono a 16 kHz, che e' l'unica cosa che vosk accetta."""
    import numpy as np

    with wave.open(str(path), "rb") as w:
        canali, ampiezza, sr, n = (w.getnchannels(), w.getsampwidth(),
                                   w.getframerate(), w.getnframes())
        raw = w.readframes(n)
    if ampiezza != 2:
        raise SystemExit(f"campioni a {ampiezza * 8} bit, attesi 16")
    a = np.frombuffer(raw, dtype=np.int16)
    if canali > 1:
        a = a.reshape(-1, canali).mean(axis=1)
    if sr != RATE:
        # Interpolazione lineare: `audioop` non esiste piu' da Python 3.13.
        quanti = int(len(a) * RATE / sr)
        a = np.interp(np.linspace(0, len(a) - 1, quanti),
                      np.arange(len(a)), a.astype(np.float64))
    return a.astype(np.int16).tobytes()


def trascrivi(pcm: bytes) -> str:
    from vosk import KaldiRecognizer, Model, SetLogLevel

    SetLogLevel(-1)
    rec = KaldiRecognizer(Model(str(MODEL)), RATE)
    rec.AcceptWaveform(pcm)
    return json.loads(rec.FinalResult()).get("text", "").strip()


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                   # noqa: BLE001
        pass
    import assistente as A

    frasi = sys.argv[1:] or DA_PROVARE
    tmp = Path(tempfile.mkdtemp())
    print(f"{'detto':<22} {'trascritto':<30} riconosciuto")
    print("-" * 70)
    for frase in frasi:
        wav = tmp / (frase.replace(" ", "_") + ".wav")
        if not _sintetizza(frase, wav):
            print(f"{frase:<22} (sintesi fallita)")
            continue
        testo = trascrivi(_a_16k_mono(wav))
        coda = A._dopo_la_sveglia(testo, A.varianti_attive(A._SVEGLIA_DEFAULT))
        esito = "NO" if coda is None else (f"si -> «{coda}»" if coda else "si")
        print(f"{frase:<22} {testo or '(niente)':<30} {esito}")


if __name__ == "__main__":
    main()
