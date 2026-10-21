"""I messaggi dell'Ingegnere composti coi numeri veri, nelle due lingue.

`tests/tono.py` legge i modelli («{a}»), non le frasi che il pilota legge ai box:
un `{a:.2f}` nel modello passa il controllo e poi stampa «0.63» su una pagina
italiana. Qui il motore gira davvero (proposte, verdetti, ripristini, uscite,
pressioni, pioggia) con valori di esempio *con i decimali*, e alle frasi che
escono si applicano le stesse regole. Stesso schema di `test_backend_tono.py`.
"""
import sys
from pathlib import Path

import pytest

from accoach import config
from accoach.engineer import (
    Balance,
    DecisionKind,
    LapStats,
    Phase,
    RaceEngineer,
    Speed,
    Symptom,
)
from accoach.engineer.core import NO_WINDOW, _skip_tail
from accoach.engineer.profiles import GT3_PROFILE, ROAD_PROFILE
from accoach.engineer.profiles._common import PressurePhase
from accoach.engineer.steps import UnknownSteps
from accoach.setup import labels

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tono  # noqa: E402

U, O = Balance.UNDERSTEER, Balance.OVERSTEER
SYM = Symptom(U, Phase.APEX, Speed.LOW)
OTHER = Symptom(O, Phase.EXIT, Speed.LOW)
PRESS_OK = {"front": 26.5, "rear": 26.5}


