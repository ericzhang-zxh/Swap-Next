# SPDX-License-Identifier: GPL-2.0-only
"""Relocation checks; no build or guest execution."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("settings_validator", ROOT / "benchmark/validate_settings.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)

class LayoutTests(unittest.TestCase):
    def test_settings_match_sources(self):
        self.assertEqual(validator.validate(), [])

    def test_settings_detect_source_drift(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "input.py").write_text("changed")
            (root / "settings.json").write_text(json.dumps({
                "source_sha256": {"input.py": "0" * 64}, "protocol_snapshots": {}}))
            self.assertEqual(validator.validate(root), ["settings source drift: input.py"])

    def test_runner_and_builder_cli(self):
        for path in ("kernel/build.py", "kernel/run.py", "kernel/prepare-rootfs.py",
                     "xswap/run.py", "xswap/prepare-rootfs.py"):
            with self.subTest(path=path):
                result = subprocess.run(["python3", str(ROOT / "benchmark" / path), "--help"],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_config_paths_exist(self):
        for suite, name in (("kernel", "kernel.config"), ("xswap", "xswap-kernel.config")):
            source = (ROOT / "benchmark" / suite / "evaluate_kernel.py").read_text()
            self.assertIn("benchmark/config/" + name, source)
            self.assertNotIn("benchmark/benchmark/", source)
            self.assertTrue((ROOT / "benchmark/config" / name).is_file())

    def test_state_separation_and_calibration_path(self):
        for suite in ("kernel", "xswap"):
            source = (ROOT / "evolve" / suite / "loop.py").read_text()
            self.assertIn('state=ADAPTER/"state-layout-v1"', source)
            self.assertIn('BASE=PROJECT/"benchmark"/"' + suite + '"', source)
        loop = (ROOT / "evolve/xswap/loop.py").read_text()
        evaluator = (ROOT / "benchmark/xswap/evaluate_kernel.py").read_text()
        self.assertIn('BASE/"state-layout-v1"/"calibration.json"', loop)
        self.assertIn("BASE / 'state-layout-v1/calibration.json'", evaluator)
        self.assertNotIn("state-v2", loop + evaluator)

    def test_frozen_deadline_and_acceptance(self):
        protocol = json.loads((ROOT / "benchmark/xswap/protocol.json").read_text())
        self.assertEqual(protocol["deadline_utc"], "2026-10-21T12:52:23+00:00")
        self.assertFalse(protocol["performance_accepted"])
        self.assertFalse(protocol["auto_promote"])
        policy = json.loads((ROOT / "system/config/policy.json").read_text())
        self.assertFalse(policy["runtime_enabled"])
        self.assertFalse(policy["thresholds_calibrated"])

if __name__ == "__main__":
    unittest.main()
