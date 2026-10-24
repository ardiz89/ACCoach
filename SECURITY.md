# Security

HONE runs on your PC with no account and no cloud. It still opens two local
web servers (the analysis pages and the live feed), writes setup files into
the game's folders, and in tablet mode answers devices on your Wi-Fi. A flaw
in any of those matters, and we want to hear about it.

## How to report

Report it privately through GitHub:
[Report a vulnerability](https://github.com/ardiz89/ACCoach/security/advisories/new).
Don't open a public issue, and don't post it on Discord or Reddit until a fix
is out.

Tell us the HONE version, how you run it (release ZIP or source), what an
attacker can do, and the steps to reproduce it. A proof of concept helps, as
long as it runs against your own machine only.

You'll get a reply within 7 days. When a fix ships, the release notes credit
you, unless you prefer otherwise.

## What's in scope

- The local servers: a page or device that reads laps, writes a setup or
  changes the settings without the key or without being on this PC.
- The tablet key: guessing it, reading it, or getting past it.
- Setup and track files: a crafted file that writes outside the game's setup
  folders or crashes HONE.
- The release: a way to ship a ZIP that doesn't match its published SHA-256
  or its build provenance.
- The log bundle: personal data that ends up in `logs --zip` without being
  declared.

## What's out of scope

- Someone with full access to your Windows account. They can already read
  your files.
- The games themselves, and the shared memory they publish.
- SmartScreen notices on the unsigned executable. They are expected, and the
  FAQ explains how to check the file.

## Supported versions

Only the latest release gets security fixes.
