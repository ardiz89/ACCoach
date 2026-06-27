"""Live lap recorder — phase 2 foundation.

Polls the telemetry stream and saves every completed lap to the ``laps/`` store,
showing a compact live status. Run it while you drive:

    python -m accoach.recorder_app

Each time you cross the line a lap is written; the first (partial) lap after you
start is skipped. The fastest valid lap on disk for the current car+track is
shown as the current reference — that's what phase 3 will coach against.
"""

from __future__ import annotations

import sys
import time

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .recording import (
    LapRecorder,
    describe_lap,
    find_reference_lap,
    save_lap,
)
from .telemetry import SharedMemoryReader, TelemetrySnapshot, format_lap_time
from .telemetry.snapshot import ACStatus

REFRESH_HZ = 20


def _status_panel(s: TelemetrySnapshot, saved: int, last_msg: str,
                  reference: str) -> Panel:
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
    table.add_row("Lap", Text(str(s.completed_laps), style="cyan"))
    table.add_row("Current", Text(format_lap_time(s.current_lap_ms), style="white"))
    table.add_row("Last", Text(format_lap_time(s.last_lap_ms), style="cyan"))
    table.add_row("Pit", Text("YES" if s.in_pit else "no",
                              style="red" if s.in_pit else "grey50"))
    table.add_row("", Text(""))
    table.add_row("Laps saved", Text(str(saved), style="bold green"))
    table.add_row("Reference", Text(reference, style="magenta"))
    table.add_row("Last event", Text(last_msg or "—", style="grey70"))
    return Panel(table, title="ACCoach · lap recorder", border_style="bright_blue")


def _reference_text(car: str, track: str) -> str:
    ref = find_reference_lap(car, track)
    if ref is None:
        return "none yet"
    return f"{format_lap_time(ref.lap_time_ms)}"


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    interval = 1.0 / REFRESH_HZ
    reader = SharedMemoryReader()
    recorder = LapRecorder()

    saved = 0
    last_msg = ""
    reference = "—"
    ref_key = ("", "")

    try:
        with Live(_status_panel(TelemetrySnapshot.disconnected(), 0, "", "—"),
                  refresh_per_second=REFRESH_HZ, screen=False) as live:
            while True:
                snap = reader.read()

                # Refresh the reference only when the car/track changes (loads files).
                if snap.connected and (snap.car_model, snap.track) != ref_key:
                    ref_key = (snap.car_model, snap.track)
                    reference = _reference_text(snap.car_model, snap.track)

                lap = recorder.update(snap)
                if lap is not None:
                    if lap.valid:
                        path = save_lap(lap)
                        saved += 1
                        last_msg = f"saved {describe_lap(lap)}"
                        reference = _reference_text(snap.car_model, snap.track)
                    else:
                        last_msg = f"skipped partial lap ({len(lap.samples)} samples)"

                live.update(_status_panel(snap, saved, last_msg, reference))
                time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        reader.close()


if __name__ == "__main__":
    main()
