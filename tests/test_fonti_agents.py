"""Lavoro degli agenti (tools/fonti.agents): coda, istruzioni, ingest congelato."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.fonti import agents, db, fonti  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "fonti"
CORPO = "At Acque Minerali I go down to third gear and it works great."
COACH = "I coach drivers in ACC and at Imola my best is 1:41.2 with the Ferrari 296 GT3."
SEGS = [{"start_s": 1.0, "text": "Into Tosa you brake at the 100 board"},
        {"start_s": 5.5, "text": "Stay left through Acque Minerali"}]
TRASCRITTO = " ".join(s["text"] for s in SEGS)
FATTO = {"corner": "Acque Minerali", "type": "gear", "value": "3",
         "quote": "down to third gear", "offset": 23}


def _fonte(conn, url, game="acc", platform="reddit", track="imola", author="a"):
    conn.execute("INSERT INTO sources(platform, url, author, title, published, game, track, meta_json)"
                 " VALUES (?,?,?,?,?,?,?,?)", (platform, url, author, "t", "2026-05-01", game, track, "{}"))
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


def _scrivi(tmp_path, d, nome="r.json"):
    p = tmp_path / nome
    p.write_text(json.dumps(d), encoding="utf-8")
    return p


def _risposta(tmp_path, nome, **cambi):
    d = json.loads((FIX / nome).read_text(encoding="utf-8"))
    d.update(cambi)
    return _scrivi(tmp_path, d, f"r-{nome}")


ECO = {"prompt_version": "1", "track": "imola"}


def _estrai(sha, facts, **eco):
    return {"sha256": sha, "kind": "extract", "facts": facts, **ECO, **eco}


def _proponi(conn, tmp_path, kind="extract", track="imola"):
    return agents.pending(conn, kind, track, tmp_path / f"jobs-{kind}-{track}")


def _job_factcheck(conn, key, bodies, version="1", own=("fonte-del-fatto",), own_authors=()):
    """`bodies`: testi o tuple (sha256, testo[, autore reddit]); `own`: le fonti del fatto."""
    terne = []
    for i, x in enumerate(bodies):
        x = x if isinstance(x, tuple) else (f"t{i}", x)
        terne.append((x[0], x[1], x[2] if len(x) > 2 else f"autore{i}"))
    payload = {"kind": "factcheck", "sha256": key, "track": "imola", "prompt_version": version,
               "fact_sha256s": sorted(own), "fact_authors": sorted(own_authors),
               "texts": [{"sha256": sha, "body": b, "segments": None,
                          "meta": [{"platform": "reddit", "author": a}]} for sha, b, a in terne]}
    conn.execute("INSERT INTO jobs(kind, key, track, prompt_version, payload_json, created_at)"
                 " VALUES ('factcheck', ?, 'imola', ?, ?, 'ora')", (key, version, json.dumps(payload)))
    conn.commit()


def _apri_rate(conn, sha, track="imola"):
    """Il lavoro `rate` come lo scrive pending, senza chiedere che l'autore abbia un fatto."""
    conn.execute("INSERT OR REPLACE INTO jobs(kind, key, track, prompt_version, payload_json, created_at)"
                 " VALUES ('rate', ?, ?, ?, '{}', 'ora')", (sha, track, agents.prompt_version("rate")))
    conn.commit()


def _coach(conn, tmp_path):
    sid = _fonte(conn, "https://yt/coach", platform="youtube", author="Canale Coach")
    sha, _ = db.add_text(conn, sid, "transcript", "Coach Uno", COACH)
    _apri_rate(conn, sha)
    return sha


def _stato(conn):
    return db.count_rows(conn)


# --- pending ------------------------------------------------------------------

def test_pending_solo_acc_e_non_congelati(conn, tmp_path):
    jobs = _proponi(conn, tmp_path)
    assert [p.name for p in jobs] == ["extract-97ee69d68d55.job.json"]
    job = json.loads(jobs[0].read_text(encoding="utf-8"))
    assert set(job) == {"kind", "sha256", "track", "prompt_version", "body", "segments", "meta", "corners",
                        "turns"}
    assert job["turns"]["Tosa"] == [7]
    assert job["body"] == CORPO and job["kind"] == "extract" and "Acque Minerali" in job["corners"]
    agents.ingest(conn, FIX / "risposta_estrai.json", "claude-test")
    assert agents.pending(conn, "extract", "imola", tmp_path / "jobs2") == []
    # Il rate è un'altra chiave: il testo ACC resta da valutare, quello «altro» mai.
    assert len(agents.pending(conn, "rate", "imola", tmp_path / "jobs3")) == 1


def test_pending_deterministico_e_ricordato(conn, tmp_path):
    a = agents.pending(conn, "extract", "imola", tmp_path / "a")[0].read_bytes()
    b = agents.pending(conn, "extract", "imola", tmp_path / "b")[0].read_bytes()
    assert a == b
    righe = conn.execute("SELECT kind, key, track, prompt_version, payload_json FROM jobs").fetchall()
    assert len(righe) == 1 and righe[0][:4] == ("extract", "97ee69d68d556536e78db575c4c7097e98af762fadd034b6c52a1c1856598a0d",
                                                "imola", "1")
    assert json.loads(righe[0][4]) == json.loads(a)


def test_prompt_version_letta_dal_file(conn, tmp_path, monkeypatch):
    for nome in agents.PROMPT_FILES.values():
        prima = (agents.PROMPTS_DIR / nome).read_text(encoding="utf-8").splitlines()[0]
        assert prima == "prompt_version: 1"
    finta = tmp_path / "prompts"
    finta.mkdir()
    for nome in agents.PROMPT_FILES.values():
        (finta / nome).write_text("prompt_version: 7\nIstruzioni.\n", encoding="utf-8")
    monkeypatch.setattr(agents, "PROMPTS_DIR", finta)
    job = json.loads(_proponi(conn, tmp_path)[0].read_text(encoding="utf-8"))
    assert job["prompt_version"] == "7"


def test_pending_salta_segmenti_illeggibili(conn, tmp_path):
    sid = _fonte(conn, "https://yt/rotto", platform="youtube")
    conn.execute("INSERT INTO texts(sha256, source_id, kind, author, body, segments_json)"
                 " VALUES ('s7', ?, 'transcript', 'x', ?, '{rotto')", (sid, CORPO))
    conn.commit()
    assert [p.name for p in _proponi(conn, tmp_path)] == ["extract-97ee69d68d55.job.json"]


# --- ingest extract -------------------------------------------------------------

def test_ingest_fixture(conn, tmp_path):
    _proponi(conn, tmp_path)
    r = agents.ingest(conn, FIX / "risposta_estrai.json", "claude-test")
    assert r == {"facts": 1, "rejects": 1}
    f = conn.execute("SELECT track, corner, type, value, quote, offset, author FROM facts").fetchall()
    assert f == [("imola", "Acque Minerali", "gear", "3", "down to third gear", 23, "u_uno")]
    assert [x[0] for x in conn.execute("SELECT reason FROM rejects")] == ["citazione_assente"]
    model, pv = conn.execute("SELECT model, prompt_version FROM results").fetchone()
    assert model == "claude-test" and pv == "1"


