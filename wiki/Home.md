# SSP: Song and Setlist Planner Wiki

SSP helps a band plan how a song goes: which part comes next, how many bars it lasts, what tempo to play it at, and what to remind each other right before it happens. It then puts that plan on every phone or tablet on stage, scrolling in time with the song.

Think of it as a shared whiteboard for your set, except it's on everyone's phone instead of taped to an amp. One small program runs on a laptop (or a tiny computer like a Raspberry Pi) backstage or in the rehearsal room, and every band member's phone or tablet just opens a web page to see it. No app to install, no account, no internet needed.

It's built with two things in mind:

- **[song-map.com](https://song-map.com/)**, for the idea that a song's shape (verse, chorus, bridge, how long each part is) deserves its own simple tool, instead of being buried in a PDF chart or a messy group chat.
- **[QLC+ Swiss Knife](https://github.com/giopas/qlc-plus-swiss-knife-tool-script)**'s "Tablet on stage" idea: every musician gets their own screen that follows the show live, instead of everyone squinting at one shared monitor.

## Pages

- **[[Getting Started]]**: install nothing, pick a folder, start the server, get every phone connected. Ten minutes, start to finish.
- **[[Planning a Song]]**: how to type up a song's sections, bars, tempo, count-ins, and hints so the band agrees on the plan before you play a single note.
- **[[Tablet on Stage]]**: what it looks like once you're actually playing. Following along live, the metronome click, and hints showing up right when you need them.

## Elsewhere in the repo

These live as plain files in the repo, not as wiki pages, since they're meant for someone looking at the code rather than a musician looking for help:

- [README.md](https://github.com/giopas/single-song-planner/blob/main/README.md): the short version of what SSP does and how to start it
- [CHANGELOG.md](https://github.com/giopas/single-song-planner/blob/main/CHANGELOG.md): what changed in each version
- [claude/WORKPLAN.md](https://github.com/giopas/single-song-planner/blob/main/claude/WORKPLAN.md): the roadmap, what's built and what's next
- [claude/PROJECT_CHARTER.md](https://github.com/giopas/single-song-planner/blob/main/claude/PROJECT_CHARTER.md): the ground rules this project is built on
