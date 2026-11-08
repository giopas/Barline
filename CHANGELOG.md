# Changelog

All notable changes to this project are documented here. Versioning
follows semver (MAJOR.MINOR.PATCH).

## [Unreleased]

## [0.14.0] -- 2026-11-08

The band's own Wi-Fi, for a room with no network.

### Added

- **Make a Wi-Fi** in the control panel's Connect card (`server/hotspot.py`):
  this computer becomes the band's Wi-Fi, `SSP-Band` with a password SSP
  makes up (easy to type: `kmrt-vhae-4827`; both editable and remembered).
  When the computer has no network the button turns blue and the card says
  so. While it's on, the card shows two codes, **1 · Join Wi-Fi** and
  **2 · Open SSP**, and the web app's **Connect a device** shows the join
  code too. Closing the control panel turns off a Wi-Fi SSP turned on.
  - **Linux:** one click (NetworkManager, `nmcli device wifi hotspot`, its
    own `SSP-Desktop-Hotspot` profile, removed again on Turn off).
  - **Windows:** one click through Mobile hotspot's WinRT API (PowerShell,
    the name and password passed as environment variables, never in the
    script). Windows only hotspots a connection it can share; when it says
    no, SSP opens the Mobile hotspot settings and says why. The wiki shows
    the one-time Loopback Adapter setup that makes it work with no network.
  - **Mac:** macOS has no way for an app to turn on Internet Sharing, so SSP
    opens System Settings › Sharing, shows the four steps, and shows the join
    code once you click **It's on**.
- The control panel looks for this computer's addresses again every few
  seconds while the server runs, so a hotspot coming up (or any network
  change) shows in the address and code without a restart.
- Wiki page **No Wi-Fi at the Venue** (the button per system, a phone's
  hotspot, a travel router, a Pi); screenshot `18-launcher-wifi.png`.
- Tests: `tests/test_hotspot.py` (16, no radio touched); a Windows CI job
  checks the PowerShell parses and its WinRT types load.

## [0.13.0] -- 2026-11-08

Paper charts: real PDFs to print, after Song Notation Tool's.

### Added

- **Paper charts as PDFs** (`server/paper.py`), made by SSP itself with the
  standard library: no PDF library, nothing to install. The PDF writer, the
  sizing rules, the floor sheet, black and white and the song carried inside
  its PDF come from
  [Song Notation Tool](https://github.com/giopas/song-notation-tool) (whose
  writer came from QLC+ Swiss Knife). A song's chart shows its tempo, length,
  how it starts (count-in or lead-in click) and its coloured shape, then each
  section: its name and first bar, a box per bar in groups of four to count
  along on, the new tempo where it changes, its count-in, and its hints (who
  each is for; for one player, the band-wide hints plus their own, marked
  "»"; "(voice memo)" where a hint has one). Sections never split across
  pages; a long song carries on with "(continued)" and page numbers.
- **Size: Fit to page** (the type grows until the page is full, or shrinks a
  little if that saves a page) or **Floor sheet** (the biggest type on one
  page; portrait or landscape, one or two columns, whichever is biggest;
  two columns put section names on a band across the top, with a rule
  between the columns).
- **Colour or Black & white** (grey bands, black names: less toner, and it
  photocopies well).
- **The set's running order** in the biggest type that fits on one page, as
  the first page of **Print set**, or on its own with **Set list only**.
- **Import a song from its PDF**: a song's chart carries the song (voice
  memos included) as an attachment, `song.ssp.json`, and the ⇡ import button
  takes the PDF.
- The print dialog remembers size, colour and what to print on each device;
  each choice also has a ⤓ download button.

### Changed

- **⎙ Print chart** is now **⎙ Paper chart**, and it and **⎙ Print set** open
  a PDF instead of a printable web page. `/export/song/<id>` and
  `/export/setlist/<id>` return the PDF (options `player`, `size=fit|floor`,
  `ink=color|bw`, `parts=all|list`, `download=1`); a link with a player who
  has since left the band gives the whole band's chart.
- README: a full **Install** section, after QLC+ Swiss Knife's: what to
  download for each computer; the first launch of an unsigned app (macOS
  right-click **Open**, **Open Anyway** on macOS 15+, or
  `xattr -dr com.apple.quarantine "/Applications/SSP.app"`; Windows
  SmartScreen); allowing SSP through the firewall so phones can connect;
  checking the download with `SHA256SUMS`; updating; uninstalling and where
  the settings live. Then running from the source code, a first-run guide
  with a "nobody can connect?" checklist, supported platforms, and privacy
  and security. The wiki's Getting Started and the release notes carry the
  same first-launch and firewall tips.
- `tools/publish_wiki.sh` publishes `wiki/` to the GitHub wiki in one
  command (`--check` only compares), and the release checklist now always
  ends with it.