def test_lavoro_non_proposto_rifiutato(conn, tmp_path):
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(conn, FIX / "risposta_estrai.json", "m")
    assert e.value.reason == "lavoro_ignoto"
    assert conn.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 0


def test_stesso_testo_due_autori_due_fatti(conn, tmp_path):
    db.add_text(conn, _fonte(conn, "https://r/acc2"), "comment", "u_due", CORPO)
    _proponi(conn, tmp_path)
    assert agents.ingest(conn, FIX / "risposta_estrai.json", "m") == {"facts": 2, "rejects": 1}
    assert sorted(conn.execute("SELECT author FROM facts").fetchall()) == [("u_due",), ("u_uno",)]


def test_stesso_testo_da_fonte_non_acc_niente_fatto(conn, tmp_path):
    # Sonda 1: lo stesso testo anche da una fonte «altro» non dà una riga a quella fonte.
    db.add_text(conn, _fonte(conn, "https://r/altro2", game="altro"), "comment", "ir_user", CORPO)
    _proponi(conn, tmp_path)
    assert agents.ingest(conn, FIX / "risposta_estrai.json", "m") == {"facts": 1, "rejects": 1}
    giochi = conn.execute("SELECT f.author, s.game FROM facts f JOIN sources s ON s.id = f.source_id").fetchall()
    assert giochi == [("u_uno", "acc")]


def test_testo_solo_non_acc_mai_accettato(tmp_path):
    # Sonda 1b: un testo che esiste solo da una fonte non ACC non diventa mai un fatto.
    c = db.open_db(tmp_path / "f.sqlite")
    sha, _ = db.add_text(c, _fonte(c, "https://r/ir", game="altro"), "comment", "ir_user", CORPO)
    assert _proponi(c, tmp_path) == []
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(c, _scrivi(tmp_path, _estrai(sha, [FATTO])), "m")
    assert e.value.reason == "lavoro_ignoto"
    # Anche se il lavoro esistesse, senza righe ACC della pista il testo non c'è.
    c.execute("INSERT INTO jobs VALUES ('extract', ?, 'imola', '1', '{}', 'ora')", (sha,))
    c.commit()
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(c, _scrivi(tmp_path, _estrai(sha, [FATTO])), "m")
    assert e.value.reason == "testo_ignoto"
    assert _stato(c)["results"] == 0
    c.close()


def test_stesso_testo_due_piste_solo_quella_del_lavoro(tmp_path):
    # Sonda 1c: lo stesso testo su Imola e su Monza; il fatto vale per la pista del lavoro.
    c = db.open_db(tmp_path / "f.sqlite")
    sha, _ = db.add_text(c, _fonte(c, "https://r/i"), "comment", "x", CORPO)
    db.add_text(c, _fonte(c, "https://r/m", track="monza"), "comment", "y", CORPO)
    _proponi(c, tmp_path)
    assert agents.ingest(c, _scrivi(tmp_path, _estrai(sha, [FATTO])), "m") == {"facts": 1, "rejects": 0}
    assert c.execute("SELECT track, author FROM facts").fetchall() == [("imola", "x")]
    assert c.execute("SELECT COUNT(*) FROM rejects").fetchone()[0] == 0
    c.close()


def test_trascritto_con_segmenti_e_start_s(conn, tmp_path):
    sid = _fonte(conn, "https://yt/v1", platform="youtube")
    sha, _ = db.add_text(conn, sid, "transcript", "Canale", TRASCRITTO, SEGS)
    _proponi(conn, tmp_path)
    # L'offset dichiarato (33) cade ancora nel primo sottotitolo; la citazione vera
    # comincia a 37, nel secondo: `start_s` segue la citazione, non l'offset (sonda 5).
    risposta = _estrai(sha, [
        {"corner": "Tosa", "type": "brake", "value": "board:100",
         "quote": "brake at the 100 board", "offset": 14},
        {"corner": "Acque Minerali", "type": "line", "value": "Stay left through Acque Minerali",
         "quote": "Stay left through Acque Minerali", "offset": 33}])
    assert agents.ingest(conn, _scrivi(tmp_path, risposta), "m") == {"facts": 2, "rejects": 0}
    assert conn.execute("SELECT corner, start_s FROM facts ORDER BY offset").fetchall() == [
        ("Tosa", 1.0), ("Acque Minerali", 5.5)]
    jobs = [json.loads(p.read_text(encoding="utf-8")) for p in _proponi(conn, tmp_path, "rate")]
    assert [j["sha256"] for j in jobs] == sorted(j["sha256"] for j in jobs)
    assert next(j for j in jobs if j["sha256"] == sha)["segments"] == SEGS


def test_segmenti_illeggibili_rifiutati(conn, tmp_path):
    # Sonda 7: segmenti guasti nel database danno un rifiuto, non un'eccezione qualsiasi.
    _proponi(conn, tmp_path)
    conn.execute("UPDATE texts SET segments_json='{rotto' WHERE author='u_uno'")
    conn.commit()
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(conn, FIX / "risposta_estrai.json", "m")
    assert e.value.reason == "segmenti_illeggibili"


def test_fatto_ripetuto_scartato(conn, tmp_path):
    # Sonda 8: lo stesso fatto due volte nella stessa risposta entra una volta.
    _proponi(conn, tmp_path)
    sha = json.loads((FIX / "risposta_estrai.json").read_text(encoding="utf-8"))["sha256"]
    assert agents.ingest(conn, _scrivi(tmp_path, _estrai(sha, [FATTO, FATTO])), "m") == {"facts": 1, "rejects": 1}
    assert [r for (r,) in conn.execute("SELECT reason FROM rejects")] == ["fatto_duplicato"]


def test_nessun_fatto_si_congela(conn, tmp_path):
    # Sonda 9: «niente da estrarre» è una risposta: si congela e il testo non torna in coda.
    _proponi(conn, tmp_path)
    sha = json.loads((FIX / "risposta_estrai.json").read_text(encoding="utf-8"))["sha256"]
    assert agents.ingest(conn, _scrivi(tmp_path, _estrai(sha, [])), "m") == {"facts": 0, "rejects": 0}
    assert conn.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 1
    assert _proponi(conn, tmp_path / "di-nuovo") == []


# --- schema, congelamento, versioni -----------------------------------------------

