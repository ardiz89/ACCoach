"""POST /api/corner-name — the driver naming a corner from the screen.

The store itself is tested in ``test_cornernames.py``. What is defended here is
the endpoint: that it refuses what would corrupt the file, that the name reaches
every page that shows corner names rather than just the one it was typed on, and
that removing a name is as easy as adding it.
"""
import pytest
from fastapi.testclient import TestClient

from accoach import cornernames
from accoach.api import create_api
from accoach.recording.storage import save_lap

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"

#: Where the synthetic lap's corners actually are. The second one lands on
#: Monza's Variante Ascari, which is what makes "the driver beats the curated
#: table" testable at all — the first is only ever "Curva 1".
APEX, ASCARI = 0.31, 0.71


@pytest.fixture
def store(tmp_path, monkeypatch):
    """The names file, redirected away from the real ~/Documents/ACCoach.

    Without this the suite writes corner names into whoever is running it.
    """
    p = tmp_path / "corner-names.json"
    monkeypatch.setattr(cornernames, "path", lambda: p)
    return p


@pytest.fixture
def client(tmp_path, store):
    laps = tmp_path / "laps"
    laps.mkdir()
    for i in range(3):
        lap = synth.build_lap()
        lap.recorded_utc = f"2026-08-04T18:0{i}:00+00:00"
        save_lap(lap, laps)
    return TestClient(create_api(laps))


def _post(c, **body):
    return c.post("/api/corner-name", json={"track": TRACK, **body})


# --- what it accepts -------------------------------------------------------

def test_a_name_is_stored_and_reported_back(client, store):
    r = _post(client, pos=APEX, name="La mia variante")
    assert r.status_code == 200
    assert r.json()["names"] == 1
    assert cornernames.for_track(TRACK, store).of(APEX) == "La mia variante"


def test_an_empty_name_removes_it(client, store):
    _post(client, pos=APEX, name="La mia variante")
    assert _post(client, pos=APEX, name="").status_code == 200
    assert len(cornernames.for_track(TRACK, store)) == 0


def test_surrounding_whitespace_is_not_part_of_the_name(client, store):
    _post(client, pos=APEX, name="  Sacramento  ")
    assert cornernames.for_track(TRACK, store).of(APEX) == "Sacramento"


# --- what it refuses, and refuses out loud ---------------------------------

@pytest.mark.parametrize("body,why", [
    ({"pos": "middle", "name": "X"}, "a position that is not a number"),
    ({"pos": 1.5, "name": "X"}, "a position outside the lap"),
    ({"name": "X"}, "no position at all"),
])
def test_a_position_that_makes_no_sense_is_refused(client, body, why):
    assert client.post("/api/corner-name", json={"track": TRACK, **body}) \
        .status_code == 422, why


def test_a_nameless_track_is_refused(client):
    assert client.post("/api/corner-name",
                       json={"track": "  ", "pos": 0.1, "name": "X"}) \
        .status_code == 422


def test_a_pasted_paragraph_is_refused_where_it_can_still_be_explained(client):
    """The name is drawn in a title, in the chips, in the debrief sentences and
    spoken out loud. Refusing it here beats wrecking a layout measured at
    1600 px, and beats truncating it into something the driver did not write."""
    long = "x" * (cornernames.MAX_NAME + 1)
    assert _post(client, pos=APEX, name=long).status_code == 422
    assert _post(client, pos=APEX, name="x" * cornernames.MAX_NAME) \
        .status_code == 200


# --- and then it has to show up everywhere ---------------------------------

def _names(payload_corners):
    return [c["name"] for c in payload_corners]


def test_the_name_reaches_the_page_it_was_typed_on(client):
    _post(client, pos=APEX, name="Sacramento")
    j = client.get("/api/trajectory",
                   params={"car": CAR, "track": TRACK, "lang": "it"}).json()
    assert "Sacramento" in _names(j["corners"])


def test_the_name_reaches_the_lap_report_too(client):
    """A rename that only changes the caption you typed it into is an app
    disagreeing with itself — the failure `laps_dir` already shipped once."""
    _post(client, pos=APEX, name="Sacramento")
    j = client.get("/api/analysis",
                   params={"car": CAR, "track": TRACK, "lang": "it"}).json()
    assert "Sacramento" in str(j)


