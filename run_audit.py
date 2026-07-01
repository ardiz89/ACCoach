"""Live cue-audit harness — record every coaching cue together with the exact
telemetry that triggered it, for surgical race-engineer review.

    python run_audit.py [--silent] [--hz N] [--out FILE]

Runs the real CoachEngine against the game's shared memory. It writes JSONL you
can read line by line:

  * a "hb" (heartbeat) line ~every 2 s: connection, lap, position, delta;
  * a "cue" line every time the coach speaks: the cue PLUS the live channels and
    the reference channels at that exact track position, so each suggestion can
    be checked against the data instead of from memory.

No game data is altered; this only reads telemetry and the coaching engine's
output. Stop with Ctrl+C — it prints a summary and flushes the file.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from accoach.coaching.tuning import tuning_for_car  # noqa: E402
from accoach.engine import CoachEngine  # noqa: E402


def _live(s) -> dict:
    return {
        "speed_kmh": round(s.speed_kmh, 1),
        "throttle": round(s.throttle, 3),
        "brake": round(s.brake, 3),
        "steer": round(s.steer_angle, 3),
        "gear": s.gear,
        "rpm": s.rpm,
        "yaw_rate": round(s.yaw_rate, 4),
        "slip_ratio": [round(x, 3) for x in s.slip_ratio],
        "abs_active": round(s.abs_active, 3),
        "tc_active": round(s.tc_active, 3),
        "accel_g": [round(x, 3) for x in s.accel_g],
        "tyre_core_temp": [round(x, 1) for x in s.tyre_core_temp],
        "tyre_pressure": [round(x, 1) for x in s.tyre_pressure],
        "tc_level": s.tc_level,
        "abs_level": s.abs_level,
        "brake_bias": round(s.brake_bias, 3),
        "fuel": round(s.fuel, 2),
    }


# Raw event thresholds — MIRROR accoach.coaching.events (kept local so the audit
# is an INDEPENDENT check, not a tautology against the same code path). If events.py
# changes its thresholds, update these to match.
_BRAKE_MIN = 0.30
_LOCK_RATIO = -0.15
_THROTTLE_MIN = 0.50


def _raw_lock(s) -> bool:
    return s.brake >= _BRAKE_MIN and min(s.slip_ratio[0], s.slip_ratio[1]) <= _LOCK_RATIO


def _raw_spin(s) -> bool:
    # Wheelspin slip ratio is class-dependent now (coaching.tuning): resolve it
    # from the live car so the mirror tracks the detector per class.
    if s.throttle < _THROTTLE_MIN or s.gear in ("R", "N"):
        return False
    spin_ratio = tuning_for_car(s.car_model).spin_ratio
    return max(s.slip_ratio[2], s.slip_ratio[3]) >= spin_ratio


# Balance thresholds — MIRROR accoach.coaching.balance (independent check).
_BAL_MIN_SPEED = 60.0
_YAW_SIGN = -1.0
_STEER_HARD = 0.15
_UNDERSTEER_RATIO = 0.9
_STEER_CATCH = 0.04
_YAW_LOOSE = 0.30


def _raw_oversteer(s) -> bool:
    if s.speed_kmh < _BAL_MIN_SPEED:
        return False
    yaw = s.yaw_rate * _YAW_SIGN
    return (abs(yaw) >= _YAW_LOOSE
            and abs(s.steer_angle) >= _STEER_CATCH
            and s.steer_angle * yaw < 0.0)


def _raw_understeer(s) -> bool:
    if s.speed_kmh < _BAL_MIN_SPEED or _raw_oversteer(s):
        return False
    steer = abs(s.steer_angle)
    if steer < _STEER_HARD:
        return False
    return (abs(s.yaw_rate) / steer) < _UNDERSTEER_RATIO


def _ref(rp) -> dict:
    # ReferencePoint carries raw wheel_slip (not the physical slip_ratio) and no
    # tyre temps — it's a recorded lap, so only what was stored is available.
    return {
        "speed_kmh": round(rp.speed_kmh, 1),
        "throttle": round(rp.throttle, 3),
        "brake": round(rp.brake, 3),
        "steer": round(rp.steer_angle, 3),
        "gear": rp.gear,
        "yaw_rate": round(rp.yaw_rate, 4),
        "wheel_slip": [round(x, 3) for x in rp.wheel_slip],
        "abs_active": round(rp.abs_active, 3),
        "tc_active": round(rp.tc_active, 3),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Live cue-audit harness")
    ap.add_argument("--silent", action="store_true", help="no voice, log only")
    ap.add_argument("--hz", type=float, default=30.0, help="poll rate (default 30)")
    ap.add_argument("--out", default=None, help="output JSONL path")
    a = ap.parse_args()

    voice = None
    if not a.silent:
        try:
            from accoach.coaching import Voice
            voice = Voice()
        except Exception as exc:  # pragma: no cover - optional dependency
            print(f"[audit] voice unavailable ({exc}); running silent")

    out_dir = Path.home() / "Documents" / "ACCoach" / "audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(a.out) if a.out else out_dir / f"audit_{stamp}.jsonl"

    engine = CoachEngine(voice=voice)
    interval = 1.0 / a.hz
    cues = 0
    raw_events = 0
    last_hb = 0.0
    connected = False
    _RAW = {"lock": _raw_lock, "spin": _raw_spin,
            "understeer": _raw_understeer, "oversteer": _raw_oversteer}
    raw_prev = {k: False for k in _RAW}

    print(f"[audit] writing {out_path}")
    print("[audit] waiting for the game...  (Ctrl+C to stop)")
    fh = out_path.open("w", encoding="utf-8")
    try:
        while True:
            now = time.monotonic()
            st = engine.tick(now)
            s = st.snapshot
            wall = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

            if s.connected != connected:
                connected = s.connected
                if connected:
                    print(f"[audit] CONNECTED - {s.car_model or '?'} @ {s.track or '?'} "
                          f"(status {s.status.name})")
                else:
                    print("[audit] disconnected")

            # Independent raw event ground-truth: log the rising edge of a real
            # lock/spin from the live snapshot, regardless of what the scheduler
            # decides to speak (and when). This is what each spoken event cue must
            # be matched against — detect-time, not speak-time.
            if s.connected and s.status.name == "LIVE" and not s.in_pit:
                for kind, fn in _RAW.items():
                    now_on = fn(s)
                    if now_on and not raw_prev[kind]:
                        raw_events += 1
                        fh.write(json.dumps({
                            "type": "raw_event", "kind": kind, "wall": wall,
                            "t": round(now, 3), "lap_pos": round(s.lap_position, 4),
                            "live": _live(s),
                        }, ensure_ascii=False) + "\n")
                        fh.flush()
                    raw_prev[kind] = now_on
            else:
                raw_prev = {k: False for k in _RAW}

            if st.spoken is not None:
                cues += 1
                d = round(st.delta.delta_ms, 1) if st.delta else None
                rec = {
                    "type": "cue",
                    "wall": wall,
                    "t": round(now, 3),
                    "lap_pos": round(s.lap_position, 4),     # snapshot pos at SPEAK time
                    "cue": {
                        "category": st.spoken.category.value,
                        "message": st.spoken.message,
                        "priority": round(st.spoken.priority, 1),
                        "segment": st.spoken.segment,
                        "pos": round(st.spoken.pos, 4),       # where the cue was GENERATED
                    },
                    "delta_ms": d,
                    "predicted_ms": int(st.delta.predicted_lap_ms) if st.delta else None,
                    "reference_ms": st.reference_ms,
                    "live": _live(s),
                    "ref": _ref(st.delta.reference_point) if st.delta else None,
                }
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                dtxt = f"{d:+.0f}ms" if d is not None else "n/a"
                msg = st.spoken.message.encode("ascii", "replace").decode("ascii")
                print(f"  >> [{st.spoken.category.value}] pos {rec['lap_pos']:.3f} "
                      f"delta {dtxt}  \"{msg}\"")

            if now - last_hb >= 2.0:
                last_hb = now
                hb = {
                    "type": "hb",
                    "wall": wall,
                    "connected": s.connected,
                    "status": s.status.name,
                    "car": s.car_model,
                    "track": s.track,
                    "in_pit": s.in_pit,
                    "lap_pos": round(s.lap_position, 3),
                    "completed_laps": s.completed_laps,
                    "saved_laps": st.saved_laps,
                    "reference_ms": st.reference_ms,
                    "delta_ms": round(st.delta.delta_ms, 1) if st.delta else None,
                }
                fh.write(json.dumps(hb, ensure_ascii=False) + "\n")
                fh.flush()

            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\n[audit] stopped - {cues} cue(s) + {raw_events} raw event(s) "
              f"logged -> {out_path}")
    finally:
        fh.close()
        engine.close()


if __name__ == "__main__":
    main()
