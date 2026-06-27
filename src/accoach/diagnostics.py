"""Diagnostics you run against the live game to validate assumptions.

Right now it contains the G-force axis check. Every derived dynamics metric
(trail-braking, under/oversteer, the friction circle) assumes
``accel_g = (lateral, vertical, longitudinal)`` with longitudinal **positive
under acceleration / negative under braking** and lateral **positive turning
left**. That mapping is asserted in the telemetry layer but never verified
against a real car — a swapped axis or flipped sign would silently invert all
coaching. This tool confirms it from two natural maneuvers:

    python -m accoach.diagnostics gaxis      # then drive as prompted

* **Straight-line braking** (brake hard, wheel straight): expect a large
  *longitudinal* G that is **negative**, and *lateral* G near zero.
* **A steady corner** (constant cornering, off brakes): expect a large
  *lateral* G, and *longitudinal* G near zero. Turning left → positive lateral.

It auto-detects each maneuver, samples the peak, and prints a verdict.

Other commands validate the channels the new coaching modules rely on:

    python -m accoach.diagnostics live       # live dashboard of the key channels
    python -m accoach.diagnostics yaw         # verdict on the yaw_rate sign (balance.py)
    python -m accoach.diagnostics aids        # confirm TC/ABS/map/bias vs the in-car HUD
"""

from __future__ import annotations

import sys
import time

from .telemetry import SharedMemoryReader
from .telemetry.snapshot import ACStatus, format_lap_time

_BRAKE_HARD = 0.6
_STRAIGHT_STEER = 0.05      # rad — effectively straight
_CORNER_STEER = 0.20        # rad — clearly turning
_COAST_THROTTLE = 0.2       # below this we treat the corner as neutral/coasting
_MIN_SPEED = 60.0           # km/h, so the G is meaningful
_G_SIGNIFICANT = 0.4        # G magnitude that counts as a real event
_YAW_SIGNIFICANT = 0.15     # rad/s that counts as the car really rotating


def _utf8() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def _sample_loop(on_sample, seconds: float | None, interval: float,
                 wall_cap_s: float = 600.0) -> int:
    """Read the game, calling ``on_sample(snapshot, live_elapsed_s)`` for every
    LIVE frame.

    ``seconds`` counts **on-track time only** — the clock advances solely while
    telemetry is LIVE — so it doesn't matter how long the driver takes to get back
    on track after the capture starts; it records that many seconds of actual
    driving and then stops. ``wall_cap_s`` is a hard real-time backstop so a run
    that never sees the track still exits. Returns the number of live samples.
    """
    reader = SharedMemoryReader()
    seen = 0
    live_elapsed = 0.0
    status_frames: dict[str, int] = {}
    inpit_frames = 0
    start = time.monotonic()
    last = start
    try:
        while True:
            s = reader.read()
            now = time.monotonic()
            dt = now - last
            last = now
            label = s.status.name if s.connected else "DISCONNECTED"
            status_frames[label] = status_frames.get(label, 0) + 1
            if s.connected and s.status == ACStatus.LIVE:
                if s.in_pit:
                    inpit_frames += 1
                seen += 1
                live_elapsed += dt
                on_sample(s, live_elapsed)
            if seconds is not None and live_elapsed >= seconds:
                break
            if now - start >= wall_cap_s:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        reader.close()
        dist = ", ".join(f"{k}={v}" for k, v in sorted(status_frames.items()))
        print(f"\n[diag] frames by game status: {dist}; LIVE in-pit frames: {inpit_frames}")
    return seen


def _warn_if_no_live(seen: int) -> None:
    if seen == 0:
        print("! no LIVE telemetry captured — make sure ACC is ON TRACK in a "
              "LIVE session (not a menu, replay or paused).")
    else:
        print(f"(captured {seen} live samples)")


