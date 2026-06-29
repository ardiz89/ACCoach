"""Analysis web app — REST API over saved laps + the static frontend.

The cold-review counterpart to the live overlay: a local web page (served here)
to look back at recorded laps — overlaid telemetry traces vs the reference, the
delta across the lap, and the corner-by-corner debrief.

    python -m accoach web        # serves http://127.0.0.1:8778

It reads only the lap store (the game needn't be running) and lives entirely in
new files, so it doesn't touch the live-coaching code.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .coaching import (
    benchmark_levels,
    build_lap_debrief,
    classify_losses,
    lap_time_consistency,
)
from .comparison import Reference
from .recording import DEFAULT_LAPS_DIR, load_lap
from .recording.catalog import LapCatalog
from .recording.lap import SAMPLE_FIELDS
from .recording.storage import _catalog_path, _slug, list_lap_files
from .sectors import ideal_lap, sector_spans, sector_times
from .telemetry.snapshot import format_lap_time
from .track import detect_corners
from .trackdata import name_corners

HOST = "127.0.0.1"
PORT = 8778
_MAX_POINTS = 600   # downsample traces for the browser


def _web_dir() -> Path:
    # When frozen by PyInstaller the static files live under _MEIPASS/accoach/web.
    base = getattr(sys, "_MEIPASS", None)
    return (Path(base) / "accoach" / "web") if base else (Path(__file__).parent / "web")


_WEB_DIR = _web_dir()


def _downsample(lap):
    """Evenly thin a lap's samples to at most _MAX_POINTS for plotting."""
    n = len(lap.samples)
    if n <= _MAX_POINTS:
        return lap.samples
    step = n / _MAX_POINTS
    return [lap.samples[int(i * step)] for i in range(_MAX_POINTS)]


def _channels(lap) -> dict:
    s = _downsample(lap)
    return {
        "pos": [round(x.pos, 4) for x in s],
        "speed": [round(x.speed_kmh, 1) for x in s],
        "throttle": [round(x.throttle, 3) for x in s],
        "brake": [round(x.brake, 3) for x in s],
        "steer": [round(x.steer_angle, 3) for x in s],
        "gear": [x.gear for x in s],
        # World ground-plane path (v3+). Old laps have all-zero coords; the
        # frontend checks ``has_map`` before drawing the track map.
        "x": [round(x.car_x, 2) for x in s],
        "z": [round(x.car_z, 2) for x in s],
    }


def _has_map(lap) -> bool:
    """True if the lap carries real world coordinates (recorded under v3+)."""
    return any(s.car_x != 0.0 or s.car_z != 0.0 for s in lap.samples)


def _delta_trace(lap, reference: Reference) -> dict:
    s = _downsample(lap)
    pos, dms = [], []
    for x in s:
        pos.append(round(x.pos, 4))
        dms.append(round((x.t_ms - reference.time_at(x.pos)) / 1000.0, 3))
    return {"pos": pos, "delta_s": dms}


