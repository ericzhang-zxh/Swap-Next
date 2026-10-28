# SPDX-License-Identifier: GPL-2.0-only
"""Relocation checks; no build or guest execution."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load_adapter():
    """Import evolve/loop.py with OpenEvolve stubbed out."""
    for name in ("openevolve", "openevolve.config", "openevolve.database", "openevolve.evaluator"):
        module = sys.modules.setdefault(name, types.ModuleType(name))
        for attr in ("DatabaseConfig", "EvaluatorConfig", "Program", "ProgramDatabase", "Evaluator"):
            setattr(module, attr, object)
    spec = importlib.util.spec_from_file_location("evolve_loop", ROOT / "evolve/loop.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LayoutTests(unittest.TestCase):

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

    def test_adapter_state_layout(self):
        loop = load_adapter()
        for name in ("kernel", "xswap"):
            suite = loop.Suite(name)
            self.assertEqual(suite.state, ROOT / "evolve" / name / "state-layout-v1")
            self.assertEqual(suite.bench, ROOT / "benchmark" / name)
        # The xswap evaluator reads the calibration report the adapter writes.
        evaluator = (ROOT / "benchmark/xswap/evaluate_kernel.py").read_text()
        self.assertIn("BASE / 'state-layout-v1/calibration.json'", evaluator)
        self.assertEqual(loop.Suite("xswap").campaign, "xswap-2026-10-21")
        self.assertIsNone(loop.Suite("kernel").campaign)

    def test_frozen_deadline_and_acceptance(self):
        protocol = json.loads((ROOT / "benchmark/xswap/protocol.json").read_text())
        self.assertEqual(protocol["deadline_utc"], "2026-10-21T12:52:23+00:00")
        self.assertFalse(protocol["performance_accepted"])
        self.assertFalse(protocol["auto_promote"])
        policy = json.loads((ROOT / "evolve/control/config/policy.json").read_text())
        self.assertFalse(policy["runtime_enabled"])
        self.assertFalse(policy["thresholds_calibrated"])

    def test_stop_paths_follow_campaign_layout(self):
        run = (ROOT / "benchmark/xswap/run.py").read_text()
        self.assertIn('PROJECT/"campaigns/STOP"', run)
        self.assertIn('PROJECT/"campaigns/xswap-2026-10-21/STOP"', run)
        for path in ("kernel/build.py", "kernel/run.py", "swap-standard/run.py", "xswap-p123/run.py"):
            with self.subTest(path=path):
                self.assertRegex((ROOT / "benchmark" / path).read_text(), r'PROJECT ?/ ?"campaigns/STOP"')

    def test_adapter_reads_campaign_candidates(self):
        loop = load_adapter()
        seen = []
        loop.campaign_store.candidates = lambda name: seen.append(name) or {"c": {"worktree": "w"}}
        self.assertEqual(loop.Suite("xswap").candidates(), {"c": {"worktree": "w"}})
        self.assertEqual(seen, ["xswap-2026-10-21"])


if __name__ == "__main__":
    unittest.main()
