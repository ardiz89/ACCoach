"""User-editable settings, loaded from ``~/Documents/ACCoach/config.toml``.

On first run the file is created with commented defaults. Reading is tolerant:
unknown keys are ignored, missing keys fall back to the default, and a malformed
file never crashes the app (we log a warning and use defaults). Call
:func:`load_config` to get the cached :class:`Config`.
"""

from __future__ import annotations

import copy
import os
import re
import threading
import time
import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path

from .paths import config_path, laps_dir


@dataclass
class ServerCfg:
    host: str = "127.0.0.1"
    port: int = 8777
    hz: float = 15.0


@dataclass
class WebCfg:
    port: int = 8778


@dataclass
class AcquireCfg:
    # Background telemetry sampling rate (Hz). Drives recording fidelity and
    # braking-point resolution, independent of the UI/overlay refresh rate.
    hz: float = 60.0


@dataclass
class VoiceCfg:
    enabled: bool = True
    language: str = "it"
    rate: int = 165
    # Speak the race engineer's setup proposals aloud (in addition to the
    # Engineer page). Independent of the per-cue coaching voice above.
    engineer: bool = True
    # La voce maschile: le frasi registrate maschili (`voice_cues_male/`) e una
    # voce di sistema maschile per il resto. Predefinita dal 23/10, scelta del
    # pilota. Un `male = false` gia' scritto nel config.toml resta com'e': il
    # vecchio modello lo scriveva per tutti e non si distingue da una scelta.
    male: bool = True
    # Pit-to-car radio effect (band-pass + squelch) on whatever is spoken.
    radio: bool = True


@dataclass
class OverlayCfg:
    x: int = -1          # -1 = auto (top-centre); set by dragging in --interactive
    y: int = -1
    scale: float = 1.0
    # Live throttle/brake trace strip under the HUD — a calibration aid for
    # trail-braking and coasting ("tempo morto"). Off by default (declutters).
    pedals: bool = False
    # Retire the braking countdown at corners you've mastered, the way fast
    # drivers peel the reference line and braking markers away one at a time as
    # they learn a track (two independent drivers described exactly this on
    # r/simracing). On by default: the crutch is meant to be outgrown. Off keeps
    # it on at every corner forever.
    wean: bool = True


@dataclass
class LoggingCfg:
    level: str = "INFO"
    console: bool = True


@dataclass
class DataCfg:
    # Empty string = use the default ~/Documents/ACCoach/laps.
    laps_dir: str = ""


@dataclass
class Config:
    # App language: drives the coach VOICE and (progressively) the UI. "en" | "it".
    language: str = "en"
    # LAN access: when true, the web + live servers bind 0.0.0.0 so a phone/tablet
    # on the same network can open the report/engineer pages (see launcher QR).
    # Off by default — local-only is the safe baseline.
    lan: bool = False
    # Start the silent recorder by itself when AC/ACC appears. Off unless asked:
    # software that records you without being asked is a different product from
    # the one anyone installed. Never starts the voice — see watch.py.
    autorecord: bool = False
    server: ServerCfg = field(default_factory=ServerCfg)
    web: WebCfg = field(default_factory=WebCfg)
    acquire: AcquireCfg = field(default_factory=AcquireCfg)
    voice: VoiceCfg = field(default_factory=VoiceCfg)
    overlay: OverlayCfg = field(default_factory=OverlayCfg)
    logging: LoggingCfg = field(default_factory=LoggingCfg)
    data: DataCfg = field(default_factory=DataCfg)

    def laps_path(self) -> Path:
        return Path(self.data.laps_dir) if self.data.laps_dir else laps_dir()

    def bind_host(self) -> str:
        """Interface the servers bind to: all interfaces in LAN mode, else local."""
        return "0.0.0.0" if self.lan else "127.0.0.1"


_DEFAULT_TOML = """# HONE — user configuration
# Edit values and restart the app. Missing keys fall back to defaults.

language = "en"      # app language: "en" | "it" (coach voice + interface)
lan = false          # allow phones/tablets on your network to open the pages (binds 0.0.0.0)
autorecord = false   # start recording by itself when the game appears (never the voice)

[server]
host = "127.0.0.1"   # backend interface (keep 127.0.0.1 for local use)
port = 8777          # live-coach WebSocket port
hz = 15.0            # broadcast rate to overlay/clients

[web]
port = 8778          # analysis/engineer web-app port

[acquire]
hz = 60.0            # telemetry sampling rate (recording fidelity)

[voice]
enabled = true       # coach voice on/off
rate = 165           # reading speed (words/min approx.)
engineer = true      # also speak the race engineer's setup proposals
male = true          # male coach voice; false = female
radio = true         # pit-to-car radio effect on the voice (band-pass + squelch)

[overlay]
x = -1               # overlay X (px); -1 = auto top-centre (drag it in --interactive)
y = -1               # overlay Y (px); -1 = auto
scale = 1.0          # overlay scale factor
pedals = false       # show the live throttle/brake trace strip (trail-braking + coasting)
wean = true          # retire the braking countdown at corners you've mastered

[logging]
level = "INFO"       # console level: DEBUG | INFO | WARNING | ERROR
console = true       # also show logs on the console (the file is always complete)

[data]
laps_dir = ""        # laps folder; empty = ~/Documents/ACCoach/laps
"""

