"""Database delle fonti (tools/fonti): schema, idempotenza dei testi, --db obbligatorio."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.fonti import db  # noqa: E402

FONTI = ROOT / "tools" / "fonti" / "fonti.py"


def test_schema_creato(tmp_path):
    conn = db.open_db(tmp_path / "fonti.sqlite")
    nomi = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"sources", "texts", "results", "facts", "rejects", "spend", "raw_items"} <= nomi
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    conn.close()


def test_add_text_idempotente(tmp_path):
    conn = db.open_db(tmp_path / "fonti.sqlite")
    conn.execute("INSERT INTO sources(platform, url) VALUES ('youtube', 'https://example.org/v')")
    sid = conn.execute("SELECT id FROM sources").fetchone()[0]
    h1, nuovo1 = db.add_text(conn, sid, "transcript", "autore", "Frena prima di Tamburello",
                             [{"start_s": 1.5, "text": "Frena"}])
    h2, nuovo2 = db.add_text(conn, sid, "transcript", "autore", "Frena prima di Tamburello")
    assert h1 == h2 and nuovo1 is True and nuovo2 is False
    assert conn.execute("SELECT COUNT(*) FROM texts").fetchone()[0] == 1
    conn.close()


def test_db_obbligatorio():
    r = subprocess.run([sys.executable, str(FONTI), "status"], capture_output=True, text=True)
    assert r.returncode != 0


def test_status_conta_righe(tmp_path):
    p = tmp_path / "f.sqlite"
    db.open_db(p).close()
    r = subprocess.run([sys.executable, str(FONTI), "--db", str(p), "status"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert "sources" in r.stdout and "spend" in r.stdout


def test_stesso_testo_due_autori_due_righe(tmp_path):
    conn = db.open_db(tmp_path / "f.sqlite")
    conn.execute("INSERT INTO sources(platform, url) VALUES ('reddit', 'https://example.org/t')")
    sid = conn.execute("SELECT id FROM sources").fetchone()[0]
    h1, n1 = db.add_text(conn, sid, "comment", "uno", "Frena al cento")
    h2, n2 = db.add_text(conn, sid, "comment", "due", "Frena al cento")
    h3, n3 = db.add_text(conn, sid, "comment", "due", "Frena al cento")
    assert h1 == h2 == h3 and (n1, n2, n3) == (True, True, False)
    assert conn.execute("SELECT COUNT(*) FROM texts").fetchone()[0] == 2
    conn.close()


def test_readme_dice_come_si_usa():
    # M5, L14: token, ordine dei comandi, file di risposta e cambio di prompt_version.
    testo = (ROOT / "tools" / "fonti" / "README.md").read_text(encoding="utf-8")
    for pezzo in ("APIFY_API_TOKEN", "export APIFY_API_TOKEN=", ".apify-key", "--env-file",
                  ".answer.json", "```json", "--model", "prompt_version", "--force --only"):
        assert pezzo in testo, pezzo
    ordine = ["check-actors", "--dry-run", "pending --kind extract", "pending --kind rate",
              "consensus --track", "pending --kind factcheck", "export --track", "review --track"]
    posti = [testo.index(x) for x in ordine]
    assert posti == sorted(posti)
