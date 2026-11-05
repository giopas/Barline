# Changelog

All notable changes to this project are documented here. Versioning
follows semver (MAJOR.MINOR.PATCH).

## [Unreleased] -- v0.1

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

### Scope notes

- One client at a time -- no multi-client WebSocket sync yet (v0.3).
- No metronome/click audio yet (v0.2 for offline/preview, v0.5 for the
  live transport).
- No player-role selection or hint-visibility emphasis in the UI yet
  (v0.4) -- hints can already be scoped to a player id in the data model.
- No recorded hint audio yet (v0.6).

See `claude/WORKPLAN.md` for the full roadmap.