class _Peak:
    """Keeps the *simultaneous* (g_long, g_lat) of the frame where one chosen
    component peaked.

    Comparing peaks taken at different instants is wrong: corner-exit
    acceleration produces a real longitudinal G that has nothing to do with the
    axis mapping. By locking onto a single frame — the one where the *primary*
    axis is largest — both components are read at the same moment, so the verdict
    reflects one physical instant, not two unrelated ones.
    """

    def __init__(self, primary: str = "long") -> None:
        self.primary = primary      # "long" for braking, "lat" for cornering
        self.g_long = 0.0
        self.g_lat = 0.0
        self._peak = 0.0
        self.samples = 0

    def update(self, g_long: float, g_lat: float) -> None:
        self.samples += 1
        mag = abs(g_long) if self.primary == "long" else abs(g_lat)
        if mag > self._peak:
            self._peak = mag
            self.g_long = g_long
            self.g_lat = g_lat


def _verdict(brake_peak: _Peak, corner_peak: _Peak) -> None:
    print("\n" + "=" * 60)
    print("G-AXIS VERDICT")
    print("=" * 60)
    ok = True

    # Braking: longitudinal should dominate and be negative.
    bl, bx = brake_peak.g_long, brake_peak.g_lat
    print(f"\nStraight-line braking peak:  g_long={bl:+.2f}  g_lat={bx:+.2f}")
    if abs(bl) < _G_SIGNIFICANT:
        print("  ! no strong braking captured — longitudinal G stayed small.")
        ok = False
    elif abs(bx) > abs(bl):
        print("  ✗ lateral G exceeded longitudinal under braking — axes look SWAPPED.")
        ok = False
    elif bl > 0:
        print("  ✗ longitudinal G is POSITIVE under braking — sign is INVERTED "
              "(expected negative).")
        ok = False
    else:
        print("  ✓ longitudinal dominant and negative — as expected.")

    # Cornering: lateral should dominate.
    cl, cx = corner_peak.g_long, corner_peak.g_lat
    print(f"\nSteady-corner peak:          g_long={cl:+.2f}  g_lat={cx:+.2f}")
    if abs(cx) < _G_SIGNIFICANT:
        print("  ! no strong cornering captured — lateral G stayed small.")
        ok = False
    elif abs(cl) > abs(cx):
        print("  ✗ longitudinal G exceeded lateral in a corner — axes look SWAPPED.")
        ok = False
    else:
        print("  ✓ lateral dominant in the corner — as expected.")

    print("\n" + "-" * 60)
    if ok:
        print("RESULT: ✓ accel_g mapping (lat, vert, long) is CONFIRMED.")
    else:
        print("RESULT: ✗ mapping NOT confirmed — review accG indexing in "
              "reader.py / lap.py before trusting derived metrics.")
    print("=" * 60)


def run_gaxis() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    print("G-axis check. Enter a LIVE session, then:")
    print("  1) brake hard in a straight line a few times")
    print("  2) hold a steady corner (off the brakes) a few times")
    print("Press Ctrl+C when done to see the verdict.\n")

    reader = SharedMemoryReader()
    brake_peak = _Peak("long")
    corner_peak = _Peak("lat")
    captured = {"brake": False, "corner": False}

    try:
        while True:
            s = reader.read()
            if s.connected and s.status == ACStatus.LIVE and s.speed_kmh >= _MIN_SPEED:
                g_lat, _, g_long = s.accel_g
                straight = abs(s.steer_angle) < _STRAIGHT_STEER
                # Coasting through the corner isolates the neutral phase where
                # longitudinal G should be small, so accel/decel can't masquerade.
                coasting_corner = (
                    abs(s.steer_angle) > _CORNER_STEER
                    and s.brake < 0.1
                    and s.throttle < _COAST_THROTTLE
                )

                if s.brake >= _BRAKE_HARD and straight:
                    brake_peak.update(g_long, g_lat)
                    if not captured["brake"] and abs(g_long) > _G_SIGNIFICANT:
                        captured["brake"] = True
                        print(f"  captured braking event (g_long={g_long:+.2f})")
                elif coasting_corner:
                    corner_peak.update(g_long, g_lat)
                    if not captured["corner"] and abs(g_lat) > _G_SIGNIFICANT:
                        captured["corner"] = True
                        print(f"  captured cornering event (g_lat={g_lat:+.2f})")

            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        reader.close()
        _verdict(brake_peak, corner_peak)


