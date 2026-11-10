#!/usr/bin/env bash
# Barline on a Raspberry Pi, in one command: a box in the gig bag that boots
# straight into Barline (and, if you like, its own Wi-Fi), so on stage nobody
# sets anything up -- join the Wi-Fi, open http://ssp.local/, play.
#
# Run it once, on the Pi, from the folder Barline was cloned into:
#
#   sudo ./launchers/pi/install.sh                       # Barline on the Pi's current network
#   sudo ./launchers/pi/install.sh --hotspot Barline-Band "a-password"   # ...and its own Wi-Fi when needed
#
# Options:
#   --hotspot NAME PASSWORD  the Pi's own Wi-Fi network (8+ character password),
#                            started at boot only when the Pi finds no network
#                            it knows (home, rehearsal room, a cable)
#   --hotspot-always         with --hotspot: start it on every boot instead
#   --user NAME              who Barline runs as (default: whoever ran sudo)
#   --data DIR               where the band's songs live (default: ~NAME/ssp-data)
#   --port N                 web port (default 80, so the address needs no number)
#   --hostname NAME          the Pi's network name (default: ssp -> http://ssp.local/)
#   --dry-run                print what would be done, change nothing
#
# Safe to run again (e.g. to switch the hotspot on or off, or after moving
# Barline): running it without --hotspot removes the Pi's own Wi-Fi.
# Undo: sudo systemctl disable --now ssp ssp-wifi
#       sudo rm /etc/systemd/system/ssp.service /etc/systemd/system/ssp-wifi.service
#       sudo nmcli connection delete SSP-Hotspot
#
# See the wiki page "Running on a Raspberry Pi" for what each step does.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_USER="${SUDO_USER:-pi}"
DATA=""
PORT=80
HOST_NAME="ssp"
HOTSPOT_NAME=""
HOTSPOT_PASS=""
HOTSPOT_ALWAYS=0
WIFI_WAIT=40
DRY=0

die() { echo "ssp install: $*" >&2; exit 1; }
say() { echo "==> $*"; }
run() {
  if [ "$DRY" = 1 ]; then echo "    (dry run) $*"; else "$@"; fi
}

while [ $# -gt 0 ]; do
  case "$1" in
    --hotspot) [ $# -ge 3 ] || die "--hotspot needs a name and a password"
               HOTSPOT_NAME="$2"; HOTSPOT_PASS="$3"; shift 3 ;;
    --hotspot-always) HOTSPOT_ALWAYS=1; shift ;;
    --user) RUN_USER="${2:?--user needs a name}"; shift 2 ;;
    --data) DATA="${2:?--data needs a folder}"; shift 2 ;;
    --port) PORT="${2:?--port needs a number}"; shift 2 ;;
    --hostname) HOST_NAME="${2:?--hostname needs a name}"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,29p' "$0"; exit 0 ;;
    *) die "unknown option: $1 (try --help)" ;;
  esac
done

[ "$DRY" = 1 ] || [ "$(id -u)" = 0 ] || die "run it with sudo"
[ -f "$REPO/server/app.py" ] || die "can't find server/app.py next to this script ($REPO)"
id "$RUN_USER" >/dev/null 2>&1 || die "no user called $RUN_USER (use --user)"
case "$PORT" in ''|*[!0-9]*) die "--port must be a number" ;; esac
[[ "$HOST_NAME" =~ ^[a-zA-Z0-9-]{1,40}$ ]] || die "--hostname: letters, digits and - only"
if [ -n "$HOTSPOT_NAME" ]; then
  [ "${#HOTSPOT_PASS}" -ge 8 ] || die "the hotspot password needs at least 8 characters"
  [ "${#HOTSPOT_NAME}" -le 32 ] || die "the hotspot name is at most 32 characters"
elif [ "$HOTSPOT_ALWAYS" = 1 ]; then
  die "--hotspot-always goes with --hotspot NAME PASSWORD"
fi
HOME_DIR="$(getent passwd "$RUN_USER" | cut -d: -f6)"
DATA="${DATA:-$HOME_DIR/ssp-data}"

say "Installing what Barline needs (python3, and avahi so ssp.local works)"
if command -v apt-get >/dev/null 2>&1; then
  if [ "$DRY" = 1 ]; then run apt-get install -y python3 avahi-daemon; else apt-get install -y python3 avahi-daemon >/dev/null; fi
else
  command -v python3 >/dev/null || die "python3 is missing"
fi

say "Songs folder: $DATA"
run mkdir -p "$DATA"
run chown "$RUN_USER": "$DATA"

if [ "$(hostname)" != "$HOST_NAME" ]; then
  say "Naming the Pi '$HOST_NAME' (address http://$HOST_NAME.local/)"
  if command -v hostnamectl >/dev/null 2>&1; then run hostnamectl set-hostname "$HOST_NAME"
  else run sh -c "echo '$HOST_NAME' > /etc/hostname"; fi
  if [ "$DRY" = 0 ] && grep -q '^127\.0\.1\.1' /etc/hosts; then
    sed -i "s/^127\.0\.1\.1.*/127.0.1.1\t$HOST_NAME/" /etc/hosts
  fi
fi