## [0.12.1] -- 2026-11-08

The macOS apps, for the first time.

### Fixed

- **The macOS builds hung and never got published** (0.10.1 to 0.12.0 had
  Windows and Linux only). Finding this computer's Wi-Fi address looked up
  the Mac's own `.local` name, which can stall for minutes when nothing
  answers: it timed out the release builds, and could have frozen the
  Connect screen or the control panel at a venue with no internet. SSP now
  reads the addresses from `ifconfig` / `ip` / `ipconfig` (with a 3-second
  limit), as QLC+ Swiss Knife does, and lists a hotspot this computer runs
  (the Pi's `SSP-Band`, macOS Internet Sharing, Windows Mobile Hotspot)
  first.

### Changed

- The README starts with the app icon.
- Every push now also runs the server tests on a Mac (`tests.yml`), so a
  macOS-only problem shows up before a release. The release build runs the
  update tests too.

## [0.12.0] -- 2026-11-08

Updates from inside the app, the same way QLC+ Swiss Knife does it.

### Added

- **Update and restart** (`server/update.py`, ported from Swiss Knife's
  `core/update.py`): when the control panel opens it asks GitHub once for
  the latest release (cached 12 hours; offline is fine). A newer version
  shows a bar with **What's new** and **Update and restart**, which
  downloads this computer's package, checks it against the release's
  `SHA256SUMS`, unpacks it safely and swaps it in once SSP has closed (the
  Windows uninstaller is kept). Run from the source code, the bar says
  `git pull` instead. **Auto-check updates** at the bottom turns the check
  off, **Check for updates** asks on demand. Nothing about you or your band
  is sent; songs and settings live outside the app and are never touched.
- The macOS release also has a `.tar.gz` per chip, for the updater (a
  `.tar.gz` keeps the `.app`'s internal links, a `.zip` doesn't). The
  release build bundles `certifi` so the packaged app can reach GitHub.

### Note

- Coming from 0.11.0 or older, download this version by hand once (the
  `.dmg`, installer or `.zip` as before). From then on SSP offers each new
  version itself.

## [0.11.0] -- 2026-11-08

A real app icon, and a control panel that looks like the rest of SSP.

### Added

- **App icon**: the bar square from the editor (four beat dots) with beat 1
  lit white, on a dark tile. Used for the browser tab, the home-screen icon
  on phones and tablets, the macOS app, the Windows app and the control
  panel. `tools/make_icons.py` draws it and writes every size, so it can be
  redrawn in one go.
- **On stage** card in the control panel: each connected phone or tablet,
  with the player it's set to, and which song (and setlist) is on the live
  screens. The status in the top bar counts connected devices.
- The control panel shows the band's name and how many songs, setlists and
  players are in the folder it's serving.

### Changed

- The control panel is dark, in SSP's colors, laid out like QLC+ Swiss
  Knife: a top bar with the version and status, numbered cards (songs
  folder, server, connect, on stage), a bigger QR code with the address
  under it (click it to open), and a status line. The log is one click away
  (**Show log**) instead of always taking space. Same buttons, same
  behaviour.
- The macOS icon has the standard margin, so it's the same size as other
  apps in the Dock.

## [0.10.1] -- 2026-11-07

Downloadable apps for macOS, Windows and Linux.

### Added

- **Standalone apps on every release**, built on GitHub when a version tag
  is pushed (`.github/workflows/release.yml`, the same recipe as QLC+ Swiss
  Knife): `.dmg` for macOS (Apple silicon and Intel), an installer and a
  portable `.zip` for Windows, a `.tar.gz` for Linux, plus `SHA256SUMS`.
  Each build is smoke-tested before it's published; the Windows installer
  is installed, tested and uninstalled. The release text is that version's
  CHANGELOG section (`tools/release_notes.py`).
- The packaged app checks itself with `--smoke` and runs as a plain server
  with `--headless [server options]`. On Windows, `SSP Server.exe` (next to
  `SSP.exe`) is the console version for both.
- App icon for macOS, Windows and the control panel window
  (`packaging/icons/`).
- `.github/workflows/tests.yml`: the whole test suite, browser tests
  included, on every push.

### Changed

- The packaged program is called **SSP** (`SSP.app`, `SSP.exe`, `SSP/SSP`)
  instead of `SingleSongPlanner`. Settings and the default songs folder keep
  their old location, so nothing moves.
- A windowed Windows build no longer risks crashing on its own log output
  (no console to write to).

## [0.10.0] -- 2026-11-07

Making SSP easy for a drummer to switch to from a metronome app.

### Added

- **Click settings per device** (⚙ Click, in the live view and the
  editor): 8ths, 16ths or triplets; a spoken count-in ("one, two, three,
  four"; a two-bar count-in goes "one . two ., one two three four");
  left or right ear only (for a Y-splitter into in-ears); click for
  count-ins only; separate levels for beat 1, other beats and
  subdivisions; a timing nudge for Bluetooth. The rules live in
  `timeline.click_events()` / `timing.js clickEvents()` (parity-tested), so
  the live click and the downloads always match.
- **Click check**: "Test the click" plays a count-in and two bars with your
  settings on the spot, and shows what the device reports (engine running,
  stereo or mono, silent switch on iPhone/iPad). For checking a real
  splitter and in-ears before a gig.
- **Practice tracks**: click tracks follow the device's click settings;
  `⬇ Practice tracks` on a setlist downloads a `.zip` with one per song.
  New route `GET /api/setlists/<id>/clicks.zip`.
- **Solo mode**: "With the band" / "Solo: this device only" in the live
  view. In solo, Start/Stop/next/prev run on this device only, from its own
  copy of the songs (`GET /api/bundle`, refreshed on every change).
- **Keep playing if the server drops**: a device that loses the server
  mid-song switches to solo by itself and plays on (to the end of the song
  and through the setlist), then rejoins the band when stopped. Can be
  switched off (then the 0.9.1 behaviour: silence and a warning).
- **Big view** for drummers: huge tempo, bar in the section ("3/8") and
  bars to the next part. On by default when the device's player is a
  drummer.
- **Fast entry**: "Add songs" (the + by Songs) takes a title and BPM (and
  an optional length; four minutes otherwise) and makes a one-section
  song. "Paste a list" turns lines like "Song A - 124 - 3:45" (or columns
  from a spreadsheet) into songs and, optionally, a setlist in that order,
  reusing songs already there. Tap tempo there and in the editor.
  (`web/static/quick.js`, tested under Node.)
- **Feels like an app**: home-screen icon and web manifest (opens
  straight into the live view), and the screen stays on in the live view:
  Wake Lock where the browser allows it, otherwise a tiny muted looping
  video (the server now answers byte ranges, which Safari needs for that).
- **Raspberry Pi in one command**: `launchers/pi/install.sh` sets up the
  service on port 80 (`http://ssp.local/`), the host name, and optionally
  the Pi's own Wi-Fi (`--hotspot NAME PASSWORD`). With `--wifi-name` /
  `--wifi-password` (or `SSP_WIFI_*`), "Connect a device" shows a QR code
  that joins the Wi-Fi. `--qr` prints the address as a QR code in the
  terminal.
- Demo band: "Encore Jam", a song added the quick way, closes the Friday
  set.
- Wiki: new page "For Drummers"; Metronome, Tablet on Stage, Planning a
  Song and Raspberry Pi pages updated.

### Changed

- The click sound menu moved from the editor toolbar and the live footer
  into ⚙ Click; old saved sound/volume choices carry over.
- Addresses on port 80 are shown without ":80"; "Connect a device" also
  offers this computer's `.local` name.

### Not verifiable here

- iPad/iPhone (WebKit) click, keep-awake video and left/right routing:
  tested in Chromium only. Needs the real iPad with the splitter.
- `launchers/pi/install.sh`: checked with shellcheck and a dry run, not on
  a real Pi.

## [0.9.1] -- 2026-11-06

From the first real-device test (a Mac, an Android phone and an iPad).

### Fixed

- **No click on iPad/iPhone.** Safari starts its audio engine a moment
  after the tap, and the click waited for it, so a run started straight
  after the tap never got a click. The click now gets scheduled straight
  away. The click also asks Safari for "playback" audio, so silent mode no
  longer mutes it (Safari 16.4 or newer), and the sounds are built at the
  device's own sample rate.
- **Click kept going on Android with the screen off**, even after the song
  was stopped: Android keeps playing sound in the background but drops
  the page's connection, so "stop" never arrived. The click now stops as
  soon as the screen goes off or the page is hidden, and when you come
  back it picks the song up again if it's still playing. If a device hears
  nothing from the server for a couple of bars mid-song, it silences its
  click and says so.
- On a phone with nothing cued, the live view hid the list of songs and
  setlists to pick from.
- `--demo` now deletes its throwaway copy when the server stops.

### Added

- **Demo band from the web app**: "Try the demo band" (bottom of the
  sidebar) switches every connected device to a throwaway copy of the demo
  band, with a banner on every screen; "Back to my band" switches back.
  Your own songs aren't touched. Also works after the control panel's demo
  button, which now remembers the band folder to go back to.
- **Easier hints**: a labelled "+ Add hint" button on every section, a
  short explanation when a section has none, and "For the whole band" /
  "For Sam (Bass)" in the menu. In the live view, "+ Hint" adds one to the
  current section on the spot.
- The app's version shows at the bottom of the sidebar.

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
