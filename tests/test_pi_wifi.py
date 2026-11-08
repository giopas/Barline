"""The Raspberry Pi's own Wi-Fi: launchers/pi/wifi-fallback.sh (run at boot)
and install.sh --hotspot, against a fake nmcli. Nothing real is touched."""

import os
import platform
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FALLBACK = os.path.join(ROOT, "launchers", "pi", "wifi-fallback.sh")
INSTALL = os.path.join(ROOT, "launchers", "pi", "install.sh")

# A fake nmcli: answers from files in $FAKE_NM, records every call in $FAKE_NM/calls.
FAKE_NMCLI = r"""#!/usr/bin/env bash
echo "$*" >> "$FAKE_NM/calls"
case "$*" in
  "-t -f NAME connection show") cat "$FAKE_NM/connections" 2>/dev/null ;;
  "-t -f NAME connection show --active") cat "$FAKE_NM/active" 2>/dev/null ;;
  "-t -f DEVICE,TYPE,STATE,CONNECTION device") cat "$FAKE_NM/devices" 2>/dev/null ;;
  "connection up SSP-Hotspot") echo "SSP-Hotspot" > "$FAKE_NM/active" ;;
esac
exit 0
"""


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class FallbackTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ssp-nm-")
        self.bin = os.path.join(self.dir, "bin")
        os.mkdir(self.bin)
        nm = os.path.join(self.bin, "nmcli")
        with open(nm, "w") as f:
            f.write(FAKE_NMCLI)
        os.chmod(nm, os.stat(nm).st_mode | stat.S_IEXEC)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, name, text):
        with open(os.path.join(self.dir, name), "w") as f:
            f.write(text)

    def run_fallback(self, wait="2"):
        env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ["PATH"], FAKE_NM=self.dir,
                   SSP_WIFI_WAIT=wait, SSP_WIFI_STEP="1")
        res = subprocess.run(["bash", FALLBACK], env=env, capture_output=True, text=True, timeout=30)
        path = os.path.join(self.dir, "calls")
        calls = ""
        if os.path.exists(path):
            with open(path) as f:
                calls = f.read()
        return res, calls

    def test_known_network_means_no_hotspot(self):
        self.write("connections", "Home\nSSP-Hotspot\n")
        self.write("devices", "lo:loopback:connected (externally):lo\nwlan0:wifi:connected:Home\n")
        res, calls = self.run_fallback()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("No hotspot needed", res.stdout)
        self.assertNotIn("connection up", calls)

    def test_a_cable_counts_too(self):
        self.write("connections", "SSP-Hotspot\n")
        self.write("devices", "eth0:ethernet:connected:Wired connection 1\nwlan0:wifi:disconnected:\n")
        res, calls = self.run_fallback()
        self.assertIn("eth0", res.stdout)
        self.assertNotIn("connection up", calls)

    def test_nothing_known_starts_the_hotspot(self):
        self.write("connections", "Home\nSSP-Hotspot\n")
        self.write("devices", "lo:loopback:connected (externally):lo\nwlan0:wifi:disconnected:\n")
        res, calls = self.run_fallback(wait="2")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("connection up SSP-Hotspot", calls)
        self.assertIn("is up", res.stdout)

    def test_already_up(self):
        self.write("connections", "SSP-Hotspot\n")
        self.write("active", "SSP-Hotspot\n")
        self.write("devices", "wlan0:wifi:connected:SSP-Hotspot\n")
        res, calls = self.run_fallback()
        self.assertIn("already up", res.stdout)
        self.assertNotIn("connection up", calls)

    def test_no_hotspot_set_up(self):
        self.write("connections", "Home\n")
        res, calls = self.run_fallback()
        self.assertEqual(res.returncode, 0)
        self.assertIn("nothing to do", res.stdout)
        self.assertNotIn("connection up", calls)


@unittest.skipUnless(platform.system() == "Linux" and shutil.which("bash") and shutil.which("getent"),
                     "install.sh's dry run reads Linux user records")
class InstallDryRunTests(unittest.TestCase):
    def dry(self, *args):
        user = os.environ.get("USER") or subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()
        res = subprocess.run(["bash", INSTALL, "--dry-run", "--user", user, *args],
                             capture_output=True, text=True, timeout=60)
        return res

    def test_hotspot_when_needed_is_the_default(self):
        res = self.dry("--hotspot", "SSP-Band", "secret123")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("autoconnect no", res.stdout)
        self.assertIn("ssp-wifi.service", res.stdout)
        self.assertIn("wifi-fallback.sh", res.stdout)
        self.assertIn("finds no network it knows", res.stdout)

    def test_hotspot_always(self):
        res = self.dry("--hotspot", "SSP-Band", "secret123", "--hotspot-always")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("autoconnect yes", res.stdout)
        self.assertNotIn("wifi-fallback.sh", res.stdout)

    def test_always_needs_a_hotspot(self):
        res = self.dry("--hotspot-always")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("goes with --hotspot", res.stderr)

    def test_short_password(self):
        res = self.dry("--hotspot", "SSP-Band", "short")
        self.assertNotEqual(res.returncode, 0)


if __name__ == "__main__":
    unittest.main()
