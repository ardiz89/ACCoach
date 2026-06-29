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


@dataclass
class OverlayCfg:
    x: int = 40
    y: int = 40
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
    server: ServerCfg = field(default_factory=ServerCfg)
    web: WebCfg = field(default_factory=WebCfg)
    acquire: AcquireCfg = field(default_factory=AcquireCfg)
    voice: VoiceCfg = field(default_factory=VoiceCfg)
    overlay: OverlayCfg = field(default_factory=OverlayCfg)
    logging: LoggingCfg = field(default_factory=LoggingCfg)
    data: DataCfg = field(default_factory=DataCfg)

    def laps_path(self) -> Path:
        return Path(self.data.laps_dir) if self.data.laps_dir else laps_dir()


_DEFAULT_TOML = """# HONE — user configuration
# Edit values and restart the app. Missing keys fall back to defaults.

language = "en"      # app language: "en" | "it" (coach voice + interface)

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

[overlay]
x = 40               # overlay X position (px from the edge)
y = 40               # overlay Y position (px from the edge)
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


def set_language(lang: str) -> None:
    """Switch the app language now (updates the cache) and persist it to
    config.toml, preserving the rest of the file."""
    import re

    cfg = load_config()
    cfg.language = lang
    path = config_path()
    try:
        text = path.read_text(encoding="utf-8") if path.exists() else _DEFAULT_TOML
        if re.search(r'(?m)^\s*language\s*=', text):
            text = re.sub(r'(?m)^\s*language\s*=.*$', f'language = "{lang}"', text, count=1)
        else:
            text = f'language = "{lang}"\n' + text
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError:  # pragma: no cover - best-effort persistence
        pass


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
