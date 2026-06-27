"""Live delta coach — phase 3 deliverable.

Drives the whole loop together: records your laps *and* shows a live delta to
the fastest valid lap on disk for the current car+track. Beat the reference and
the next lap becomes the new one to chase.

    python -m accoach.compare_app

Until you have a reference lap for the current car+track (drive at least one
valid lap), it just records and shows "no reference yet".
"""

from __future__ import annotations

import sys
import time

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .comparison import DeltaState, LapComparator, Reference, format_delta
from .recording import (
    LapRecorder,
    describe_lap,
    find_reference_lap,
    save_lap,
)
from .telemetry import SharedMemoryReader, TelemetrySnapshot, format_lap_time
from .telemetry.snapshot import ACStatus

REFRESH_HZ = 20


def _load_comparator(car: str, track: str) -> tuple[LapComparator | None, int]:
    """Build a comparator from the current reference lap on disk (or None)."""
    ref_lap = find_reference_lap(car, track)
    if ref_lap is None:
        return None, 0
    reference = Reference(ref_lap)
    if not reference.usable:
        return None, 0
    return LapComparator(reference), ref_lap.lap_time_ms


def _delta_panel(delta: DeltaState | None) -> Panel:
    if delta is None:
        body: Text | Table = Text("no reference yet — drive a clean lap",
                                   style="bold yellow", justify="center")
        return Panel(body, title="Delta", border_style="grey50")

    color = "green" if delta.ahead else "red"
    big = Text(f"{format_delta(delta.delta_ms)}", style=f"bold {color}")
    big.append(" s", style="grey62")

    table = Table.grid(padding=(0, 2))
    table.add_column(justify="center")
    table.add_row(big)
    table.add_row(Text("AHEAD" if delta.ahead else "BEHIND",
                       style=f"bold {color}"))
    table.add_row(Text(""))

    rp = delta.reference_point
    dspeed = delta.live_speed_kmh - rp.speed_kmh
    sp_color = "green" if dspeed >= 0 else "red"
    detail = Table.grid(padding=(0, 1))
    detail.add_column(justify="right", style="bold")
    detail.add_column()
    detail.add_row("Predicted", Text(format_lap_time(int(delta.predicted_lap_ms)),
                                      style="bold white"))
    detail.add_row("Reference", Text(format_lap_time(delta.reference_lap_ms),
                                      style="magenta"))
    detail.add_row("Speed", Text(f"{delta.live_speed_kmh:6.1f}  "
                                 f"({dspeed:+.1f} vs ref)", style=sp_color))
    detail.add_row("Ref throttle", Text(f"{rp.throttle * 100:4.0f}%", style="green"))
    detail.add_row("Ref brake", Text(f"{rp.brake * 100:4.0f}%", style="red"))
    detail.add_row("Ref gear", Text(rp.gear, style="magenta"))

    return Panel(Group(table, detail), title="Delta vs reference",
                 border_style="green" if delta.ahead else "red")


def _status_panel(s: TelemetrySnapshot, saved: int, last_msg: str) -> Panel:
    table = Table.grid(padding=(0, 1))
    table.add_column(justify="right", style="bold")
    table.add_column()
    if not s.connected:
        conn = Text("waiting for game…", style="bold yellow")
    elif s.status == ACStatus.LIVE:
        conn = Text("● LIVE", style="bold green")
    else:
        conn = Text(f"○ {s.status.name}", style="grey50")
    table.add_row("State", conn)
    table.add_row("Car @ Track",
                  Text(f"{s.car_model or '?'} @ {s.track or '?'}", style="white"))
    table.add_row("Current", Text(format_lap_time(s.current_lap_ms), style="white"))
    table.add_row("Last", Text(format_lap_time(s.last_lap_ms), style="cyan"))
    table.add_row("Best", Text(format_lap_time(s.best_lap_ms), style="bold green"))
    table.add_row("Laps saved", Text(str(saved), style="bold green"))
    table.add_row("Last event", Text(last_msg or "—", style="grey70"))
    return Panel(table, title="ACCoach · live delta coach", border_style="bright_blue")


def _render(s: TelemetrySnapshot, delta: DeltaState | None,
            saved: int, last_msg: str) -> Group:
    top = Table.grid(expand=True)
    top.add_column(ratio=1)
    top.add_column(ratio=1)
    top.add_row(_status_panel(s, saved, last_msg), _delta_panel(delta))
    return Group(top)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    interval = 1.0 / REFRESH_HZ
    reader = SharedMemoryReader()
    recorder = LapRecorder()

    comparator: LapComparator | None = None
    key = ("", "")
    saved = 0
    last_msg = ""

    try:
        with Live(_render(TelemetrySnapshot.disconnected(), None, 0, ""),
                  refresh_per_second=REFRESH_HZ, screen=False) as live:
            while True:
                snap = reader.read()

                if snap.connected and (snap.car_model, snap.track) != key:
                    key = (snap.car_model, snap.track)
                    comparator, _ = _load_comparator(snap.car_model, snap.track)

                lap = recorder.update(snap)
                if lap is not None and lap.valid:
                    save_lap(lap)
                    saved += 1
                    last_msg = f"saved {describe_lap(lap)}"
                    # A new best becomes the reference to chase from now on.
                    comparator, _ = _load_comparator(snap.car_model, snap.track)
                elif lap is not None:
                    last_msg = f"skipped partial lap ({len(lap.samples)} samples)"

                delta = comparator.compare(snap) if comparator else None
                live.update(_render(snap, delta, saved, last_msg))
                time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        reader.close()


if __name__ == "__main__":
    main()
