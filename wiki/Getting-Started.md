# Getting Started

You don't need to install anything fancy, and nobody in the band needs an account. One computer is "the server", the machine that holds the songs. Everyone else just opens a web page.

## Step 1: Start SSP on one computer

This computer is home base for your band's songs. Pick whoever's laptop is usually around at rehearsal, or a cheap little computer like a Raspberry Pi that stays plugged in at your rehearsal space (see [[Running on a Raspberry Pi]]).

- **On a Mac:** double-click `start-macos.command` in the `launchers` folder (or the packaged `SSP - Song and Setlist Planner.app` if you have that).
- **On Windows:** double-click `start-windows.bat` (or the packaged `.exe`).
- **On Linux:** run `start-linux.sh` (or the packaged build).

A small window opens. That's the control panel, the only screen that looks like a normal computer program. Everything else happens in a browser, even on this same machine.

![The control panel, running](https://raw.githubusercontent.com/giopas/SSP---Song-and-Setlist-Planner/main/screenshots/13-launcher.png)

## Step 2: Tell it where to keep your songs

The control panel asks for a folder. Pick (or make) one folder for your band, maybe `MyBand Songs`. Every song and setlist goes in there as small text files, one per song, which you can back up or copy onto a USB stick. Next time, SSP remembers this folder (and a few recent ones).

**Just curious?** Press **Try the demo band** instead. It opens a made-up band, The Paper Lanterns, with six songs and two setlists, so you can click around a finished example. It's a throwaway copy: press the button again and it's back to how it started.

You can do the same from inside SSP, on any device: **Try the demo band** at the bottom of the sidebar. Everyone connected switches to the demo together (a yellow banner says so), so the whole band can try the live view on the demo songs. **Back to my band** in the banner brings your own songs back, untouched. Anything changed in the demo is thrown away.

## Step 3: Click "Start server"

The control panel shows a QR code and one or more addresses, something like:

```
http://192.168.1.20:8420/
```

That's what every phone and tablet in the room opens.

## Step 4: Get everyone on the same Wi-Fi

This is the one rule that matters: every device has to be on the same Wi-Fi network as the computer running SSP. Phone, tablet on a mic stand, whatever. Same Wi-Fi, same room.

SSP never needs the internet. Nothing about your set leaves the room, there's no account, and no cloud service can lag or drop out mid-song. If the venue has no Wi-Fi, a phone's hotspot works, or a Raspberry Pi can make its own network (see [[Running on a Raspberry Pi]]).

## Step 5: Scan the code on each phone or tablet

Point the phone's camera at the QR code, or type the address into Safari, Chrome, whatever's there. No app store, no download.

Inside SSP, the **Connect a device** button (bottom left) shows the same code, plus one code per band member that opens straight into that player's live view. Handy for setting up the drummer's tablet without anyone typing.

![Connect a device: one QR code per player](https://raw.githubusercontent.com/giopas/SSP---Song-and-Setlist-Planner/main/screenshots/04-connect.png)

## Step 6: Say who's holding the device

The first time a phone opens SSP, it asks who's using it. Pick yourself, and hints aimed at you stand out. "Whole band" is fine for a shared screen. You can change it any time from the button at the bottom of the sidebar or the top of the live view.

![Who's using this device?](https://raw.githubusercontent.com/giopas/SSP---Song-and-Setlist-Planner/main/screenshots/11-phone-who.png)

## One thing worth knowing

Anyone on that Wi-Fi who has the address can see and change everything. There's no separate login per band member. Treat the address the way you'd treat a whiteboard in your rehearsal room: anyone standing in the room can write on it. That's fine for a band that trusts each other in a room they control, which is what SSP is built for.

## Next

Head to **[[Planning a Song]]** to type up your first song.
