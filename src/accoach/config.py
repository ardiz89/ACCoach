"""User-editable settings, loaded from ``~/Documents/ACCoach/config.toml``.

On first run the file is created with commented defaults. Reading is tolerant:
unknown keys are ignored, missing keys fall back to the default, and a malformed
file never crashes the app (we log a warning and use defaults). Call
:func:`load_config` to get the cached :class:`Config`.
"""

from __future__ import annotations

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
    # Prefer an installed male system voice (skips the shipped neural cues).
    male: bool = False
    # Pit-to-car radio effect (band-pass + squelch) on whatever is spoken.
    radio: bool = True


@dataclass
class OverlayCfg:
    x: int = -1          # -1 = auto (top-centre); set by dragging in --interactive
    y: int = -1
    scale: float = 1.0


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
male = false         # use an installed male system voice instead of the default
radio = true         # pit-to-car radio effect on the voice (band-pass + squelch)

[overlay]
x = -1               # overlay X (px); -1 = auto top-centre (drag it in --interactive)
y = -1               # overlay Y (px); -1 = auto
scale = 1.0          # overlay scale factor

[logging]
level = "INFO"       # console level: DEBUG | INFO | WARNING | ERROR
console = true       # also show logs on the console (the file is always complete)

[data]
laps_dir = ""        # laps folder; empty = ~/Documents/ACCoach/laps
"""

_cache: Config | None = None


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
male = {b(cfg.voice.male)}         # use an installed male system voice instead of the default
radio = {b(cfg.voice.radio)}         # pit-to-car radio effect on the voice (band-pass + squelch)

[overlay]
x = {cfg.overlay.x}               # overlay X (px); -1 = auto top-centre
y = {cfg.overlay.y}               # overlay Y (px); -1 = auto
scale = {cfg.overlay.scale}          # overlay scale factor

[logging]
level = "{cfg.logging.level}"
console = {b(cfg.logging.console)}

[data]
laps_dir = "{cfg.data.laps_dir}"
'''


def save_config(cfg: Config | None = None) -> None:
    """Persist the (cached) config to config.toml. Best-effort, never fatal."""
    cfg = cfg or load_config()
    try:
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_to_toml(cfg), encoding="utf-8")
    except OSError:  # pragma: no cover - best-effort persistence
        pass


def set_language(lang: str) -> None:
    """Switch the app language now (updates the cache) and persist it."""
    cfg = load_config()
    cfg.language = lang
    save_config(cfg)


def load_config(*, reload: bool = False) -> Config:
    """Return the cached config, loading (and first-run-creating) it if needed."""
    global _cache
    if _cache is not None and not reload:
        return _cache

    cfg = Config()
    path = config_path()
    if not path.exists():
        _write_default(path)
    else:
        try:
            with path.open("rb") as fh:
                raw = tomllib.load(fh)
            _merge(cfg, raw)
        except Exception:   # noqa: BLE001 - bad TOML must not crash the app
            from .logging_setup import get_logger
            get_logger("config").warning(
                "config.toml unreadable, using defaults", exc_info=True
            )
    _cache = cfg
    return cfg
