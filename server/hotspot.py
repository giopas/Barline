"""
Make this computer the band's Wi-Fi, for a rehearsal room or a venue with
no network: the phones and tablets join it, then open Barline as usual.

What each system allows (and so what the control panel offers):

    Linux    NetworkManager (``nmcli device wifi hotspot``) makes a WPA2
             network with or without any other connection: one click.
    Windows  Mobile Hotspot, started through its WinRT API from PowerShell:
             one click when Windows agrees. Windows only hotspots a
             connection it can share, so with no network at all it usually
             says no (unless a Microsoft Loopback Adapter is set up, see
             the wiki); then Barline opens the Mobile hotspot settings instead.
    macOS    No supported way for an app to turn on Internet Sharing (and
             "Create Network" is gone since Big Sur), so Barline opens
             System Settings > Sharing and shows the steps.

Whatever made the network, the control panel and the web app's Connect
screen show a "join this Wi-Fi" QR code with its name and password, and
local_addresses() already puts the hotspot's address (10.42.0.x,
192.168.137.x, 192.168.2.x) first.

Nothing here reaches beyond this computer's own radio: the network has no
internet unless this computer shares one, which is the point -- Barline stays
on the band's own Wi-Fi (PROJECT_CHARTER.md).

Every command is a list run without a shell; the name and password reach
PowerShell as environment variables, never pasted into the script.
"""

from __future__ import annotations

import base64
import os
import platform
import secrets
import shutil
import subprocess
import webbrowser

DEFAULT_SSID = "Barline-Band"
# The desktop panel's own NetworkManager profile; the Pi installer's is
# "SSP-Hotspot", so the two never step on each other.
NM_CONNECTION = "SSP-Desktop-Hotspot"

MAC_SETTINGS_URL = "x-apple.systempreferences:com.apple.Sharing-Settings.extension"
WINDOWS_SETTINGS_URL = "ms-settings:network-mobilehotspot"

# Easy to read out loud and to type on a phone if the QR code won't scan:
# no 0/O, 1/l/I, and nothing that needs the symbols keyboard.
_LETTERS = "abcdefghjkmnpqrstuvwxyz"
_DIGITS = "23456789"


def make_password() -> str:
    """e.g. ``kmrt-vhae-4827``: 14 characters, about 50 bits."""
    part = lambda n: "".join(secrets.choice(_LETTERS) for _ in range(n))  # noqa: E731
    return f"{part(4)}-{part(4)}-{''.join(secrets.choice(_DIGITS) for _ in range(4))}"


def check(ssid: str, password: str):
    """None when the name and password can make a WPA2 network, else what's wrong."""
    ssid = ssid or ""
    password = password or ""
    if not ssid.strip():
        return "Give the network a name."
    if len(ssid.encode("utf-8")) > 32:
        return "The network name can be 32 characters at most."
    if any(ord(c) < 32 for c in ssid):
        return "The network name can't contain control characters."
    if not 8 <= len(password) <= 63:
        return "The password needs 8 to 63 characters."
    if any(not 32 <= ord(c) < 127 for c in password):
        return "Use plain letters, digits and symbols in the password (no accents)."
    return None


# -- running commands (swapped out by the tests) ----------------------------

def _run(cmd, timeout=30, env=None):
    """(returncode, stdout, stderr); (127, "", why) when it can't run at all."""
    kw = {}
    if platform.system() == "Windows":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # no console flash
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,  # nosec B603
                             env=env, check=False, **kw)
        return res.returncode, res.stdout or "", res.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", "it took too long"
    except OSError as exc:
        return 127, "", str(exc)


def method(system: str = None, which=shutil.which):
    """How this computer can make a network: "nmcli", "windows", "macos"
    (by hand, in System Settings) or None."""
    system = system or platform.system()
    if system == "Linux":
        return "nmcli" if which("nmcli") else None
    if system == "Windows":
        return "windows" if which("powershell") or which("powershell.exe") else None
    if system == "Darwin":
        return "macos"
    return None


def one_click(system: str = None, which=shutil.which) -> bool:
    return method(system, which) in ("nmcli", "windows")


def _result(ok, message, manual=False):
    return {"ok": ok, "message": message, "manual": manual}


