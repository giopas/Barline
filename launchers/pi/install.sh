#!/usr/bin/env bash
# SSP on a Raspberry Pi, in one command: a box in the gig bag that boots
# straight into SSP (and, if you like, its own Wi-Fi), so on stage nobody
# sets anything up -- join the Wi-Fi, open http://ssp.local/, play.
#
# Run it once, on the Pi, from the folder SSP was cloned into:
#
#   sudo ./launchers/pi/install.sh                       # SSP on the Pi's current network
#   sudo ./launchers/pi/install.sh --hotspot SSP-Band "a-password"   # ...and its own Wi-Fi
#
# Options:
#   --hotspot NAME PASSWORD  make the Pi its own Wi-Fi network (8+ character password)
#   --user NAME              who SSP runs as (default: whoever ran sudo)
#   --data DIR               where the band's songs live (default: ~NAME/ssp-data)
#   --port N                 web port (default 80, so the address needs no number)
#   --hostname NAME          the Pi's network name (default: ssp -> http://ssp.local/)
#   --dry-run                print what would be done, change nothing
#
# Safe to run again (e.g. to switch the hotspot on, or after moving SSP).
# Undo: sudo systemctl disable --now ssp; sudo rm /etc/systemd/system/ssp.service
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
    --user) RUN_USER="${2:?--user needs a name}"; shift 2 ;;
    --data) DATA="${2:?--data needs a folder}"; shift 2 ;;
    --port) PORT="${2:?--port needs a number}"; shift 2 ;;
    --hostname) HOST_NAME="${2:?--hostname needs a name}"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
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
fi
HOME_DIR="$(getent passwd "$RUN_USER" | cut -d: -f6)"
DATA="${DATA:-$HOME_DIR/ssp-data}"

say "Installing what SSP needs (python3, and avahi so ssp.local works)"
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

if [ -n "$HOTSPOT_NAME" ]; then
  command -v nmcli >/dev/null 2>&1 || die "the hotspot needs NetworkManager (current Raspberry Pi OS has it)"
  say "Setting up the Wi-Fi '$HOTSPOT_NAME' (starts on every boot)"
  if nmcli -t -f NAME connection show 2>/dev/null | grep -qx SSP-Hotspot; then
    run nmcli connection delete SSP-Hotspot
  fi
  run nmcli connection add type wifi ifname wlan0 con-name SSP-Hotspot autoconnect yes ssid "$HOTSPOT_NAME" \
    802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared ipv6.method ignore \
    wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$HOTSPOT_PASS" connection.autoconnect-priority 100
fi

# the Wi-Fi name/password go in a root-only file, read by the service
# (so SSP can show a "join the Wi-Fi" QR code), never on its command line
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

say "Starting SSP on every boot (systemd service 'ssp')"
UNIT=/etc/systemd/system/ssp.service
CONTENT="[Unit]
Description=SSP - Song and Setlist Planner server
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
echo "SSP is installed."
if [ -n "$HOTSPOT_NAME" ]; then
  echo "  The Pi's own Wi-Fi '$HOTSPOT_NAME' starts on boot (reboot now, or: sudo nmcli connection up SSP-Hotspot)."
  echo "  Careful: while it's up, the Pi is off your home Wi-Fi; switch back with"
  echo "  sudo nmcli connection down SSP-Hotspot"
  HOT_URL="http://10.42.0.1/"
  [ "$PORT" = 80 ] || HOT_URL="http://10.42.0.1:$PORT/"
  echo "  On that Wi-Fi, open $URL (or $HOT_URL)"
else
  echo "  Open $URL on any phone or tablet on this network."
fi
echo "  'Connect a device' inside SSP shows QR codes (including one to join the Wi-Fi)."
if [ "$DRY" = 0 ]; then
  ( cd "$REPO/server" && python3 -c "import qr, sys; print(qr.terminal(sys.argv[1]))" "$URL" ) || true
fi
echo "  Status: systemctl status ssp     Log: journalctl -u ssp -f"