def test_json_malformato_rifiutato_intero(conn, tmp_path):
    _proponi(conn, tmp_path)
    prima = _stato(conn)
    tronco = tmp_path / "tronco.json"
    tronco.write_text((FIX / "risposta_estrai.json").read_text(encoding="utf-8")[:80], encoding="utf-8")
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(conn, tronco, "m")
    assert e.value.reason == "json_malformato"
    with pytest.raises(agents.AnswerRejected):
        agents.ingest(conn, _risposta(tmp_path, "risposta_estrai.json", extra=1), "m")
    d = json.loads((FIX / "risposta_estrai.json").read_text(encoding="utf-8"))
    d["facts"][0]["note"] = "in più"
    with pytest.raises(agents.AnswerRejected):
        agents.ingest(conn, _scrivi(tmp_path, d, "chiave_fatto.json"), "m")
    with pytest.raises(agents.AnswerRejected):
        agents.ingest(conn, _risposta(tmp_path, "risposta_valuta.json",
                                      speaker={"name": "x", "role": "pilota esperto"}), "m")
    v = json.loads((FIX / "risposta_valuta.json").read_text(encoding="utf-8"))
    v["reasons"][0]["field"] = "team"
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(conn, _scrivi(tmp_path, v, "campo.json"), "m")
    assert e.value.reason == "schema_errato:reasons[].field"
    with pytest.raises(agents.AnswerRejected):
        agents.ingest(conn, _risposta(tmp_path, "risposta_factcheck.json", verdict="forse"), "m")
    assert _stato(conn) == prima


def test_gia_congelato(conn, tmp_path):
    _proponi(conn, tmp_path)
    agents.ingest(conn, FIX / "risposta_estrai.json", "claude-test")
    prima = _stato(conn)
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(conn, FIX / "risposta_estrai.json", "claude-test")
    assert e.value.reason == "gia_congelato"
    assert _stato(conn) == prima
    # Un altro modello è un'altra chiave.
    assert agents.ingest(conn, FIX / "risposta_estrai.json", "altro-modello") == {"facts": 1, "rejects": 1}


def test_versione_dal_lavoro_non_dal_file(conn, tmp_path, monkeypatch):
    _proponi(conn, tmp_path)  # versione 1
    finta = tmp_path / "prompts"
    finta.mkdir()
    for nome in agents.PROMPT_FILES.values():
        (finta / nome).write_text("prompt_version: 2\n", encoding="utf-8")
    monkeypatch.setattr(agents, "PROMPTS_DIR", finta)
    agents.ingest(conn, FIX / "risposta_estrai.json", "m")
    assert conn.execute("SELECT prompt_version FROM results").fetchall() == [("1",)]


def test_due_versioni_aperte_vince_la_piu_nuova(conn, tmp_path, monkeypatch):
    _proponi(conn, tmp_path)  # versione 1
    finta = tmp_path / "prompts"
    finta.mkdir()
    for nome in agents.PROMPT_FILES.values():
        (finta / nome).write_text("prompt_version: 10\n", encoding="utf-8")
    monkeypatch.setattr(agents, "PROMPTS_DIR", finta)
    _proponi(conn, tmp_path / "v10")
    # Sonda V: solo la versione più alta è aperta; la stessa risposta non si congela due volte.
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(conn, FIX / "risposta_estrai.json", "m")
    assert e.value.reason == "versione_superata"
    v10 = _risposta(tmp_path, "risposta_estrai.json", prompt_version="10")
    agents.ingest(conn, v10, "m")
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(conn, v10, "m")
    assert e.value.reason == "gia_congelato"
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(conn, FIX / "risposta_estrai.json", "m")
    assert e.value.reason == "versione_superata"
    assert conn.execute("SELECT prompt_version, track FROM results").fetchall() == [("10", "imola")]


def test_errore_di_scrittura_non_lascia_nulla(conn, tmp_path):
    # Sonda 5: se una scrittura fallisce a metà, non resta niente.
    _proponi(conn, tmp_path)
    conn.execute("CREATE TRIGGER boom BEFORE INSERT ON rejects BEGIN SELECT RAISE(ABORT, 'boom'); END")
    conn.commit()
    prima = _stato(conn)
    with pytest.raises(sqlite3.DatabaseError):
        agents.ingest(conn, FIX / "risposta_estrai.json", "m")
    assert _stato(conn) == prima


def test_transazione_di_chi_chiama_non_si_tocca(conn, tmp_path):
    # Sonda 6: l'ingest non salva né annulla quello che chi chiama aveva in sospeso.
    _proponi(conn, tmp_path)
    conn.execute("INSERT INTO spend(track, baseline_usd, last_usd, cap_usd) VALUES ('imola', 0, 0, 2)")
    agents.ingest(conn, FIX / "risposta_estrai.json", "m")
    altra = sqlite3.connect(str(tmp_path / "f.sqlite"))
    try:
        assert altra.execute("SELECT COUNT(*) FROM spend").fetchone()[0] == 0
    finally:
        altra.close()
    assert conn.in_transaction
    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM spend").fetchone()[0] == 0
    # Fallito l'ingest, quello che chi chiama ha in sospeso resta.
    conn.execute("INSERT INTO spend(track, baseline_usd, last_usd, cap_usd) VALUES ('imola', 0, 0, 2)")
    with pytest.raises(agents.AnswerRejected):
        agents.ingest(conn, _risposta(tmp_path, "risposta_estrai.json", extra=1), "m")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM spend").fetchone()[0] == 1


# --- rate -----------------------------------------------------------------------

def test_rate_citato_entra(conn, tmp_path):
    _coach(conn, tmp_path)
    assert agents.ingest(conn, FIX / "risposta_valuta.json", "m") == {"facts": 0, "rejects": 0}
    payload = json.loads(conn.execute("SELECT payload_json FROM results WHERE kind='rate'").fetchone()[0])
    assert payload["speaker"] == {"name": "Coach Uno", "role": "coach"}


@pytest.mark.parametrize("cambio, motivo", [
    # Sonda 3: ruolo, tempo e auto inventati senza una citazione.
    ({"reasons": []}, "ruolo_non_citato"),
    ({"speaker": {"name": "Mario Rossi", "role": "anonimo"}, "lap_time": None, "car": None,
      "reasons": []}, "nome_non_citato"),
    ({"lap_time": "1:39.0"}, "tempo_non_citato"),
    ({"car": "Porsche 992 GT3 R"}, "auto_non_citata"),
    # Sonda 3b: una citazione inventata.
    ({"reasons": [{"field": "role", "claim": "races", "quote": "I race in GT World Challenge",
                   "offset": 0}]}, "citazione_assente"),
    ({"reasons": [{"field": "role", "claim": "coach", "quote": "I coach drivers in ACC",
                   "offset": 30}]}, "offset_errato"),
])
def test_rate_senza_citazione_rifiutato_intero(conn, tmp_path, cambio, motivo):
    _coach(conn, tmp_path)
    prima = _stato(conn)
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(conn, _risposta(tmp_path, "risposta_valuta.json", **cambio), "m")
    assert e.value.reason == motivo
    assert _stato(conn) == prima


