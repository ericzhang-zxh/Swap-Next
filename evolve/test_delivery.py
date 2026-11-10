# SPDX-License-Identifier: GPL-2.0-only
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from evolve import delivery as d

REPO = Path(__file__).resolve().parents[1]


def fixture(root, *, closed=True):
    directory = root / "campaigns/test-line"
    directory.mkdir(parents=True)
    d.write(directory / "campaign.json", {"campaign": "test-line", "line": "xswap",
            "status": "closed" if closed else "open", "machine": "fixture"})
    d.write(directory / "policy.json", {"seed_ref": "a" * 40})
    d.write(directory / "protocol.json", {"campaign": "test-line", "baseline_commit": "a" * 40,
                                         "required_correctness_gates": ["data_roundtrip"]})
    d.write(directory / "ledger/budget.json", {"guests": 7, "probe_guests": 3})
    d.write(directory / "candidates/one.json", {"id": "one", "status": "closed",
            "hypothesis": "Reduce readahead cost", "candidate_commit": "b" * 40, "source_tree": "c" * 40})
    metric = "disk.swapin_seq.mean_ns"
    row = {"id": "eval-one", "action": "evaluate", "tier": "fast", "candidate": "one",
           "candidate_commit": "b" * 40, "candidate_tree": "c" * 40,
           "status": "FAST_PASS", "runs": [],
           "pairs": [{"a": {metric: 100.0}, "b": {metric: 85.0}}],
           "analysis": {"primary": [metric], "metrics": {metric: {"guard_pass": True},
                        "disk.swapin_seq.p99_ns": {"guard_pass": False, "advisory": True}}}}
    d.write(directory / "ledger/ledger.json", [row])
    renderer = root / ".agents/skills/explaining-campaign-results/scripts/build_page.py"
    renderer.parent.mkdir(parents=True)
    shutil.copy2(REPO / ".agents/skills/explaining-campaign-results/scripts/build_page.py", renderer)
    return directory


def explain(root):
    summary = d.extract(root, "test-line")
    story = d.story_template(summary)
    story["headline"] = "A fast screen needs further review."
    for item in story.get("patches", []):
        item["patch"] = (root / item["source"]).read_text()
    ref = "campaigns/test-line/ledger/ledger.json"
    for section in story["sections"]:
        section["evidence"] = [ref]
        section["lead"] = "Schematic of the measured path."
        section["blocks"] = [{"type": "flow", "takeaway": "Application access reaches swap",
                              "nodes": [{"id": "a", "label": "Application", "col": 0, "row": 0},
                                        {"id": "b", "label": "Swap", "col": 1, "row": 0}],
                              "edges": [{"from": "a", "to": "b", "label": "fault"}]}]
    d.write(root / "campaigns/test-line/report/story.json", story)
    return story


