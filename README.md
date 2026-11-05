# Single Song Planner (SSP)

Plan your set, and keep everyone in sync on stage.

SSP is a tool for bands and other music groups to work out a song's
structure together -- sections, tempo, count-ins, and reminders for each
player -- and then give every musician a live, synced, on-stage reference
on their own tablet or phone.

## What it does

- **Draft a song's structure** as a band: verses, choruses, bridges, however
  you think about your songs. Set bars and tempo per section, a count-in
  style, and hints -- a note for the whole band, or something aimed at one
  player ("Bass: root notes only here").
- **Build a setlist** from your songs and switch between them instantly.
- **Play it live**: any connected device can start a run, and every
  tablet/phone scrolls and highlights in sync, with its own metronome
  click playing in time.

## How it works

One small server -- a laptop, a Raspberry Pi, or similar -- runs on your
own Wi-Fi and holds the whole band's songs and setlists. Everyone in the
room (drafting the structure, or following along live) opens the same
address in their phone or tablet's browser. There's no app to install, no
account, no internet connection involved at all.

**This is deliberate, not a limitation to work around.** SSP is meant to
run on your local network only -- never exposed to the internet -- because
a remote server is exactly the kind of lag and dropped-connection risk a
rehearsal or a live set can't afford.

**Trust model (v1):** anyone on the same Wi-Fi who has the address can
read and edit everything. There's no per-user login yet -- treat the
server's address the way you'd treat a shared rehearsal-room whiteboard.

## Getting started

On a laptop, open the desktop control panel:

- macOS: double-click `launchers/start-macos.command` (or run the packaged
  `Single Song Planner.app`, see "Packaged builds" below)
- Windows: double-click `launchers/start-windows.bat` (or
  `SingleSongPlanner.exe` once packaged)
- Linux: run `launchers/start-linux.sh` (or the packaged
  `SingleSongPlanner` binary)

1. Pick (or create) a folder for your band's songs and setlists -- the
   panel remembers it, and a handful of recently used folders, for next
   time.
2. Click **Start server**. The panel lists the addresses to open --
   something like `http://192.168.1.42:8420/`.
3. On each phone or tablet, connect to the same Wi-Fi and open that
   address in the browser.
4. Start planning. Everything you create is saved as you go.

Running it on a headless Raspberry Pi instead (no screen, always on) skips
the control panel: run `server/app.py` directly, or install it as a
background service -- see `launchers/ssp.service`.

Requires Python 3.9+ with Tk (python.org's installers for Windows/macOS
already include it; on Linux, `sudo apt install python3-tk` or your
distro's equivalent) -- or just use a packaged build below, which needs
nothing installed at all.

### Packaged builds

For anyone who'd rather not install Python: `packaging/` has a PyInstaller
spec and a build script per OS (`build-macos.sh`, `build-windows.bat`,
`build-linux.sh`) that produce a standalone, double-click-to-run build --
same idea as QLC+ Swiss Knife's packaged releases. Each must be built ON
that OS (PyInstaller doesn't cross-compile); see `packaging/ssp.spec` for
what gets bundled.

## Credit

SSP's song-structure focus takes its cue from
[song-map.com](https://song-map.com/). The "one local server, every device
a synced client" pattern -- and the metronome/click-track engine -- are
adapted from
[QLC+ Swiss Knife](https://github.com/giopas/qlc-plus-swiss-knife-tool-script)'s
Stage Monitor feature.

## Status

Early and actively developing. See `claude/WORKPLAN.md` for the current
roadmap and `CHANGELOG.md` for what's shipped.

## License

MIT -- free and open source, forever. See `LICENSE`.