def test_rate_nome_citato_o_autore(conn, tmp_path):
    _coach(conn, tmp_path)
    # Sonda N2: l'autore della fonte (il canale, l'autore del post) non è chi parla.
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(conn, _risposta(tmp_path, "risposta_valuta.json",
                                      speaker={"name": "Canale Coach", "role": "coach"}), "m1")
    assert e.value.reason == "nome_non_citato"
    # L'autore della riga del testo sì, senza citazione.
    assert agents.ingest(conn, FIX / "risposta_valuta.json", "m1") == {"facts": 0, "rejects": 0}
    # Un nome detto nel testo si cita con field=name.
    sid = _fonte(conn, "https://r/luca")
    body = "Hi, my name is Luca Bianchi and I drive ACC at Imola."
    sha, _ = db.add_text(conn, sid, "comment", "u_luca", body)
    _apri_rate(conn, sha)
    d = {"sha256": sha, "kind": "rate", **ECO, "speaker": {"name": "Luca Bianchi", "role": "anonimo"},
         "lap_time": None, "car": None,
         "reasons": [{"field": "name", "claim": "gives their name",
                      "quote": "my name is Luca Bianchi", "offset": 4}]}
    assert agents.ingest(conn, _scrivi(tmp_path, d, "luca.json"), "m") == {"facts": 0, "rejects": 0}
    d["reasons"][0]["field"] = "car"
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(conn, _scrivi(tmp_path, d, "luca2.json"), "m2")
    assert e.value.reason == "nome_non_citato"


# --- factcheck --------------------------------------------------------------------

KEY = json.loads((FIX / "risposta_factcheck.json").read_text(encoding="utf-8"))["fact_key"]


def test_factcheck_citato_nei_testi_del_lavoro(conn, tmp_path):
    _job_factcheck(conn, KEY, [CORPO])
    assert agents.ingest(conn, FIX / "risposta_factcheck.json", "m") == {"facts": 0, "rejects": 0}
    assert conn.execute("SELECT kind, sha256 FROM results").fetchall() == [("factcheck", KEY)]


def test_factcheck_rifiutato_intero(conn, tmp_path):
    # Sonda 4: un fact_key mai proposto, una citazione da un testo fuori dal lavoro,
    # un offset sbagliato e una citazione inventata: niente si congela.
    db.add_text(conn, _fonte(conn, "https://r/monza", track="monza"), "comment", "m",
                "At the Ascari chicane you stay flat out in sixth.")
    prima = _stato(conn)
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(conn, _risposta(tmp_path, "risposta_factcheck.json", fact_key="deadbeef"), "m")
    assert e.value.reason == "lavoro_ignoto"
    _job_factcheck(conn, KEY, [CORPO])
    prima = _stato(conn)
    for cambio, motivo in [({"quote": "you stay flat out in", "offset": 22}, "citazione_assente"),
                           ({"offset": 999}, "offset_errato"),
                           ({"quote": "totally made up words here", "offset": 0}, "citazione_assente")]:
        with pytest.raises(agents.AnswerRejected) as e:
            agents.ingest(conn, _risposta(tmp_path, "risposta_factcheck.json", **cambio), "m")
        assert e.value.reason == motivo
    assert _stato(conn) == prima


# --- comando ----------------------------------------------------------------------

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


def test_cli_errore_inatteso_passa_al_prossimo(conn, tmp_path, capsys, monkeypatch):
    dbp = tmp_path / "f.sqlite"
    fonti.main(["--db", str(dbp), "pending", "--kind", "extract", "--track", "imola",
                "--out", str(tmp_path / "cli")])
    vera = agents.ingest
    visti = []

    def finta(c, path, model):
        visti.append(Path(path).name)
        if len(visti) == 1:
            raise KeyError("guasto")
        return vera(c, path, model)

    monkeypatch.setattr(agents, "ingest", finta)
    rotto = _scrivi(tmp_path, {}, "primo.json")
    assert fonti.main(["--db", str(dbp), "ingest", "--model", "m", str(rotto),
                       str(FIX / "risposta_estrai.json")]) == 1
    assert visti == ["primo.json", "risposta_estrai.json"]
    err = capsys.readouterr().err
    assert "primo.json: errore inatteso (KeyError)" in err
    assert conn.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 1


def test_lavoro_ricorda_la_pista(tmp_path, monkeypatch):
    # Sonda T: lo stesso testo proposto per due piste; ognuna ha il suo lavoro.
    from tools.fonti import vocab
    monkeypatch.setitem(vocab.CORNERS, "monza", vocab.CORNERS["imola"])  # curve finte per Monza
    c = db.open_db(tmp_path / "f.sqlite")
    sha, _ = db.add_text(c, _fonte(c, "https://r/i"), "comment", "x", CORPO)
    db.add_text(c, _fonte(c, "https://r/m", track="monza"), "comment", "y", CORPO)
    _proponi(c, tmp_path, track="imola")
    _proponi(c, tmp_path, track="monza")
    assert sorted(t for (t,) in c.execute("SELECT track FROM jobs")) == ["imola", "monza"]
    assert agents.ingest(c, _scrivi(tmp_path, _estrai(sha, [FATTO])), "m") == {"facts": 1, "rejects": 0}
    assert c.execute("SELECT track FROM results").fetchall() == [("imola",)]
    assert c.execute("SELECT track, author FROM facts").fetchall() == [("imola", "x")]
    # Imola è fatto, Monza resta da fare.
    assert agents.pending(c, "extract", "imola", tmp_path / "ri") == []
    assert len(agents.pending(c, "extract", "monza", tmp_path / "rm")) == 1
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(c, _scrivi(tmp_path, _estrai(sha, [FATTO], track="spa"), "spa.json"), "m")
    assert e.value.reason == "lavoro_ignoto"
    c.close()


def test_database_vecchio_riceve_la_pista(tmp_path):
    p = tmp_path / "vecchio.sqlite"
    v = sqlite3.connect(str(p))
    v.execute("CREATE TABLE results(id INTEGER PRIMARY KEY, sha256 TEXT, kind TEXT, prompt_version TEXT,"
              " model TEXT, payload_json TEXT, frozen_at TEXT, UNIQUE(sha256, kind, prompt_version, model))")
    v.commit()
    v.close()
    c = db.open_db(p)
    assert "track" in {r[1] for r in c.execute("PRAGMA table_info(results)")}
    c.close()


RATE_BODY = ("I am not a coach. At Acque Minerali I go down to third gear. "
             "I coach drivers in ACC and the Tosa kerb is fine.")


def _r(field, quote):
    return {"field": field, "claim": "c", "quote": quote, "offset": RATE_BODY.index(quote)}


@pytest.mark.parametrize("speaker, car, reasons, motivo", [
    # Sonda N1: una citazione vera che non dice nulla del ruolo.
    ({"name": "", "role": "coach"}, None, [_r("role", "I go down to third")], "ruolo_non_citato"),
    # Una parola del ruolo negata non prova il ruolo.
    ({"name": "", "role": "coach"}, None, [_r("role", "I am not a coach")], "ruolo_non_citato"),
    # Sonda N3: il nome è una curva, anche se citato o se è l'autore della riga.
    ({"name": "Acque Minerali", "role": "anonimo"}, None, [_r("name", "At Acque Minerali I")],
     "nome_non_citato"),
    ({"name": "Tosa Racer", "role": "anonimo"}, None, [], "nome_non_citato"),
    # Sonda N4: l'auto è un pezzo del consiglio.
    ({"name": "", "role": "anonimo"}, "third gear", [_r("car", "down to third gear")], "auto_non_citata"),
    ({"name": "", "role": "anonimo"}, "the Tosa kerb", [_r("car", "and the Tosa kerb is")],
     "auto_non_citata"),
])
def test_rate_ruolo_nome_auto_veri(tmp_path, speaker, car, reasons, motivo):
    c = db.open_db(tmp_path / "f.sqlite")
    sha, _ = db.add_text(c, _fonte(c, "https://r/n", author="op_user"), "comment", "Tosa Racer", RATE_BODY)
    _apri_rate(c, sha)
    d = {"sha256": sha, "kind": "rate", **ECO, "speaker": speaker, "lap_time": None, "car": car,
         "reasons": reasons}
    prima = _stato(c)
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(c, _scrivi(tmp_path, d), "m")
    assert e.value.reason == motivo
    assert _stato(c) == prima
    # Con un ruolo provato dalle parole giuste la valutazione entra.
    ok = {**d, "speaker": {"name": "", "role": "coach"}, "car": None,
          "reasons": [_r("role", "I coach drivers in ACC")]}
    assert agents.ingest(c, _scrivi(tmp_path, ok, "ok.json"), "m") == {"facts": 0, "rejects": 0}
    c.close()


