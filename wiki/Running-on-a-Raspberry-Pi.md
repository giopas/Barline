# Running on a Raspberry Pi

A laptop works, but it has to stay open, awake and plugged in for the whole show. A Raspberry Pi is a small, cheap computer that can live in your gig bag: plug it in, wait a minute, and SSP is running, with no screen and nobody's laptop involved.

Any Raspberry Pi from the last few years is plenty (a Pi 3, 4, 5 or Zero 2 W). These steps assume you're comfortable typing a few commands; you do them once.

## The one-command way

Once SSP is on the Pi (steps 1 and 2 below), one command does steps 3 to 5 for you:

```
cd ~/ssp
sudo ./launchers/pi/install.sh --hotspot SSP-Band "choose-a-password"
```

It starts SSP on every boot, on the plain address **`http://ssp.local/`** (no `:8420` to remember), and gives the Pi its own Wi-Fi called `SSP-Band` **for when it's needed**. At every boot the Pi first looks for a network it knows (your home Wi-Fi, the rehearsal room's, a network cable). If it finds one, it joins it as usual, and the band opens SSP there. If it finds none within about 40 seconds (a venue with no network, or one the Pi has never seen), it makes `SSP-Band` instead. So the Pi in your gig bag *is* the setup: plug it in, wait a minute, join `SSP-Band`, open `http://ssp.local/`. At home it stays on your Wi-Fi, ready for updates.

**Connect a device** inside SSP shows a QR code that joins `SSP-Band` (only while the Pi is actually running it), and another that opens SSP. `--help` lists the other options (user, songs folder, port, name); running it again is safe.

- **Always its own Wi-Fi**, never your home one: add `--hotspot-always` (the behaviour before 0.14).
- **Never its own Wi-Fi:** run the installer again without `--hotspot`; that removes it.
- **Want `SSP-Band` right now** (say, the venue's Wi-Fi is known but keeps devices apart): `sudo nmcli connection up SSP-Hotspot`. Back to a known network: `sudo nmcli connection down SSP-Hotspot`.
- **What did it decide at boot?** `journalctl -u ssp-wifi`.

The rest of this page is the same thing, step by step, for anyone who'd rather know what each piece does.

## 1. Set up the Pi

Use Raspberry Pi Imager to write **Raspberry Pi OS Lite** to a microSD card. In the Imager's settings, set a username (these steps use `pi`), your Wi-Fi, turn on SSH, and set the hostname to `ssp`. Put the card in, power the Pi on, and from your computer:

```
ssh pi@ssp.local
```

## 2. Get SSP

```
sudo apt update
sudo apt install -y git python3
git clone https://github.com/giopas/SSP---Song-and-Setlist-Planner.git ~/ssp
mkdir -p ~/ssp-data
```

Try it once by hand:

```
python3 ~/ssp/server/app.py --data ~/ssp-data
```

It prints the addresses to open. Open one on your phone, check that it works, then press Ctrl+C to stop it. (`--demo` instead of `--data ~/ssp-data` shows the demo band.)

To bring songs over from a laptop, copy its data folder into `~/ssp-data` (for example with `scp -r`), or export songs one by one and import them on the Pi (see [[Printing and Moving Songs]]).

## 3. Start it automatically

```
sudo cp ~/ssp/launchers/ssp.service /etc/systemd/system/ssp.service
sudo systemctl daemon-reload
sudo systemctl enable --now ssp
```

From now on, SSP starts every time the Pi powers on, and starts again by itself if anything goes wrong. If your username isn't `pi`, edit the `User=` line and the paths in that file first.

- Is it running? `systemctl status ssp`
- What's it doing? `journalctl -u ssp -f`

## 4. Open it

Because the hostname is `ssp`, most phones, tablets and laptops can open:

```
http://ssp.local:8420/
```

If a device doesn't find that name, use the number address: `hostname -I` on the Pi shows it, and so does the **Connect a device** button inside SSP (with a QR code).

## 5. No Wi-Fi at the venue? Let the Pi make its own

The Pi can be its own Wi-Fi network: everyone joins it, and SSP works exactly the same with no router in sight. The installer above does this for you (`--hotspot`), and only when there's no known network around: that's the easy way. By hand, on current Raspberry Pi OS (which uses NetworkManager), an always-on hotspot is:

```
sudo nmcli device wifi hotspot ifname wlan0 ssid SSP-Band password "choose-a-password"
sudo nmcli connection modify Hotspot connection.autoconnect yes
```

The "only when needed" part is `launchers/pi/wifi-fallback.sh`, which the installer runs at boot as the `ssp-wifi` service: it waits for a known network and starts the hotspot if none comes. Join `SSP-Band` from each device and open SSP as above. Note that while the Pi is a hotspot it isn't on your home Wi-Fi, and phones on it won't have internet (they may warn about that; tell them to stay connected anyway).

## Updating

```
cd ~/ssp && git pull
sudo systemctl restart ssp
```

Your songs are in `~/ssp-data`, outside the program folder, so updating never touches them. Back that folder up now and then.

## Safety

SSP is built for your own local network. Don't set up port forwarding on a router to reach it from the internet: there's no login, and anyone who could reach it could change everything.
