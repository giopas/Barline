# Tablet on Stage

This page is about what every musician actually sees once a song's planned and you're playing it. It's SSP's take on [QLC+ Swiss Knife](https://github.com/giopas/qlc-plus-swiss-knife-tool-script)'s own "tablet on stage" idea: instead of one shared monitor everyone has to crane their neck at, every player gets their own screen, already open, already following along.

## What works right now (v0.1)

Every phone or tablet connected to SSP is looking at the exact same page, live. If anyone changes something, the singer checking the set before a show, or the guitarist tweaking a bar count at rehearsal, every other screen in the room updates right behind it. There's no refresh button to hunt for.

So even today, propping a tablet on a mic stand and opening the current song already beats a paper chart taped to an amp: the section names, bar counts, and hints are all right there, in one glance, within your own hand's reach.

## What's coming in the next few versions

A few pieces of the full "tablet on stage" picture are planned but not built yet. They're on the roadmap, not hidden somewhere in the app:

- A metronome you can actually hear. Each section's tempo already lives in the plan; next up is making SSP play that tempo out loud, sticks, click, or a verbal count, through the device itself.
- Everyone scrolling together, live. Right now, following along is still manual: you watch the bars and sections the way you'd watch a chart. The plan is for the server to track where the band actually is in the song and move every screen in time with it on its own, so nobody has to count bars in their head while also playing.
- Hints aimed at just you. A hint written for "bass only" will show up clearly on the bassist's screen and stay out of everyone else's way, instead of every hint going to everybody.

Check [claude/WORKPLAN.md](https://github.com/giopas/single-song-planner/blob/main/claude/WORKPLAN.md) for which version each of these lands in.

## Why it's not just a PDF on a tablet

A PDF chart doesn't know what bar you're on, doesn't remind you of anything at the right second, and doesn't update when the band changes the arrangement two minutes before a show. SSP is built to be the band's one shared, live source of truth for the song. That's also why it deliberately never leaves your own Wi-Fi: a show is the worst possible moment for a laggy internet connection to get in the way of something this time-sensitive.
