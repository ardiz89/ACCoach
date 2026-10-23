# HONE user guide

HONE is a real-time driving coach for **Assetto Corsa** and **Assetto Corsa
Competizione**. While you drive it talks to you and shows an overlay with the gap
to your best lap. After the session you get the debrief and the full analysis in
the browser. There is nothing to set up in the game, because HONE reads the
telemetry from the shared memory of AC and ACC.

This guide takes you from the first start to your first lap with the coach, and
on to the analysis. If you're looking for one thing, jump to
[Install](#install), [SmartScreen](#smartscreen--security),
[Privacy](#privacy), [the overlay](#4-reading-the-overlay),
[lap recording](#how-lap-recording-works-and-starting-from-the-pits) or
[what to do when something goes wrong](#9-if-something-goes-wrong).

---

## 1. What you need

- **Windows.** AC and ACC publish their telemetry through shared memory, and
  that only exists on Windows.
- **Assetto Corsa** or **Assetto Corsa Competizione**, installed.
- **HONE**, in one of the two ways below.

Your laps end up in **`Documents\ACCoach\laps`**, whichever way you run HONE.
That way the analysis always finds them.

### Install

**The executable**, if you only want to use it. Download the zip from the
[Releases](https://github.com/ardiz89/ACCoach/releases) page, unzip it and run
`HONE.exe`. You don't need Python.

**The source**, if you develop. You need Python 3.11 or newer.

```powershell
git clone https://github.com/ardiz89/ACCoach.git
cd ACCoach
pip install -r requirements.txt
python accoach_main.py live      # coach and overlay
python accoach_main.py help      # list the commands
```

From the source you can also double-click `HONE.bat`. The first time, it sets up
its own Python environment and installs what HONE needs.

### SmartScreen & security

The first time you run it, Windows may say *"Windows protected your PC"*. That's
Microsoft Defender SmartScreen. **It's normal, and it doesn't mean the file is
infected.**

The executable isn't signed with a paid code-signing certificate, which costs
hundreds of euros a year. Without a reputation built up over time, SmartScreen
warns about any new app from an independent author.

To run it, click **More info** and then **Run anyway**.

### Verify the download (SHA-256)

Every release publishes the SHA-256 of its zip. Compare it with the file you
downloaded. If they match, the file is exactly the one that was published. In
PowerShell, from the folder where you saved it, run this.

```powershell
Get-FileHash .\HONE-<version>-windows.zip -Algorithm SHA256
```

Use the name of the zip you actually downloaded. Compare the result with the
string in the release notes. If they differ, **don't run the file**, and
download it again from the official Releases page.

### Privacy

HONE works **entirely offline**.

- There's no account and no login.
- HONE makes no calls to the internet. Telemetry, laps and analysis never leave
  your PC.
- Everything is stored under `Documents\ACCoach\`. Laps are in `laps\`, logs in
  `logs\` and settings in `config.toml`.
- HONE's parts talk to each other through two local servers, the analysis on
  port 8778 and the live backend on port 8777. They only listen on this PC.
  The exception is when you turn on access from other devices on your network,
  described in "Opening the report on a phone or tablet".

You can wipe everything at any time by emptying the `Documents\ACCoach\` folder.

---

## 2. Up and running in 30 seconds

1. **Start the game** and get on track in a **Practice** session, with the car
   and track you want to train on.
2. **Put the game in Borderless mode**, a window without borders, and not in
   exclusive fullscreen. The overlay can't draw over exclusive fullscreen.
3. **Open HONE.** The **hub** opens. Its sidebar has six sections,
   **Home · Drive · Analysis · Setup · Devices · Settings**. Go to **Drive** and
   press **Coach Live**.

> After the first time, Home shows you your last session, already analysed.
> That's where you go to see how it went.

**The Drive panel walks you through it.** Once you press Coach Live, the page
moves through three stages, one after the other.

**Before you go.** The first step, *Coach Live is on*, is ticked off as soon as
the coach responds, usually within a couple of seconds. At that point voice and
overlay are ready. Next comes *Connect your tablet to the engineer*. Scan the QR
code with the tablet's camera, or open the address written next to it. It opens
the tablet view, described in "The tablet view". The
tablet can only connect with network access on. If it's off, the panel offers a
*Turn on network access* button, and afterwards you restart Coach Live. If you
don't need the tablet, press *Skip, I'll drive without*. The last step, *Start
the game and leave the pits*, ticks itself off when the telemetry arrives.

**You're driving.** The panel tells you whether the tablet is connected, which
track and car you're on, how many laps you've completed and your best. If you're
following a tip from the Report card, you read *You're working on* with its
name. The coach reminds you of it in the corners that advice covers. When you're
done, press **I'm done, show me how it went**. The coach stops and the report
opens on the Report card. *Stop without opening the report* only stops the
coach.

**Session over.** If you close the game, after a minute the panel switches to
*Session over* and offers two choices. *Show me how it went* opens the report.
*I'm staying on track* is for when you've closed the game only to switch tracks.
The coach stays on until you stop it.

**If you forget to press the button.** In **Settings** there's *Record by itself
when the game starts*. With the hub open, HONE notices that AC or ACC has started
and begins recording on its own. That way you don't lose a session you forgot to
start. **Only the silent recorder starts**, and the voice and the overlay stay
off until you press Coach Live. A coach that starts talking just because you
opened the game would be an intrusion. The option is off by default. If you stop
the recording by hand it stays stopped, and starts again only when you close and
reopen the game.

From the command line you do the same thing like this.

```
python accoach_main.py live      # voice coach and overlay, in one process
```

Add `--silent` if you want the overlay without the voice. With `--interactive`
you can drag the overlay somewhere else on the screen.

---

## 3. How the coach trains you

The coach works like a real race engineer. First it **watches you drive**, then
it **corrects you**. It tells you three kinds of things.

### Immediate warnings

These don't need a reference lap. From the first metre of the first lap, the
coach warns you when you do something that's wrong on any lap.

- If you **lock up** under braking, you hear "You're locking up, ease off the
  brake".
- If you **spin the wheels** on exit, you hear "Wheelspin on exit, ease the
  throttle".
- If the car **understeers**, you hear "The front is sliding, go in slower".
- If the car **oversteers**, you hear "Oversteer, open the throttle gently on
  exit".
- If you **coast**, with neither brake nor throttle pressed, you hear "You're
  coasting, go straight from brake to throttle".
- If you let go of the brake too early, without **trail braking**, you hear
  "Releasing too early, trail the brake to turn-in".

### Corner advice

To tell you where you lose time and why, the coach needs a **reference lap**,
your fastest valid one.

1. **Drive one clean, complete lap**, from the line to the line. The one that
   starts from the pits doesn't count. It's saved and becomes the reference.
2. Corner advice starts on the next lap. The coach compares your lap with the
   reference. **As you approach each corner** it gives you the advice for that
   corner. For example, it says "Carry more speed through the corner" or "You're
   running deep, brake earlier". It speaks before the corner, while you can
   still do something about it.
3. Once you get that corner right, it **stops repeating** that advice.
4. Every time you beat your reference, the comparison moves to the new lap.

> When you're not on a good lap, like after the pits, a spin or an off, the
> coach **stays quiet** about technique. Only the safety warnings remain.

### One theme at a time

After a few complete laps, dirty ones included, the coach stops commenting on
everything. It **picks one weakness**, the corner where you lose the most and
why. It announces it with a sentence like "The new focus is Variante Ascari.
Let's work on braking". **From then on it only talks to you about that theme on
track**, all around the lap and not only in that corner. Bad braking isn't
confined to one corner, and the habit is what you train.

This applies to the themes the coach can recognise anywhere on the track, which
are braking and traction. With a focus on cornering or on the line, the voice
doesn't narrow, because that advice only comes once the corner is over.

On braking and traction it speaks to you **with a word** instead of a sentence,
like "less brake", "later" or "throttle". It tells you the words **in advance**,
in the message that announces the focus. For example, "On track you'll only hear
braking words, like “less brake”". Then the focus line on the overlay keeps them
in front of you while you drive.

Three independent professional coaches set themselves the same limit, **two or
three themes per session**, and on track **short words** agreed beforehand. A
driver can only take in so much, and by the tenth sentence in three laps you've
stopped listening.

**You don't lose anything.** Whatever the coach keeps quiet about on track is in
the **debrief** after the session and in the report, with its tenths. The
debrief is worked out from the lap, not from what the voice said. So it also has
the corners the voice skipped. The voice chooses what to tell you now, and the
debrief chooses nothing.

**The filter only covers driving technique.** You always hear lock-ups, wheelspin,
understeer and oversteer, fuel, pit calls, setup advice at the line and praise.

Until there's a focus, in the first laps while it's still watching you, the
coach talks about everything. When the corner improves, or doesn't improve after
a few laps, the coach sets it aside and moves to the next one. The theme changes,
and so do the words.

### Setup advice

Between laps, when a symptom keeps coming back, the coach suggests an
adjustment. It can be about tyre pressures, TC and ABS levels where the car has
them, or brake bias. It only judges pressures on GT3 cars, with the tyres up to
temperature, aiming for about 26.5 psi. On other cars it doesn't mention them,
because that figure only holds for GT3.

There are two kinds of change, and they close in different ways.

- **At the wheel.** A dial you turn on the straight, like TC, ABS or brake bias.
  You don't have to confirm anything, because HONE **watches the channel** and
  notices on its own that the dial has moved. The test starts without you taking
  your hands off the wheel. On AC those levels can't be read, so the Engineer
  page gives you an **I've changed it** button.
- **In the pits.** A setup file to write. Here the coach also tells you **when to
  come in**.

### The engineer's road

The engineer works in phases, one after the other. On a GT3 they are Pressures,
Mechanical grip, Aero / rake, Brake bias and Electronics. It keeps checking the
pressures in the later phases too.

1. To decide anything it needs a baseline of **3 clean laps**. For the
   engineer a lap is clean when it's valid, with no off-track and the tyres
   averaging at least 75 °C. It collects the baseline at the start, after a
   restore and when the track changes between dry and wet. In the wet, though,
   it proposes nothing, because its remedies were worked out in the dry.
2. With the baseline it proposes **one change at a time**. The proposal tells
   you whether it's done in the pits or from the wheel.
3. Once you've made it, it counts **3 clean laps** with the change to check it.
4. If the change helped it keeps it, and those laps become the baseline for the
   next step. If not, it asks you to put it back as it was.
5. When the phase has nothing left that it knows how to fix, it moves on to the
   next one with the baseline it already has.

Where you are shows in the **road**, the row of phases above the phase line, on
the tablet and on the Engineer page. Finished phases carry a tick and the
current one is highlighted. A skipped phase is struck through, with no tick.
That happens when the engineer can't judge it on that car, or finds nothing to
correct. When the engineer stands down, in the wet for example, the sentence
below the phases only says it isn't writing any change for now. The reason is
in its message. Otherwise the sentence gives the current step, with the clean
laps counted, for example "Clean laps for the baseline, 2 of 3."

### The Test log

On the **Engineer** page, under the proposal, there's the **Test log**. It
tells you how many proposed changes were **kept** after the measurement, and how
many were rejected. It's the only number on that page that isn't a claim of ours.
The tests you drove count it, and it can prove us wrong.

It also shows **which levers earn their place**, whether "most effective first"
holds up, and the **side effects** you've seen. One example is a change that
cured understeer on entry and brought some on exit. We never predict side
effects. They get seen and written down.

While there are only a few tests, **you get counts and no percentages**. Over
three tests a hit rate is just noise.

### Being called into the pits

When a change has to be made in the garage, you hear three things.

1. **At the start of the last sector**, or about 20 s before the pit entry if
   that comes first, "Setup change ready, box this lap". The 20 s rule matters
   because on some circuits the pit lane splits off **before** the last sector.
   A call tied to the sector would come after you'd passed the entry.
2. **Just before the entry**, "Pit entry just ahead, come in".
3. **Standing in the box**, what to do with the change. It tells you out loud
   because the change is on a browser page you weren't looking at while driving.

There's a fourth thing you don't hear but **see**. From the first call, the
pit-in warning stays lit on the overlay until you enter the pit lane. You'll find
it in "Reading the overlay".

Keep in mind that **no game publishes where the pit lane begins**. HONE learns
it by watching where you leave the track when you actually come in, and keeps the
median over several visits. On a track where you've never pitted, call number 2
**doesn't exist**, because a guessed pit entry would make you lift in the wrong
place. From your second visit onwards the call is there.

Going back to the garage from the game menu teaches it nothing, on purpose. The
car vanishes mid-track and reappears in the box. Taking that jump at face value
would put the pit entry in the middle of a straight.

### How lap recording works (and starting from the pits)

You don't have to do anything special. Start the session, practice, hotlap or
race, and drive.

- A lap closes when you **cross the line**. HONE recognises it from **two
  signals together**, the game's lap counter and your track position starting
  again from zero. One alone isn't enough. On ACC the counter doesn't count the
  out-lap. Without the second signal, the first flying lap after every pit exit
  would be lost. The time we save is the game's official one.
- The **first lap is almost always partial**, because you start mid-track, and we
  discard it. We only save **complete** laps, from line to line.
- **If you start from the pits**, recording is paused in the garage and in the pit
  lane. The out-lap is partial and discarded, and the first lap saved is your
  first flying lap. The lap on which you come into the pits isn't saved either.
  If you change car or track everything resets, and a lap never spans two
  sessions.
- A lap has two independent qualities. It's **complete** if it started from the
  line, and only then is it saved. It's **clean** if you stayed within track
  limits. A dirty lap is saved, but it **never becomes the reference**.
- **How we decide a lap is clean depends on the game**, because the two titles
  tell us different things. On **AC** we count wheels off the track, and with 3
  or more the lap is dirty. On **ACC** we read the game's own track-limits
  verdict. So on ACC a cut counts even without a wheel on the grass. If the game
  tells us nothing, the lap stays "unknown", which doesn't mean clean.
- The report also tells you **which corner** you lost the lap at, for example "off
  track at Variante Ascari". Laps recorded before version 8 of the schema don't
  have this. They say the lap was dirty, but not where.

---

## 4. Reading the overlay

- **The delta bar** fills **to the right in red** when you're slower than the
  reference, and **to the left in green** when you're faster.
- **At the top** you see your **PB**, the lap you're racing against, and the
  **predicted time** if you keep the pace. When a braking zone is coming, that
  space goes to the **countdown in metres**. When it's time to brake it becomes
  a single red word, **BRAKE**. The threshold is in time, not distance. Ten
  metres is 0.14 s at 250 km/h, and half a second in a slow corner.
- **A label** shows the last advice spoken, and fades on its own. When the
  engineer proposes a change that can **only be made in the pits**, the coach
  calls you in at the end of the lap. From then on the label becomes the
  **pit-in warning**, in amber, and it doesn't fade. It stays until you enter
  the pit lane, or until the change is no longer pending, for example if it gets
  withdrawn. A call that lasts two seconds is one you miss if you were looking
  at the corner. Spoken advice keeps coming. It just loses its line on the
  overlay until the warning goes out.
- **Below it there's a thin amber line**, the **focus**. It's the theme you're
  working on, with the corner and the tenths it costs you. Once the coach has
  moved to short words, described in "One theme at a time", it also shows **an
  example word**, like "LESS BRAKE". The whole sentence stays in the label and
  in the debrief. The focus line reminds you of the theme, not of every word
  you'll hear.

### The pedal trace

You turn it on in **Settings**, with **Show the pedal trace**. It's **off** by
default, because it makes the overlay taller. Keep it on when you're working on
your brake release, and turn it off when you want a clean screen.

It's a strip under the overlay with your **throttle in green** and your **brake
in red**, over the last few seconds, as you use them. Under the two traces there's
a ribbon that colours itself.

| Ribbon | What you're doing |
|---|---|
| **amber** | You're pressing both pedals, so **you're trail braking**. |
| **grey** | You're pressing neither pedal, and that's **time you're giving away**. |
| nothing | A clean release. You let go of the brake and picked up the throttle with no gap. |

At the top right you get the same thing in one word, **TRAIL**, or **COAST** with
a timer for how long you've been coasting.

The coach **tells** you about trail braking, but after the fact. Here you **see
it while you do it**, and that's the only way to correct a release. Where the two
traces overlap, that's your trail braking.

> On road cars the spoken advice about trail braking is **off**. There, carrying
> the brake into the turn rotates the car, and without aerodynamic downforce a
> late release makes it snap. The trace stays, because watching it doesn't tell
> you what to do.

### The corner number

At the bottom, after each corner, you read **what that corner cost you** against
your reference, with a coloured dot. It stays there until you finish the next
corner.

| Colour | What it says |
|---|---|
| **cyan** | You gained **at least 0.25 s**. That's the threshold for the coach's praise. |
| **green** | You're within the normal range, between a 0.25 s gain and a 0.12 s loss. |
| **yellow** | You lose **0.12 to 0.25 s**. From 0.12 s the coach starts talking to you. |
| **red** | You lose **more than 0.25 s**. |

Three things look like faults and aren't.

- **The number is measured, the colour is tuned.** You can recount the tenths by
  hand. We chose the colour thresholds, and they're the same ones the coach uses
  to decide whether to speak. So colour and voice never tell you different things.
- **The number is relative to your reference**, the one chosen for today's
  conditions. If your best lap is slow, green doesn't mean you're fast. It means
  you're **consistent**.
- **In your first session with a car or on a new track the box isn't there**, not
  even as a dash. Without one of your complete laps there's nothing to measure
  against, and a made-up number would be worse than none. It also disappears in
  the pits, on the out-lap and on off-pace laps.

The spoken advice **doesn't change**. It always comes at the entry of the same
corner, on the next lap, where you can still do something about it. The number is
an account after the fact, and that's why it can be missing.

### When the delta isn't there

The delta only shows **on laps that can count**, the ones that started from the
line. That's not a fault. A number comparing the pit lane with a flying lap goes
over 30 s and pins the bar at full scale. It would look like a disastrous lap,
and it isn't a lap at all. In its place you always find **the reason**.

| What you read | What's going on |
|---|---|
| *In the pits. I start at the line.* | You're in the garage or the pit lane. |
| *Out lap. I'll start at the line.* | The coach starts working from the line. |
| *No reference yet. Drive one clean lap.* | You don't have a complete lap with this car on this track yet. |
| *Lap invalidated. Keep going, no delta.* | The game has cancelled this lap, which only happens on ACC. |
| *Off-pace lap. I'll pick up at the line.* | Here the delta **stays**, because the lap started from the line. |
| *Flying lap* | It lights up for a moment when the coach starts working again. |

On an **invalidated lap the coach keeps talking to you**, and only the delta goes
away. A cancelled lap is a free lap. Braking, lock-ups, tyres and setup can all
be read the same, and going back to the pits would be time thrown away.

There's one exception, **praise**. On a lap the game no longer counts, in a corner
where you gained, you don't hear "You're gaining here, same again next lap". And
the corner box doesn't show that gain. You gained that time by leaving the track,
and praise would teach you the shortcut. The advice on corners where you **lost**
time all stays. On a lap you've thrown away, that's usually where there's most to
learn.

Without a reference, on the other hand, everything that doesn't need one stays
on. Understeer and oversteer, coasting, trail braking, gears, pressures and
temperatures are always there. It's worth knowing in your first session with a
new car.

---

## 5. Analysis and report in the browser

Once the session is over, go through it at your own pace.

- In the hub, in the **Analysis** section, press **Analysis and report**. From the
  command line, type this instead.
  ```
  python accoach_main.py web
  ```
  The page `http://127.0.0.1:8778` opens by itself.

On a laptop, up to 1600 px wide, the page stays as it is. On a wider screen the
text of the report and of the Engineer page grows by itself, up to 20 px instead
of 14.

### The Report card

Open the report and you land on the **Report card** for your latest outing. It's
a single page, built to be read in ten seconds. At the top you see track, car,
date and how many laps you drove, with the valid ones in brackets. The dropdown
picks an older outing.

Under it is the verdict, in one or two sentences. It tells you how much you leave
on average each lap against your reference lap, and where it piles up. It
compares that with the previous session, same car on the same track. If there's
no previous session, it says so.

Then come four blocks, in this order.

- **Your main faults.** Driving habits that repeat across several corners, like
  braking too early or getting back on the throttle late. For each one you see
  what it costs you per lap, in how many corners and on how many laps it shows up.
  Beside it, an arrow tells you whether it went down, stayed the same or went up
  since the previous session. Next to that you see your last sessions. That's
  where you read your progress, as a fault going down from one session to the
  next. A click opens it corner by corner.
- **Where you lose most.** The corners that cost you the most, by name.
- **Most frequent mistakes.** Lock-ups, wheelspin, understeer, oversteer and
  off-tracks, counted over the session. Only the ones that happened show up. On
  ACC with ABS on, a physical lock-up doesn't happen, so we don't count it.
- **The plan for your next run.** Three tips at most, in order.

Every number comes from your laps. If a figure is missing, the line says so or
doesn't appear, and we don't make one up. Every session is measured against the
same reference, today's. So if a fault goes down, it's you that changed and not
the yardstick. When the reference changes, the history is recalculated.

The Report card is about driving. Setup problems stay with the Engineer.

**You follow the plan one tip at a time.** Each tip targets one fault and the
corners where it costs most. **I'll follow it** and **Not for me** show on the
first suggested tip until you pick one. **Drop it** shows on the tip you're
working on. Every tip has **How to do it →**.

- **I'll follow it** puts it in progress, dated today.
- **Not for me** takes a tip you haven't started out of the plan. The fault
  stays on the Report card, and the tip stays out of the plan until you take it
  back. You find it again under "You set these aside.", with the **Take it
  back** button.
- **Drop it** closes the tip you're working on without counting it as done.

The tip you're working on is measured only on the laps you drive after you take
it. It's done when, over at least three laps, you're under the target on half of
them. The target is to win back half of what you lose today. When that happens,
the Report card tells you and offers the next tip.

**On track, the coach works on the same advice.** On your next outing the focus,
described in "One theme at a time", works on the corners of the tip you're
following and speaks there. So the plan and the coach tell you the same thing.
If you no longer lose enough in those corners, the coach picks on its own as
always. A verdict from the coach doesn't close the tip. Only the report's
measurement does.

**In the other tabs, the tip you follow is marked.** Compare, Line, Sectors,
Dynamics and Trends open with a line that has a purple border. The line names
the corners of the tip and tells you what to look at in that tab. A click on a
corner's name takes you there, and **How to do it →** opens the tip's page. In
the charts and lists, the corners of the tip carry a purple dot. With no tip in
progress the tabs stay as they are.

### How to do it

**How to do it →** on a tip opens its page, and **← Back to the
Report card** takes you back. The page is built from your own laps, and it has
these parts.

- At the top, the problem in one sentence with your numbers. It tells you where
  you start braking, how many metres before your best lap, and what it costs you.
- **From your laps**, the figures, one per corner, the most expensive first. Each
  has a map of the corner with the points of your usual lap and your best. The
  brake, throttle or speed traces are laid over each other. If a lap has no
  coordinates or is missing a channel, you read what's missing instead of the
  figure.
- **The technique**, a few lines on what to do, what to watch on track and what
  to ignore. Where the technique changes from one car to another, it changes
  here too. On a low-downforce road car it won't have you practise trail
  braking. There the right technique is to brake in a straight line and then
  turn. For the same reason the coach on track doesn't mention it on those cars.
- **The drill**, with how many laps to drive, the target in numbers and when it's
  done.
- **How it's going**, the number for that fault in each session since you started
  following it. It fills in from the first session after you press **I'll follow
  it**.
- **Glossary**, the words the page uses, like braking point, apex or reference
  lap, with one sentence each.

### The report tabs

The tabs come in three groups, in the order you usually read them.

**How today went**

- **Report card** is the page described above. It opens by itself after a new
  session. Otherwise the report reopens the last tab you were looking at.
- **Session** tells the story of one outing. You get the laps in the order you
  drove them. The cut or invalid ones are there too, but they don't count towards
  averages. Then your best, your consistency, the track temperature, and **what
  changed since last time** with the same car on the same track, corner by
  corner. A click on a lap opens it in Compare. We work out sessions from the
  timestamps, and a long break counts as a new session.
  You also get **fuel per lap**, measured from the tank and not estimated, next to
  each lap and as the session average. On laps recorded before HONE read the tank
  it doesn't appear, because we don't know it, and that doesn't mean zero litres.
  It doesn't appear on laps where you refuelled either, because there's a refuel
  in the middle and not a consumption.
- **Lap explained** shows you the lap one thing at a time, instead of five
  charts at once. It tells you what cost you most, why, and what to do, with the
  chart cropped to the stretch it's talking about. It's three steps at most. If
  you're a long way off the pace it opens with the general theme and stops
  there. At that distance a corner-by-corner breakdown doesn't help. On your
  reference lap it tells you there's nothing to correct, instead of inventing a
  lesson.

**Why, in detail**

- **Compare.** Pick car and track and two laps, one to review and one to compare
  against. You get four charts aligned on track position, **lap delta**,
  **speed**, **throttle and brake** and **steering**, with the corner bands.
  Hovering shows the values point by point. You can export the lap as **CSV** or
  **JSON**.

  On the **same screen** there's the **track map**. It shows your line coloured by
  the gap, and your braking points against the reference's. The corners carry
  **their names**, the same ones you find in the rest of the page. If you lost the
  lap, a red cross marks where you lost it. The map **stays put** while you scroll
  the charts. Hover over the delta and the same point lights up on the map.

  Under the map there's **Your braking points**, the panel with your braking
  points corner by corner. For each corner you read **the speed you brake at**, in which
  gear, how long the braking zone is and your minimum speed. Speed is a reference
  you have in every car, and you read it on the dash. There's also the **visual
  reference** where the track has one, like the 150 m board. Where it doesn't,
  **write your own**. The cell opens, and your reference goes into the sheet and
  into the coach's voice. At Imola two independent guides contradict each other on
  almost every corner. No measurement chooses between the 50 board and the 100
  board. You're the one looking at the corner.

  The last column is the **spread**, how far your braking point moves from one lap
  to the next. You read it in km/h and in the metres that means on that braking
  zone. We measure it on your latest laps **within the same track-temperature
  band**, and the header says which laps and at what temperature. The braking
  sheets on forums don't know this, and that's why their numbers aren't yours. You
  can download the sheet as **CSV**, and the **Print** button prints just the
  sheet.
- **Line.** Shows where you drove, corner by corner. The zoomed corner has your
  line and the reference's, and **the shaded band between them is the gap**. If at
  true scale it's too thin, the **gap ×3** selector magnifies it. The chart says
  so, and the scale bar stays true. Beside it you get the same corner in numbers.
  They tell you how far **inside or outside** you were at entry, apex and exit.
  Then you see whether your slowest point comes **before or after** the
  reference's. There's also how tight the **arc** you drove was, and how many
  **extra metres** you covered. Below is the table of every corner, which you can
  download as **CSV**.

  On the two lines you also see **where you brake and where you get back on the
  throttle**. The filled mark is yours and the empty one is the reference's.
  That's what turns "you're wider on entry" into a diagnosis. Wide with the same
  braking point and wide braking 15 m later are two different mistakes. The
  thresholds match the "Your braking points" panel, so the mark and the **You
  brake at** column talk about the same spot.

  At the bottom right of the drawing there's **the whole lap with the corner
  circled**. Two hairpins on the same track make the same picture, and without
  that drawing you'd have to remember which one you opened. At the top there's the
  **debrief sentence** for that corner. It's the same sentence as in the debrief,
  not a second opinion.

  **You can name the corner yourself.** Next to the corner's title there's a
  pencil. Write what you call it, and from then on that name appears everywhere,
  in the debrief, the losses, the braking points and the coach's voice. HONE
  knows the corner names of **14 of 26 circuits**, and for ten more ACC circuits
  it doesn't even have the shape. There, only you know the corner's name. If you
  don't like our name, yours replaces it, and you remove it the same way you
  added it. The names live in `Documents\ACCoach\corner-names.json`, in plain
  text, and you can read, copy and fix them by hand.

  Under the two lines you see **the track from above**, with the asphalt and the
  kerbs, and the grass, gravel and concrete beside them. It isn't a drawing of
  ours. It's the geometry the game uses to decide where you are, read piece by
  piece from its surface model.

  We recognise the track **by the shape of your lap, not by its name**. The two
  sims name circuits differently. Mount Panorama is `mount_panorama` in one and
  `rt_bathurst` in the other, so the name isn't enough to find it. Without the
  game installed there are still the **26 circuits HONE ships with**. Their centre
  line and widths come from OpenStreetMap and satellite imagery. They have less
  detail and no kerbs, but they don't depend on what you have on disk.

  The page warns you about two things.

  * The track only appears **if it really is the one you drove on**. Different
    versions of the same circuit are around, and one that doesn't fit would draw
    the road in the wrong place.
  * The track **disappears when you magnify the gap ×3**. There the drawn line is
    no longer where you drove, and you'd look off the road without being off.

  The drawing **rotates** to fill the box. A rotation doesn't move one point
  relative to another. Shape, widths and metres stay the same, and the scale bar
  measures the same metres.

  On "before or after" the tab gives you two warnings of its own. In a long corner
  the bottom of the speed curve is **flat**, like at Fagnes for about a hundred
  metres. There two identical laps would have their minimum in two different
  places by pure chance. HONE then writes **same place** and says over how many
  metres the minimum is flat, instead of having you chase a difference that isn't
  there. If you went off or spun in that corner, it doesn't tell you that you
  took the apex late. It tells you, for example, "You drop to 32 km/h against 93,
  so there's no line to read here".
- **Sectors.** Shows the three sectors, the **track's real ones** when the game
  publishes them, and otherwise the lap split into three parts. The tab says
  which. You see your time against the reference with gap bars. Then there's the
  **ideal lap**, your best sectors put together, with what it's worth against your
  actual best lap. Below you get **every lap, sector by sector**, with the best of
  each column highlighted. Nobody drove the ideal lap, and there you see **which
  laps it's made of**. So you can tell whether that sector was a lucky one or a
  habit.
- **Dynamics.** Tells you what the car was doing, not what you did. You get the
  longitudinal and lateral G in the **G-G diagram**, which tells you how much of
  the available grip you were using. Then there's **slip** per axle, with the
  front locking and the rear spinning. After that come **rotation** against
  steering, **revs** with the shifts, and the **tyres along the lap**, with
  temperature and pressure. The **Balance** chart colours the line blue where the
  car understeers and red where it oversteers. It's the tab to open when the
  debrief tells you why and you want to see it with your own eyes.

**Over time**

- **Trends.** At the top you find **your faults, session by session**, up to
  twenty sessions, measured against the same reference as the Report card.
  That's where you see whether a fault goes down, and a click on its name opens
  its **How to do it**. Below are your lap times over time, your **consistency**
  and your **weak points** corner by corner, systematic or one-off. Then the
  **recurring mistakes**, with how many times you made them and in which
  corners. This is where the numbers are worked out. The plan that comes out of
  it lives on the **Report card**, and the tyres live in **Race pace**.
- **Race pace.** Tells you how the pace holds up **on a single tank**. It's a
  different cut from Session, and the difference matters. We work out a session
  from the timestamps, and one outing can contain a **refuel**. Averaging the
  pace across a refuel mixes two fuel loads. A stint is cut where the tank **goes
  back up**. We compare the fuel at the end of a lap with the fuel at the start of
  the next.

  For each stint you get the **pace**, the median of the laps actually driven at
  pace. A spin stays on the list but doesn't count towards it. Then the
  **spread**, the fuel per lap, the laps left in the tank and the pace chart lap
  by lap. At the bottom are the **tyres across the stint**, with temperatures and
  pressures per wheel.

  What the numbers **don't** say matters more than the numbers. The pace trend is
  a **net** figure. The stint speeds up because the tank empties and slows down
  because the tyres fade. To separate the two you'd need to know what a litre is
  worth in seconds, and today **we don't know**. It's measured by driving a stint
  on purpose at a constant pace. That's why the slope comes with its own margin of
  error. When the slope is smaller than that margin, the tab writes "There's no
  measurable drift." instead of inventing a degradation for you. It isn't tyre
  wear either, because neither sim publishes it. What you see is temperature.

In the lap dropdown, next to the time, you find **the track temperature**, as in
`2:03.732 · 37.8 °`. It matters. Between a cold track and a hot one, braking
points move by 10-20 m. Two laps at very different temperatures are almost two
different circuits, and comparing them tells you little.

Under the other tabs there's always **the lap you're looking at**, with time,
reference, gap and track temperature. With many tabs it's easy to read one lap's
numbers while thinking of another.

The horizontal axis of every chart is **in metres**, not in per cent of the lap.
"At 50 %" is a number you'd have to convert before you could drive with it. We
**measure the metres on the recorded coordinates**, and we don't derive them from
the position times the track length. Sometimes a lap has no coordinates, or its
coordinates don't add up with speed and time. Then the axis falls back to per
cent, instead of giving you a wrong scale.

There are two shortcuts. **Every tab opens with a key**, in order from left to
right, and you see which one by hovering over the tab. The lap dropdown has one
too. The **[** and **]** keys step through the laps.

Under each corner you also see **where, inside the corner, the time went**. It
can be a bar split into *entry, apex, exit and the run after*, and hovering shows
the seconds of each piece. When nearly all the time is in one place, you get a
single sentence instead, like "Most of the time goes on entry, 0.21 s.". It isn't
an estimate. It's the time lost in the corner split into pieces, and the pieces
add up exactly to the total. The run after is there because the debrief gives a
corner the straight that follows it too. That's where you pay for a bad exit,
and without that piece the other three wouldn't add up.

Sometimes, under a corner's title, you find a line that starts with **↩**. It
means **the loss in that corner didn't start there**. You arrived already slower,
and the km/h you're missing at the entry were already lost at the exit of the
corner before. In that case **that** is the corner to work on, and once it's
fixed, this one improves by itself. The line only appears when the numbers really
add up. If you lost the speed on the straight between the two, with a lift or a
bad shift, we don't blame the corner before.

In the debrief, **above** the list of corners, one or two boxes with a light blue
border can appear. They're observations **about the whole lap**, not about one
corner.

- *You lift where the reference stays flat out.* The box tells you what the lift
  cost you. The figure only covers the lift itself, but you carry the speed you
  lose down the straight.
- *You're N km/h down on top speed.* Here the rest of the sentence matters. If
  you're as fast as the reference in the corners, it isn't you who's slower, and
  you should look at the wing and the gearing. If you're slower in the corners
  too, it's exit speed, and the setup has nothing to do with it.

### Corner by session

Under the weak points, every **systematic** corner has its own chart. It shows
the median loss in that corner, **one bar per session**. Two outings on the same
afternoon stay two bars. That way you see whether what you changed between them
worked.

There are two thresholds, and both apply. A session with **fewer than three
laps** through that corner doesn't appear, because a median over two laps is worth
little more than one lap. A missing session is **not** drawn at zero, because zero
here means you took the corner well. And the corner only appears with **at least
two sessions** above that threshold. A single point isn't a trend, it's a lucky
lap. A corner that has just become systematic may not have a chart yet, until it
has two good sessions.

### Which lap becomes the reference

It's your fastest lap with that car on that track, with three extra rules.

- **Dirty laps are never candidates.** A cut lap is faster for a reason.
- **A lap nobody judged doesn't beat a lap that was judged.** On ACC, the "clean"
  of laps recorded **before 21 July 2026** came from a field that game declares
  and never fills. It said clean because nothing looked, not because the lap was
  clean. We don't throw those laps away. They stay your reference if you have
  nothing else, because a doubtful target beats no target. But they lose to any
  lap that was really checked. The rule came from a real case. At Monza the
  reference was a 1:53.712 that **cut the Variante della Roggia** for half the
  corner. It was the fastest precisely because of that. When this happens,
  the summary says "Chosen because it was checked". Then it adds "your 1:53.712 is
  faster, but nothing has checked it for track limits".
- **Conditions matter**, and there are three of them, the **tyre**, the **track
  temperature** and the **track grip**. A lap driven in conditions close to
  today's beats a slightly faster one driven in very different conditions. The
  tyre weighs most of all, because a different compound is a different car, and
  grip weighs least. It's a preference, not a filter. If nothing resembles
  today, the reference is still your best lap.

  Two things to know about this data. We **only compare** the tyre, without
  interpreting it. On ACC the compound name is always the same, `dry_compound` or
  `wet_compound`. On AC it's whatever the car's author chose, like `Soft (S)`.
  That's still enough to tell whether two laps were on the same tyre. **Grip on
  ACC is always 0**. That game leaves the old field at zero and puts the
  conditions in another part of the memory, which we don't read yet. So on ACC
  grip carries no weight, and the reference is decided on tyre and temperature.

In the **report** the same rule applies, but there "today" doesn't exist. The
reference is chosen for the conditions **of the lap you're reviewing**. If you
review a lap from a cold morning, the right target is your best in that cold.
It isn't the record set in the evening on rubbered-in asphalt. Otherwise every
tenth in the debrief would measure the weather and not the driving. When the
comparison lap is slower than your best, the summary tells you, with the
temperature of both. For example "Chosen for conditions" and "track at 12.0 °C,
while your 1:39.000 was set at 32.0 °C". If you pick the comparison lap yourself
from the dropdown, your choice holds and doesn't change.

If you're a long way off the pace, your own best lap is a target that keeps you
where you are. In the **Analysis** section of the hub there's
**Import a PRO reference lap**. You can import a faster lap, and from then on the
coach measures you against it.

> Want to try HONE without the game? `python accoach_main.py web --demo` loads
> sample laps.

### The tablet view

The QR code in the Drive panel opens `/tablet`, a page made for an old
tablet beside the wheel, like an iPad 3. It changes by itself depending on where
you are. If the coach isn't running, the page says so and reconnects as soon as
it's back. If the coach is on but the game isn't sending data, the page says
it's waiting for it. That happens when the game is closed or hasn't started yet.

At the top there are two tabs, **Telemetry** and **Setup**. When you stop in the
pits the page switches to Setup, and when you drive off it goes back to
Telemetry. You can always tap the other tab, and your choice holds until you
enter or leave the pits. Setup shows a mark when there's a change to make in the
pits. On both tabs, above the phase, is the road described in "The engineer's
road".

- **Telemetry.** You see speed, gear, TC, ABS and engine map, and the temperature
  and pressure of the four tyres. A strip shows throttle, brake and steering
  from the last 8 s. Below it are the road and the phase the engineer is on.
  A change to make from the wheel appears in a box. The *I've changed it* button
  is there only where HONE can't read the dial, as explained in "Setup advice".
- **Return-to-pits call.** When the engineer has a change to make in the pits,
  the call to come in at the end of the lap appears at the top. The telemetry
  stays below. For a rejected change the call is similar and tells you to put
  the last change back as it was. Tapping the call takes you to Setup.
- **Setup.** The page shows the phase and the levers to change, one per row,
  from the current value to the new one. Below are the reason and the
  confidence. As the starting file, HONE offers the last setup it wrote for
  that car and track since the web process started. If it hasn't written one,
  it offers the most recently modified file. You can pick another from the
  list. Press *Write the change* and confirm. HONE creates a new file and
  leaves yours alone. The page then shows the file name in large type, to load
  from the game's garage. If it can't find a setup for that car on that track,
  it asks you to save one from the garage.
- **On track, Setup is for reading.** You see the change, the starting file
  and the levers while you drive, but the buttons only switch on when you're
  stopped in the pits. When you write the file, the engineer starts counting
  the test laps. On track the car still has the previous setup, and those laps
  would say nothing about the change.
- **A rejected change.** The button becomes *Write the restore* and writes a file
  with the previous values. If you've already reloaded the previous file in the
  game's garage, press *I've already put it back*. This button too only works
  in the pits.
- **The full Engineer page follows the same rule.** Its writing buttons switch
  off when you're driving and not stopped in the pits, even paused on track.
  With the game off or in the menus you can still write, to prepare a setup
  without driving.

For anything else, such as the history of the trials, use the full engineer
page. It stays at `/engineer`, and the *Full page* link at the bottom of the
tablet view leads there. On an old browser the full page doesn't start. There
the link isn't shown, and opening `/engineer` lands on `/tablet` by itself.

### Opening the report on a phone or tablet

You need this if you play on three monitors and want the **Report** or the
**Engineer** on a screen to the side.

1. In the hub, in the **Devices** section, tick **Allow access from other devices
   on my network**. HONE remembers it.
2. The QR codes appear, including **Report** and **Engineer**, with the address
   under them, like `http://192.168.1.23:8778`. **Scan the code** with your phone,
   or type the address into the browser.

A few practical details.

- The phone has to be on the **same Wi-Fi network** as the PC.
- If **Windows** asks the first time, allow access on **private networks**.
- For the **Report**, which shows your saved laps, the analysis only has to be
  running. The live **Engineer** page also needs Coach Live, or the Live backend
  if you drive without the overlay.
- With the option off, everything stays on this PC only, at `127.0.0.1`.

---

## 6. The debrief in the terminal

For a quick summary after the session, type this.

```
python accoach_main.py debrief [car] [track]
```

It lists the corners where you lost the most time, with the cause, and your
consistency. It reads the saved laps, so the game can be closed.

---

## 7. Every command

From a terminal in the source folder, type `python accoach_main.py <command>`.
The packaged app has no console window,
so `HONE.exe <command>` runs the command but prints nothing in the terminal.

**To drive you only need three commands**, the same ones you see with
`python accoach_main.py help`.

| Command | What it does |
|---|---|
| `live [--silent]` | **Voice coach and overlay** in one process. It's the normal way to use HONE. |
| `web [--demo]` | The analysis in the browser, with saved laps, report and guide. |
| `launcher` | The hub, the window with all the sections. |

The other commands are tools for developing, testing on track or using a second
screen. You don't need them to drive, and that's why they aren't on the first
screen. You get the full, up-to-date list like this.

```
python accoach_main.py help --all
```

These are the ones you might really need.

| Command | What it does |
|---|---|
| `debrief [car] [track]` | The text debrief after the session. The game can be closed. |
| `coach [--silent]` | The voice coach in the terminal, without the overlay. |
| `recorder` | Records laps only, without the coach. |
| `monitor` | Shows the raw telemetry. |
| `setup show <file>` | Reads an ACC setup without starting the game. |
| `selftest` | Checks that the voice works and writes a report. |
| `logs` | Opens the folder with the logs and crash reports. |
| `logs --zip` | Packs the logs and some context into one file to attach to a report. **The logs go in as they are, unfiltered.** Read "What's in that zip" before you send it. |
| `find-rain` | Finds the ACC rain fields by measuring them. You need a session with changing weather. |

### The configuration file

Almost everything is set from **Settings**. The rest is in
`Documents\ACCoach\config.toml`, which HONE creates on first start with a comment
for each entry. Edit it with the app closed, because **values are read at
startup**.

These entries only exist there.

| Entry | What it sets |
|---|---|
| `data.laps_dir` | Moves the laps folder, to another disk or a synced folder. If you leave it empty it stays `Documents\ACCoach\laps`. |
| `acquire.hz` | How many samples per second the recorder reads. |
| `server.host` · `server.port` · `server.hz` | Address, port and rate of the Live backend. |
| `web.port` | The port of the analysis. |
| `logging.level` · `logging.console` | How much the logs write. |

---

## 8. Getting the most out of it

- **Build a good reference.** The coach compares you with your fastest clean
  lap. At first that's your first clean, complete lap, and then it's replaced
  every time you drive a better one.
- **Always use Borderless** if you want the overlay.
- **Work on one car and one track at a time.** The reference only holds for that
  car on that track.
- If the coach distracts you while you're learning a track, use `--silent` and
  watch only the overlay. Turn the voice back on when you want the advice.
- Go over the **recurring mistakes** in Trends. That's where your pace improves.

---

## 9. If something goes wrong

- **The overlay stays on "Waiting for the game…" and doesn't connect.** The game
  has to be running and you have to be on track, in a session. HONE only reads the
  shared memory while the game is running.
- **You can't see the overlay.** You're in exclusive fullscreen. Switch to
  **Borderless**.
- **You can't hear the voice.** Check you didn't start with `--silent`. Then run
  `python accoach_main.py selftest`, which writes a report and tries to speak.
  From the source, install pyttsx3 with `pip install pyttsx3`.
- **Some sentences sound more robotic than others.** The coach's fixed sentences
  and the focus's short words are recorded with a neural voice. Sentences that
  change every time, like the focus announcement with the corner's name, come from
  the Windows voice, which is more robotic. It changes the sound, not what you're
  told.
- **No corner advice arrives.** You don't have a reference yet. One clean,
  complete lap is enough, from the line to the line. The immediate warnings arrive
  anyway.
- **The analysis doesn't show your laps.** You have to drive them first with Coach
  Live or the recorder. They end up in `Documents\ACCoach\laps`, where the
  analysis reads them.

### Where the logs are

`logs` opens the folder with the logs and the crash reports. To send them to us,
`logs --zip` packs them into a single file in `Documents\ACCoach\`. It writes the
zip even when there are no logs at all, and says so inside. "There were no logs"
and "I didn't collect them" are different answers.

From the source you type `python accoach_main.py logs --zip`. From the packaged
app, `HONE.exe logs --zip` makes the zip just the same, but prints nothing in
the terminal.

### What's in that zip

Two things, and they aren't the same.

The first is `contesto.txt`, which we write. It has the version, the commit, your
Python and Windows versions and the last cars and tracks you drove. It has no
paths, no machine name and no account name, because none of that would help us.

The second is your log files, which go in **exactly as they are, unfiltered**.
At least all of this is in them.

- Paths that include your Windows account name, like `C:\Users\<account>\...`,
  and any network location you set as your laps folder.
- One dated line every time you started HONE. Together they're a record of when
  you sat down to drive, going back as far as your oldest log.
- Your lap times, the tracks and cars you drove, and the names of the files you
  opened.
- Crash reports (`crash-*.log`), each with the full error, the paths of our source
  files and whatever value the error carried with it.

We leave all of it in on purpose. A log with the interesting parts taken out
can't diagnose anything, and quietly censoring one would be worse than the path.
The zip is an ordinary file on your disk, and `contesto.txt` inside it says this
too. From the source, the command also prints it when it finishes. Open it and
look before you send it.

---

## Free and Pro

HONE will have a **freemium model with a one-time purchase**, and no
subscription. Today everything is free, while the product grows with the
community.

| Feature | Free | Pro (coming) |
|---|:---:|:---:|
| Voice coach and overlay | yes | yes |
| Debrief with the why, and the analysis app | yes | yes |
| Race engineer (setup) | no | yes |
| Focus and training plan | no | yes |
| Importing PRO reference laps | no | yes |

Pro will be a one-time purchase. The model may change before launch.

---

Got more questions? Open an [issue on GitHub](https://github.com/ardiz89/ACCoach/issues).
