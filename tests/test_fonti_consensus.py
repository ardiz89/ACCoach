"""Consenso fra autori indipendenti (tools/fonti.consensus).

I dati di prova passano dalla strada vera: `pending` propone il lavoro, una risposta
dell'agente scritta qui la congela `ingest`, che verifica ogni fatto. Niente righe
inserite a mano in `facts` o in `results`.
"""
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.fonti import agents, consensus, db, fonti  # noqa: E402

AM = "Acque Minerali"
MARCIA = "down to third gear"
FRENA_100 = "brake at the 100 board"
FRENA_150 = "brake at the 150 board"


class Banco:
    """Un database di prova e i passi veri per riempirlo."""

    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.conn = db.open_db(tmp_path / "f.sqlite")
        self.n = 0

    def _dir(self, nome):
        self.n += 1
        return self.tmp / f"{nome}-{self.n}"

    def fonte(self, url, platform="reddit", author="a", game="acc", track="imola"):
        self.conn.execute(
            "INSERT OR IGNORE INTO sources(platform, url, author, title, published, game, track,"
            " meta_json) VALUES (?,?,?,?,?,?,?,?)",
            (platform, url, author, "t", "2026-05-01", game, track, "{}"))
        self.conn.commit()
        return self.conn.execute("SELECT id FROM sources WHERE url=?", (url,)).fetchone()[0]

    def testo(self, url, author, body, facts, platform="reddit", model="m"):
        """Un testo con i suoi fatti `(type, value, quote[, corner])`, estratti e congelati."""
        kind = "transcript" if platform == "youtube" else "comment"
        sha, _ = db.add_text(self.conn, self.fonte(url, platform, author), kind, author, body)
        self.estrai(sha, body, facts, model)
        return sha

    def estrai(self, sha, body, facts, model="m"):
        agents.pending(self.conn, "extract", "imola", self._dir("je"))
        version = agents.prompt_version("extract")
        out = []
        for f in facts:
            type_, value, quote = f[:3]
            out.append({"corner": f[3] if len(f) > 3 else AM, "type": type_, "value": value,
                        "quote": quote, "offset": body.index(quote)})
        p = self._dir("r").with_suffix(".json")
        p.write_text(json.dumps({"sha256": sha, "kind": "extract", "facts": out,
                                 "prompt_version": version, "track": "imola"}), encoding="utf-8")
        r = agents.ingest(self.conn, p, model)
        assert r["rejects"] == 0, f"fatto scartato dal verificatore: {body!r}"

    def valuta(self, sha, body, role="coach", role_q=None, name="", lap=None, lap_q=None):
        agents.pending(self.conn, "rate", "imola", self._dir("jr"))
        reasons = []
        for field, q in (("role", role_q), ("lap_time", lap_q)):
            if q:
                reasons.append({"field": field, "claim": "c", "quote": q, "offset": body.index(q)})
        d = {"sha256": sha, "kind": "rate", "prompt_version": agents.prompt_version("rate"),
             "track": "imola", "speaker": {"name": name, "role": role}, "lap_time": lap,
             "car": None, "reasons": reasons}
        p = self._dir("v").with_suffix(".json")
        p.write_text(json.dumps(d), encoding="utf-8")
        agents.ingest(self.conn, p, "m")

    def coach(self, url, author, facts, name=True):
        body = f"I coach drivers in ACC every week. At Acque Minerali you {FRENA_100}."
        sha = self.testo(url, author, body, facts or [("brake", "board:100", FRENA_100)])
        self.valuta(sha, body, "coach", "I coach drivers in ACC", name=author if name else "")
        return sha

    def build(self):
        return consensus.build(self.conn, "imola")


@pytest.fixture
def b(tmp_path):
    banco = Banco(tmp_path)
    yield banco
    banco.conn.close()


def _voce(entries, corner=AM, type_="gear"):
    got = [e for e in entries if e["corner"] == corner and e["type"] == type_]
    assert len(got) == 1, entries
    return got[0]


def _gear(b, url, author, prefix="At", platform="reddit"):
    body = f"{prefix} Acque Minerali I go {MARCIA} and it works great."
    return b.testo(url, author, body, [("gear", "3", MARCIA)], platform=platform)


def _brake(b, url, author, board=100, prefix="At"):
    q = FRENA_100 if board == 100 else FRENA_150
    body = f"{prefix} Acque Minerali you {q}."
    return b.testo(url, author, body, [("brake", f"board:{board}", q)])


# --- verificato -------------------------------------------------------------------