def visual(root, artifact):
    views = []
    for width in (390, 1200):
        for theme in ("light", "dark"):
            relative = f"campaigns/test-line/report/qa/{width}-{theme}.png"
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture screenshot, not real visual verification")
            views.append({"width": width, "theme": theme, "screenshot": relative,
                          "sha256": d.digest_bytes(path.read_bytes()),
                          **{name: True for name in d.VISUAL_CHECKS}})
    return {"artifact_sha256": artifact, "views": views}


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.campaign = fixture(self.root)

    def test_closed_campaign_report_is_derived_and_idempotent(self):
        explain(self.root)
        first = d.render(self.root, "test-line")
        self.assertEqual(first, d.render(self.root, "test-line"))
        summary = d.read(self.campaign / "report/summary.json")
        self.assertEqual(summary["budget"]["guests"], 7)
        self.assertFalse(summary["performance_accepted"])
        self.assertEqual(summary["regressions"][0]["advisory"], True)
        spec = d.read(self.campaign / "report/explainer.json")
        result = next(s for s in spec["sections"] if s["id"] == "results")
        self.assertEqual([p["value"] for p in result["blocks"][0]["points"]], [100.0, 85.0])
        html = (self.campaign / "report/explainer.html").read_text()
        self.assertIn('<details class="audit">', html)
        self.assertNotIn('<details class="audit" open', html)
        self.assertEqual(d.status(self.root, "test-line")["state"], "generated")
        self.assertFalse((self.campaign / "runs").exists())

    def test_noisy_calibration_exposes_samples_without_candidate_claim(self):
        metric = "metadata_delta_bytes_per_capacity_slot"
        samples = [0.115, 0.115, 0.123]
        row = {"id": "cal-one", "action": "calibrate", "tier": "probe",
               "status": "CALIBRATION_NOISY", "analysis": {
                   "bands": {"metadata-brd": {metric: {"n": 3}}},
                   "reasons": ["metadata-brd: METADATA_CALIBRATION_NOISY"]},
               "runs": [{"id": "run-" + str(i), "case": "metadata-brd", "status": "PASS",
                         "run_valid": True, "metrics": {metric: value}}
                        for i, value in enumerate(samples)]}
        d.write(self.campaign / "ledger/ledger.json", [row])
        explain(self.root)
        d.render(self.root, "test-line")
        summary = d.read(self.campaign / "report/summary.json")
        self.assertEqual(summary["verdict"], "inconclusive")
        spec = d.read(self.campaign / "report/explainer.json")
        results = next(s for s in spec["sections"] if s["id"] == "results")
        chart = results["blocks"][0]
        self.assertEqual([p["value"] for p in chart["points"]], [1000 * v for v in samples])
        self.assertIn("1,000 capacity slots", chart["x_label"])
        self.assertEqual(chart["series"], ["Baseline"])
        self.assertIn("No complete paired", results["blocks"][-1]["text"])
        limits = next(s for s in spec["sections"] if s["id"] == "limits")
        self.assertIn("METADATA_CALIBRATION_NOISY", limits["blocks"][0]["text"])
        self.assertEqual(spec["verdict"]["tiles"][0]["value"], "No paired result")
        html = (self.campaign / "report/explainer.html").read_text()
        self.assertIn('class="narrow-only"', html)
        self.assertIn('viewBox="0 0 340 ', html)

    def test_pinned_source_links_require_matching_committed_bytes(self):
        story = explain(self.root)
        story["source_commit"] = "e" * 40
        d.write(self.campaign / "report/story.json", story)
        def committed(root, command, spec):
            self.assertEqual(command, "show")
            commit, path = spec.split(":", 1)
            self.assertEqual(commit, "e" * 40)
            return (root / path).read_bytes()
        with patch.object(d, "_git", side_effect=committed):
            d.render(self.root, "test-line")
        html = (self.campaign / "report/explainer.html").read_text()
        self.assertIn("/blob/" + "e" * 40 + "/campaigns/test-line/protocol.json", html)
        with patch.object(d, "_git", return_value=b"different source"):
            with self.assertRaisesRegex(ValueError, "differs from current evidence"):
                d.render(self.root, "test-line")

    def test_drift_invalidates_explanation_and_delivery(self):
        explain(self.root)
        d.render(self.root, "test-line")
        ledger = self.campaign / "ledger/ledger.json"
        rows = d.read(ledger)
        rows[0]["status"] = "CORRECTNESS_FAIL"
        d.write(ledger, rows)
        self.assertEqual(d.status(self.root, "test-line")["state"], "pending")
        with self.assertRaisesRegex(ValueError, "changed evidence"):
            d.render(self.root, "test-line")

    def test_missing_or_fake_narrative_evidence_is_refused(self):
        story = explain(self.root)
        story["sections"][0]["evidence"] = ["fake.json"]
        with self.assertRaisesRegex(ValueError, "source references"):
            d.make_spec(d.extract(self.root, "test-line"), story)
        story = explain(self.root)
        story["sections"][1]["blocks"] = [{"type": "bars", "values": [999]}]
        with self.assertRaisesRegex(ValueError, "numerical charts"):
            d.make_spec(d.extract(self.root, "test-line"), story)

    def test_raw_missing_is_explicit_and_hash_mismatch_is_rejected(self):
        ledger = self.campaign / "ledger/ledger.json"
        rows = d.read(ledger)
        ref = "campaigns/test-line/runs/one/result.json"
        rows[0]["runs"] = [{"id": "one", "result": ref, "result_sha256": "0" * 64}]
        d.write(ledger, rows)
        self.assertEqual(d.extract(self.root, "test-line")["missing_raw_evidence"], [ref])
        d.write(self.root / ref, {})
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            d.extract(self.root, "test-line")

    def test_nan_and_source_escape_fail_closed(self):
        path = self.campaign / "ledger/ledger.json"
        path.write_text('[{"id":"bad","analysis":{"score":NaN}}]')
        with self.assertRaisesRegex(ValueError, "non-finite"):
            d.extract(self.root, "test-line")
        with self.assertRaises(ValueError):
            d.at(self.root, "../outside")
        link = self.root / "escape"
        link.symlink_to("/tmp")
        with self.assertRaisesRegex(ValueError, "symlinks"):
            d.at(self.root, "escape/anything", exists=False)

    def test_artifact_and_visual_bindings(self):
        explain(self.root)
        receipt = d.render(self.root, "test-line")
        evidence = visual(self.root, receipt["artifacts"]["explainer.html"])
        bad = copy.deepcopy(evidence)
        bad["views"].pop()
        with self.assertRaisesRegex(ValueError, "both themes"):
            d.record_visual_check(self.root, "test-line", bad)
        bad = copy.deepcopy(evidence)
        bad["views"][0]["no_overflow"] = False
        with self.assertRaisesRegex(ValueError, "incomplete"):
            d.record_visual_check(self.root, "test-line", bad)
        d.record_visual_check(self.root, "test-line", evidence)
        self.assertEqual(d.status(self.root, "test-line")["state"], "visually_checked")
        (self.campaign / "report/explainer.html").write_text("changed")
        self.assertEqual(d.status(self.root, "test-line")["state"], "pending")

    def test_exact_pages_commit_and_live_artifacts_required(self):
        explain(self.root)
        receipt = d.render(self.root, "test-line")
        d.record_visual_check(self.root, "test-line", visual(self.root, receipt["artifacts"]["explainer.html"]))
        body = (self.campaign / "report/explainer.html").read_bytes()
        run = {"head_sha": "f" * 40, "status": "completed", "conclusion": "success",
               "path": ".github/workflows/pages.yml"}
        def fetch(url):
            return body if url.endswith("/test-line/") else b'<a href="test-line/">report</a>'
        with patch.object(d, "_git", return_value=body):
            with self.assertRaisesRegex(ValueError, "exact commit"):
                d.verify_live(self.root, "test-line", "a" * 40, "123", fetch=fetch, github=lambda _: run)
            verified = d.verify_live(self.root, "test-line", "f" * 40, "123", fetch=fetch, github=lambda _: run)
            self.assertEqual(verified["state"], "live_verified")
            with self.assertRaisesRegex(ValueError, "live HTML"):
                d.verify_live(self.root, "test-line", "f" * 40, "123",
                              fetch=lambda _: b"wrong", github=lambda _: run)
        self.assertEqual(d.status(self.root, "test-line")["state"], "live_verified")

    def test_report_overview_does_not_expose_host_paths(self):
        rows = d.read(self.campaign / "ledger/ledger.json")
        rows[0]["reason"] = "missing /home/alice/private/result.json"
        d.write(self.campaign / "ledger/ledger.json", rows)
        summary = d.extract(self.root, "test-line")
        self.assertNotIn("/home/alice", json.dumps(summary))
        self.assertIn("[local path]", summary["evaluations"][0]["reason"])

    def test_unified_metadata_subtitle(self):
        story = explain(self.root)
        spec = d.make_spec(d.extract(self.root, "test-line"), story)
        self.assertIn("subtitle", spec)
        sub = spec["subtitle"]
        self.assertIn("line: xswap", sub)
        self.assertIn("base aaaaaaaa", sub)
        self.assertIn("1 candidate", sub)
        self.assertIn("10 guests / 0 builds", sub)
        self.assertNotIn("hurricpc", sub)
        self.assertNotIn("rev7", sub)



    def test_patches_section_renders_diffs_and_validates_sources(self):
        patch_path = self.campaign / "patches/one.patch"
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_text("--- a/mm/xswap.c\n+++ b/mm/xswap.c\n@@ -1,2 +1,3 @@\n+bool xswap_load_batch(void);\n")
        story = explain(self.root)
        story["patches"] = [{"takeaway": "M1 batch swap-in loader",
                             "source": "campaigns/test-line/patches/one.patch",
                             "patch": patch_path.read_text()}]
        d.write(self.campaign / "report/story.json", story)
        d.render(self.root, "test-line")
        html = (self.campaign / "report/explainer.html").read_text()
        md = (self.campaign / "report/REPORT.md").read_text()
        self.assertIn("Core kernel patches", html)
        self.assertIn("xswap_load_batch", html)
        self.assertIn("## Core kernel patches", md)
        self.assertIn("```diff", md)
        story["patches"][0]["source"] = "campaigns/test-line/ledger/ledger.json"
        with self.assertRaisesRegex(ValueError, "patch source reference"):
            d.make_spec(d.extract(self.root, "test-line"), story)


if __name__ == "__main__":
    unittest.main()

