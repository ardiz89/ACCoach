# HONE — Frequently Asked Questions

Quick links: [Requirements](#requirements) · [Install](#install) ·
[SmartScreen & SHA-256](#smartscreen--security) · [Privacy](#privacy) ·
[Overlay](#overlay) · [Free vs Pro](#free-vs-pro) · [Troubleshooting](#troubleshooting)

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

## Troubleshooting

**"Waiting for the game…" and it won't connect.**
Start AC/ACC and enter a session (practice/hotlap/race). HONE connects as soon as
the game starts publishing telemetry.

**I have no reference lap.**
Drive at least one valid lap: it becomes the reference. Or seed a PRO lap:
`python -m accoach import-reference <file.lap.json.gz>`.

**The voice isn't speaking.**
Run with the voice on (default) rather than `--silent`. Fixed phrases use a
pre-rendered neural voice; numeric phrases fall back to the system voice.

**Where are the logs if something breaks?**
`python -m accoach logs` opens the folder with logs and crash reports.

---

More questions? Open an [issue on GitHub](https://github.com/ardiz89/ACCoach/issues).
