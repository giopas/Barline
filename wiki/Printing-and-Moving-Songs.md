# Printing and Moving Songs

## Paper charts

Sometimes paper is the backup you want. **Print chart** on a song (or **Print set** on a setlist) asks who it's for:

- **Whole band**: every section, every hint, each with who it's for.
- **One player**: the hints for the whole band plus that player's own, marked with an arrow. Other players' hints are left off.

It opens a plain, light page with the song's colored shape at the top, then each section's starting bar, length, tempo, count-in and hints. Print it from the browser, or choose "Save as PDF". A setlist prints a cover page with the running order and total time, then one page per song.

![The bass player's chart](https://raw.githubusercontent.com/giopas/SSP---Song-and-Setlist-Planner/main/screenshots/10-print-chart-bass.png)

## Taking a song to another setup

Every song is one small file in your songs folder, so you can copy it to another SSP by hand. That works, except for voice memos, which live in their own folder.

The easy way is **Export** on the song: it downloads one `.ssp.json` file with the song *and* its voice memos inside. On the other SSP, click the ⇡ button next to Songs and pick the file. The song arrives as a new song; it never overwrites anything that's already there, even if it's the same song imported twice.

That's also how to share a song's structure with another band, or keep a backup of one song before a big rearrangement.

## Backing up everything

Copy the whole data folder (the one you picked in the control panel). That's everything: band, songs, setlists, voice memos. To restore, point the control panel at the copy.