def test_factcheck_non_si_conferma_da_solo(conn, tmp_path):
    # Sonda 4d: la citazione sta solo nel testo da cui viene il fatto.
    own = json.loads((FIX / "risposta_estrai.json").read_text(encoding="utf-8"))["sha256"]
    _job_factcheck(conn, KEY, [(own, CORPO)], own=[own])
    prima = _stato(conn)
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(conn, FIX / "risposta_factcheck.json", "m")
    assert e.value.reason == "autoconferma"
    assert _stato(conn) == prima


def test_factcheck_conferma_da_un_altro_testo(conn, tmp_path):
    own = json.loads((FIX / "risposta_estrai.json").read_text(encoding="utf-8"))["sha256"]
    altro = "Second opinion: I go down to third gear there too."
    q = "I go down to third gear"
    _job_factcheck(conn, KEY, [(own, CORPO), ("altro", altro)], own=[own])
    d = json.loads((FIX / "risposta_factcheck.json").read_text(encoding="utf-8"))
    d.update(quote=q, offset=altro.index(q))
    assert agents.ingest(conn, _scrivi(tmp_path, d), "m") == {"facts": 0, "rejects": 0}


def test_pending_factcheck_elenca_le_fonti_del_fatto(conn, tmp_path, monkeypatch):
    _proponi(conn, tmp_path)
    agents.ingest(conn, FIX / "risposta_estrai.json", "m")
    own = json.loads((FIX / "risposta_estrai.json").read_text(encoding="utf-8"))["sha256"]
    altro = "Second opinion: at Acque Minerali I go down to third gear there too."
    sha2, _ = db.add_text(conn, _fonte(conn, "https://r/altro-acc"), "comment", "u_due", altro)
    _finto_consensus(monkeypatch, [{"value": "3", "authors": [], "sources": []}])
    job = json.loads(agents.pending(conn, "factcheck", "imola", tmp_path / "fc")[0].read_text(encoding="utf-8"))
    assert job["fact_sha256s"] == [own]
    assert job["fact_authors"] == ["reddit:u_uno"]
    assert sorted(t["sha256"] for t in job["texts"]) == sorted([own, sha2])
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(conn, FIX / "risposta_factcheck.json", "m")
    assert e.value.reason == "autoconferma"


# --- round 3 ------------------------------------------------------------------------

def _rate_job(c, tmp_path, body, author="x"):
    sha, _ = db.add_text(c, _fonte(c, f"https://r/{abs(hash(body))}"), "comment", author, body)
    _apri_rate(c, sha)
    return sha


def _rate(sha, body, role="anonimo", role_q=None, name="", lap=None, lap_q=None, name_q=None):
    reasons = []
    for field, q in (("role", role_q), ("lap_time", lap_q), ("name", name_q)):
        if q:
            reasons.append({"field": field, "claim": "c", "quote": q, "offset": body.index(q)})
    return {"sha256": sha, "kind": "rate", **ECO, "speaker": {"name": name, "role": role},
            "lap_time": lap, "car": None, "reasons": reasons}


@pytest.mark.parametrize("body, role, quote", [
    # Sonde H1-H5: una parola del ruolo non detta in prima persona non prova nulla.
    ("The racing line through Tosa goes wide on exit.", "pilota", "The racing line through Tosa"),
    ("I use the Coach Dave setup at Imola for practice.", "coach", "I use the Coach Dave"),
    ("My coach told me to brake later at Rivazza.", "coach", "My coach told me to"),
    ("In the race yesterday I was slow at Piratella.", "pilota", "In the race yesterday I"),
    ("Watch this team video about Variante Alta lines.", "pilota", "Watch this team video"),
    ("Il mio coach dice di frenare tardi alla Tosa.", "coach", "Il mio coach dice di"),
    ("I am not a driver coach, just a fan.", "coach", "I am not a driver coach"),
])
def test_ruolo_solo_in_prima_persona(tmp_path, body, role, quote):
    c = db.open_db(tmp_path / "f.sqlite")
    sha = _rate_job(c, tmp_path, body)
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(c, _scrivi(tmp_path, _rate(sha, body, role, quote)), "m")
    assert e.value.reason == "ruolo_non_citato"
    assert _stato(c)["results"] == 0
    c.close()


@pytest.mark.parametrize("body, role, quote", [
    ("I'm a driver coach and Imola is my home track.", "coach", "I'm a driver coach"),
    ("I am an instructor at a sim school, Imola weekly.", "coach", "I am an instructor at"),
    ("Faccio l'istruttore di guida e Imola la conosco.", "coach", "Faccio l'istruttore di guida"),
    ("I race in GT World Challenge and Imola is tough.", "pilota", "I race in GT World"),
    ("Corro nel campionato italiano su ACC da due anni.", "pilota", "Corro nel campionato italiano"),
])
def test_ruolo_detto_in_prima_persona(tmp_path, body, role, quote):
    c = db.open_db(tmp_path / "f.sqlite")
    sha = _rate_job(c, tmp_path, body)
    assert agents.ingest(c, _scrivi(tmp_path, _rate(sha, body, role, quote)), "m") == {"facts": 0, "rejects": 0}
    c.close()


@pytest.mark.parametrize("lap, quote", [
    ("third", "down to third gear today."),   # sonda H6
    ("1:41", "my best lap is 1:41 or 101.2"),
    ("101.2", "my best lap is 1:41 or 101.2"),
])
def test_tempo_sul_giro_nel_formato(tmp_path, lap, quote):
    c = db.open_db(tmp_path / "f.sqlite")
    body = "At Acque Minerali I go down to third gear today. And my best lap is 1:41 or 101.2 here."
    sha = _rate_job(c, tmp_path, body)
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(c, _scrivi(tmp_path, _rate(sha, body, lap=lap, lap_q=quote)), "m")
    assert e.value.reason == "tempo_non_citato"
    c.close()


def test_tempo_sul_giro_valido(tmp_path):
    c = db.open_db(tmp_path / "f.sqlite")
    body = "On ACC my best lap at Imola is 1:41,234 in the evening."
    sha = _rate_job(c, tmp_path, body)
    d = _rate(sha, body, lap="1:41,234", lap_q="my best lap at Imola is 1:41,234")
    assert agents.ingest(c, _scrivi(tmp_path, d), "m") == {"facts": 0, "rejects": 0}
    c.close()


