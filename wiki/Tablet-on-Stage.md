# Tablet on Stage

This is what every musician sees once a song's planned and you're playing it. It's SSP's take on [QLC+ Swiss Knife](https://github.com/giopas/qlc-plus-swiss-knife-tool-script)'s "tablet on stage" idea: instead of one shared monitor everyone cranes their neck at, every player gets their own screen, following along.

## Getting a song up on every screen

Open **Live view** on each device (the green button in the sidebar, or one of the player QR codes from **Connect a device**). Then, from any device:

- on a song, press **▶ Go live**, or
- on a setlist, press **▶ Go live with this setlist**.

That song now sits ready on every live screen in the room, and the sidebar's Live view follows it. In a setlist, the ◀ ▶ arrows at the top move to the previous or next song, on everyone's screen at once.

![Ready to start, on the drummer's tablet](https://raw.githubusercontent.com/giopas/SSP---Song-and-Setlist-Planner/main/screenshots/05-live-ready-tablet.png)

## Start

Anyone can press **▶ Start**. Usually it's the drummer, but it doesn't have to be. SSP waits a moment so every device is ready, plays the count-in, and from then on every screen follows the song on its own: the current section in big letters, which bar you're on, the beat lighting up, and what's coming next ("Next: Verse 2 in 2 bars", in yellow when it's close). The screens stay in step because they share one clock; nobody has to press "next".

To start somewhere other than the top, tap a section in the list (or in the colored strip) before pressing Start. That's handy for running just the bridge at rehearsal.

**Stop** works from any device and stops everyone. At the end of a song in a setlist, the next song comes up ready, so the band is one tap from carrying on.

| Drummer's tablet | Bass player's phone |
|---|---|
| ![Tablet during a song](https://raw.githubusercontent.com/giopas/SSP---Song-and-Setlist-Planner/main/screenshots/07-live-tablet-drums.png) | ![Phone during a song](https://raw.githubusercontent.com/giopas/SSP---Song-and-Setlist-Planner/main/screenshots/08-live-phone-bass.png) |

## Big view (drummers)

**Big view** at the top swaps the song list for three huge numbers: the tempo, the bar you're on in this part ("3/8"), and how many bars until the next part (yellow when it's two or fewer). It's on by itself on a device held by a drummer, and anyone can switch it on or off.

## Solo: just this device

**With the band** at the top switches to **Solo: this device only**. Start, Stop and the song arrows then only work on your own device, from its own copy of the songs: for practising a song while the others tune, or when there's no server. Tap it again to rejoin the band. If the server drops off mid-song, a device switches to solo by itself and keeps playing (see [[For Drummers]]).

## Count-ins on screen

During a count-in the screen turns yellow and says which section it's counting into, with the beat lit up. A count-in in the middle of a song (after a stop, say) shows the same way.

![A count-in back into the last chorus](https://raw.githubusercontent.com/giopas/SSP---Song-and-Setlist-Planner/main/screenshots/09-live-count-in.png)

## Your hints, up front

The panel next to (or under) the big section name shows the hints for right now. Its **+ Hint** button adds a note to that section on the spot, handy at rehearsal ("we keep rushing here"). Yours come first, marked **For you**, then the ones for the whole band. Hints for other players stay out of the way ("+1 for other players"); tap that, or **Show everyone's hints**, to see them. Underneath, **Coming up** shows the next section's hints before you get there.

The full song is listed below, and scrolls along with the band. On a phone, there's only room for what matters: where you are, what's next, and your hints.

On a laptop or a shared screen set to "Whole band", every hint shows, each labelled with who it's for:

![The live view on a laptop](https://raw.githubusercontent.com/giopas/SSP---Song-and-Setlist-Planner/main/screenshots/06-live-laptop.png)

## The click

Each device can play its own metronome click, in time with everyone else. Tap **Click: tap to enable** once (browsers only allow sound after a tap), pick a sound and a volume. Nobody else hears your click unless you want them to. More in [[Metronome and Click Tracks]].

The click only plays while the device's screen is on and SSP is in front. Phones cut the connection to the server when the screen goes off, and a click that can't hear "stop" shouldn't keep going. Turn the screen back on and it picks the song up again.

## Foot pedals and keyboards

In the live view, the space bar starts and stops, and the arrow keys (or Page Up/Page Down) move through a setlist. That's what most Bluetooth page-turner pedals send, so a pedal works as a hands-free start button.

## Make it an app

On iPad/iPhone: Safari's Share → **Add to Home Screen**. On Android: Chrome's menu → **Add to Home screen**. SSP gets its own icon and opens full-screen, straight into the live view.

## Before the show

- Set each tablet's auto-lock to "never" (or a long time) for the gig. SSP can't keep a screen awake by itself over plain Wi-Fi.
- If the Wi-Fi drops for a moment, the device says "reconnecting" and catches up by itself when it's back. If it drops mid-song for more than a couple of bars, that device's click goes quiet ("Lost touch with the server") rather than clicking on blind.
- Plug the server in. A laptop going to sleep takes everyone's screens with it; a Raspberry Pi doesn't have that problem.

## Why not just a PDF on a tablet?

A PDF doesn't know what bar you're on, doesn't remind you of anything at the right moment, and doesn't update when the band changes the arrangement two minutes before the show. SSP is the band's one shared, live copy of the song. That's also why it never leaves your own Wi-Fi: a show is the worst moment for a laggy internet connection to get in the way of something this time-sensitive.
