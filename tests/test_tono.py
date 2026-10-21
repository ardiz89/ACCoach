"""Il tono dei testi dell'app, come proprietà che si controlla.

Il pilota ha bocciato il testo «da macchina»: frasi lunghe, slogan, due punti a
effetto, emoji, la stessa frase in più posti, numeri col punto. `tests/tono.py`
contiene le regole e raccoglie i testi di ogni superficie; qui:

* ogni regola ha il suo esempio, positivo e negativo;
* il raccoglitore prova di vedere davvero i testi (su file finti e sui veri), e
  non ci si accorge di una superficie vuota solo quando è tardi;
* le superfici *fuori* da `tono.PENDING` non hanno nessuna violazione, i loro
  segnaposti sono gli stessi in italiano e in inglese, e nessuna frase sta in due
  chiavi. Ogni task di riscrittura toglie la sua superficie da `PENDING`.

`PENDING` vuol dire «non ancora riscritta»: le sue violazioni si contano
(`python tests/tono.py`) ma non fanno fallire nulla.
"""
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tono  # noqa: E402


def broken(text, lang="it"):
    return tono.violations(text, lang)


# --- le regole: un esempio che passa e uno che no ---------------------------

def test_emoji_and_pictographic_symbols_are_refused():
    assert broken("📊  Analisi e report") == ["emoji"]
    assert "emoji" in broken("▶  Avvia")
    assert "emoji" in broken("✓ Fatto") and "emoji" in broken("⚡ Veloce")
    assert broken("Analisi e report") == []
    assert broken("Dal giro 3 → 4") == []          # una freccia non è un'emoji


def test_a_colon_is_refused_everywhere_but_times_ratios_and_placeholders():
    assert broken("Obiettivo: sotto 1:47.427") == ["colon"]
    assert broken("Curve:") == ["colon"]
    assert broken("Nota a metà frase: così no.") == ["colon"]
    assert broken("Il giro è 1:47.427 e alle 22:58 sei in pista.") == []
    assert broken("Il rapporto è 3:1.") == []
    assert broken("L'obiettivo è stare sotto {v:.2f} a giro.") == []
    assert broken("Apri http://localhost:8000 dal tablet.") == []
    assert broken("Il consiglio: tieni il gas.", "en") == ["colon"]


def test_a_dash_for_emphasis_is_refused_but_not_between_two_values():
    assert broken("Qui perdi {s} s — più che in ogni altro punto.") == ["dash"]
    assert "dash" in broken("Frena prima – poi gira.")
    assert "dash" in broken("Frena prima - poi gira.")
    assert broken("Fra 22 °C — 30 °C sei in finestra.") == []
    assert broken("Fra 22 – 30 psi.") == []
    assert broken("Un nome-composto e un lock-up.") == []
    assert broken("—") == []                      # una cella vuota non è una frase


def test_an_exclamation_mark_is_refused():
    assert broken("Bella sessione!") == ["bang"]
    assert broken("Bella sessione.") == []
    assert broken("Great session!", "en") == ["bang"]


def test_a_sentence_over_the_word_limit_is_refused():
    ok = " ".join(["parola"] * 25) + "."
    too_long = " ".join(["parola"] * 26) + "."
    assert broken(ok) == [] and broken(too_long) == ["long"]
    # Il limite è per frase, non per testo: tre frasi da venti parole vanno bene.
    assert broken(" ".join([" ".join(["parola"] * 20) + "."] * 3)) == []
    # Un limite più stretto, quello della voce.
    assert tono.violations("Frena molto prima della curva lenta di destra.", "it", 8) == []
    assert tono.violations("Frena molto prima della curva lenta di destra, adesso.",
                           "it", 8) == ["long"]
    # I marcatori HTML non sono parole.
    assert broken("<b>" + " ".join(["parola"] * 25) + "</b>") == []


def test_the_decimal_comma_is_required_in_italian_only():
    assert broken("Perdi 0.18 s qui.") == ["decimal"]
    assert broken("Perdi 0,18 s qui.") == []
    assert broken("You lose 0.18 s here.", "en") == []
    assert broken("You lose 0,18 s here.", "en") == ["decimal"]
    # I tempi sul giro e le versioni non sono decimali.
    assert broken("Il tuo giro è 1:47.427.") == []
    assert broken("Serve Python 3.11 o la versione 1.2.3.") == []
    assert broken("Sei a 1,000 giri.", "en") == []         # le migliaia in inglese