def test_due_autori_verificato(b):
    _gear(b, "https://r/1", "uno")
    _gear(b, "https://r/2", "due", prefix="Honestly at")
    e = _voce(b.build())
    assert e["state"] == "verificato"
    assert e["fact_key"] == hashlib.sha256(f"imola|{AM}|gear|3".encode("utf-8")).hexdigest()
    assert e["values"][0]["value"] == "3"
    assert e["values"][0]["authors"] == ["reddit:due", "reddit:uno"]
    # Sulla frenata due autori non bastano: serve un coach con un nome.
    _brake(b, "https://r/3", "tre")
    _brake(b, "https://r/4", "quattro", prefix="Honestly at")
    assert _voce(b.build(), type_="brake")["state"] == "singolo"
    b.coach("https://yt/c", "Coach Uno", None)
    e = _voce(b.build(), type_="brake")
    assert e["state"] == "verificato" and e["values"][0]["value"] == "board:100"
    assert "reddit:coach uno" in e["values"][0]["authors"]


def test_brake_senza_affidabile_resta_singolo(b):
    _brake(b, "https://r/1", "uno")
    _brake(b, "https://r/2", "due", prefix="Honestly at")
    e = _voce(b.build(), type_="brake")
    assert e["state"] == "singolo" and e["fact_key"] is None


def test_brake_coach_senza_nome_non_basta(b):
    _brake(b, "https://r/1", "uno")
    b.coach("https://r/c", "Coach Anonimo", None, name=False)
    assert _voce(b.build(), type_="brake")["state"] == "singolo"


def test_brake_pilota_serve_il_tempo(b):
    _brake(b, "https://r/1", "uno")
    body = f"I race in the LFM championship with friends. At Acque Minerali you {FRENA_100}."
    sha = b.testo("https://r/p", "Pilota Due", body, [("brake", "board:100", FRENA_100)])
    b.valuta(sha, body, "pilota", "I race in the LFM championship", name="Pilota Due")
    assert _voce(b.build(), type_="brake")["state"] == "singolo"


def test_brake_pilota_con_nome_e_tempo(b):
    _brake(b, "https://r/1", "uno")
    body = (f"I race in the LFM championship and my best is 1:41.2 here. "
            f"At Acque Minerali you {FRENA_100}.")
    sha = b.testo("https://r/p", "Pilota Due", body, [("brake", "board:100", FRENA_100)])
    b.valuta(sha, body, "pilota", "I race in the LFM championship", name="Pilota Due",
             lap="1:41.2", lap_q="my best is 1:41.2")
    assert _voce(b.build(), type_="brake")["state"] == "verificato"


def test_valutazione_da_un_altro_testo_dello_stesso_autore(b):
    # Il ruolo l'ha detto in un altro testo della stessa pista: vale per l'autore.
    _brake(b, "https://r/1", "uno")
    _brake(b, "https://r/2", "Coach Uno", prefix="Honestly at")
    body = "I coach drivers in ACC every week at Imola."
    sid = b.fonte("https://r/3", author="Coach Uno")
    sha, _ = db.add_text(b.conn, sid, "comment", "Coach Uno", body)
    b.valuta(sha, body, "coach", "I coach drivers in ACC", name="Coach Uno")
    assert _voce(b.build(), type_="brake")["state"] == "verificato"


# --- indipendenza ---------------------------------------------------------------------

def test_stesso_autore_una_fonte(b):
    _gear(b, "https://yt/v1", "Canale X", platform="youtube")
    _gear(b, "https://yt/v2", "canale x", prefix="Honestly at", platform="youtube")
    e = _voce(b.build())
    assert e["state"] == "singolo" and e["fact_key"] is None
    assert e["values"][0]["authors"] == ["youtube:canale x"]
    assert [s["url"] for s in e["values"][0]["sources"]] == ["https://yt/v1", "https://yt/v2"]


def test_stesso_nome_su_piattaforme_diverse_sono_due(b):
    _gear(b, "https://yt/v1", "marco", platform="youtube")
    _gear(b, "https://r/2", "marco", prefix="Honestly at")
    assert _voce(b.build())["state"] == "verificato"


def test_testo_identico_di_due_account_conta_uno(b):
    body = f"At Acque Minerali I go {MARCIA} and it works great."
    sha, _ = db.add_text(b.conn, b.fonte("https://r/1"), "comment", "uno", body)
    db.add_text(b.conn, b.fonte("https://r/2"), "comment", "due", body)
    b.estrai(sha, body, [("gear", "3", MARCIA)])
    e = _voce(b.build())
    assert e["values"][0]["authors"] == ["reddit:due", "reddit:uno"]
    assert e["state"] == "singolo"


