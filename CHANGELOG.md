# Changelog

All notable changes to this project are documented here. Versioning
follows semver (MAJOR.MINOR.PATCH).

## [0.9.0] -- 2026-11-05

Everything planned for 1.0 is in. 1.0.0 gets tagged once it's been played
through on real tablets and phones over real Wi-Fi.

### Added

- **Metronome.** Each device plays its own click (wood, beep or tick, with
  a louder first beat), scheduled on the browser's audio clock so it
  stays tight. Preview a whole song's click, or one section's count-in and
  first bars, while planning. The sounds are the same ones QLC+ Swiss
  Knife uses, built from the same formulas.
- **Practice click tracks.** Download a `.wav` of a song's click, with
  every tempo change and count-in in place.
- **Live sync between devices.** Every edit shows up on every connected
  device within a moment, without losing anyone's cursor. When another
  device changes the song you're on, you're told who. A dropped Wi-Fi
  connection reconnects by itself and catches up.
- **Connect a device**: a QR code for the server's address, plus one per
  player that opens straight into that player's live view. The desktop
  control panel shows the QR code too.
- **Band page**: players with a name and an instrument. Removing a player
  sends their hints back to the whole band.
- **Who's using this device**: each phone or tablet says who's holding it;
  hints aimed at that player stand out ("For you"), others' hints stay one
  tap away. The sidebar shows how many devices are connected.
- **Live view and transport.** Any device can start or stop a song for the
  whole band. The server fixes the start time and shares the tempo map;
  every screen then follows the song from a shared clock: the current
  section, bar and beat, what's next and how soon, your hints, the next
  section's hints, and the whole song scrolling along. Start from any
  section. Setlists: cue a setlist, move between songs from any device,
  and the next song comes up ready at the end of each one. Space and arrow
  keys (and so most Bluetooth page-turner pedals) start, stop and change
  song.
- **Count-ins on stage**: a count-in, even mid-song, shows in yellow with
  the beat. A run always starts with a count-in (one bar of click if the
  first section has none).
- **Voice memos on hints**: record one (on the server's own computer) or
  attach an audio file (on phones and tablets), up to 30 seconds; anyone
  can play it back. Memos no song uses any more are cleaned up.
- **Printable charts** for a song or a whole setlist, for the whole band or
  one player. Print, or save as PDF.
- **Export and import** a song as one `.ssp.json` file with its voice
  memos. Importing never overwrites an existing song.
- **Demo band** (`demo/`, a fictional band and six songs), opened with
  `server/app.py --demo` or the control panel's "Try the demo band". Always
  a throwaway copy.
- **Phones**: the editor and live view both fit a phone screen; the sidebar
  becomes a slide-out menu.
- **Setlists** can be reordered and show each song's tempo and length and
  the set's total time.
- **Raspberry Pi guide** in the wiki: running headless as a service,
  `ssp.local`, and the Pi as its own Wi-Fi hotspot. `launchers/ssp.service`
  updated to match.
- **Wiki** pages for the metronome, printing and moving songs, and the Pi,
  with screenshots and GIFs throughout; the README has them too.
- **Tests**: server API, live sync, transport, clips, export/import, a
  decoded QR code, the browser and server tempo maps agreeing on every
  demo song, and browser tests with two and three devices
  (`python3 -m unittest discover -s tests`).
- **Screenshots and GIFs** are made by `tools/shots.py` from the demo
  band, so they can be retaken whenever a screen changes.

### Changed

- Live sync uses Server-Sent Events rather than a WebSocket: the server
  only ever pushes, edits still go up as normal requests, it needs nothing
  outside Python's standard library, and browsers reconnect it by
  themselves.
- The control panel stops the server properly (ends the live run and
  every device's connection) so the port is free straight away.
- Section, hint and player ids made in the browser are now plain random
  ids (no `tmp-` prefix). Songs saved by 0.1 load unchanged.

### Security

- Stricter Content-Security-Policy (no framing, no referrer); every
  request body has a size limit; recorded clips are only ever read or
  written by a strictly checked name inside the data folder's `audio/`
  folder; printed charts escape everything they show.

## [0.1.0] -- 2026-11-05

### Changed

- Renamed the project from "Single Song Planner" to "SSP -- Song and
  Setlist Planner" everywhere a person sees it (README, window titles,
  the web app's title/tagline, the server's startup banner, the
  packaged macOS app's display name). The short form "SSP", the repo
  name, and every on-disk/technical name (settings folder, packaged
  binary, macOS bundle identifier) are unchanged, so nobody's
  already-saved settings or data folder move.
- Added a wiki (`wiki/`), written for the band using the tool rather
  than a developer reading the source, covering what SSP is for and
  how to get a rehearsal or show set up.

### Added

- Server (`server/app.py`): plain stdlib Python, headless-capable, holds
  the data model in memory backed by one-JSON-file-per-song storage.
- JSON REST API: band/players, songs (with sections and hints), setlists.
- Single-page web app (`web/static/`): song switcher, setlist builder,
  section editor (label, bars, BPM override, count-in), hints per
  section, bar/beat visualization (song-shape overview strip + detailed
  per-section bar/beat grid).
- Launchers for macOS, Windows, and Linux; a starting-point systemd unit
  for a headless Raspberry Pi.
- Atomic JSON writes (temp file + rename) so a dropped connection or a
  crash mid-save can't corrupt a song file.
- Desktop launcher (`launcher/gui.py`): a small Tkinter control panel --
  pick a data folder, pick a port, start/stop the server, see the
  reachable addresses, watch a live log -- instead of a terminal.
  Launcher scripts now open this by default; a headless Pi still runs
  `server/app.py` directly.
- Settings persistence (`launcher/settings.py`): the chosen data folder,
  port, and a recently-used-folders list ("sessions") are saved to a
  per-OS app-support folder and restored next launch.
- Packaging (`packaging/`): a PyInstaller spec plus a build script per OS
  (Windows/macOS/Linux) producing a standalone, double-click-to-run
  build -- no Python install needed to use it.
- Color coding: each section gets its own color, consistent across the
  song-shape overview strip, its bar/beat grid, and its card's left
  border, so the structure reads at a glance.
- Duplicate-section button: clone a section (bars, BPM override,
  count-in, and all its hints) and insert the copy right after it, for
  repeating a section verbatim without retyping it.

### Fixed

- Editing a section's label, bar count, or BPM override -- or adding a
  hint -- could silently fail to save after a different edit on the same
  song had already round-tripped to the server: the rendered inputs kept
  showing what was typed, but the underlying object those edits were
  applied to had become stale and was no longer what got saved. (The
  editor stopped replacing its in-memory copy of the open song/setlist
  with the server's response after a save, which was the root cause.)
- A second instance of the same underlying issue: editing a section's
  bar count a second time, or adding a second hint, after the section
  card had already finished its first render, could throw instead of
  saving (looking up the target element through the already-emptied
  `<template>` clone instead of the live card in the document).

### Scope notes

- One client at a time -- no multi-client WebSocket sync yet (v0.3).
- No metronome/click audio yet (v0.2 for offline/preview, v0.5 for the
  live transport).
- No player-role selection or hint-visibility emphasis in the UI yet
  (v0.4) -- hints can already be scoped to a player id in the data model.
- No recorded hint audio yet (v0.6).

See `claude/WORKPLAN.md` for the full roadmap.
