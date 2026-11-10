"""Cliente Apify minimo: token, corse asincrone, schema degli attori, tetto di spesa per pista.

Una corsa si avvia, si aspetta a passi limitati e se ne legge il dataset per id. Chi
chiama salva l'id prima di aspettare: se l'attesa finisce prima della corsa, il
prossimo `collect` riprende quella corsa invece di pagarne un'altra.
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import urllib.parse
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
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class RunPending(ApifyError):
    """La corsa è ancora in corso dopo le attese previste: si riprende al prossimo collect."""


TERMINAL = ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT")
WAIT_S = 60   # quanto aspetta Apify a ogni domanda sullo stato (il suo massimo)
POLLS = 30    # quante domande al massimo: mezz'ora per corsa


def _actor(actor_id: str) -> str:
    return urllib.parse.quote(actor_id.replace("/", "~"), safe="~")


def _id(x: str) -> str:
    return urllib.parse.quote(str(x), safe="")


_TOKEN = re.compile(r"[!-~]+")  # una riga, ASCII stampabile, niente spazi dentro


def _valid(tok: str, where: str) -> str:
    """Il token pulito, o TokenMissing con un messaggio che non lo contiene mai."""
    tok = tok.strip()
    if not _TOKEN.fullmatch(tok):
        raise TokenMissing(f"Il token Apify in {where} non è valido. "
                           "Deve stare su una riga sola, senza spazi e solo in ASCII.")
    return tok


def load_token(env_file: Path | None) -> str:
    """Variabile APIFY_API_TOKEN, poi il file env (o un file col solo token), poi ~/.apify-key."""
    tok = os.environ.get("APIFY_API_TOKEN", "")
    if tok.strip():
        return _valid(tok, "APIFY_API_TOKEN")
    if env_file is not None and Path(env_file).is_file():
        righe = [r for r in Path(env_file).read_text(encoding="utf-8-sig").splitlines() if r.strip()]
        # Un file con una riga sola e senza «=» è il token stesso.
        if len(righe) == 1 and "=" not in righe[0]:
            return _valid(righe[0], "file del token")
        for riga in righe:
            k, sep, v = riga.partition("=")
            k = k.strip()
            if k.startswith("export "):
                k = k[len("export "):].strip()
            v = v.strip().strip("\"'")
            if sep and k == "APIFY_API_TOKEN" and v:
                return _valid(v, "file env")
    chiave = Path.home() / ".apify-key"
    if chiave.is_file():
        tok = chiave.read_text(encoding="utf-8-sig")
        if tok.strip():
            return _valid(tok, "~/.apify-key")
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
            raise ApifyError(f"Apify ha risposto {status} a {method} {url.split('?')[0]}", status)
        return json.loads(raw.decode("utf-8")) if raw else None

    def usage_usd(self) -> float:
        d = self._call("GET", f"{API}/users/me/limits")
        return float(d["data"]["current"]["monthlyUsageUsd"])

    def start_run(self, actor_id, run_input, max_items, max_charge_usd=None) -> dict:
        """Avvia la corsa e torna subito: l'oggetto corsa di Apify (con `id`)."""
        url = f"{API}/acts/{_actor(actor_id)}/runs?maxItems={int(max_items)}"
        if max_charge_usd is not None:
            # Per difetto al centesimo: la quota non si sfora arrotondando.
            url += f"&maxTotalChargeUsd={max(math.floor(max_charge_usd * 100) / 100, 0.01):.2f}"
        d = self._call("POST", url, run_input)
        run = (d or {}).get("data") or {}
        if not run.get("id"):
            raise ApifyError(f"Apify non ha dato l'id della corsa di {actor_id}.")
        return run

    def wait_run(self, run_id, polls: int = POLLS) -> dict:
        """Aspetta la fine della corsa a passi di WAIT_S secondi; RunPending se non arriva."""
        for _ in range(max(int(polls), 1)):
            d = self._call("GET", f"{API}/actor-runs/{_id(run_id)}?waitForFinish={WAIT_S}")
            run = (d or {}).get("data") or {}
            if run.get("status") in TERMINAL:
                return run
        raise RunPending(f"La corsa {run_id} è ancora in corso su Apify. Rilancia collect più "
                         "tardi: la riprendo senza pagarla di nuovo.")

    def dataset_items(self, run_id, limit: int) -> list[dict]:
        url = f"{API}/actor-runs/{_id(run_id)}/dataset/items?format=json&clean=true&limit={int(limit)}"
        out = self._call("GET", url)
        return out if isinstance(out, list) else []

    def input_schema(self, actor_id) -> dict | None:
        """Lo schema d'ingresso della build predefinita dell'attore. Gratis: nessuna corsa.

        None se la build non ha uno schema; ApifyError (con `status`) se Apify rifiuta.
        """
        d = self._call("GET", f"{API}/acts/{_actor(actor_id)}/builds/default")
        build = (d or {}).get("data") or {}
        schema = (build.get("actorDefinition") or {}).get("input")
        if schema is None and isinstance(build.get("inputSchema"), str):
            try:
                schema = json.loads(build["inputSchema"])
            except ValueError:
                schema = None
        return schema if isinstance(schema, dict) else None


def spent(conn: sqlite3.Connection, track: str) -> float:
    """La spesa della pista: la più alta fra il conto (in ritardo) e la somma delle corse."""
    riga = conn.execute("SELECT baseline_usd, last_usd, runs_usd FROM spend WHERE track=?",
                        (track,)).fetchone()
    if riga is None:
        return 0.0
    base, last, runs = riga
    conto = (last - base) if base is not None and last is not None else 0.0
    return max(conto, runs or 0.0, 0.0)


def guard(conn: sqlite3.Connection, client: Apify, track: str, cap_usd: float = CAP_USD) -> float:
    """Salva la base alla prima volta; restituisce quanto resta o solleva CapReached."""
    uso = client.usage_usd()
    riga = conn.execute("SELECT baseline_usd FROM spend WHERE track=?", (track,)).fetchone()
    if riga is None:
        conn.execute("INSERT INTO spend(track, baseline_usd, last_usd, cap_usd, runs_usd)"
                     " VALUES (?,?,?,?,0)", (track, uso, uso, cap_usd))
    else:
        conn.execute("UPDATE spend SET last_usd=?, cap_usd=? WHERE track=?", (uso, cap_usd, track))
    conn.commit()
    speso = spent(conn, track)
    resto = cap_usd - speso
    if resto <= 0:
        raise CapReached(f"Tetto Apify raggiunto per {track}: spesi {speso:.2f} di {cap_usd:.2f} USD.")
    return resto
