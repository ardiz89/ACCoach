"""i18n: language setting + spoken-cue translation (Italian source -> English)."""
import pytest

from accoach import config, i18n


@pytest.fixture(autouse=True)
def _reset_config_cache():
    config._cache = None
    yield
    config._cache = None


def test_cue_text_translates_static_to_english():
    assert i18n.cue_text("Bloccaggio, alleggerisci il freno", "en") == \
        "Lock-up — ease off the brake"
    # Italian is the source: asking for Italian returns it unchanged.
    assert i18n.cue_text("Bloccaggio, alleggerisci il freno", "it") == \
        "Bloccaggio, alleggerisci il freno"


def test_cue_text_translates_numeric_templates():
    assert i18n.cue_text("Stai perdendo 3 decimi qui", "en") == "Losing 3 tenths here"
    assert i18n.cue_text("Benzina per circa 2 giri.", "en") == "Fuel for about 2 laps."


def test_cue_text_translates_advisor_aids():
    assert i18n.cue_text(
        "Pattini in uscita in più punti del giro: prova ad alzare il TC (dal 4 al 5).",
        "en") == "Spinning up on exit in several places: try raising the TC (from 4 to 5)."
    assert i18n.cue_text(
        "Blocchi l'anteriore in più curve: prova ad alzare l'ABS.", "en") == \
        "Locking the fronts in several corners: try raising the ABS."


def test_cue_text_translates_pressure_and_temp():
    assert i18n.cue_text(
        "Gomme anteriori a 29.5 psi, troppo alte: cala circa 2.0 psi a freddo.",
        "en") == "Front tyres at 29.5 psi, too high: drop about 2.0 psi cold."
    assert i18n.cue_text(
        "Gomme fredde (60°C): puoi spingere di più per portarle in temperatura.",
        "en") == "Tyres cold (60°C): push harder to bring them up to temperature."


def test_cue_text_unknown_passes_through():
    assert i18n.cue_text("frase sconosciuta", "en") == "frase sconosciuta"


def test_t_translates_ui_chrome():
    assert i18n.t("overlay.waiting", "en") == "waiting for the game…"
    assert i18n.t("overlay.waiting", "it") == "in attesa del gioco…"
    assert i18n.t("lbl.best", "it") == "Migliore"


def test_t_unknown_key_falls_back_to_key():
    assert i18n.t("nope.nope", "en") == "nope.nope"


def test_current_language_defaults_to_en(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    config.load_config(reload=True)
    assert i18n.current_language() == "en"


def test_save_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    cfg = config.load_config(reload=True)
    cfg.voice.enabled = False
    cfg.voice.rate = 200
    cfg.overlay.scale = 1.3
    cfg.overlay.x, cfg.overlay.y = 120, 80
    cfg.lan = True
    config.save_config(cfg)
    fresh = config.load_config(reload=True)
    assert fresh.voice.enabled is False
    assert fresh.voice.rate == 200
    assert fresh.overlay.scale == 1.3
    assert fresh.overlay.x == 120 and fresh.overlay.y == 80
    assert fresh.lan is True
    assert fresh.bind_host() == "0.0.0.0"


def test_set_language_persists_and_switches(tmp_path, monkeypatch):
    cfgfile = tmp_path / "config.toml"
    monkeypatch.setattr(config, "config_path", lambda: cfgfile)
    config.load_config(reload=True)
    config.set_language("it")
    assert i18n.current_language() == "it"                 # cache updated
    assert 'language = "it"' in cfgfile.read_text(encoding="utf-8")  # persisted
    # …and a fresh load from disk keeps it.
    config.load_config(reload=True)
    assert config.load_config().language == "it"


# --- «1 decimi» -----------------------------------------------------------
#
# Il plurale era fisso, e non su un caso di bordo: il coach parla da 120 ms in
# su, quindi tutto quello che sta fra 120 e 149 ms si arrotonda a uno. La frase
# piu' piccola che dice, e quella che dice piu' spesso, era sgrammaticata — in
# entrambe le lingue, perche' anche la traduzione diceva «1 tenths».

def test_one_tenth_is_singular_in_both_languages():
    from accoach.coaching.analyzer import CornerStats, classify_corner

    st = CornerStats(lost_ms=130.0, throttle_live=1.0, throttle_ref=1.0,
                     brake_live=0.0, brake_ref=0.0, min_speed_live=100.0,
                     min_speed_ref=100.0, braking_early=False, braking_late=False)
    it = classify_corner(st, 0, 0.3).message
    assert "1 decimo " in it and "decimi" not in it
    assert i18n.cue_text(it, "en") == "Losing 1 tenth here"


def test_more_than_one_tenth_stays_plural():
    from accoach.coaching.analyzer import CornerStats, classify_corner

    st = CornerStats(lost_ms=320.0, throttle_live=1.0, throttle_ref=1.0,
                     brake_live=0.0, brake_ref=0.0, min_speed_live=100.0,
                     min_speed_ref=100.0, braking_early=False, braking_late=False)
    it = classify_corner(st, 0, 0.3).message
    assert "3 decimi " in it
    assert i18n.cue_text(it, "en") == "Losing 3 tenths here"


def test_the_last_lap_but_one_of_fuel_is_singular_and_translated():
    """`fuel.py` il singolare lo diceva gia' — ma la tabella di traduzione
    conosceva solo il plurale, quindi «Benzina per circa 1 giro.» arrivava in
    italiano a un utente inglese."""
    assert i18n.cue_text("Benzina per circa 1 giro.", "en") == "Fuel for about 1 lap."
    assert i18n.cue_text("Benzina per circa 3 giri.", "en") == "Fuel for about 3 laps."
