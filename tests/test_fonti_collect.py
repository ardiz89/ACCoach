"""Raccolta (tools/fonti.collect) con Apify finto dalle fixture. Mai in rete."""
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.fonti import apify, collect, db  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "fonti"
TOK = "tok-di-prova"
PIANO = [
    {"actor": "streamers/youtube-scraper", "input": {"searchQueries": ["ACC Imola"]},
     "max_items": 5, "platform": "youtube"},
    {"actor": "trudax/reddit-scraper-lite", "input": {"searches": ["Imola"]},
     "max_items": 10, "platform": "reddit"},
]


class Finto:
    """Apify finto con l'API asincrona: si avvia la corsa, si aspetta, si legge il dataset.

    `attese`: quante risposte «RUNNING» dà ogni corsa prima di finire. `per_run`: quanto
    costa una corsa (usageTotalUsd). `ritardo`: l'uso del conto non si muove (Apify lo
    aggiorna in ritardo).
    """

    def __init__(self, uso=0.54, per_run=0.0, attese=0, items=None, ritardo=False,
                 stato="SUCCEEDED", schema=None):
        self.uso, self.per_run, self.attese, self.ritardo = uso, per_run, attese, ritardo
        self.stato, self.schema = stato, schema or {}
        self.items = items or {}
        self.avvii, self.chiamate, self.corse = [], [], {}

    def _items(self, actor):
        if actor in self.items:
            return self.items[actor]
        nome = "apify_youtube.json" if "youtube" in actor else "apify_reddit.json"
        return json.loads((FIX / nome).read_text(encoding="utf-8"))

    def __call__(self, method, url, headers, body):
        assert TOK not in url and headers["Authorization"] == f"Bearer {TOK}"
        self.chiamate.append((method, url))
        path = url.split("?")[0]
        if path.endswith("/users/me/limits"):
            return 200, json.dumps({"data": {"current": {"monthlyUsageUsd": self.uso}}}).encode()
        m = re.search(r"/acts/([^/]+)/runs$", path)
        if m and method == "POST":
            rid = f"corsa{len(self.avvii) + 1}"
            self.avvii.append((url, json.loads(body)))
            self.corse[rid] = {"actor": m.group(1), "attese": self.attese}
            return 201, json.dumps({"data": {"id": rid, "status": "RUNNING"}}).encode()
        m = re.search(r"/actor-runs/([^/]+)/dataset/items$", path)
        if m:
            return 200, json.dumps(self._items(self.corse[m.group(1)]["actor"])).encode()
        m = re.search(r"/actor-runs/([^/]+)$", path)
        if m:
            c = self.corse[m.group(1)]
            if c["attese"] > 0:
                c["attese"] -= 1
                return 200, json.dumps({"data": {"id": m.group(1), "status": "RUNNING"}}).encode()
            if not c.get("finita"):
                c["finita"] = True
                if not self.ritardo:
                    self.uso += self.per_run
            return 200, json.dumps({"data": {"id": m.group(1), "status": self.stato,
                                             "usageTotalUsd": self.per_run}}).encode()
        m = re.search(r"/acts/([^/]+)/builds/default$", path)
        if m:
            if m.group(1) not in self.schema:
                return 404, b"{}"
            return 200, json.dumps({"data": {"actorDefinition": {
                "input": self.schema[m.group(1)]}}}).encode()
        return 404, b"{}"


def _conn(tmp_path):
    return db.open_db(tmp_path / "f.sqlite")


def _client(finto):
    return apify.Apify(TOK, http=finto)


def test_raccolta_da_fixture(tmp_path):
    conn, f = _conn(tmp_path), Finto()
    r = collect.collect(conn, _client(f), "imola", PIANO)
    assert r["sources"] == 3 and r["texts"] == 4 and r["spent_usd"] == 0
    assert "maxItems=5" in f.avvii[0][0] and "streamers~youtube-scraper" in f.avvii[0][0]
    assert f.avvii[0][1] == PIANO[0]["input"]
    t = conn.execute("SELECT kind, author, segments_json FROM texts WHERE kind='transcript'").fetchall()
    assert len(t) == 1 and t[0][1] == "Pilota Uno"
    segs = json.loads(t[0][2])
    assert segs[1] == {"start_s": 95.4, "text": "Stay left through Acque Minerali"}
    assert {a for (a,) in conn.execute("SELECT author FROM texts WHERE kind='comment'")} == {"u_due", "u_tre"}
    giochi = dict(conn.execute("SELECT url, game FROM sources").fetchall())
    assert giochi["https://www.youtube.com/watch?v=vid001"] == "acc"
    assert giochi["https://www.youtube.com/watch?v=vid002"] == "altro"
    assert conn.execute("SELECT COUNT(*) FROM sources WHERE track='imola'").fetchone()[0] == 3
    # Il dataset si legge per id della corsa.
    assert any("/actor-runs/corsa1/dataset/items" in u for _, u in f.chiamate)
    assert not any("run-sync" in u for _, u in f.chiamate)


