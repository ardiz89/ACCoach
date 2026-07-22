"""Importare un riferimento PRO senza passare dalla riga di comando.

Il meccanismo c'era da tempo: `python -m accoach import-reference <file>`. Non
c'era nessun bottone, né nell'hub né nella web app — quindi il livello "PRO"
della scala di confronto era di fatto irraggiungibile, e chi è a tre secondi dal
passo si allenava contro il proprio giro a tre secondi dal passo, misurando ogni
perdita su una traiettoria sbagliata.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from accoach.i18n import t                                    # noqa: E402
from accoach.recording.storage import load_lap, save_lap      # noqa: E402

import synth                                                  # noqa: E402


def _imported(lap):
    """Lo stesso trattamento che applica il bottone."""
    lap.valid = True
    lap.clean = True
    lap.source = "pro"
    lap.recorded_utc = ""
    return lap


def test_an_imported_lap_is_marked_as_a_pro_benchmark(tmp_path):
    lap = _imported(synth.build_lap())
    back = load_lap(save_lap(lap, tmp_path))
    assert back.source == "pro"
    assert back.valid and back.clean is True


def test_an_imported_lap_becomes_the_reference_when_it_is_faster(tmp_path):
    from accoach.recording.storage import find_reference_lap

    mine = synth.build_lap()
    mine.lap_time_ms = 105_000
    mine.recorded_utc = "2026-07-20T09:00:00+00:00"
    save_lap(mine, tmp_path)

    pro = _imported(synth.build_lap())
    pro.lap_time_ms = 99_000
    save_lap(pro, tmp_path)

    ref = find_reference_lap("ferrari_488_gt3", "monza", tmp_path)
    assert ref is not None and ref.lap_time_ms == 99_000
    assert ref.source == "pro"


def test_a_slower_imported_lap_does_not_displace_your_best(tmp_path):
    """Importare non deve peggiorare il bersaglio: PRO non è un grado militare."""
    from accoach.recording.storage import find_reference_lap

    mine = synth.build_lap()
    mine.lap_time_ms = 99_000
    mine.clean = True          # come lo registra il recorder di oggi
    mine.recorded_utc = "2026-07-20T09:00:00+00:00"
    save_lap(mine, tmp_path)

    pro = _imported(synth.build_lap())
    pro.lap_time_ms = 105_000
    save_lap(pro, tmp_path)

    ref = find_reference_lap("ferrari_488_gt3", "monza", tmp_path)
    assert ref is not None and ref.lap_time_ms == 99_000


def test_the_button_and_its_explanation_exist_in_both_languages():
    for lang in ("en", "it"):
        assert t("btn.import_pro", lang=lang) != "btn.import_pro"
        hint = t("import.hint", lang=lang)
        assert hint != "import.hint" and len(hint) > 40


def test_a_failed_import_says_why():
    """Un import che fallisce in silenzio è come il pilota finisce a chiedersi
    perché il riferimento non è mai cambiato."""
    msg = t("import.failed", lang="it").format(err="file troncato")
    assert "file troncato" in msg


def test_the_import_button_stays_usable_while_coach_live_runs():
    """Non spawna processi e non tocca la telemetria: non c'è ragione di
    disabilitarlo, e disabilitarlo senza motivo si legge come un guasto."""
    from accoach.launcher import _IMPORT_PRO, _LIVE_SAFE_KEYS

    assert _IMPORT_PRO in _LIVE_SAFE_KEYS
