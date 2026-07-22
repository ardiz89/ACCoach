"""A lap driven off track says so — and only that lap says anything.

The flag was computed at every lap since v5 and shown nowhere, while silently
deciding which lap became the reference. So a lap could vanish from the running
for the reference with nothing on screen explaining it.

The stored flag has three states (clean / dirty / unknown) and the surface has
two. That's the point, not an oversight: "unknown" covers every lap recorded
before the flag existed — 16 of 26 in the archive this was written against — and
marking the majority of rows "?" reads as a broken page, not an informative one.
"""
from dataclasses import replace

import pytest

from accoach.api import _off_track, create_api
from accoach.recording.storage import save_lap

import synth

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient       # noqa: E402


def _lap(ms: int, clean: bool | None):
    return replace(synth.build_lap(), lap_time_ms=ms, clean=clean)


def test_only_dirty_is_marked():
    assert _off_track({"clean": 0}) is True
    assert _off_track({"clean": 1}) is False
    assert _off_track({"clean": -1}) is False, "unknown must not render"
    assert _off_track({}) is False, "an older row must not render either"


@pytest.fixture
def client(tmp_path):
    for ms, clean in ((100_000, False), (102_000, True), (104_000, None)):
        save_lap(_lap(ms, clean), tmp_path)
    return TestClient(create_api(laps_dir=tmp_path))


def _laps(client):
    lap = synth.build_lap()
    r = client.get(f"/api/analysis?car={lap.car_model}&track={lap.track}")
    assert r.status_code == 200, r.text
    return r.json()


def test_the_endpoint_carries_the_flag(client):
    by_time = {l["lap_time"]: l for l in _laps(client)["laps"]}
    assert by_time["1:40.000"]["off_track"] is True
    assert by_time["1:42.000"]["off_track"] is False
    assert by_time["1:44.000"]["off_track"] is False      # unknown


def test_the_fastest_lap_being_off_track_is_visible_and_not_the_reference(client):
    """The case the whole thing exists for: fastest, off track, not the reference.

    Before, the page starred it and compared against it with nothing said.
    """
    data = _laps(client)
    fastest = min(data["laps"], key=lambda l: l["lap_time_ms"])
    assert fastest["off_track"] is True
    assert data["best_path"] != fastest["path"]
    assert data["reference"]["lap_time"] == "1:42.000"


def test_the_words_exist_in_both_languages():
    import re
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1]
           / "src" / "accoach" / "web" / "i18n.js").read_text(encoding="utf-8")
    for key in ("lap.offTrack", "lap.offTrack.why"):
        m = re.search(rf'"{re.escape(key)}"\s*:\s*\{{(.+?)\}}', src, re.S)
        assert m, f"{key} missing from the catalogue"
        body = m.group(1)
        assert "en:" in body and "it:" in body
        # …and never the word that's already taken three times over: "giro pulito"
        # means "no time lost per corner" in the debrief and on Home, and "drive a
        # clean lap" means "a complete one" in the coach.
        assert "sporc" not in body.lower() and "pulit" not in body.lower(), \
            f"{key} reuses the overloaded clean/dirty wording"
