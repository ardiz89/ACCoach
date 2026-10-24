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

### Tablet and pages

- A tablet view built for older iPads (Safari 9): live telemetry, the pit
  reminder, and the setup tab when you're stopped in the pits. [#116, #117]
- The engineer page uses tabs on narrow screens and shows live steering. [#114]
- The report opens on a one-page summary of how the last session went, and
  every view links to the next useful one. [#115]

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
