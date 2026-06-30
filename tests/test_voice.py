"""Voice: gender-aware SAPI voice pick + config round-trip of male/radio toggles."""
import tomllib

from accoach.config import Config, _merge, _to_toml
from accoach.coaching.voice import _pick_voice_id


class _V:
    """Duck-typed SAPI5 voice token (id / name / languages)."""

    def __init__(self, vid, name, languages=()):
        self.id = vid
        self.name = name
        self.languages = list(languages)


_IT_F = _V("TTS_IT_ELSA", "Microsoft Elsa", ["it-IT"])
_IT_M = _V("TTS_IT_COSIMO", "Microsoft Cosimo", ["it-IT"])
_EN_M = _V("TTS_EN_DAVID", "Microsoft David", ["en-US"])


def test_picks_male_italian_when_male_requested():
    assert _pick_voice_id([_IT_F, _IT_M, _EN_M], "it", male=True) == "TTS_IT_COSIMO"


def test_picks_female_italian_by_default():
    assert _pick_voice_id([_IT_M, _IT_F, _EN_M], "it", male=False) == "TTS_IT_ELSA"


def test_male_falls_back_to_language_when_no_male_installed():
    # Only a female IT voice present: language match (score 2) still beats an
    # off-language male (score 1), so we stay in Italian rather than switch tongue.
    assert _pick_voice_id([_IT_F, _EN_M], "it", male=True) == "TTS_IT_ELSA"


def test_none_when_nothing_matches():
    assert _pick_voice_id([], "it", male=False) is None


def test_voice_male_radio_config_roundtrip():
    cfg = Config()
    assert cfg.voice.male is False and cfg.voice.radio is True   # defaults
    cfg.voice.male = True
    cfg.voice.radio = False

    fresh = Config()
    _merge(fresh, tomllib.loads(_to_toml(cfg)))
    assert fresh.voice.male is True
    assert fresh.voice.radio is False
    assert fresh.voice.engineer is True      # neighbouring keys still parse
