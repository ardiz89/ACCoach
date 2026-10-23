"""Pre-rendered cue coverage (ElevenLabs recordings).

The coach speaks fixed cues from shipped WAVs and only falls back to robotic
SAPI5 for phrases without a WAV. These tests guard that contract: if a cue
phrase changes or is added without re-running ``tools/render_voice.py``, the
coverage test fails — instead of the voice silently regressing to SAPI5.
"""
import json
import wave
from pathlib import Path

from accoach.coaching.voice import _load_prerendered

_ROOT = Path(__file__).resolve().parent.parent
_CUES = _ROOT / "src" / "accoach" / "voice_cues"
from accoach.coaching import spoken


def _manifest() -> dict:
    return json.loads((_CUES / "manifest.json").read_text(encoding="utf-8"))


def test_every_static_cue_has_a_neural_wav():
    missing = spoken.static_cue_messages() - set(_manifest())
    assert not missing, (
        "cue senza WAV neurale — riesegui `python tools/render_voice.py --voice female`: " + repr(missing)
    )


def test_trigger_words_have_a_neural_wav():
    """The trigger words are neural, not SAPI5, from the moment a focus is elected.

    From that moment, every technique call on track is a trigger word — the
    phrases they replace ("Qui hai margine, frena più tardi", "Dai più gas qui") had
    their neural WAV, so electing a focus used to downgrade the voice for the
    rest of the session. The coverage test above cannot see it on its own:
    `static_cue_messages()` walks `ast.Call` nodes and TRIGGER is a dict, so it
    is folded in explicitly there. Only the Italian side: the shipped WAVs are
    Italian by construction.
    """
    from accoach.coaching.cue import TRIGGER

    man = _manifest()
    missing = sorted(e["it"] for e in TRIGGER.values() if e["it"] not in man)
    assert not missing, (
        "parole-innesco senza WAV neurale (escono da SAPI5): " + repr(missing)
    )


def test_the_numeric_cues_have_a_neural_wav_for_what_the_detectors_say():
    """Le frasi con un numero piccolo hanno il loro WAV, e devono essere quelle
    che i rilevatori dicono davvero: la lista di `spoken` le riscrive a
    mano, e fino al Task 8 rendeva «Stai perdendo 1 decimi qui» mentre il coach
    diceva «1 decimo» (quindi SAPI5)."""
    from accoach.coaching.analyzer import CornerStats, classify_corner

    said = set()
    for tenths in range(2, 26):        # da 120 ms il coach parla; 1-25 decimi
        st = CornerStats(lost_ms=tenths * 100.0 - 20.0, throttle_live=1.0,
                         throttle_ref=1.0, brake_live=0.0, brake_ref=0.0,
                         min_speed_live=100.0, min_speed_ref=100.0,
                         braking_early=False, braking_late=False)
        said.add(classify_corner(st, 0, 0.3).message)
    said.add(classify_corner(CornerStats(
        lost_ms=130.0, throttle_live=1.0, throttle_ref=1.0, brake_live=0.0,
        brake_ref=0.0, min_speed_live=100.0, min_speed_ref=100.0,
        braking_early=False, braking_late=False), 0, 0.3).message)
    assert said <= spoken.numeric_cue_messages(), said - spoken.numeric_cue_messages()
    assert "Qui perdi 1 decimo" in said
    man = _manifest()
    missing = sorted(m for m in spoken.numeric_cue_messages() if m not in man)
    assert not missing, missing


def test_no_orphan_wav_is_shipped():
    """Ogni WAV nella cartella è nel manifest: una frase cambiata lascia il suo
    vecchio WAV, che nessuno suonerà più ma che finirebbe nell'EXE."""
    for folder in (_CUES, _ROOT / "src" / "accoach" / "voice_cues_male"):
        if not (folder / "manifest.json").exists():
            continue
        listed = set(json.loads((folder / "manifest.json").read_text(encoding="utf-8")).values())
        orphans = sorted(p.name for p in folder.glob("*.wav") if p.name not in listed)
        assert not orphans, (folder.name, orphans)


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
    assert any("Blocchi le ruote" in k for k in pr)     # a known fixed safety cue


# --- optional male neural set (voice_cues_male/) --------------------------

_MALE = _ROOT / "src" / "accoach" / "voice_cues_male"


def test_male_set_when_present_covers_the_same_cues():
    """If the male neural set is shipped, it must cover the same static cues and
    hold real audio — otherwise the male option would silently drop phrases."""
    if not (_MALE / "manifest.json").exists():
        import pytest
        pytest.skip("male neural set not rendered (optional drop-in)")
    man = json.loads((_MALE / "manifest.json").read_text(encoding="utf-8"))
    missing = spoken.static_cue_messages() - set(man)
    assert not missing, (
        "cue maschile mancante — riesegui `python tools/render_voice.py --voice male`: "
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
    assert pr and any("Blocchi le ruote" in k for k in pr)
