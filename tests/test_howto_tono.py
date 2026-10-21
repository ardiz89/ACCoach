"""I testi della Pagella e del «Come si fa», nel tono deciso col pilota.

Il pilota ha bocciato il testo «da macchina»: la stessa frase su ogni scheda,
gli slogan, i due punti a effetto. Qui il tono diventa una proprietà che si
controlla: nessuna frase ripetuta fra i difetti, niente due punti negli
esercizi, niente emoji, numeri con la virgola in italiano, e nessuna cifra
inventata dentro i testi (i numeri arrivano come parametri).
"""
import re

import pytest

from accoach.coaching import training
from accoach.coaching.defects import DEFECTS, DefectSummary
from accoach.coaching.errors import ERRORS
from accoach.coaching.howto import (
    HowTo,
    defect_name,
    error_name,
    fmt_s,
    howto,
    problem,
    verdict,
)

LANGS = ("it", "en")
_FIELDS = ("what", "watch", "ignore", "drill", "done_when")


def _split(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _sentences(h: HowTo):
    return [s for f in _FIELDS for s in _split(getattr(h, f))]


def _top(key="brake_early", mean=290.0, unit="ms"):
    return DefectSummary(key=key, mean=mean, unit=unit, laps_with=10, laps=14,
                         corners=[(2, mean)], main=True)


def _verdicts(lang):
    return [
        verdict(0.62, _top(), 0.45, None, lang),
        verdict(0.62, _top(), 0.45, {"gap_delta_s": -0.15, "better": ["brake_early"],
                                     "worse": ["over_brake"]}, lang),
        verdict(0.40, _top("coasting", 0.6, "s"), 0.0,
                {"gap_delta_s": 0.08, "better": [], "worse": ["lift"]}, lang),
        verdict(0.30, None, 0.0, {"gap_delta_s": 0.0, "better": [], "worse": []}, lang),
    ]


def _problems(lang):
    return [problem(k, "Variante Alta", 0.6 if k == "coasting" else 290,
                    "s" if k == "coasting" else "ms", lang, metres=14)
            for k in DEFECTS]


def _all_texts():
    for lang in LANGS:
        for k in DEFECTS:
            h = howto(k, lang)
            yield from (getattr(h, f) for f in _FIELDS)
        yield from _verdicts(lang)
        yield from _problems(lang)


# --- i nomi -----------------------------------------------------------------

def test_defect_names_are_the_ones_decided_with_the_pilot():
    assert [defect_name(k, "it") for k in DEFECTS] == [
        "Freni troppo presto", "Freni troppo tardi", "Troppo freno",
        "Gas tardi in uscita", "Poca velocità in curva",
        "Alzi il gas sul dritto", "Veleggi prima di frenare"]


@pytest.mark.parametrize("lang", LANGS)
def test_every_defect_and_error_has_a_distinct_name(lang):
    names = [defect_name(k, lang) for k in DEFECTS]
    errors = [error_name(k, lang) for k in ERRORS]
    assert all(names) and len(set(names)) == len(names)
    assert all(errors) and len(set(errors)) == len(errors)


def test_english_is_a_translation_not_a_copy():
    for k in DEFECTS:
        assert defect_name(k, "en") != defect_name(k, "it")
        it, en = howto(k, "it"), howto(k, "en")
        for f in _FIELDS:
            assert getattr(en, f) != getattr(it, f), (k, f)
        assert en.laps == it.laps
    for k in ERRORS:
        assert error_name(k, "en") != error_name(k, "it")


def test_unknown_language_falls_back_to_english():
    assert defect_name("lift", "de") == defect_name("lift", "en")
    assert howto("lift", "de") == howto("lift", "en")


# --- il «come si fa» --------------------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
def test_every_defect_has_its_own_howto_and_no_sentence_repeats(lang):
    sentences = [s for k in DEFECTS for s in _sentences(howto(k, lang))]
    assert len(sentences) == len(set(sentences))


@pytest.mark.parametrize("lang", LANGS)
def test_every_howto_is_complete(lang):
    for k in DEFECTS:
        h = howto(k, lang)
        assert all(getattr(h, f).strip() for f in _FIELDS), k
        assert h.laps >= 1


@pytest.mark.parametrize("lang", LANGS)
def test_howto_texts_have_no_colon_and_no_digit(lang):
    # I due punti sono il tic da slogan («Una cosa alla volta: …»). Le cifre non
    # si inventano: i numeri del pilota arrivano da `problem` e dal piano, e il
    # numero di giri dell'esercizio sta in `laps`, non nel testo.
    for k in DEFECTS:
        h = howto(k, lang)
        for f in _FIELDS:
            text = getattr(h, f)
            assert ":" not in text, (k, f, text)
            assert not re.search(r"\d", text), (k, f, text)


@pytest.mark.parametrize("lang", LANGS)
def test_the_one_thing_at_a_time_rule_is_not_repeated_here(lang):
    # Si dice una volta sola, sopra il piano: qui finirebbe su ogni vista.
    for k in DEFECTS:
        for s in _sentences(howto(k, lang)):
            low = s.lower()
            assert "una cosa alla volta" not in low
            assert "one thing at a time" not in low


def test_no_sentence_is_copied_from_the_old_training_tab():
    # «Mai la stessa frase in due posti»: la scheda Allenamento esiste ancora
    # finché non viene smontata, e lo slogan bocciato non deve sopravvivere qui.
    old = {s for lang in LANGS for v in training._T[lang].values() for s in _split(v)}
    for lang in LANGS:
        for k in DEFECTS:
            for s in _sentences(howto(k, lang)):
                assert s not in old, s
                assert "difendila" not in s and "defend it" not in s


@pytest.mark.parametrize("lang", LANGS)
def test_done_when_sentences_do_not_share_a_skeleton(lang):
    # Sette «È fatto quando in metà dei giri …» di fila sono lo stesso scheletro
    # ripetuto, anche se nessuna frase è identica: le prime due parole e le
    # ultime due devono cambiare da un difetto all'altro.
    words = [howto(k, lang).done_when.rstrip(".").split() for k in DEFECTS]
    heads = [tuple(w[:2]) for w in words]
    assert len(set(heads)) == len(heads), heads
    tails = [tuple(w[-2:]) for w in words]
    assert len(set(tails)) >= len(tails) - 3, tails


# --- tono di tutti i testi --------------------------------------------------

def test_no_emoji_and_no_slogan_colons():
    texts = list(_all_texts())
    assert len(texts) == 2 * (7 * 5 + 4 + 7)
    for text in texts:
        assert not re.search(r"[\U0001F300-\U0001FAFF☀-➿]", text), text
        assert not re.search(r"^[^:]{1,30}:\s", text), text


def test_italian_numbers_use_the_comma():
    assert fmt_s(0.18, "it") == "0,18 s" and fmt_s(0.18, "en") == "0.18 s"
    assert "0,29 s" in problem("brake_early", "Variante Alta", 290, "ms", "it", metres=14)
    for t in _verdicts("it") + _problems("it"):
        assert not re.search(r"\d\.\d", t), t
    for t in _verdicts("en") + _problems("en"):
        assert not re.search(r"\d,\d", t), t


# --- il problema in una frase -----------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
def test_problem_names_the_corner_and_the_cost(lang):
    for k, text in zip(DEFECTS, _problems(lang)):
        # Il nome apre come etichetta («Variante Alta. Qui …»), mai «In <nome>».
        assert text.startswith("Variante Alta. "), text
        assert not text.startswith(("In ", "At ")), text
        assert (" Qui " if lang == "it" else " Here ") in text, text
        assert ("0,60 s" if lang == "it" else "0.60 s") in text if k == "coasting" \
            else ("0,29 s" if lang == "it" else "0.29 s") in text


def test_problem_reads_like_the_approved_model():
    assert problem("brake_early", "Variante Alta", 290, "ms", "it", metres=14) == (
        "Variante Alta. Qui stacchi in media 14 metri prima del tuo giro migliore, "
        "e ci perdi 0,29 s a giro.")
    assert problem("brake_early", "Variante Alta", 290, "ms", "en", metres=14) == (
        "Variante Alta. Here you brake 14 m earlier than your best lap on average, "
        "and it costs you 0.29 s a lap.")


def test_problem_says_the_metres_only_for_the_braking_point():
    assert "14 metri prima" in problem("brake_early", "Ascari", 290, "ms", "it", metres=14)
    assert "14 metri dopo" in problem("brake_late", "Ascari", 290, "ms", "it", metres=14)
    assert "1 metro prima" in problem("brake_early", "Ascari", 290, "ms", "it", metres=1.2)
    assert "metri" not in problem("brake_early", "Ascari", 290, "ms", "it")
    assert "metri" not in problem("min_speed", "Ascari", 290, "ms", "it", metres=14)
    assert "14 m earlier" in problem("brake_early", "Ascari", 290, "ms", "en", metres=14)


@pytest.mark.parametrize("lang", LANGS)
def test_problem_without_a_corner_speaks_of_the_lap(lang):
    # Alzate e veleggio non hanno curve nel consiglio: la frase non può
    # cominciare con «In » seguito dal vuoto.
    for k in DEFECTS:
        text = problem(k, "", 150, "ms", lang)
        assert text[0].isupper() and "  " not in text, text
        assert not text.startswith(("In ", "At ", "Qui ", "Here ")), text


# --- il verdetto ------------------------------------------------------------

def test_verdict_first_session_says_so():
    text = verdict(0.62, _top(), 0.45, None, "it")
    assert "0,62 s" in text and "45%" in text and "«Freni troppo presto»" in text
    assert text.endswith("È la tua prima sessione qui. Il confronto arriva dalla prossima.")


def test_no_verdict_has_a_colon_anywhere():
    # Il regex «a effetto» guarda solo l'inizio del testo e si era lasciato
    # sfuggire «… qui: il confronto …» a metà verdetto.
    for lang in LANGS:
        for text in _verdicts(lang):
            assert ":" not in text, text


def test_verdict_compares_with_the_previous_session():
    better = verdict(0.62, _top(), 0.45, {"gap_delta_s": -0.15, "better": ["brake_early"],
                                          "worse": ["over_brake"]}, "it")
    assert "0,15 s in meno" in better
    assert "«Freni troppo presto» in calo" in better
    assert "«Troppo freno» in crescita" in better
    worse = verdict(0.62, _top(), 0.45, {"gap_delta_s": 0.08, "better": [], "worse": []}, "it")
    assert "0,08 s in più" in worse and "calo" not in worse and "crescita" not in worse
    same = verdict(0.62, _top(), 0.45, {"gap_delta_s": 0.001, "better": [], "worse": []}, "it")
    assert "in meno" not in same and "in più" not in same


def test_verdict_is_at_most_three_sentences():
    for lang in LANGS:
        for text in _verdicts(lang):
            assert 1 <= len(_split(text)) <= 3, text


def test_coasting_is_not_a_share_of_the_lost_time():
    # Il veleggio è in secondi di veleggio, non di perdita: la spec vieta di
    # sommarlo (o di farne una quota) della perdita del verdetto.
    text = verdict(0.40, _top("coasting", 0.6, "s"), 0.3, None, "it")
    assert "%" not in text and "«Veleggi prima di frenare»" in text


def test_verdict_without_a_dominant_defect():
    text = verdict(0.30, None, 0.0, None, "en")
    assert "0.30 s" in text and "“" not in text
