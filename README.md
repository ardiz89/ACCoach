# ACCoach

Real-time driving coach for **Assetto Corsa** and **Assetto Corsa Competizione**.

The goal: read live telemetry while you drive, analyze your driving style, and
give you real-time suggestions (voice + on-screen overlay) on how to improve —
plus a step-by-step car setup assistant.

## Status

**Phase 1 — Foundations (done):** telemetry acquisition + raw-data monitor.

- `accoach.telemetry` — reads the AC/ACC shared memory (Physics, Graphics,
  Static pages) and exposes a clean, game-agnostic `TelemetrySnapshot`.
- `accoach.monitor` — a live terminal dashboard showing everything the coach
  can "see" (inputs, engine, tyres, dynamics, timing). Use it to verify the
  pipeline works before building analysis on top.

**Phase 2 — Lap recording (done):** capture and persist laps.

- `accoach.recording` — turns the snapshot stream into completed laps
  (`LapRecorder`), modeled as position-keyed samples (`Lap`/`LapSample`) and
  saved as gzipped JSON in `laps/`. The fastest valid lap per car+track is the
  reference the coaching layer will compare against.
- `accoach.recorder_app` — a live recorder that saves each lap as you drive.

**Phase 3 — Reference-lap comparison (done):** live delta to your best lap.

- `accoach.comparison` — `Reference` turns a recorded lap into a position-indexed
  lookup (interpolated time + channels); `LapComparator` returns a live
  `DeltaState` (gap to reference, predicted lap time) lined up by track position.
- `accoach.compare_app` — records laps *and* shows the live delta to the fastest
  valid lap; beat it and the next lap becomes the reference.

**Phase 4 — Voice coaching (done):** spoken, real-time suggestions.

- `accoach.coaching` — `CoachAnalyzer` divides the track into its real corners
  (detected from the reference by `accoach.track`, fixed segments as fallback),
  compares your channels to the reference's, and learns where you lose time. It
  coaches **feed-forward**: a corner's advice (brake later, more throttle, carry
  speed…) is spoken on the *approach to that corner on the next lap* — where it
  can still help — and is dropped once you take the corner well. `EventDetector`
  calls out lock-ups and wheelspin live from ABS/TC intervention and wheel slip
  (no reference needed); `CueScheduler` picks the most valuable cue and
  rate-limits it; `Voice` speaks it via offline TTS (text fallback if `pyttsx3`
  is absent). The fixed cue phrases are pre-rendered with **Piper neural TTS**
  (build-time, shipped as WAVs) for a more human voice and instant playback;
  dynamic/numeric phrases fall back to SAPI5. `build_lap_debrief` produces the
  cold post-lap breakdown (worst corners + cause + consistency).
- `accoach.coach_app` — the full loop: record → delta → analyze → speak.
- `accoach.debrief_app` — review a saved lap: where the time went, per corner.

**Data foundation (done):** richer channels + an indexed catalog.

- Recorded laps now carry the signals coaching needs to explain *why* time was
  lost: per-wheel slip, ABS/TC intervention, yaw rate, and tyre core temps (lap
  schema v2; older v1 laps still load, missing channels default). `Reference`
  exposes them all (plus steering and lateral G) for cause attribution.
- `accoach.recording.catalog` — a SQLite index beside the lap files, so finding
  the reference lap is one indexed lookup instead of scanning and decompressing
  the whole `laps/` folder. The index is a rebuildable cache; the files stay the
  source of truth.
- `accoach.diagnostics` — a live G-axis check that validates the telemetry's
  acceleration mapping before any derived metric trusts it.

**Frontend backbone (in progress):** headless engine + state broadcast.

- `accoach.engine` — `CoachEngine` runs the whole live loop (read → record →
  compare → analyze → speak) and returns an `EngineState` each `tick`, decoupled
  from any UI. The terminal coach and the server share this one implementation.
- `accoach.serialize` — turns an `EngineState` into a JSON-able dict for clients.
- `accoach.server` — a FastAPI backend that runs the engine and broadcasts state
  over WebSocket (`ws://127.0.0.1:8777/ws`); the on-screen overlay and the
  analysis app are just clients.