@pytest.mark.parametrize("name, quote, ok", [
    ("Honestly", "Honestly I go flat through", False),   # sonda H7
    ("Marco Neri", "Marco Neri says brake later", False),
    ("Marco Neri", "I'm Marco Neri and I", True),
    ("Marco Neri", "mi chiamo Marco Neri e", True),
    ("Marco", "my name is Marco Neri", True),           # il nome di battesimo detto basta
])
def test_nome_solo_dopo_una_presentazione(tmp_path, name, quote, ok):
    c = db.open_db(tmp_path / "f.sqlite")
    body = ("Honestly I go flat through the Tamburello chicane. Marco Neri says brake later. "
            "I'm Marco Neri and I race. Ciao, mi chiamo Marco Neri e guido. Yes my name is Marco Neri ok.")
    sha = _rate_job(c, tmp_path, body)
    d = _rate(sha, body, name=name, name_q=quote)
    if ok:
        assert agents.ingest(c, _scrivi(tmp_path, d), "m") == {"facts": 0, "rejects": 0}
    else:
        with pytest.raises(agents.AnswerRejected) as e:
            agents.ingest(c, _scrivi(tmp_path, d), "m")
        assert e.value.reason == "nome_non_citato"
    c.close()


def test_nome_da_autore_del_testo_resta(tmp_path):
    # Sonda H8: l'autore della riga basta per il nome, il ruolo detto in prima persona entra.
    c = db.open_db(tmp_path / "f.sqlite")
    body = "I coach drivers in ACC at Imola every week."
    sha = _rate_job(c, tmp_path, body, author="x")
    d = _rate(sha, body, "coach", "I coach drivers in ACC", name="x")
    assert agents.ingest(c, _scrivi(tmp_path, d), "m") == {"facts": 0, "rejects": 0}
    c.close()


def test_factcheck_senza_fonti_del_fatto_rifiutato(conn, tmp_path):
    _job_factcheck(conn, KEY, [CORPO], own=())
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(conn, FIX / "risposta_factcheck.json", "m")
    assert e.value.reason == "fonti_del_fatto_ignote"
    # Anche un payload senza la chiave.
    conn.execute("UPDATE jobs SET payload_json=? WHERE kind='factcheck'",
                 (json.dumps({"texts": [{"sha256": "t0", "body": CORPO, "meta": []}]}),))
    conn.commit()
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(conn, FIX / "risposta_factcheck.json", "m")
    assert e.value.reason == "fonti_del_fatto_ignote"
    assert _stato(conn)["results"] == 0


def test_factcheck_stesso_autore_altro_testo_autoconferma(conn, tmp_path):
    altro = "Second opinion: I go down to third gear there too."
    q = "I go down to third gear"
    _job_factcheck(conn, KEY, [("proprio", CORPO, "u_uno"), ("altro", altro, "U_Uno")],
                   own=["proprio"], own_authors=["reddit:u_uno"])
    d = json.loads((FIX / "risposta_factcheck.json").read_text(encoding="utf-8"))
    d.update(quote=q, offset=altro.index(q))
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(conn, _scrivi(tmp_path, d), "m")
    assert e.value.reason == "autoconferma"


def _finto_consensus(monkeypatch, values):
    import types

    import tools.fonti as pacchetto
    finto = types.ModuleType("tools.fonti.consensus")
    finto.build = lambda c, track: [{"corner": "Acque Minerali", "type": "gear", "state": "verificato",
                                     "values": values, "fact_key": KEY}]
    monkeypatch.setitem(sys.modules, "tools.fonti.consensus", finto)
    monkeypatch.setattr(pacchetto, "consensus", finto, raising=False)


@pytest.mark.parametrize("values", [
    [],                    # sonde 4c/4d: la voce non ha valori
    [{"val": "3"}],        # sonda F1: la forma della voce è cambiata
    [{"value": "4"}],      # nessun fatto con quel valore
])
def test_pending_factcheck_senza_fonti_si_ferma(conn, tmp_path, monkeypatch, values):
    _proponi(conn, tmp_path)
    agents.ingest(conn, FIX / "risposta_estrai.json", "m")
    _finto_consensus(monkeypatch, values)
    with pytest.raises(RuntimeError, match="fonti del fatto"):
        agents.pending(conn, "factcheck", "imola", tmp_path / "fc")
    assert conn.execute("SELECT COUNT(*) FROM jobs WHERE kind='factcheck'").fetchone()[0] == 0


# --- round 4 ------------------------------------------------------------------------

@pytest.mark.parametrize("body, role, quote", [
    # Sonde P1-P8: forme generiche, un «insegno» qualsiasi, parole riferite da altri.
    ("Honestly I'm a sim racer and Tosa is hard.", "pilota", "I'm a sim racer and"),
    ("Io corro con la Ferrari alla Tosa di solito.", "pilota", "Io corro con la Ferrari"),
    ("I race in public lobbies at Imola mostly.", "pilota", "I race in public lobbies"),
    ("Oggi ti insegno a frenare alla Rivazza bene.", "coach", "Oggi ti insegno a frenare"),
    ("He always says I am a driving coach lol.", "coach", "says I am a driving coach"),
    ("Sono un pilota della domenica su ACC.", "pilota", "Sono un pilota della domenica"),
    ("Corro in ACC da due anni ormai.", "pilota", "Corro in ACC da due"),
    # «sono pilota» senza campionato né team nella citazione.
    ("Sono un pilota di ACC e corro a Imola.", "pilota", "Sono un pilota di"),
    # Il campionato più in là di sei parole non conta.
    ("I race in lobbies most nights and weekends with friends in a championship.", "pilota",
     "I race in lobbies most nights and weekends with friends in a championship"),
    # Le parole riferite: virgolette nella citazione o «said» nelle sei parole prima.
    ('My friend wrote "I am a driving coach for ACC" yesterday.', "coach",
     '"I am a driving coach'),
    ("My friend Marco said that I am a driving coach for ACC.", "coach", "I am a driving coach"),
    ("Secondo lui sono un pilota del campionato LFM, magari.", "pilota",
     "sono un pilota del campionato LFM"),
    ("According to Marco I race in the LFM championship.", "pilota", "I race in the LFM championship"),
])
def test_ruolo_generico_o_riferito_rifiutato(tmp_path, body, role, quote):
    c = db.open_db(tmp_path / "f.sqlite")
    sha = _rate_job(c, tmp_path, body)
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(c, _scrivi(tmp_path, _rate(sha, body, role, quote)), "m")
    assert e.value.reason == "ruolo_non_citato"
    assert _stato(c)["results"] == 0
    c.close()


