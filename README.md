# SSP -- Song and Setlist Planner

Plan your set, and keep everyone in sync on stage.

SSP is a tool for bands and other music groups to work out a song's
structure together -- sections, tempo, count-ins, and reminders for each
player -- and then put it on every musician's own tablet or phone, all
moving through the song together, each with its own click.

![The editor: a song's sections, bars, tempo, count-ins and hints](screenshots/01-editor.png)

## What it does

- **Draft a song's structure as a band.** Verses, choruses, bridges, however
  you think about your songs. Bars and tempo per section (a half-time bridge
  can have its own BPM), a count-in, and hints: a note for the whole band,
  or one aimed at a single player ("Bass: root notes only here"). A hint can
  carry a short voice memo too.
- **Everyone edits the same copy.** Change a bar count on the laptop and the
  singer's phone updates a moment later. No refresh, no "which version is
  the latest".
- **Build setlists** and switch between songs instantly. In a hurry? Paste
  your set ("Song A - 124", one per line) or tap a tempo in: a title and a
  BPM is all the click needs.
- **Play it live.** Anyone can press Start -- usually the drummer. Every
  screen follows the song bar by bar, shows what's coming next, and puts
  *your* hints up front. Each device plays its own metronome click in time,
  set up its own way: subdivisions, a spoken count-in, one ear only for a
  Y-splitter into in-ears, a click for count-ins only. Drummers get a big
  view (tempo, bar, bars to the next part), and a device keeps playing on
  its own if the server drops mid-song.
- **Take it with you.** Download a practice click track (`.wav`) that follows
  the song's tempo changes (or a `.zip` of them for a whole setlist), print a chart for the whole band or one player,
  or export a song (voice memos included) as a single file for another band.

| On the drummer's tablet | On the bassist's phone |
|---|---|
| ![Live view on a tablet, as the drummer](screenshots/07-live-tablet-drums.png) | ![Live view on a phone, as the bass player](screenshots/08-live-phone-bass.png) |

![One tap on the tablet: tablet and phone follow the song together](screenshots/live.gif)

Coming from a metronome app? See [For Drummers](https://github.com/giopas/SSP---Song-and-Setlist-Planner/wiki/For-Drummers).

## How it works

One small server -- a laptop, a Raspberry Pi, or similar -- runs on your own
Wi-Fi and holds the whole band's songs and setlists. Everyone in the room
opens the same address in their phone or tablet's browser (or scans the QR
code the server shows). There's no app to install, no account, and no
internet connection involved at all.

![Edits on the laptop show up on the phone](screenshots/sync.gif)

**Local network only, on purpose.** SSP is never meant to be reachable over
the internet: a remote server is exactly the kind of lag and dropped
connection a rehearsal or a live set can't afford. The server makes no
outbound connections, sends no telemetry, and only reads and writes its own
data folder.

**Trust model:** anyone on the same Wi-Fi who has the address can read and
edit everything. There's no per-user login -- treat the address the way
you'd treat a whiteboard in your rehearsal room.

## Getting started

On a laptop, open the control panel:

- macOS: double-click `launchers/start-macos.command` (or a packaged
  `SSP - Song and Setlist Planner.app`, see below)
- Windows: double-click `launchers/start-windows.bat`
- Linux: run `launchers/start-linux.sh`

![The control panel](screenshots/13-launcher.png)

1. Pick (or create) a folder for your band's songs. The panel remembers it.
2. Click **Start server**. It shows the address and a QR code.
3. On each phone or tablet, join the same Wi-Fi and scan the code or type
   the address.
4. Start planning. Everything is saved as you go.

Want to look around first? **Try the demo band** (in the control panel, or
at the bottom of the sidebar in the app itself, where it switches every
connected device at once) loads a fictional band
(The Paper Lanterns) with seven songs and two setlists. It's a throwaway
copy, so nothing you do there sticks. From a terminal:
`python3 server/app.py --demo`.

On a Raspberry Pi with no screen, skip the control panel and run the server
as a service: see the wiki page *Running on a Raspberry Pi* and
`launchers/ssp.service`.

Requires Python 3.9 or newer. The server uses only Python's standard
library; the control panel also needs Tk (included with python.org's
installers for Windows and macOS; on Linux, `sudo apt install python3-tk`).

### Packaged builds

`packaging/` has a PyInstaller spec and a build script per OS that produce
a double-click-to-run build with nothing to install. Each has to be built on
its own OS (PyInstaller doesn't cross-compile).

## More

The [wiki](https://github.com/giopas/SSP---Song-and-Setlist-Planner/wiki)
walks through planning a song, using it on stage, the metronome, printing,
moving songs between setups, and running SSP on a Raspberry Pi.

| Setlists | The band | Connect a device |
|---|---|---|
| ![Setlist builder](screenshots/02-setlist.png) | ![Band members](screenshots/03-band.png) | ![QR code to connect](screenshots/04-connect.png) |

## For developers

- `python3 -m unittest discover -s tests` runs the tests (the browser tests
  need Playwright and are skipped without it).
- `python3 tools/make_demo_data.py` regenerates `demo/`;
  `python3 tools/shots.py` retakes every screenshot and GIF in
  `screenshots/` from the demo band.
- `tools/make_voice.sh` rebuilds the spoken count-in (`web/static/voice/`).
- `launchers/pi/install.sh` sets up a Raspberry Pi in one command (see the
  wiki's "Running on a Raspberry Pi").
- No build step: the web app in `web/static/` is plain HTML, CSS and
  JavaScript.

## Credit

SSP's song-structure focus takes its cue from
[song-map.com](https://song-map.com/). The "one local server, every device a
synced client" pattern, the per-player "tablet on stage" idea, the QR code
encoder and the click-track sounds are adapted from
[QLC+ Swiss Knife](https://github.com/giopas/qlc-plus-swiss-knife-tool-script).

## License

MIT -- free and open source, forever. See `LICENSE`. What's changed in each
version is in `CHANGELOG.md`.
