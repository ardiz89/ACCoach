"""REST routes for reading and writing car setups (`/api/setup/*`).

Registered onto the analysis FastAPI app (see ``api.create_api``). The browser
"race engineer" UI uses these to: discover setups, read the current one in
physical + click terms, **preview** a change without writing, **apply** it (with
explicit confirmation, backup and atomic write), and **undo**.

Works on both ACC ``.json`` and AC ``.ini`` setups through the format-agnostic
loader. All paths are confined to the configured setups roots — we never read or
write outside them.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from .acc_format import slot_labels
from .diff import diff
from .labels import (
    canonical_slot,
    err_needs_value,
    err_slot_invalid,
    err_slot_out_of_range,
    err_slot_required,
    reload_hint,
    tr,
)
from .loader import load_any
from .store import DEFAULT_ROOTS, backup, latest_backup, list_setups, save


# --- request models --------------------------------------------------------

class SetupChange(BaseModel):
    param: str                         # parameter key, e.g. "tyrePressure"
    slot: str | int | None = None      # slot label/index; null for scalars
    delta_clicks: int | None = None    # relative change (preferred)
    value: int | None = None           # or an absolute click value


class PreviewBody(BaseModel):
    path: str
    changes: list[SetupChange]


class ApplyBody(PreviewBody):
    as_name: str
    confirm: bool = False
    overwrite: bool = False


class UndoBody(BaseModel):
    path: str


# --- helpers ---------------------------------------------------------------

def _safe(path: str | Path, roots: list[Path]) -> Path:
    """Resolve ``path`` and ensure it stays under one of ``roots`` (no escapes)."""
    p = Path(path).resolve()
    for root in roots:
        try:
            p.relative_to(root.resolve())
            return p
        except ValueError:
            continue
    raise HTTPException(403, "path outside the setup folders")


def _resolve_slot(setup, spec, slot, lang: str | None = None) -> tuple[int, str | None]:
    """Map a slot label/index to an int slot; returns (slot, error)."""
    n = setup.slots(spec)
    if n == 1:
        return 0, None
    labels = slot_labels(n)
    if slot is None:
        return -1, err_slot_required(spec.key, labels, lang)
    if isinstance(slot, int) or (isinstance(slot, str) and slot.isdigit()):
        i = int(slot)
        if 0 <= i < n:
            return i, None
        return -1, err_slot_out_of_range(i, spec.key, lang)
    # Accept the label in any language we render it in, not just the canonical
    # spelling — the web UI sends indices, so this path is a human typing.
    canon = canonical_slot(slot) if isinstance(slot, str) else slot
    if canon in labels:
        return labels.index(canon), None
    return -1, err_slot_invalid(slot, spec.key, lang)


def _apply_changes(setup, changes: list[SetupChange],
                   lang: str | None = None) -> list[str]:
    """Apply changes in place; return a list of error strings (empty == ok)."""
    errors: list[str] = []
    for ch in changes:
        spec = setup.spec_by_key(ch.param)
        if spec is None:
            errors.append(f"unknown parameter: {ch.param}")
            continue
        if not setup.present(spec):
            errors.append(f"'{ch.param}' not present in this setup")
            continue
        slot, err = _resolve_slot(setup, spec, ch.slot, lang)
        if err:
            errors.append(err)
            continue
        try:
            if ch.value is not None:
                setup.set_click(spec, slot, ch.value)
            elif ch.delta_clicks is not None:
                setup.adjust(spec, slot, ch.delta_clicks)
            else:
                errors.append(err_needs_value(ch.param, lang))
        except ValueError as e:
            errors.append(str(e))
    return errors


def _setup_payload(setup, path: Path, lang: str | None = None) -> dict:
    """Structured view of a setup for the UI: groups -> params -> slots.

    ``group``/``label``/``note`` are display text and get translated; ``key`` is
    the identifier the UI sends back to us, so it stays canonical.
    """
    params = []
    for spec in setup.specs():
        if not setup.present(spec):
            continue
        n = setup.slots(spec)
        labels = slot_labels(n) if n > 1 else ("",)
        params.append({
            "key": spec.key, "group": tr(spec.group, lang),
            "label": tr(spec.label, lang),
            "unit": spec.unit, "step": spec.step, "note": tr(spec.note, lang),
            "slots": [{"slot": tr(labels[i], lang), "click": setup.click(spec, i),
                       "physical": setup.physical(spec, i)} for i in range(n)],
        })
    groups: list[str] = []
    for p in params:
        if p["group"] not in groups:
            groups.append(p["group"])
    return {"path": str(path), "name": path.stem, "car": setup.car_name,
            "format": setup.ext, "groups": groups, "params": params}


def _diff_payload(changes, lang: str | None = None) -> list[dict]:
    return [{
        "group": tr(c.group, lang), "label": tr(c.label, lang),
        "slot": tr(c.slot, lang) if isinstance(c.slot, str) else c.slot,
        "old_click": c.old_click, "new_click": c.new_click,
        "delta": c.delta, "old_phys": c.old_phys, "new_phys": c.new_phys,
    } for c in changes]


def _load(path: Path):
    try:
        return load_any(path)
    except (OSError, ValueError) as e:
        raise HTTPException(404, f"setup unreadable: {e}")


# --- registration ----------------------------------------------------------

def register_setup_routes(app: FastAPI, root=DEFAULT_ROOTS) -> None:
    # Accept a single path or a collection of roots.
    if isinstance(root, (str, Path)):
        roots = [Path(root)]
    else:
        roots = [Path(r) for r in root]

    @app.get("/api/setup/combos")
    def setup_combos() -> list[dict]:
        """Every car/track folder (ACC or AC) that holds setups."""
        out = []
        for game_root in roots:
            if not game_root.is_dir():
                continue
            for car_dir in sorted(p for p in game_root.iterdir() if p.is_dir()):
                for track_dir in sorted(p for p in car_dir.iterdir() if p.is_dir()):
                    n = sum(len(list(track_dir.glob(g))) for g in ("*.json", "*.ini"))
                    if n:
                        out.append({"car": car_dir.name, "track": track_dir.name,
                                    "count": n})
        return out

    @app.get("/api/setup/list")
    def setup_list(car: str = Query(...), track: str = Query(...)) -> list[dict]:
        found = []
        for game_root in roots:
            found += list_setups(car, track, game_root)
        return [{"name": p.stem, "path": str(p)} for p in found]

    @app.get("/api/setup/class")
    def setup_class(car: str = Query(...),
                    lang: str | None = Query(None)) -> dict:
        """Which engineer (GT3 / Formula / Road) a car gets, and its profile."""
        from ..engineer.classmap import classify, profile_for
        from ..engineer.profiles._common import tr as tr_engineer
        cls = classify(car)
        prof = profile_for(cls)
        # name (GT3 / Formula / Road) is a class identifier and stays as-is; the
        # phase labels and al-volo lever names follow the REQUEST's language. They
        # used to follow config.language, which is the desktop's setting — so a
        # browser set to English rendered these phases in Italian next to English
        # chrome, on the same screen.
        return {"car": car, "class": cls.value,
                "profile": {"name": prof.name,
                            "phases": [tr_engineer(p.label, lang) for p in prof.phases],
                            "al_volo": [tr_engineer(x, lang) for x in prof.al_volo]}}

    @app.get("/api/setup/current")
    def setup_current(path: str = Query(...),
                      lang: str | None = Query(None)) -> dict:
        p = _safe(path, roots)
        return _setup_payload(_load(p), p, lang)

    @app.post("/api/setup/preview")
    def setup_preview(body: PreviewBody,
                      lang: str | None = Query(None)) -> dict:
        p = _safe(body.path, roots)
        before = _load(p)
        after = before.copy()
        errors = _apply_changes(after, body.changes, lang)
        if errors:
            return {"ok": False, "errors": errors, "diff": []}
        return {"ok": True, "errors": [],
                "diff": _diff_payload(diff(before, after), lang)}

    @app.post("/api/setup/apply")
    def setup_apply(body: ApplyBody, lang: str | None = Query(None)) -> dict:
        if not body.confirm:
            raise HTTPException(400, "confirmation required (confirm=true)")
        p = _safe(body.path, roots)
        before = _load(p)
        after = before.copy()
        errors = _apply_changes(after, body.changes, lang)
        if errors:
            raise HTTPException(422, {"errors": errors})
        try:
            out = save(after, p.parent, body.as_name, overwrite=body.overwrite)
        except FileExistsError as e:
            raise HTTPException(409, str(e))
        return {
            "ok": True, "path": str(out), "name": out.stem,
            "diff": _diff_payload(diff(before, after), lang),
            "reload_hint": reload_hint(out.stem, lang),
        }

    @app.post("/api/setup/undo")
    def setup_undo(body: UndoBody) -> dict:
        p = _safe(body.path, roots)
        if latest_backup(p) is None:
            raise HTTPException(404, "no backup available")
        from .store import undo as _undo
        _undo(p)
        return {"ok": True, "path": str(p)}
