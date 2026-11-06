"""La pista vista dall'alto dai file grafici di AC.

Per ora solo la parte che decide *quali* file: dalla linea dell'IA di una pista
si risale alla sua cartella, al suo `models.ini` (o `models_<layout>.ini`) e
ai kn5 che elenca, con posizione e rotazione. Sola lettura: niente viene mai
scritto nella cartella del gioco.
"""
from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArtFile:
    """Un kn5 grafico e dove l'ini lo mette.

    `rotation_deg` e' come sta scritta nell'ini: (yaw/Y, pitch/X, roll/Z) in
    gradi. Applicarla non spetta a questo modulo di lettura.
    """

    path: Path
    position: tuple[float, float, float]
    rotation_deg: tuple[float, float, float]


_ZERO = (0.0, 0.0, 0.0)


def _triple(text: str | None) -> tuple[float, float, float]:
    try:
        v = [float(p) for p in (text or "").replace(";", ",").split(",")]
    except ValueError:
        return _ZERO
    return (v[0], v[1], v[2]) if len(v) == 3 else _ZERO


def _inside(folder: Path, name: str) -> Path | None:
    """Il file, solo se sta davvero dentro la cartella della pista."""
    name = name.strip().strip('"').replace("\\", "/")
    if not name:
        return None
    try:
        root = folder.resolve()
        got = (folder / name).resolve()
        got.relative_to(root)
    except (ValueError, OSError):
        return None
    return got if got.is_file() else None


def art_files(spline: Path) -> list[ArtFile]:
    """I kn5 grafici della pista a cui appartiene `spline` (la sua fast_lane.ai)."""
    layout_dir = spline.parent.parent
    ini = layout_dir.parent / f"models_{layout_dir.name}.ini"
    if ini.is_file():
        folder = layout_dir.parent
    elif any(layout_dir.glob("*.kn5")) or (layout_dir / "models.ini").is_file():
        folder, ini = layout_dir, layout_dir / "models.ini"
    else:
        folder, ini = layout_dir.parent, layout_dir.parent / "models.ini"
    if not ini.is_file():
        try:
            return [ArtFile(p, _ZERO, _ZERO)
                    for p in sorted(folder.glob("*.kn5")) if p.is_file()]
        except OSError:
            return []
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        cp.read_string(ini.read_text(encoding="utf-8-sig", errors="replace"))
    except (configparser.Error, OSError):
        return []
    out: list[ArtFile] = []
    for section in cp.sections():
        got = _inside(folder, cp.get(section, "file", fallback=""))
        if got is not None:
            out.append(ArtFile(got, _triple(cp.get(section, "position", fallback=None)),
                               _triple(cp.get(section, "rotation", fallback=None))))
    return out