def test_raccolta_rilanciata_non_duplica(tmp_path):
    conn, f = _conn(tmp_path), Finto()
    collect.collect(conn, _client(f), "imola", PIANO)
    prima = db.count_rows(conn)
    r = collect.collect(conn, _client(f), "imola", PIANO)
    assert r["texts"] == 0 and r["sources"] == 0
    assert db.count_rows(conn) == prima


def test_rilancio_non_chiama_run(tmp_path):
    conn, f = _conn(tmp_path), Finto()
    collect.collect(conn, _client(f), "imola", PIANO)
    assert len(f.avvii) == 2
    r = collect.collect(conn, _client(f), "imola", PIANO)
    assert len(f.avvii) == 2 and r["skipped"] == 2
    assert conn.execute("SELECT COUNT(*) FROM collect_runs WHERE finished_at IS NOT NULL").fetchone()[0] == 2
    collect.collect(conn, _client(f), "imola", PIANO, force=True)
    assert len(f.avvii) == 4


def test_tetto_a_meta_piano(tmp_path):
    conn, f = _conn(tmp_path), Finto(per_run=2.06)   # la prima voce sfonda il tetto
    with pytest.raises(apify.CapReached):
        collect.collect(conn, _client(f), "imola", PIANO)
    assert len(f.avvii) == 1
    righe = conn.execute("SELECT entry_key FROM collect_runs").fetchall()
    assert righe == [(collect.entry_key(PIANO[0]),)]


def test_errore_di_rete_senza_traceback(tmp_path, monkeypatch, capsys):
    import urllib.error
    from tools.fonti import fonti

    def rotto(self, *a, **k):
        raise urllib.error.URLError("giu")

    monkeypatch.setenv("APIFY_API_TOKEN", TOK)
    monkeypatch.setattr(apify.Apify, "usage_usd", rotto)
    piano = tmp_path / "p.json"
    piano.write_text(json.dumps(PIANO), encoding="utf-8")
    rc = fonti.main(["--db", str(tmp_path / "d"), "collect", "--track", "imola", "--plan", str(piano)])
    err = capsys.readouterr().err
    assert rc == 1 and "Rete" in err and TOK not in err and "Traceback" not in err


# --- I3: un lotto pagato non si perde ------------------------------------------------

def test_corsa_lunga_si_riprende_senza_ripagare(tmp_path):
    conn, f = _conn(tmp_path), Finto(attese=10_000)
    with pytest.raises(apify.RunPending):
        collect.collect(conn, _client(f), "imola", PIANO[:1], polls=3)
    assert len(f.avvii) == 1
    riga = conn.execute("SELECT run_id, finished_at FROM collect_runs").fetchone()
    assert riga == ("corsa1", None)
    f.corse["corsa1"]["attese"] = 0     # intanto su Apify la corsa è finita
    r = collect.collect(conn, _client(f), "imola", PIANO[:1], polls=3)
    assert len(f.avvii) == 1 and r["texts"] == 1
    assert conn.execute("SELECT finished_at IS NOT NULL FROM collect_runs").fetchone() == (1,)


