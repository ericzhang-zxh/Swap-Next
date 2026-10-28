# SPDX-License-Identifier: GPL-2.0-only
"""Closed campaign starts fail before runtime artifacts; all tests are guest-free."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load_runner(suite):
    path = ROOT / "benchmark" / suite
    dependencies = ("evidence", "lifetime", "validity", "regimes")
    modules = {key: value for key, value in sys.modules.items() if key not in dependencies}
    with patch.dict(sys.modules, modules, clear=True), \
         patch.object(sys, "path", [str(path), str(ROOT / "benchmark/kernel"), str(ROOT / "evolve/control"), *sys.path]):
        spec = importlib.util.spec_from_file_location("boundary_" + suite, path / "run.py")
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
    return runner


class ExecutionBoundaryTests(unittest.TestCase):
    def test_legacy_runners_refuse_closed_before_runtime_artifacts(self):
        for suite in ("kernel", "xswap", "xswap-structure", "xswap-hole-probe", "xswap-p123"):
            with self.subTest(suite=suite), tempfile.TemporaryDirectory() as temporary:
                runner = load_runner(suite)
                project = Path(temporary)
                base = project / "benchmark" / suite
                base.mkdir(parents=True)
                (base / "protocol.json").write_text(json.dumps({"campaign": "closed", "baseline_commit": "a" * 40}))
                argv = ["run.py", "--build", "b", "--backend", "disk"]
                if suite == "kernel":
                    argv += ["--campaign", "closed"]
                if suite == "xswap-p123":
                    argv += ["--workload", "swapin"]
                with patch.object(runner, "PROJECT", project), patch.object(runner, "BASE", base), \
                     patch.object(sys, "argv", argv), patch.object(runner.os, "geteuid", return_value=1000), \
                     patch.dict("os.environ", {"SWAP_NEXT_ACCEL": "kvm"}), \
                     patch.object(runner.campaign_store, "require_execution", side_effect=runner.campaign_store.CampaignError("closed")) as gate, \
                     patch.object(runner.subprocess, "Popen") as launch:
                    with self.assertRaisesRegex(runner.campaign_store.CampaignError, "closed"):
                        runner.main()
                    gate.assert_called_once()
                    launch.assert_not_called()
                self.assertEqual([p.relative_to(project).as_posix() for p in project.rglob("*") if p.is_file()],
                                 ["benchmark/" + suite + "/protocol.json"])

    def test_confirmation_refuses_closed_before_writing_ledger(self):
        spec = importlib.util.spec_from_file_location("boundary_confirm", ROOT / "evolve/confirm.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            protocol = project / "protocol.json"
            protocol.write_text(json.dumps({"campaign": "closed"}))
            with patch.object(module, "PROJECT", project), \
                 patch.object(sys, "argv", ["confirm.py", "--protocol", str(protocol)]), \
                 patch.object(module.campaign_store, "require_execution", side_effect=module.campaign_store.CampaignError("closed")), \
                 patch.object(module.subprocess, "run") as launch:
                with self.assertRaisesRegex(module.campaign_store.CampaignError, "closed"):
                    module.main()
                launch.assert_not_called()
            self.assertEqual(list(project.iterdir()), [protocol])


if __name__ == "__main__":
    unittest.main()