def test_due_modelli_stesso_autore_conta_uno(b):
    body = f"At Acque Minerali I go {MARCIA} and it works great."
    sha = b.testo("https://r/1", "uno", body, [("gear", "3", MARCIA)], model="m1")
    b.estrai(sha, body, [("gear", "3", MARCIA)], model="m2")
    e = _voce(b.build())
    assert e["state"] == "singolo" and e["values"][0]["authors"] == ["reddit:uno"]
    assert len(e["values"][0]["sources"]) == 1


def test_solo_la_versione_piu_recente(b, tmp_path, monkeypatch):
    _gear(b, "https://r/1", "uno")
    _gear(b, "https://r/2", "due", prefix="Honestly at")
    assert _voce(b.build())["state"] == "verificato"
    nuovi = tmp_path / "prompts"
    nuovi.mkdir()
    for nome in agents.PROMPT_FILES.values():
        (nuovi / nome).write_text("prompt_version: 2\nIstruzioni.\n", encoding="utf-8")
    monkeypatch.setattr(agents, "PROMPTS_DIR", nuovi)
    agents.pending(b.conn, "extract", "imola", tmp_path / "v2")
    # I risultati della versione 1 sono superati: finché la 2 non arriva, niente.
    assert b.build() == []
    body = f"At Acque Minerali I go {MARCIA} and it works great."
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    b.estrai(sha, body, [("gear", "3", MARCIA)])
    e = _voce(b.build())
    assert e["state"] == "singolo" and e["values"][0]["authors"] == ["reddit:uno"]


# --- conteso e singolo -----------------------------------------------------------

def test_conteso(b):
    _brake(b, "https://r/1", "uno", 100)
    _brake(b, "https://r/2", "due", 100, prefix="Honestly at")
    _brake(b, "https://r/3", "tre", 150)
    _brake(b, "https://r/4", "quattro", 150, prefix="Honestly at")
    e = _voce(b.build(), type_="brake")
    assert e["state"] == "conteso" and e["fact_key"] is None
    assert [v["value"] for v in e["values"]] == ["board:100", "board:150"]


def test_conteso_due_contro_un_affidabile(b):
    _gear(b, "https://r/1", "uno")
    _gear(b, "https://r/2", "due", prefix="Honestly at")
    body = "I coach drivers in ACC every week. At Acque Minerali I go down to fourth gear."
    sha = b.testo("https://r/c", "Coach Uno", body, [("gear", "4", "down to fourth gear")])
    b.valuta(sha, body, "coach", "I coach drivers in ACC", name="Coach Uno")
    e = _voce(b.build())
    assert e["state"] == "conteso"
    assert [v["value"] for v in e["values"]] == ["3", "4"]


def test_due_contro_un_anonimo_resta_verificato(b):
    _gear(b, "https://r/1", "uno")
    _gear(b, "https://r/2", "due", prefix="Honestly at")
    body = "At Acque Minerali I go down to fourth gear."
    b.testo("https://r/3", "tre", body, [("gear", "4", "down to fourth gear")])
    e = _voce(b.build())
    assert e["state"] == "verificato"
    assert [v["value"] for v in e["values"]] == ["3", "4"]


def test_descrittivo(b):
    q = "Stay left through Acque Minerali"
    body = f"{q} and you will be fine."
    b.testo("https://r/1", "uno", body, [("line", q.lower(), q)])
    b.testo("https://r/2", "due", "Honestly, " + body, [("line", q.lower(), q)])
    e = _voce(b.build(), type_="line")
    assert e["state"] == "descrittivo" and e["fact_key"] is None


# --- gioco, pista, ordine -----------------------------------------------------------

def test_non_acc_escluso(b):
    _gear(b, "https://r/1", "uno")
    _gear(b, "https://r/2", "due", prefix="Honestly at")
    # La fonte riclassificata dopo l'estrazione: i suoi fatti non contano più.
    b.conn.execute("UPDATE sources SET game='altro' WHERE url='https://r/2'")
    b.conn.commit()
    e = _voce(b.build())
    assert e["state"] == "singolo" and e["values"][0]["authors"] == ["reddit:uno"]
    b.conn.execute("UPDATE sources SET game='altro' WHERE url='https://r/1'")
    b.conn.commit()
    assert b.build() == []


def test_altra_pista_esclusa(b):
    _gear(b, "https://r/1", "uno")
    assert consensus.build(b.conn, "monza") == []


def _riempi(b, ordine):
    passi = {
        "g1": lambda: _gear(b, "https://r/1", "uno"),
        "g2": lambda: _gear(b, "https://r/2", "due", prefix="Honestly at"),
        "b1": lambda: _brake(b, "https://r/3", "tre", 150),
        "t1": lambda: b.testo("https://r/4", "quattro", f"At Tosa you {FRENA_100}.",
                              [("brake", "board:100", FRENA_100, "Tosa")]),
        "c1": lambda: b.coach("https://r/5", "Coach Uno", None),
    }
    for k in ordine:
        passi[k]()