def test_elementi_grezzi_salvati_prima_di_leggerli(tmp_path, monkeypatch):
    conn, f = _conn(tmp_path), Finto()

    def rotto(*a, **k):
        raise KeyError("guasto")

    monkeypatch.setattr(collect, "_reddit", rotto)
    r = collect.collect(conn, _client(f), "imola", PIANO[1:])
    assert r["bad_items"] == 3
    righe = conn.execute("SELECT track, entry_key, item_json FROM raw_items").fetchall()
    assert len(righe) == 3 and {t for t, _, _ in righe} == {"imola"}
    assert {k for _, k, _ in righe} == {collect.entry_key(PIANO[1])}
    assert json.loads(righe[0][2])["dataType"] in ("post", "comment")
    # Rilanciare non duplica le righe grezze.
    collect.collect(conn, _client(f), "imola", PIANO[1:])
    assert conn.execute("SELECT COUNT(*) FROM raw_items").fetchone()[0] == 3


def test_elemento_guasto_non_ferma_il_lotto(tmp_path, capsys):
    items = json.loads((FIX / "apify_reddit.json").read_text(encoding="utf-8"))
    senza_url = {"dataType": "post", "id": None, "username": "u_x", "title": "Imola",
                 "body": "Tosa is slow.", "parsedCommunityName": "ACCompetizione"}
    titolo_nullo = {"dataType": "post", "id": "t3_nul",
                    "url": "https://www.reddit.com/r/ACCompetizione/comments/nul/x/",
                    "username": "u_y", "title": None, "body": "At Tosa I brake late.",
                    "parsedCommunityName": "ACCompetizione"}
    f = Finto(items={"trudax~reddit-scraper-lite": [senza_url, *items, titolo_nullo]})
    conn = _conn(tmp_path)
    r = collect.collect(conn, _client(f), "imola", PIANO[1:])
    assert r["bad_items"] == 1 and r["texts"] == 4
    assert "elemento" in capsys.readouterr().err
    riga = conn.execute("SELECT title FROM sources WHERE url LIKE '%/nul/%'").fetchone()
    assert riga == (None,)
    corpo = conn.execute("SELECT body FROM texts WHERE author='u_y'").fetchone()[0]
    assert corpo == "At Tosa I brake late."


def test_titolo_nullo_youtube(tmp_path):
    item = {"id": "v9", "title": None, "url": "https://www.youtube.com/watch?v=v9",
            "channelName": "C", "subtitles": None}
    f = Finto(items={"streamers~youtube-scraper": [item]})
    conn = _conn(tmp_path)
    collect.collect(conn, _client(f), "imola", PIANO[:1])
    assert conn.execute("SELECT title FROM sources").fetchone() == (None,)


# --- I4: una voce vuota non è finita, --force per una voce sola --------------------

def test_voce_vuota_non_segnata_finita(tmp_path):
    vuoto = [{"id": "v1", "title": "ACC Imola", "url": "https://www.youtube.com/watch?v=v1",
              "channelName": "C", "subtitles": None}]
    f = Finto(items={"streamers~youtube-scraper": vuoto})
    conn = _conn(tmp_path)
    r = collect.collect(conn, _client(f), "imola", PIANO)
    assert r["empty"] == [1]
    fatte = dict(conn.execute("SELECT entry_key, finished_at IS NOT NULL FROM collect_runs"))
    assert fatte == {collect.entry_key(PIANO[0]): 0, collect.entry_key(PIANO[1]): 1}
    # Rilanciare riprende la stessa corsa: non si ripaga.
    r = collect.collect(conn, _client(f), "imola", PIANO)
    assert len(f.avvii) == 2 and r["empty"] == [1] and r["skipped"] == 1
    # Con --force e --only si ripaga quella voce sola.
    collect.collect(conn, _client(f), "imola", PIANO, force=True, only=1)
    assert len(f.avvii) == 3 and "youtube" in f.avvii[-1][0]


def test_only_una_voce(tmp_path):
    conn, f = _conn(tmp_path), Finto()
    collect.collect(conn, _client(f), "imola", PIANO, only=2)
    assert len(f.avvii) == 1 and "reddit" in f.avvii[0][0]
    with pytest.raises(ValueError):
        collect.collect(conn, _client(f), "imola", PIANO, only=3)


def test_cli_voce_vuota_detta_chiara(tmp_path, monkeypatch, capsys):
    from tools.fonti import fonti

    vuoto = [{"id": "v1", "title": "ACC Imola", "url": "https://www.youtube.com/watch?v=v1",
              "channelName": "C", "subtitles": None}]
    f = Finto(items={"streamers~youtube-scraper": vuoto})
    monkeypatch.setenv("APIFY_API_TOKEN", TOK)
    monkeypatch.setattr(apify, "_urllib_http", f)
    piano = tmp_path / "p.json"
    piano.write_text(json.dumps(PIANO), encoding="utf-8")
    rc = fonti.main(["--db", str(tmp_path / "d"), "collect", "--track", "imola", "--plan", str(piano),
                     "--only", "1"])
    out = capsys.readouterr()
    assert rc == 1
    assert "Voce 1" in out.err and "0 testi" in out.err and "check-actors" in out.err


