"""Post-session debrief tool.

Reviews your most recent lap for a car+track against your reference (fastest
valid) lap and prints where the time went, plus a consistency summary:

    python -m accoach.debrief_app                 # most recent lap on disk
    python -m accoach.debrief_app "ferrari" "spa" # filter car/track (slug match)

It reads saved laps only — the game doesn't need to be running.
"""

from __future__ import annotations

import sys

from .coaching import build_lap_debrief, format_debrief, lap_time_consistency
from .comparison import Reference
from .recording import DEFAULT_LAPS_DIR, find_reference_lap, load_lap
from .recording.catalog import LapCatalog
from .recording.storage import _catalog_path, list_lap_files
from .track import detect_corners


def _latest_car_track(cat: LapCatalog) -> tuple[str, str] | None:
    rows = cat._conn.execute(
        "SELECT car_model, track FROM lap ORDER BY recorded_utc DESC LIMIT 1"
    ).fetchone()
    return (rows["car_model"], rows["track"]) if rows else None


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    laps_dir = DEFAULT_LAPS_DIR
    with LapCatalog(_catalog_path(laps_dir)) as cat:
        cat.sync(list_lap_files(laps_dir))

        if len(argv) >= 2:
            car, track = _resolve_names(cat, argv[0], argv[1])
        else:
            ct = _latest_car_track(cat)
            if ct is None:
                print("No recorded laps found in", laps_dir)
                return
            car, track = ct

        laps = cat.laps_for(car, track)
        if not laps:
            print(f"No laps for {car!r} @ {track!r}.")
            return

        reference_lap = find_reference_lap(car, track, laps_dir)
        if reference_lap is None:
            print(f"No valid reference lap for {car!r} @ {track!r} yet.")
            return
        reference = Reference(reference_lap)
        if not reference.usable:
            print("Reference lap has too few samples to analyze.")
            return

        # Review the most recent valid lap.
        review_path = next((r["path"] for r in laps if r["valid"]), None)
        if review_path is None:
            print("No valid lap to review.")
            return
        review_lap = load_lap(review_path)

        corners = detect_corners(reference_lap.samples)
        debrief = build_lap_debrief(review_lap, reference, corners)
        consistency = lap_time_consistency([r["lap_time_ms"] for r in laps if r["valid"]])

        print(format_debrief(debrief, top=3, consistency=consistency))
        print(f"\n  ({len(corners)} corners detected on this track)")


def _resolve_names(cat: LapCatalog, car: str, track: str) -> tuple[str, str]:
    """Map a slug filter back to the stored display names."""
    laps = cat.laps_for(car, track)
    if laps:
        row = cat._conn.execute(
            "SELECT car_model, track FROM lap WHERE car_key=? AND track_key=? LIMIT 1",
            (cat._slug(car), cat._slug(track)),
        ).fetchone()
        if row:
            return row["car_model"], row["track"]
    return car, track


if __name__ == "__main__":
    main()
