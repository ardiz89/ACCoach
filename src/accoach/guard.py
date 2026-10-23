"""Il guardiano dei due server: chi puo' parlare con HONE, e come.

Le due app (pagine e API sulla 8778, feed dal vivo sulla 8777) ascoltano anche
in rete quando il pilota accende ``lan``, e fino a qui si fidavano di chiunque.
Una revisione ci ha trovato quattro buchi, e questo modulo ne chiude tre in un
punto solo, prima che la richiesta arrivi a qualunque route:

1. **Host.** Un sito qualunque puo' far risolvere il suo nome a 127.0.0.1 (DNS
   rebinding) e poi leggere le nostre risposte come se fossero sue: il browser
   pensa di parlare con ``evil.example``. L'unico punto in cui si vede e'
   l'header ``Host``, quindi si ammettono solo i nomi di questo PC.
2. **La chiave per il Wi-Fi.** Il PC del pilota non porta chiavi; un tablet si,
   ed e' quella del codice QR dell'hub. Senza, chiunque sulla stessa rete
   (l'ospite al circolo) apriva la pagina Ingegnere e scriveva assetti.
3. **Scritture solo JSON, e solo dalle nostre pagine.** Un form o un
   ``fetch(..., {mode: "no-cors"})`` da un altro sito non puo' mandare
   ``application/json`` senza un preflight, e il preflight il browser lo fa
   rispettare. L'``Origin``, quando c'e', deve essere la porta delle pagine.

E' ASGI puro e non ``BaseHTTPMiddleware`` perche' deve coprire anche il
WebSocket: ``/ws`` della 8777 porta la telemetria, e un sito che la apre da un
browser sul PC del pilota la leggerebbe tutta.
"""

from __future__ import annotations

import asyncio
import hmac
import html
import os
import secrets
import socket
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from starlette.requests import cookie_parser

from . import netinfo
from .i18n import current_language
from .paths import base_dir

COOKIE = "hone_key"
HEADER = "x-hone-key"
QUERY = "k"

# L'IP di rete cambia col DHCP (il portatile che passa dal Wi-Fi di casa a
# quello del circuito): gli indirizzi si ricalcolano, ma non a ogni richiesta,
# perche' `gethostbyname_ex` puo' metterci secondi con una VPN di mezzo.
_TTL_S = 30.0
_SAFE = frozenset({"GET", "HEAD", "OPTIONS"})
_MAX_AGE = 31536000   # un anno: il segnalibro sul tablet deve reggere

_MESSAGGIO_401 = {
    "it": "Apri HONE dal codice QR dell'hub.",
    "en": "Open HONE from the hub's QR code.",
}

_cache: dict = {}
# Un ricalcolo degli indirizzi alla volta (vedi `_rinfresca`).
_lock_rete = threading.Lock()


def _dimentica() -> None:
    """Svuota le cache (indirizzi e chiave). Per i test, e per chi cambia rete."""
    generazione = _cache.get("generazione", 0) + 1
    _cache.clear()
    _cache["generazione"] = generazione


def key_path() -> Path:
    return base_dir() / "lan-key.txt"


def lan_key() -> str:
    """La chiave di questa installazione, creata al primo uso.

    **Persistente**: un segnalibro sul tablet deve reggere un riavvio del PC.
    Le due app la chiedono in due processi diversi e magari nello stesso
    istante, quindi la creazione e' atomica e *non sovrascrive*: si scrive un
    file temporaneo e lo si collega al nome vero con ``os.link``, che fallisce
    se il file c'e' gia'. Chi perde la corsa legge la chiave di chi l'ha vinta,
    invece di tenersene in memoria una che sul disco non c'e' piu'.
    """
    path = key_path()
    cached = _cache.get(("key", str(path)))
    if cached:
        return cached
    key = _leggi(path)
    if not key:
        path.parent.mkdir(parents=True, exist_ok=True)
        nuova = secrets.token_urlsafe(24)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
        tmp.write_text(nuova, encoding="utf-8")
        try:
            if path.exists():
                # C'e' ma e' vuoto o rovinato: qui una sovrascrittura e' la cura.
                os.replace(tmp, path)
            else:
                try:
                    os.link(tmp, path)
                except FileExistsError:
                    pass   # l'altro processo e' arrivato prima: vale la sua
                except OSError:
                    # Un disco senza hard link (FAT): niente garanzia contro la
                    # corsa, ma meglio una chiave che nessuna.
                    os.replace(tmp, path)
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass
        key = _leggi(path) or nuova
    _cache[("key", str(path))] = key
    return key