@pytest.mark.parametrize("body, role, quote", [
    ("I race in the LFM championship at Imola.", "pilota", "I race in the LFM championship"),
    ("Corro per il team Rossi su ACC da anni.", "pilota", "Corro per il team Rossi"),
    ("I drive for Scuderia Blu in ACC.", "pilota", "I drive for Scuderia Blu"),
    ("I'm a driver for a GTWC esports team.", "pilota", "I'm a driver for a GTWC"),
    ("Sono un pilota del campionato LFM su ACC.", "pilota", "Sono un pilota del campionato"),
    ("Io insegno guida sportiva a Imola.", "coach", "Io insegno guida sportiva"),
    ("Da anni insegno ai piloti GT come frenare.", "coach", "Da anni insegno ai piloti"),
])
def test_ruolo_con_campionato_team_o_guida(tmp_path, body, role, quote):
    c = db.open_db(tmp_path / "f.sqlite")
    sha = _rate_job(c, tmp_path, body)
    assert agents.ingest(c, _scrivi(tmp_path, _rate(sha, body, role, quote)), "m") == {"facts": 0, "rejects": 0}
    c.close()


# --- round 5 ------------------------------------------------------------------------

@pytest.mark.parametrize("body, quote, ok", [
    # «I teach» e «I coach» senza chi o cosa si allena non dicono che chi parla è un coach.
    ("Today I teach you to brake at Rivazza.", "I teach you to brake", False),
    ("Honestly I coach myself with replays at Imola.", "I coach myself with replays", False),
    ("I teach you to brake later, then we talk about racing.",
     "I teach you to brake later, then we talk about racing", False),   # oltre 4 parole
    ("I coach drivers in ACC at Imola every week.", "I coach drivers in ACC", True),
    ("I teach sim racing on weekends at Imola.", "I teach sim racing on", True),
    ("I teach racecraft to students at Imola.", "I teach racecraft to students", True),
    ("I coach a few clients in ACC.", "I coach a few clients", True),
    # Sonda P7: l'apostrofo tipografico si normalizza già, la presentazione vera entra.
    ("Hi, I\u2019m a driver coach for ACC players.", "I\u2019m a driver coach for", True),
])
def test_coach_dice_chi_allena(tmp_path, body, quote, ok):
    c = db.open_db(tmp_path / "f.sqlite")
    sha = _rate_job(c, tmp_path, body)
    d = _rate(sha, body, "coach", quote)
    if ok:
        assert agents.ingest(c, _scrivi(tmp_path, d), "m") == {"facts": 0, "rejects": 0}
    else:
        with pytest.raises(agents.AnswerRejected) as e:
            agents.ingest(c, _scrivi(tmp_path, d), "m")
        assert e.value.reason == "ruolo_non_citato"
    c.close()


# --- correzione finale ------------------------------------------------------------

def _fatto_di_u_uno(conn, tmp_path, monkeypatch):
    """Il fatto della fixture (Acque Minerali, gear 3, da u_uno) come voce verificata."""
    _proponi(conn, tmp_path)
    agents.ingest(conn, FIX / "risposta_estrai.json", "m")
    _finto_consensus(monkeypatch, [{"value": "3", "authors": [], "sources": []}])
    return json.loads((FIX / "risposta_estrai.json").read_text(encoding="utf-8"))["sha256"]


def test_respinto_puo_citare_il_testo_del_fatto(conn, tmp_path):
    # I2: il veto legge il contesto del fatto stesso, ironia o correzione dello stesso autore.
    own = json.loads((FIX / "risposta_estrai.json").read_text(encoding="utf-8"))["sha256"]
    altro = "Second opinion: third gear works there too, at Acque Minerali."
    _job_factcheck(conn, KEY, [(own, CORPO, "u_uno"), ("altro", altro)], own=[own],
                   own_authors=["reddit:u_uno"])
    d = json.loads((FIX / "risposta_factcheck.json").read_text(encoding="utf-8"))
    d.update(verdict="respinto", reason="it is ironic", quote="I go down to third gear",
             offset=CORPO.index("I go down to third gear"))
    assert agents.ingest(conn, _scrivi(tmp_path, d), "m-a") == {"facts": 0, "rejects": 0}
    # Lo stesso testo per un confermato resta un'autoconferma.
    d.update(verdict="confermato")
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(conn, _scrivi(tmp_path, d, "c.json"), "m-b")
    assert e.value.reason == "autoconferma"
    # Un respinto con una citazione fuori dai testi del lavoro no.
    d.update(verdict="respinto", quote="totally made up words here", offset=0)
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(conn, _scrivi(tmp_path, d, "x.json"), "m-c")
    assert e.value.reason == "citazione_assente"


def test_factcheck_senza_testo_indipendente_non_si_scrive(conn, tmp_path, monkeypatch, capsys):
    # M3: con i soli testi del fatto un confermato è impossibile: il lavoro non si scrive.
    _fatto_di_u_uno(conn, tmp_path, monkeypatch)
    db.add_text(conn, _fonte(conn, "https://r/stesso"), "comment", "U_Uno",
                "Again at Acque Minerali I go down to third gear.")
    assert agents.pending(conn, "factcheck", "imola", tmp_path / "fc") == []
    assert conn.execute("SELECT COUNT(*) FROM jobs WHERE kind='factcheck'").fetchone()[0] == 0
    err = capsys.readouterr().err
    assert "Acque Minerali" in err and "indipendente" in err


LUNGO = ("Hello there. Nice day today. I like fast cars. At Acque Minerali I take third. "
         "Then relax a bit. Lunch is great. Some more words. Coffee time now. "
         "Later at Acque Minerali stay left. Bye now.")


def test_factcheck_taglia_i_testi_attorno_alla_curva(conn, tmp_path, monkeypatch):
    own = _fatto_di_u_uno(conn, tmp_path, monkeypatch)
    sha, _ = db.add_text(conn, _fonte(conn, "https://r/lungo"), "comment", "u_lungo", LUNGO)
    job = json.loads(agents.pending(conn, "factcheck", "imola", tmp_path / "fc")[0].read_text(encoding="utf-8"))
    corpi = {t["sha256"]: t["body"] for t in job["texts"]}
    assert corpi[own] == CORPO
    assert corpi[sha] == ("I like fast cars. At Acque Minerali I take third. Then relax a bit."
                          "\n[…]\n"
                          "Coffee time now. Later at Acque Minerali stay left. Bye now.")
    # La citazione si cerca nel testo del lavoro, tagliato com'è.
    d = json.loads((FIX / "risposta_factcheck.json").read_text(encoding="utf-8"))
    q = "At Acque Minerali I take third"
    d.update(fact_key=KEY, quote=q, offset=corpi[sha].index(q))
    assert agents.ingest(conn, _scrivi(tmp_path, d), "m") == {"facts": 0, "rejects": 0}


def test_extract_solo_testi_che_nominano_una_curva(conn, tmp_path):
    # M4: «Thanks!» non darà mai un fatto: niente lavoro.
    db.add_text(conn, _fonte(conn, "https://r/grazie"), "comment", "u_grazie", "Thanks a lot, mate!")
    db.add_text(conn, _fonte(conn, "https://r/tamb"), "comment", "u_t", "Tamburelo is fast.")
    nomi = sorted(json.loads(p.read_text(encoding="utf-8"))["body"] for p in _proponi(conn, tmp_path))
    assert nomi == [CORPO, "Tamburelo is fast."]


