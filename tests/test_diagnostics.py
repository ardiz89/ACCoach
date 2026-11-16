"""Diagnostics formatting/verdict helpers (the live loops aren't unit-tested)."""
from dataclasses import replace

from accoach.diagnostics import _live_line, _sectors_verdict, _yaw_verdict
from accoach.telemetry.snapshot import TelemetrySnapshot


def test_live_line_formats_without_error():
    s = replace(
        TelemetrySnapshot.disconnected(),
        connected=True, speed_kmh=212.4, gear="5", rpm=7200, max_rpm=8000,
        throttle=1.0, brake=0.0, steer_angle=-0.18, yaw_rate=0.42,
        slip_ratio=(-0.30, -0.10, 0.05, 0.20),
        abs_active=0.0, tc_active=0.3, tc_level=4, abs_level=3, brake_bias=0.61,
    )
    line = _live_line(s)
    assert "212" in line and "0.61" in line
    assert " 4  3" in line          # tc_level / abs_level columns


def test_live_line_handles_unknown_aids():
    s = replace(TelemetrySnapshot.disconnected(), connected=True,
                max_rpm=0, tc_level=-1, abs_level=-1, brake_bias=-1.0)
    line = _live_line(s)            # must not raise on -1 / zero max_rpm
    assert "--" in line             # brake bias shown as placeholder


def test_yaw_verdict_runs(capsys):
    # Just exercise each branch; it prints, returns None.
    _yaw_verdict(agree=90, disagree=5, left_seen=40, right_seen=55)
    assert "CORRECT" in capsys.readouterr().out
    _yaw_verdict(agree=5, disagree=90, left_seen=40, right_seen=55)
    assert "_YAW_SIGN = -1.0" in capsys.readouterr().out
    _yaw_verdict(agree=2, disagree=2, left_seen=2, right_seen=2)
    assert "not enough" in capsys.readouterr().out


def test_sectors_verdict_runs(capsys):
    # All three sectors seen, count matches -> confirmed.
    _sectors_verdict({"count": 3, "seen": {0, 1, 2}, "valid": 900,
                      "bounds": {1: 0.31, 2: 0.66}, "prev": 2})
    assert "✓" in capsys.readouterr().out
    # current_sector never read -> offset wrong.
    _sectors_verdict({"count": 0, "seen": set(), "valid": 0,
                      "bounds": {}, "prev": None})
    assert "sempre -1" in capsys.readouterr().out
    # Indices read but sector_count is 0 -> works via transitions.
    _sectors_verdict({"count": 0, "seen": {0, 1, 2}, "valid": 500,
                      "bounds": {1: 0.3, 2: 0.6}, "prev": 2})
    assert "sector_count è 0" in capsys.readouterr().out


def test_il_self_test_parla_con_la_voce_del_config(monkeypatch, tmp_path):
    """La prova della voce usa la voce scelta, come `live`: prima costruiva
    `Voice(enabled=True)` e parlava femminile anche col config su maschile."""
    from accoach import config, diagnostics
    import accoach.coaching as coaching

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("[voice]\nmale = true\nradio = false\nrate = 150\n", encoding="utf-8")
    monkeypatch.setattr(config, "config_path", lambda: cfg_file)
    config.load_config(reload=True)

    built = {}

    class _Finta:
        is_audio = False
        _prerendered: dict = {}
        _engine = None

        def __init__(self, **kw):
            built.update(kw)

        def say(self, _text):
            pass

        def close(self):
            pass

    monkeypatch.setattr(coaching, "Voice", _Finta)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    diagnostics.run_selftest(str(tmp_path / "report.json"))
    assert built["male"] is True
    assert built["radio"] is False
    assert built["rate"] == 150