def _leggi(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _calcola() -> tuple[float, frozenset[str], frozenset[str]]:
    """Indirizzi del PC e nomi ammessi nell'Host, in un colpo solo.

    E' la parte lenta (``gethostbyname_ex`` puo' metterci secondi con una VPN
    di mezzo): il guardiano la chiama fuori dal loop, vedi `_rinfresca`.
    """
    try:
        locali = set(netinfo.local_addresses())
    except Exception:  # noqa: BLE001 - best-effort, mai cadere qui
        locali = {"127.0.0.1", "::1"}
    nomi = {"localhost", "127.0.0.1", "::1", "[::1]"}
    nomi.update(a.lower() for a in locali)
    try:
        nomi.add(socket.gethostname().lower())
    except Exception:  # noqa: BLE001 - best-effort, mai cadere qui
        pass
    return time.monotonic(), frozenset(locali), frozenset(nomi)


def _rete() -> tuple[float, frozenset[str], frozenset[str]]:
    """La cache degli indirizzi; la calcola qui solo se e' vuota.

    Chi la legge non la rinfresca mai: se e' scaduta vale lo stesso, finche'
    `_rinfresca` non ne porta una nuova. Calcolarla qui, sul loop della 8777,
    vorrebbe dire fermare il feed dal vivo per tutto il tempo del resolver.
    """
    hit = _cache.get("rete")
    if hit is None:
        hit = _calcola()
        _cache["rete"] = hit
    return hit


def _ricalcola(generazione: int) -> None:
    try:
        nuova = _calcola()
        # Un `_dimentica()` arrivato nel frattempo vince: niente dati vecchi
        # scritti sopra una cache appena svuotata.
        if _cache.get("generazione", 0) == generazione:
            _cache["rete"] = nuova
    finally:
        _lock_rete.release()


async def _rinfresca() -> None:
    """Prima di ogni richiesta: la cache c'e' ed e' fresca, o lo sara'.

    Vuota (il primo colpo di un processo) si riempie in un thread e si
    aspetta, senza fermare il loop. Scaduta si rinfresca in un thread e
    **non** si aspetta: intanto vale quella di prima, e un solo ricalcolo alla
    volta anche con mille richieste nel frattempo.
    """
    hit = _cache.get("rete")
    if hit is not None and time.monotonic() - hit[0] <= _TTL_S:
        return
    loop = asyncio.get_running_loop()
    if hit is None:
        await loop.run_in_executor(None, _rete)
        return
    if _lock_rete.acquire(blocking=False):
        try:
            loop.run_in_executor(None, _ricalcola, _cache.get("generazione", 0))
        except Exception:  # pragma: no cover - executor chiuso
            _lock_rete.release()


def _invecchia() -> None:
    """Fa scadere la cache senza svuotarla. Per i test."""
    hit = _cache.get("rete")
    if hit is not None:
        _cache["rete"] = (hit[0] - 10 * _TTL_S, hit[1], hit[2])


def allowed_hosts() -> frozenset[str]:
    """I nomi con cui questo PC puo' essere chiamato nell'header ``Host``.

    Loopback, gli indirizzi del PC (dentro c'e' l'IP di rete, quello del QR) e
    il nome della macchina. La porta non conta: si confronta solo il nome.
    """
    return _rete()[2]


def is_local_client(ip: str | None) -> bool:
    """True se la richiesta arriva da questo PC (che non porta chiavi)."""
    if not ip:
        return False
    if ip.lower().startswith("::ffff:"):
        ip = ip[7:]   # IPv4 mappato su socket IPv6: e' lo stesso indirizzo
    return ip in _rete()[1]


def _host_name(host: str) -> str:
    """Il nome dall'header Host, senza porta. ``[::1]:8778`` -> ``[::1]``."""
    host = host.strip().lower()
    if host.startswith("["):
        end = host.find("]")
        return host[: end + 1] if end != -1 else host
    if host.count(":") == 1:
        return host.split(":", 1)[0]
    return host


def _origin_ok(origin: str, page_port: int) -> bool:
    try:
        parts = urlsplit(origin)
        port = parts.port
    except ValueError:
        return False
    name = (parts.hostname or "").lower()
    if not name or port != page_port:
        return False
    hosts = allowed_hosts()
    return name in hosts or f"[{name}]" in hosts


def _same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


class GuardMiddleware:
    """Il guardiano, montato come middleware piu' esterno di tutte e due le app."""

    def __init__(self, app, *, page_port: int):
        self.app = app
        self.page_port = int(page_port)

    async def __call__(self, scope, receive, send):
        kind = scope["type"]
        if kind not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        await _rinfresca()
        headers: dict[str, str] = {}
        for k, v in scope.get("headers") or ():
            headers[k.decode("latin-1").lower()] = v.decode("latin-1")
        # `allowed_hosts` e `is_local_client` si chiamano dal modulo, non da
        # un riferimento preso all'import: i test li rimpiazzano li'.
        if _host_name(headers.get("host", "")) not in allowed_hosts():
            await self._nega(kind, send, 403, "host not allowed")
            return

        # L'Origin, quando c'e', e' sempre una delle nostre pagine: anche sulle
        # letture e sui preflight. Il CORS della 8777 ammette qualunque host
        # sulla porta delle pagine, e un sito ospitato su `evil.example:8778`
        # leggeva `/health` dal browser del PC, che e' locale e non porta
        # chiavi. Le pagine non ne soffrono: una GET o una navigazione sulla
        # stessa origine l'Origin non lo manda, e quando lo manda e' il nostro.
        origin = headers.get("origin")
        if origin is not None and not _origin_ok(origin, self.page_port):
            await self._nega(kind, send, 403, "origin not allowed")
            return

        method = scope.get("method", "GET").upper() if kind == "http" else "GET"
        # Il preflight non porta credenziali: Host e Origin bastano, il resto
        # lo decide il CORS dietro di noi.
        if kind == "http" and method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
        dalla_query = (query.get(QUERY) or [""])[0]
        client = scope.get("client")
        ip = client[0] if client else None
        query_ok = bool(dalla_query) and _same(dalla_query, lan_key())
        if not is_local_client(ip):
            key = lan_key()
            portate = (cookie_parser(headers.get("cookie", "")).get(COOKIE, ""),
                       headers.get(HEADER, ""))
            if not (query_ok or any(p and _same(p, key) for p in portate)):
                await self._nega(kind, send, 401, None)
                return

        if kind == "http" and method not in _SAFE:
            ctype = headers.get("content-type", "").strip().lower()
            if not ctype.startswith("application/json"):
                await self._nega(kind, send, 415,
                                 "content type must be application/json")
                return

        if kind == "http" and method == "GET" and query_ok:
            # Il QR porta `?k=`: da qui in poi la chiave la ricorda il cookie.
            # Non HttpOnly di proposito: le pagine lo leggono e lo passano alla
            # 8777 come `?k=` o `X-HONE-Key`. I cookie non guardano la porta, ma
            # una fetch cross-origin senza credenziali non li manda, e il
            # WebSocket di un browser non accetta header.
            cookie = (f"{COOKIE}={dalla_query}; Path=/; Max-Age={_MAX_AGE}; "
                      "SameSite=Lax").encode("latin-1")

            async def send_col_cookie(message):
                if message["type"] == "http.response.start":
                    message = dict(message)
                    message["headers"] = list(message.get("headers") or []) + [
                        (b"set-cookie", cookie)]
                await send(message)

            await self.app(scope, receive, send_col_cookie)
            return

        await self.app(scope, receive, send)

    async def _nega(self, kind, send, status, text):
        if kind == "websocket":
            # Chiudere prima di accettare: il server risponde 403 all'handshake.
            await send({"type": "websocket.close", "code": 1008})
            return
        if status == 401:
            lang = current_language()
            frase = html.escape(_MESSAGGIO_401.get(lang, _MESSAGGIO_401["en"]), quote=False)
            body = (f'<!doctype html><html lang="{html.escape(lang)}"><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width">'
                    f"<title>HONE</title><p>{frase}</p></html>").encode("utf-8")
            ctype = b"text/html; charset=utf-8"
        else:
            body = text.encode("utf-8")
            ctype = b"text/plain; charset=utf-8"
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", ctype),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