_cache: Config | None = None
_baseline: Config | None = None   # what this process last loaded or saved


def _merge(dc, data: dict) -> None:
    """Overlay a TOML table onto a dataclass instance, in place, type-tolerant."""
    if not isinstance(data, dict):
        return
    by_name = {f.name: f for f in fields(dc)}
    for key, value in data.items():
        f = by_name.get(key)
        if f is None:
            continue   # ignore unknown keys
        current = getattr(dc, f.name)
        if is_dataclass(current):
            _merge(current, value)
        else:
            try:
                setattr(dc, f.name, type(current)(value))
            except (TypeError, ValueError):
                pass   # keep the default on a bad value
    # nested dataclasses absent from `data` simply keep their defaults


def _write_default(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_DEFAULT_TOML, encoding="utf-8")
    except Exception:   # noqa: BLE001 - first-run convenience, never fatal
        pass


def _to_toml(cfg: Config) -> str:
    """Serialize the config back to TOML (with comments), deterministically."""
    b = lambda v: "true" if v else "false"  # noqa: E731
    return f'''# HONE — user configuration
# Edit values and restart the app. Missing keys fall back to defaults.

language = "{cfg.language}"      # app language: "en" | "it" (coach voice + interface)
lan = {b(cfg.lan)}          # allow phones/tablets on your network to open the pages (binds 0.0.0.0)
autorecord = {b(cfg.autorecord)}   # start recording by itself when the game appears (never the voice)

[server]
host = "{cfg.server.host}"
port = {cfg.server.port}
hz = {cfg.server.hz}

[web]
port = {cfg.web.port}

[acquire]
hz = {cfg.acquire.hz}            # telemetry sampling rate (recording fidelity)

[voice]
enabled = {b(cfg.voice.enabled)}       # coach voice on/off
rate = {cfg.voice.rate}           # reading speed (words/min approx.)
engineer = {b(cfg.voice.engineer)}      # also speak the race engineer's setup proposals
male = {b(cfg.voice.male)}         # male coach voice; false = female
radio = {b(cfg.voice.radio)}         # pit-to-car radio effect on the voice (band-pass + squelch)

[overlay]
x = {cfg.overlay.x}               # overlay X (px); -1 = auto top-centre
y = {cfg.overlay.y}               # overlay Y (px); -1 = auto
scale = {cfg.overlay.scale}          # overlay scale factor
pedals = {b(cfg.overlay.pedals)}       # show the live throttle/brake trace strip (trail-braking + coasting)
wean = {b(cfg.overlay.wean)}          # retire the braking countdown at corners you've mastered

[logging]
level = "{cfg.logging.level}"
console = {b(cfg.logging.console)}

[data]
laps_dir = "{cfg.data.laps_dir}"
'''


