"""Parse, interpret and serialize an ACC setup ``.json`` file.

An ACC setup is a JSON document whose adjustable values are **integer indices**
("clicks"), e.g. ``"tyrePressure": [57, 52, 51, 48]`` or ``"rearWing": 11``.
We keep the raw document intact and expose two things on top of it:

* a registry (:data:`SETUP_PARAMS`) describing the adjustable parameters — where
  they live in the JSON, how to label their slots, and (where we're confident) a
  click->physical conversion for display;
* :class:`AccSetup`, a thin wrapper to read/adjust those values in clicks and
  serialize back to JSON.

Only the *click* value is authoritative. Physical numbers are advisory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ACC wheel-indexed arrays are ordered FL, FR, RL, RR.
WHEEL_LABELS = ("Ant-Sx", "Ant-Dx", "Post-Sx", "Post-Dx")
AXLE_LABELS = ("Ant", "Post")


def slot_labels(n: int) -> tuple[str, ...]:
    """Human labels for an n-length value array (4=wheels, 2=axles, else index)."""
    if n == 4:
        return WHEEL_LABELS
    if n == 2:
        return AXLE_LABELS
    return tuple(str(i) for i in range(n))


@dataclass(frozen=True)
class ParamSpec:
    """Describes one adjustable parameter inside the ACC setup JSON.

    ``path`` is the chain of dict keys from the document root to the leaf value
    (an int for scalars, or a list of ints for per-wheel/per-axle parameters).
    ``step``/``base``/``unit`` give a best-effort click->physical reading for
    display: physical = ``base + clicks * step``. When ``base`` is ``None`` we
    only know the per-click increment, not the absolute value, so we show clicks
    plus the increment. When ``step`` is ``None`` the value is a bare click/level.
    """

    key: str                      # leaf key, e.g. "tyrePressure"
    group: str                    # UI grouping, e.g. "Gomme"
    label: str                    # human label, e.g. "Pressione"
    path: tuple[str, ...]         # parent keys to the leaf (excludes key)
    unit: str | None = None       # "psi", "%", "mm", "liv.", "click", ...
    step: float | None = None     # physical units per click
    base: float | None = None     # physical value at click 0
    note: str = ""                # caveat shown in UI (e.g. conversion uncertain)

    @property
    def full_path(self) -> tuple[str, ...]:
        return self.path + (self.key,)


# Registry for ACC setups. Conversions are filled in only where reasonably
# trustworthy (tyre pressure, fuel); elsewhere we stay in clicks/levels on
# purpose rather than ship a wrong psi/degree number.
def _wheel(key, group, label, parent, **kw):
    return ParamSpec(key, group, label, parent, **kw)


_BASIC = ("basicSetup",)
_ADV = ("advancedSetup",)

SETUP_PARAMS: tuple[ParamSpec, ...] = (
    # --- Gomme -------------------------------------------------------------
    ParamSpec("tyrePressure", "Gomme", "Pressione", _BASIC + ("tyres",),
              unit="psi", step=0.1, base=20.3,
              note="≈ a freddo; base 20.3 psi, 0.1 psi/click"),
    ParamSpec("tyreCompound", "Gomme", "Mescola", _BASIC + ("tyres",),
              unit="", step=None, base=None),
    # --- Allineamento ------------------------------------------------------
    ParamSpec("camber", "Allineamento", "Camber", _BASIC + ("alignment",),
              unit="click", step=None, note="gradi reali in staticCamber"),
    ParamSpec("toe", "Allineamento", "Convergenza", _BASIC + ("alignment",),
              unit="click", step=None),
    ParamSpec("casterLF", "Allineamento", "Caster Sx", _BASIC + ("alignment",),
              unit="click", step=None),
    ParamSpec("casterRF", "Allineamento", "Caster Dx", _BASIC + ("alignment",),
              unit="click", step=None),
    # --- Elettronica -------------------------------------------------------
    ParamSpec("tC1", "Elettronica", "TC1", _BASIC + ("electronics",),
              unit="liv.", step=1, base=0),
    ParamSpec("tC2", "Elettronica", "TC2", _BASIC + ("electronics",),
              unit="liv.", step=1, base=0),
    ParamSpec("abs", "Elettronica", "ABS", _BASIC + ("electronics",),
              unit="liv.", step=1, base=0),
    ParamSpec("eCUMap", "Elettronica", "Mappa motore", _BASIC + ("electronics",),
              unit="liv.", step=1, base=0),
    ParamSpec("fuelMix", "Elettronica", "Mappa benzina", _BASIC + ("electronics",),
              unit="liv.", step=1, base=0),
    # --- Strategia ---------------------------------------------------------
    ParamSpec("fuel", "Strategia", "Benzina", _BASIC + ("strategy",),
              unit="L", step=1, base=0),
    # --- Bilanciamento meccanico ------------------------------------------
    ParamSpec("aRBFront", "Meccanica", "Barra ant.", _ADV + ("mechanicalBalance",),
              unit="click", step=None),
    ParamSpec("aRBRear", "Meccanica", "Barra post.", _ADV + ("mechanicalBalance",),
              unit="click", step=None),
    ParamSpec("wheelRate", "Meccanica", "Molle", _ADV + ("mechanicalBalance",),
              unit="click", step=None),
    ParamSpec("bumpStopRateUp", "Meccanica", "Bump stop (su)",
              _ADV + ("mechanicalBalance",), unit="click", step=None),
    ParamSpec("bumpStopRateDn", "Meccanica", "Bump stop (giù)",
              _ADV + ("mechanicalBalance",), unit="click", step=None),
    ParamSpec("bumpStopWindow", "Meccanica", "Finestra bump stop",
              _ADV + ("mechanicalBalance",), unit="click", step=None),
    ParamSpec("brakeTorque", "Meccanica", "Coppia frenante",
              _ADV + ("mechanicalBalance",), unit="click", step=None),
    ParamSpec("brakeBias", "Meccanica", "Bilanciamento freni",
              _ADV + ("mechanicalBalance",), unit="%", step=0.2, base=None,
              note="~0.2%/click; base anteriore dipende dall'auto"),
    # --- Ammortizzatori ----------------------------------------------------
    ParamSpec("bumpSlow", "Ammortizzatori", "Compressione lenta",
              _ADV + ("dampers",), unit="click", step=None),
    ParamSpec("bumpFast", "Ammortizzatori", "Compressione veloce",
              _ADV + ("dampers",), unit="click", step=None),
    ParamSpec("reboundSlow", "Ammortizzatori", "Estensione lenta",
              _ADV + ("dampers",), unit="click", step=None),
    ParamSpec("reboundFast", "Ammortizzatori", "Estensione veloce",
              _ADV + ("dampers",), unit="click", step=None),
    # --- Aero / altezze ----------------------------------------------------
    ParamSpec("rideHeight", "Aero", "Altezza", _ADV + ("aeroBalance",),
              unit="mm", step=1, base=0, note="passo 1 mm (approssimato)"),
    ParamSpec("splitter", "Aero", "Splitter", _ADV + ("aeroBalance",),
              unit="click", step=None),
    ParamSpec("rearWing", "Aero", "Ala posteriore", _ADV + ("aeroBalance",),
              unit="click", step=None),
    ParamSpec("brakeDuct", "Aero", "Condotti freni", _ADV + ("aeroBalance",),
              unit="click", step=None),
    # --- Trasmissione ------------------------------------------------------
    ParamSpec("preload", "Trasmissione", "Precarico diff.",
              _ADV + ("drivetrain",), unit="click", step=None),
)


class SetupError(ValueError):
    """Raised when a setup document is malformed or a parameter is missing."""


@dataclass
class AccSetup:
    """An ACC setup document with convenient click-level read/adjust access."""

    raw: dict[str, Any]
    path: Path | None = None
    _specs_by_key: dict[str, ParamSpec] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._specs_by_key = {s.key: s for s in SETUP_PARAMS}

    # -- identity ----------------------------------------------------------
    ext = "json"

    @property
    def car_name(self) -> str:
        return str(self.raw.get("carName", "") or "")

    # -- common interface (shared with AcSetup) ----------------------------
    def specs(self) -> tuple[ParamSpec, ...]:
        return SETUP_PARAMS

    def spec_by_key(self, key: str) -> ParamSpec | None:
        return self._specs_by_key.get(key)

    # -- navigation --------------------------------------------------------
    def _leaf_container(self, spec: ParamSpec) -> tuple[dict, str]:
        node: Any = self.raw
        for k in spec.path:
            if not isinstance(node, dict) or k not in node:
                raise SetupError(f"percorso assente: {'.'.join(spec.path)}")
            node = node[k]
        if not isinstance(node, dict) or spec.key not in node:
            raise SetupError(f"parametro assente: {spec.key}")
        return node, spec.key

    def present(self, spec: ParamSpec) -> bool:
        try:
            self._leaf_container(spec)
            return True
        except SetupError:
            return False

    def get(self, spec: ParamSpec) -> int | list[int]:
        node, key = self._leaf_container(spec)
        return node[key]

    def slots(self, spec: ParamSpec) -> int:
        """Number of adjustable slots (1 for scalars, len for arrays)."""
        val = self.get(spec)
        return len(val) if isinstance(val, list) else 1

    def click(self, spec: ParamSpec, slot: int = 0) -> int:
        val = self.get(spec)
        if isinstance(val, list):
            if not 0 <= slot < len(val):
                raise SetupError(f"slot {slot} fuori range per {spec.key}")
            return int(val[slot])
        return int(val)

    def set_click(self, spec: ParamSpec, slot: int, value: int) -> None:
        if value < 0:
            raise SetupError(f"valore negativo non valido per {spec.key}: {value}")
        node, key = self._leaf_container(spec)
        cur = node[key]
        if isinstance(cur, list):
            if not 0 <= slot < len(cur):
                raise SetupError(f"slot {slot} fuori range per {spec.key}")
            cur[slot] = int(value)
        else:
            node[key] = int(value)

    def adjust(self, spec: ParamSpec, slot: int, delta_clicks: int) -> int:
        """Add ``delta_clicks`` to a slot; returns the new click value."""
        new = self.click(spec, slot) + int(delta_clicks)
        self.set_click(spec, slot, new)
        return new

    # -- physical (display only) ------------------------------------------
    def physical(self, spec: ParamSpec, slot: int = 0) -> str:
        """Best-effort human reading of a slot. Never used for writing."""
        clicks = self.click(spec, slot)
        unit = spec.unit or ""
        if spec.step is not None and spec.base is not None:
            phys = spec.base + clicks * spec.step
            num = f"{phys:g}" if phys == int(phys) else f"{phys:.1f}"
            return f"{num} {unit}".strip()
        if spec.step is not None:                       # know increment, not base
            return f"{clicks} click (~{spec.step:g}{unit}/click)"
        if unit and unit != "click":
            return f"{clicks} {unit}".strip()
        return f"{clicks} click"

    # -- serialization -----------------------------------------------------
    def to_json(self) -> str:
        # Tabs + spaced separators keep it close to ACC's own formatting and
        # human-diffable; the game parses standard JSON regardless.
        return json.dumps(self.raw, indent="\t", separators=(",", ": ")) + "\n"

    def to_text(self) -> str:
        return self.to_json()

    def copy(self) -> "AccSetup":
        return AccSetup(raw=json.loads(json.dumps(self.raw)), path=self.path)


def load(path: Path | str) -> AccSetup:
    """Load an ACC setup ``.json`` from disk."""
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SetupError(f"JSON non valido in {path.name}: {e}") from e
    if not isinstance(raw, dict) or "basicSetup" not in raw:
        raise SetupError(f"{path.name} non sembra un setup ACC")
    return AccSetup(raw=raw, path=path)


def loads(text: str) -> AccSetup:
    """Parse an ACC setup from a JSON string (handy for tests)."""
    raw = json.loads(text)
    if not isinstance(raw, dict) or "basicSetup" not in raw:
        raise SetupError("testo non è un setup ACC")
    return AccSetup(raw=raw, path=None)
