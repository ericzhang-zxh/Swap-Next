# SPDX-License-Identifier: GPL-2.0-only
"""Runner validation tests; no guest launches."""
import argparse
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
