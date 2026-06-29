"""Live voice coach — phase 4 deliverable.

Ties the whole pipeline together: read telemetry → record laps → compute the
live delta to your best lap → analyze each segment → speak the most useful cue.

    python -m accoach.coach_app            # with voice (if pyttsx3 is installed)
    python -m accoach.coach_app --silent   # text-only cues, no audio

You need a reference lap first (drive at least one valid lap, or have one saved);
until then it records and stays quiet. Beat the reference and the next lap
becomes the one you're coached against.
"""

from __future__ import annotations

import sys
import time

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .coaching import Voice
from .comparison import DeltaState, format_delta
from .engine import CoachEngine
from .telemetry import TelemetrySnapshot, format_lap_time
from .telemetry.snapshot import ACStatus

REFRESH_HZ = 20


def _delta_panel(delta: DeltaState | None) -> Panel:
    if delta is None:
        return Panel(Text("no reference yet — drive a clean lap",
                          style="bold yellow", justify="center"),
                     title="Delta", border_style="grey50")
    color = "green" if delta.ahead else "red"
    big = Text(f"{format_delta(delta.delta_ms)} s", style=f"bold {color}")
    table = Table.grid(padding=(0, 1))
    table.add_column(justify="right", style="bold")
    table.add_column()
    table.add_row("Delta", big)
    table.add_row("Predicted", Text(format_lap_time(int(delta.predicted_lap_ms)),
                                     style="white"))
    table.add_row("Reference", Text(format_lap_time(delta.reference_lap_ms),
                                    style="magenta"))
    return Panel(table, title="Delta vs reference",
                 border_style="green" if delta.ahead else "red")


def _coach_panel(history: list[str], audio: bool) -> Panel:
    table = Table.grid(padding=(0, 1))
    table.add_column()
    if history:
        for line in history[-6:]:
            table.add_row(Text(line, style="bold white"))
    else:
        table.add_row(Text("listening… drive and I'll coach you", style="grey62"))
    mode = "🔊 voice" if audio else "📝 text"
    return Panel(table, title=f"Coach · {mode}", border_style="cyan")


_FOCUS_STYLE = {
    "brief": ("🎯", "bold yellow"), "drill": ("🎯", "yellow"),
    "improved": ("✅", "bold green"), "stuck": ("⏸", "grey62"),
    "clean": ("✨", "bold green"), "assess": ("…", "grey50"),
}


def _focus_panel(focus: dict | None) -> Panel:
    """The lesson plan: the one weakness being coached right now."""
    if not focus:
        return Panel(Text("warming up… drive a few clean laps", style="grey50"),
                     title="Focus", border_style="grey50")
    icon, style = _FOCUS_STYLE.get(focus.get("kind", ""), ("•", "white"))
    table = Table.grid(padding=(0, 1))
    table.add_column()
    table.add_row(Text(f"{icon} {focus['message']}", style=style))
    f = focus.get("focus")
    if f:
        table.add_row(Text(f"{f['name']} · {f['theme']} · "
                           f"−{f['baseline_ms'] / 1000.0:.2f}s", style="cyan"))
    return Panel(table, title="Focus · lesson", border_style="yellow")


def _status_panel(s: TelemetrySnapshot, saved: int) -> Panel:
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
    return Panel(table, title="HONE · voice coach", border_style="bright_blue")


def _render(s, delta, history, saved, audio, focus=None) -> Group:
    top = Table.grid(expand=True)
    top.add_column(ratio=1)
    top.add_column(ratio=1)
    top.add_row(_status_panel(s, saved), _delta_panel(delta))
    return Group(top, _coach_panel(history, audio), _focus_panel(focus))


def main(argv: list[str] | None = None) -> None:
    from .logging_setup import setup_logging
    setup_logging()
    argv = sys.argv[1:] if argv is None else argv
    silent = "--silent" in argv or "-s" in argv

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    interval = 1.0 / REFRESH_HZ
    from .config import load_config
    cfg = load_config()
    voice = Voice(enabled=not silent, language=cfg.language)
    engine = CoachEngine(voice=voice, acquire_hz=cfg.acquire.hz)

    try:
        with Live(_render(TelemetrySnapshot.disconnected(), None, [], 0, voice.is_audio),
                  refresh_per_second=REFRESH_HZ, screen=False) as live:
            while True:
                st = engine.tick(time.monotonic())
                live.update(_render(st.snapshot, st.delta, st.history,
                                    st.saved_laps, voice.is_audio, st.focus))
                time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        engine.close()


if __name__ == "__main__":
    main()
