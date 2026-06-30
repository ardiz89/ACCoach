"""Pre-rendered neural (Piper) cue coverage.

The coach speaks fixed cues from shipped WAVs (neural quality) and only falls
back to robotic SAPI5 for phrases without a WAV. These tests guard that contract:
if a cue phrase changes or is added without re-running ``tools/render_cues.py``,
the coverage test fails — instead of the voice silently regressing to SAPI5.
"""
import json
import sys
import wave
from pathlib import Path

from accoach.coaching.voice import _load_prerendered

_ROOT = Path(__file__).resolve().parent.parent
_CUES = _ROOT / "src" / "accoach" / "voice_cues"
sys.path.insert(0, str(_ROOT / "tools"))
import render_cues  # noqa: E402 - build-time helper, reused here for coverage


def _manifest() -> dict:
    return json.loads((_CUES / "manifest.json").read_text(encoding="utf-8"))


def test_every_static_cue_has_a_neural_wav():
    missing = render_cues.static_cue_messages() - set(_manifest())
    assert not missing, (
        "cue senza WAV neurale — riesegui `python tools/render_cues.py`: " + repr(missing)
    )


def test_manifest_wavs_all_exist_and_are_audio():
    man = _manifest()
    assert man, "manifest vuoto"
    for msg, fname in man.items():
        p = _CUES / fname
        assert p.exists(), f"WAV mancante {fname} per {msg!r}"
        with wave.open(str(p), "rb") as w:        # valid RIFF/WAV with real frames
            assert w.getnframes() > 0


def test_runtime_loads_prerendered_backend():
    pr = _load_prerendered()
    assert pr, "il backend pre-renderizzato non carica nessun WAV"
    assert any("Bloccaggio" in k for k in pr)     # a known fixed safety cue


# --- optional male neural set (voice_cues_male/) --------------------------

_MALE = _ROOT / "src" / "accoach" / "voice_cues_male"


def test_male_set_when_present_covers_the_same_cues():
    """If the male neural set is shipped, it must cover the same static cues and
    hold real audio — otherwise the male option would silently drop phrases."""
    if not (_MALE / "manifest.json").exists():
        import pytest
        pytest.skip("male neural set not rendered (optional drop-in)")
    man = json.loads((_MALE / "manifest.json").read_text(encoding="utf-8"))
    missing = render_cues.static_cue_messages() - set(man)
    assert not missing, (
        "cue maschile mancante — riesegui `python tools/render_cues.py --male`: "
        + repr(missing)
    )
    for fname in man.values():
        p = _MALE / fname
        assert p.exists(), f"WAV maschile mancante {fname}"
        with wave.open(str(p), "rb") as w:
            assert w.getnframes() > 0


def test_runtime_loads_male_backend_when_present():
    if not (_MALE / "manifest.json").exists():
        import pytest
        pytest.skip("male neural set not rendered (optional drop-in)")
    pr = _load_prerendered(male=True)
    assert pr and any("Bloccaggio" in k for k in pr)
