#!/usr/bin/env bash
# SSP on a Raspberry Pi: its own Wi-Fi, only when it's needed.
#
# Run once at boot by the ssp-wifi service (install.sh --hotspot sets it up).
# Waits for the Pi to get on a network it knows (your home Wi-Fi, the
# rehearsal room's, a cable). If it does, nothing changes. If nothing is
# connected after the wait (a venue with no network, or an unknown one),
# it starts the Pi's own Wi-Fi, the "SSP-Hotspot" connection, so phones can
# join it and open SSP.
#
#   SSP_WIFI_WAIT      seconds to wait for a known network (default 40)
#   SSP_HOTSPOT_CON    the connection to start (default SSP-Hotspot)
#
# Back on your home Wi-Fi later: sudo nmcli connection down SSP-Hotspot
# (NetworkManager then joins a known network by itself).

set -u

WAIT="${SSP_WIFI_WAIT:-40}"
CON="${SSP_HOTSPOT_CON:-SSP-Hotspot}"
STEP="${SSP_WIFI_STEP:-2}"

log() { echo "ssp-wifi: $*"; }

case "$WAIT" in ''|*[!0-9]*) WAIT=40 ;; esac

if ! nmcli -t -f NAME connection show 2>/dev/null | grep -qx "$CON"; then
  log "no '$CON' connection: nothing to do (install.sh --hotspot makes it)"
  exit 0
fi

# Something other than the loopback, and other than our own hotspot, is connected?
connected_elsewhere() {
  nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device 2>/dev/null | while IFS=: read -r dev type state conn; do
    [ "$type" = loopback ] && continue
    [ "$conn" = "$CON" ] && continue
    case "$state" in connected) echo "$dev ($conn)"; break ;; esac
  done
}

hotspot_up() {
  nmcli -t -f NAME connection show --active 2>/dev/null | grep -qx "$CON"
}

waited=0
while :; do
  if hotspot_up; then
    log "'$CON' is already up"
    exit 0
  fi
  where="$(connected_elsewhere)"
  if [ -n "$where" ]; then
    log "on a known network: $where. No hotspot needed."
    exit 0
  fi
  [ "$waited" -ge "$WAIT" ] && break
  sleep "$STEP"
  waited=$((waited + STEP))
done

log "no known network after ${WAIT}s: starting '$CON'"
if nmcli connection up "$CON"; then
  log "'$CON' is up: join it and open SSP"
  exit 0
fi
log "couldn't start '$CON' (see: journalctl -u ssp-wifi)"
exit 1