def create_api(
    laps_dir: Path | str = DEFAULT_LAPS_DIR,
    setups_root: Path | str | None = None,
) -> FastAPI:
    laps_dir = Path(laps_dir)
    app = FastAPI(title="HONE analysis")

    # Race-engineer setup read/write routes (/api/setup/*). Kept in their own
    # module so this file stays about lap analysis.
    from .setup.store import DEFAULT_ROOTS
    from .setup.web_api import register_setup_routes
    register_setup_routes(app, setups_root or DEFAULT_ROOTS)

    def _catalog() -> LapCatalog:
        cat = LapCatalog(_catalog_path(laps_dir))
        cat.sync(list_lap_files(laps_dir))
        return cat

    @app.get("/api/combos")
    def combos() -> list[dict]:
        """Every car+track that has laps, with its best time."""
        with _catalog() as cat:
            rows = cat._conn.execute(
                """SELECT car_model, track, car_key, track_key,
                          COUNT(*) AS laps,
                          MIN(CASE WHEN valid=1 AND lap_time_ms>0
                                   THEN lap_time_ms END) AS best_ms
                   FROM lap GROUP BY car_key, track_key
                   ORDER BY MAX(recorded_utc) DESC"""
            ).fetchall()
        out = []
        for r in rows:
            best = r["best_ms"] or 0
            out.append({
                "car": r["car_model"], "track": r["track"],
                "car_key": r["car_key"], "track_key": r["track_key"],
                "laps": r["laps"], "best_ms": best,
                "best": format_lap_time(best) if best else "--:--.---",
            })
        return out

    @app.get("/api/laps")
    def laps(car: str = Query(...), track: str = Query(...)) -> list[dict]:
        with _catalog() as cat:
            rows = cat.laps_for(car, track)
        return [{
            "path": r["path"],
            "lap_time_ms": r["lap_time_ms"],
            "lap_time": format_lap_time(r["lap_time_ms"]),
            "valid": bool(r["valid"]),
            "recorded_utc": r["recorded_utc"],
            "samples": r["sample_count"],
        } for r in rows]

    @app.get("/api/analysis")
    def analysis(
        car: str = Query(...),
        track: str = Query(...),
        lap: str | None = Query(None),       # the lap to review (default: most recent)
        baseline: str | None = Query(None),  # the lap to compare against (default: fastest)
    ) -> dict:
        with _catalog() as cat:
            all_laps = cat.laps_for(car, track)
        valid = [r for r in all_laps if r["valid"] and r["lap_time_ms"] > 0]
        fastest = min(valid, key=lambda r: r["lap_time_ms"])["path"] if valid else None

        baseline_path = baseline or fastest
        review_path = lap or next((r["path"] for r in all_laps if r["valid"]), None)
        if baseline_path is None or review_path is None:
            raise HTTPException(404, "no valid lap for this car+track")

        try:
            baseline_lap = load_lap(baseline_path)
            review = load_lap(review_path)
        except (OSError, ValueError):
            raise HTTPException(404, "lap file unreadable")

        reference = Reference(baseline_lap)
        if not reference.usable:
            raise HTTPException(422, "comparison lap has too few samples")

        try:
            corners = detect_corners(baseline_lap.samples)
            names = {c.index: n for c, n in zip(corners, name_corners(track, corners))}
            debrief = build_lap_debrief(review, reference, corners)
            consistency = lap_time_consistency([r["lap_time_ms"] for r in valid])
        except Exception:  # noqa: BLE001 - a degenerate lap shouldn't 500 the UI
            raise HTTPException(422, "lap could not be analysed")

        # Minimum speed per corner (you vs the reference, lined up by position) —
        # the metric a driver reads first to see where they're scrubbing speed.
        corner_speeds = []
        for c in corners:
            inside = [s for s in review.samples if c.entry_pos <= s.pos <= c.exit_pos]
            if not inside:
                continue
            vmin_live = min(s.speed_kmh for s in inside)
            vmin_ref = min(reference.point_at(s.pos).speed_kmh for s in inside)
            corner_speeds.append({
                "index": c.index,
                "name": names.get(c.index, f"Corner {c.index + 1}"),
                "apex": round(c.apex_pos, 4),
                "vmin_live": round(vmin_live, 0),
                "vmin_ref": round(vmin_ref, 0),
                "delta": round(vmin_live - vmin_ref, 0),
            })

        return {
            "car": car, "track": track,
            "has_map": _has_map(review) and _has_map(baseline_lap),
            "reference": {
                "path": baseline_path,
                "lap_time_ms": reference.lap_time_ms,
                "lap_time": format_lap_time(reference.lap_time_ms),
                "channels": _channels(baseline_lap),
            },
            "review": {
                "path": review_path,
                "lap_time_ms": review.lap_time_ms,
                "lap_time": format_lap_time(review.lap_time_ms),
                "channels": _channels(review),
                "delta": _delta_trace(review, reference),
            },
            "corners": [{
                "index": c.index, "entry": c.entry_pos,
                "apex": c.apex_pos, "exit": c.exit_pos,
                "name": names.get(c.index, f"Corner {c.index + 1}"),
            } for c in corners],
            "corner_speeds": corner_speeds,
            "losses": [{
                "label": names.get(x.index, f"Corner {x.index + 1}"),
                "lost_s": round(x.lost_ms / 1000, 3),
                "category": x.category.value, "message": x.message,
                "detail": x.detail, "fix": x.fix,
                "vmin_live": round(x.min_speed_live, 0),
                "vmin_ref": round(x.min_speed_ref, 0),
                "apex": x.apex_pos,
            } for x in debrief.losses],
            "consistency": consistency,
            "laps": [{
                "path": r["path"], "lap_time": format_lap_time(r["lap_time_ms"]),
                "valid": bool(r["valid"]),
            } for r in all_laps],
        }

    @app.get("/api/sectors")
    def sectors(
        car: str = Query(...),
        track: str = Query(...),
        lap: str | None = Query(None),       # the lap to review (default: most recent)
        baseline: str | None = Query(None),  # the lap to compare against (default: fastest)
    ) -> dict:
        """Per-sector breakdown of review vs baseline, plus the ideal lap."""
        with _catalog() as cat:
            all_laps = cat.laps_for(car, track)
        valid = [r for r in all_laps if r["valid"] and r["lap_time_ms"] > 0]
        if not valid:
            raise HTTPException(404, "no valid lap for this car+track")
        fastest = min(valid, key=lambda r: r["lap_time_ms"])["path"]
        baseline_path = baseline or fastest
        review_path = lap or next((r["path"] for r in all_laps if r["valid"]), None)
        try:
            review = load_lap(review_path)
            base = load_lap(baseline_path)
        except (OSError, ValueError):
            raise HTTPException(404, "lap file unreadable")

        # Canonical spans come from the baseline: real sim sectors if it has
        # them, else equal thirds. Every lap is timed against these same spans so
        # review / baseline / ideal all line up.
        spans, real = sector_spans(base)
        n = len(spans)
        rev_st = sector_times(review, spans)
        base_st = sector_times(base, spans)
        if not rev_st or not base_st:
            raise HTTPException(422, "lap too sparse for sector splits")

        # Ideal lap stitched from the best sector of every valid lap.
        ideal = None
        try:
            objs = [load_lap(r["path"]) for r in valid]
            ideal = ideal_lap(objs, [r["path"] for r in valid], spans)
        except (OSError, ValueError):
            ideal = None

        sectors_out = [{
            "index": i,
            "start": round(spans[i][0], 3),
            "end": round(spans[i][1], 3),
            "review_ms": rev_st[i],
            "baseline_ms": base_st[i],
            "delta_ms": rev_st[i] - base_st[i],
            "is_best": bool(ideal and ideal.best_from[i] == review_path),
        } for i in range(n)]

        out = {
            "car": car, "track": track, "n": n, "real": real,
            "review": {"path": review_path, "lap_time_ms": review.lap_time_ms,
                       "lap_time": format_lap_time(review.lap_time_ms)},
            "baseline": {"path": baseline_path, "lap_time_ms": base.lap_time_ms,
                         "lap_time": format_lap_time(base.lap_time_ms)},
            "sectors": sectors_out,
            "laps": [{"path": r["path"], "lap_time": format_lap_time(r["lap_time_ms"]),
                      "valid": bool(r["valid"])} for r in all_laps],
        }
        if ideal:
            your_best = min(valid, key=lambda r: r["lap_time_ms"])["lap_time_ms"]
            out["ideal"] = {
                "best_ms": ideal.best_ms,
                "best_from": ideal.best_from,
                "ideal_ms": ideal.ideal_ms,
                "ideal": format_lap_time(ideal.ideal_ms),
                "gain_ms": your_best - ideal.ideal_ms,
            }
        return out

    @app.get("/api/progress")
    def progress(car: str = Query(...), track: str = Query(...)) -> dict:
        """Lap-time trend, consistency, benchmark levels and recurring mistakes."""
        with _catalog() as cat:
            all_laps = cat.laps_for(car, track)
            pro_path = cat.fastest_pro_path(car, track)
        valid = [r for r in all_laps if r["valid"] and r["lap_time_ms"] > 0]
        if not valid:
            return {"car": car, "track": track, "laps": [], "pb_trend": [],
                    "consistency": lap_time_consistency([]), "levels": [],
                    "trends": [], "recurring": []}

        # Chronological (oldest first) for the trend.
        chrono = sorted(valid, key=lambda r: r["recorded_utc"] or "")
        laps = [{"recorded_utc": r["recorded_utc"],
                 "lap_time_ms": r["lap_time_ms"],
                 "lap_time": format_lap_time(r["lap_time_ms"])} for r in chrono]

        per_day: dict[str, int] = {}
        for r in chrono:
            day = (r["recorded_utc"] or "")[:10] or "?"
            per_day[day] = min(per_day.get(day, r["lap_time_ms"]), r["lap_time_ms"])
        pb_trend = [{"day": d, "best_ms": ms, "best": format_lap_time(ms)}
                    for d, ms in sorted(per_day.items())]

        # Recurring mistakes: aggregate the debrief over the recent valid laps.
        fastest_row = min(valid, key=lambda r: r["lap_time_ms"])
        fastest = fastest_row["path"]
        best_ms = fastest_row["lap_time_ms"]
        recurring: list[dict] = []
        trends: list[dict] = []
        try:
            ref_lap = load_lap(fastest)
            reference = Reference(ref_lap)
            corners = detect_corners(ref_lap.samples)
            cnames = {c.index: n for c, n in zip(corners, name_corners(track, corners))}
            debriefs = []
            tally: dict[str, dict] = {}
            for r in chrono[-15:]:
                if r["path"] == fastest:
                    continue
                deb = build_lap_debrief(load_lap(r["path"]), reference, corners)
                debriefs.append(deb)
                for loss in deb.losses:
                    t = tally.setdefault(loss.category.value,
                                         {"message": loss.message, "count": 0, "corners": set()})
                    t["count"] += 1
                    t["corners"].add(cnames.get(loss.index, f"Corner {loss.index + 1}"))
            recurring = sorted(
                ({"category": k, "message": v["message"], "count": v["count"],
                  "corners": sorted(v["corners"])} for k, v in tally.items()),
                key=lambda x: x["count"], reverse=True)
            # Systematic (a weakness to train) vs sporadic (a one-off), per corner.
            trends = [{
                "corner_index": t.corner_index,
                "name": cnames.get(t.corner_index, t.name),
                "category": t.category.value,
                "kind": t.kind,
                "systematic": t.systematic,
                "occurrences": t.occurrences,
                "laps": t.laps,
                "median_s": round(t.median_ms / 1000.0, 3),
                "total_s": round(t.total_ms / 1000.0, 3),
            } for t in classify_losses(debriefs)]
        except (OSError, ValueError):
            recurring = []
            trends = []

        # Benchmark ladder: rolling best → ideal (consistency) → PRO (skill ceiling).
        ideal_ms = pro_ms = None
        try:
            objs = [load_lap(r["path"]) for r in valid]
            spans, _ = sector_spans(load_lap(fastest))
            il = ideal_lap(objs, [r["path"] for r in valid], spans)
            ideal_ms = il.ideal_ms if il else None
        except (OSError, ValueError):
            ideal_ms = None
        if pro_path:
            try:
                pro_ms = load_lap(pro_path).lap_time_ms
            except (OSError, ValueError):
                pro_ms = None
        levels = [{
            "key": lv.key, "label": lv.label,
            "lap_time_ms": lv.lap_time_ms, "lap_time": format_lap_time(lv.lap_time_ms),
            "gain_ms": lv.gain_ms, "gain_s": round(lv.gain_ms / 1000.0, 3),
        } for lv in benchmark_levels(best_ms, ideal_ms=ideal_ms, pro_ms=pro_ms)]

        return {
            "car": car, "track": track,
            "laps": laps, "pb_trend": pb_trend,
            "consistency": lap_time_consistency([r["lap_time_ms"] for r in valid]),
            "levels": levels,
            "trends": trends,
            "recurring": recurring,
        }

    @app.get("/api/export")
    def export(
        car: str = Query(...),
        track: str = Query(...),
        lap: str | None = Query(None),
        fmt: str = Query("csv"),
    ) -> Response:
        """Download a lap's full-resolution telemetry as CSV or JSON."""
        with _catalog() as cat:
            all_laps = cat.laps_for(car, track)
        path = lap or next((r["path"] for r in all_laps if r["valid"]), None)
        if path is None:
            raise HTTPException(404, "no lap to export")
        try:
            lp = load_lap(path)
        except (OSError, ValueError):
            raise HTTPException(404, "lap file unreadable")

        stem = (f"{_slug(car)}__{_slug(track)}__"
                f"{format_lap_time(lp.lap_time_ms).replace(':', 'm').replace('.', 's')}")

        if fmt == "json":
            import json
            return Response(
                json.dumps(lp.to_dict()), media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{stem}.json"'})

        import csv
        import io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(SAMPLE_FIELDS)
        for s in lp.samples:
            w.writerow(s.as_row())
        return Response(
            buf.getvalue(), media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{stem}.csv"'})

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(str(_WEB_DIR / "index.html"))

    @app.get("/engineer")
    def engineer() -> FileResponse:
        """The race-engineer setup page (live diagnosis + setup editor)."""
        return FileResponse(str(_WEB_DIR / "engineer.html"))

    if _WEB_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(_WEB_DIR)), name="static")

    return app


