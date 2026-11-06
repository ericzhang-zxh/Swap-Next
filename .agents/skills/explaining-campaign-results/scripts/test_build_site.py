#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
import json
import pathlib
import shutil
import tempfile
import unittest

from build_site import (
    build_site,
    get_sort_key,
    published_name,
    resolve_base_sha,
    resolve_campaign_date,
    resolve_harness_model,
    resolve_line,
    resolve_metadata_bar,
    resolve_scale_and_budget,
)


class BuildSiteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = pathlib.Path(self.temp_dir.name)
        self.campaigns = self.root / "campaigns"
        self.campaigns.mkdir(parents=True)
        self.site = self.root / "_site"

    def _create_campaign(self, name, *, date_in_spec=None, camp_json=None, deliv_json=None,
                         subtitle=None, candidates_count=0, budget=None, protocol=None,
                         subfolder=None):
        camp_dir = self.campaigns / name
        camp_dir.mkdir(parents=True, exist_ok=True)
        report_dir = camp_dir / "report"
        if subfolder:
            target_dir = report_dir / subfolder
        else:
            target_dir = report_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        if camp_json is not None:
            (camp_dir / "campaign.json").write_text(json.dumps(camp_json))
        if protocol is not None:
            (camp_dir / "protocol.json").write_text(json.dumps(protocol))
        if budget is not None:
            (camp_dir / "ledger").mkdir(parents=True, exist_ok=True)
            (camp_dir / "ledger" / "budget.json").write_text(json.dumps(budget))
        if deliv_json is not None:
            (report_dir / "delivery.json").write_text(json.dumps(deliv_json))

        if candidates_count > 0:
            cands_dir = camp_dir / "candidates"
            cands_dir.mkdir(parents=True, exist_ok=True)
            for i in range(candidates_count):
                (cands_dir / f"cand{i+1}.json").write_text(json.dumps({"id": f"cand{i+1}"}))

        explainer_html = target_dir / "explainer.html"
        explainer_html.write_text("<html><body>Explainer</body></html>")

        spec = {"title": f"Title for {name}", "verdict": {"status": "accepted", "headline": "Good"}}
        if date_in_spec:
            spec["date"] = date_in_spec
        if subtitle:
            spec["subtitle"] = subtitle
        (target_dir / "explainer.json").write_text(json.dumps(spec))
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

    def test_standardized_card_bottom_metadata_bar(self):
        # Create campaigns matching the 4 required harness mappings
        self._create_campaign(
            "exp1-sync-zero-redundancy",
            subfolder="exp1-sync-zero-redundancy-2026-11-06",
            camp_json={"line": "exp1-sync-zero-redundancy"},
            protocol={"baseline_commit": "5e84ca928deeacb4eee656806a003f27d1eca82f"},
            candidates_count=1,
            budget={"guests": 57, "probe_guests": 12, "builds": 1},
        )
        self._create_campaign(
            "codex-r01-demand-2026-11-03",
            camp_json={"line": "demand"},
            protocol={"baseline_commit": "5e84ca928deeacb4eee656806a003f27d1eca82f"},
            candidates_count=1,
            budget={"guests": 2, "probe_guests": 9, "builds": 3},
        )
        self._create_campaign(
            "xswap-tcg-kbench-rev7-2026-10-29",
            camp_json={"line": "xswap"},
            protocol={"baseline_commit": "5e84ca928deeacb4eee656806a003f27d1eca82f"},
            candidates_count=0,
            budget={"guests": 79, "probe_guests": 15, "builds": 0},
        )
        self._create_campaign(
            "xswap-2026-10-21",
            camp_json={"line": "xswap"},
            protocol={"baseline_commit": "37de636c972a413f5c25e5b6c891fb4df2f53aed"},
            candidates_count=0,
            budget={"guests": 0, "builds": 0},
        )

        build_site(self.campaigns, self.site)
        index_html = (self.site / "index.html").read_text()

        # Check harness mappings
        self.assertIn("agy (gemini4argon) · line: exp1-sync-zero-redundancy · base 5e84ca92 · 1 candidate · 69 guests / 1 build", index_html)
        self.assertIn("codex (gpt-6-astra) · line: demand · base 5e84ca92 · 1 candidate · 11 guests / 3 builds", index_html)
        self.assertIn("grok-bot / claudecode (opus5.5) · line: xswap · base 5e84ca92 · 0 candidates · 94 guests / 0 builds", index_html)
        self.assertIn("claudecode (opus5.5) · line: xswap · base 37de636c · 0 candidates · 0 guests / 0 builds", index_html)

    def test_dated_campaign_folder_creates_undated_alias(self):
        self._create_campaign("exp3-async-zswap-prefetch-2026-11-06")
        build_site(self.campaigns, self.site)
        self.assertTrue((self.site / "exp3-async-zswap-prefetch-2026-11-06" / "index.html").exists())
        self.assertTrue((self.site / "exp3-async-zswap-prefetch" / "index.html").exists())

    def test_campaign_deduplication_by_folder(self):
        # Create campaign with both root report/explainer.html and nested dated explainer.html
        camp_dir = self.campaigns / "exp1-sync-zero-redundancy"
        camp_dir.mkdir(parents=True)
        (camp_dir / "campaign.json").write_text(json.dumps({"line": "exp1-sync-zero-redundancy"}))

        # Root undated explainer
        root_report = camp_dir / "report"
        root_report.mkdir(parents=True)
        (root_report / "explainer.html").write_text("<html><body>Old Undated</body></html>")
        (root_report / "explainer.json").write_text(json.dumps({"title": "Old Root", "verdict": {"headline": "Old"}}))

        # Nested dated explainer
        nested_report = root_report / "exp1-sync-zero-redundancy-2026-11-06"
        nested_report.mkdir(parents=True)
        (nested_report / "explainer.html").write_text("<html><body>New Dated</body></html>")
        (nested_report / "explainer.json").write_text(json.dumps({
            "title": "New Dated",
            "date": "2026-11-06",
            "verdict": {"headline": "New"},
        }))

        build_site(self.campaigns, self.site)
        index_html = (self.site / "index.html").read_text()

        # Should only have one card for exp1
        self.assertEqual(index_html.count("href=\"exp1-sync-zero-redundancy"), 1)
        self.assertIn("href=\"exp1-sync-zero-redundancy-2026-11-06/\"", index_html)
        self.assertNotIn("href=\"exp1-sync-zero-redundancy/\"", index_html)
        # But both directories should exist in _site so URLs resolve cleanly
        self.assertTrue((self.site / "exp1-sync-zero-redundancy-2026-11-06" / "index.html").exists())
        self.assertTrue((self.site / "exp1-sync-zero-redundancy" / "index.html").exists())

    def test_hide_hostnames_and_protocol_jargon(self):
        self._create_campaign(
            "exp-test-machine",
            camp_json={"line": "exp-line", "machine": "hurricpc"},
            subtitle="protocol rev7 · on hurricpc-wsl · base 5e84ca92",
            date_in_spec="2026-11-06",
        )

        build_site(self.campaigns, self.site)
        index_html = (self.site / "index.html").read_text()

        self.assertNotIn("hurricpc", index_html.lower())
        self.assertNotIn("rev7", index_html)


if __name__ == "__main__":
    unittest.main()