def run_live(seconds: float | None = None) -> None:
    """Stream the channels the new coaching modules key off, for eyeballing the
    detector thresholds against real driving.

    With ``seconds`` set it runs for that long printing one full line per sample
    (so the output survives being captured when the game hides the terminal);
    otherwise it refreshes a single line in place until Ctrl+C.
    """
    _utf8()
    batch = seconds is not None
    print("Live channel monitor. Enter a LIVE session and drive.")
    print("  spd  gr rpm%  thr brk  steer   yaw   Flock Rspin abs tc  TC ABS  BB")
    seen = _sample_loop(
        lambda s, t: print((f"{t:5.1f}s" if batch else "\r") + _live_line(s),
                           end=("\n" if batch else ""), flush=True),
        seconds, interval=(0.5 if batch else 0.05),
    )
    print()
    _warn_if_no_live(seen)


def _live_line(s) -> str:
    """Format one monitor row from a snapshot (kept separate so it's testable)."""
    rpm_pct = (100.0 * s.rpm / s.max_rpm) if s.max_rpm else 0.0
    front_lock = min(s.slip_ratio[0], s.slip_ratio[1])   # most negative front
    rear_spin = max(s.slip_ratio[2], s.slip_ratio[3])    # fastest rear
    bb = f"{s.brake_bias:.2f}" if s.brake_bias >= 0 else " -- "
    return (
        f" {s.speed_kmh:4.0f} {s.gear:>2} {rpm_pct:3.0f}% "
        f"{s.throttle:3.1f} {s.brake:3.1f} "
        f"{s.steer_angle:+5.2f} {s.yaw_rate:+5.2f} "
        f"{front_lock:+5.2f} {rear_spin:+5.2f} "
        f"{s.abs_active:3.1f}{s.tc_active:4.1f} "
        f"{s.tc_level:2d} {s.abs_level:2d} {bb:>5}"
    )


def run_yaw(seconds: float | None = None) -> None:
    """Verdict on whether ``yaw_rate`` shares a sign convention with ``steer_angle``
    — the one assumption ``balance.py`` makes for oversteer detection (``_YAW_SIGN``).

    In a clean, grippy corner (off the brakes, no big slide) steering and yaw must
    point the *same* way: turn left (steer > 0) and the car yaws left. If the data
    shows them consistently opposite, ``_YAW_SIGN`` must be flipped to -1.
    """
    _utf8()
    print("Yaw-sign check. Enter a LIVE session, then drive several CLEAN")
    print("corners (both left and right, smooth, no sliding).")
    print("Ctrl+C for the verdict." if seconds is None
          else f"Running for {seconds:.0f}s, then a verdict.\n")

    stats = {"agree": 0, "disagree": 0, "left": 0, "right": 0}

    def on_sample(s, _t) -> None:
        if s.speed_kmh < _MIN_SPEED:
            return
        clean_corner = (
            abs(s.steer_angle) > _CORNER_STEER
            and abs(s.yaw_rate) > _YAW_SIGNIFICANT
            and s.brake < 0.1
            and s.abs_active < 0.2
            and s.tc_active < 0.2
        )
        if not clean_corner:
            return
        stats["agree" if s.steer_angle * s.yaw_rate > 0 else "disagree"] += 1
        stats["left" if s.steer_angle > 0 else "right"] += 1

    seen = _sample_loop(on_sample, seconds, 0.02)
    _warn_if_no_live(seen)
    _yaw_verdict(stats["agree"], stats["disagree"], stats["left"], stats["right"])


def _yaw_verdict(agree: int, disagree: int, left_seen: int, right_seen: int) -> None:
    print("\n" + "=" * 60)
    print("YAW-SIGN VERDICT")
    print("=" * 60)
    total = agree + disagree
    print(f"\nclean-corner frames: {total}  (left {left_seen}, right {right_seen})")
    print(f"steer & yaw same sign: {agree}   opposite: {disagree}")
    if total < 50:
        print("\n! not enough clean cornering captured — drive more smooth corners.")
    elif left_seen < 10 or right_seen < 10:
        print("\n! sample is one-sided — capture both left and right corners.")
    elif agree >= total * 0.8:
        print("\n✓ steer and yaw share a sign. balance.py _YAW_SIGN = 1.0 is CORRECT.")
    elif disagree >= total * 0.8:
        print("\n✗ steer and yaw are OPPOSITE. Set balance.py _YAW_SIGN = -1.0 "
              "(else clean corners false-fire as OVERSTEER).")
    else:
        print("\n? inconclusive — signs are mixed. Capture cleaner corners and re-run "
              "before trusting oversteer detection.")
    print("=" * 60)


