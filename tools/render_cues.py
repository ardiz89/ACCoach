"""Pre-render the coach's fixed cue phrases to WAV with Piper (neural TTS).

Run at BUILD time (not shipped): `python tools/render_cues.py`. It AST-scans the
coaching modules for the static string messages passed to `Cue(...)` (skipping
f-strings / dynamic numeric phrases, which fall back to SAPI5 at runtime),
synthesizes each with Piper's Italian voice, and writes them to
`src/accoach/voice_cues/<slug>.wav` plus a `manifest.json` (message -> filename)
that the runtime PrerenderedBackend loads. Re-run whenever cue phrases change.
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
OUT = ROOT / "src" / "accoach" / "voice_cues"
PIPER = ROOT / "tools" / "piper"
PIPER_EXE = PIPER / "piper.exe"
MODEL = "voices/it_IT-paola-medium.onnx"


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


def render(text: str, dest: Path) -> bool:
    p = subprocess.run(
        [str(PIPER_EXE), "-m", MODEL, "-f", str(dest)],
        input=text, text=True, capture_output=True, cwd=str(PIPER),
    )
    return p.returncode == 0 and dest.exists()


def main() -> None:
    if not PIPER_EXE.exists():
        print("Piper not found at", PIPER_EXE)
        print("Download piper_windows_amd64.zip + an Italian voice into tools/piper/")
        raise SystemExit(1)

    OUT.mkdir(parents=True, exist_ok=True)
    messages = sorted(static_cue_messages() | dynamic_cue_messages())
    print(f"rendering {len(messages)} cue phrases (static + numeric) with Piper…")

    manifest: dict[str, str] = {}
    for text in messages:
        fname = slug(text) + ".wav"
        if render(text, OUT / fname):
            manifest[text] = fname
            print(f"  ✓ {text}")
        else:
            print(f"  ✗ FAILED: {text}")

    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {len(manifest)} WAVs + manifest.json to {OUT}")


if __name__ == "__main__":
    sys.exit(main())
