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
- **The thin amber line** is your focus: theme, corner and the tenths it costs.
  Once the coach has moved to trigger words (see *One theme at a time*) it also
  carries **an example word**, like "LESS BRAKE" — the whole sentence stays in
  the pill above it and in the debrief; the line names the theme, not every
  word you'll hear.
- **Watching your own trail braking:** turn on **Settings → Show the pedal
  trace**. It adds a strip under the HUD with your throttle (green) and brake
  (red) over the last few seconds. The ribbon below them goes **amber** while
  both pedals are down — that's trail braking — **grey** while neither is, which
  is time you're giving away, and stays blank on a clean release. The coach
  *tells* you about your brake release after the fact; this is the only place
  you can watch it as you do it. Off by default because it makes the overlay
  taller.

## One theme at a time (and why the coach says less after a few laps)

Once you've put in a few clean laps, HONE stops commenting on everything and
**elects one weakness**: the corner where you lose the most, and why. It tells
you ("New focus — Variante Ascari: let's work on braking…"), and **from then on
it only talks about that theme on track**. Everywhere on the lap, not just in
that corner: if your braking is off, it isn't off in one place only, and the
*mistake* is what gets trained.

And it says it in **one word**, not a sentence: "less brake", "later",
"throttle". The words are agreed with you **up front**, in the message that
announces the focus — *"On track I'll only say words about braking, like 'less
brake'"* — and the focus line on the overlay keeps the word in front of you while
you drive.

This isn't a whim: three independent professional coaches impose the same limit
— **two or three themes per session**, and on track **trigger words of one to
three words**, agreed beforehand. The reason they give is always the same, and
it's yours: a driver in motion has finite bandwidth, and by the tenth sentence in
three laps you've stopped listening.

**Nothing is lost.** Whatever the coach keeps quiet about on track is in the
**debrief** and in the report, with its tenths: the debrief is computed from the
lap, not from what was said, so the corners the voice skipped are all still
there. The voice picks what to tell you *now*; the debrief picks nothing.

**Outside the filter is anything that isn't driving technique on the active
theme**: lock-ups, wheelspin, understeer and oversteer, fuel, the pit calls,
the finish-line setup advisories, praise — always spoken.

Until there's a focus — the first laps, while it's still watching you drive — the
coach talks about everything, as it always did. And when the corner improves, or
won't budge after a few laps, it parks it and moves on: new theme, new words.

## Why it went quiet after a cut

On a lap the game has **invalidated** (ACC only — AC has no such flag), HONE
keeps coaching but stops **praising**. A corner where you gained time on an
invalidated lap earns no "Nice stretch" and no green on the corner card: you
gained that time by leaving the track, and congratulating you for it would be
teaching you the shortcut. Everything you *lost* is still called out, and the
debrief still shows the whole lap — an invalidated lap is a free lap to learn
from, and usually the one with the most in it.

## Being called into the pits

When the race engineer proposes a change that needs the garage, it doesn't just
tell you *what* to change — it tells you *when to come in*. You'll hear it at the
start of the final sector (or about 20 s before the pit entry, whichever comes
first), again just before the entry, and once more standing in the box, telling
you what to do with the change.

There is a fourth thing, and you don't hear it — you see it. The overlay has a
**pill** that normally shows the last piece of advice spoken, and fades on its
own. From the call onwards, that pill is no longer the last piece of advice: it
is the **pit-in warning**, in amber, and it **does not fade**. It stays lit
until you enter the pit lane, or until the change is no longer pending (if it
gets dropped): a call that disappears after two seconds is a call you miss if
you happened to be looking at the corner ahead. The advice is still **spoken**
— it only gives up that line, and takes it back as soon as the warning goes
out.

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

Open the report and you land on the **Report card** for your latest outing. It
is one page, built to be read in ten seconds. At the top you get track, car,
date and how many laps you drove (valid out of total). The dropdown opens an
older outing.

Under that is the verdict, one or two sentences: how much you leave on the
table each lap against your reference lap, and where it piles up. It compares
that with the previous session on the same car and track. If there isn't one,
it says so.

Then, in order:

- **Your main faults.** These are driving habits that repeat across several
  corners, like braking too early or getting back on the throttle late. For
  each one you see what it costs you per lap, in how many corners and on how
  many laps it shows up, and an arrow (down, same, up) against the previous
  session, with your last sessions beside it. Progress shows up here, as a
  fault going down from one session to the next. A click opens it corner by
  corner.