- `accoach.overlay` — a transparent, always-on-top, click-through HUD (PySide6)
  showing the delta bar, predicted/reference times and the current cue, drawn
  over the game. It can be fed over WebSocket (server mode) or in-process.
- `accoach.app` — **live mode**: engine + voice + overlay in one process (no
  second terminal, no socket). `accoach.launcher` — a small GUI with a button
  per mode. `python -m accoach` is the unified entry point.
- `accoach.api` — the **analysis web app**: a local web page (served by FastAPI)
  to review saved laps in the browser — overlaid speed/throttle/brake traces vs
  the reference, the delta across the lap, corner bands, and the debrief.

Planned next: analysis web app → setup assistant. See the expert-panel roadmap.

## Quick start

Double-click **`ACCoach.bat`** for a launcher with a button per mode, or from a
terminal:

```powershell
pip install -r requirements.txt   # first time (PySide6 for the overlay/GUI)
python -m accoach live            # coach + on-screen overlay in one window
python -m accoach live --demo     # see it work with a synthetic lap, no game
python -m accoach                 # list every command
```

Set the game to **Borderless** so the overlay draws over it. `--silent` disables
the voice.

## How it works

Both games publish live telemetry through three Windows memory-mapped files
(`Local\acpmf_physics`, `Local\acpmf_graphics`, `Local\acpmf_static`). They
share a common layout; ACC extends it with extra fields. ACCoach maps the full
ACC layout, reads only the bytes that actually exist (plain AC allocates less),
and normalizes everything into `TelemetrySnapshot`.

## Setup

```powershell
pip install -r requirements.txt
```

Requires Python 3.11+ on Windows (the shared memory is Windows-only).

## Run the live monitor

1. Start Assetto Corsa or ACC and enter a session (practice/hotlap/race).
2. From the project root:

   ```powershell
   python run_monitor.py
   ```

The dashboard auto-connects when the game starts publishing telemetry and shows
a waiting state otherwise. `Ctrl+C` to quit.

## Record laps

While driving, run the recorder to save every completed lap to `laps/`:

```powershell
python run_recorder.py
```

The first (partial) lap after you start is skipped; full laps are saved and the
fastest valid one for the current car+track is shown as the reference. `Ctrl+C`
to quit.

## Live delta coach

To record *and* see a live delta to your best lap at the same time:

```powershell
python run_compare.py
```

The delta is positive when you're slower than the reference, negative when
faster, and updates as you go round; it also shows the predicted lap time and
what the reference was doing (speed, throttle, brake, gear) at your position.

## Voice coach

For spoken, real-time coaching while you drive:

```powershell
python run_coach.py            # with voice (needs pyttsx3)
python run_coach.py --silent   # text-only cues, no audio
```