def _seed_demo() -> str:
    """Seed a temp lap store with several laps (improving over days) for a demo."""
    import tempfile

    from .recording.lap import Lap, LapSample
    from .recording.storage import save_lap
    from .telemetry.snapshot import SessionType

    import math

    corners = [(0.22, 0.40, 0.31, 120.0), (0.62, 0.80, 0.71, 95.0)]
    zones = {0: (0.16, 0.40), 1: (0.58, 0.80)}

    def track_xz(pos):
        """A closed synthetic circuit; periodic in pos so it joins at 0≡1."""
        a = 2 * math.pi * pos
        x = 300.0 * math.sin(a) + 70.0 * math.sin(2 * a)
        z = 210.0 * math.cos(a) - 50.0 * math.sin(3 * a)
        return x, z

    def profile(pos):
        spd, brake, thr, steer = 255.0, 0.0, 1.0, 0.0
        for lo, hi, apex, vmin in corners:
            if (lo - 0.05) <= pos <= hi:
                half = (hi - lo) / 2
                d = min(1.0, abs(pos - apex) / half)
                spd = vmin + (255.0 - vmin) * d
                brake = 0.85 if (lo - 0.04) <= pos < apex else 0.0
                thr = 1.0 if pos >= apex else 0.0
                steer = 0.28 * ((pos - lo) / (apex - lo) if pos < apex
                               else (hi - pos) / (hi - apex))
                steer = max(0.0, steer)
        return spd, brake, thr, steer

    def build(slow_corner, amt):
        s, off = [], 0
        for i in range(401):
            pos = i / 400
            spd, brake, thr, steer = profile(pos)
            cx, cz = track_xz(pos)
            if slow_corner is not None:
                lo, hi = zones[slow_corner]
                if lo <= pos <= hi:
                    off += max(1, amt // 5)
                    spd = max(spd - amt, 80.0)
                    # Ran wide here: nudge the line radially outward so the
                    # track map shows a visibly different racing line.
                    r = math.hypot(cx, cz) or 1.0
                    push = amt * 0.18
                    cx += cx / r * push
                    cz += cz / r * push
            sector = 0 if pos < 0.30 else (1 if pos < 0.65 else 2)  # unequal sectors
            s.append(LapSample(int(pos * 100000) + off, pos, spd, thr, brake,
                               steer, "4", 8000, 0.0, 0.0, car_x=cx, car_z=cz,
                               current_sector=sector))
        return Lap("HONE Demo", "Demo Circuit", SessionType.PRACTICE,
                   100000 + off, True, samples=s)

    d = tempfile.mkdtemp(prefix="accoach_webdemo_")
    save_lap(build(None, 0), d)   # the fast reference lap
    # A few laps getting better over successive days (less time lost each time).
    specs = [(0, 30, "2026-06-20"), (0, 24, "2026-06-21"), (1, 20, "2026-06-22"),
             (0, 16, "2026-06-23"), (1, 12, "2026-06-24"), (0, 8, "2026-06-25")]
    for sc, amt, day in specs:
        lap = build(sc, amt)
        lap.recorded_utc = f"{day}T18:00:00+00:00"
        save_lap(lap, d)
    return d


def _port_in_use(host: str, port: int) -> bool:
    """True if something is already listening on host:port."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def main(argv: list[str] | None = None) -> None:
    import threading
    import webbrowser

    import uvicorn

    from .config import load_config
    from .logging_setup import setup_logging
    setup_logging()
    cfg = load_config()
    host, port = HOST, cfg.web.port

    argv = sys.argv[1:] if argv is None else argv
    # The engineer page and the analysis page are served by the same app; the
    # launcher passes --engineer to land directly on the setup editor.
    path = "/engineer" if "--engineer" in argv else "/"
    url = f"http://{host}:{port}{path}"

    # If a server is already up (e.g. the user opened Analysis earlier), don't try
    # to bind a second one — just open the browser at the requested page.
    if _port_in_use(host, port):
        print(f"HONE già attivo: apro {url}")
        webbrowser.open(url)
        return

    laps_dir = _seed_demo() if "--demo" in argv else cfg.laps_path()
    if "--demo" in argv:
        print("HONE analysis in DEMO mode (synthetic laps)")

    print(f"HONE analysis on {url}  (Ctrl+C to stop)")
    # Open the browser once the server has had a moment to come up.
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_api(laps_dir), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
