"""Speak cues out loud, off the hot path.

Speaking runs on a background worker thread fed by a queue; :meth:`Voice.say`
just enqueues and returns immediately, keeping the telemetry loop at full rate.

Two backends, tried in order per phrase:
1. **Pre-rendered neural cues** — the fixed cue phrases are synthesized at build
   time with Piper (neural TTS) and shipped as WAVs (``accoach/voice_cues/`` +
   ``manifest.json``). Playback is just ``winsound`` reading a small WAV: instant
   and far more human than SAPI5, with zero runtime synthesis. Works even without
   pyttsx3 installed.
2. **SAPI5 via pyttsx3** — for dynamic phrases (numbers) and any cue without a
   pre-rendered WAV. Picks the Italian voice.

If neither is available it degrades to printing ``[coach] …`` so the coaching
logic stays usable (and testable) without audio. ``enabled=False`` forces that.
"""

from __future__ import annotations

import json
import queue
import sys
import threading
from pathlib import Path

# Sentinel pushed on the queue to tell the worker to stop.
_STOP = object()


def _cues_dir() -> Path:
    # Ships inside the package; resolves under _MEIPASS when frozen.
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "accoach" / "voice_cues"
    return Path(__file__).resolve().parent.parent / "voice_cues"


def _load_prerendered() -> dict[str, str]:
    """Map cue message -> absolute WAV path from the shipped manifest."""
    try:
        d = _cues_dir()
        manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, str] = {}
    for msg, fname in manifest.items():
        p = d / fname
        if p.exists():
            out[msg] = str(p)
    return out


class Voice:
    def __init__(
        self,
        enabled: bool = True,
        rate: int = 180,
        volume: float = 1.0,
        language: str = "it",
    ) -> None:
        self._q: "queue.Queue[object]" = queue.Queue()
        self._engine = None
        self._prerendered: dict[str, str] = {}
        self._thread: threading.Thread | None = None

        if not enabled:
            return

        self._prerendered = _load_prerendered()   # independent of pyttsx3

        try:
            import pyttsx3  # noqa: PLC0415 (optional dependency)

            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", rate)
            self._engine.setProperty("volume", volume)
            self._select_voice(language)
        except Exception:  # pragma: no cover - depends on host audio stack
            self._engine = None

        if self._prerendered or self._engine is not None:
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()

    def _select_voice(self, language: str) -> None:
        """Pick an installed SAPI5 voice matching ``language`` (e.g. it / en)."""
        target = (language or "it").lower()[:2]
        words = {"it": "ital", "en": "engl", "es": "span", "de": "germ", "fr": "fren"}
        word = words.get(target, "")
        try:
            for v in self._engine.getProperty("voices"):
                blob = f"{getattr(v, 'id', '')} {getattr(v, 'name', '')}".lower()
                # ``languages`` items may be bytes or str depending on the driver.
                raw = getattr(v, "languages", []) or []
                langs = " ".join(
                    (x.decode("latin1", "ignore") if isinstance(x, bytes) else str(x))
                    for x in raw
                ).lower()
                if (word and word in blob) or langs.startswith(target) \
                        or f"{target}-" in langs:
                    self._engine.setProperty("voice", v.id)
                    return
        except Exception:  # pragma: no cover
            pass  # keep default voice

    def say(self, text: str) -> None:
        """Queue ``text`` to be spoken (or printed if there's no audio)."""
        if self._thread is None:
            print(f"[coach] {text}")
            return
        self._q.put(text)

    def _speak(self, text: str) -> None:
        wav = self._prerendered.get(text)
        if wav is not None:
            import winsound  # noqa: PLC0415 (Windows stdlib)
            winsound.PlaySound(wav, winsound.SND_FILENAME)
        elif self._engine is not None:
            self._engine.say(text)
            self._engine.runAndWait()
        else:
            print(f"[coach] {text}")

    def _worker(self) -> None:  # pragma: no cover - audio side effects
        while True:
            item = self._q.get()
            if item is _STOP:
                break
            text = str(item)
            try:
                self._speak(text)
            except Exception:
                # Pre-rendered playback failed (or odd state): try the engine.
                try:
                    if self._engine is not None:
                        self._engine.say(text)
                        self._engine.runAndWait()
                    else:
                        print(f"[coach] {text}")
                except Exception:
                    print(f"[coach] {text}")

    @property
    def is_audio(self) -> bool:
        return self._thread is not None

    def close(self) -> None:
        if self._thread is not None:
            self._q.put(_STOP)
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._engine is not None:
            try:
                self._engine.stop()
            except Exception:  # pragma: no cover
                pass

    def __enter__(self) -> "Voice":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
