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
# Una chiave che non si crea o non si legge si riprova dopo un minuto, non a
# ogni richiesta: con l'Accesso controllato alle cartelle ogni tentativo e' una
# notifica di Defender, e le richieste del PC passano lo stesso.
_RIPROVA_S = 60.0
_SAFE = frozenset({"GET", "HEAD", "OPTIONS"})
_MAX_AGE = 31536000   # un anno: il segnalibro sul tablet deve reggere

_MESSAGGIO_401 = {
    "it": "Apri HONE dal codice QR dell'hub.",
    "en": "Open HONE from the hub's QR code.",
}
# Documenti non si scrive (Accesso controllato alle cartelle): la chiave non
# c'e', e un tablet non puo' entrare. Meglio dirlo che rispondere 500.
_MESSAGGIO_503 = {
    "it": "HONE non riesce a salvare la chiave di rete sul PC. Controlla che "
          "Windows non blocchi la cartella Documenti.",
    "en": "HONE can't save the network key on the PC. Check that Windows "
          "isn't blocking the Documents folder.",
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


# La chiave si scrive anche a mano: l'iPad del pilota (iOS 9.3.6) non legge i
# QR con la fotocamera. Sedici caratteri dall'alfabeto di Crockford, cioe' 80
# bit: niente I, L, O e U, che sul vetro di un tablet si confondono con 1 e 0.
_ALFABETO = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_LUNGHEZZA = 16
# Chi scrive a mano sbaglia le maiuscole, mette un trattino per non perdere il
# segno, o legge una O dove c'e' uno 0: Crockford li perdona tutti.
_PERDONA = str.maketrans({"O": "0", "I": "1", "L": "1", "-": None, " ": None})


def normalizza(key: str) -> str:
    """La chiave come la confronta il guardiano: maiuscola, senza trattini."""
    return (key or "").strip().upper().translate(_PERDONA)


def _valida(key: str) -> str:
    """La chiave normalizzata se ha il formato giusto, se no ``""``."""
    k = normalizza(key)
    if len(k) == _LUNGHEZZA and all(c in _ALFABETO for c in k):
        return k
    return ""


def _nuova() -> str:
    return "".join(secrets.choice(_ALFABETO) for _ in range(_LUNGHEZZA))


def _unico(path: Path, coda: str) -> Path:
    return path.with_name(f"{path.name}.{os.getpid()}.{secrets.token_hex(4)}.{coda}")


def lan_key() -> str:
    """La chiave di questa installazione, creata al primo uso.

    **Persistente**: un segnalibro sul tablet deve reggere un riavvio del PC.
    Le due app la chiedono in due processi diversi e magari nello stesso
    istante, quindi la creazione e' atomica e *non sovrascrive*: si scrive un
    file temporaneo e lo si collega al nome vero con ``os.link``, che fallisce
    se il file c'e' gia'. Chi perde la corsa legge la chiave di chi l'ha vinta,
    invece di tenersene in memoria una che sul disco non c'e' piu'.

    Un file che c'e' ma non vale (vuoto, rovinato, o la chiave di 32 caratteri
    di prima, che a mano non si scriveva) si sposta via e si rifa' con la
    stessa regola. Lo spostamento e' la parte delicata: dopo un aggiornamento
    tutte e due le app trovano la chiave vecchia nello stesso istante, e quella
    che arriva seconda potrebbe spostare via la chiave *nuova* dell'altra. Per
    questo chi sposta guarda cosa ha spostato, e una chiave valida la rimette.

    Se la cartella non si puo' scrivere (Accesso controllato alle cartelle di
    Windows) solleva ``OSError``: chi la chiama decide cosa mostrare.
    """
    path = key_path()
    cached = _cache.get(("key", str(path)))
    if cached:
        return cached
    fallito = _cache.get(("errore", str(path)))
    if fallito is not None:
        quando, errore = fallito
        if time.monotonic() - quando < _RIPROVA_S:
            raise errore
        del _cache[("errore", str(path))]
    try:
        return _crea_o_leggi(path)
    except OSError as e:
        _cache[("errore", str(path))] = (time.monotonic(), e)
        raise


def _crea_o_leggi(path: Path) -> str:
    key = _valida(_leggi(path))
    for _ in range(5):
        if key:
            break
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            via = _unico(path, "old")
            try:
                os.replace(path, via)
            except FileNotFoundError:
                pass   # l'ha gia' spostato l'altro processo
            except PermissionError:
                pass   # l'altro lo sta leggendo o scrivendo: si riprova
            else:
                try:
                    spostata = _valida(_leggi(via))
                except OSError:
                    # Non si legge ora: non si sa cosa c'e' dentro, quindi non
                    # si butta. Torna al suo posto e si riprova fra un minuto.
                    _rimetti(via, path)
                    raise
                if spostata:
                    # Era la chiave appena scritta dall'altro: torna al suo posto.
                    _rimetti(via, path)
                _togli(via)
            key = _valida(_leggi(path))
            continue
        nuova = _nuova()
        tmp = _unico(path, "tmp")
        tmp.write_text(nuova, encoding="utf-8")
        try:
            try:
                os.link(tmp, path)
            except FileExistsError:
                pass   # l'altro processo e' arrivato prima: vale la sua
            except OSError:
                # Un disco senza hard link (FAT): niente garanzia contro la
                # corsa, ma meglio una chiave che nessuna.
                if not path.exists():
                    os.replace(tmp, path)
        finally:
            _togli(tmp)
        key = _valida(_leggi(path))
    if not key:
        raise OSError(f"cannot create a valid LAN key at {path}")
    _cache[("key", str(path))] = key
    return key


def _rimetti(via: Path, path: Path) -> None:
    """Riporta ``via`` al nome vero, senza sovrascrivere una chiave arrivata dopo."""
    try:
        os.link(via, path)
    except FileExistsError:
        pass
    except OSError:
        if not path.exists():
            os.replace(via, path)
    _togli(via)


def _togli(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _leggi(path: Path) -> str:
    """Il contenuto, ``""`` se il file non c'e'. Ogni altro ``OSError`` risale.

    Un file valido che l'antivirus o il backup tengono aperti per un attimo non
    e' un file rovinato: leggerlo come vuoto lo farebbe spostare via, e il
    tablet perderebbe la chiave del segnalibro.
    """
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
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


def _scaduta() -> bool:
    hit = _cache.get("rete")
    return hit is None or time.monotonic() - hit[0] > _TTL_S


def _ricalcola_se_scaduta(generazione: int) -> None:
    """Come `_ricalcola`, ma chi la chiama aspetta il risultato.

    Se un ricalcolo e' gia' in corso (quello lanciato da `_rinfresca`) si
    aspetta lui, e poi non se ne fa un secondo: la cache e' gia' fresca.
    """
    if not _lock_rete.acquire(timeout=10.0):
        return
    try:
        if _scaduta():
            nuova = _calcola()
            if _cache.get("generazione", 0) == generazione:
                _cache["rete"] = nuova
    finally:
        _lock_rete.release()


async def _dopo_un_ricalcolo() -> bool:
    """Prima di dire no per colpa di una lista *scaduta*, la si rifa'.

    Dopo un cambio di rete (il portatile dal Wi-Fi di casa a quello del
    circuito) il QR porta l'IP nuovo, ma la lista in cache e' ancora quella di
    prima: `_rinfresca` la rifa' senza aspettare, e il primo colpo del tablet
    prendeva un 403. Qui si aspetta, sempre fuori dal loop. True se c'e' stato
    da aspettare, cioe' se vale la pena guardare di nuovo. Con una lista
    fresca non si aspetta niente: un host estraneo resta un no immediato.
    """
    if not _scaduta():
        return False
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _ricalcola_se_scaduta,
                               _cache.get("generazione", 0))
    return True


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
    """Chiave portata contro chiave vera, dopo averle normalizzate tutte e due:
    il pilota puo' averla scritta in minuscolo sul tablet."""
    return hmac.compare_digest(normalizza(a).encode("utf-8"),
                               normalizza(b).encode("utf-8"))


def new_nonce() -> str:
    """Un nonce per risposta: uno fisso si impara e si ricopia nello script."""
    return secrets.token_urlsafe(16)


def csp(host_header: str, nonce: str, live_port: int) -> str:
    """La Content-Security-Policy di una pagina servita dalla 8778.

    Uno script iniettato da un testo sfuggito all'escape non ha il nonce, e il
    browser non lo esegue. ``'unsafe-inline'`` accanto al nonce e' voluto: i
    browser CSP2 lo ignorano quando c'e' un nonce, Safari 9 (l'iPad del
    pilota, CSP1) il nonce non lo conosce e senza resterebbe senza lo script
    della lingua. ``connect-src`` apre solo la 8777 dello stesso host con cui
    la pagina e' stata chiamata: e' li' che stanno il WebSocket e
    ``/engineer/applied``. L'host l'ha gia' vagliato il guardiano, quindi qui
    entra solo un nome di questo PC.
    """
    host = _host_name(host_header)
    live = int(live_port)
    return (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        f"connect-src 'self' ws://{host}:{live} http://{host}:{live}; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )


# Su ogni risposta delle pagine, anche un JSON o un rifiuto del guardiano: un
# file servito con un tipo sbagliato non diventa uno script (nosniff), e nessun
# sito puo' mettere le nostre pagine in un iframe e far cliccare il pilota su
# «Applica» senza che lo sappia (DENY, per i browser senza frame-ancestors).
_PAGE_HEADERS = ((b"x-content-type-options", b"nosniff"),
                 (b"x-frame-options", b"DENY"))


def _con_header(send):
    """`send` che aggiunge `_PAGE_HEADERS` all'inizio di ogni risposta."""
    async def wrapped(message):
        if message["type"] == "http.response.start":
            message = dict(message)
            presenti = {k.lower() for k, _ in message.get("headers") or []}
            message["headers"] = list(message.get("headers") or []) + [
                h for h in _PAGE_HEADERS if h[0] not in presenti]
        await send(message)
    return wrapped


class GuardMiddleware:
    """Il guardiano, montato come middleware piu' esterno di tutte e due le app.

    ``page_headers`` lo accende solo l'app delle pagine (8778): la 8777 parla
    JSON e WebSocket con l'overlay e con l'hub, e non ne ha bisogno.
    """

    def __init__(self, app, *, page_port: int, page_headers: bool = False):
        self.app = app
        self.page_port = int(page_port)
        self.page_headers = bool(page_headers)

    async def __call__(self, scope, receive, send):
        kind = scope["type"]
        if kind not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        if kind == "http" and self.page_headers:
            send = _con_header(send)

        await _rinfresca()
        headers: dict[str, str] = {}
        for k, v in scope.get("headers") or ():
            headers[k.decode("latin-1").lower()] = v.decode("latin-1")
        # `allowed_hosts` e `is_local_client` si chiamano dal modulo, non da
        # un riferimento preso all'import: i test li rimpiazzano li'.
        nome = _host_name(headers.get("host", ""))
        if nome not in allowed_hosts() and not (
                await _dopo_un_ricalcolo() and nome in allowed_hosts()):
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
        try:
            key = lan_key()
        except OSError:
            # Il PC non porta chiavi e passa lo stesso; agli altri si spiega.
            key = None
        query_ok = bool(dalla_query) and key is not None and _same(dalla_query, key)
        portate = (cookie_parser(headers.get("cookie", "")).get(COOKIE, ""),
                   headers.get(HEADER, ""))
        con_chiave = query_ok or (key is not None
                                  and any(p and _same(p, key) for p in portate))
        # Chi porta la chiave giusta entra senza chiedersi da dove arriva: la
        # localita' puo' voler aspettare il ricalcolo degli indirizzi (secondi
        # con una VPN), e il tablet in pista non deve fermarsi ogni 30 s.
        if not con_chiave:
            client = scope.get("client")
            ip = client[0] if client else None
            locale = is_local_client(ip) or (
                await _dopo_un_ricalcolo() and is_local_client(ip))
            if not locale:
                await self._nega(kind, send, 503 if key is None else 401, None,
                                 origin)
                return

        if kind == "http" and method not in _SAFE:
            ctype = headers.get("content-type", "").strip().lower()
            if not ctype.startswith("application/json"):
                await self._nega(kind, send, 415,
                                 "content type must be application/json", origin)
                return

        if kind == "http" and method == "GET" and query_ok:
            # Il QR porta `?k=`: da qui in poi la chiave la ricorda il cookie.
            # Non HttpOnly di proposito: le pagine lo leggono e lo passano alla
            # 8777 come `?k=` o `X-HONE-Key`. I cookie non guardano la porta, ma
            # una fetch cross-origin senza credenziali non li manda, e il
            # WebSocket di un browser non accetta header.
            # Normalizzata: il cookie porta la chiave come la scrive il disco,
            # anche se il pilota l'ha battuta in minuscolo o coi trattini.
            cookie = (f"{COOKIE}={normalizza(dalla_query)}; Path=/; Max-Age={_MAX_AGE}; "
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

    async def _nega(self, kind, send, status, text, origin=None):
        """Il rifiuto. ``origin`` e' quello gia' vagliato da `_origin_ok`.

        Sulla 8777 la pagina che chiama sta su un'altra porta, e senza
        ``Access-Control-Allow-Origin`` il browser le nasconde la risposta: il
        tablet vedeva un errore di rete e diceva «coach spento» invece della
        frase del QR. Lo si mette solo per un'origine nostra, e solo sulla
        8777: sulle pagine la chiamata e' della stessa origine.
        """
        if kind == "websocket":
            # Chiudere prima di accettare: il server risponde 403 all'handshake.
            await send({"type": "websocket.close", "code": 1008})
            return
        if status in (401, 503):
            lang = current_language()
            testi = _MESSAGGIO_401 if status == 401 else _MESSAGGIO_503
            frase = html.escape(testi.get(lang, testi["en"]), quote=False)
            body = (f'<!doctype html><html lang="{html.escape(lang)}"><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width">'
                    f"<title>HONE</title><p>{frase}</p></html>").encode("utf-8")
            ctype = b"text/html; charset=utf-8"
        else:
            body = text.encode("utf-8")
            ctype = b"text/plain; charset=utf-8"
        risposta = [(b"content-type", ctype),
                    (b"content-length", str(len(body)).encode())]
        if origin is not None and not self.page_headers:
            risposta += [(b"access-control-allow-origin", origin.encode("latin-1")),
                         (b"vary", b"Origin")]
        await send({"type": "http.response.start", "status": status,
                    "headers": risposta})
        await send({"type": "http.response.body", "body": body})
