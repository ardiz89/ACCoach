"""Esportazione dei fatti confermati e pagina di controllo (tools/fonti.export, .review).

I dati di prova passano dalla strada vera: `pending` propone il lavoro, la risposta
dell'agente scritta qui la congela `ingest`. Niente righe a mano in `facts` o `results`.
"""
import html
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tools.fonti import agents, consensus, db, export, fonti, review  # noqa: E402
import tono  # noqa: E402

AM = "Acque Minerali"
RIV = "Rivazza"
TOSA = "Tosa"
LUNGA = ("you lift a little after the kink and then you go down to third gear and you "
         "roll the speed through the middle while the car settles on the exit")


class Banco:
    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.conn = db.open_db(tmp_path / "f.sqlite")
        self.n = 0

    def _dir(self, nome):
        self.n += 1
        return self.tmp / f"{nome}-{self.n}"

    def fonte(self, url, platform, author):
        self.conn.execute(
            "INSERT OR IGNORE INTO sources(platform, url, author, title, published, game, track,"
            " meta_json) VALUES (?,?,?,?,?,?,?,?)",
            (platform, url, author, "t", "2026-05-01", "acc", "imola", "{}"))
        self.conn.commit()
        return self.conn.execute("SELECT id FROM sources WHERE url=?", (url,)).fetchone()[0]

    def testo(self, url, author, body, facts=(), platform="reddit", segments=None):
        kind = "transcript" if platform == "youtube" else "comment"
        sha, _ = db.add_text(self.conn, self.fonte(url, platform, author), kind, author, body,
                             segments)
        if facts:
            agents.pending(self.conn, "extract", "imola", self._dir("je"))
            out = [{"corner": c, "type": t, "value": v, "quote": q, "offset": body.index(q)}
                   for c, t, v, q in facts]
            p = self._dir("r").with_suffix(".json")
            p.write_text(json.dumps({"sha256": sha, "kind": "extract", "facts": out,
                                     "prompt_version": agents.prompt_version("extract"),
                                     "track": "imola"}), encoding="utf-8")
            r = agents.ingest(self.conn, p, "m")
            assert r["rejects"] == 0, f"fatto scartato: {body!r}"
        return sha

    def factcheck(self, corner, type_, verdict, body, quote, model="m"):
        """Il controllo di una voce `verificato`, citando `quote` dal testo `body`."""
        agents.pending(self.conn, "factcheck", "imola", self._dir("jf"))
        e = next(e for e in consensus.build(self.conn, "imola")
                 if e["corner"] == corner and e["type"] == type_)
        assert e["state"] == "verificato" and e["fact_key"]
        d = {"fact_key": e["fact_key"], "kind": "factcheck", "track": "imola",
             "prompt_version": agents.prompt_version("factcheck"), "verdict": verdict,
             "reason": f"il testo dice {verdict}", "quote": quote, "offset": body.index(quote)}
        p = self._dir("fc").with_suffix(".json")
        p.write_text(json.dumps(d), encoding="utf-8")
        agents.ingest(self.conn, p, model)
        return e["fact_key"]


@pytest.fixture
def b(tmp_path):
    banco = Banco(tmp_path)
    yield banco
    banco.conn.close()


TERZO_AM = "In my league at Acque Minerali the quick guys go down to third gear every lap."
TERZO_RIV = "In my league at Rivazza the quick guys go down to second gear every lap."