def run_aids(seconds: float | None = None) -> None:
    """Confirm the ACC aid-level mapping: change TC/ABS/map/brake-bias in the car
    and watch the values move. It logs a line each time a value *changes* (so the
    knob turns stand out), in both timed and Ctrl+C modes. Stale -1s mean the
    graphics-page offsets in structs.py are wrong; a frozen brake_bias means
    reader._brake_bias needs its plausibility band widened."""
    _utf8()
    print("Aid-level check. In a LIVE session, change TC / ABS / engine map /")
    print("brake bias on the wheel and confirm these track the in-car HUD.")
    print("Ctrl+C to stop." if seconds is None
          else f"Running for {seconds:.0f}s — turn the knobs now.\n")

    state = {"last": None}

    def on_sample(s, t) -> None:
        key = (s.tc_level, s.abs_level, s.engine_map, round(s.brake_bias, 3))
        if key == state["last"]:
            return
        state["last"] = key
        bb = f"{s.brake_bias:.3f}" if s.brake_bias >= 0 else "unknown"
        print(f"[{t:5.1f}s] TC={s.tc_level:2d}  ABS={s.abs_level:2d}  "
              f"map={s.engine_map:2d}  brake_bias={bb}", flush=True)

    seen = _sample_loop(on_sample, seconds, 0.1)
    _warn_if_no_live(seen)


def run_sectors(seconds: float | None = None) -> None:
    """Validate the sim's real sector data (``currentSectorIndex`` / ``sectorCount``)
    that the Settori view and the ideal lap depend on.

    Drive at least one full, clean lap. It logs every time the sector index
    changes — the position and lap time at the boundary — so you can confirm the
    splits land where the track's real sectors are. A current_sector stuck at -1
    (or sector_count 0) means the graphics/static offsets in structs.py are wrong
    for this game/content, and the view will fall back to equal thirds."""
    _utf8()
    print("Sector check. In a LIVE session, drive a full lap (or two).")
    print("Each sector change is logged with the position and time it happened.")
    print("Ctrl+C to stop." if seconds is None
          else f"Running for {seconds:.0f}s of driving — go.\n")

    state: dict = {"prev": None, "count": None, "valid": 0, "seen": set(),
                   "bounds": {}}

    def on_sample(s, t) -> None:
        if s.sector_count and state["count"] != s.sector_count:
            state["count"] = s.sector_count
            print(f"[{t:5.1f}s] il gioco riporta {s.sector_count} settori", flush=True)
        cur = s.current_sector
        if cur >= 0:
            state["valid"] += 1
            state["seen"].add(cur)
        prev = state["prev"]
        if prev is not None and cur != prev:
            arrow = "↩ traguardo" if cur < prev else "→"
            if cur > prev:
                state["bounds"][cur] = s.lap_position
            print(f"[{t:5.1f}s] settore {prev} {arrow} {cur}  @ pos "
                  f"{s.lap_position:.3f}  (giro {format_lap_time(int(s.current_lap_ms))})",
                  flush=True)
        state["prev"] = cur

    seen = _sample_loop(on_sample, seconds, 0.02)
    _warn_if_no_live(seen)
    _sectors_verdict(state)


def _sectors_verdict(state: dict) -> None:
    print("\n" + "=" * 60)
    print("VERDETTO SETTORI")
    print("=" * 60)
    count = state["count"]
    distinct = sorted(state["seen"])
    print(f"\nsector_count dal gioco: {count if count else 'sconosciuto (0)'}")
    print(f"settori visti guidando: {distinct or 'nessuno'}")
    if state["bounds"]:
        bs = ", ".join(f"S{k}@{p:.3f}" for k, p in sorted(state["bounds"].items()))
        print(f"posizioni di confine: {bs}")
    print()
    if state["valid"] == 0:
        print("✗ current_sector è sempre -1 — l'offset currentSectorIndex in "
              "structs.py è sbagliato per questo gioco/contenuto, oppure il "
              "contenuto AC non pubblica i settori. La vista Settori userà i terzi.")
    elif not count:
        print("? gli indici settore si leggono, ma sector_count è 0 — i confini "
              "funzionano comunque (ricavati dalle transizioni); verifica solo "
              "l'offset sectorCount in structs.py se ti serve il conteggio.")
    elif len(distinct) >= count >= 2:
        print(f"✓ settori OK: visti {len(distinct)} indici distinti su {count} "
              "attesi, con confini a posizioni crescenti. La vista Settori userà "
              "gli split reali del gioco.")
    else:
        print(f"? parziale: attesi {count} settori ma visti {len(distinct)} — "
              "guida un giro intero e pulito e ripeti. Se resta sotto, controlla "
              "l'offset in structs.py.")
    print("=" * 60)


