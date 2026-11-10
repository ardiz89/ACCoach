"""Fatti sulle curve letti dalle fonti, per pista (``<pista>.json``)."""
from __future__ import annotations

import json
import re
import logging
from pathlib import Path

log = logging.getLogger(__name__)

KNOWN_VERSIONS = (2, 3)
# Il nome della pista arriva dall'indirizzo della pagina: mai un percorso.
_TRACK = re.compile(r"[a-z0-9_]+")


def load(track: str, root: Path | None = None) -> dict | None:
    """Il file dei fatti della pista, o None se manca o non si legge."""
    # Il catalogo dei giri scrive la pista come la dà il gioco («Imola»).
    track = track.strip().lower() if isinstance(track, str) else ""
    if not _TRACK.fullmatch(track):
        return None
    path = Path(root or Path(__file__).parent) / f"{track}.json"
    try:
        text = path.read_text("utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        log.warning("trackfacts %s: non si legge (%s)", track, exc)
        return None
    try:
        data = json.loads(text)
    except ValueError as exc:
        log.warning("trackfacts %s: JSON non valido (%s)", track, exc)
        return None
    if not isinstance(data, dict):
        log.warning("trackfacts %s: contenuto inatteso", track)
        return None
    if data.get("version") not in KNOWN_VERSIONS:
        log.warning("trackfacts %s: versione %r sconosciuta", track, data.get("version"))
        return None
    return data


def _of_corner(items, name: str) -> list:
    return [i for i in (items or []) if isinstance(i, dict) and i.get("corner") == name]


def for_corner(facts: dict | None, catalog_name: str) -> dict:
    """I fatti di una curva, divisi per gruppo."""
    out = {"reference": [], "single": [], "disputed": [], "mistakes": []}
    if not isinstance(facts, dict):
        return out
    out["reference"] = _of_corner(facts.get("facts"), catalog_name)
    for item in _of_corner(facts.get("single"), catalog_name):
        out["mistakes" if item.get("type") == "mistake" else "single"].append(item)
    out["disputed"] = _of_corner(facts.get("disputed"), catalog_name)
    return out


def gear_compare(you_gear: str | None, corner: dict) -> dict | None:
    """Marcia tua contro la prima marcia delle fonti (riferimento, poi singola)."""
    you = str(you_gear).strip() if you_gear is not None else ""
    if not you.isdigit():
        return None
    for group, state in (("reference", "reference"), ("single", "single")):
        for item in corner.get(group) or []:
            if item.get("type") == "gear":
                src = str(item.get("value", "")).strip()
                if src.isdigit() and src != you:
                    return {"you": you, "source": src, "state": state}
                return None
    return None
