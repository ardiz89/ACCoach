"""Live telemetry monitor — the raw-data visualization for phase 1.

Run it to confirm the whole acquisition chain works end to end:

    python -m accoach.monitor

It shows a continuously updating dashboard of everything the coach can "see".
When the game isn't running it shows a waiting state and connects automatically
as soon as AC/ACC starts publishing telemetry.
"""

from __future__ import annotations

import sys
import time

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .telemetry import SharedMemoryReader, TelemetrySnapshot, format_lap_time
from .telemetry.snapshot import ACStatus

REFRESH_HZ = 30
WHEELS = ("FL", "FR", "RL", "RR")


def _bar(value: float, width: int = 24, color: str = "green") -> Text:
    """A 0..1 horizontal bar."""
    value = max(0.0, min(1.0, value))
    filled = int(round(value * width))
    bar = Text()
    bar.append("█" * filled, style=color)
    bar.append("─" * (width - filled), style="grey37")
    bar.append(f" {value * 100:5.1f}%")
    return bar


def _inputs_panel(s: TelemetrySnapshot) -> Panel:
    table = Table.grid(padding=(0, 1))
    table.add_column(justify="right", style="bold")
    table.add_column()
    table.add_row("Throttle", _bar(s.throttle, color="green"))
    table.add_row("Brake", _bar(s.brake, color="red"))
    if s.clutch:
        table.add_row("Clutch", _bar(s.clutch, color="yellow"))
    # steering: map radians to a -1..1-ish visual
    steer = max(-1.0, min(1.0, s.steer_angle))
    table.add_row("Steer", Text(f"{s.steer_angle:+.2f} rad", style="cyan"))
    table.add_row("Gear", Text(s.gear, style="bold magenta"))

    rev = (s.rpm / s.max_rpm) if s.max_rpm else 0.0
    rev_color = "red" if rev > 0.95 else "yellow" if rev > 0.85 else "green"
    table.add_row("RPM", _bar(rev, color=rev_color))
    table.add_row("", Text(f"{s.rpm} / {s.max_rpm}", style="grey62"))
    table.add_row("Speed", Text(f"{s.speed_kmh:6.1f} km/h", style="bold white"))
    return Panel(table, title="Inputs & Engine", border_style="blue")


def _tyres_panel(s: TelemetrySnapshot) -> Panel:
    table = Table(show_header=True, header_style="bold", expand=True)
    table.add_column("Wheel")
    table.add_column("Core °C", justify="right")
    table.add_column("Press psi", justify="right")
    table.add_column("Brake °C", justify="right")
    table.add_column("Slip", justify="right")
    for i, w in enumerate(WHEELS):
        table.add_row(
            w,
            f"{s.tyre_core_temp[i]:.0f}",
            f"{s.tyre_pressure[i]:.1f}",
            f"{s.brake_temp[i]:.0f}",
            f"{s.wheel_slip[i]:.2f}",
        )
    return Panel(table, title="Tyres", border_style="yellow")


def _dynamics_panel(s: TelemetrySnapshot) -> Panel:
    table = Table.grid(padding=(0, 1))
    table.add_column(justify="right", style="bold")
    table.add_column()
    gx, gy, gz = s.accel_g
    table.add_row("G lat", Text(f"{gx:+.2f}", style="cyan"))
    table.add_row("G long", Text(f"{gz:+.2f}", style="cyan"))
    table.add_row("G vert", Text(f"{gy:+.2f}", style="grey62"))
    table.add_row("ABS", _bar(s.abs_active, width=12, color="red"))
    table.add_row("TC", _bar(s.tc_active, width=12, color="orange3"))
    return Panel(table, title="Dynamics & Assists", border_style="magenta")


def _timing_panel(s: TelemetrySnapshot) -> Panel:
    table = Table.grid(padding=(0, 1))
    table.add_column(justify="right", style="bold")
    table.add_column()
    table.add_row("Current", Text(format_lap_time(s.current_lap_ms), style="white"))
    table.add_row("Last", Text(format_lap_time(s.last_lap_ms), style="cyan"))
    table.add_row("Best", Text(format_lap_time(s.best_lap_ms), style="bold green"))
    table.add_row("Lap", Text(str(s.completed_laps), style="white"))
    table.add_row("Track pos", _bar(s.lap_position, width=20, color="blue"))
    table.add_row("Fuel", Text(f"{s.fuel:.1f} L", style="grey70"))
    table.add_row("Pit", Text("YES" if s.in_pit else "no",
                              style="red" if s.in_pit else "grey50"))
    return Panel(table, title="Timing & Session", border_style="green")


def _header(s: TelemetrySnapshot) -> Panel:
    if not s.connected:
        body = Text("Waiting for Assetto Corsa / ACC…  (start the game & enter a session)",
                    style="bold yellow")
    else:
        live = s.status == ACStatus.LIVE
        dot = Text("● ", style="green" if live else "grey50")
        body = Text.assemble(
            dot,
            (f"{s.car_model or '?'}", "bold white"),
            ("  @  ", "grey50"),
            (f"{s.track or '?'}", "bold white"),
            ("    status=", "grey50"),
            (s.status.name, "cyan"),
            ("  session=", "grey50"),
            (s.session.name, "cyan"),
        )
    return Panel(body, title="HONE · live telemetry", border_style="bright_blue")


def _render(s: TelemetrySnapshot) -> Group:
    if not s.connected:
        return Group(_header(s))
    top = Table.grid(expand=True)
    top.add_column(ratio=1)
    top.add_column(ratio=1)
    top.add_row(_inputs_panel(s), _timing_panel(s))
    bottom = Table.grid(expand=True)
    bottom.add_column(ratio=2)
    bottom.add_column(ratio=1)
    bottom.add_row(_tyres_panel(s), _dynamics_panel(s))
    return Group(_header(s), top, bottom)


def main() -> None:
    # Unicode bars/dots break on legacy Windows consoles (cp1252); force UTF-8.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    interval = 1.0 / REFRESH_HZ
    reader = SharedMemoryReader()
    try:
        with Live(_render(TelemetrySnapshot.disconnected()),
                  refresh_per_second=REFRESH_HZ, screen=False) as live:
            while True:
                snap = reader.read()
                live.update(_render(snap))
                time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        reader.close()


if __name__ == "__main__":
    main()
