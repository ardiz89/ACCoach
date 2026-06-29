<h1 align="center">HONE</h1>
<p align="center"><b>Know why you're slow.</b></p>
<p align="center">The real-time driving coach for Assetto Corsa and ACC — it tells you <i>why</i> you lose time, not just where. Offline. No subscription.</p>

---

HONE reads your live telemetry while you drive, works out **where** you lose time
and — the part nobody else does — **why**, says it out loud and on a glanceable
overlay, then breaks the lap down corner by corner afterwards and, when you want,
rewrites your car setup lap after lap.

> 🏁 Free and complete today. Everything runs on your PC: no account, no cloud,
> nothing leaves your machine.

<!-- TODO: "wow" GIF here — overlay + voice through a lap, then the debrief's "why". -->
<!-- ![HONE in action](docs/assets/demo.gif) -->

## Why HONE is different

There are great tools for sim racing (overlays, spotters, cloud analysis). HONE
doesn't compete on those — it does three things the others don't do together.

1. **It tells you the *why*, not just the *what*.** Not "you braked too early",
   but *"the car understeers at the apex in slow corners — carry more entry
   speed."* Causal handling diagnosis (under/oversteer × entry/apex/exit ×
   speed), braking broken down (how many metres early you brake, peak pressure),
   and time lost down a straight attributed to the corner that caused it.

2. **A real race engineer — even for road cars.** It closes the loop
   *telemetry → diagnosis → setup change → apply → re-test*: one change at a time,
   you re-drive, it's kept only if it actually helps. Three profiles (Formula,
   GT3, road cars) — not just ACC.

3. **Offline and free, and it can speak your language.** Everything runs locally,
   no subscription. A neural coach voice — currently **Italian**, the first of
   more languages — so coaching feels native, not machine-translated.

And it trains you with a **plan**: one recurring weakness at a time
(briefing → drill → measured progress → praise), instead of dumping every mistake
on you at once.

## What it does

- 🎙️ **Live voice coach** — the single most useful call at the right moment, never
  talking over itself. Lock-ups and wheelspin flagged instantly.
- 📺 **On-screen overlay** — delta bar, predicted time, the current cue and the
  focus you're working on, over the game (Borderless mode).
- 🔧 **Race engineer** — concrete setup advice, one lever at a time, with a
  convergence loop and tyre/pressure/electronics management.
- 🧠 **Focus / Lesson** — one weakness at a time, trained with measured praise
  ("Turn 4: from 0.30s to 0.07s").
- 📊 **Analysis web app** — traces, sectors, track map, the "why" debrief, trend
  over time, multi-level benchmarking (your best → theoretical ideal → PRO) and
  **systematic** vs **sporadic** weaknesses.
- 🗣️ **Post-session debrief** — your worst corners, the cause of each, your
  consistency.

## Quick start

**With the executable (recommended):** download `HONE.exe` from the
[Releases](https://github.com/ardiz89/ACCoach/releases) page, run it, pick a mode.
No Python needed. (See the [FAQ](docs/FAQ.md) for the first-run SmartScreen notice
and how to verify the file hash.)

**From source:**

```powershell
pip install -r requirements.txt   # first time (PySide6 for overlay/GUI)
python -m accoach live            # coach + overlay in one window
python -m accoach live --demo     # try it on a synthetic lap, no game
python -m accoach                 # list every command
```

Set the game to **Borderless** so the overlay draws over it. `--silent` turns off
the voice.

## Requirements

- **Windows** (the AC/ACC shared memory is Windows-only).
- **Assetto Corsa** or **Assetto Corsa Competizione**, in **Borderless** for the
  overlay.
- From source only: **Python 3.11+**.

## Privacy

HONE is **100% offline**. Telemetry, recorded laps, analysis and voice all stay on
your PC. No account, no network calls, nothing sent to third parties. Laps live in
`Documents\ACCoach\`. Details in the [FAQ](docs/FAQ.md#privacy).

## Free vs Pro

HONE follows a **one-time freemium** model — no subscription. Everything is free
today while the product matures with the community.

| | Free | Pro (coming) |
|---|---|---|
| Voice coach + overlay | ✅ | ✅ |
| "Why" debrief + analysis web app | ✅ | ✅ |
| Race engineer (setup AI) | | ✅ |
| Focus / Lesson (training plan) | | ✅ |
| Importable PRO references | | ✅ |

> Pro will be a one-time purchase, not a subscription. The model may change before
> launch — community feedback counts.

## License

**Source-available** under [PolyForm Noncommercial 1.0.0](LICENSE): free for
personal, non-commercial use; commercial use (reselling, paid products/services)
needs a license from the author. The code is visible for transparency and study.

## For developers

Technical docs in the repo (the package is still named `accoach`, the repo
codename):

- [`GUIDA.md`](GUIDA.md) — full usage guide (Italian).
- [`ENGINEER.md`](ENGINEER.md) — race-engineer architecture.
- [`TESTING.md`](TESTING.md) — how the tests run (`python -m pytest -q`).
- [`REVIEW-2026-06-29.md`](REVIEW-2026-06-29.md) — latest engineering review.

Layout: code in `src/accoach/` (telemetry → recording → comparison → coaching →
engine → server/overlay/web). `python -m accoach` is the single entry point;
`build_exe.bat` produces the executable.
