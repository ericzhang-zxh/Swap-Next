#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
import json
import pathlib
import shutil
import tempfile
import unittest

from build_site import build_site, get_sort_key, published_name, resolve_campaign_date


class BuildSiteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = pathlib.Path(self.temp_dir.name)
        self.campaigns = self.root / "campaigns"
        self.campaigns.mkdir(parents=True)
        self.site = self.root / "_site"

    def _create_campaign(self, name, *, date_in_spec=None, camp_json=None, deliv_json=None, subtitle=None):
        camp_dir = self.campaigns / name
        camp_dir.mkdir(parents=True, exist_ok=True)
        report_dir = camp_dir / "report"
        report_dir.mkdir(parents=True, exist_ok=True)

        if camp_json is not None:
            (camp_dir / "campaign.json").write_text(json.dumps(camp_json))
        if deliv_json is not None:
            (report_dir / "delivery.json").write_text(json.dumps(deliv_json))

        explainer_html = report_dir / "explainer.html"
        explainer_html.write_text("<html><body>Explainer</body></html>")

        spec = {"title": f"Title for {name}", "verdict": {"status": "accepted", "headline": "Good"}}
        if date_in_spec:
            spec["date"] = date_in_spec
        if subtitle:
            spec["subtitle"] = subtitle
        (report_dir / "explainer.json").write_text(json.dumps(spec))
        return explainer_html, spec, camp_dir

    def test_resolve_date_from_explicit_spec(self):
        page, spec, camp_dir = self._create_campaign("c1", date_in_spec="2026-11-06")
        self.assertEqual(resolve_campaign_date(page, spec, camp_dir), "2026-11-06")

    def test_resolve_date_from_published_name(self):
        page, spec, camp_dir = self._create_campaign("my-campaign-2026-11-05")
        self.assertEqual(resolve_campaign_date(page, spec, camp_dir), "2026-11-05")

    def test_resolve_date_from_campaign_json(self):
        page, spec, camp_dir = self._create_campaign("c-undated", camp_json={"closed": "2026-11-04"})
        self.assertEqual(resolve_campaign_date(page, spec, camp_dir), "2026-11-04")

    def test_resolve_date_from_delivery_json(self):
        page, spec, camp_dir = self._create_campaign("c-deliv", deliv_json={"history": [{"time": 1793945749}]})
        # 1793945749 corresponds to 2026-11-05
        self.assertTrue(resolve_campaign_date(page, spec, camp_dir).startswith("2026-"))

    def test_resolve_date_from_subtitle_regex(self):
        page, spec, camp_dir = self._create_campaign("c-sub", subtitle="Finished on 2026-10-31 boots")
        self.assertEqual(resolve_campaign_date(page, spec, camp_dir), "2026-10-31")

    def test_build_site_sorts_newest_first_and_displays_dates(self):
        self._create_campaign("old-2026-10-20")
        self._create_campaign("mid-2026-11-01")
        self._create_campaign("newest-2026-11-06")

        build_site(self.campaigns, self.site)
        index_html = (self.site / "index.html").read_text()

        pos_newest = index_html.find("newest-2026-11-06")
        pos_mid = index_html.find("mid-2026-11-01")
        pos_old = index_html.find("old-2026-10-20")

        self.assertTrue(0 <= pos_newest < pos_mid < pos_old, "Campaigns must sort newest first!")
        self.assertIn("2026-11-06", index_html)
        self.assertIn("2026-11-01", index_html)
        self.assertIn("2026-10-20", index_html)


if __name__ == "__main__":
    unittest.main()