def _riempi(b):
    """AM/gear confermato, Rivazza/gear respinto, Tosa/gear singolo, Rivazza/line descrittivo."""
    b.testo("https://www.youtube.com/watch?v=abc", "Uno",
            "At Acque Minerali I go down to third gear and it works great.",
            [(AM, "gear", "3", "down to third gear")], platform="youtube",
            segments=[{"text": "At Acque Minerali I go down to third gear and it works great.",
                       "start_s": 95.4}])
    b.testo("https://r/2", "due", "Honestly at Acque Minerali I go down to third gear and it works.",
            [(AM, "gear", "3", "down to third gear")])
    b.testo("https://r/3", "tre", "At Rivazza I go down to second gear and it works great.",
            [(RIV, "gear", "2", "down to second gear")])
    b.testo("https://r/4", "quattro", "Honestly at Rivazza I go down to second gear and it works.",
            [(RIV, "gear", "2", "down to second gear")])
    b.testo("https://r/5", "cinque", "At Tosa I go down to second gear and it works great.",
            [(TOSA, "gear", "2", "down to second gear")])
    b.testo("https://r/6", "sei", "At Rivazza keep it tight on the way in and let it run wide.",
            [(RIV, "line", "keep it tight on the way in", "keep it tight on the way in")])
    b.testo("https://r/7", "sette", TERZO_AM)
    b.testo("https://r/8", "otto", TERZO_RIV)
    am = b.factcheck(AM, "gear", "confermato", TERZO_AM, "the quick guys go down to third gear")
    riv = b.factcheck(RIV, "gear", "respinto", TERZO_RIV, "the quick guys go down to second gear")
    return am, riv


def _carica(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_export_solo_confermati(b, tmp_path):
    _riempi(b)
    out = tmp_path / "trackfacts"
    assert export.export(b.conn, "imola", out) == 1
    d = _carica(out / "imola.json")
    assert d["track"] == "imola" and d["version"] == 1
    assert [(f["corner"], f["type"], f["value"], f["n"]) for f in d["facts"]] == [(AM, "gear", "3", 2)]
    urls = [s["url"] for s in d["facts"][0]["sources"]]
    assert urls == ["https://r/2", "https://www.youtube.com/watch?v=abc"]
    yt = d["facts"][0]["sources"][1]
    assert yt["start_s"] == 95.4 and yt["quote"] == "down to third gear"


def test_export_verificato_senza_controllo_non_esce(b, tmp_path):
    b.testo("https://r/1", "uno", "At Acque Minerali I go down to third gear and it works great.",
            [(AM, "gear", "3", "down to third gear")])
    b.testo("https://r/2", "due", "Honestly at Acque Minerali I go down to third gear and it works.",
            [(AM, "gear", "3", "down to third gear")])
    assert export.export(b.conn, "imola", tmp_path / "o") == 0
    assert _carica(tmp_path / "o" / "imola.json")["facts"] == []


def test_export_un_modello_respinge_e_basta(b, tmp_path):
    _riempi(b)
    b.factcheck(AM, "gear", "respinto", TERZO_AM, "the quick guys go down to third gear", model="m2")
    assert export.export(b.conn, "imola", tmp_path / "o") == 0


def test_export_identico_due_volte(b, tmp_path):
    _riempi(b)
    export.export(b.conn, "imola", tmp_path / "a")
    export.export(b.conn, "imola", tmp_path / "b")
    uno = (tmp_path / "a" / "imola.json").read_bytes()
    assert uno == (tmp_path / "b" / "imola.json").read_bytes()
    assert uno.endswith(b"}\n") and b"\r\n" not in uno
    d = json.loads(uno)
    assert uno.decode("utf-8") == json.dumps(d, sort_keys=True, ensure_ascii=False, indent=1) + "\n"


def test_citazione_15_parole(b, tmp_path):
    assert len(LUNGA.split()) == 30
    for url, autore, pre in (("https://r/1", "uno", "At Acque Minerali"),
                             ("https://r/2", "due", "Honestly at Acque Minerali")):
        b.testo(url, autore, f"{pre} {LUNGA}.", [(AM, "gear", "3", LUNGA)])
    b.testo("https://r/7", "sette", TERZO_AM)
    b.factcheck(AM, "gear", "confermato", TERZO_AM, "the quick guys go down to third gear")
    assert export.export(b.conn, "imola", tmp_path / "o") == 1
    src = _carica(tmp_path / "o" / "imola.json")["facts"][0]["sources"]
    assert [s["quote"] for s in src] == [" ".join(LUNGA.split()[:15])] * 2


def _hrefs(page):
    return [html.unescape(h) for h in re.findall(r'href="([^"]*)"', page)]


def test_review_sezioni_e_link(b, tmp_path):
    _riempi(b)
    b.conn.execute("INSERT INTO spend(track, baseline_usd, last_usd, cap_usd) VALUES ('imola', 1.0, 1.54, 2.0)")
    b.conn.commit()
    p = review.render(b.conn, "imola", tmp_path / "pagina.html")
    page = p.read_text(encoding="utf-8")
    for h in ("Verificati", "Contesi", "Una fonte sola", "Respinti dal controllo", "Descrittivi"):
        assert f">{h}<" in page
    assert "https://www.youtube.com/watch?v=abc&t=95s" in _hrefs(page)
    assert "https://r/2" in _hrefs(page)
    assert "0,54 $" in page and "2,00 $" in page
    # Le curve nell'ordine del catalogo.
    assert page.index(f">{TOSA}<") < page.index(f">{AM}<") < page.index(f">{RIV}<")
    # Nessun testo grezzo intero, né in chiaro né in forma escapata.
    for body in (TERZO_AM, "At Acque Minerali I go down to third gear and it works great."):
        assert body not in page and html.escape(body) not in page
    assert "<script" not in page and "http://" not in page.split("<body", 1)[0]
    assert "2 persone" in page and "1 persona" in page


def test_review_url_senza_query_e_scarti(b, tmp_path):
    b.testo("https://youtu.be/xyz", "Uno",
            "At Tosa I go down to second gear and it works great.",
            [(TOSA, "gear", "2", "down to second gear")], platform="youtube",
            segments=[{"text": "At Tosa I go down to second gear and it works great.",
                       "start_s": 61.9}])
    # Un fatto che il verificatore scarta finisce negli scarti con il suo motivo.
    body = "At Tosa it is a fun corner overall."
    sha, _ = db.add_text(b.conn, b.fonte("https://r/9", "reddit", "nove"), "comment", "nove", body)
    agents.pending(b.conn, "extract", "imola", tmp_path / "je")
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"sha256": sha, "kind": "extract", "track": "imola",
                             "prompt_version": agents.prompt_version("extract"),
                             "facts": [{"corner": TOSA, "type": "gear", "value": "2",
                                        "quote": "not in the text at all", "offset": 0}]}),
                 encoding="utf-8")
    assert agents.ingest(b.conn, p, "m")["rejects"] == 1
    page = review.render(b.conn, "imola", tmp_path / "x.html").read_text(encoding="utf-8")
    assert "https://youtu.be/xyz?t=61s" in _hrefs(page)
    assert "citazione_assente" in page
    assert "Non hai ancora speso" in page


