"""The terminal path into the setup writer: show, preview, apply, undo.

This module shipped with the setup foundation and was reachable only as
``python -m accoach.setup.cli`` — an entry point nothing advertised and nothing
tested. It is now a documented ``accoach setup`` command, so the round trip it
performs on a real file gets checked here: a write that lands in the wrong place
or an undo that restores the wrong thing costs a session's setup work.
"""
import json

import pytest

from accoach.setup.cli import main
from tests.test_setup_format import SAMPLE


@pytest.fixture
def setup_file(tmp_path):
    p = tmp_path / "base.json"
    p.write_text(json.dumps(SAMPLE), encoding="utf-8")
    return p


def test_show_prints_the_car_and_its_parameters(setup_file, capsys):
    main(["show", str(setup_file)])
    out = capsys.readouterr().out
    assert "mclaren_720s_gt3_evo" in out
    assert "11" in out                       # rearWing, in clicks


def test_bump_previews_without_writing(setup_file, capsys):
    main(["bump", str(setup_file), "--param", "rearWing", "--clicks", "-1"])
    out = capsys.readouterr().out
    assert "anteprima" in out
    assert list(setup_file.parent.iterdir()) == [setup_file]
    # The source file is untouched, not merely un-copied.
    assert json.loads(setup_file.read_text())["advancedSetup"]["aeroBalance"]["rearWing"] == 11


def test_bump_apply_writes_a_new_file_and_leaves_the_original(setup_file, capsys):
    main(["bump", str(setup_file), "--param", "rearWing", "--clicks", "-1",
          "--apply", "--as", "ACCoach_test"])
    out = capsys.readouterr().out
    written = setup_file.parent / "ACCoach_test.json"
    assert written.exists() and str(written) in out
    assert json.loads(written.read_text())["advancedSetup"]["aeroBalance"]["rearWing"] == 10
    assert json.loads(setup_file.read_text())["advancedSetup"]["aeroBalance"]["rearWing"] == 11


def test_undo_restores_the_previous_version(setup_file, capsys):
    """The two writes must differ, or 'restored' and 'never changed' look alike.

    Each ``bump`` re-reads the *original*, so writing -1 twice would produce the
    same 10 both times and this test would pass without undo doing anything.
    """
    dest = "ACCoach_test"
    for clicks in ("-1", "-2"):              # 11 -> 10, then 11 -> 9
        main(["bump", str(setup_file), "--param", "rearWing", "--clicks", clicks,
              "--apply", "--as", dest, "--overwrite"])
    written = setup_file.parent / f"{dest}.json"
    wing = json.loads(written.read_text())["advancedSetup"]["aeroBalance"]["rearWing"]
    assert wing == 9
    capsys.readouterr()

    main(["undo", str(written)])
    assert "Ripristinato" in capsys.readouterr().out
    assert json.loads(written.read_text())["advancedSetup"]["aeroBalance"]["rearWing"] == 10


def test_a_per_wheel_parameter_demands_a_slot(setup_file):
    """Without it, 'lower the pressure' would silently pick a corner for you."""
    with pytest.raises(SystemExit, match="slot"):
        main(["bump", str(setup_file), "--param", "tyrePressure", "--clicks", "+2"])


def test_the_italian_slot_spelling_still_resolves(setup_file, capsys):
    """`canonical_slot` exists to keep the pre-i18n spellings working."""
    main(["bump", str(setup_file), "--param", "tyrePressure", "--slot", "Post-Dx",
          "--clicks", "+2"])
    assert "anteprima" in capsys.readouterr().out


def test_an_unknown_parameter_lists_the_real_ones(setup_file):
    with pytest.raises(SystemExit, match="rearWing"):
        main(["bump", str(setup_file), "--param", "nonesiste", "--clicks", "+1"])