def test_the_unit_is_one_space_from_its_number():
    assert broken("Perdi 0,18s qui.") == ["unit"]
    assert broken("Perdi 0,18 s qui.") == []
    assert "unit" in broken("Il {thr}% del gas")            # il segnaposto vale un numero
    assert broken("Il {thr} % del gas") == []
    assert "unit" in broken("Vai a 165km/h") and "unit" in broken("Sono 22°C")
    assert "unit" in broken("{secs}s di ritardo")
    assert broken("Sono 22 °C e 165 km/h.") == []
    assert broken("Il giro 3 e la 2a marcia.") == []        # «3», «2a» non sono unità
    assert broken("Metti lap{s} qui", "en") == []            # un segnaposto di plurale


def test_the_slogans_are_refused_in_both_languages():
    assert broken("bella costanza!") == ["bang", "slogan"]
    assert broken("Continua così.") == ["slogan"]
    assert broken("Scopri i tuoi limiti.") == ["slogan"]
    assert broken("You're all set.", "en") == ["slogan"]
    assert broken("Keep it up", "en") == ["slogan"]
    assert broken("Discover your limits.", "en") == ["slogan"]
    assert broken("Il giro è stato scoperto.") == []
    assert broken("Sei pronto a partire.") == ["slogan"]


def test_every_rule_can_be_hit_and_the_text_with_nothing_wrong_is_clean():
    assert set(tono.RULES) == {"emoji", "colon", "dash", "bang", "long",
                               "decimal", "unit", "slogan"}
    assert broken("Questi sono giri di prova, non i tuoi.") == []
    assert broken("") == [] and broken("   ") == []


def test_placeholders_are_names_without_their_format():
    assert tono.placeholders("Sotto {v:.2f} per {secs} s e {n!r}") == {"v", "secs", "n"}
    assert tono.placeholders("niente") == set()
    # La sintassi del plurale ha lo stesso nome nelle due lingue.
    assert tono.placeholders("{laps|giro|giri}") == tono.placeholders("{laps|lap|laps}") == {"laps"}


# --- il raccoglitore --------------------------------------------------------

def test_lang_pairs_finds_flat_and_nested_it_en_tables(tmp_path):
    mod = tmp_path / "m.py"
    mod.write_text(textwrap.dedent('''
        A = {"it": "Ciao {n}", "en": "Hi {n}"}
        B = {"it": {"x": "Uno", "y": "Due"}, "en": {"x": "One"}}
        C = {"it": "Solo italiano"}
        D = {"it": f"Giro {n}", "en": "Lap " + "{n}"}
    '''), encoding="utf-8")
    # La chiave è «file:riga» più la sottochiave.
    got = {k.rsplit(":", 1)[1]: v for k, v in tono.lang_pairs(mod).items()}
    assert got["2"] == {"it": "Ciao {n}", "en": "Hi {n}"}
    assert got["3[x]"] == {"it": "Uno", "en": "One"}
    assert got["3[y]"] == {"it": "Due"}
    assert "4" not in got                                   # senza «en» non è una coppia
    assert got["5"] == {"it": "Giro {n}", "en": "Lap {n}"}


def test_static_cue_texts_see_only_calls_that_take_a_cue_category(tmp_path):
    mod = tmp_path / "c.py"
    mod.write_text(textwrap.dedent('''
        def f(self):
            a = Cue(CueCategory.BRAKE, "Frena prima della curva")
            b = self._make(1, CueCategory.GAS, "Più gas qui")
            c = other("Una stringa qualsiasi")
            d = Cue(CueCategory.GAS, f"Benzina per circa {n} giri")
            msg = f"Gomme a {psi} psi, troppo alte"
            e = Cue(CueCategory.GAS, msg)
    '''), encoding="utf-8")
    assert tono.static_cue_texts(mod) == {
        "Frena prima della curva", "Più gas qui", "Benzina per circa {n} giri",
        "Gomme a {psi} psi, troppo alte"}


def test_markdown_sentences_skip_code_and_keep_prose():
    src = textwrap.dedent('''
        # 1. Titolo della guida

        Una frase **in grassetto** con `codice` e un [link](http://x.y/z).
        Continua sulla riga dopo.

        ```
        pip install -r requirements.txt: non è prosa
        ```

        - Una voce di elenco
        | Colonna | Altra |
        |---|---|
        | cella uno | cella due |
    ''')
    got = [t for _, t in tono.markdown_sentences(src)]
    assert "1. Titolo della guida" in got or "Titolo della guida" in got
    assert "Una frase in grassetto con e un link. Continua sulla riga dopo." in got
    assert "Una voce di elenco" in got and "cella uno" in got and "cella due" in got
    assert not any("pip install" in t for t in got)