def run_dryrun(seconds: float | None = None) -> None:
    """Dry-run the live technique detectors and print every cue they'd raise, with
    the channel values that triggered it — the instrument for tuning thresholds
    against a real car. Bypasses the scheduler/TTS so nothing is throttled.

    Drive a clean lap first (ideally nothing fires), then deliberately provoke an
    understeer, an oversteer, a lock-up, a wheelspin and a too-tall gear, and check
    each is named with sane numbers.
    """
    _utf8()
    from .coaching import BalanceDetector, BrakingDetector, EventDetector, GearDetector

    detectors = [EventDetector(), BalanceDetector(), BrakingDetector(), GearDetector()]
    counts: dict[str, int] = {}
    print("Coach dry-run. Drive a clean lap, then provoke faults on purpose.")
    print("Every cue the detectors raise is printed with its trigger values.\n")

    def on_sample(s, t) -> None:
        flock = min(s.slip_ratio[0], s.slip_ratio[1])
        rspin = max(s.slip_ratio[2], s.slip_ratio[3])
        for det in detectors:
            for cue in det.update(s, t):
                counts[cue.category.value] = counts.get(cue.category.value, 0) + 1
                print(f"[{t:6.1f}s pos{s.lap_position:.2f}] {cue.category.value:11} | "
                      f"spd{s.speed_kmh:3.0f} st{s.steer_angle:+.2f} yaw{s.yaw_rate:+.2f} "
                      f"brk{s.brake:.1f} thr{s.throttle:.1f} Flk{flock:+.2f} Rsp{rspin:+.2f} "
                      f"abs{s.abs_active:.1f} tc{s.tc_active:.1f} | {cue.message}",
                      flush=True)

    seen = _sample_loop(on_sample, seconds, 0.02, wall_cap_s=240.0)
    _warn_if_no_live(seen)
    print("\n--- cue counts ---")
    if counts:
        for cat, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"  {cat:12} {n}")
    else:
        print("  (none fired)")


