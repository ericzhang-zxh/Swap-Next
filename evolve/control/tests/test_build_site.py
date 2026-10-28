# SPDX-License-Identifier: GPL-2.0-only
"""build_site.py publishes campaigns/<c>/report/ pages at unchanged URLs."""
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".agents/skills/explaining-campaign-results/scripts/build_site.py"
PAGE = "<!doctype html><html><body>report</body></html>"


def run_site(campaigns, site):
    return subprocess.run([sys.executable, str(SCRIPT), str(campaigns), str(site)],
                          capture_output=True, text=True)


class BuildSiteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.campaigns = pathlib.Path(self.tmp.name) / "campaigns"
        self.site = pathlib.Path(self.tmp.name) / "_site"

    def tearDown(self):
        self.tmp.cleanup()

    def write_report(self, rel):
        path = self.campaigns / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(PAGE)
        return path

    def test_site_urls(self):
        self.write_report("xswap-next-2026-10-24/report/explainer.html")
        self.write_report(
            "swap-standard-2026-10-22/report/swap-standard-evolve-2026-10-22/explainer.html")
        result = run_site(self.campaigns, self.site)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.site / "xswap-next-2026-10-24/index.html").is_file())
        self.assertTrue((self.site / "swap-standard-evolve-2026-10-22/index.html").is_file())
        self.assertFalse((self.site / "swap-standard-2026-10-22").exists())
        index = (self.site / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="xswap-next-2026-10-24/"', index)
        self.assertIn('href="swap-standard-evolve-2026-10-22/"', index)
        self.assertLess(index.index("xswap-next-2026-10-24/"),
                        index.index("swap-standard-evolve-2026-10-22/"))

    def test_duplicate_published_name_fails(self):
        self.write_report("xswap-2026-10-21/report/explainer.html")
        self.write_report("other-2026-10-20/report/xswap-2026-10-21/explainer.html")
        result = run_site(self.campaigns, self.site)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("xswap-2026-10-21", result.stderr)


if __name__ == "__main__":
    unittest.main()