# --- M1: il tetto è duro -------------------------------------------------------------

def _tetto(url):
    return float(re.search(r"maxTotalChargeUsd=([0-9.]+)", url).group(1))


def test_quota_fissa_per_voce(tmp_path):
    conn, f = _conn(tmp_path), Finto(per_run=0.40)
    collect.collect(conn, _client(f), "imola", PIANO)
    assert _tetto(f.avvii[0][0]) == pytest.approx(1.00)      # 2,00 diviso due voci
    assert _tetto(f.avvii[1][0]) == pytest.approx(1.60)      # il resto all'ultima


def test_spesa_letta_dal_run_quando_il_conto_tarda(tmp_path):
    conn, f = _conn(tmp_path), Finto(per_run=1.20, ritardo=True)
    collect.collect(conn, _client(f), "imola", PIANO[:1], cap_usd=2.0)
    # Il conto dice 0 spesi, la corsa 1,20: vale la cifra più alta.
    assert apify.guard(conn, _client(f), "imola", 2.0) == pytest.approx(0.80)
    assert conn.execute("SELECT spent_usd FROM collect_runs").fetchone()[0] == pytest.approx(1.20)
    collect.collect(conn, _client(f), "imola", PIANO, cap_usd=2.0)
    assert _tetto(f.avvii[1][0]) == pytest.approx(0.80)
    with pytest.raises(apify.CapReached):
        apify.guard(conn, _client(f), "imola", 2.0)


def test_corsa_ripresa_non_conta_due_volte(tmp_path):
    conn, f = _conn(tmp_path), Finto(per_run=0.30, ritardo=True, attese=10_000)
    with pytest.raises(apify.RunPending):
        collect.collect(conn, _client(f), "imola", PIANO[:1], polls=1)
    f.corse["corsa1"]["attese"] = 0
    collect.collect(conn, _client(f), "imola", PIANO[:1], polls=1)
    collect.collect(conn, _client(f), "imola", PIANO[:1], polls=1)
    assert conn.execute("SELECT runs_usd FROM spend").fetchone()[0] == pytest.approx(0.30)


# --- M2: la stima nel dry-run --------------------------------------------------------