def _atomic_write(path: Path, text: str) -> None:
    """Write via a temp file in the same folder, so a reader (the hub, the web
    server: other processes) never catches the file half written. On Windows the
    replace is refused while another process has the file open, so it is
    retried for a moment."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.02)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:  # pragma: no cover
                pass


def _read_toml(path: Path) -> dict:
    """Il file come dizionario, tollerando quello che fa Blocco Note.

    Il 24/10 un `config.toml` salvato col BOM (Blocco Note e PowerShell 5 lo
    mettono) veniva scartato intero, in silenzio: lingua inglese e porte
    predefinite, e il pilota non sapeva perche'. Il BOM UTF-8 si toglie, e un
    file UTF-16 (il «Unicode» di Blocco Note) si legge come tale."""
    data = path.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = data.decode("utf-16")
    else:
        text = data.decode("utf-8-sig")
    return tomllib.loads(text)


# Perche' l'ultimo `load_config` non ha potuto leggere il file (None se l'ha
# letto): l'hub lo dice, invece di partire coi predefiniti senza spiegare.
_problem: str | None = None


def config_problem() -> str | None:
    """Il motivo per cui `config.toml` non si legge, o None se va bene."""
    return _problem


def _parse_disk() -> Config | None:
    """The config as the file holds it now, or ``None`` if it can't be parsed.
    Never touches the shared cache."""
    try:
        raw = _read_toml(config_path())
    except Exception:   # noqa: BLE001 - mid-write or hand-edited file
        return None
    cfg = Config()
    _merge(cfg, raw)
    return cfg


def read_language() -> str | None:
    """The language the file says right now, or ``None`` if unreadable. Leaves
    the shared cache alone (a web page being served must not replace it)."""
    cfg = _parse_disk()
    return None if cfg is None else cfg.language


def _leaves(dc, prefix=()):
    for f in fields(dc):
        v = getattr(dc, f.name)
        if is_dataclass(v):
            yield from _leaves(v, prefix + (f.name,))
        else:
            yield prefix + (f.name,), v


def _get(dc, path):
    for k in path:
        dc = getattr(dc, k)
    return dc


def _set(dc, path, value) -> None:
    for k in path[:-1]:
        dc = getattr(dc, k)
    setattr(dc, path[-1], value)


def save_config(cfg: Config | None = None) -> bool:
    """Persist what the caller changed, on top of what the file holds now.

    Several processes write this file (the hub, the overlay, the web pages), and
    each holds a copy loaded when it started. Writing the whole copy back undid
    whatever the others had changed since, so only the fields that differ from
    what this process loaded are written. An unreadable file is left alone:
    replacing it with defaults would wipe the driver's settings. Best-effort,
    never raises. Returns whether the file was written, so the caller can say
    when it was not."""
    global _baseline
    cfg = cfg or load_config()
    try:
        path = config_path()
        if path.exists():
            disk = _parse_disk()
            if disk is None:
                from .logging_setup import get_logger
                get_logger("config").warning("config.toml unreadable, not saving")
                return False
        else:
            disk = Config()
        base = _baseline if _baseline is not None else Config()
        for leaf, value in _leaves(cfg):
            if value != _get(base, leaf):
                _set(disk, leaf, value)
        _atomic_write(path, _to_toml(disk))
        for leaf, value in _leaves(disk):      # the caller's copy now matches the file
            _set(cfg, leaf, value)
        _baseline = copy.deepcopy(cfg)
        return True
    except OSError:
        from .logging_setup import get_logger
        get_logger("config").warning("config.toml not saved", exc_info=True)
        return False


class ConfigUnreadable(Exception):
    """config.toml can't be parsed right now, so nothing is written to it."""


def write_language(lang: str) -> None:
    """Change only the ``language`` line of the file, leaving the rest as is.

    For the web endpoint: it must not rewrite settings it does not own, so it
    edits the line in place (comments and all) and refuses an unreadable file."""
    path = config_path()
    try:
        text = path.read_text(encoding="utf-8-sig")
        tomllib.loads(text)
    except Exception as exc:   # noqa: BLE001
        raise ConfigUnreadable(str(exc)) from exc
    line = f'language = "{lang}"'
    # Only the top-level key counts: the part before the first [section], and
    # either quote style TOML allows.
    m = re.search(r"(?m)^[ \t]*\[", text)
    cut = m.start() if m else len(text)
    head, rest = text[:cut], text[cut:]
    head, n = re.subn(r"(?m)^language[ \t]*=[ \t]*(?:\"[^\"\n]*\"|'[^'\n]*')", line, head, count=1)
    new = (head + rest) if n else (line + "\n" + text)
    # Whatever was done, the file must still parse and say what was asked.
    try:
        ok = tomllib.loads(new).get("language") == lang
    except Exception:   # noqa: BLE001
        ok = False
    if not ok:
        raise ConfigUnreadable("could not set the top-level language key")
    _atomic_write(path, new)
    if _cache is not None:
        _cache.language = lang
        if _baseline is not None:
            _baseline.language = lang


def set_language(lang: str) -> None:
    """Switch the app language now (updates the cache) and persist it."""
    cfg = load_config()
    cfg.language = lang
    save_config(cfg)


def load_config(*, reload: bool = False) -> Config:
    """Return the cached config, loading (and first-run-creating) it if needed."""
    global _cache, _baseline, _problem
    if _cache is not None and not reload:
        return _cache

    cfg = Config()
    path = config_path()
    _problem = None
    if not path.exists():
        _write_default(path)
    else:
        try:
            raw = _read_toml(path)
            _merge(cfg, raw)
        except Exception as exc:   # noqa: BLE001 - bad TOML must not crash the app
            _problem = str(exc) or type(exc).__name__
            from .logging_setup import get_logger
            get_logger("config").warning(
                "config.toml unreadable, using defaults", exc_info=True
            )
    _cache = cfg
    _baseline = copy.deepcopy(cfg)
    return cfg
