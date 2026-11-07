"""Update check and "Update and restart" (server/update.py, ported from
QLC+ Swiss Knife): versions, the right download per computer, the 12-hour
cache and the off switch, SHA-256 verification, safe unpacking, the swap
scripts, and that packaging/make_archive.py writes the names the updater
looks for. Never touches the internet: SSP_UPDATE_FEED points at local files.

    python3 -m unittest tests.test_update
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import shutil
import ssl
import stat
import sys
import tarfile
import tempfile
import unittest
import zipfile
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))

import update  # noqa: E402
from version import VERSION  # noqa: E402


def _text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _tar(path, files):
    with tarfile.open(path, "w:gz") as t:
        for n, data in files.items():
            ti = tarfile.TarInfo(n)
            ti.size = len(data)
            t.addfile(ti, io.BytesIO(data))
    return path


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ssp-update-test-")
        self.env = mock.patch.dict(os.environ, {"SSP_UPDATE": os.path.join(self.tmp, "update.json")})
        self.env.start()
        os.environ.pop("SSP_UPDATE_FEED", None)

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def feed(self, tag="v99.0.0", assets=None, name="feed.json"):
        p = os.path.join(self.tmp, name)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"tag_name": tag, "html_url": "https://github.com/x/y/releases/tag/" + tag,
                       "body": "notes", "assets": assets or []}, f)
        os.environ["SSP_UPDATE_FEED"] = p
        return p

    # -- check ----------------------------------------------------------------

    def test_versions(self):
        self.assertEqual(update.parse_version("v0.11.0"), (0, 11, 0))
        self.assertEqual(update.parse_version("garbage"), ())
        self.assertTrue(update.is_newer("v0.12.0", "0.11.0"))
        self.assertTrue(update.is_newer("1.0.0", "0.11.0"))
        self.assertFalse(update.is_newer("0.11.0", "0.11.0"))
        self.assertFalse(update.is_newer("nonsense", "0.11.0"))

    def test_pick_asset_by_platform(self):
        a = [{"name": f"SSP-1.0.0-{o}-{r}.{e}"} for o, r, e in
             (("macos", "arm64", "tar.gz"), ("macos", "arm64", "dmg"), ("macos", "x86_64", "tar.gz"),
              ("windows", "x64", "zip"), ("linux", "x64", "tar.gz"))]
        a += [{"name": "SSP-1.0.0-windows-x64-setup.exe"}, {"name": "SHA256SUMS"}]
        self.assertTrue(update.pick_asset(a, "macos", "arm64")["name"].endswith("arm64.tar.gz"))  # not the .dmg
        self.assertTrue(update.pick_asset(a, "macos", "x86_64")["name"].endswith("x86_64.tar.gz"))
        self.assertEqual(update.pick_asset(a, "windows", "x64")["name"], "SSP-1.0.0-windows-x64.zip")
        self.assertTrue(update.pick_asset(a, "linux", "x64")["name"].endswith(".tar.gz"))
        self.assertIsNone(update.pick_asset(a, "linux", "arm64"))

    def test_check_newer_and_cache(self):
        self.feed()
        r = update.check()
        self.assertTrue(r["newer"])
        self.assertEqual(r["latest"], "99.0.0")
        self.assertEqual(r["current"], VERSION)
        self.assertFalse(r["frozen"])
        # cached: a feed that no longer exists isn't asked again within 12 h
        os.environ["SSP_UPDATE_FEED"] = os.path.join(self.tmp, "gone.json")
        self.assertEqual(update.check()["latest"], "99.0.0")
        self.assertTrue(update.check(force=True)["error"])

    def test_same_version_is_not_newer(self):
        self.feed("v" + VERSION)
        self.assertFalse(update.check()["newer"])

    def test_off_switch(self):
        self.feed()
        update.set_enabled(False)
        r = update.check()
        self.assertFalse(r["enabled"])
        self.assertNotIn("newer", r)
        update.set_enabled(True)
        self.assertTrue(update.check()["newer"])

    def test_offline_is_calm(self):
        os.environ["SSP_UPDATE_FEED"] = "/no/such/file.json"
        r = update.check()
        self.assertTrue(r["error"])
        self.assertFalse(r.get("newer"))

    def test_settings_file_is_in_the_app_support_folder(self):
        os.environ.pop("SSP_UPDATE")
        import platform_dirs
        self.assertEqual(os.path.dirname(update._file()), platform_dirs.user_app_dir())

    def test_a_release_without_this_computers_package_is_asked_again_soon(self):
        with mock.patch.object(update, "is_frozen", lambda: True), \
                mock.patch.object(update, "install_root", lambda: self.tmp):
            self.feed()  # no packages built yet
            r = update.check(now=1000.0)
            self.assertTrue(r["newer"] and r["asset"] is None and r["pending"])
            os_, arch = update.platform_key()
            ext = "zip" if os_ == "windows" else "tar.gz"
            self.feed(assets=[{"name": f"SSP-99.0.0-{os_}-{arch}.{ext}",
                               "browser_download_url": "https://github.com/x", "size": 1}], name="f2.json")
            self.assertTrue(update.check(now=1000.0 + 60)["pending"])  # still within 10 minutes
            r = update.check(now=1000.0 + 11 * 60)  # asked again: the package is there
            self.assertTrue(r["asset"] and not r["pending"])
            self.assertTrue(update.check(now=1000.0 + 3 * 3600)["asset"])  # and kept for hours

    # -- install ----------------------------------------------------------------

    def test_parse_sums(self):
        h = "a" * 64
        self.assertEqual(update.parse_sums(f"{h}  SSP-1.zip\n{h.upper()} *dir/x.tar.gz\njunk"),
                         {"SSP-1.zip": h, "x.tar.gz": h})

    def test_safe_extract_refuses_escape(self):
        out = os.path.join(self.tmp, "out")
        os.mkdir(out)
        z = os.path.join(self.tmp, "bad.zip")
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("../evil.txt", "x")
        with self.assertRaises(ValueError):
            update._safe_extract(z, out)
        t = _tar(os.path.join(self.tmp, "bad.tar.gz"), {"../evil.txt": b"x"})
        with self.assertRaises(ValueError):
            update._safe_extract(t, out)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "evil.txt")))

    def test_install_verifies_and_stages(self):
        """A packaged install: download -> SHA-256 -> unpack -> swap script (not run here)."""
        inst = os.path.join(self.tmp, "apps", "SSP")
        os.makedirs(inst)
        exe = os.path.join(inst, "SSP")
        with open(exe, "w") as f:
            f.write("old")
        ran = []
        name = "SSP-99.0.0-linux-x64.tar.gz"
        arc = _tar(os.path.join(self.tmp, name), {"SSP/SSP": b"new", "SSP/x.txt": b"1"})
        with open(arc, "rb") as f:
            good = hashlib.sha256(f.read()).hexdigest()
        sums = os.path.join(self.tmp, "SHA256SUMS")
        with open(sums, "w") as f:
            f.write(f"{good}  {name}\n")
        with mock.patch.object(update, "is_frozen", lambda: True), \
                mock.patch.object(update.sys, "executable", exe), \
                mock.patch.object(update.platform, "system", lambda: "Linux"), \
                mock.patch.object(update, "platform_key", lambda: ("linux", "x64")), \
                mock.patch.object(update.subprocess, "Popen", lambda *a, **k: ran.append(a)):
            self.feed(assets=[{"name": name, "browser_download_url": arc, "size": 1},
                              {"name": "SHA256SUMS", "browser_download_url": sums}])
            r = update.install()
            self.assertTrue(r["ok"] and r["restart"], r)
            self.assertIn("ssp-update.sh", ran[0][0][-1])
            staged = os.path.join(os.path.dirname(ran[0][0][-1]), "new", "SSP")
            self.assertEqual(_text(staged), "new")
            # a wrong checksum is refused and nothing is started
            ran.clear()
            with open(sums, "w") as f:
                f.write(f"{'0' * 64}  {name}\n")
            r = update.install(update.check(force=True))
            self.assertFalse(r["ok"])
            self.assertIn("SHA-256", r["message"])
            self.assertFalse(ran)
            # no checksum file: refused
            self.feed(assets=[{"name": name, "browser_download_url": arc}], name="f3.json")
            self.assertFalse(update.install(update.check(force=True))["ok"])

    def test_install_from_sources_only_explains(self):
        self.feed()
        r = update.install()
        self.assertFalse(r["ok"])
        self.assertIn("git pull", r["message"])

    def test_helper_scripts(self):
        _n, sh = update.helper_script(4242, "/opt/SSP", "/tmp/new", "Linux", "SSP")
        self.assertIn("kill -0 4242", sh)
        self.assertIn("mv '/opt/SSP' '/opt/SSP.old'", sh)
        self.assertIn("'/opt/SSP/SSP' &", sh)
        _n, mac = update.helper_script(7, "/Applications/SSP.app", "/tmp/n", "Darwin")
        self.assertIn("xattr -dr com.apple.quarantine", mac)
        self.assertIn("open '/Applications/SSP.app'", mac)
        n, bat = update.helper_script(9, r"C:\Apps\SSP", r"C:\tmp\new", "Windows", "SSP.exe")
        self.assertTrue(n.endswith(".bat"))
        self.assertIn("tasklist", bat)
        self.assertIn("SSP.exe", bat)
        _n, q = update.helper_script(1, "/o'brien/SSP", "/n", "Linux", "SSP")
        self.assertIn("'/o'\\''brien/SSP'", q)  # quoting survives an apostrophe

    def test_ssl_context_for_packaged_apps(self):
        import inspect
        self.assertIsInstance(update._ssl_context(), ssl.SSLContext)
        self.assertIn("context=_ssl_context()", inspect.getsource(update._read))
        self.assertIn("context=_ssl_context()", inspect.getsource(update._download))

    def test_downloads_only_from_github(self):
        with self.assertRaises(ValueError):
            update._check_host("https://evil.example/SSP.zip")
        update._check_host("https://github.com/giopas/x/releases/download/v1/SSP.zip")

    def test_zip_symlinks_are_kept(self):
        z = os.path.join(self.tmp, "a.zip")
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("App.app/Contents/Frameworks/lib.dylib", "x")
            info = zipfile.ZipInfo("App.app/Contents/Resources/lib.dylib")
            info.external_attr = (stat.S_IFLNK | 0o755) << 16
            zf.writestr(info, "../Frameworks/lib.dylib")
        out = os.path.join(self.tmp, "out")
        os.mkdir(out)
        update._safe_extract(z, out)
        link = os.path.join(out, "App.app/Contents/Resources/lib.dylib")
        self.assertTrue(os.path.islink(link))
        self.assertEqual(_text(link), "x")

    def test_windows_updater_keeps_the_uninstaller(self):
        old, new = os.path.join(self.tmp, "old"), os.path.join(self.tmp, "new")
        os.mkdir(old)
        os.mkdir(new)
        for n in ("unins000.exe", "unins000.dat", "SSP.exe"):
            with open(os.path.join(old, n), "w") as f:
                f.write(n)
        update.keep_uninstaller(old, new)
        self.assertEqual(sorted(os.listdir(new)), ["unins000.dat", "unins000.exe"])

    # -- packaging matches ------------------------------------------------------

    def test_packaging_writes_the_names_the_updater_looks_for(self):
        sp = importlib.util.spec_from_file_location("make_archive", os.path.join(ROOT, "packaging", "make_archive.py"))
        m = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(m)
        for ext, o, a in (("tar.gz", "macos", "arm64"), ("tar.gz", "macos", "x86_64"),
                          ("zip", "windows", "x64"), ("tar.gz", "linux", "x64")):
            name = m.asset_name(ext, o, a)
            self.assertTrue(update._ASSET_RE.match(name), name)
            self.assertEqual(update.pick_asset([{"name": name}], o, a)["name"], name)
        src = _text(os.path.join(ROOT, "packaging", "make_archive.py"))
        mac = src.split('system == "Darwin"')[1].split('elif system == "Windows"')[0]
        self.assertIn('asset_name("tar.gz")', mac)  # a tarball keeps the .app's symlinks
        wf = _text(os.path.join(ROOT, ".github", "workflows", "release.yml"))
        self.assertIn("SHA256SUMS", wf)  # the updater refuses a release without it
        iss = _text(os.path.join(ROOT, "packaging", "windows", "installer.iss"))
        self.assertIn("windows-x64-setup", iss)  # never picked by the updater (see pick_asset test)


if __name__ == "__main__":
    unittest.main()