- **Where you lose most.** The corners that cost you the most, by name.
- **Most frequent mistakes.** Lockups, wheelspin, understeer, oversteer and
  off-tracks, counted over the session. Only the ones that happened show up. On
  ACC with ABS on, physical lockup doesn't happen, so we don't count it.
- **The plan for your next run.** Three pieces of advice at most, in order.

Every number comes from your laps. When a figure isn't there, the line says so
or doesn't appear. We don't make one up. Every session is measured against the
same reference, today's, so when a fault goes down it is you that changed and
not the yardstick. When the reference changes, the history is recalculated.

The report card is about driving. Setup problems stay with the Engineer.

**You follow the plan one piece of advice at a time.** Each piece of advice is
about one fault and the corners where it weighs most. The three choices are for
the piece at the top; the others only show **How to do it →**.

- **I'll follow it** puts it in progress, dated today.
- **Not for me** takes a piece you haven't started out of the plan. The fault
  stays on the report card, and the advice stays out of the plan until you
  take it back. You find it again under "You set aside", with **Take it back**.
- **Drop it** closes the one in progress without counting it as done.

The piece in progress is measured only on the laps you drive after you take it.
It counts as done when, over at least three laps, you are under the target on
half of them. The target is to win back half of what you lose today. When that
happens the report card tells you and offers the next one.

**In the car, the coach follows your advice.** On your next outing the focus
(see "One theme at a time") works on the corners of the advice you are
following, and speaks there, so the plan and the coach tell you the same thing.
If you no longer lose enough in those corners, the coach picks as it always
does. A verdict from the coach doesn't close the advice. Only the report's
measurement does.

**How to do it →** on a piece of advice opens its page, and **← Back to the
report card** brings you back. It is built from your own laps:

- The problem in one sentence, with your numbers: where you brake, how many
  metres before your best lap, what it costs you.
- The figures, one per corner, the most expensive first. Each has a map of the
  corner with the points of your usual lap and your best, and the brake,
  throttle or speed trace laid over each other. If one of the two laps has no
  coordinates or no channel, the page says what is missing where the figure
  would be.
- How to do it: a few lines on what to do, what to watch for on track and what
  to ignore. Where the drill depends on the car, it changes. On a low-downforce
  road car it won't have you practise trail braking, because there the right
  technique is to brake in a straight line and then turn (the same choice that
  keeps the live coach silent about it on those cars).
- The drill: how many laps, the target in numbers, when it is done.
- How it's going: that fault's number in each session since you started
  following it. It fills in from the first session after you press **I'll
  follow it**.
- Glossary: the words that page uses (braking point, apex, reference lap...),
  each in one sentence.

The tabs come in three groups, in the order you usually read them.

**How today went**

- **Report card** — the page above. It opens by itself after a new session;
  otherwise the report reopens the last tab you were on.
