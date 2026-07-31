# HONE — Frequently Asked Questions

Quick links: [Requirements](#requirements) · [Install](#install) ·
[SmartScreen & SHA-256](#smartscreen--security) · [Privacy](#privacy) ·
[Overlay](#overlay) · [Recording](#how-lap-recording-works-and-starting-from-the-pits) ·
[Free vs Pro](#free-vs-pro) · [Troubleshooting](#troubleshooting)

---

## Requirements

- **Windows.** AC and ACC expose telemetry via shared memory, which is
  Windows-only.
- **Assetto Corsa** or **Assetto Corsa Competizione**.
- For the overlay: the game in **Borderless** (windowed-fullscreen) mode.
- From source only: Python 3.11+ and `pip install -r requirements.txt`. With the
  executable you need nothing.

## Install

### Executable (recommended)

1. Download `HONE.exe` (or the zip) from the
   [Releases](https://github.com/ardiz89/ACCoach/releases) page.
2. Run it. On first run Windows may show a SmartScreen notice (see below).
3. Pick a mode from the launcher, or from a terminal: `HONE.exe live`,
   `HONE.exe web`, etc.

### From source

```powershell
git clone https://github.com/ardiz89/ACCoach.git
cd ACCoach
pip install -r requirements.txt
python -m accoach live        # coach + overlay
python -m accoach             # list every command
```

## SmartScreen & security

On first run Windows may say *"Windows protected your PC"* (Microsoft Defender
SmartScreen). **This is normal and does not mean the file is infected.**

It happens because the executable isn't signed with a paid code-signing
certificate (hundreds of euros a year): without accumulated "reputation",
SmartScreen warns about any new app from an independent author.

To run it: click **"More info"** → **"Run anyway"**.

### Verify the file (SHA-256)

Every release publishes the SHA-256 of the executable. Compare it with the file
you downloaded: if they match, the file is exactly what was published.

In PowerShell:

```powershell
Get-FileHash .\HONE.exe -Algorithm SHA256
```

Compare the string with the one in the release notes. If they differ, **do not
run the file** and re-download from the official Releases page.

## Privacy

HONE is **100% offline**. Concretely:

- No account, no login.
- No outbound network calls: telemetry, laps and analysis never leave your PC.
- Data is stored locally under `Documents\ACCoach\` (laps in `laps\`, logs in
  `logs\`, settings in `config.toml`).
- The local servers (`web` on `127.0.0.1:8778`, backend on `127.0.0.1:8777`)
  listen only on `localhost` — your machine — to let HONE's parts talk to each
  other, not to the internet.

You can wipe everything at any time by emptying the `Documents\ACCoach\` folder.

## Overlay

The overlay is transparent, always-on-top and *click-through* (it never steals
clicks from the game).

- **Not showing over the game?** Set the game to **Borderless**. A transparent
  overlay can't draw over *exclusive fullscreen* — same constraint as SimHub and
  Crew Chief.
- **Move or close it:** start it with `--interactive`, or close the terminal that
  launched it (`Ctrl+C`).

## What the analysis app shows

Open it from the hub (**Analysis → 📊 Analysis & Report**) or with
`python -m accoach web`. It runs on your machine, on your laps; there is no
account and nothing is uploaded.

Under the tabs you always see **which lap you are looking at** — its time, the
reference, the gap and the track temperature — and every chart's x-axis is in
**metres**, measured from the recorded coordinates rather than assumed from a
track length. A lap whose coordinates don't add up falls back to per cent instead
of showing you a wrong scale.

- **Lap explained** — the lap one thing at a time: what cost you most, why, and
  what to do, with the chart cropped to the stretch it is talking about and the
  track map beside it showing where that is. Three steps at most. If you are a
  long way off the pace it opens with the general theme and stops there, because
  corner-by-corner is the wrong lens at that distance.
- **Session** — one outing: the laps in the order you drove them (including the
  ones that don't count — you still drove them), your best, consistency, track
  temperature, **fuel per lap** (measured from the tank, on laps recorded from
  v11 onwards), and **what changed since last time** on that car and track.
- **Compare** — two laps, aligned on track position: time delta, speed,
  throttle/brake, steering, with a shared crosshair. Exports to CSV/JSON.
- **Map** — your line coloured by where you gained and lost, your braking points
  against the reference's, and **Your braking points**: the cheat sheet, built
  from *your* recent laps in one track-temperature band, with the spread that
  says whether you have a braking point at all. Prints and exports.
- **Line** — where you actually drove, corner by corner: your line against the
  reference with the gap between them shaded, how far inside or outside you were
  at entry, apex and exit, the arc you drove, and the extra metres you covered.
  Where a corner's speed minimum is flat it says "same place" instead of
  inventing an apex shift, and where the car went off it says so instead of
  reading the geometry as a choice. Under both lines it draws **the track seen
  from above** — the asphalt, its kerbs, and the grass, gravel and concrete
  beside it. That is not a drawing of ours: it is the geometry the game itself
  uses to decide where you are, read from its surface model with the surface
  types already separated. The circuit is recognised **by the shape you drove,
  not by its name** — the two sims don't even agree on those. Without the game
  installed there are still the **26 circuits HONE ships with** (centre line and
  widths, from OpenStreetMap and satellite imagery): less detail, no kerbs, but
  independent of what you have on disk. It appears only when the fit says this
  really is that circuit, and never while the gap is magnified — a magnified line
  isn't where the car was.
- **Sectors** — your sectors against the reference (the sim's real sectors when
  it publishes them), the **ideal lap** stitched from your best sectors, and
  every lap sector by sector so you can see which laps that ideal is made of.
- **Dynamics** — what the car was doing: G with the friction circle, slip per
  axle, rotation vs steering, revs and shifts, tyre temperatures and pressures
  along the lap, and the handling ribbon (blue understeer, red oversteer).
- **Trends** — lap times over time, consistency, recurring mistakes, and **your
  plan**: one or two goals taken from your *systematic* weak points, with a
  target in seconds, measured only on the laps you drive after you accept it.

Keyboard: **1-9** switch tabs, **[** and **]** step through laps.

## Free vs Pro

A **one-time freemium** model (no subscription). Everything is free today while
the product grows with the community.

| Feature | Free | Pro (coming) |
|---|:---:|:---:|
| Voice coach + overlay | ✅ | ✅ |
| "Why" debrief + analysis app | ✅ | ✅ |
| Race engineer (setup AI) | — | ✅ |
| Focus / Lesson (training plan) | — | ✅ |
| Importable PRO references | — | ✅ |

Pro will be a one-time purchase. The model may change before launch.

## How lap recording works (and starting from the pits)

You don't have to do anything special: start the session (Practice, Hotlap, Race)
and drive.

- A lap is closed when you **cross the start/finish line**. HONE watches **two
  signals at once**: the game's lap counter and the wrap of your track position.
  Neither is enough alone — ACC **doesn't count the out-lap**, so on the counter
  alone the first flying lap after every pit exit was lost. The saved time is the
  game's own official lap time.
- The **first lap is almost always partial** (you start mid-track), so it's
  discarded automatically. Only **complete, line-to-line laps** are saved.
- **Starting from the pits:** recording is paused in the garage *and in the pit
  lane*; your **out-lap** is partial and discarded; your **first flying lap** is
  the first one saved. Your **in-lap** isn't saved either, and changing car/track
  resets everything — a lap never spans two sessions.
- Two independent qualities: a lap is **complete** (started at the line — required
  to be saved) and **clean** (no track-limits excursion). A dirty lap is still
  saved but **never used as the reference**.
- **How "clean" is decided depends on the game**, because the two titles expose
  different things: **AC** counts wheels off track (3 or more = dirty), **ACC**
  reads the game's own track-limits verdict. On ACC that includes cutting a
  chicane without ever touching the grass. If the game tells us nothing the lap
  stays *unknown*, which is not the same as clean.
- The report also names **which corner** you lost the lap at (e.g. "off track at
  Variante Ascari"). Laps recorded before schema v8 don't carry this: they say
  the lap was dirty, not where.

## Which lap becomes the reference

The reference is the fastest lap you've driven on that car and track — with two
rules on top:

- **Dirty laps are never eligible.** A cut lap is faster for a reason.
- **Track temperature is taken into account.** Braking points move 10-20 m
  between a cold track and a hot one, so a lap driven in comparable conditions
  wins over a slightly faster one driven in very different ones. It's a
  preference, not a filter: if nothing matches today's conditions you still get
  your best lap rather than "no reference". The lap dropdown shows the track
  temperature of each lap next to its time.

## Troubleshooting

**"Waiting for the game…" and it won't connect.**
Start AC/ACC and enter a session (practice/hotlap/race). HONE connects as soon as
the game starts publishing telemetry.

**I have no reference lap.**
Drive at least one valid lap: it becomes the reference. Or import a faster one —
**Analysis → Import a PRO reference lap** in the hub. (There's a command-line
equivalent, `python -m accoach import-reference <file.lap.json.gz>`, but the
button is the same thing with a file picker.)

**The voice isn't speaking.**
Run with the voice on (default) rather than `--silent`. Fixed phrases use a
pre-rendered neural voice; numeric phrases fall back to the system voice.

**Where are the logs if something breaks?**
`python -m accoach logs` opens the folder with logs and crash reports.

---

More questions? Open an [issue on GitHub](https://github.com/ardiz89/ACCoach/issues).
