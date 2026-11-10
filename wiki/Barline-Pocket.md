# Barline Pocket

Barline normally runs on one computer in the rehearsal room, and every phone connects to it. That's right for rehearsals and gigs, but at home there's no server. **Barline Pocket** is the same app with no server: it runs on its own on your phone or tablet, keeps the band's songs on that device, and works with no internet.

Use it to practise with the click, look at a song's shape on the bus, or write notes ("walk up to the chorus on the A string") at home. Your notes go back to the band in a file, and the band's Barline merges them in.

| Pocket on a phone | Bringing Sam's notes back to the band |
|---|---|
| ![Barline Pocket on a phone](https://raw.githubusercontent.com/giopas/barline/main/screenshots/22-pocket-phone.png) | ![Importing a Pocket file: one song to merge, with a choice of structure](https://raw.githubusercontent.com/giopas/barline/main/screenshots/21-import-merge.png) |

## Open it

1. On the phone or tablet, open **[giopas.github.io/barline](https://giopas.github.io/barline/)**. It needs the internet this once, to load.
2. Add it to the home screen. On iPhone or iPad: Safari's Share button, then **Add to Home Screen**. On Android: Chrome's menu, then **Add to Home screen** (or **Install app**).
3. Open it from the home screen. From now on it works offline.

Nothing to buy or sign up for, and no app store: it's a web page that keeps itself on your device.

## Get the band's songs onto it

On the band's Barline (the laptop or the Pi):

- **Band → Export everything** makes one file with every song, setlist, player and voice memo.
- Or open a setlist and press **Export**: that setlist, its songs and the players.

Send the file to your phone: email it to yourself, AirDrop it, or put it in Files, iCloud Drive or Google Drive. Then in Pocket, press **Import a file** and pick it. The first time, Pocket asks who you are in the band, so it knows which hints are yours and whose name to put on the notes you write.

Want a look first? **Try the demo band** loads the made-up band from the screenshots.

## What works in Pocket

Everything about planning a song: sections, bars, tempo, count-ins, hints, voice memos (on a phone you can record one straight in), tags, setlists. The live view and the click work too, on your device only. Your own Start and Stop, no band to follow.

What Pocket can't do, because it has no server: connect other devices, print paper charts, or download click-track files. Do those on the band's Barline.

## Bring your notes back

In Pocket, **Band → Export everything** (on a phone this opens the share sheet: Mail, AirDrop, Files...). Then, on the band's Barline, press **⇡** next to Songs (or **Band → Import a file**) and pick that file.

A song the band's Barline already has is **merged**, not added a second time:

- **Hints come from both copies.** A note only you wrote is added. A note the band wrote while you were away stays. Nothing is deleted by a merge.
- **When both copies changed the same hint**, the one changed most recently wins. The import screen says when that happened.
- **Each hint says who wrote it**: "Sam (Bass)", next to the hint in the editor and in the live view. That's the player each device said it was being used by.
- **The structure comes from one copy.** If both copies have the same sections, bars and tempo, there's nothing to decide. If they differ (you made the intro four bars longer at home, say), the import screen shows the difference and asks which one to keep: **Keep the band's copy's** or **Keep the file's**. It doesn't guess. A hint whose section isn't in the structure you keep moves to the section with the same name, or the one in the same place.

The import screen lists every song in the file before anything changes: which ones are new, which will be merged (with "2 new hints from Sam (Bass)"), and which are already the same. Nothing happens until you press **Import**.

It works the other way too: export from the band's Barline after rehearsal and import that file in Pocket, and the band's latest changes merge into your copy.

## Keep a copy

Pocket keeps your songs in the phone's browser storage. That's reliable once Pocket is on the home screen, but if you clear the browser's data, or never open Pocket from the home screen for a long time, the phone may delete it. Export now and then: the file is your backup, and the band's Barline is the main copy anyway.

## For the curious

Pocket is the same web page as the band's Barline, built into a static site by `tools/build_pocket.py` and published to GitHub Pages with each release. Instead of asking a server, it answers its own requests in the page and stores everything in the browser (IndexedDB). It can't talk to the band's server directly: the server is plain `http://` on your Wi-Fi and Pocket is `https://`, and browsers don't allow that mix. That's why the way back is a file.