def test_ordinamento_deterministico(tmp_path):
    uscite = []
    for i, ordine in enumerate((["g1", "g2", "b1", "t1", "c1"], ["c1", "t1", "b1", "g2", "g1"])):
        (tmp_path / str(i)).mkdir()
        banco = Banco(tmp_path / str(i))
        _riempi(banco, ordine)
        uscite.append(json.dumps(banco.build(), sort_keys=True, ensure_ascii=False))
        banco.conn.close()
    assert uscite[0] == uscite[1]
    entries = json.loads(uscite[0])
    # Le curve nell'ordine della pista: la Tosa viene prima delle Acque Minerali.
    assert [(e["corner"], e["type"]) for e in entries] == [
        ("Tosa", "brake"), (AM, "brake"), (AM, "gear")]


def test_forma_della_voce(b):
    _gear(b, "https://r/1", "uno")
    e = b.build()[0]
    assert set(e) == {"corner", "type", "state", "values", "fact_key"}
    v = e["values"][0]
    assert set(v) == {"value", "authors", "sources"}
    assert set(v["sources"][0]) == {"url", "start_s", "quote"}
    assert v["sources"][0] == {"url": "https://r/1", "start_s": None, "quote": MARCIA}


# --- il fact-check legge il consenso ---------------------------------------------------

def test_pending_factcheck_usa_verificati(b, tmp_path):
    _gear(b, "https://r/1", "uno")
    _gear(b, "https://r/2", "due", prefix="Honestly at")       # gear: verificato
    _brake(b, "https://r/3", "tre", 100)                       # brake: singolo
    b.testo("https://r/4", "quattro", f"At Tosa you {FRENA_100}.",
            [("brake", "board:100", FRENA_100, "Tosa")])
    b.testo("https://r/5", "cinque", f"Honestly at Tosa you {FRENA_100}.",
            [("brake", "board:100", FRENA_100, "Tosa")])
    b.testo("https://r/6", "sei", f"At Tosa you {FRENA_150}.",
            [("brake", "board:150", FRENA_150, "Tosa")])
    b.testo("https://r/7", "sette", f"Honestly at Tosa you {FRENA_150}.",
            [("brake", "board:150", FRENA_150, "Tosa")])           # Tosa brake: conteso
    stati = {(e["corner"], e["type"]): e["state"] for e in b.build()}
    assert stati == {(AM, "gear"): "verificato", (AM, "brake"): "singolo",
                     ("Tosa", "brake"): "conteso"}
    jobs = agents.pending(b.conn, "factcheck", "imola", tmp_path / "fc")
    assert len(jobs) == 1
    job = json.loads(jobs[0].read_text(encoding="utf-8"))
    chiave = hashlib.sha256(f"imola|{AM}|gear|3".encode("utf-8")).hexdigest()
    assert job["sha256"] == chiave and job["fact"]["fact_key"] == chiave
    assert job["fact"]["state"] == "verificato"
    assert len(job["fact_sha256s"]) == 2
    assert job["fact_authors"] == ["reddit:due", "reddit:uno"]


def test_pending_factcheck_su_build_vero_ha_le_fonti(b, tmp_path):
    _gear(b, "https://r/1", "uno")
    _gear(b, "https://r/2", "due", prefix="Honestly at")
    _brake(b, "https://r/3", "tre", 100)
    _brake(b, "https://r/4", "quattro", 100, prefix="Honestly at")
    b.coach("https://r/5", "Coach Uno", None)
    jobs = agents.pending(b.conn, "factcheck", "imola", tmp_path / "fc")
    assert len(jobs) == 2
    for p in jobs:
        job = json.loads(p.read_text(encoding="utf-8"))
        assert job["fact_sha256s"] and job["fact_authors"]


# --- il comando -------------------------------------------------------------------------

def test_cli_consensus(b, capsys):
    _gear(b, "https://r/1", "uno")
    _gear(b, "https://r/2", "due", prefix="Honestly at")
    _brake(b, "https://r/3", "tre", 150)
    assert fonti.main(["--db", str(b.tmp / "f.sqlite"), "consensus", "--track", "imola"]) == 0
    out = capsys.readouterr().out
    assert AM in out and "verificato" in out and "singolo" in out
    assert "board:150" in out


def test_cli_consensus_vuoto(tmp_path, capsys):
    assert fonti.main(["--db", str(tmp_path / "f.sqlite"), "consensus", "--track", "imola"]) == 0
    assert "Nessun fatto" in capsys.readouterr().out
