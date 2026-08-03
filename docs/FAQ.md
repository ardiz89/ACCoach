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
- **Watching your own trail braking:** turn on **Settings → Show the pedal
  trace**. It adds a strip under the HUD with your throttle (green) and brake
  (red) over the last few seconds. The ribbon below them goes **amber** while
  both pedals are down — that's trail braking — **grey** while neither is, which
  is time you're giving away, and stays blank on a clean release. The coach
  *tells* you about your brake release after the fact; this is the only place
  you can watch it as you do it. Off by default because it makes the overlay
  taller.

## Being called into the pits

When the race engineer proposes a change that needs the garage, it doesn't just
tell you *what* to change — it tells you *when to come in*. You'll hear it at the
start of the final sector (or about 20 s before the pit entry, whichever comes
first), again just before the entry, and once more standing in the box, telling
you what to do with the change.

**No game publishes where the pit lane begins**, so HONE learns it: it watches
where you leave the track the first time you actually drive in, and keeps the
median across visits. On a track you've never pitted at, the second call simply
doesn't exist — a guessed pit entry spoken with confidence is worse than
silence, because you'd lift for it. Returning to the garage from the game menu
teaches it nothing, deliberately: the car vanishes from mid-track and reappears
in the box, and taking that jump at face value would put the pit entry in the
middle of a straight.

Changes you can make **at the wheel** (TC, ABS, brake bias) need no confirmation
at all: HONE reads those channels live and sees the dial move by itself. On AC
those levels aren't published, so the Engineer page offers a "Done" button
instead.

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
- **Training** — the tab that answers the question the others leave open: *so
  what do I actually do about it?* It starts from your best lap against your
  **theoretical ideal** — your best sectors stitched together, which is not an
  invented time: you have driven all of it, just never on the same lap — and
  says which sector holds most of that gap. Then the programme: three steps at
  most, **one at a time**, and only the first one is open. Each step carries a
  real **drill** — how many laps to run it for, what to do lap by lap, what to
  watch and what to deliberately ignore, and the number that says when it's
  done. The drill isn't generic: it is chosen from where *inside the corner* the
  time goes — braking zone, apex, or exit — and it is filled with **your** own
  numbers: the speed you brake at there, how much your braking point moves from
  lap to lap, the minimum speed you carry against the reference's. At the bottom
  is **your next session**, counted in laps: warm-up, the drill laps, and a few
  free laps to see whether it stuck once you stop thinking about it.

  **Your plan** lives here too (it used to sit under Trends): one or two goals
  taken from your *systematic* weak points, with a target in seconds, measured
  only on the laps you drive after you accept it. Corners the live coach has
  already cleared never enter it — there is one memory of "you've got this
  corner", not two.

  The tab **only opens once it has something to say**: **6 valid laps** on that
  car and track, and at least one weakness that repeats. Below that you get how
  many laps are missing, not an empty page. Six laps leave five to compare
  against your best one, and a weakness has to come back on three of those five
  to be called one; below that, what looks like a weakness is just what two laps
  did, and a programme built on it would change every time you drive.

  One thing worth reading twice: the two time figures on that tab **do not add
  up together**. The gap to your theoretical ideal and what you bleed on an
  average lap in the corners are the same road measured two ways, and summing
  them would count the same time twice.

  At the bottom sits **«The words you'll hear other people use»** — a short
  glossary, closed, showing the terms in a row: you scan it and open it for the
  one word you don't have. It is never the only place a word is explained (the
  exercise above still glosses its own), and it only carries the terms of the
  exercise you have open.

  The exercises are **not the same for every car** where the difference matters:
  on a low-downforce road car HONE won't have you practise trail braking, because
  on those cars slowing in a straight line and then turning is the correct
  technique — the same decision, on the same data, that makes the live coach stay
  silent about it there. You get **«Brake in a straight line, then turn»** instead.
- **Session** — one outing: the laps in the order you drove them (including the
  ones that don't count — you still drove them), your best, consistency, track
  temperature, **fuel per lap** (measured from the tank, on laps recorded from
  v11 onwards), and **what changed since last time** on that car and track.
- **Race pace** — how the pace holds up over **one tank**. A different cut from
  Session, and a measured one: a sitting is inferred from timestamps and can
  contain a **refuel**, so a pace averaged across it averages two fuel loads. A
  stint is cut where the tank goes back *up*. You get the pace (the median of
  the laps that were actually running one — a spin stays on the list but can't
  move the median), the spread, litres per lap, laps left in the tank, the pace
  lap by lap, and the tyres across the stint.
  And then what those numbers **don't** say, which matters more than the numbers.
  The pace trend is a **net** figure — a stint speeds up as the tank empties and
  slows down as the tyres give up — and telling the two apart needs a
  seconds-per-litre figure we do not have yet (it has to be measured on a stint
  driven at a deliberately constant pace). So the slope comes with its own error
  bar, and when it is smaller than that bar the tab says **"no measurable
  drift"** rather than inventing a degradation figure for you. It is not tyre
  wear either: neither sim publishes a wear number we record, so what you see is
  temperature.
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
- **Trends** — lap times over time, consistency, your weak points corner by
  corner (systematic or one-off) and recurring mistakes. It is the working; the
  plan that comes out of it lives under **Training**, and the tyre charts under
  **Race pace** — here the series covered your whole archive while calling
  itself a stint.

Keyboard: **1-9** and **0** switch tabs, **[** and **]** step through laps.

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
- **A lap nobody judged doesn't beat a lap that was judged.** On ACC, the
  "clean" flag on laps recorded **before 21 July 2026** came from a field that
  game declares and never fills: it says clean because nothing looked, not
  because it was. Those laps aren't discarded — they still become your reference
  if you have nothing else, since a doubtful target beats no target — but they
  lose to any lap that was really checked. It came from a real case: at Monza
  the reference was a 1:53.712 that **cut the Variante della Roggia** for half
  the corner, and was the fastest lap precisely because of that. When it
  happens the summary says so: "chosen as the judged lap — your 1:53.712 is
  faster but nothing ever checked it for track limits".
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