def test_the_report_catalogue_is_read_in_full_with_its_multiline_entries():
    cat = tono.i18n_catalogue()
    assert len(cat) > 400
    assert all(set(v) == {"it", "en"} for v in cat.values()), \
        [k for k, v in cat.items() if set(v) != {"it", "en"}][:5]
    assert "sample laps" in cat["demo.banner"]["en"]
    # Una voce scritta su due righe.
    assert cat["tour.e6.x"]["en"].startswith("A dial you turn on the straight")
    assert cat["tour.e6.x"]["it"].startswith("Una manopola che giri")


def test_the_engineer_page_keys_are_not_in_the_report():
    report = {**tono.SURFACES["report_a"](), **tono.SURFACES["report_b"]()}
    engineer = tono.SURFACES["engineer"]()
    assert "web/i18n.js:tour.e6.t" in engineer and "web/i18n.js:tour.e6.t" not in report
    assert "web/i18n.js:demo.banner" in report and "web/i18n.js:demo.banner" not in engineer
    assert "web/i18n.js:tour.a1.t" in report
    # Una chiave chiesta solo dentro un modello di engineer.js
    # (`${t("eng.click")}`) è della pagina Ingegnere, non del report.
    assert "web/i18n.js:eng.click" in engineer and "web/i18n.js:eng.click" not in report
    # Più i dizionari del pacchetto engineer e la tabella dei rimedi.
    assert any("engineer/core.py" in k for k in engineer)
    assert any("profiles/_common.py" in k for k in engineer)


def test_the_report_is_split_in_two_without_losing_a_key():
    a, b = tono.SURFACES["report_a"](), tono.SURFACES["report_b"]()
    assert not set(a) & set(b)
    eng = tono._engineer_keys()
    every = {f"web/i18n.js:{k}" for k in tono.i18n_catalogue() if k not in eng}
    assert set(a) | set(b) == every
    assert any(k.startswith("web/i18n.js:pag.") for k in a)
    assert "web/i18n.js:demo.banner" in a and not any(k.startswith("web/i18n.js:pag.") for k in b)


def test_every_surface_collects_texts_in_both_languages():
    floor = {"report_a": 220, "report_b": 200, "engineer": 200, "report_backend": 200, "hub": 130,
             "coach": 40, "guide": 400}
    for name, fn in tono.SURFACES.items():
        entries = fn()
        assert len(entries) >= floor[name], (name, len(entries))
        if name == "guide":
            langs = {lg for e in entries.values() for lg in e}
            assert langs >= {"it", "en"}
            continue
        both = [e for e in entries.values() if "it" in e and "en" in e]
        assert len(both) >= 0.9 * len(entries), name


def test_each_surface_has_its_own_sources():
    s = {n: " ".join(f()) for n, f in tono.SURFACES.items()}
    for src in ("debrief.py", "trajectory.py", "training.py", "howto.py", "api.py"):
        assert src in s["report_backend"], src
    assert "_UI[overlay.waiting]" in s["hub"]
    for src in ("cue.py", "focus.py", "_CUE_EN"):
        assert src in s["coach"], src
    # Le frasi di pitcall.py stanno già nella tabella inglese e portano la sua chiave.
    assert "_CUE_EN[Ingresso box qui davanti, rientra]" in s["coach"]
    coach = tono.SURFACES["coach"]()
    assert coach["i18n.py:_CUE_EN[Ingresso box qui davanti, rientra]"]["en"] == "Pit entry just ahead — come in"
    # Le frasi fisse di tutti i moduli del coach, non solo dei quattro nominati:
    assert any(v.get("it") == "Gas a metà troppo a lungo: aspetta e poi apri tutto"
               and "braking.py" in k for k, v in coach.items())
    assert any(v.get("it") == "Frena prima" and "analyzer.py" in k for k, v in coach.items())
    assert "GUIDA.md" in s["guide"] and "FAQ.md" in s["guide"]
    assert "guide.py:" in s["guide"]          # i testi fissi della pagina della guida
    # Nessuna chiave in due superfici.
    keys = {n: set(f()) for n, f in tono.SURFACES.items()}
    names = list(keys)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            assert not (keys[a] & keys[b]), (a, b)


