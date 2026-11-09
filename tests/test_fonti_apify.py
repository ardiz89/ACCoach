"""Apify (tools/fonti): token, tetto di spesa, regola del gioco. Mai in rete."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.fonti import apify, collect, db  # noqa: E402

TOK = "tok-di-prova"


def _casa(monkeypatch, tmp_path):
    casa = tmp_path / "casa"
    casa.mkdir()
    monkeypatch.setenv("USERPROFILE", str(casa))
    monkeypatch.setenv("HOME", str(casa))
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    return casa


def test_token_ordine_e_mai_stampato(monkeypatch, tmp_path):
    casa = _casa(monkeypatch, tmp_path)
    env = tmp_path / ".env"
    env.write_text("ALTRO=1\nAPIFY_API_TOKEN=tok-dal-file\n", encoding="utf-8")
    (casa / ".apify-key").write_text("tok-dalla-casa\n", encoding="utf-8")
    assert apify.load_token(env) == "tok-dal-file"
    monkeypatch.setenv("APIFY_API_TOKEN", TOK)
    assert apify.load_token(env) == TOK
    monkeypatch.delenv("APIFY_API_TOKEN")
    assert apify.load_token(None) == "tok-dalla-casa"
    (casa / ".apify-key").unlink()
    with pytest.raises(apify.TokenMissing) as e:
        apify.load_token(None)
    assert TOK not in str(e.value)
    assert TOK not in repr(apify.Apify(TOK))


def _limiti(usd):
    def http(method, url, headers, body):
        assert url.endswith("/users/me/limits")
        assert TOK not in url
        return 200, json.dumps({"data": {"current": {"monthlyUsageUsd": usd}}}).encode()
    return http


def test_guard_base_e_tetto(tmp_path):
    conn = db.open_db(tmp_path / "f.sqlite")
    apify.guard(conn, apify.Apify(TOK, http=_limiti(0.54)), "imola", 2.0)
    assert apify.guard(conn, apify.Apify(TOK, http=_limiti(1.50)), "imola", 2.0) == pytest.approx(1.04)
    with pytest.raises(apify.CapReached):
        apify.guard(conn, apify.Apify(TOK, http=_limiti(2.54)), "imola", 2.0)


@pytest.mark.parametrize("titolo,sub,atteso", [
    ("ACC Imola hotlap 720S", "", "acc"),
    ("Assetto Corsa Competizione guide", "", "acc"),
    ("iRacing Imola", "", "altro"),
    ("accelerate", "", "altro"),
    ("Imola tips", "ACCompetizione", "acc"),
])
def test_game_of(titolo, sub, atteso):
    assert collect.game_of(titolo, "", sub) == atteso