It records laps, tracks the delta to your best, and speaks the single most
useful suggestion per situation ("brake later", "more throttle here", "carry
more speed"), rate-limited so it never talks over itself.

## Post-session debrief

After driving, review where the time actually went (reads saved laps, game not
needed):

```powershell
python run_debrief.py                  # your most recent lap
python run_debrief.py ferrari spa      # filter by car / track
```

It ranks your worst corners against your reference lap, names the likely cause
of each loss, and summarizes your lap-time consistency.

## On-screen overlay

A glanceable HUD over the game (delta bar + current cue). Run the backend, then
the overlay (needs `pip install PySide6`, and the game set to **Borderless**):

```powershell
python run_server.py     # backend (broadcasts state on ws://127.0.0.1:8777/ws)
python run_overlay.py    # transparent overlay; --interactive to move/close it
```

The overlay is click-through by default so it never steals input from the game.

## Analysis web app

Review your laps in the browser (reads saved laps, game not needed):

```powershell
python -m accoach web          # then open http://127.0.0.1:8778
python -m accoach web --demo    # try it with synthetic laps
```

Pick a car+track, a lap to review and a lap to compare it against (any two of
your laps, default = fastest), and see speed/throttle/brake traces overlaid, the
delta across the lap with corner bands, and the worst-corner debrief. Hover the
charts for a point-by-point readout (your speed vs the comparison lap, delta,
inputs, gear), and **export** the selected lap's full-resolution telemetry as
CSV or JSON. An **Andamento** (progress) tab charts your lap-time trend over
time, your consistency, and your most recurring mistakes per track.

## Validate the G-force axes

Derived metrics assume `accel_g = (lateral, vertical, longitudinal)`. Confirm it
against your install once:

```powershell
python run_verify_g.py
```

Drive as prompted (hard straight-line braking, then a steady corner); it prints
a verdict on whether the axis/sign mapping holds.

## Package as an executable

To build a standalone `ACCoach.exe` (no Python needed to run it):

```powershell
pip install pyinstaller
build_exe.bat            # -> dist\ACCoach\ACCoach.exe
```

The exe is the unified entry point: `ACCoach.exe` opens the launcher,
`ACCoach.exe live`, `ACCoach.exe web`, etc. run a specific mode.

The neural cue WAVs are pre-rendered with Piper (`tools/render_cues.py`, needs
`tools/piper/` — build-time only, not shipped). Re-run it when cue phrases change.

## Project layout

```
src/accoach/
  telemetry/
    structs.py     # ctypes layout of the AC/ACC shared memory
    snapshot.py    # clean game-agnostic TelemetrySnapshot + enums
    reader.py      # Win32 shared-memory reader -> snapshots
  recording/
    lap.py         # Lap / LapSample model + (de)serialization (schema v2)
    recorder.py    # LapRecorder: snapshot stream -> completed laps
    storage.py     # save/load laps, find the reference lap (catalog-backed)
    catalog.py     # SQLite index over the lap files
  comparison/
    reference.py   # Reference: position-indexed view of a recorded lap
    delta.py       # LapComparator: live delta + predicted lap time
  coaching/
    cue.py         # Cue / CueCategory: a piece of spoken advice
    analyzer.py    # CoachAnalyzer: per-corner comparison + cause attribution
    events.py      # EventDetector: live lock-up / wheelspin cues
    debrief.py     # build_lap_debrief: post-lap breakdown + consistency
    scheduler.py   # CueScheduler: pick + rate-limit what gets said
    voice.py       # Voice: offline TTS worker (text fallback)
  track.py         # detect_corners: real corners from a reference lap
  engine.py        # CoachEngine: headless live loop -> EngineState
  serialize.py     # EngineState -> JSON for frontends
  server.py        # FastAPI backend: run engine, broadcast over WebSocket
  overlay.py       # PySide6 transparent on-screen HUD
  app.py           # live mode: engine + voice + overlay in one process
  launcher.py      # PySide6 GUI launcher (a button per mode)
  api.py           # analysis web app: REST over saved laps + static frontend
  web/             # the analysis page (index.html, app.js, style.css)
  __main__.py      # unified entry point: python -m accoach <command>
  diagnostics.py   # live checks (G-axis validation)
  monitor.py       # live terminal dashboard (phase 1 deliverable)
  recorder_app.py  # live lap recorder (phase 2 deliverable)
  compare_app.py   # live delta coach (phase 3 deliverable)
  coach_app.py     # live voice coach (phase 4 deliverable)
  debrief_app.py   # post-session lap debrief
run_monitor.py     # convenience launcher (no install needed)
run_recorder.py    # convenience launcher for the recorder
run_compare.py     # convenience launcher for the delta coach
run_coach.py       # convenience launcher for the voice coach
run_debrief.py     # convenience launcher for the debrief
run_server.py      # convenience launcher for the headless backend
run_overlay.py     # convenience launcher for the on-screen overlay
run_live.py        # convenience launcher for live mode (one window)
run_launcher.py    # convenience launcher for the GUI launcher
run_web.py         # convenience launcher for the analysis web app
run_verify_g.py    # convenience launcher for the G-axis check
ACCoach.bat        # double-click -> GUI launcher
```
