"""Lavoro degli agenti (tools/fonti.agents): coda, istruzioni, ingest congelato."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.fonti import agents, db, fonti  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "fonti"
CORPO = "At Acque Minerali I go down to third gear and it works great."
SEGS = [{"start_s": 1.0, "text": "Into Tosa you brake at the 100 board"},
        {"start_s": 5.5, "text": "Stay left through Acque Minerali"}]
TRASCRITTO = " ".join(s["text"] for s in SEGS)


def _fonte(conn, url, game="acc", platform="reddit", track="imola"):
    conn.execute("INSERT INTO sources(platform, url, author, title, published, game, track, meta_json)"
                 " VALUES (?,?,?,?,?,?,?,?)", (platform, url, "a", "t", "2026-05-01", game, track, "{}"))
    conn.commit()
    return conn.execute("SELECT id FROM sources WHERE url=?", (url,)).fetchone()[0]


@pytest.fixture
def conn(tmp_path):
    c = db.open_db(tmp_path / "f.sqlite")
    acc = _fonte(c, "https://r/acc")
    altro = _fonte(c, "https://r/altro", game="altro")
    sha, _ = db.add_text(c, acc, "comment", "u_uno", CORPO)
    assert sha == json.loads((FIX / "risposta_estrai.json").read_text(encoding="utf-8"))["sha256"]
    db.add_text(c, altro, "comment", "u_altro", "iRacing Imola: down to third gear at Tosa.")
    yield c
    c.close()


def _risposta(tmp_path, nome, **cambi):
    d = json.loads((FIX / nome).read_text(encoding="utf-8"))
    d.update(cambi)
    p = tmp_path / f"r-{nome}"
    p.write_text(json.dumps(d), encoding="utf-8")
    return p


def test_pending_solo_acc_e_non_congelati(conn, tmp_path):
    out = tmp_path / "jobs"
    jobs = agents.pending(conn, "extract", "imola", out)
    assert [p.name for p in jobs] == [f"extract-{'97ee69d68d55'}.job.json"]
    job = json.loads(jobs[0].read_text(encoding="utf-8"))
    assert set(job) == {"kind", "sha256", "track", "prompt_version", "body", "segments", "meta", "corners"}
    assert job["body"] == CORPO and job["kind"] == "extract" and "Acque Minerali" in job["corners"]
    agents.ingest(conn, FIX / "risposta_estrai.json", "claude-test")
    assert agents.pending(conn, "extract", "imola", tmp_path / "jobs2") == []
    # Il rate è un'altra chiave: il testo ACC resta da valutare, quello «altro» mai.
    assert len(agents.pending(conn, "rate", "imola", tmp_path / "jobs3")) == 1


def test_pending_deterministico(conn, tmp_path):
    a = agents.pending(conn, "extract", "imola", tmp_path / "a")[0].read_bytes()
    b = agents.pending(conn, "extract", "imola", tmp_path / "b")[0].read_bytes()
    assert a == b


def test_ingest_fixture(conn):
    r = agents.ingest(conn, FIX / "risposta_estrai.json", "claude-test")
    assert r == {"facts": 1, "rejects": 1}
    f = conn.execute("SELECT track, corner, type, value, quote, offset, author FROM facts").fetchall()
    assert f == [("imola", "Acque Minerali", "gear", "3", "down to third gear", 23, "u_uno")]
    assert [x[0] for x in conn.execute("SELECT reason FROM rejects")] == ["citazione_assente"]
    model, pv = conn.execute("SELECT model, prompt_version FROM results").fetchone()
    assert model == "claude-test" and pv == agents.prompt_version("extract")


def test_stesso_testo_due_autori_due_fatti(conn, tmp_path):
    altra = _fonte(conn, "https://r/acc2")
    db.add_text(conn, altra, "comment", "u_due", CORPO)
    r = agents.ingest(conn, FIX / "risposta_estrai.json", "claude-test")
    assert r == {"facts": 2, "rejects": 1}
    assert sorted(conn.execute("SELECT author FROM facts").fetchall()) == [("u_due",), ("u_uno",)]


def test_trascritto_con_segmenti_e_start_s(conn, tmp_path):
    sid = _fonte(conn, "https://yt/v1", platform="youtube")
    sha, _ = db.add_text(conn, sid, "transcript", "Canale", TRASCRITTO, SEGS)
    risposta = {"sha256": sha, "kind": "extract", "facts": [
        {"corner": "Tosa", "type": "brake", "value": "board:100",
         "quote": "brake at the 100 board", "offset": 14},
        {"corner": "Acque Minerali", "type": "line", "value": "Stay left through Acque Minerali",
         "quote": "Stay left through Acque Minerali", "offset": 37}]}
    p = tmp_path / "t.json"
    p.write_text(json.dumps(risposta), encoding="utf-8")
    assert agents.ingest(conn, p, "m") == {"facts": 2, "rejects": 0}
    assert conn.execute("SELECT corner, start_s FROM facts ORDER BY offset").fetchall() == [
        ("Tosa", 1.0), ("Acque Minerali", 5.5)]
    jobs = [json.loads(p.read_text(encoding="utf-8"))
            for p in agents.pending(conn, "rate", "imola", tmp_path / "j")]
    assert [j["sha256"] for j in jobs] == sorted(j["sha256"] for j in jobs)
    assert next(j for j in jobs if j["sha256"] == sha)["segments"] == SEGS


def _stato(conn):
    return db.count_rows(conn)


def test_json_malformato_rifiutato_intero(conn, tmp_path):
    prima = _stato(conn)
    tronco = tmp_path / "tronco.json"
    tronco.write_text((FIX / "risposta_estrai.json").read_text(encoding="utf-8")[:80], encoding="utf-8")
    with pytest.raises(agents.AnswerRejected):
        agents.ingest(conn, tronco, "m")
    with pytest.raises(agents.AnswerRejected):
        agents.ingest(conn, _risposta(tmp_path, "risposta_estrai.json", extra=1), "m")
    d = json.loads((FIX / "risposta_estrai.json").read_text(encoding="utf-8"))
    d["facts"][0]["note"] = "in più"
    p = tmp_path / "chiave_fatto.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(agents.AnswerRejected):
        agents.ingest(conn, p, "m")
    with pytest.raises(agents.AnswerRejected):
        agents.ingest(conn, _risposta(tmp_path, "risposta_valuta.json",
                                      speaker={"name": "x", "role": "pilota esperto"}), "m")
    with pytest.raises(agents.AnswerRejected):
        agents.ingest(conn, _risposta(tmp_path, "risposta_factcheck.json", verdict="forse"), "m")
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(conn, _risposta(tmp_path, "risposta_estrai.json", sha256="0" * 64), "m")
    assert e.value.reason == "testo_ignoto"
    assert _stato(conn) == prima


def test_gia_congelato(conn):
    agents.ingest(conn, FIX / "risposta_estrai.json", "claude-test")
    prima = _stato(conn)
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(conn, FIX / "risposta_estrai.json", "claude-test")
    assert e.value.reason == "gia_congelato"
    assert _stato(conn) == prima
    # Un altro modello è un'altra chiave.
    assert agents.ingest(conn, FIX / "risposta_estrai.json", "altro-modello") == {"facts": 1, "rejects": 1}


def test_rate_e_factcheck_citazioni_solo_presenti(conn):
    assert agents.ingest(conn, FIX / "risposta_valuta.json", "m") == {"facts": 0, "rejects": 1}
    assert agents.ingest(conn, FIX / "risposta_factcheck.json", "m") == {"facts": 0, "rejects": 0}
    reasons = [x[0] for x in conn.execute("SELECT reason FROM rejects")]
    assert reasons == ["citazione_assente"]
    kinds = sorted(k for (k,) in conn.execute("SELECT kind FROM results"))
    assert kinds == ["factcheck", "rate"]


def test_prompt_version_letta_dal_file(conn, tmp_path, monkeypatch):
    for kind, nome in agents.PROMPT_FILES.items():
        prima = (agents.PROMPTS_DIR / nome).read_text(encoding="utf-8").splitlines()[0]
        assert prima == "prompt_version: 1"
    finta = tmp_path / "prompts"
    finta.mkdir()
    for nome in agents.PROMPT_FILES.values():
        (finta / nome).write_text("prompt_version: 7\nIstruzioni.\n", encoding="utf-8")
    monkeypatch.setattr(agents, "PROMPTS_DIR", finta)
    job = json.loads(agents.pending(conn, "extract", "imola", tmp_path / "j")[0].read_text(encoding="utf-8"))
    assert job["prompt_version"] == "7"


def test_cli_pending_e_ingest(conn, tmp_path, capsys):
    dbp = tmp_path / "f.sqlite"
    out = tmp_path / "cli"
    assert fonti.main(["--db", str(dbp), "pending", "--kind", "extract", "--track", "imola",
                       "--out", str(out)]) == 0
    assert len(list(out.glob("*.job.json"))) == 1
    assert fonti.main(["--db", str(dbp), "ingest", "--model", "m",
                       str(FIX / "risposta_estrai.json")]) == 0
    assert fonti.main(["--db", str(dbp), "ingest", "--model", "m",
                       str(FIX / "risposta_estrai.json")]) == 1
    assert "gia_congelato" in capsys.readouterr().err
