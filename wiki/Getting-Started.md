# Getting Started

You don't need to install anything fancy, and nobody in the band needs an account. One computer is "the server", the machine that holds the songs. Everyone else just opens a web page.

## Step 1: Start SSP on one computer

This computer is home base for your band's songs. Pick whoever's laptop is usually around at rehearsal, or a cheap little computer like a Raspberry Pi that stays plugged in at your rehearsal space (see [[Running on a Raspberry Pi]]).

The easy way: download SSP for your computer from the [latest release](https://github.com/giopas/SSP---Song-and-Setlist-Planner/releases/latest). Nothing else to install.

- **On a Mac:** the `.dmg` (`arm64` for M1 and newer Macs, `x86_64` for older Intel ones). Open it and drag **SSP** into Applications. The first time, right-click SSP and choose **Open**: it isn't signed by Apple yet, so macOS asks once. On macOS 15 or newer, if that doesn't work, go to **System Settings › Privacy & Security** and click **Open Anyway**. If it says SSP "is damaged", that's just the download quarantine: open Terminal and paste `xattr -dr com.apple.quarantine "/Applications/SSP.app"`.
- **On Windows:** the `-setup.exe`. It installs just for you (no admin password) and puts SSP in the Start menu. If Windows says "protected your PC", click **More info**, then **Run anyway**. The `.zip` works too, with no install.
- **On Linux:** unpack the `.tar.gz` and run `SSP/SSP`.

Got the source code instead (from GitHub, or for a Raspberry Pi)? Double-click `start-macos.command` or `start-windows.bat` in the `launchers` folder, or run `start-linux.sh`. Updating the app never touches your songs: they live in their own folder.

A small window opens. That's the control panel, the only screen that looks like a normal computer program. Everything else happens in a browser, even on this same machine.

![The control panel, running](https://raw.githubusercontent.com/giopas/SSP---Song-and-Setlist-Planner/main/screenshots/13-launcher.png)

## Step 2: Tell it where to keep your songs

The control panel asks for a folder. Pick (or make) one folder for your band, maybe `MyBand Songs`. Every song and setlist goes in there as small text files, one per song, which you can back up or copy onto a USB stick. Next time, SSP remembers this folder (and a few recent ones).

**Just curious?** Press **Try the demo band** instead. It opens a made-up band, The Paper Lanterns, with seven songs and two setlists, so you can click around a finished example. It's a throwaway copy: press the button again and it's back to how it started.

You can do the same from inside SSP, on any device: **Try the demo band** at the bottom of the sidebar. Everyone connected switches to the demo together (a yellow banner says so), so the whole band can try the live view on the demo songs. **Back to my band** in the banner brings your own songs back, untouched. Anything changed in the demo is thrown away.

## Step 3: Click "Start server"

The control panel shows a QR code and one or more addresses, something like:

```
http://192.168.1.20:8420/
```

That's what every phone and tablet in the room opens. Click the address to open it on this computer too.

Underneath, the **On stage** card fills in as people connect: one chip per phone or tablet, with the player it's set to ("Sam · Bass"), and the song that's on the live screens. The top-right corner says how many devices are connected. If something looks wrong, **Show log** at the bottom opens the server's log.

The first time you press **Start server**, your computer may ask whether SSP can accept connections or find devices on your network (or Windows shows a firewall box). Say **Allow** (on Windows, tick **Private networks**), or the phones can't get in.

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

## Keeping SSP up to date

When a new version comes out, a blue bar appears at the top of the control panel: **SSP 0.13.0 is out**. **What's new** shows what changed; **Update and restart** downloads it, checks it isn't damaged or tampered with, closes SSP and opens the new one. Your songs, setlists and settings stay exactly where they are. If the server was running, press **Start server** again and the phones and tablets reconnect by themselves.

SSP looks for a new version once when the control panel opens. That's the only time it talks to the internet, it sends nothing about you or your band, and with no internet (at a venue, say) it just stays quiet. To turn it off, click **Auto-check updates: on** at the bottom; **Check for updates** asks whenever you like.

Running SSP from the source code? The bar tells you to run `git pull` in the SSP folder instead. On a Raspberry Pi, see "Updating" in [[Running on a Raspberry Pi]].

## Next

Head to **[[Planning a Song]]** to type up your first song.
