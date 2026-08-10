"""Play the trigger words so a human can judge them. Nothing else can.

The measurements in the test suite prove a WAV is not silence. They cannot say
whether "rilascia" is *pronounced well* when torn out of a sentence, and a single
word said badly is worse than the sentence it replaces.

By default you hear what the driver hears: the same radio treatment
:class:`accoach.coaching.voice.Voice` applies (``radio=True``). Pass ``--nudo``
to hear Piper's raw output instead — useful to tell a bad synthesis apart from a
harsh filter.

Usage (from the repo root):
    python tools/ascolta_inneschi.py            # female set, radio, like the car
    python tools/ascolta_inneschi.py --male
    python tools/ascolta_inneschi.py --nudo
"""

from __future__ import annotations

import json
import sys
import time
import winsound
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from accoach.coaching.cue import TRIGGER  # noqa: E402
from accoach.coaching.radio import radioize_wav  # noqa: E402

male = "--male" in sys.argv[1:]
raw = "--nudo" in sys.argv[1:]

folder = ROOT / "src" / "accoach" / ("voice_cues_male" if male else "voice_cues")
manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))

voice = "maschile" if male else "femminile"
treat = "nuda" if raw else "con la radio, come in macchina"
print(f"\nVoce {voice}, {treat} — {len(TRIGGER)} parole-innesco.")
print("Ctrl+C per fermare.\n")

for cat, entry in TRIGGER.items():
    word = entry["it"]
    name = manifest.get(word)
    if not name:
        print(f"  {word:16} MANCA dal manifest")
        continue
    data = (folder / name).read_bytes()
    if not raw:
        data = radioize_wav(data)
    print(f"  {word:16} [{cat.name}]")
    winsound.PlaySound(data, winsound.SND_MEMORY)
    time.sleep(0.45)          # a beat between words, or they blur together

print("\nQuella che non ti convince, dimmela: si può risintetizzare da sola.")
