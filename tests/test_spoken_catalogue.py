"""L'elenco chiuso di quello che la voce dice in italiano, e la voce maschile.

Ogni frase dell'elenco diventera' un WAV registrato una volta (ElevenLabs): una
frase detta che non sta nell'elenco non avra' il suo WAV e cadra' sulla voce di
Windows senza che nessuno se ne accorga. Per questo l'elenco non si controlla
rileggendolo: il test «di chiusura» fa girare i percorsi veri che costruiscono
frasi a runtime (pressioni, temperature, aiuti, ingegnere) e pretende che ogni
testo arrivato a `voice.say` ci sia.
"""
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

import tono
from accoach.coaching.spoken import spoken_phrases
from accoach.engineer.voice_levers import all_voice_levers

import test_voce_generale as gen_t
import test_voce_leve as leve_t

_ROOT = Path(__file__).resolve().parent.parent
_MANIFEST = _ROOT / "src" / "accoach" / "voice_cues" / "manifest.json"

# Le sole frasi che possono dire un numero: un insieme chiuso, e il numero e' il
# consiglio stesso (spec, «Scelte mie» 2).
_NUMBERED = re.compile(r"^(Qui perdi \d+ decim[oi]|Benzina per circa \d gir[oi]\.)$")

# Le otto frasi generali del Task 1, scritte qui a mano: se il codice cambia
# una frase, questo elenco e quello del catalogo devono cambiare insieme.
_TASK1 = [
    "Gomme anteriori troppo gonfie. Togli pressione a freddo.",
    "Gomme posteriori troppo gonfie. Togli pressione a freddo.",
    "Gomme anteriori troppo sgonfie. Aggiungi pressione a freddo.",
    "Gomme posteriori troppo sgonfie. Aggiungi pressione a freddo.",
    "Gomme troppo calde. Guida più fluido.",
    "Gomme troppo fredde. Spingi per scaldarle.",
    "Blocchi davanti in più curve. Alza l'ABS di uno.",
    "Pattini in uscita in più punti. Alza il TC di uno.",
]

_PREFIXES = [
    "Ingegnere, rientra ai box.",
    "Ingegnere, cambia dal volante.",
    "Ingegnere, se vuoi prova ai box.",
    "Ingegnere, se vuoi prova dal volante.",
]
_REVERT = "Riporta l'assetto com'era."


@pytest.fixture(scope="module")
def catalogue():
    return spoken_phrases()


def test_sorted_and_without_duplicates(catalogue):
    assert catalogue == sorted(set(catalogue))


def test_every_wav_of_today_is_in_the_list(catalogue):
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    assert len(manifest) == 59
    # Le chiavi di oggi non hanno numeri di dettaglio: le sole cifre sono i
    # decimi e la benzina. Verificato, non supposto.
    assert [k for k in manifest if re.search(r"\d", k) and not _NUMBERED.match(k)] == []
    assert sorted(set(manifest) - set(catalogue)) == []


def test_the_task1_general_sentences_are_in(catalogue):
    assert sorted(set(_TASK1) - set(catalogue)) == []


def test_the_engineer_is_in(catalogue):
    assert len(all_voice_levers()) == 25
    wanted = set(all_voice_levers()) | set(_PREFIXES) | {_REVERT}
    assert sorted(wanted - set(catalogue)) == []


def test_no_digit_except_tenths_and_fuel(catalogue):
    assert [p for p in catalogue if re.search(r"\d", p) and not _NUMBERED.match(p)] == []
    assert sum(bool(_NUMBERED.match(p)) for p in catalogue) == 25 + 3


def test_the_whole_list_keeps_the_voice_tone(catalogue):
    """Il tono della voce su tutto l'elenco, in un posto solo: le regole del 21/10
    con le otto parole della superficie `coach`. Non e' una superficie di
    `tono.py` perche' l'elenco ripete di proposito pezzi di frase («Togli
    pressione a freddo» per i due assi) e il controllo dei doppioni li conterebbe,
    e perche' e' solo italiano."""
    limit = tono.MAX_WORDS_BY_SURFACE["coach"]
    bad = {p: tono.violations(p, "it", limit) for p in catalogue}
    assert {p: v for p, v in bad.items() if v} == {}


# --- il test di chiusura: i percorsi veri ------------------------------------

def _said_by_the_coach(cue):
    """Quello che il motore passa a `voice.say` per questo avviso, in italiano,
    senza focus e con un focus attivo (la parola d'innesco, se la categoria ne ha
    una)."""
    from accoach.engine import _spoken_forms
    from accoach.i18n import cue_text
    cue.message = cue_text(cue.message, "it")
    return {_spoken_forms(cue, theme, "it")[0] for theme in (None, "braking")}


def _real_cues():
    cues = [gen_t._pressure(c[0]) for c in gen_t.PRESSURE_CASES]
    cues += [gen_t._temp(98.0), gen_t._temp(62.0)]
    cues += [gen_t._aid(kind, lv) for kind in ("abs", "tc") for lv in (3, -1, 9)]
    return cues


def test_closing_every_dynamic_coach_cue_is_in_the_list(catalogue):
    said = set()
    for cue in _real_cues():
        said |= _said_by_the_coach(cue)
    assert len(said) >= 9          # 4 pressioni, 2 temperature, ABS, TC, ripartitore
    assert sorted(said - set(catalogue)) == []


def test_closing_every_engineer_announcement_is_in_the_list(catalogue, tmp_path, monkeypatch):
    from accoach.engineer import Decision, DecisionKind
    eng, voice = leve_t._engine(tmp_path, monkeypatch)
    changes = [c for _, c in leve_t._all_remedies()]
    changes += [leve_t._pressure(f, r) for f, r in
                ((24.7, 27.5), (30.0, 27.5), (27.5, 24.7), (27.5, 30.0))]
    for change in changes:
        for tag in ("BOX", "AV"):
            ch = replace(change, tag=tag)
            for kind, conf, c in ((DecisionKind.PROPOSE, "high", ch),
                                  (DecisionKind.PROPOSE, "medium", ch),
                                  (DecisionKind.REVERTED, "", ch.reversed())):
                eng._engineer_spoken_sig = None
                eng._announce_engineer(Decision(kind, "msg", c, conf))
    eng.close()
    assert set(_PREFIXES) <= set(voice.said) and _REVERT in voice.said
    assert sorted(set(voice.said) - set(catalogue)) == []


# --- la voce maschile predefinita --------------------------------------------

def test_male_voice_is_the_default():
    from accoach.config import Config
    assert Config().voice.male is True


def test_the_config_template_writes_male_true():
    from accoach.config import _DEFAULT_TOML, Config, _to_toml
    assert re.search(r"^male = true\b", _DEFAULT_TOML, re.M)
    assert re.search(r"^male = true\b", _to_toml(Config()), re.M)
