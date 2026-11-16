"""Impronta del setup: riconosce quale file è caricato nell'auto.

Il gioco non dice «sto usando HONE_8»: espone solo TC, ABS, mappa motore,
ripartitore e pressioni a freddo. Qui si confrontano quelle letture coi valori
dei file di setup salvati. Modulo puro: niente I/O oltre la lettura dei file.

Cosa decide e cosa no: TC, ABS e mappa sono certi (interi, letti uguali al
file). Il ripartitore conta solo dopo la taratura (`bias_offset`, dalla risposta
del pilota), le pressioni a freddo solo se `COLD_PSI_VERIFIED`: finché non è
provato che il gioco le espone come nel file, servono a scegliere fra file
altrimenti identici (`probable`), mai a escluderne uno.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..coaching.pitcall import stopped_in_box
from ..setup import acc_format
from ..telemetry.snapshot import ACStatus
from ..textfmt import fmt_num

COLD_PSI_VERIFIED: bool = False
PSI_TOL = 0.3          # psi: scarto massimo fra lettura e file
BIAS_STEP = 0.002      # frazione per click del ripartitore
BIAS_TOL = 0.001       # mezzo click
#: Gomme «fredde» ai box: la media delle temperature interne entro tanti gradi
#: dall'aria. Sopra, le pressioni lette sono quelle di una sosta a gomme calde
#: e non la pressione a freddo del file. Da verificare al test (il registro
#: tiene pressioni e temperatura di ogni sosta, fredde o no).
COLD_TYRE_MARGIN_C = 15.0

_WHEELS = ("fl", "fr", "rl", "rr")
_UNREAD = -1


@dataclass(frozen=True)
class Reading:
    """Quello che il gioco espone; -1 / -1.0 = non letto."""

    tc: int
    abs: int
    emap: int
    bias: float
    cold_psi: tuple[float, float, float, float] | None
    fuel: float
    air_temp: float
    road_temp: float

    def to_dict(self) -> dict:
        return {"tc": self.tc, "abs": self.abs, "emap": self.emap,
                "bias": self.bias,
                "cold_psi": list(self.cold_psi) if self.cold_psi else None,
                "fuel": self.fuel, "air_temp": self.air_temp,
                "road_temp": self.road_temp}

    @classmethod
    def from_dict(cls, d: dict) -> "Reading":
        psi = d.get("cold_psi")
        return cls(tc=int(d.get("tc", -1)), abs=int(d.get("abs", -1)),
                   emap=int(d.get("emap", -1)), bias=float(d.get("bias", -1.0)),
                   cold_psi=tuple(float(x) for x in psi) if psi else None,
                   fuel=float(d.get("fuel", 0.0)),
                   air_temp=float(d.get("air_temp", 0.0)),
                   road_temp=float(d.get("road_temp", 0.0)))

    @classmethod
    def from_snapshot(cls, s, cold_psi) -> "Reading":
        return cls(tc=s.tc_level, abs=s.abs_level, emap=s.engine_map,
                   bias=s.brake_bias,
                   cold_psi=tuple(cold_psi) if cold_psi else None,
                   fuel=s.fuel, air_temp=s.air_temp, road_temp=s.road_temp)


@dataclass(frozen=True)
class FileValues:
    name: str
    path: str
    tc: int
    abs: int
    emap: int
    bias_clicks: int
    cold_psi: tuple[float, ...]
    fuel: int


def file_values(path: Path) -> FileValues | None:
    """I valori di un setup ACC; None per .ini, JSON rotti o senza elettronica."""
    try:
        path = Path(path)
        if path.suffix.lower() != ".json":
            return None
        raw = acc_format.load(path).raw
        el = raw["basicSetup"]["electronics"]
        click = [int(x) for x in raw["basicSetup"]["tyres"]["tyrePressure"]]
        if len(click) != 4:
            return None
        return FileValues(
            name=path.stem, path=str(path),
            tc=int(el["tC1"]), abs=int(el["abs"]), emap=int(el["eCUMap"]),
            bias_clicks=int(raw["advancedSetup"]["mechanicalBalance"]["brakeBias"]),
            cold_psi=tuple(round(20.3 + 0.1 * c, 1) for c in click),
            fuel=int(raw["basicSetup"]["strategy"]["fuel"]))
    except Exception:       # file del pilota o scaricato: uno rotto si salta
        return None


@dataclass(frozen=True)
class FieldDiff:
    field: str      # tc abs emap bias psi_fl psi_fr psi_rl psi_rr
    seen: float
    want: float


def compare(r: Reading, f: FileValues, *, carry: dict[str, int],
            bias_offset: float | None
            ) -> tuple[tuple[FieldDiff, ...], tuple[FieldDiff, ...]]:
    """(campi certi, pressioni) di cui la lettura differisce dal file.

    `carry` = click delle modifiche al volo accettate, sommati al file.
    """
    certain: list[FieldDiff] = []
    for key, name, seen, want in (
            ("tC1", "tc", r.tc, f.tc), ("abs", "abs", r.abs, f.abs),
            ("eCUMap", "emap", r.emap, f.emap)):
        want = want + carry.get(key, 0)
        if seen != _UNREAD and seen != want:
            certain.append(FieldDiff(name, seen, want))
    if bias_offset is not None and r.bias >= 0:
        want_b = bias_offset + BIAS_STEP * (f.bias_clicks + carry.get("brakeBias", 0))
        if abs(r.bias - want_b) > BIAS_TOL:
            certain.append(FieldDiff("bias", r.bias, want_b))
    psi: list[FieldDiff] = []
    if r.cold_psi is not None:
        for w, seen, want in zip(_WHEELS, r.cold_psi, f.cold_psi):
            if abs(seen - want) > PSI_TOL:
                psi.append(FieldDiff("psi_" + w, seen, want))
    if COLD_PSI_VERIFIED:
        certain.extend(psi)
    return tuple(certain), tuple(psi)


@dataclass(frozen=True)
class Match:
    state: str                  # match ambiguous unsaved unknown
    names: tuple[str, ...]
    best: str | None
    probable: bool
    diffs: dict[str, tuple[FieldDiff, ...]]


def match(r: Reading, files: list[FileValues], *, carry: dict[str, int],
          bias_offset: float | None) -> Match:
    if not files or _UNREAD in (r.tc, r.abs, r.emap):
        return Match("unknown", (), None, False, {})
    certain: dict[str, tuple[FieldDiff, ...]] = {}
    full: dict[str, tuple[FieldDiff, ...]] = {}
    psi_ok: dict[str, bool] = {}
    for f in files:
        c, p = compare(r, f, carry=carry, bias_offset=bias_offset)
        certain[f.name] = c
        full[f.name] = c if COLD_PSI_VERIFIED else c + p
        psi_ok[f.name] = r.cold_psi is not None and not p
    ok = tuple(n for n in certain if not certain[n])
    if not ok:
        best = min(certain, key=lambda n: len(certain[n]))
        return Match("unsaved", (), best, False, full)
    if len(ok) == 1:
        return Match("match", ok, ok[0], False, full)
    near = [n for n in ok if psi_ok[n]]
    if len(near) == 1:
        return Match("match", ok, near[0], True, full)
    return Match("ambiguous", ok, None, False, full)


def changed(before: Reading, after: Reading) -> tuple[FieldDiff, ...]:
    """Cosa è cambiato fra due letture (seen = dopo, want = prima)."""
    out: list[FieldDiff] = []
    for name in ("tc", "abs", "emap"):
        a, b = getattr(before, name), getattr(after, name)
        if a != _UNREAD and b != _UNREAD and a != b:
            out.append(FieldDiff(name, b, a))
    if (before.bias >= 0 and after.bias >= 0
            and abs(after.bias - before.bias) > BIAS_TOL):
        out.append(FieldDiff("bias", after.bias, before.bias))
    if COLD_PSI_VERIFIED and before.cold_psi and after.cold_psi:
        for w, a, b in zip(_WHEELS, before.cold_psi, after.cold_psi):
            if abs(b - a) > PSI_TOL:
                out.append(FieldDiff("psi_" + w, b, a))
    return tuple(out)


_LABEL = {
    "it": {"tc": "TC", "abs": "ABS", "emap": "mappa motore", "bias": "ripartitore",
           "psi_fl": "anteriore sinistra", "psi_fr": "anteriore destra",
           "psi_rl": "posteriore sinistra", "psi_rr": "posteriore destra"},
    "en": {"tc": "TC", "abs": "ABS", "emap": "engine map", "bias": "brake bias",
           "psi_fl": "front left", "psi_fr": "front right",
           "psi_rl": "rear left", "psi_rr": "rear right"},
}


def _val(d: FieldDiff, x: float, lang: str) -> str:
    if d.field == "bias":
        return fmt_num(x * 100, 1, lang, "%")
    if d.field.startswith("psi_"):
        return fmt_num(x, 1, lang, "psi")
    if d.field == "emap":       # l'HUD di ACC mostra la mappa da 1: solo le parole
        return str(int(x) + 1)
    return str(int(x))


def describe(diffs, lang: str) -> str:
    """Le differenze a parole, per il pilota."""
    labels = _LABEL["it" if lang == "it" else "en"]
    word = "invece di" if lang == "it" else "instead of"
    return ", ".join(f"{labels[d.field]} {_val(d, d.seen, lang)} {word} "
                     f"{_val(d, d.want, lang)}" for d in diffs)


class PitWatch:
    """Guarda i box frame per frame: pressioni a freddo da fermo e lettura all'uscita.

    `update` risponde "live" quando, fermo ai box, la lettura cambia; "exit" al
    primo frame in pista dopo la corsia box. Un frame non LIVE, non connesso o
    non ACC azzera la sosta in corso (niente uscita fantasma).

    «Fermo ai box» e' `coaching.pitcall.stopped_in_box`, la regola che vale
    per tutto il progetto: su ACC `in_pit` resta 0 anche fermi in piazzola o in
    garage, e quello che si accende e' la corsia box a velocita' zero.

    Le pressioni lette da fermo valgono come «a freddo» solo con le gomme
    fredde (`COLD_TYRE_MARGIN_C`); quelle lette comunque, e la temperatura
    interna media, restano in `box_psi` e `box_core_c` fino alla sosta dopo,
    per il registro.
    """

    def __init__(self) -> None:
        self.entry: Reading | None = None
        self.live: Reading | None = None
        self.exit: Reading | None = None
        #: Le pressioni lette da fermo in questa sosta (o nell'ultima), fredde
        #: o no, e la media delle temperature interne; None se non lette.
        self.box_psi: tuple[float, float, float, float] | None = None
        self.box_core_c: float | None = None
        self._track: Reading | None = None      # ultima lettura in pista
        self._in_stop = False
        self._cold: tuple[float, float, float, float] | None = None
        self._live_key: tuple | None = None

    def reset(self) -> None:
        self.entry = self.live = self.exit = self._track = None
        self.box_psi = self.box_core_c = None
        self._reset_stop()

    def _reset_stop(self) -> None:
        self._in_stop = False
        self._cold = None
        self._live_key = None

    @property
    def stop_live(self) -> Reading | None:
        """La lettura da fermo di questa sosta, finche' la macchina e' ai box;
        None in pista, dove quella di `live` e' della sosta di prima."""
        return self.live if self._in_stop else None

    @staticmethod
    def _key(r: Reading) -> tuple:
        # fuel e temperature si muovono da sole in sosta: non sono un cambio
        return (r.tc, r.abs, r.emap, round(r.bias, 3), r.cold_psi)

    @staticmethod
    def _core_c(snap) -> float | None:
        cores = [t for t in snap.tyre_core_temp if t > 0]
        return round(sum(cores) / len(cores), 1) if cores else None

    @staticmethod
    def _cold_tyres(core_c: float | None, air: float) -> bool:
        # Temperature non lette (tutte 0): come prima, le pressioni si tengono.
        if core_c is None or not air > 0:
            return True
        return core_c <= air + COLD_TYRE_MARGIN_C

    def update(self, snap) -> str | None:
        if not (snap.connected and snap.status == ACStatus.LIVE and snap.is_acc):
            self._reset_stop()
            return None
        if not snap.in_pit and not snap.in_pit_lane:
            if self._in_stop:
                self.exit = Reading.from_snapshot(snap, self._cold)
                self._reset_stop()
                return "exit"
            self._track = Reading.from_snapshot(snap, None)
            return None
        if not self._in_stop:
            self._in_stop = True
            self.entry = self._track
            self.live = None
            self.box_psi = self.box_core_c = None
        if not stopped_in_box(snap):
            return None
        psi = tuple(snap.tyre_pressure)
        if len(psi) == 4 and all(p > 0 for p in psi):
            self.box_psi = tuple(round(p, 1) for p in psi)
            self.box_core_c = self._core_c(snap)
            if self._cold_tyres(self.box_core_c, snap.air_temp):
                self._cold = self.box_psi
        r = Reading.from_snapshot(snap, self._cold)
        key = self._key(r)
        self.live = r
        if key != self._live_key:
            self._live_key = key
            return "live"
        return None
