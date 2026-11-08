"""server/hotspot.py: making this computer the band's Wi-Fi. No radio is
touched: every command goes to a fake runner that records it."""

import base64
import os
import platform
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

import hotspot  # noqa: E402


class FakeRun:
    """Answers commands from a table of (first words -> (code, out, err))."""

    def __init__(self, answers=None):
        self.answers = answers or {}
        self.calls = []

    def __call__(self, cmd, timeout=30, env=None):
        self.calls.append((list(cmd), env))
        for key, answer in self.answers.items():
            if tuple(cmd[:len(key)]) == key:
                return answer
        return (0, "", "")


def which_all(name):
    return "/usr/bin/" + name


def which_none(_name):
    return None


NMCLI_DEVICES = "wlp2s0:wifi:disconnected\nenp3s0:ethernet:unavailable\nlo:loopback:unmanaged\n"


class Basics(unittest.TestCase):
    def test_password_is_easy_and_valid(self):
        seen = set()
        for _ in range(50):
            p = hotspot.make_password()
            self.assertRegex(p, r"^[a-z]{4}-[a-z]{4}-[2-9]{4}$")
            self.assertIsNone(hotspot.check("SSP-Band", p))
            self.assertFalse(set(p) & set("0o1lI"))
            seen.add(p)
        self.assertGreater(len(seen), 45)

    def test_check(self):
        self.assertIsNone(hotspot.check("SSP-Band", "12345678"))
        self.assertIn("name", hotspot.check("  ", "12345678"))
        self.assertIn("32", hotspot.check("x" * 33, "12345678"))
        self.assertIn("32", hotspot.check("é" * 17, "12345678"))  # 34 bytes
        self.assertIn("8 to 63", hotspot.check("SSP", "short"))
        self.assertIn("8 to 63", hotspot.check("SSP", "x" * 64))
        self.assertIn("accents", hotspot.check("SSP", "passwörd1"))
        self.assertIn("control", hotspot.check("SSP\n", "12345678"))

    def test_method_per_system(self):
        self.assertEqual(hotspot.method("Linux", which_all), "nmcli")
        self.assertIsNone(hotspot.method("Linux", which_none))
        self.assertEqual(hotspot.method("Windows", which_all), "windows")
        self.assertEqual(hotspot.method("Darwin", which_none), "macos")
        self.assertIsNone(hotspot.method("FreeBSD", which_all))
        self.assertTrue(hotspot.one_click("Linux", which_all))
        self.assertTrue(hotspot.one_click("Windows", which_all))
        self.assertFalse(hotspot.one_click("Darwin", which_all))

    def test_steps(self):
        self.assertEqual(hotspot.steps("Linux"), ())
        self.assertIn("Internet Sharing", " ".join(hotspot.steps("Darwin")))
        self.assertIn("Mobile hotspot", " ".join(hotspot.steps("Windows")))

    def test_bad_values_never_reach_a_command(self):
        run = FakeRun()
        r = hotspot.start("SSP", "short", run=run, system="Linux", which=which_all)
        self.assertFalse(r["ok"])
        self.assertEqual(run.calls, [])


class Linux(unittest.TestCase):
    def test_wifi_device(self):
        run = FakeRun({("nmcli", "-t"): (0, NMCLI_DEVICES, "")})
        self.assertEqual(hotspot.wifi_device(run), "wlp2s0")
        run = FakeRun({("nmcli", "-t"): (0, "wlan0:wifi:unmanaged\nwlan1:wifi-p2p:disconnected\n", "")})
        self.assertIsNone(hotspot.wifi_device(run))
        self.assertIsNone(hotspot.wifi_device(FakeRun({("nmcli", "-t"): (8, "", "not running")})))

    def test_start(self):
        run = FakeRun({("nmcli", "-t"): (0, NMCLI_DEVICES, "")})
        r = hotspot.start("Band; Wi-Fi", "kmrt-vhae-4827", run=run, system="Linux", which=which_all)
        self.assertTrue(r["ok"], r)
        cmd = run.calls[-1][0]
        self.assertEqual(cmd, ["nmcli", "device", "wifi", "hotspot", "ifname", "wlp2s0", "con-name",
                               hotspot.NM_CONNECTION, "ssid", "Band; Wi-Fi", "password", "kmrt-vhae-4827"])
        self.assertNotEqual(hotspot.NM_CONNECTION, "SSP-Hotspot")  # the Pi installer's profile

    def test_start_reports_networkmanager(self):
        run = FakeRun({("nmcli", "-t"): (0, NMCLI_DEVICES, ""),
                       ("nmcli", "device", "wifi"): (4, "", "Error: Device 'wlp2s0' does not support AP mode.\n")})
        r = hotspot.start("SSP", "12345678", run=run, system="Linux", which=which_all)
        self.assertFalse(r["ok"])
        self.assertIn("AP mode", r["message"])
        r = hotspot.start("SSP", "12345678", run=FakeRun({("nmcli", "-t"): (0, "", "")}),
                          system="Linux", which=which_all)
        self.assertIn("No Wi-Fi adapter", r["message"])

    def test_stop_removes_the_profile(self):
        run = FakeRun()
        r = hotspot.stop(run=run, system="Linux", which=which_all)
        self.assertTrue(r["ok"])
        self.assertEqual([c[0] for c in run.calls], [["nmcli", "connection", "down", hotspot.NM_CONNECTION],
                                                     ["nmcli", "connection", "delete", hotspot.NM_CONNECTION]])