def test_it_beats_the_curated_name_for_the_same_corner(client):
    before = client.get("/api/trajectory",
                        params={"car": CAR, "track": TRACK, "lang": "it"}).json()
    assert "Variante Ascari" in _names(before["corners"])
    _post(client, pos=ASCARI, name="La mia Ascari")
    after = client.get("/api/trajectory",
                       params={"car": CAR, "track": TRACK, "lang": "it"}).json()
    assert "La mia Ascari" in _names(after["corners"])
    assert "Variante Ascari" not in _names(after["corners"])


def test_taking_it_off_gives_the_curated_name_back(client):
    _post(client, pos=ASCARI, name="La mia Ascari")
    _post(client, pos=ASCARI, name="")
    j = client.get("/api/trajectory",
                   params={"car": CAR, "track": TRACK, "lang": "it"}).json()
    assert "Variante Ascari" in _names(j["corners"])


# --- what the screen found, and the tests would not have -------------------

def test_a_corner_says_whether_its_name_was_typed_or_ours(client):
    """Found by opening the page, not by a test: the rename box pre-filled
    itself with whatever was on screen, so on a corner called "Corner 1" one
    Save with nothing changed stored the detector's *count* as a name — where
    it then outranks every curated table and looks identical to the fallback it
    replaced. The box needs to know, so the payload has to say."""
    j = client.get("/api/trajectory",
                   params={"car": CAR, "track": TRACK, "lang": "it"}).json()
    assert [c["typed"] for c in j["corners"]] == [False, False]

    _post(client, pos=APEX, name="Sacramento")
    j = client.get("/api/trajectory",
                   params={"car": CAR, "track": TRACK, "lang": "it"}).json()
    assert [c["typed"] for c in j["corners"]] == [True, False]


def test_a_curated_name_is_not_reported_as_typed(client):
    """Variante Ascari is ours. Offering to "Remove" it would promise an undo
    for something the driver never did."""
    j = client.get("/api/trajectory",
                   params={"car": CAR, "track": TRACK, "lang": "it"}).json()
    ascari = [c for c in j["corners"] if c["name"] == "Variante Ascari"]
    assert ascari and ascari[0]["typed"] is False


# --- POST /api/braking-reference (roadmap item 2) --------------------------

def _mark(c, **body):
    return c.post("/api/braking-reference", json={"track": TRACK, **body})


def test_a_braking_reference_is_stored(client, store):
    r = _mark(client, pos=0.12, text="alla fine del verde")
    assert r.status_code == 200 and r.json()["marks"] == 1
    assert cornernames.marks_for(TRACK, store).of(0.12) == "alla fine del verde"


def test_it_reaches_the_braking_sheet(client):
    """Where it was typed, and it has to arrive as the row's own wording.

    Keyed on the row's braking ONSET and not on the apex — those are different
    positions (0.19 against 0.31 on this lap), which is the whole reason a
    braking reference has its own tolerance."""
    sheet = client.get("/api/braking",
                       params={"car": CAR, "track": TRACK, "lang": "it"}).json()
    at = sheet["rows"][0]["pos"]
    _mark(client, pos=at, text="dove finisce la riga blu")
    j = client.get("/api/braking",
                   params={"car": CAR, "track": TRACK, "lang": "it"}).json()
    assert j["rows"][0]["landmark"] == "dove finisce la riga blu"
    assert j["rows"][0]["typed"] is True


def test_a_row_says_when_the_wording_is_ours_and_not_theirs(client):
    j = client.get("/api/braking",
                   params={"car": CAR, "track": TRACK, "lang": "it"}).json()
    assert all(r["typed"] is False for r in j["rows"])


@pytest.mark.parametrize("body", [
    {"pos": "here", "text": "x"},
    {"pos": 2.0, "text": "x"},
    {"text": "x"},
])
def test_a_reference_with_no_usable_position_is_refused(client, body):
    assert client.post("/api/braking-reference",
                       json={"track": TRACK, **body}).status_code == 422


def test_a_reference_longer_than_a_table_cell_is_refused(client):
    long = "x" * (cornernames.MAX_MARK + 1)
    assert _mark(client, pos=0.12, text=long).status_code == 422
    assert _mark(client, pos=0.12, text="x" * cornernames.MAX_MARK).status_code == 200
