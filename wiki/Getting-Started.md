# Getting Started

You don't need to install anything fancy, and nobody in the band needs an account. You need one computer to be "the server," the one machine that holds the songs, and everyone else just opens a web page.

## Step 1: Start SSP on one computer

This computer is going to be home base for your band's songs. Pick whoever's laptop is usually around at rehearsal, or a cheap little computer like a Raspberry Pi that just stays plugged in at your rehearsal space.

- **On a Mac:** double-click `start-macos.command` (or open the packaged `SSP - Song and Setlist Planner.app` if you have that instead).
- **On Windows:** double-click `start-windows.bat` (or the packaged `.exe`).
- **On Linux:** run `start-linux.sh` (or the packaged build).

A small window pops up. That's the control panel, and it's the only screen that looks like a normal computer program; everything else happens in a browser, even on this same machine.

## Step 2: Tell it where to keep your songs

The control panel asks for a folder. Pick (or make) one folder for your band, maybe call it `MyBand Songs`. Every song and setlist you create gets saved there, as a bunch of small text files you could even back up or copy onto a USB stick. Next time you open SSP, it remembers this folder (and a few recent ones), so you won't have to pick it again.

## Step 3: Click "Start server"

The control panel shows you one or more addresses, something like:

```
http://192.168.1.42:8420/
```

That's the web address every phone and tablet in the room is going to type in (or scan a QR code for, once that's added). It's right there on screen whenever you need it, so there's no reason to memorize it.

## Step 4: Get everyone's phone on the same Wi-Fi

This is the one rule that actually matters: every device has to be on the same Wi-Fi network as the computer running SSP. A phone, a tablet on a mic stand, whatever. Same Wi-Fi, same room.

SSP is built to never need the internet, so nothing about your setlist leaves the room, there's no account to log into, and there's no cloud service that could lag or drop out mid-song. It's just your band's own little network, talking to itself. If your venue has no Wi-Fi, most phones can share their own hotspot instead, same idea in a smaller room.

## Step 5: Open the address on each phone or tablet

Type the address from Step 3 into any browser already on the phone, Safari, Chrome, whatever's there. No app store, no download. You should see SSP's song list, and you're in.

## One thing worth knowing

Right now, anyone on that Wi-Fi who has the address can see and change everything. There's no separate login per band member yet. Treat the address the way you'd treat a whiteboard in your rehearsal room: anyone standing in the room can write on it. That's fine for a band that trusts each other in a room they control, which is the situation SSP is built for.

## Next

Once everyone's connected, head to **[[Planning a Song]]** to start typing up your first song's structure.
