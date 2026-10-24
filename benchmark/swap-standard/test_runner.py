# SPDX-License-Identifier: GPL-2.0-only
"""Runner validation tests; no guest launches."""
import argparse
import re
import subprocess
import shlex
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
spec = importlib.util.spec_from_file_location("standard_runner", BASE / "run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerValidationTests(unittest.TestCase):
    def test_swap_preallocation_is_real_and_failure_cleans_owned_image(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "swap.raw"
            runner.create_swap_image(path, True, 4096)
            self.assertEqual(path.stat().st_size, 4096)
            self.assertGreaterEqual(path.stat().st_blocks * 512, 4096)
            with self.assertRaises(FileExistsError):
                runner.create_swap_image(path, True, 8192)
            self.assertEqual(path.stat().st_size, 4096)
            path.unlink()
            with patch.object(runner.os, "posix_fallocate", side_effect=OSError("no space")):
                with self.assertRaises(OSError):
                    runner.create_swap_image(path, True, 4096)
            self.assertFalse(path.exists())

    def test_correctness_routes(self):
        for backend in ('disk', 'zswap'):
            runner.validate_workload(backend, 'xswap', 'correctness')
        for backend, mode in (('disk', 'plain'), ('zram', 'xswap'), ('brd', 'xswap')):
            with self.assertRaises(ValueError):
                runner.validate_workload(backend, mode, 'correctness')

    def test_swap_peak_output_retains_zero_usage(self):
        script = (BASE / "bench.sh").read_text()
        function = re.search(r"^report_swap_peaks\(\) \{.*?^\}", script, re.M | re.S).group(0)
        with tempfile.TemporaryDirectory() as directory:
            samples = Path(directory) / "samples"
            samples.write_text("/dev/vda 0\nxswap1 64\n/dev/vda 0\nxswap1 32\n")
            function = function.replace("/tmp/swaps.samples", shlex.quote(str(samples)))
            output = subprocess.check_output(["bash", "-c", function + "\nreport_swap_peaks"], text=True)
        self.assertEqual(output, "SWAP_PEAK_BEGIN\n/dev/vda 0\nxswap1 64\nSWAP_PEAK_END\n")

    def test_run_id_valid(self):
        for value in ("a", "A0_zz-9", "x" * 96):
            with self.subTest(value=value):
                self.assertEqual(runner.run_id(value), value)

    def test_run_id_rejects_paths_and_invalid_names(self):
        for value in ("", ".", "..", "../escape", "/tmp/run", "a/b", "a b",
                      "x" * 97, "é", "a\n", "a.b", "a\x00"):
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    runner.run_id(value)

    def test_stop_file_must_be_absolute(self):
        self.assertEqual(runner.absolute_stop_file("/tmp/campaign/STOP"),
                         Path("/tmp/campaign/STOP"))
        for value in ("", "STOP", "../STOP", "~/STOP"):
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    runner.absolute_stop_file(value)

    def test_either_stop_file_stops_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            global_stop, extra = root / "global", root / "campaign"
            with patch.object(runner, "STOP", global_stop):
                self.assertFalse(runner.stop_requested())
                self.assertFalse(runner.stop_requested(extra))
                extra.touch()
                self.assertTrue(runner.stop_requested(extra))
                self.assertFalse(runner.stop_requested())
                extra.unlink()
                global_stop.touch()
                self.assertTrue(runner.stop_requested())
                self.assertTrue(runner.stop_requested(extra))

    def test_existing_run_evidence_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "runs"
            dest = runner.create_run_directory(root, "trial_1")
            evidence = dest / "result.json"
            evidence.write_text("prior evidence")
            with self.assertRaises(FileExistsError):
                runner.create_run_directory(root, "trial_1")
            self.assertEqual(evidence.read_text(), "prior evidence")

    def test_existing_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "trial").symlink_to(root / "missing", target_is_directory=True)
            with self.assertRaises(FileExistsError):
                runner.create_run_directory(root, "trial")
            self.assertFalse((root / "missing").exists())


if __name__ == "__main__":
    unittest.main()