def test_setup_lines_show_each_file_against_the_car():
    from accoach.diagnostics import setup_lines
    from accoach.engineer.fingerprint import FileValues

    s = replace(
        TelemetrySnapshot.disconnected(), connected=True, in_pit=True,
        speed_kmh=0.0, tc_level=3, abs_level=2, engine_map=1, brake_bias=0.58,
        tyre_pressure=(26.5, 26.5, 26.0, 26.0), fuel=40.0, air_temp=21.0,
        road_temp=27.0, car_model="mclaren_720s_gt3", track="imola")
    hone8 = FileValues("HONE_8", "x/HONE_8.json", 3, 2, 1, 15,
                       (26.5, 26.5, 26.0, 26.0), 40)
    hone7 = FileValues("HONE_7", "x/HONE_7.json", 4, 2, 1, 15,
                       (25.7, 25.7, 26.0, 26.0), 40)
    lines = setup_lines(s, [hone8, hone7])
    text = "\n".join(lines)
    assert any("HONE_8" in ln for ln in lines)
    assert any("HONE_7" in ln for ln in lines)
    assert "+0.8" in text and "+0.0" in text      # anteriori contro HONE_7 / HONE_8
    assert "TC" in text and "0.58" in text and "15" in text
    seven = text[text.index("HONE_7"):]
    assert "TC letto 3 file 4" in seven            # differenza certa sul TC
    assert "nessuna" in text[:text.index("HONE_7")]  # HONE_8 combacia


def test_setup_lines_see_the_acc_box_and_say_the_map_as_the_hud():
    """Su ACC fermo in piazzola `in_pit` e' 0: il box e' la corsia a velocita'
    zero (`stopped_in_box`). La mappa grezza accanto a quella dell'HUD, e le
    temperature interne delle gomme per sapere se le pressioni sono a freddo."""
    from accoach.diagnostics import setup_lines
    from accoach.engineer.fingerprint import FileValues

    s = replace(
        TelemetrySnapshot.disconnected(), connected=True, in_pit=False,
        in_pit_lane=True, speed_kmh=0.0, tc_level=3, abs_level=2, engine_map=0,
        brake_bias=0.58, tyre_pressure=(26.5, 26.5, 26.0, 26.0),
        tyre_core_temp=(24.0, 24.5, 23.0, 23.5), fuel=40.0, air_temp=21.0,
        road_temp=27.0, car_model="mclaren_720s_gt3", track="imola")
    f = FileValues("HONE_8", "x/HONE_8.json", 3, 2, 0, 15,
                   (26.5, 26.5, 26.0, 26.0), 40)
    text = "\n".join(setup_lines(s, [f]))
    assert "box=si" in text
    assert "mappa 0 (HUD 1)" in text
    assert "gomme dentro (FL FR RL RR) 24.0 24.5 23.0 23.5" in text
    moving = replace(s, speed_kmh=40.0)
    assert "box=no" in "\n".join(setup_lines(moving, [f]))


def test_setup_lines_check_the_bias_where_the_offset_is_measured():
    """Per la 720S lo scarto del ripartitore e' misurato sull'archivio
    (`MEASURED_BIAS_OFFSET`): in garage la riga dice il valore atteso e il
    ripartitore entra fra le differenze certe. Il passo 1 del foglio Ingegnere
    conferma cosi' la misura senza fare i conti a mano."""
    from accoach.diagnostics import setup_lines
    from accoach.engineer.fingerprint import FileValues

    s = replace(
        TelemetrySnapshot.disconnected(), connected=True, in_pit_lane=True,
        speed_kmh=0.0, tc_level=3, abs_level=4, engine_map=0, brake_bias=0.64,
        tyre_pressure=(26.3, 25.8, 24.7, 24.4), fuel=60.0, air_temp=21.0,
        road_temp=27.0, car_model="mclaren_720s_gt3_evo", track="Imola")
    imola = FileValues("HONE_7", "x/HONE_7.json", 3, 4, 0, 0,
                       (26.3, 25.8, 24.7, 24.4), 60)
    brands = FileValues("HONE_2", "x/HONE_2.json", 3, 4, 0, 15,
                        (26.3, 25.8, 24.7, 24.4), 60)
    text = "\n".join(setup_lines(s, [imola, brands]))
    seven, two = text[:text.index("HONE_2")], text[text.index("HONE_2"):]
    assert "atteso 0.640" in seven
    assert "differenze certe: nessuna" in seven
    assert "atteso 0.670" in two
    assert "RIPARTITORE letto 0.64 file 0.67" in two


def test_setup_lines_without_files_says_so():
    from accoach.diagnostics import setup_lines

    lines = setup_lines(replace(TelemetrySnapshot.disconnected(), connected=True), [])
    assert lines and any("nessun setup" in ln for ln in lines)