def run_stats(seconds: float | None = None) -> None:
    """Record channel distributions over a drive — especially in the regimes the
    detectors care about (hard braking, hard cornering, throttle-on) — so the
    thresholds can be set from real numbers instead of guesses."""
    _utf8()
    print("Stats capture. Drive normally, then a few HARD brakings (try to lock),")
    print("a few throttle-on slides, and a couple of too-hot corner entries.\n")

    A = {k: [] for k in ("abs", "tc", "steer", "yaw", "flock", "rspin")}
    brake_lock = []     # front-lock slip while braking hard
    brake_abs = []      # abs_active while braking hard
    thr_spin = []       # rear-spin slip while on throttle
    thr_tc = []         # tc_active while on throttle
    corner_ratio = []   # |yaw| / |steer| in clean fast corners

    def on_sample(s, _t) -> None:
        flock = min(s.slip_ratio[0], s.slip_ratio[1])
        rspin = max(s.slip_ratio[2], s.slip_ratio[3])
        A["abs"].append(s.abs_active); A["tc"].append(s.tc_active)
        A["steer"].append(abs(s.steer_angle)); A["yaw"].append(abs(s.yaw_rate))
        A["flock"].append(flock); A["rspin"].append(rspin)
        if s.brake > 0.5:
            brake_lock.append(flock); brake_abs.append(s.abs_active)
        if s.throttle > 0.7 and s.speed_kmh > 40:
            thr_spin.append(rspin); thr_tc.append(s.tc_active)
        if abs(s.steer_angle) > 0.15 and s.brake < 0.1 and s.speed_kmh > 60:
            corner_ratio.append(abs(s.yaw_rate) / abs(s.steer_angle))

    seen = _sample_loop(on_sample, seconds, 0.02, wall_cap_s=240.0)
    _warn_if_no_live(seen)
    if seen == 0:
        return

    def pct(xs, p):
        if not xs:
            return float("nan")
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(p / 100 * len(xs)))]

    def line(name, xs):
        print(f"  {name:16} n={len(xs):5d}  min={pct(xs,0):+.3f}  p50={pct(xs,50):+.3f}  "
              f"p90={pct(xs,90):+.3f}  p99={pct(xs,99):+.3f}  max={pct(xs,100):+.3f}")

    print("\n=== CHANNEL DISTRIBUTIONS ===")
    line("abs_active", A["abs"]); line("tc_active", A["tc"])
    line("|steer| rad", A["steer"]); line("|yaw| rad/s", A["yaw"])
    line("front-lock slip", A["flock"]); line("rear-spin slip", A["rspin"])
    print("\n=== BRAKING HARD (brake>0.5) ===")
    line("front-lock slip", brake_lock); line("abs_active", brake_abs)
    print("\n=== ON THROTTLE (>0.7) ===")
    line("rear-spin slip", thr_spin); line("tc_active", thr_tc)
    print("\n=== CLEAN FAST CORNERS (|steer|>0.15, off brake) ===")
    line("|yaw|/|steer|", corner_ratio)
    print("  (understeer ~= yaw/steer well BELOW this median for the steering applied)")


def run_selftest(report_path: str | None = None) -> str:
    """Check the TTS voice (works even windowed: writes a JSON report to a file)."""
    import json
    import tempfile
    import time
    from pathlib import Path

    from .coaching import Voice

    report: dict = {"frozen": bool(getattr(sys, "frozen", False))}
    try:
        import pyttsx3
        report["pyttsx3"] = getattr(pyttsx3, "__version__", "?")
    except Exception as e:  # noqa: BLE001
        report["pyttsx3"] = f"MISSING: {e!r}"

    try:
        v = Voice(enabled=True)
        report["is_audio"] = v.is_audio
        report["prerendered_cues"] = len(v._prerendered)
        if v._engine is not None:
            vid = v._engine.getProperty("voice")
            names = [x.name for x in v._engine.getProperty("voices") if x.id == vid]
            report["voice"] = names[0] if names else str(vid)
        # A pre-rendered (neural Piper) cue, then a SAPI5-fallback phrase.
        v.say("Puoi frenare più tardi")
        time.sleep(2.5)
        v.say("Self test completato.")
        time.sleep(2.0)
        v.close()
        report["spoke"] = True
    except Exception as e:  # noqa: BLE001
        report["error"] = repr(e)

    path = Path(report_path or (Path(tempfile.gettempdir()) / "accoach_selftest.json"))
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("self-test report written to", path)
    return str(path)


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "live"
    seconds = _arg_value(argv, "--seconds", "-s")
    secs = float(seconds) if seconds is not None else None
    if cmd in ("gaxis", "g", "g-axis"):
        run_gaxis()
    elif cmd in ("live", "monitor", "mon"):
        run_live(secs)
    elif cmd in ("yaw", "yaw-sign", "balance"):
        run_yaw(secs)
    elif cmd in ("aids", "aid"):
        run_aids(secs)
    elif cmd in ("sectors", "sector", "sec"):
        run_sectors(secs)
    elif cmd in ("dryrun", "dry", "coach"):
        run_dryrun(secs)
    elif cmd in ("stats", "stat"):
        run_stats(secs)
    else:
        print(f"unknown diagnostic: {cmd!r}. "
              "Available: live, dryrun, stats, yaw, aids, sectors, gaxis")


def _arg_value(argv: list[str], *names: str) -> str | None:
    """Value following any of ``names`` in ``argv`` (e.g. --seconds 30), else None."""
    for name in names:
        if name in argv:
            i = argv.index(name)
            if i + 1 < len(argv):
                return argv[i + 1]
    return None


if __name__ == "__main__":
    main()