def test_dry_run_stima(tmp_path, capsys):
    from tools.fonti import fonti

    piano = tmp_path / "p.json"
    piano.write_text(json.dumps([dict(PIANO[0], cost_per_item_usd=0.004, max_items=25),
                                 dict(PIANO[1], cost_per_item_usd=0.0034, max_items=150),
                                 dict(PIANO[1], max_items=1, input={"x": 1})]), encoding="utf-8")
    assert fonti.main(["--db", str(tmp_path / "d"), "collect", "--track", "imola", "--plan",
                       str(piano), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "voce 1" in out and "0.10 USD" in out and "0.51 USD" in out
    assert "stima ignota" in out
    assert "Stima totale: 0.61 USD" in out


def test_piano_imola_ha_il_prezzo():
    piano = json.loads((ROOT / "tools" / "fonti" / "piani" / "imola.json").read_text(encoding="utf-8"))
    prezzi = {v["platform"]: v["cost_per_item_usd"] for v in piano}
    assert prezzi == {"youtube": 0.004, "reddit": 0.0034}


# --- I4: lo schema degli attori -------------------------------------------------------

SCHEMA_YT = {"type": "object", "properties": {
    "searchQueries": {"type": "array"}, "maxResults": {"type": "integer"},
    "downloadSubtitles": {"type": "boolean"},
    "subtitlesFormat": {"type": "string", "enum": ["srt", "vtt", "xml", "plaintext"]},
    "subtitlesLanguage": {"type": "string", "enum": ["any", "en", "it"]}}}


def test_check_actors_trova_chiavi_e_valori(tmp_path):
    piano = [{"platform": "youtube", "actor": "streamers/youtube-scraper", "max_items": 1,
              "input": {"searchQueries": ["a"], "transcriptionAndSubtitle": "downloadSubtitles",
                        "subtitlesFormat": "ass", "downloadSubtitles": "si",
                        "subtitlesLanguage": "en"}},
             {"platform": "reddit", "actor": "nessuno/attore", "max_items": 1, "input": {}}]
    f = Finto(schema={"streamers~youtube-scraper": SCHEMA_YT})
    problemi = collect.check_actors(_client(f), piano)
    testo = "\n".join(problemi)
    assert "transcriptionAndSubtitle" in testo and "sconosciuta" in testo
    assert "«ass»" in testo and "subtitlesFormat" in testo
    assert "downloadSubtitles" in testo and "boolean" in testo
    assert "subtitlesLanguage" not in testo and "searchQueries" not in testo
    assert "nessuno/attore" in testo
    assert not f.avvii and all(m == "GET" for m, _ in f.chiamate)


def test_check_actors_piano_buono(tmp_path, monkeypatch, capsys):
    from tools.fonti import fonti

    piano = tmp_path / "p.json"
    piano.write_text(json.dumps([{"platform": "youtube", "actor": "streamers/youtube-scraper",
                                  "max_items": 1, "input": {"searchQueries": ["a"],
                                                            "downloadSubtitles": True}}]),
                     encoding="utf-8")
    f = Finto(schema={"streamers~youtube-scraper": SCHEMA_YT})
    monkeypatch.setenv("APIFY_API_TOKEN", TOK)
    monkeypatch.setattr(apify, "_urllib_http", f)
    assert fonti.main(["check-actors", "--plan", str(piano)]) == 0
    out = capsys.readouterr()
    assert "Nessun problema" in out.out and TOK not in out.out + out.err


# --- M6: quale gioco -----------------------------------------------------------------

@pytest.mark.parametrize("titolo,desc,sub,atteso", [
    ("ACC Imola hotlap 720S", "", "", "acc"),
    ("Assetto Corsa Competizione guide", "", "", "acc"),
    ("iRacing Imola", "", "", "altro"),
    ("accelerate", "", "", "altro"),
    ("Imola tips", "", "ACCompetizione", "acc"),
    ("AC vs ACC Imola", "", "", "altro"),
    ("ACC vs AC: Imola compared", "", "", "altro"),
    ("Imola AC1 and ACC", "", "", "altro"),
    ("Assetto Corsa 1 vs ACC at Imola", "", "", "altro"),
    ("Imola hotlap", "#acc #simracing #iracing", "", "altro"),     # solo hashtag
    ("Imola hotlap", "ACC version soon", "", "altro"),
    ("AC vs ACC tips", "", "ACCompetizione", "altro"),
])
def test_game_of(titolo, desc, sub, atteso):
    assert collect.game_of(titolo, desc, sub) == atteso


# --- I5: la classe d'auto --------------------------------------------------------------

@pytest.mark.parametrize("testi,atteso", [
    (("ACC Imola GT3 guide", "", ""), "gt3"),
    # N1: la descrizione e il flair non assegnano mai la classe, possono solo toglierla.
    (("Imola hotlap", "Porsche 992 GT3 R setup", ""), "ignota"),
    (("Imola GT4 tips", "", ""), "gt4"),
    (("Imola", "", "GT4"), "ignota"),
    (("GT3 vs GT4 at Imola", "", ""), "ignota"),
    (("Imola guide", "", ""), "ignota"),
    (("Imola gt30 gt3x", "", ""), "ignota"),
])
def test_classe_dalla_fonte(testi, atteso):
    assert collect.car_class_of(*testi) == atteso


def test_classe_salvata_e_commento_eredita_dal_post(tmp_path):
    items = [
        {"dataType": "comment", "id": "t1_c1", "postId": "t3_abc",
         "url": "https://www.reddit.com/r/simracing/comments/abc/comment/c1/",
         "username": "u_due", "body": "I brake at the 100 board.", "parsedCommunityName": "simracing"},
        {"dataType": "post", "id": "t3_abc", "url": "https://www.reddit.com/r/simracing/comments/abc/imola_gt3/",
         "username": "u_uno", "title": "ACC Imola GT3 braking", "body": "Where?", "flair": "Question",
         "parsedCommunityName": "simracing"},
    ]
    f = Finto(items={"trudax~reddit-scraper-lite": items})
    conn = _conn(tmp_path)
    r = collect.collect(conn, _client(f), "imola", PIANO[1:])
    assert r["sources"] == 1
    righe = conn.execute("SELECT url, author, title, game, car_class FROM sources").fetchall()
    assert righe == [("https://www.reddit.com/comments/abc/", "u_uno", "ACC Imola GT3 braking",
                      "acc", "gt3")]
    assert conn.execute("SELECT COUNT(DISTINCT source_id) FROM texts").fetchone()[0] == 1


def test_ordine_degli_elementi_non_conta(tmp_path):
    items = json.loads((FIX / "apify_reddit.json").read_text(encoding="utf-8"))
    righe = []
    for i, ordine in enumerate((items, list(reversed(items)))):
        conn = db.open_db(tmp_path / f"o{i}.sqlite")
        collect.collect(conn, _client(Finto(items={"trudax~reddit-scraper-lite": ordine})),
                        "imola", PIANO[1:])
        righe.append(sorted(conn.execute(
            "SELECT url, author, title, game, car_class FROM sources").fetchall()))
        conn.close()
    assert righe[0] == righe[1]


def test_database_vecchio_riceve_le_colonne(tmp_path):
    p = tmp_path / "vecchio.sqlite"
    v = sqlite3.connect(str(p))
    v.execute("CREATE TABLE sources(id INTEGER PRIMARY KEY, platform TEXT, url TEXT UNIQUE,"
              " author TEXT, title TEXT, published TEXT, game TEXT, track TEXT, meta_json TEXT)")
    v.execute("INSERT INTO sources(platform, url, title, game, track) VALUES"
              " ('youtube', 'https://y/1', 'ACC Imola GT3 guide', 'acc', 'imola')")
    v.execute("CREATE TABLE collect_runs(track TEXT, entry_key TEXT, finished_at TEXT, items INTEGER,"
              " spent_usd REAL, PRIMARY KEY(track, entry_key))")
    v.execute("CREATE TABLE spend(track TEXT PRIMARY KEY, baseline_usd REAL, last_usd REAL, cap_usd REAL)")
    v.commit()
    v.close()
    c = db.open_db(p)
    assert "car_class" in {r[1] for r in c.execute("PRAGMA table_info(sources)")}
    assert "run_id" in {r[1] for r in c.execute("PRAGMA table_info(collect_runs)")}
    assert "runs_usd" in {r[1] for r in c.execute("PRAGMA table_info(spend)")}
    assert c.execute("SELECT car_class FROM sources").fetchone() == ("gt3",)
    assert c.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION == 2
    c.close()



# --- round 2 -------------------------------------------------------------------------

# N1: le cinque sonde della revisione, più i modelli non GT3 di ACC.
@pytest.mark.parametrize("titolo,desc,atteso", [
    ("ACC Imola Porsche 992 GT3 Cup onboard", "", "altra"),
    ("Lamborghini Huracan Super Trofeo EVO2 at Imola ACC", "", "altra"),
    ("ACC Imola guide", "Driving the Ferrari 296 GT3 today", "ignota"),
    ("ACC Imola GT3 hotlap", "Next week the GT4 Alpine A110", "ignota"),
    ("ACC Imola GT3 hotlap", "Also try the Porsche Cup", "ignota"),
    ("Ginetta G55 at Imola, ACC", "", "gt4"),
    ("BMW M2 CS Racing TCX at Imola ACC", "", "altra"),
    ("Ferrari 488 Challenge Evo Imola", "", "altra"),
    ("McLaren 570S at Imola", "", "gt4"),
    ("Porsche 718 Cayman GT4 Clubsport Imola", "", "gt4"),
    ("Maserati MC at Imola", "", "gt4"),
    ("KTM X-Bow at Imola", "", "gt4"),
    ("Imola trofeo GT3", "", "ignota"),
    ("ACC Imola GT2 guide", "", "altra"),
    ("ACC Imola GT3 guide", "#acc #simracing", "gt3"),
])
def test_classe_solo_dal_titolo(titolo, desc, atteso):
    assert collect.car_class_of(titolo, desc, "") == atteso


@pytest.mark.parametrize("corpo,atteso", [
    ("In the GT4 I brake at the 150 board.", "gt4"),
    ("With the 992 Cup I brake at the 100.", "altra"),
    ("GT3 or GT4, brake at the 100.", "ignota"),
    ("I brake at the 100 board.", None),
    ("In the GT3 I brake at the 100 board.", None),   # un testo non assegna la GT3
])
def test_classe_del_testo(corpo, atteso):
    assert collect.text_class_of(corpo) == atteso


def test_commento_che_dice_gt4_ha_la_sua_classe(tmp_path):
    # N2: il post dice GT3, il commento parla di GT4: per i fatti del commento vale GT4.
    items = [
        {"dataType": "post", "id": "t3_abc", "url": "https://www.reddit.com/r/x/comments/abc/t/",
         "username": "u_uno", "title": "ACC Imola GT3 braking", "body": "Where?",
         "parsedCommunityName": "ACCompetizione"},
        {"dataType": "comment", "id": "t1_c1", "postId": "t3_abc",
         "url": "https://www.reddit.com/r/x/comments/abc/t/c1/", "username": "u_due",
         "body": "In my GT4 I brake at the 150 board.", "parsedCommunityName": "ACCompetizione"},
        {"dataType": "comment", "id": "t1_c2", "postId": "t3_abc",
         "url": "https://www.reddit.com/r/x/comments/abc/t/c2/", "username": "u_tre",
         "body": "I brake at the 100 board.", "parsedCommunityName": "ACCompetizione"},
    ]
    conn = _conn(tmp_path)
    collect.collect(conn, _client(Finto(items={"trudax~reddit-scraper-lite": items})), "imola", PIANO[1:])
    assert conn.execute("SELECT car_class FROM sources").fetchall() == [("gt3",)]
    per_testo = dict(conn.execute("SELECT author, car_class FROM texts").fetchall())
    assert per_testo == {"u_uno": None, "u_due": "gt4", "u_tre": None}


def test_database_vecchio_classe_per_testo(tmp_path):
    p = tmp_path / "v.sqlite"
    v = sqlite3.connect(str(p))
    v.execute("CREATE TABLE texts(id INTEGER PRIMARY KEY, sha256 TEXT NOT NULL, source_id INTEGER,"
              " kind TEXT, author TEXT, body TEXT, segments_json TEXT, collected_at TEXT,"
              " UNIQUE(sha256, source_id, author))")
    v.execute("INSERT INTO texts(sha256, source_id, kind, author, body) VALUES"
              " ('s', 1, 'comment', 'a', 'In the GT4 I brake at the 150.')")
    v.commit()
    v.close()
    c = db.open_db(p)
    assert c.execute("SELECT car_class FROM texts").fetchone() == ("gt4",)
    c.close()


# 1: i sottotitoli, nei formati che l'attore documenta.
SRT = "1\n00:00:01,000 --> 00:00:03,000\nBrake at the 100 board for Tosa\n"
VTT = ("WEBVTT\n\n00:01.500 --> 00:03.000\n<c>Brake at the 100 board</c> for Tosa\n\n"
       "01:00:02.000 --> 01:00:04.000\nStay left\n")


@pytest.mark.parametrize("sub,campo,corpo,start", [
    ({"srt": SRT, "language": "en"}, "srt", "Brake at the 100 board for Tosa", 1.0),
    ({"vtt": VTT}, "vtt", "Brake at the 100 board for Tosa Stay left", 1.5),
    ({"plaintext": "Brake at the 100 board for Tosa."}, "plaintext",
     "Brake at the 100 board for Tosa.", None),
    ({"text": "Brake at the 100 board for Tosa."}, "text", "Brake at the 100 board for Tosa.", None),
])
def test_sottotitoli_nei_campi_documentati(tmp_path, sub, campo, corpo, start):
    item = {"id": "v1", "title": "ACC Imola GT3", "url": "https://www.youtube.com/watch?v=v1",
            "channelName": "C", "subtitles": [{"srtUrl": "https://x/s", **sub}]}
    conn = _conn(tmp_path)
    r = collect.collect(conn, _client(Finto(items={"streamers~youtube-scraper": [item]})), "imola", PIANO[:1])
    assert r["subtitle_fields"] == {campo: 1}
    body, segs = conn.execute("SELECT body, segments_json FROM texts").fetchone()
    assert body == corpo
    assert (json.loads(segs)[0]["start_s"] if segs else None) == start


def test_sottotitoli_campo_ignoto_detto(tmp_path, monkeypatch, capsys):
    from tools.fonti import fonti

    item = {"id": "v1", "title": "ACC Imola GT3", "url": "https://www.youtube.com/watch?v=v1",
            "channelName": "C", "subtitles": [{"srtUrl": "https://x/s", "content": "boh"}]}
    monkeypatch.setenv("APIFY_API_TOKEN", TOK)
    monkeypatch.setattr(apify, "_urllib_http", Finto(items={"streamers~youtube-scraper": [item]}))
    piano = tmp_path / "p.json"
    piano.write_text(json.dumps(PIANO[:1]), encoding="utf-8")
    fonti.main(["--db", str(tmp_path / "d"), "collect", "--track", "imola", "--plan", str(piano)])
    out = capsys.readouterr()
    assert "Sottotitoli letti da: nessuno 1." in out.out
    assert "content" in out.out and "srtUrl" in out.out


def test_piano_imola_solo_sottotitoli_esistenti():
    piano = json.loads((ROOT / "tools" / "fonti" / "piani" / "imola.json").read_text(encoding="utf-8"))
    yt = next(v for v in piano if v["platform"] == "youtube")
    assert yt["input"]["transcriptionAndSubtitle"] == "ALWAYS_SUBTITLES"


# 6: una corsa finita male non è finita.
@pytest.mark.parametrize("stato", ["FAILED", "ABORTED", "TIMED-OUT"])
def test_corsa_fallita_non_segnata_finita(tmp_path, monkeypatch, capsys, stato):
    from tools.fonti import fonti

    f = Finto(stato=stato)
    monkeypatch.setenv("APIFY_API_TOKEN", TOK)
    monkeypatch.setattr(apify, "_urllib_http", f)
    piano = tmp_path / "p.json"
    piano.write_text(json.dumps(PIANO[:1]), encoding="utf-8")
    assert fonti.main(["--db", str(tmp_path / "d"), "collect", "--track", "imola", "--plan", str(piano)]) == 1
    err = capsys.readouterr().err
    assert f"Voce 1" in err and stato in err
    conn = db.open_db(tmp_path / "d" / "fonti.sqlite")
    assert conn.execute("SELECT finished_at FROM collect_runs").fetchone() == (None,)
    assert conn.execute("SELECT COUNT(*) FROM raw_items").fetchone()[0] == 2   # pagati, salvati
    conn.close()


# 7: tre errori diversi dello schema.
@pytest.mark.parametrize("codice,frase", [
    (401, "token non valido o senza permesso"),
    (403, "token non valido o senza permesso"),
    (404, "attore non trovato"),
    (200, "schema non trovato"),
])
def test_check_actors_distingue_gli_errori(codice, frase):
    def http(method, url, headers, body):
        if codice == 200:
            return 200, json.dumps({"data": {"actorDefinition": {}}}).encode()
        return codice, b"{}"

    piano = [{"platform": "youtube", "actor": "a/b", "max_items": 1, "input": {}}]
    problemi = collect.check_actors(apify.Apify(TOK, http=http), piano)
    assert len(problemi) == 1 and frase in problemi[0], problemi
    for altra in {"token non valido o senza permesso", "attore non trovato", "schema non trovato"} - {frase}:
        assert altra not in problemi[0]


# N3: un titolo che nomina un altro simulatore non è su ACC.
@pytest.mark.parametrize("titolo", [
    "ACC vs iRacing at Imola", "ACC and LMU Imola", "Le Mans Ultimate vs ACC Imola",
    "ACC or AMS2 at Imola", "rF2 and ACC Imola", "Gran Turismo 7 vs ACC Imola",
    "GT7 ACC Imola comparison", "F1 24 and ACC at Imola", "ACC vs rFactor 2 Imola",
])
def test_altro_simulatore_nel_titolo(titolo):
    assert collect.game_of(titolo, "", "ACCompetizione") == "altro"


def test_gt3_e_f1_non_si_confondono():
    assert collect.game_of("ACC Imola GT3 hotlap", "", "") == "acc"
    assert collect.game_of("ACC Imola F12 setup", "", "") == "acc"
