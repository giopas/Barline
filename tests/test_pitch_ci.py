"""The pitch video and deck are made and attached by GitHub Actions, never by hand.

pitch.yml makes them with tools/make_pitch_video.py and attaches them to the
release; release.yml calls it after publishing. The video page lives on the
same Pages site as Barline Pocket (a repo has only one), so pocket.yml adds it
and pitch.yml restarts pocket.yml on the release's tag. The README links to
the latest release's files, and the in-app update check must never pick them up.
"""
import importlib.util
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WF = ROOT / ".github" / "workflows"
sys.path.insert(0, str(ROOT))


def _tool():
    try:
        import PIL  # noqa: F401  (the tool needs Pillow; the server doesn't)
    except ImportError:
        raise unittest.SkipTest("Pillow isn't installed")
    spec = importlib.util.spec_from_file_location("pitch", ROOT / "tools" / "make_pitch_video.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class PitchCI(unittest.TestCase):
    def test_release_calls_pitch_after_publishing(self):
        rel = (WF / "release.yml").read_text(encoding="utf-8")
        m = re.search(r"\n  pitch:\n((?:    .*\n|\s*\n)+)", rel + "\n")
        self.assertTrue(m, "release.yml has no pitch job")
        job = m.group(1)
        for need in ("needs: publish", "uses: ./.github/workflows/pitch.yml",
                     "tag: ${{ github.ref_name }}", "contents: write", "actions: write"):
            self.assertIn(need, job)

    def test_pitch_uses_the_strict_voice_and_attaches_both_files(self):
        text = (WF / "pitch.yml").read_text(encoding="utf-8")
        self.assertIn("--stills --tts edge --strict-voice", text)
        self.assertIn("gh release upload", text)
        self.assertIn("Barline_Pitch.mp4 Barline_Pitch.pdf", text)
        for trigger in ("  workflow_call:", "  workflow_dispatch:", "  push:",
                        '      - "tools/make_pitch_video.py"', '      - "screenshots/**"'):
            self.assertIn(trigger, text)

    def test_pitch_republishes_the_pocket_site_on_the_release_tag(self):
        pitch = (WF / "pitch.yml").read_text(encoding="utf-8")
        self.assertIn('gh workflow run pocket.yml --repo "$GITHUB_REPOSITORY" --ref "$LATEST"', pitch)
        self.assertIn("actions: write", pitch)
        # one Pages site: no second workflow may deploy to Pages
        deployers = [p.name for p in WF.glob("*.yml") if "actions/deploy-pages@" in p.read_text(encoding="utf-8")]
        self.assertEqual(deployers, ["pocket.yml"])

    def test_the_pocket_site_carries_the_video_page_after_pockets_own_build(self):
        pocket = (WF / "pocket.yml").read_text(encoding="utf-8")
        build = pocket.index("python tools/build_pocket.py --out _site")
        video = pocket.index("cp tools/pitch_page.html _site/video/index.html")
        self.assertLess(build, video, "the video must stay out of Pocket's offline copy")
        self.assertIn("-p 'Barline_Pitch.*' -D _site/video", pocket)
        self.assertIn("_site/video/slide-01.png", pocket)
        self.assertIn("_site/video/icon.png", pocket)

    def test_pockets_service_worker_leaves_the_video_page_alone(self):
        import tools.build_pocket as bp
        self.assertIn('pathname.includes("/video/")) return;', bp.SW)
        with tempfile.TemporaryDirectory() as out:
            files = bp.build(out)
        self.assertFalse([f for f in files if f.startswith("video/")])

    def test_update_check_ignores_the_pitch_files(self):
        from server import update
        for name in ("Barline_Pitch.mp4", "Barline_Pitch.pdf"):
            self.assertIsNone(update._ASSET_RE.match(name))

    def test_readme_poster_opens_the_page_and_links_the_latest_files(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("(screenshots/pitch-poster.png)](https://giopas.github.io/Barline/video/)", readme)
        for ext in ("mp4", "pdf"):
            self.assertIn(f"releases/latest/download/Barline_Pitch.{ext}", readme)
        self.assertTrue((ROOT / "screenshots" / "pitch-poster.png").is_file())

    def test_the_page_plays_the_files_put_beside_it(self):
        html = (ROOT / "tools" / "pitch_page.html").read_text(encoding="utf-8")
        for name in ("Barline_Pitch.mp4", "Barline_Pitch.pdf", "icon.png", "slide-01.png"):
            self.assertIn(f'"{name}"', html)
        self.assertIn("<video", html)
        self.assertIn("playsinline", html)
        self.assertIn('href="../"', html)  # Pocket, one level up

    def test_the_tool_names_its_files_after_the_stem(self):
        m = _tool()
        self.assertEqual(m.FILE_STEM, "Barline_Pitch")

    def test_every_slide_picture_exists(self):
        m = _tool()
        for slide in m.SLIDES:
            for name in slide.get("media", []):
                self.assertTrue((ROOT / "screenshots" / name).is_file(), f"{slide['title']}: {name}")

    def test_strict_voice_never_makes_a_video_without_one(self):
        m = _tool()
        voice = m.Voice("edge", "en-US-AndrewNeural", 180)
        voice.edge_cmd = ["false"]  # edge-tts fails, as when the service can't be reached
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(voice.render("Hello", os.path.join(tmp, "v.wav"), tmp))
        src = (ROOT / "tools" / "make_pitch_video.py").read_text(encoding="utf-8")
        self.assertIn('sys.exit(f"--strict-voice: slide {i + 1} got no voice.")', src)


if __name__ == "__main__":
    unittest.main()
