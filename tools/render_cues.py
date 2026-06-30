"""Pre-render the coach's fixed cue phrases to WAV with Piper (neural TTS).

Run at BUILD time (not shipped): `python tools/render_cues.py`. It AST-scans the
coaching modules for the static string messages passed to `Cue(...)` (skipping
f-strings / dynamic numeric phrases, which fall back to SAPI5 at runtime),
synthesizes each with Piper's Italian voice, and writes them to
`src/accoach/voice_cues/<slug>.wav` plus a `manifest.json` (message -> filename)
that the runtime PrerenderedBackend loads. Re-run whenever cue phrases change.

Pass `--male` to render the optional male neural set (Piper it_IT-riccardo) into
`src/accoach/voice_cues_male/`; the runtime uses it when the "male voice" option
is on, otherwise that option falls back to a male SAPI5 voice.
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COACHING = ROOT / "src" / "accoach" / "coaching"
PIPER = ROOT / "tools" / "piper"
PIPER_EXE = PIPER / "piper.exe"

# (output folder, Piper model) per voice variant. Female is the shipped default;
# male is an optional drop-in the runtime prefers when the male option is on.
_VARIANTS = {
    "female": (ROOT / "src" / "accoach" / "voice_cues", "voices/it_IT-paola-medium.onnx"),
    "male": (ROOT / "src" / "accoach" / "voice_cues_male", "voices/it_IT-riccardo-x_low.onnx"),
}


def static_cue_messages() -> set[str]:
    """Literal message strings of any call that also takes a CueCategory.

    Catches both `Cue(CueCategory.X, "msg", ...)` and helper calls like
    `self._make(s, CueCategory.X, "msg")` used across the detector modules.
    f-strings (dynamic numeric phrases) are ignored — they fall back to SAPI5.
    """
    messages: set[str] = set()

    def has_cue_category(call: ast.Call) -> bool:
        for a in list(call.args) + [kw.value for kw in call.keywords]:
            if isinstance(a, ast.Attribute) and isinstance(a.value, ast.Name) \
                    and a.value.id == "CueCategory":
                return True
        return False

    for path in sorted(COACHING.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and has_cue_category(node):
                for a in list(node.args) + [kw.value for kw in node.keywords]:
                    if isinstance(a, ast.Constant) and isinstance(a.value, str) \
                            and len(a.value) > 5:
                        messages.add(a.value)
    return messages


def dynamic_cue_messages() -> set[str]:
    """Enumerate the small-range numeric cues so they're neural too.

    These mirror the f-strings in the coaching modules over their real value
    ranges; the runtime matches the full string exactly (any drift falls back to
    SAPI5). Continuous numbers (tyre psi/°C advisories) stay on SAPI5.
    """
    msgs: set[str] = set()
    # analyzer.py: f"Stai perdendo {tenths:.0f} decimi qui"  (integer tenths)
    for n in range(1, 26):
        msgs.add(f"Stai perdendo {n} decimi qui")
    # fuel.py: f"Benzina per circa {thresh} giri."  (thresh in {2,3}; 1 is static)
    for n in (2, 3):
        msgs.add(f"Benzina per circa {n} giri.")
    return msgs


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
    messages = sorted(static_cue_messages() | dynamic_cue_messages())
    print(f"rendering {len(messages)} cue phrases (static + numeric) "
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