# -- Linux: NetworkManager ---------------------------------------------------

def wifi_device(run=_run):
    """The first Wi-Fi device NetworkManager manages (e.g. ``wlan0``), or None."""
    code, out, _err = run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"], timeout=10)
    if code != 0:
        return None
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and parts[1] == "wifi" and parts[2] != "unmanaged":
            return parts[0]
    return None


def _nm_start(ssid, password, run):
    dev = wifi_device(run)
    if not dev:
        return _result(False, "No Wi-Fi adapter found (NetworkManager lists none).")
    code, out, err = run(["nmcli", "device", "wifi", "hotspot", "ifname", dev, "con-name", NM_CONNECTION,
                          "ssid", ssid, "password", password], timeout=40)
    if code == 0:
        return _result(True, f'"{ssid}" is on ({dev}).')
    why = (err or out).strip().splitlines()
    return _result(False, "NetworkManager said: " + (why[-1] if why else f"error {code}"))


def _nm_stop(run):
    code, out, err = run(["nmcli", "connection", "down", NM_CONNECTION], timeout=20)
    run(["nmcli", "connection", "delete", NM_CONNECTION], timeout=20)  # don't leave the password behind
    if code == 0:
        return _result(True, "The band Wi-Fi is off.")
    why = (err or out).strip().splitlines()
    return _result(False, "NetworkManager said: " + (why[-1] if why else f"error {code}"))


# -- Windows: Mobile Hotspot through WinRT ------------------------------------