WIFI_UNIT=/etc/systemd/system/ssp-wifi.service
if [ -n "$HOTSPOT_NAME" ]; then
  [ "$DRY" = 1 ] || command -v nmcli >/dev/null 2>&1 || die "the hotspot needs NetworkManager (current Raspberry Pi OS has it)"
  if [ "$HOTSPOT_ALWAYS" = 1 ]; then
    say "Setting up the Wi-Fi '$HOTSPOT_NAME' (starts on every boot)"
    AUTO=yes
  else
    say "Setting up the Wi-Fi '$HOTSPOT_NAME' (starts at boot when the Pi finds no network it knows)"
    AUTO=no
  fi
  if nmcli -t -f NAME connection show 2>/dev/null | grep -qx SSP-Hotspot; then
    run nmcli connection delete SSP-Hotspot
  fi
  run nmcli connection add type wifi ifname wlan0 con-name SSP-Hotspot autoconnect "$AUTO" ssid "$HOTSPOT_NAME" \
    802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared ipv6.method ignore \
    wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$HOTSPOT_PASS" connection.autoconnect-priority 100

  if [ "$HOTSPOT_ALWAYS" = 1 ]; then
    if [ -f "$WIFI_UNIT" ]; then
      run systemctl disable ssp-wifi >/dev/null 2>&1 || true
      run rm -f "$WIFI_UNIT"
    fi
  else
    # a one-shot at boot: wait for a known network, else start SSP-Hotspot
    # (launchers/pi/wifi-fallback.sh)
    WIFI_CONTENT="[Unit]
Description=Barline - the Pi's own Wi-Fi when there's no known network
After=NetworkManager.service
Wants=NetworkManager.service

[Service]
# simple, not oneshot: the wait never holds up the rest of the boot (Barline
# itself listens on every address, so it doesn't need to wait either)
Type=simple
Environment=SSP_WIFI_WAIT=$WIFI_WAIT
ExecStart=/bin/bash \"$REPO/launchers/pi/wifi-fallback.sh\"

[Install]
WantedBy=multi-user.target
"
    if [ "$DRY" = 1 ]; then
      echo "    (dry run) would write $WIFI_UNIT:"; printf '%s\n' "$WIFI_CONTENT"
    else
      printf '%s' "$WIFI_CONTENT" > "$WIFI_UNIT"
    fi
    run systemctl daemon-reload
    run systemctl enable ssp-wifi >/dev/null 2>&1
  fi
else
  # no --hotspot: no own Wi-Fi (removes one an earlier run set up)
  if nmcli -t -f NAME connection show 2>/dev/null | grep -qx SSP-Hotspot; then
    say "Removing the Pi's own Wi-Fi (run again with --hotspot to bring it back)"
    run nmcli connection delete SSP-Hotspot
  fi
  if [ -f "$WIFI_UNIT" ]; then
    run systemctl disable ssp-wifi >/dev/null 2>&1 || true
    run rm -f "$WIFI_UNIT"
  fi
fi

# the Wi-Fi name/password go in a root-only file, read by the service
# (so Barline can show a "join the Wi-Fi" QR code), never on its command line
ENV_FILE=/etc/ssp.env
esc() { local v="${1//\\/\\\\}"; printf '%s' "${v//\"/\\\"}"; }
ENV_CONTENT="SSP_WIFI_NAME=\"$(esc "$HOTSPOT_NAME")\"
SSP_WIFI_PASSWORD=\"$(esc "$HOTSPOT_PASS")\"
"
if [ "$DRY" = 1 ]; then
  echo "    (dry run) would write $ENV_FILE (Wi-Fi name and password, root only)"
else
  ( umask 077; printf '%s' "$ENV_CONTENT" > "$ENV_FILE" )
fi

say "Starting Barline on every boot (systemd service 'ssp')"
UNIT=/etc/systemd/system/ssp.service
CONTENT="[Unit]
Description=Barline - Song and Setlist Planner server
After=network-online.target avahi-daemon.service
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$REPO/server
EnvironmentFile=-/etc/ssp.env
ExecStart=/usr/bin/env python3 \"$REPO/server/app.py\" --port $PORT --data \"$DATA\"
Restart=always
RestartSec=2
# port 80 without running as root
AmbientCapabilities=CAP_NET_BIND_SERVICE
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
"
if [ "$DRY" = 1 ]; then
  echo "    (dry run) would write $UNIT:"; printf '%s\n' "$CONTENT"
else
  printf '%s' "$CONTENT" > "$UNIT"
fi
run systemctl daemon-reload
run systemctl enable ssp >/dev/null 2>&1
run systemctl restart ssp
run systemctl restart avahi-daemon || true

URL="http://$HOST_NAME.local/"
[ "$PORT" = 80 ] || URL="http://$HOST_NAME.local:$PORT/"
echo
echo "Barline is installed."
if [ -n "$HOTSPOT_NAME" ]; then
  if [ "$HOTSPOT_ALWAYS" = 1 ]; then
    echo "  The Pi's own Wi-Fi '$HOTSPOT_NAME' starts on every boot (reboot now, or: sudo nmcli connection up SSP-Hotspot)."
    echo "  Careful: while it's up, the Pi is off your home Wi-Fi; switch back with"
    echo "  sudo nmcli connection down SSP-Hotspot"
  else
    echo "  At boot the Pi joins a network it knows; with none around (after ${WIFI_WAIT}s) it makes"
    echo "  its own Wi-Fi '$HOTSPOT_NAME'. Try it now: sudo nmcli connection up SSP-Hotspot"
    echo "  (and back: sudo nmcli connection down SSP-Hotspot). Log: journalctl -u ssp-wifi"
  fi
  HOT_URL="http://10.42.0.1/"
  [ "$PORT" = 80 ] || HOT_URL="http://10.42.0.1:$PORT/"
  echo "  On that Wi-Fi, open $URL (or $HOT_URL)"
else
  echo "  Open $URL on any phone or tablet on this network."
fi
echo "  'Connect a device' inside Barline shows QR codes (including one to join the Wi-Fi)."
if [ "$DRY" = 0 ]; then
  ( cd "$REPO/server" && python3 -c "import qr, sys; print(qr.terminal(sys.argv[1]))" "$URL" ) || true
fi
echo "  Status: systemctl status ssp     Log: journalctl -u ssp -f"
