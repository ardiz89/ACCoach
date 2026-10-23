"""Ogni frase che la voce puo' dire in italiano ha il suo WAV, in tutte e due le voci.

Una frase senza WAV non si sente meno: si sente con la voce di Windows, in mezzo
a quelle registrate, e nessun test lo diceva. L'elenco viene dal codice
(`spoken_phrases`), il confronto e' col `manifest.json` di ciascuna voce.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from accoach.coaching.spoken import spoken_phrases

_CUES = Path(__file__).resolve().parents[1] / "src" / "accoach"
_VOICES = ("voice_cues_male", "voice_cues")


def _manifest(folder: str) -> dict[str, str]:
    return json.loads((_CUES / folder / "manifest.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("folder", _VOICES)
def test_every_spoken_phrase_has_a_wav(folder):
    man = _manifest(folder)
    missing = [p for p in spoken_phrases() if p not in man]
    assert missing == []
    absent = [f for f in man.values() if not (_CUES / folder / f).is_file()]
    assert absent == []


@pytest.mark.parametrize("folder", _VOICES)
def test_the_manifest_has_nothing_the_code_never_says(folder):
    extra = sorted(set(_manifest(folder)) - set(spoken_phrases()))
    assert extra == []


@pytest.mark.parametrize("folder", _VOICES)
def test_the_wavs_are_what_the_player_reads(folder):
    for name in _manifest(folder).values():
        with wave.open(str(_CUES / folder / name)) as w:
            assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (22050, 1, 2)
            assert w.getnframes() > 0