_PS_PRELUDE = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$ext = [System.WindowsRuntimeSystemExtensions].GetMethods()
$asTaskOp = ($ext | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
$asTaskAct = ($ext | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction' })[0]
function Await($op, [Type]$type) { $t = $asTaskOp.MakeGenericMethod($type).Invoke($null, @($op)); $null = $t.Wait(-1); $t.Result }
function AwaitAction($op) { $t = $asTaskAct.Invoke($null, @($op)); $null = $t.Wait(-1) }
$null = [Windows.Networking.Connectivity.NetworkInformation, Windows.Networking.Connectivity, ContentType = WindowsRuntime]
$null = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager, Windows.Networking.NetworkOperators, ContentType = WindowsRuntime]
$null = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult, Windows.Networking.NetworkOperators, ContentType = WindowsRuntime]
$TM = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]
# the connection to share: the internet one, else one named like a loopback
# adapter (the no-network setup in the wiki), else any Windows accepts
$profiles = @()
$net = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
if ($net) { $profiles += $net }
$profiles += @([Windows.Networking.Connectivity.NetworkInformation]::GetConnectionProfiles() | Sort-Object { if ($_.ProfileName -match 'loopback') { 0 } else { 1 } })
function Find-Manager {
  foreach ($p in $profiles) {
    try {
      if ($TM::GetTetheringCapabilityFromConnectionProfile($p).ToString() -eq 'Enabled') {
        return $TM::CreateFromConnectionProfile($p)
      }
    } catch { }
  }
  return $null
}
"""

PS_START = _PS_PRELUDE + r"""
$m = Find-Manager
if (-not $m) { Write-Output 'SSP:NOCONNECTION'; exit 3 }
$cfg = $m.GetCurrentAccessPointConfiguration()
$cfg.Ssid = $env:SSP_HOTSPOT_SSID
$cfg.Passphrase = $env:SSP_HOTSPOT_PASSWORD
AwaitAction ($m.ConfigureAccessPointAsync($cfg))
$r = Await ($m.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
if ($r.Status.ToString() -eq 'Success') { Write-Output 'SSP:OK'; exit 0 }
Write-Output ('SSP:FAIL ' + $r.Status + ' ' + $r.AdditionalErrorMessage); exit 4
"""

PS_STOP = _PS_PRELUDE + r"""
foreach ($p in $profiles) {
  try {
    $m = $TM::CreateFromConnectionProfile($p)
    if ($m.TetheringOperationalState.ToString() -eq 'On') {
      $null = Await ($m.StopTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
    }
  } catch { }
}
Write-Output 'SSP:OK'
"""


def powershell_command(script: str) -> list:
    """powershell.exe with the script base64-encoded (UTF-16LE, as -EncodedCommand
    wants it), so no quoting of any kind is involved."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-EncodedCommand", encoded]


def _win_start(ssid, password, run):
    env = dict(os.environ, SSP_HOTSPOT_SSID=ssid, SSP_HOTSPOT_PASSWORD=password)
    code, out, err = run(powershell_command(PS_START), timeout=60, env=env)
    if "SSP:OK" in out:
        return _result(True, f'"{ssid}" is on (Windows Mobile hotspot).')
    if "SSP:NOCONNECTION" in out:
        return _result(False, "Windows only makes a hotspot to share a connection, and this computer "
                              "has none it will share. The Mobile hotspot settings are open: "
                              "see the wiki for the no-network setup, or use a phone's hotspot.", manual=True)
    detail = next((ln[9:].strip() for ln in out.splitlines() if ln.startswith("SSP:FAIL")), "")
    if not detail:
        lines = (err or out).strip().splitlines()
        detail = lines[-1] if lines else f"error {code}"
    return _result(False, "Windows said: " + detail, manual=True)


def _win_stop(run):
    code, out, err = run(powershell_command(PS_STOP), timeout=40)
    if "SSP:OK" in out:
        return _result(True, "The band Wi-Fi is off.")
    lines = (err or out).strip().splitlines()
    return _result(False, "Windows said: " + (lines[-1] if lines else f"error {code}"))


# -- the two calls the control panel makes ------------------------------------

def start(ssid: str, password: str, run=_run, system: str = None, which=shutil.which) -> dict:
    """Turn the band Wi-Fi on. {"ok", "message", "manual"}: manual means
    the system's own settings are the way (and open_settings() helps)."""
    problem = check(ssid, password)
    if problem:
        return _result(False, problem)
    how = method(system, which)
    if how == "nmcli":
        return _nm_start(ssid, password, run)
    if how == "windows":
        return _win_start(ssid, password, run)
    if how == "macos":
        return _result(False, "A Mac turns this on in System Settings > Sharing.", manual=True)
    return _result(False, "This computer can't make a Wi-Fi network from Barline.", manual=True)


def stop(run=_run, system: str = None, which=shutil.which) -> dict:
    how = method(system, which)
    if how == "nmcli":
        return _nm_stop(run)
    if how == "windows":
        return _win_stop(run)
    return _result(False, "Turn it off where you turned it on (System Settings > Sharing).", manual=True)


def open_settings(system: str = None, run=_run) -> bool:
    """Open the system's own hotspot settings, where there's one to open."""
    system = system or platform.system()
    if system == "Darwin":
        return run(["open", MAC_SETTINGS_URL], timeout=10)[0] == 0
    if system == "Windows":
        try:
            os.startfile(WINDOWS_SETTINGS_URL)  # type: ignore[attr-defined]  # noqa: S606
            return True
        except (AttributeError, OSError):
            return webbrowser.open(WINDOWS_SETTINGS_URL)
    if system == "Linux":
        for cmd in (["nm-connection-editor"], ["gnome-control-center", "wifi"]):
            if shutil.which(cmd[0]):
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # nosec B603
                return True
    return False


MAC_STEPS = (
    "1. In System Settings > General > Sharing, click (i) next to Internet Sharing.",
    "2. Share your connection from: Thunderbolt Bridge (or Ethernet). It doesn't need to be plugged in.",
    "3. To devices using: Wi-Fi. Click Wi-Fi Options: the name and password above, Security WPA2/WPA3.",
    "4. Turn Internet Sharing on, then click Done.",
)

WINDOWS_STEPS = (
    "1. In Settings > Network & internet > Mobile hotspot, click Edit:",
    "   the name and password above.",
    "2. Turn Mobile hotspot on. With no network at all, Windows may refuse:",
    "   the wiki shows the one-time Loopback Adapter setup, or use a phone's hotspot.",
)


def steps(system: str = None) -> tuple:
    """What to do by hand on this system (empty where Barline does it all)."""
    system = system or platform.system()
    return {"Darwin": MAC_STEPS, "Windows": WINDOWS_STEPS}.get(system, ())