def test_review_escapa_le_fonti(b, tmp_path):
    autore = "<b>tre</b>"
    b.testo("https://r/1?a=1&b=<x>", autore, "At Tosa I go down to second gear and it works great.",
            [(TOSA, "gear", "2", "down to second gear")])
    page = review.render(b.conn, "imola", tmp_path / "x.html").read_text(encoding="utf-8")
    assert "<b>tre</b>" not in page and "<x>" not in page
    assert html.escape(autore) + " (reddit)" in page


def test_review_rispetta_il_tono(b, tmp_path):
    _riempi(b)
    page = review.render(b.conn, "imola", tmp_path / "x.html").read_text(encoding="utf-8")
    for frase in review.TESTI:
        assert tono.violations(frase, "it") == [], frase


def test_cli_export_e_review(b, tmp_path, capsys):
    _riempi(b)
    b.conn.close()
    b.conn = db.open_db(tmp_path / "f.sqlite")
    out = tmp_path / "facts"
    assert fonti.main(["--db", str(tmp_path / "f.sqlite"), "export", "--track", "imola",
                       "--out", str(out)]) == 0
    assert _carica(out / "imola.json")["facts"][0]["corner"] == AM
    pagina = tmp_path / "rev.html"
    assert fonti.main(["--db", str(tmp_path / "f.sqlite"), "review", "--track", "imola",
                       "--out", str(pagina)]) == 0
    assert ">Verificati<" in pagina.read_text(encoding="utf-8")
    assert "1" in capsys.readouterr().out