- **Session** — one outing: the laps in the order you drove them (including the
  ones that don't count — you still drove them), your best, consistency, track
  temperature, **fuel per lap** (measured from the tank, on laps recorded from
  v11 onwards), and **what changed since last time** on that car and track.
- **Lap explained** — the lap one thing at a time: what cost you most, why, and
  what to do, with the chart cropped to the stretch it is talking about and the
  track map beside it showing where that is. Three steps at most. If you are a
  long way off the pace it opens with the general theme and stops there, because
  corner-by-corner is the wrong lens at that distance.

**Why, in detail**

- **Compare** — two laps, aligned on track position: time delta, speed,
  throttle/brake, steering, with a shared crosshair. Exports to CSV/JSON.
  Beside the charts, on the same screen, **the track map**: your line coloured
  by where you gained and lost, and your braking points against the reference's.
  It stays put while you scroll the charts, so the spike in the delta and the
  corner it happened in are one glance apart instead of one tab apart — they
  used to be two separate tabs answering the same question. The crosshair
  crosses both: hover a chart and the map lights up the same point. Under the
  map, **Your braking points**: the cheat sheet, built from *your* recent laps
  in one track-temperature band, with the spread that says whether you have a
  braking point at all. Prints and exports.
- **Line** — where you actually drove, corner by corner: your line against the
  reference with the gap between them shaded, how far inside or outside you were
  at entry, apex and exit, the arc you drove, and the extra metres you covered.
  Where a corner's speed minimum is flat it says "same place" instead of
  inventing an apex shift, and where the car went off it says so instead of
  reading the geometry as a choice. Beside the corner's title there is a pencil:
  **you can name the corner yourself**, and that name then appears everywhere —
  the debrief, the losses, the braking sheet, the coach's voice. HONE knows the
  corner names of 14 of the 26 circuits it ships, and ten more ACC circuits have
  no bundled geometry at all; on those you are the only source there is. Your
  name outranks ours, and comes off the same way it went on. They live in
  `Documents\ACCoach\corner-names.json` in plain text — along with the
  **braking references** you type into the braking sheet ("at the end of the
  green on the left"), which is the other half of the same idea: the positions
  were measured long ago, the words could not be sourced, and you are the one
  looking at the corner. Under both lines it draws **the track seen
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

**Over time**

- **Trends** — at the top, your **faults session by session**, up to twenty
  sessions, measured against the same reference as the Report card. That is
  where you see a fault going down; a click on its name opens its **How to do
  it**. Below, lap times over time, consistency, your weak points corner by
  corner (systematic or one-off) and recurring mistakes. It is the working; the
  plan that comes out of it lives on the **Report card**, and the tyre charts under
  **Race pace** — here the series covered your whole archive while calling
  itself a stint.
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

Under the other tabs you always see **which lap you are looking at** — its time, the
reference, the gap and the track temperature — and every chart's x-axis is in
**metres**, measured from the recorded coordinates rather than assumed from a
track length. A lap whose coordinates don't add up falls back to per cent instead
of showing you a wrong scale.

Keyboard: **every tab has a key that opens it**, in the order they sit left to
right — hover a tab to see which one it is (the lap picker says so too). **[**
and **]** step through laps.

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

## How a Coach Live session goes (the Drive panel)

After you press **Coach Live**, the **Drive** page shows three moments, one after
the other.

**Before you go.** *Coach Live is on* is already ticked: voice and overlay are
ready. Next comes *Connect your tablet to the engineer*: scan the QR code with the
tablet's camera, or open the address next to it. The tablet only connects with
network access on; if it's off, the panel has a *Turn on network access* button.
If you don't need the tablet, press *Skip, I'll drive without*. The last step,
*Start the game and leave the pits*, ticks itself when the telemetry arrives.

**You're driving.** The panel shows whether the tablet is connected, the track
and car, the laps completed with your best, and, under *You're working on*, the
advice you're following: the coach reminds you of it in its corners. When you're
done, press **I'm done, show me how it went**. It stops the coach and opens the
report on the report card. *Stop without opening the report* only stops the coach.
Coach Live never stops by itself.

**Session over.** If you close the game, the panel switches to *Session over*
after a minute and offers two choices: *Show me how it went* and *I'm staying on
track*, for when you're only changing track. The coach stays on until you stop it.

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

**The trigger words sound worse than the sentences.**
They do, and we know. Fixed phrases come from a pre-rendered **neural** voice;
the focus trigger words haven't been recorded yet, so for now they come out of
the **system** voice, which is more robotic. Work in progress — it changes how
it sounds, not what you're told.

**Where are the logs if something breaks?**
`logs` opens the folder with logs and crash reports. To send them to us, `logs
--zip` packages them into a single file in `Documents\ACCoach\`. It writes the
zip even when there are no logs at all, and says so inside: "no logs" and "I
didn't collect them" are different answers.

**What is in that zip, exactly?**
Two things, and they are not the same.

`contesto.txt`, which we write: the version, the commit, your Python/Windows
versions and the last cars and tracks you drove — no paths, no machine name, no
account name, because none of that would help us.

Your log files, which go in **exactly as they are, not filtered**. At least all
of this is in them:

- paths that include your Windows account name (`C:\Users\<account>\...`), and
  any network location you set as your laps folder;
- one dated line every time you started HONE — together, a record of when you
  sat down to drive, going back as far as your oldest log;
- your lap times, the tracks and cars you drove, and the names of files you
  opened;
- crash reports (`crash-*.log`), each with a full traceback, the paths of our
  source files, and whatever value the error carried with it.

We leave all of it in on purpose — a log with the interesting parts taken out
cannot diagnose anything, and quietly censoring one would be worse than the
path. The zip is an ordinary file on your disk, and the command prints a short
version of this when it finishes: open it and look before you send it.

(Type the command the way `help` shows it: `HONE.exe logs --zip` from the
packaged app, `python accoach_main.py logs --zip` from a source checkout.)

---

More questions? Open an [issue on GitHub](https://github.com/ardiz89/ACCoach/issues).