@pytest.fixture(params=["it", "en"])
def lang(request, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    config.load_config(reload=True)
    config.set_language(request.param)
    yield request.param
    config._cache = None


def _lap(time_ms=100437, scores=None, press=PRESS_OK, fuel=0.0, **kw):
    scores = scores or {}
    st = LapStats(lap_time_ms=time_ms, symptom_scores=dict(scores),
                  symptom_corners={s: 4 for s in scores}, pressures_hot=press, **kw)
    st.fuel_l = fuel
    return st


def _until(eng, lap, kind=DecisionKind.PROPOSE, n=8):
    for _ in range(n):
        d = eng.observe(lap())
        if d.kind is kind:
            return d
    raise AssertionError(f"il motore non e' arrivato a {kind}")


def _messages():
    """Tutto quello che il motore dice, nella lingua attiva."""
    out = []
    # La raccolta, coi tre motivi per cui un giro non conta.
    eng = RaceEngineer(GT3_PROFILE, min_stable=3)
    out.append(eng.observe(_lap()).message)
    for why, where, warm in (("cut", "Variante Ascari", True), ("cut", "", True),
                             ("invalid", "", True), ("", "", False)):
        st = _lap(stable=bool(not why), warmed_up=warm)
        st.unstable_why, st.lost_where = why, where
        out.append(_skip_tail(st))
    # La proposta, la sua asticella, la prova e il verdetto con tutte le code.
    eng = RaceEngineer(GT3_PROFILE, min_stable=3)
    d = _until(eng, lambda: _lap(scores={SYM: 0.634, OTHER: 0.213}, fuel=20.4))
    out += [d.message, d.change.rationale, d.prediction.text]
    eng.mark_applied()
    out.append(eng.observe(_lap(scores={SYM: 0.18, OTHER: 0.57}, fuel=58.7)).message)
    out.append(_until(eng, lambda: _lap(time_ms=101950, scores={SYM: 0.18, OTHER: 0.57},
                                        fuel=58.7), DecisionKind.ACCEPTED).message)
    # Migliora ma non risolve.
    eng = RaceEngineer(GT3_PROFILE, min_stable=3)
    _until(eng, lambda: _lap(scores={SYM: 0.734}))
    eng.mark_applied()
    out.append(_until(eng, lambda: _lap(scores={SYM: 0.412}), DecisionKind.ACCEPTED).message)
    # Peggiora, e poi non fa niente: i due ripristini.
    for after_time, after in ((101950, 0.634), (100437, 0.611)):
        eng = RaceEngineer(GT3_PROFILE, min_stable=3)
        _until(eng, lambda: _lap(scores={SYM: 0.634}))
        eng.mark_applied()
        d = _until(eng, lambda: _lap(time_ms=after_time, scores={SYM: after}),
                   DecisionKind.REVERTED)
        out += [d.message, d.change.rationale]
    # Le pressioni: proposta, prova, verdetto, e quella tagliata al massimo per sosta.
    for front in (24.73, 25.83):
        eng = RaceEngineer(GT3_PROFILE, min_stable=3)
        d = _until(eng, lambda: _lap(press={"front": front, "rear": 26.5}))
        out += [d.change.rationale, d.prediction.text]
    eng.mark_applied()
    out.append(_until(eng, lambda: _lap(time_ms=100437, press=PRESS_OK),
                      DecisionKind.ACCEPTED).message)
    eng = RaceEngineer(GT3_PROFILE, min_stable=3)
    _until(eng, lambda: _lap(press={"front": 24.73, "rear": 26.5}))
    eng.mark_applied()
    d = _until(eng, lambda: _lap(time_ms=101950), DecisionKind.REVERTED)
    out += [d.message, d.change.rationale]
    eng = RaceEngineer(GT3_PROFILE, min_stable=3)
    _until(eng, lambda: _lap(press={"front": 24.73, "rear": 26.5}, fuel=20.4))
    eng.mark_applied()
    out.append(_until(eng, lambda: _lap(time_ms=101950, fuel=58.7),
                      DecisionKind.ACCEPTED).message)
    # Le fasi che si chiudono, fino in fondo.
    eng = RaceEngineer(GT3_PROFILE, min_stable=3)
    for _ in range(12):
        d = eng.observe(_lap())
        out.append(d.message)
        if d.kind is DecisionKind.DONE:
            break
    # Rimedi finiti.
    eng = RaceEngineer(GT3_PROFILE, min_stable=3)
    for _ in range(40):
        d = eng.observe(_lap(scores={SYM: 0.634}))
        out.append(d.message)
        if d.change is not None:
            out.append(d.change.rationale)
        if d.kind in (DecisionKind.PROPOSE, DecisionKind.REVERTED):
            eng.mark_applied()
        if eng.exhausted_calls:
            break
    # Pioggia, e un cambio di condizioni a metà prova.
    eng = RaceEngineer(GT3_PROFILE, min_stable=3)
    out.append(eng.observe(_lap(wet=True)).message)
    eng = RaceEngineer(GT3_PROFILE, min_stable=3)
    eng.observe(_lap(wet=False))
    out.append(eng.observe(_lap(wet=True)).message)
    # Una modifica rimasta senza verdetto dall'altra sessione.
    eng = RaceEngineer(GT3_PROFILE, min_stable=3)
    _until(eng, lambda: _lap(scores={SYM: 0.634}))
    eng.mark_applied()
    state = eng.state()
    eng = RaceEngineer(GT3_PROFILE, min_stable=3)
    eng.restore(state)
    out.append(eng.observe(_lap()).message)
    # Le uscite che si ripetono, con la leva e senza.
    for exhausted in (False, True):
        eng = RaceEngineer(GT3_PROFILE, min_stable=3)
        if exhausted:
            eng.remedy_idx[OTHER] = 9
        for corner, where in ((2, "Tosa"), (5, "Piratella"), (9, "Acque Minerali")):
            st = _lap(stable=False)
            st.unstable_why, st.lost_where = "cut", where
            st.off_symptom, st.off_corner = OTHER, corner
            d = eng.observe(st)
        out.append(d.message)
    # Un'auto di cui non sappiamo il passo: non scrive, e dice perché.
    eng = RaceEngineer(ROAD_PROFILE, min_stable=3, steps=UnknownSteps())
    eng.phase_idx = 1
    out.append(_until(eng, lambda: _lap(scores={Symptom(U, Phase.APEX, Speed.LOW): 0.634}),
                      DecisionKind.STAND_DOWN).message)
    eng = RaceEngineer(ROAD_PROFILE, min_stable=3, steps=UnknownSteps())
    out.append(_until(eng, lambda: _lap(press={"front": 27.83, "rear": 30.0}),
                      DecisionKind.STAND_DOWN).message)
    # Un'auto che non sappiamo classificare: le pressioni non si toccano.
    out.append(PressurePhase(26.5, 0.5).reconfigure(pressure_window=NO_WINDOW).blind())
    # Il ripristino detto all'editor dopo una scrittura.
    out.append(labels.reload_hint("HONE_3"))
    return [m for m in out if m]


def test_every_engineer_message_follows_the_rules(lang):
    texts = _messages()
    assert len(texts) > 30
    bad = [(t, tono.violations(t, lang)) for t in texts if tono.violations(t, lang)]
    assert not bad, bad


def test_the_sample_decimals_reach_the_page_with_the_right_separator(lang):
    text = " ".join(_messages())
    if lang == "it":
        for num in ("0,63", "0,18", "24,7 psi", "25,5 psi", "26,5 psi", "20 L", "59 L"):
            assert num in text, num
        assert "0.63" not in text and "24.7" not in text
    else:
        for num in ("0.63", "0.18", "24.7 psi", "25.5 psi", "26.5 psi", "20 L", "59 L"):
            assert num in text, num


def test_the_symptom_is_said_in_words_not_as_its_identifier(lang):
    """«understeer apex low» è la chiave del registro, non una frase: su una
    pagina in italiano era inglese, e in inglese non era una frase."""
    text = " ".join(_messages())
    assert str(SYM) not in text and str(OTHER) not in text
    words = {"it": "sottosterzo a centro curva nelle curve lente",
             "en": "understeer mid-corner in slow corners"}[lang]
    assert words in text


def test_english_is_not_a_copy_of_italian(tmp_path, monkeypatch):
    def run(lg):
        monkeypatch.setattr(config, "config_path", lambda: tmp_path / f"{lg}.toml")
        config.load_config(reload=True)
        config.set_language(lg)
        try:
            return _messages()
        finally:
            config._cache = None
    it, en = run("it"), run("en")
    assert len(it) == len(en)
    same = [a for a, b in zip(it, en) if a == b and len(a.split()) >= 4]
    assert not same, same
