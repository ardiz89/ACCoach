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
from .store import DEFAULT_ROOTS, latest_backup, list_setups, save


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


class SeedBody(BaseModel):
    """Copy an existing setup of the same car into a track that has none."""

    source: str                        # path of the setup to copy from
    track: str                         # destination track folder name
    as_name: str = ""                  # default: the source's own name


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

    @app.get("/api/setup/elsewhere")
    def setup_elsewhere(car: str = Query(...),
                        track: str = Query("")) -> list[dict]:
        """This car's setups on **other** tracks — the seed list.

        The page needs it for the case that has no good answer otherwise: you
        are driving a car/track the game has never saved a setup for, so there
        is nothing to edit. ACC only creates ``Setups/<car>/<track>/`` when you
        save one from the garage, so a brand-new circuit is always empty — and
        it is the normal state on the first session there, not an error.

        The car is matched case-insensitively against the folder names. The sim
        does not spell every identifier the same way the folders do (the lap
        archive holds ``Imola`` and ``Zolder`` capitalised next to ``monza``
        lowercase), and this is the comparison that decides whether the driver
        sees their own setups or an empty list.
        """
        car_l, track_l = car.strip().lower(), track.strip().lower()
        out = []
        for game_root in roots:
            if not game_root.is_dir():
                continue
            for car_dir in sorted(p for p in game_root.iterdir() if p.is_dir()):
                if car_dir.name.lower() != car_l:
                    continue
                for track_dir in sorted(p for p in car_dir.iterdir() if p.is_dir()):
                    if track_dir.name.lower() == track_l:
                        continue          # the track we're missing, by definition
                    for p in sorted(track_dir.glob("*.json")) + \
                            sorted(track_dir.glob("*.ini")):
                        if p.is_file():
                            out.append({"track": track_dir.name, "name": p.stem,
                                        "path": str(p)})
        return out

    @app.post("/api/setup/seed")
    def setup_seed(body: SeedBody) -> dict:
        """Copy a setup of the same car into ``track``, creating the folder.

        This is what a real engineer does arriving at a circuit with nothing on
        file: they start from the last one and work from there. It is a
        **starting point, not a proposal** — pressures and aero from another
        track are wrong here, and the engineer's own loop is what will move
        them. The UI says so; this route just puts the file in place.

        The destination is derived from the *source path* (``…/<car>/<track>/``
        → ``…/<car>/<new track>/``), never from a car name in the request: the
        copy therefore cannot land under a different car, or outside the setups
        roots, whatever the caller sends. Only the track name comes from the
        request, and it is checked before it becomes a folder.

        The track string is the sim's own — the same identifier ACC uses for the
        folder (``Imola`` on disk, ``Imola`` in the telemetry). If a title ever
        disagreed, the result would be a folder the game ignores: harmless, and
        visible immediately because the game's setup list would not show it.
        """
        src = _safe(body.source, roots)
        track = body.track.strip()
        if (not track or track in (".", "..")
                or any(c in track for c in '\\/:*?"<>|')):
            raise HTTPException(400, f"invalid track name: {body.track!r}")
        setup = _load(src)
        dest_dir = _safe(src.parent.parent / track, roots)
        name = (body.as_name or src.stem).strip()
        try:
            out = save(setup, dest_dir, name, overwrite=False)
        except FileExistsError as e:
            raise HTTPException(409, str(e))
        return {"ok": True, "path": str(out), "name": out.stem,
                "car": dest_dir.parent.name, "track": dest_dir.name,
                "from_track": src.parent.name, "from_name": src.stem}

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

    @app.get("/api/setup/record")
    def setup_record(car: str = Query(""), track: str = Query("")) -> dict:
        """The engineer's track record: how many of its changes actually worked.

        The one number a setup tool should be willing to publish, and the only
        one here that isn't a claim — it is counted from tests the driver drove.
        Empty until the loop has been round a few times, and *empty is the right
        answer then*: a hit rate over three samples is noise wearing a
        percentage sign, so this returns the counts and lets the reader decide.
        """
        from ..engineer.ledger import read, side_effect_counts, summarise
        rows = read(car=car, track=track)
        s = summarise(rows)
        return {
            "tests": s.tests,
            "kept": s.kept,
            "hit_rate": s.hit_rate,
            "median_gain_ms": s.median_gain_ms,
            "by_param": {k: {"kept": v[0], "tests": v[1]}
                         for k, v in sorted(s.by_param.items())},
            "by_symptom": {k: {"kept": v[0], "tests": v[1]}
                           for k, v in sorted(s.by_symptom.items())},
            # Does "most effective first" hold up? Ranks are ints; JSON keys
            # aren't, so they go out as strings on purpose.
            "by_rank": {str(k): {"kept": v[0], "tests": v[1]}
                        for k, v in sorted(s.by_rank.items())},
            "side_effects": [{"param": p, "symptom": sym, "seen": n}
                             for (p, sym), n in
                             sorted(side_effect_counts(rows).items(),
                                    key=lambda kv: kv[1], reverse=True)],
        }

    @app.post("/api/setup/undo")
    def setup_undo(body: UndoBody) -> dict:
        p = _safe(body.path, roots)
        if latest_backup(p) is None:
            raise HTTPException(404, "no backup available")
        from .store import undo as _undo
        _undo(p)
        return {"ok": True, "path": str(p)}
