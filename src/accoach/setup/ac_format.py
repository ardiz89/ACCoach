"""Parse, interpret and serialize an Assetto Corsa (classic) setup ``.ini``.

AC setups are flat INI: one ``[SECTION]`` per adjustable value, each with a
``VALUE=<int>`` line; per-corner parameters use ``_LF/_RF/_LR/_RR`` suffixes
(e.g. ``PRESSURE_LF``). As with ACC we operate in the file's native integer
*clicks*, not physical units.

This module mirrors :mod:`acc_format` (same ``specs()``/``click()``/``set_click``
interface) so the rest of the setup layer — diff, store, the REST routes and the
editor UI — works on AC and ACC setups through one code path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .acc_format import ParamSpec  # reused shape: key/group/label/unit/note/step


class AcSetupError(ValueError):
    """Raised when an AC setup file is malformed or a section is missing."""


# Per-corner section order matches our wheel order: FL, FR, RL, RR.
def _wheel(prefix: str) -> tuple[str, ...]:
    return (f"{prefix}_LF", f"{prefix}_RF", f"{prefix}_LR", f"{prefix}_RR")


# Registry: ACCoach param key -> AC INI sections (one per slot). Conversions to
# physical units aren't reliable across AC mods, so we stay in clicks (step=None).
@dataclass(frozen=True)
class AcSpec(ParamSpec):
    sections: tuple[str, ...] = ()


def _spec(key, group, label, sections, unit="click", note=""):
    return AcSpec(key=key, group=group, label=label, path=(), unit=unit,
                  step=None, base=None, note=note, sections=tuple(sections))


AC_PARAMS: tuple[AcSpec, ...] = (
    _spec("tyrePressure", "Gomme", "Pressione", _wheel("PRESSURE"), "psi"),
    _spec("camber", "Allineamento", "Camber", _wheel("CAMBER")),
    _spec("toe", "Allineamento", "Convergenza", _wheel("TOE_OUT")),
    _spec("frontWing", "Aero", "Ala anteriore", ("WING_1",)),
    _spec("rearWing", "Aero", "Ala posteriore", ("WING_2",)),
    _spec("aRBFront", "Meccanica", "Barra ant.", ("ARB_FRONT",)),
    _spec("aRBRear", "Meccanica", "Barra post.", ("ARB_REAR",)),
    _spec("wheelRate", "Meccanica", "Molle", _wheel("SPRING_RATE")),
    _spec("bumpSlow", "Ammortizzatori", "Compressione", _wheel("DAMP_BUMP")),
    _spec("reboundSlow", "Ammortizzatori", "Estensione", _wheel("DAMP_REBOUND")),
    _spec("rideHeight", "Altezze", "Altezza (rod length)", _wheel("ROD_LENGTH"), "mm"),
    _spec("diffPower", "Trasmissione", "Diff. power", ("DIFF_POWER",)),
    _spec("diffCoast", "Trasmissione", "Diff. coast", ("DIFF_COAST",)),
    _spec("preload", "Trasmissione", "Precarico diff.", ("DIFF_PRELOAD",)),
    _spec("finalRatio", "Trasmissione", "Rapporto finale", ("FINAL_RATIO",)),
    _spec("brakeBias", "Freni", "Bilanciamento freni", ("FRONT_BIAS",), "%"),
    _spec("brakePower", "Freni", "Potenza freni", ("BRAKE_POWER_MULT",), "%"),
    _spec("tC1", "Elettronica", "Controllo trazione", ("TRACTION_CONTROL",), "liv."),
    _spec("abs", "Elettronica", "ABS", ("ABS",), "liv."),
    _spec("fuel", "Strategia", "Benzina", ("FUEL",), "L"),
)


@dataclass
class AcSetup:
    """An AC ``.ini`` setup with the same access surface as :class:`AccSetup`."""

    # Ordered to round-trip exactly: list of (section_name, [(key, value_str), ...]).
    sections: list[tuple[str, list[list[str]]]]
    path: Path | None = None
    _index: dict[str, list[list[str]]] = field(init=False, repr=False)
    _specs_by_key: dict[str, AcSpec] = field(init=False, repr=False)

    ext = "ini"

    def __post_init__(self) -> None:
        self._index = {name: kv for name, kv in self.sections}
        self._specs_by_key = {s.key: s for s in AC_PARAMS}

    # -- identity ----------------------------------------------------------
    @property
    def car_name(self) -> str:
        car = self._index.get("CAR")
        if car:
            for k, v in car:
                if k == "MODEL":
                    return v
        return ""

    # -- common interface --------------------------------------------------
    def specs(self) -> tuple[AcSpec, ...]:
        return AC_PARAMS

    def spec_by_key(self, key: str) -> AcSpec | None:
        return self._specs_by_key.get(key)

    def present(self, spec: AcSpec) -> bool:
        return all(self._value_cell(sec) is not None for sec in spec.sections)

    def slots(self, spec: AcSpec) -> int:
        return len(spec.sections)

    def _value_cell(self, section: str) -> list[str] | None:
        """The ``[VALUE, '..']`` pair inside a section, or None if absent."""
        kv = self._index.get(section)
        if not kv:
            return None
        for pair in kv:
            if pair[0] == "VALUE":
                return pair
        return None

    def click(self, spec: AcSpec, slot: int = 0) -> int:
        if not 0 <= slot < len(spec.sections):
            raise AcSetupError(f"slot {slot} fuori range per {spec.key}")
        cell = self._value_cell(spec.sections[slot])
        if cell is None:
            raise AcSetupError(f"sezione assente: {spec.sections[slot]}")
        return int(round(float(cell[1])))

    def set_click(self, spec: AcSpec, slot: int, value: int) -> None:
        if not 0 <= slot < len(spec.sections):
            raise AcSetupError(f"slot {slot} fuori range per {spec.key}")
        cell = self._value_cell(spec.sections[slot])
        if cell is None:
            raise AcSetupError(f"sezione assente: {spec.sections[slot]}")
        cell[1] = str(int(value))

    def adjust(self, spec: AcSpec, slot: int, delta_clicks: int) -> int:
        new = self.click(spec, slot) + int(delta_clicks)
        self.set_click(spec, slot, new)
        return new

    def physical(self, spec: AcSpec, slot: int = 0) -> str:
        clicks = self.click(spec, slot)
        unit = spec.unit or ""
        return f"{clicks} {unit}".strip() if unit and unit != "click" else f"{clicks}"

    # -- serialization -----------------------------------------------------
    def to_text(self) -> str:
        out: list[str] = []
        for name, kv in self.sections:
            out.append(f"[{name}]")
            for pair in kv:
                out.append(f"{pair[0]}={pair[1]}")
            out.append("")                       # blank line between sections
        return "\n".join(out).rstrip("\n") + "\n"

    def copy(self) -> "AcSetup":
        clone = [(name, [list(p) for p in kv]) for name, kv in self.sections]
        return AcSetup(sections=clone, path=self.path)


def loads(text: str) -> AcSetup:
    sections: list[tuple[str, list[list[str]]]] = []
    cur: list[list[str]] | None = None
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("[") and s.endswith("]"):
            cur = []
            sections.append((s[1:-1], cur))
        elif "=" in s and cur is not None:
            k, v = s.split("=", 1)
            cur.append([k.strip(), v.strip()])
    if not sections:
        raise AcSetupError("file non è un setup AC (.ini)")
    return AcSetup(sections=sections, path=None)


def load(path: Path | str) -> AcSetup:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise AcSetupError(f"illeggibile: {e}") from e
    setup = loads(text)
    setup.path = path
    return setup
