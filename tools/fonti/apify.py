"""Cliente Apify minimo: token, uso mensile, tetto di spesa per pista."""

from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.apify.com/v2"
CAP_USD = 2.0


class TokenMissing(Exception):
    pass


class CapReached(Exception):
    pass


class ApifyError(Exception):
    pass


def load_token(env_file: Path | None) -> str:
    """Variabile APIFY_API_TOKEN, poi il file env, poi ~/.apify-key."""
    tok = os.environ.get("APIFY_API_TOKEN", "").strip()
    if tok:
        return tok
    if env_file is not None and Path(env_file).is_file():
        for riga in Path(env_file).read_text(encoding="utf-8-sig").splitlines():
            k, sep, v = riga.partition("=")
            v = v.strip().strip("\"'")
            if sep and k.strip() == "APIFY_API_TOKEN" and v:
                return v
    chiave = Path.home() / ".apify-key"
    if chiave.is_file():
        tok = chiave.read_text(encoding="utf-8-sig").strip()
        if tok:
            return tok
    raise TokenMissing("Token Apify non trovato: variabile APIFY_API_TOKEN, file env o ~/.apify-key.")


def _urllib_http(method, url, headers, body):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class Apify:
    def __init__(self, token: str, http=None):
        self._token = token
        self._http = http or _urllib_http

    def __repr__(self) -> str:
        return "Apify(token=***)"

    def _call(self, method, url, body=None):
        headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}
        data = json.dumps(body).encode("utf-8") if body is not None else None
        status, raw = self._http(method, url, headers, data)
        if status >= 400:
            raise ApifyError(f"Apify ha risposto {status} a {method} {url.split('?')[0]}")
        return json.loads(raw.decode("utf-8")) if raw else None

    def usage_usd(self) -> float:
        d = self._call("GET", f"{API}/users/me/limits")
        return float(d["data"]["current"]["monthlyUsageUsd"])

    def run(self, actor_id, run_input, max_items, max_charge_usd=None) -> list[dict]:
        url = f"{API}/acts/{actor_id.replace('/', '~')}/run-sync-get-dataset-items?maxItems={int(max_items)}"
        if max_charge_usd is not None:
            url += f"&maxTotalChargeUsd={max(max_charge_usd, 0.01):.2f}"
        out = self._call("POST", url, run_input)
        return out if isinstance(out, list) else []


def guard(conn: sqlite3.Connection, client: Apify, track: str, cap_usd: float = CAP_USD) -> float:
    """Salva la base alla prima volta; restituisce quanto resta o solleva CapReached."""
    uso = client.usage_usd()
    riga = conn.execute("SELECT baseline_usd FROM spend WHERE track=?", (track,)).fetchone()
    if riga is None:
        conn.execute("INSERT INTO spend(track, baseline_usd, last_usd, cap_usd) VALUES (?,?,?,?)",
                     (track, uso, uso, cap_usd))
        base = uso
    else:
        base = riga[0]
        conn.execute("UPDATE spend SET last_usd=?, cap_usd=? WHERE track=?", (uso, cap_usd, track))
    conn.commit()
    resto = cap_usd - (uso - base)
    if resto <= 0:
        raise CapReached(f"Tetto Apify raggiunto per {track}: spesi {uso - base:.2f} di {cap_usd:.2f} USD.")
    return resto
