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
   pre-rendered WAV. Picks a voice matching the language and (optionally) gender.

If neither is available it degrades to printing ``[coach] …`` so the coaching
logic stays usable (and testable) without audio. ``enabled=False`` forces that.

Two options shape the timbre:

* ``male=True`` prefers an installed male system voice (e.g. "Cosimo" / "David")
  and skips the shipped neural cues (rendered with a single, non-male voice) so
  every phrase comes out in the same voice. A high-quality male cue set is a
  future drop-in (a ``voice_cues_male/`` folder).
* ``radio=True`` (default) runs whatever is played — neural cue or SAPI phrase —
  through :mod:`accoach.coaching.radio`, so it sounds like a pit-to-car radio
  call. Per-cue results are cached so each fixed cue is processed only once.
"""

from __future__ import annotations

import json
import queue
import sys
import threading
from pathlib import Path

# Sentinel pushed on the queue to tell the worker to stop.
_STOP = object()

# Name fragments that betray a voice's gender across the common Windows SAPI5
# voices (and a few extra languages). Used only as a preference, never a hard
# requirement — if the wanted gender isn't installed we keep the best language
# match instead of going silent.
_MALE_KW = ("cosimo", "david", "mark", "paul", "guy", "george", "ravi",
            "james", "male", "maschile", "uomo")
_FEMALE_KW = ("elsa", "zira", "paola", "hedda", "caroline", "hazel", "susan",
              "catherine", "linda", "female", "femminile", "donna")
_LANG_WORD = {"it": "ital", "en": "engl", "es": "span", "de": "germ", "fr": "fren"}


def _voice_langs(v) -> str:
    """A voice's advertised languages as a lowercase string (driver-agnostic)."""
    raw = getattr(v, "languages", []) or []
    return " ".join(
        (x.decode("latin1", "ignore") if isinstance(x, bytes) else str(x))
        for x in raw
    ).lower()


def _pick_voice_id(voices, language: str, male: bool):
    """Choose the best installed SAPI5 voice id for ``language``/gender, or None.

    Scores each voice: +2 if it matches the language, +1 if it matches the wanted
    gender. The highest score wins; ties keep installation order. Returns None
    only when nothing matches at all (keep the engine default)."""
    target = (language or "it").lower()[:2]
    word = _LANG_WORD.get(target, "")
    best_id, best_score = None, 0
    for v in voices:
        blob = f"{getattr(v, 'id', '')} {getattr(v, 'name', '')}".lower()
        langs = _voice_langs(v)
        lang_ok = bool(word and word in blob) or langs.startswith(target) \
            or f"{target}-" in langs
        is_male = any(k in blob for k in _MALE_KW)
        # In female/default mode a voice with no male marker counts as a match,
        # so we don't regress the previous "first language voice" behaviour.
        gender_ok = is_male if male else not is_male
        score = (2 if lang_ok else 0) + (1 if gender_ok else 0)
        if score > best_score:
            best_id, best_score = getattr(v, "id", None), score
    return best_id if best_score > 0 else None


def _cues_dir(male: bool = False) -> Path | None:
    """Folder of pre-rendered cue WAVs (under _MEIPASS when frozen).

    The shipped set is a female neural voice (Piper it_IT-paola). A male neural
    set is an optional drop-in: ``voice_cues_male/`` (render with
    ``tools/render_cues.py --male``). Returns None for male when that set isn't
    installed, so the caller falls back to the male SAPI5 voice instead of the
    female cues."""
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) / "accoach" if base else Path(__file__).resolve().parent.parent
    if male:
        md = root / "voice_cues_male"
        return md if (md / "manifest.json").exists() else None
    return root / "voice_cues"


def _load_prerendered(male: bool = False) -> dict[str, str]:
    """Map cue message -> absolute WAV path from the manifest (empty if none)."""
    d = _cues_dir(male)
    if d is None:
        return {}
    try:
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
        male: bool = False,
        radio: bool = True,
    ) -> None:
        self._q: "queue.Queue[object]" = queue.Queue()
        self._engine = None
        self._prerendered: dict[str, str] = {}
        self._thread: threading.Thread | None = None
        self._radio = radio
        self._male = male
        self._radio_cache: dict[str, bytes] = {}   # cue path -> processed WAV

        if not enabled:
            return

        # Neural cues: the shipped set is female; male mode uses the optional
        # voice_cues_male/ set if installed, else falls back to the male SAPI
        # voice (empty dict here) so every phrase shares one voice.
        self._prerendered = _load_prerendered(male=male)   # independent of pyttsx3

        try:
            import pyttsx3  # noqa: PLC0415 (optional dependency)

            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", rate)
            self._engine.setProperty("volume", volume)
            self._select_voice(language, male)
        except Exception:  # pragma: no cover - depends on host audio stack
            self._engine = None

        if self._prerendered or self._engine is not None:
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()

    def _select_voice(self, language: str, male: bool) -> None:
        """Pick an installed SAPI5 voice matching ``language`` and gender."""
        try:
            vid = _pick_voice_id(self._engine.getProperty("voices"), language, male)
            if vid is not None:
                self._engine.setProperty("voice", vid)
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
            self._play_cue(wav)
        elif self._engine is not None:
            self._play_engine(text)
        else:
            print(f"[coach] {text}")

    def _play_cue(self, path: str) -> None:  # pragma: no cover - audio side effects
        """Play a pre-rendered cue WAV, radio-processed (and cached) if enabled."""
        import winsound  # noqa: PLC0415 (Windows stdlib)
        if not self._radio:
            winsound.PlaySound(path, winsound.SND_FILENAME)
            return
        data = self._radio_cache.get(path)
        if data is None:
            from .radio import radioize_wav  # noqa: PLC0415
            data = radioize_wav(Path(path).read_bytes())
            self._radio_cache[path] = data
        winsound.PlaySound(data, winsound.SND_MEMORY)

    def _play_engine(self, text: str) -> None:  # pragma: no cover - audio side effects
        """Speak via SAPI5. With radio on, render to a WAV, process, play in memory."""
        if not self._radio:
            self._engine.say(text)
            self._engine.runAndWait()
            return
        import tempfile  # noqa: PLC0415
        import winsound  # noqa: PLC0415
        from .radio import radioize_wav  # noqa: PLC0415
        tmp = Path(tempfile.gettempdir()) / f"hone_tts_{threading.get_ident()}.wav"
        try:
            self._engine.save_to_file(text, str(tmp))
            self._engine.runAndWait()
            data = radioize_wav(tmp.read_bytes())
            winsound.PlaySound(data, winsound.SND_MEMORY)
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass

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
