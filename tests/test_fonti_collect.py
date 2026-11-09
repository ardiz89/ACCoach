"""Raccolta (tools/fonti.collect) con Apify finto dalle fixture."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.fonti import apify, collect, db  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "fonti"
PIANO = [
    {"actor": "streamers/youtube-scraper", "input": {"searchQueries": ["ACC Imola"]},
     "max_items": 5, "platform": "youtube"},
    {"actor": "trudax/reddit-scraper-lite", "input": {"searches": ["Imola"]},
     "max_items": 10, "platform": "reddit"},
]


def _http(chiamate):
    def http(method, url, headers, body):
        if url.endswith("/users/me/limits"):
            return 200, json.dumps({"data": {"current": {"monthlyUsageUsd": 0.54}}}).encode()
        chiamate.append((url, json.loads(body)))
        nome = "apify_youtube.json" if "youtube" in url else "apify_reddit.json"
        return 201, (FIX / nome).read_bytes()
    return http


def _conn(tmp_path):
    return db.open_db(tmp_path / "f.sqlite")


def test_raccolta_da_fixture(tmp_path):
    conn, chiamate = _conn(tmp_path), []
    r = collect.collect(conn, apify.Apify("tok-di-prova", http=_http(chiamate)), "imola", PIANO)
    assert r["sources"] == 3 and r["texts"] == 4 and r["spent_usd"] == 0
    assert "maxItems=5" in chiamate[0][0] and "streamers~youtube-scraper" in chiamate[0][0]
    t = conn.execute("SELECT kind, author, segments_json FROM texts WHERE kind='transcript'").fetchall()
    assert len(t) == 1 and t[0][1] == "Pilota Uno"
    segs = json.loads(t[0][2])
    assert segs[1] == {"start_s": 95.4, "text": "Stay left through Acque Minerali"}
    assert {a for (a,) in conn.execute("SELECT author FROM texts WHERE kind='comment'")} == {"u_due", "u_tre"}
    giochi = dict(conn.execute("SELECT url, game FROM sources").fetchall())
    assert giochi["https://www.youtube.com/watch?v=vid001"] == "acc"
    assert giochi["https://www.youtube.com/watch?v=vid002"] == "altro"
    assert conn.execute("SELECT COUNT(*) FROM sources WHERE track='imola'").fetchone()[0] == 3


def test_raccolta_rilanciata_non_duplica(tmp_path):
    conn, chiamate = _conn(tmp_path), []
    client = apify.Apify("tok-di-prova", http=_http(chiamate))
    collect.collect(conn, client, "imola", PIANO)
    prima = db.count_rows(conn)
    r = collect.collect(conn, client, "imola", PIANO)
    assert r["texts"] == 0 and r["sources"] == 0
    assert db.count_rows(conn) == prima


def test_rilancio_non_chiama_run(tmp_path):
    conn, chiamate = _conn(tmp_path), []
    client = apify.Apify("tok-di-prova", http=_http(chiamate))
    collect.collect(conn, client, "imola", PIANO)
    assert len(chiamate) == 2
    r = collect.collect(conn, client, "imola", PIANO)
    assert len(chiamate) == 2 and r["skipped"] == 2
    assert conn.execute("SELECT COUNT(*) FROM collect_runs").fetchone()[0] == 2
    collect.collect(conn, client, "imola", PIANO, force=True)
    assert len(chiamate) == 4


def test_tetto_a_meta_piano(tmp_path):
    conn, chiamate = _conn(tmp_path), []
    base = _http(chiamate)

    def http(method, url, headers, body):
        if url.endswith("/users/me/limits"):
            uso = 0.54 if not chiamate else 2.60  # la prima voce sfonda il tetto
            return 200, json.dumps({"data": {"current": {"monthlyUsageUsd": uso}}}).encode()
        return base(method, url, headers, body)

    with pytest.raises(apify.CapReached):
        collect.collect(conn, apify.Apify("tok-di-prova", http=http), "imola", PIANO)
    assert len(chiamate) == 1
    righe = conn.execute("SELECT entry_key FROM collect_runs").fetchall()
    assert righe == [(collect.entry_key(PIANO[0]),)]


def test_errore_di_rete_senza_traceback(tmp_path, monkeypatch, capsys):
    import urllib.error
    from tools.fonti import fonti

    def rotto(self, *a, **k):
        raise urllib.error.URLError("giu")

    monkeypatch.setenv("APIFY_API_TOKEN", "tok-di-prova")
    monkeypatch.setattr(apify.Apify, "usage_usd", rotto)
    piano = tmp_path / "p.json"
    piano.write_text(json.dumps(PIANO), encoding="utf-8")
    rc = fonti.main(["--db", str(tmp_path / "d"), "collect", "--track", "imola", "--plan", str(piano)])
    err = capsys.readouterr().err
    assert rc == 1 and "Rete" in err and "tok-di-prova" not in err and "Traceback" not in err