def test_rate_solo_per_autori_con_un_fatto(conn, tmp_path):
    # M4: il rate serve solo a pesare un fatto, quindi viene dopo l'estrazione.
    db.add_text(conn, _fonte(conn, "https://r/senza"), "comment", "u_senza",
                "At Tosa I coach drivers in ACC.")
    assert agents.pending(conn, "rate", "imola", tmp_path / "r0") == []
    _proponi(conn, tmp_path)
    agents.ingest(conn, FIX / "risposta_estrai.json", "m")
    jobs = [json.loads(p.read_text(encoding="utf-8"))
            for p in agents.pending(conn, "rate", "imola", tmp_path / "r1")]
    assert [j["body"] for j in jobs] == [CORPO]


def test_citazione_salvata_come_nel_testo(tmp_path):
    # L5: si salva il pezzo del testo, non la stringa dell'agente.
    c = db.open_db(tmp_path / "f.sqlite")
    body = "At Acque Minerali I go DOWN  to Third gear and it works."
    sha, _ = db.add_text(c, _fonte(c, "https://r/maiusc"), "comment", "x", body)
    _proponi(c, tmp_path)
    f = dict(FATTO, quote="down to third gear", offset=body.index("DOWN"))
    assert agents.ingest(c, _scrivi(tmp_path, _estrai(sha, [f])), "m")["facts"] == 1
    assert c.execute("SELECT quote FROM facts").fetchone() == ("DOWN  to Third gear",)
    c.close()


def test_lavori_vecchi_tolti_dalla_cartella(conn, tmp_path):
    # L11: un lavoro congelato non resta nella cartella, quelli di un'altra pista sì.
    out = tmp_path / "jobs"
    vecchio = agents.pending(conn, "extract", "imola", out)[0]
    monza = out / "extract-aaaaaaaaaaaa.job.json"
    monza.write_text(json.dumps({"kind": "extract", "track": "monza"}), encoding="utf-8")
    rate = out / "rate-bbbbbbbbbbbb.job.json"
    rate.write_text(json.dumps({"kind": "rate", "track": "imola"}), encoding="utf-8")
    agents.ingest(conn, FIX / "risposta_estrai.json", "m")
    assert agents.pending(conn, "extract", "imola", out) == []
    assert not vecchio.exists() and monza.exists() and rate.exists()


@pytest.mark.parametrize("testo, ok", [
    ("```json\n{risposta}\n```\n", True),
    ("```\n{risposta}\n```", True),
    ("Here it is:\n```json\n{risposta}\n```", False),
    ("```json\n{risposta}\n```\n```json\n{risposta}\n```", False),
])
def test_risposta_in_un_recinto(conn, tmp_path, testo, ok):
    # M5: un solo recinto ```json si toglie, il resto è JSON malformato.
    _proponi(conn, tmp_path)
    p = tmp_path / "f.answer.json"
    p.write_text(testo.replace("{risposta}", (FIX / "risposta_estrai.json").read_text(encoding="utf-8")),
                 encoding="utf-8")
    if ok:
        assert agents.ingest(conn, p, "m") == {"facts": 1, "rejects": 1}
    else:
        with pytest.raises(agents.AnswerRejected) as e:
            agents.ingest(conn, p, "m")
        assert e.value.reason == "json_malformato"


def test_cli_ingest_dice_verdetto_e_ruolo(conn, tmp_path, capsys):
    # L12: per rate e factcheck si stampa il ruolo o il verdetto, non «fatti 0».
    dbp = tmp_path / "f.sqlite"
    _coach(conn, tmp_path)
    _job_factcheck(conn, KEY, [CORPO])
    assert fonti.main(["--db", str(dbp), "ingest", "--model", "m", str(FIX / "risposta_valuta.json"),
                       str(FIX / "risposta_factcheck.json")]) == 0
    out = capsys.readouterr().out
    assert "risposta_valuta.json: ruolo coach, nome Coach Uno." in out
    assert "risposta_factcheck.json: verdetto confermato." in out


def test_prompt_senza_pista_scritta():
    # L13: la pista la dice il lavoro.
    for nome in agents.PROMPT_FILES.values():
        testo = (agents.PROMPTS_DIR / nome).read_text(encoding="utf-8")
        assert "Imola" not in testo, nome


def test_una_regola_una_copia():
    # L6, L7: ordine delle versioni, autore e versione più nuova stanno solo in db.
    import inspect

    from tools.fonti import consensus, export, vocab
    for m in (agents, consensus, export):
        src = inspect.getsource(m)
        for nome in ("def _version_order", "def _author_id", "def _newest", "consensus._newest"):
            assert nome not in src, (m.__name__, nome)
    for nome in ("normalize", "negated", "negative_sense"):
        assert not hasattr(vocab, nome)
    assert "che non c'è ancora" not in inspect.getsource(agents)
    assert "(sha256, kind, prompt_version, model, track)" in agents.__doc__


@pytest.mark.parametrize("verdetto", ["confermato", "respinto"])
@pytest.mark.parametrize("q", ["Then relax a bit.\n[…]\nCoffee time now",
                               "[…] Coffee time now. Later"])
def test_factcheck_citazione_oltre_il_taglio(conn, tmp_path, monkeypatch, verdetto, q):
    # 8: una citazione che contiene «[…]» o passa sopra il taglio non regge.
    _fatto_di_u_uno(conn, tmp_path, monkeypatch)
    sha, _ = db.add_text(conn, _fonte(conn, "https://r/lungo"), "comment", "u_lungo", LUNGO)
    job = json.loads(agents.pending(conn, "factcheck", "imola", tmp_path / "fc")[0].read_text(encoding="utf-8"))
    corpo = {t["sha256"]: t["body"] for t in job["texts"]}[sha]
    d = json.loads((FIX / "risposta_factcheck.json").read_text(encoding="utf-8"))
    d.update(fact_key=KEY, verdict=verdetto, quote=q, offset=corpo.index(q.split()[0]))
    with pytest.raises(agents.AnswerRejected) as e:
        agents.ingest(conn, _scrivi(tmp_path, d), "m")
    assert e.value.reason == "citazione_oltre_taglio"


# --- 10/11: la verifica si rifà --------------------------------------------------------

def test_reverify_rifa_fatti_e_scarti_e_rispetta_la_pista(conn, tmp_path):
    _proponi(conn, tmp_path)
    agents.ingest(conn, FIX / "risposta_estrai.json", "claude-test")
    prima = conn.execute("SELECT corner, type, value, quote FROM facts").fetchall()
    assert agents.reverify(conn, "imola") == {"facts": 1, "rejects": 1}
    assert conn.execute("SELECT corner, type, value, quote FROM facts").fetchall() == prima
    assert agents.reverify(conn, "imola") == {"facts": 1, "rejects": 1}   # ripetibile
    conn.execute("UPDATE sources SET track=NULL")
    conn.commit()
    assert agents.reverify(conn, "imola") == {"facts": 0, "rejects": 0}
    assert conn.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 1   # la risposta resta