def test_the_coach_is_measured_with_the_voice_limit():
    assert tono.MAX_WORDS_BY_SURFACE["coach"] == 8 and tono.MAX_WORDS == 25
    entries = {"k": {"it": "Frena molto prima della curva lenta di destra adesso."}}
    assert tono.surface_violations("coach", entries) == [("k", "it", "long")]
    assert tono.surface_violations("report", entries) == []


# --- la verifica di una superficie, provata su superfici finte --------------

def test_surface_checks_catch_what_they_promise_to_catch():
    dirty = {"a": {"it": "Obiettivo: sotto {v}", "en": "Target: under {w}"}}
    assert tono.surface_violations("x", dirty) == [("a", "it", "colon"), ("a", "en", "colon")]
    assert tono.placeholder_mismatches(dirty) == ["a"]
    clean = {"a": {"it": "L'obiettivo è stare sotto {v}.", "en": "Stay under {v}."}}
    assert tono.surface_violations("x", clean) == [] and tono.placeholder_mismatches(clean) == []
    # Una voce con una sola lingua non si confronta con l'altra.
    assert tono.placeholder_mismatches({"a": {"it": "Ciao {n}"}}) == []


def test_duplicates_are_found_per_language_between_keys_and_surfaces():
    one = {"a": {"it": "Tieni il gas fino alla corda.", "en": "Hold the throttle to the apex."}}
    two = {"b": {"it": "Un testo del tutto diverso, qui.", "en": "Something else entirely here now."},
           "c": {"it": "Poi tieni il gas fino alla corda.", "en": "Hold the throttle to the apex"}}
    dups = tono.duplicates({"s1": one, "s2": two})
    assert list(dups) == [("en", "hold the throttle to the apex")]
    assert dups[("en", "hold the throttle to the apex")] == ["s1|a", "s2|c"]
    # La stessa frase due volte nello stesso testo non è un doppione fra chiavi.
    same = {"a": {"it": "Tieni il gas fino alla corda. Tieni il gas fino alla corda."}}
    assert tono.duplicates({"s": same}) == {}
    # Le etichette corte non contano.
    assert tono.duplicates({"s": {"a": {"it": "Giro"}, "b": {"it": "Giro"}}}) == {}
    # Cambiare lingua non fa un doppione.
    assert tono.duplicates({"s": {"a": {"it": "Hold the throttle to the apex."},
                                  "b": {"en": "Hold the throttle to the apex."}}}) == {}


# --- il controllo vero, superficie per superficie ---------------------------

def test_pending_names_only_known_surfaces():
    assert tono.PENDING <= set(tono.SURFACES), tono.PENDING - set(tono.SURFACES)


@pytest.mark.parametrize("name", sorted(tono.SURFACES))
def test_a_rewritten_surface_has_no_violations_and_matching_placeholders(name):
    if name in tono.PENDING:
        pytest.skip(f"{name}: ancora da riscrivere")
    entries = tono.SURFACES[name]()
    found = tono.surface_violations(name, entries)
    assert not found, found[:20]
    assert not tono.placeholder_mismatches(entries), tono.placeholder_mismatches(entries)[:20]


def test_no_sentence_is_repeated_among_the_rewritten_surfaces():
    done = {n: f() for n, f in tono.SURFACES.items() if n not in tono.PENDING}
    dups = tono.duplicates(done)
    assert not dups, list(dups.items())[:10]


# --- le correzioni del primo giro di revisione ------------------------------

def test_more_emoji_blocks_are_refused_but_arrows_stay():
    for ch in ("⏸", "⏱", "⌚", "ℹ"):
        assert "emoji" in broken(f"{ch} Pausa"), ch
    assert broken("Dal giro 3 → 4 ← 2") == []


def test_ordinals_thousands_and_sector_times_are_not_violations():
    assert broken("Il 2° giro e il 95° percentile.") == []
    assert "unit" in broken("Sono 22° e 3°")      # un grado nudo a fine frase resta unità
    assert broken("Sei a 12.000 giri.") == []
    assert broken("Il tuo S1 è 34.512 oggi.") == []
    assert broken("Perdi 0.181 s qui.") == ["decimal"]


def test_more_units_need_their_space():
    for text in ("a 3000rpm", "20mm", "5cm", "300Nm", "200kW", "120mph", "220kPa"):
        assert "unit" in broken(text), text
    for text in ("a 3000 rpm", "20 mm", "300 Nm", "220 kPa"):
        assert broken(text) == [], text


