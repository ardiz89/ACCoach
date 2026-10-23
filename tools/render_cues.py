"""Pre-render the coach's fixed cue phrases to WAV with Piper (neural TTS).

Run at BUILD time (not shipped): `python tools/render_cues.py`. It takes every
Italian phrase the voice can say from `accoach.coaching.spoken.spoken_phrases()`
(the fixed cues, the numeric ones, the general `Cue.voice` sentences and the
engineer's prefix, levers and revert), synthesizes each with Piper's Italian
voice, and writes them to `src/accoach/voice_cues/<slug>.wav` plus a `manifest.json` (message -> filename)
that the runtime PrerenderedBackend loads. Re-run whenever cue phrases change.

Pass `--male` to render the optional male neural set (Piper it_IT-riccardo) into
`src/accoach/voice_cues_male/`; the runtime uses it when the "male voice" option
is on, otherwise that option falls back to a male SAPI5 voice.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIPER = ROOT / "tools" / "piper"
PIPER_EXE = PIPER / "piper.exe"

# (output folder, Piper model) per voice variant. La maschile e' quella
# predefinita dal 23/10 (`voice.male = true`); la femminile resta l'altra scelta.
_VARIANTS = {
    "female": (ROOT / "src" / "accoach" / "voice_cues", "voices/it_IT-paola-medium.onnx"),
    "male": (ROOT / "src" / "accoach" / "voice_cues_male", "voices/it_IT-riccardo-x_low.onnx"),
}


def static_cue_messages() -> set[str]:
    """Le frasi fisse e le parole d'innesco: la scansione vive in
    `accoach.coaching.spoken`, l'elenco da cui partono generazione e test."""
    from accoach.coaching.spoken import static_cue_messages as scan
    return scan()


def dynamic_cue_messages() -> set[str]:
    """I decimi (1-25) e la benzina (1-3), da `accoach.coaching.spoken`."""
    from accoach.coaching.spoken import numeric_cue_messages
    return numeric_cue_messages()


def slug(text: str) -> str:
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"cue_{h}"


def render(text: str, dest: Path, model: str) -> bool:
    p = subprocess.run(
        [str(PIPER_EXE), "-m", model, "-f", str(dest)],
        input=text, text=True, capture_output=True, cwd=str(PIPER),
    )
    return p.returncode == 0 and dest.exists()


def main() -> None:
    variant = "male" if "--male" in sys.argv[1:] else "female"
    out, model = _VARIANTS[variant]

    if not PIPER_EXE.exists():
        print("Piper not found at", PIPER_EXE)
        print("Download piper_windows_amd64.zip + an Italian voice into tools/piper/")
        raise SystemExit(1)

    out.mkdir(parents=True, exist_ok=True)
    # Tutto quello che la voce dice in italiano, non solo le frasi fisse: anche
    # le frasi generali di `Cue.voice` e l'ingegnere (`coaching/spoken.py`).
    from accoach.coaching.spoken import spoken_phrases
    messages = spoken_phrases()
    print(f"rendering {len(messages)} spoken phrases "
          f"with Piper [{variant}: {model}]…")

    manifest: dict[str, str] = {}
    for text in messages:
        fname = slug(text) + ".wav"
        if render(text, out / fname, model):
            manifest[text] = fname
            print(f"  OK   {text}")
        else:
            print(f"  FAIL {text}")

    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {len(manifest)} WAVs + manifest.json to {out}")


if __name__ == "__main__":
    sys.exit(main())