class Windows(unittest.TestCase):
    def decoded(self, cmd):
        self.assertEqual(cmd[:2], ["powershell", "-NoProfile"])
        self.assertEqual(cmd[-2], "-EncodedCommand")
        return base64.b64decode(cmd[-1]).decode("utf-16-le")

    def test_start_passes_values_by_environment(self):
        run = FakeRun({("powershell",): (0, "SSP:OK\n", "")})
        r = hotspot.start("Band 'x'", "pa$$word;12", run=run, system="Windows", which=which_all)
        self.assertTrue(r["ok"], r)
        cmd, env = run.calls[0]
        script = self.decoded(cmd)
        self.assertEqual(script, hotspot.PS_START)
        self.assertNotIn("pa$$word", script)
        self.assertNotIn("pa$$word", " ".join(cmd))
        self.assertEqual(env["SSP_HOTSPOT_SSID"], "Band 'x'")
        self.assertEqual(env["SSP_HOTSPOT_PASSWORD"], "pa$$word;12")
        self.assertIn("StartTetheringAsync", script)
        self.assertIn("loopback", script)

    def test_no_connection_to_share_means_settings(self):
        run = FakeRun({("powershell",): (3, "SSP:NOCONNECTION\n", "")})
        r = hotspot.start("SSP", "12345678", run=run, system="Windows", which=which_all)
        self.assertFalse(r["ok"])
        self.assertTrue(r["manual"])
        self.assertIn("share", r["message"])

    def test_failure_detail(self):
        run = FakeRun({("powershell",): (4, "SSP:FAIL WiFiDeviceOff \n", "")})
        r = hotspot.start("SSP", "12345678", run=run, system="Windows", which=which_all)
        self.assertIn("WiFiDeviceOff", r["message"])
        run = FakeRun({("powershell",): (1, "", "Add-Type : Cannot add type\n")})
        r = hotspot.start("SSP", "12345678", run=run, system="Windows", which=which_all)
        self.assertIn("Cannot add type", r["message"])

    def test_stop(self):
        run = FakeRun({("powershell",): (0, "SSP:OK\n", "")})
        self.assertTrue(hotspot.stop(run=run, system="Windows", which=which_all)["ok"])
        self.assertIn("StopTetheringAsync", self.decoded(run.calls[0][0]))

    @unittest.skipUnless(platform.system() == "Windows" and shutil.which("powershell"), "Windows only")
    def test_scripts_parse(self):
        for script in (hotspot.PS_START, hotspot.PS_STOP):
            check = ("$e = $null; [void][System.Management.Automation.Language.Parser]::ParseInput("
                     "[Console]::In.ReadToEnd(), [ref]$null, [ref]$e); if ($e.Count) { $e; exit 1 }")
            res = subprocess.run(["powershell", "-NoProfile", "-Command", check], input=script,
                                 capture_output=True, text=True, timeout=60)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    @unittest.skipUnless(platform.system() == "Windows" and shutil.which("powershell"), "Windows only")
    def test_winrt_types_load(self):
        """The prelude (Add-Type, the AsTask lookup, the WinRT types, the
        profile list) runs for real; there's no Wi-Fi to start on a CI box."""
        cmd = hotspot.powershell_command(hotspot._PS_PRELUDE + "\nWrite-Output ('SSP:LOADED ' + $profiles.Count)")
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        self.assertIn("SSP:LOADED", res.stdout, res.stdout + res.stderr)


class Mac(unittest.TestCase):
    def test_mac_is_by_hand(self):
        run = FakeRun()
        r = hotspot.start("SSP", "12345678", run=run, system="Darwin", which=which_all)
        self.assertFalse(r["ok"])
        self.assertTrue(r["manual"])
        self.assertEqual(run.calls, [])
        self.assertTrue(hotspot.stop(run=run, system="Darwin")["manual"])

    def test_open_settings(self):
        run = FakeRun()
        self.assertTrue(hotspot.open_settings("Darwin", run=run))
        self.assertEqual(run.calls[0][0], ["open", hotspot.MAC_SETTINGS_URL])


if __name__ == "__main__":
    unittest.main()