def test_the_dash_between_values_needs_bare_values_on_both_sides():
    assert broken("Curva 3 — 4 decimi persi") == ["dash"]
    assert broken("Fra 22 °C — 30 °C sei in finestra.") == []
    assert broken("Fra 22 — 30.") == []
    assert broken("Il 3 — è tardi") == ["dash"]


def test_branches_on_the_language_are_collected_in_pairs(tmp_path):
    mod = tmp_path / "b.py"
    mod.write_text(textwrap.dedent('''
        def why(lang, n):
            if lang == "it":
                axis = "anteriore" if n else "posteriore"
                why = f"Pressione {axis} fuori finestra: {n} click"
                why += " il massimo per sosta"
                return why
            else:
                why = f"Pressure out of window: {n} clicks"
                why += " the most per stop"
                return why

        def note():
            if current_language() == "it":
                return "Non so che auto è."
            return "I don't know the car."

        def pick(lang):
            return "Curva" if lang == "it" else "Corner"
    '''), encoding="utf-8")
    got = tono.lang_pairs(mod)
    flat = {k.split(":", 1)[1]: v for k, v in got.items()}
    assert flat["3@0"] == {"it": "Pressione {axis} fuori finestra: {n} click",
                           "en": "Pressure out of window: {n} clicks"}
    assert flat["3@1"] == {"it": " il massimo per sosta", "en": " the most per stop"}
    assert {"it": "Curva", "en": "Corner"} in flat.values()
    # Un ramo senza `else` esplicito: l'inglese è il testo che segue; qui resta solo l'italiano.
    assert {"it": "Non so che auto è."} in flat.values()


def test_the_real_engineer_branches_are_collected():
    engineer = tono.SURFACES["engineer"]()
    pair = [e for k, e in engineer.items()
            if "profiles/_common.py" in k and e.get("it", "").startswith("Pressione {axis} fuori finestra")]
    assert pair and pair[0]["en"].endswith("{sign}{clicks} clicks")
    # Le espressioni di un'f-string («{ax.capitalize()}» contro «{axis}») non sono
    # confrontabili per nome: le coppie dei rami non si confrontano sui segnaposti.
    assert tono.placeholder_mismatches(engineer) == [
        k for k, e in engineer.items() if "@" not in k and "it" in e and "en" in e
        and tono.placeholders(e["it"]) != tono.placeholders(e["en"])]
    assert tono.placeholder_mismatches({"a@0": {"it": "{x}", "en": "{y}"}}) == []
    assert tono.placeholder_mismatches({"a:0": {"it": "{x}", "en": "{y}"}}) == ["a:0"]


def test_fstring_cues_get_an_english_side_from_the_patterns():
    assert tono.cue_english("Benzina per circa {thresh} giri.") == "Fuel for about {thresh} laps."
    assert tono.cue_english("Una frase mai tradotta {x}") == "Una frase mai tradotta {x}"
    coach = tono.SURFACES["coach"]()
    fuel = [k for k, e in coach.items() if "fuel.py" in k and e["it"].startswith("Benzina per circa")]
    assert fuel and "{laps_left}" in coach[fuel[0]]["it"]


def test_the_guide_may_repeat_a_ui_label_but_not_itself():
    ui = {"a": {"it": "Apri la pagina Ingegnere nel browser."}}
    guide = {"g1": {"it": "Apri la pagina Ingegnere nel browser."}}
    assert tono.duplicates({"hub": ui, "guide": guide}) == {}
    both = {"g1": guide["g1"], "g2": guide["g1"]}
    assert list(tono.duplicates({"hub": ui, "guide": both}).values()) == [["guide|g1", "guide|g2"]]
    assert tono.duplicates({"hub": ui, "report": {"r": ui["a"]}})


def test_keys_asked_inside_a_template_are_found(tmp_path, monkeypatch):
    """`${t("…")}` e `${tf("…", …)}` stanno dentro un letterale col backtick:
    senza cercarli come argomenti, la chiave finisce nella superficie sbagliata."""
    (tmp_path / "x.js").write_text(
        'el.innerHTML = `<b>${t("a.one")}</b> ${tf("a.two", { n: 1 })}`;', encoding="utf-8")
    monkeypatch.setattr(tono, "WEB", tmp_path)
    assert {"a.one", "a.two"} <= tono._literals("x.js")
