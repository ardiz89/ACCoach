# Changelog

What changes from one HONE release to the next, written for the people who
drive with it. Numbers in brackets are the pull requests on GitHub.

## Unreleased: first public release

HONE has not had a public release yet. Everything below is what the first one
will contain, grouped by what you'll notice.

### While you drive

- The coach talks about one theme at a time, with a trigger word agreed in
  advance, and stays quiet when a call would only add noise. [#85, #113]
- With a focus active, the coach talks about the focus corner and doesn't
  repeat the same sentence within a lap. [#113]
- Lock-up warnings no longer fire while you park in the pits. [#86]
- The pit-entry reminder stays on screen until you actually come in. [#83]
- A new neural voice in Italian and English, recorded with ElevenLabs, with an
  optional pit-to-car radio effect. [#117]
- Repeated track-limit exits with the same pattern now point at the setup, not
  just at the driver. [#112]
- Coach Live opens a guided session from the hub, and the engineer page stays
  live while you drive. [#104, #115]
- Every corner is measured against your own best attempt at it, on laps in the
  same conditions, live and in the report.
- The coach tells you when a lap was invalidated and why, once the corner is
  over. It doesn't repeat the same sentence, and it leaves the out-lap alone.
- The coach never suggests raising ABS or TC on a car that runs them at zero.
- The pedal trace shows bars with a notch at the reference, and the steering
  on the side you turn.
- Moving the overlay works on one copy that follows the settings, saves when
  you let go, and goes back to the centre on request.

### Race engineer

- The engineer walks through the setup in phases (pressures, mechanical grip,
  traction, brake balance) and keeps only the changes that measurably help. A
  change that didn't help stays flagged until you restore it. [#84, #108]
- It calls you into the pits for tyre pressures and prepares the change. [#111]
- On Assetto Corsa, one click is worth what it is worth on that car, and an
  unknown car class never inherits another class's window. [#109]
- The GT3 pressure window follows ACC 1.9 and lives in one place. [#106]
- Before a change it states how the change will be judged, and it keeps score
  of how often it is right. [#57]
- It asks which setup it is working on, and calls you into the pits when it is
  waiting for your answer. A test the tyres contradict stays on hold until you
  answer.
- Coming into the pits, it tells you how many litres to add.

### Tablet and pages

- A tablet view built for older iPads (Safari 9): live telemetry, the pit
  reminder, and the setup tab when you're stopped in the pits. [#116, #117]
- The engineer page uses tabs on narrow screens and shows live steering. [#114]
- The report opens on a one-page summary of how the last session went, and
  every view links to the next useful one. [#115]
- The tablet shows the fuel and the laps it lasts, and asks again for the list
  of setups while it is empty.

### After you drive

- "Lap explained": what cost you most, why, and what to do, one thing at a
  time. [#42]
- Session, race pace per tank, braking points from your own laps, the line
  against your reference in metres, and the track seen from above with kerbs
  and run-offs. [#43, #45, #46, #55, #58]
- A training plan with a target and a date, measured only on the laps that
  follow. [#50, #56]
- Corner names on Monza, Imola, Spa, Suzuka and other circuits, measured from
  real laps and never guessed. [#53, #59] You can also name a corner yourself,
  and your name wins.
- Two laps close together no longer share the same lap time, and a saved lap
  no longer resets the coach. [#102, #110]
- "Corner by corner": every valid lap of a session, corner by corner. It shows
  what you lose on a typical lap, where in the corner, your braking and your
  line.
- On the twelve ACC tracks, the same tab shows what public guides and videos
  say about each corner, with a short quote and a link. A fact becomes a
  reference only when at least two independent authors say it and a check
  confirms it. Gears and braking come only from GT3 sources.
- The map has the track seen from above under the lines, taken from the
  Assetto Corsa files on your PC, with zoom. Over it the line keeps one width,
  and the colour shows the gap.
- The cause of a time loss in a corner is the phase that costs the most. The
  report names what you do differently from the reference only where the time
  goes and above the noise between two laps. Grip is measured against the limit
  at that speed.
- The PRO lap is no longer one of your laps. It wins only when it is faster
  than your best, and the import says what happens.
- A lap with the car standing still for more than 5 seconds counts towards no
  average, no consistency and no defect. Its errors still count.
- The ideal lap and the consistency use only laps that stayed on track.

### Privacy and security

- The local servers answer only this PC by default. In tablet mode, a device
  on your Wi-Fi needs the key from the QR code. [#118]
- Other websites open in the same browser can't read your laps or write a
  setup. Writes accept JSON only, and request bodies are capped at 1 MB. [#118]
- Setup names can't escape the setup folder, and Windows reserved names such
  as `CON` are refused with an explanation. [#103, #118]
- Corrupt setup and track files are reported instead of crashing the app.
  [#118]
- The release build installs its dependencies from a lock file with pinned
  hashes, publishes the SHA-256 of the ZIP, and attaches a signed build
  provenance you can check with `gh attestation verify`. [#118]
- `logs --zip` builds a bundle for a bug report, replaces your Windows home
  folder with `%USERPROFILE%`, and says what's inside before you send it.
  [#97, #118]

### Known limits

- The executable isn't signed with a paid certificate, so Windows SmartScreen
  shows a notice on first run. The FAQ explains how to check the file.
- The tablet view needs the PC and the tablet on the same network, and some
  security software blocks it until you allow HONE.
