# Planning a Song

This is where the band agrees, in writing, how a song actually goes, so nobody's guessing on stage whether the bridge repeats twice or three times.

![Adding a section, setting its bars and tempo, aiming a hint, duplicating it](https://raw.githubusercontent.com/giopas/SSP---Song-and-Setlist-Planner/main/screenshots/planning.gif)

## Sections

A song is a list of sections, in order: intro, verse, chorus, bridge, outro, whatever your song has. Click **+ Add section** and give it a name. The sections show up as a row of colored blocks along the top, one color each, so you can see the shape of the song at a glance. Click a block to jump to that section.

Use the arrows on a section to move it up or down. If a section repeats exactly (the second chorus is the same as the first), click the duplicate button: SSP copies its bars, tempo, count-in and hints and puts the copy right after it.

## Bars

Every section needs a bar count: how many bars it lasts. If your verse is 16 bars, type 16. This number is what makes everything else work: it's how SSP knows when one section ends and the next begins. Each section shows its starting bar ("bar 17") so you can check the arrangement against a recording.

The bars are drawn as little squares, four dots in each for the four beats.

## Tempo (BPM)

Every song has a default BPM. Most sections just use it. If one section is deliberately slower or faster, a half-time bridge say, give that section its own BPM and SSP uses it just for those bars. The live view and the metronome both follow the change.

## Count-ins

A count-in is extra bars played *before* a section, so everyone comes in together. Pick a style per section:

- **sticks**: the drummer clicks the sticks
- **click**: a metronome click
- **verbal**: someone counts out loud ("one, two, three, four")
- **none**: straight in

and how many bars. A count-in doesn't eat into the section: a 4-bar intro with a 1-bar count-in plays five bars in total. They show as dashed squares in front of the section.

Count-ins aren't just for the top of a song. After a dead stop in the middle, give the next section a count-in, and the live view counts the band back in.

When you start a song from the live view, there's always a count-in first, even if the first section has none set: one bar of click, so nobody's surprised by bar 1.

Press the ♫ button on a section to hear its count-in and first two bars on this device, or **Preview click** at the top for the whole song.

## Hints

A hint is a short note on a section: a reminder the band (or one player) needs right then. "Root notes only here", "watch for the tempo drop", "everyone in on the 'and'".

Click **+** under Hints on any section. The menu next to each hint picks who it's for: the whole band, or one player. A hint for one player stands out on that player's screen (with "For you" on it) and stays out of everyone else's way, though anyone can still choose to see it.

Players are set up on the **Band** page: a name and an instrument each.

![The band](https://raw.githubusercontent.com/giopas/SSP---Song-and-Setlist-Planner/main/screenshots/03-band.png)

### Voice memos

Some things are easier to hear than read: how a fill goes, a sung phrase, "count it like this". The 🎤 button on a hint attaches a short recording (up to 30 seconds) that anyone can play back with ▶.

On the computer running the server, the button records straight from the microphone. Phones and tablets connected over Wi-Fi can't do that (browsers only allow the microphone on secure or local pages), so there the button lets you pick an audio file instead: record it with the phone's voice memo app first, then attach it.

## Everyone at once

Everybody connected sees the same song, and changes show up on every screen within a moment. If two people change the same song at the same moment, the last one saved wins. SSP tells you when someone else changed the song you're looking at.

![The laptop edits, the phone follows](https://raw.githubusercontent.com/giopas/SSP---Song-and-Setlist-Planner/main/screenshots/sync.gif)

## Building a setlist

Click **+** next to Setlists. Add songs from "All songs" on the right, and use the arrows to put them in playing order. The setlist shows how long the set runs, count-ins included. Switching between songs and setlists is instant; there's no loading screen.

![A setlist](https://raw.githubusercontent.com/giopas/SSP---Song-and-Setlist-Planner/main/screenshots/02-setlist.png)

## Next

When a song's ready, see **[[Tablet on Stage]]** for playing it live.
