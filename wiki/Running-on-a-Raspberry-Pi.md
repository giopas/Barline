# Running on a Raspberry Pi

A laptop works, but it has to stay open, awake and plugged in for the whole show. A Raspberry Pi is a small, cheap computer that can live in your gig bag: plug it in, wait a minute, and SSP is running, with no screen and nobody's laptop involved.

Any Raspberry Pi from the last few years is plenty (a Pi 3, 4, 5 or Zero 2 W). These steps assume you're comfortable typing a few commands; you do them once.

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

The Pi can be its own Wi-Fi network: everyone joins it, and SSP works exactly the same with no router in sight. On current Raspberry Pi OS (which uses NetworkManager):

```
sudo nmcli device wifi hotspot ifname wlan0 ssid SSP-Band password "choose-a-password"
sudo nmcli connection modify Hotspot connection.autoconnect yes
```

Join `SSP-Band` from each device and open SSP as above. Note that while the Pi is a hotspot it isn't on your home Wi-Fi, and phones on it won't have internet (they may warn about that; tell them to stay connected anyway).

## Updating

```
cd ~/ssp && git pull
sudo systemctl restart ssp
```

Your songs are in `~/ssp-data`, outside the program folder, so updating never touches them. Back that folder up now and then.

## Safety

SSP is built for your own local network. Don't set up port forwarding on a router to reach it from the internet: there's no login, and anyone who could reach it could change everything.
