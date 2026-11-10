# SPDX-License-Identifier: GPL-2.0-only
"""Runner validation tests; no guest launches."""
import argparse
from types import SimpleNamespace
import json
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

    def test_run_root_must_be_inside_campaigns(self):
        campaigns = runner.PROJECT / "campaigns"
        good = campaigns / "x/runs/guests"
        self.assertEqual(runner.run_root(str(good)), good.resolve())
        for value in ("/tmp/x/runs/guests", str(campaigns / "x/runs"), "campaigns/x/runs/guests",
                      str(campaigns / "runs/guests"), str(campaigns / "x/../../tmp/runs/guests"),
                      str(campaigns / "x/y/runs/guests")):
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    runner.run_root(value)
                argv = ["run.py", "--build", "b", "--backend", "disk", "--workload", "swapin",
                        "--run-root", value]
                with patch.object(sys, "argv", argv), patch.object(runner.os, "geteuid") as euid, \
                     patch("sys.stderr"), self.assertRaises(SystemExit) as raised:
                    runner.main()
                self.assertEqual(raised.exception.code, 2)
                euid.assert_not_called()

    def test_execution_requires_explicit_matching_campaign_identity(self):
        default = BASE / "runs"
        missing = SimpleNamespace(campaign=None, run_root=default)
        with self.assertRaisesRegex(runner.campaign_store.CampaignError, "explicit campaign"):
            runner.execution_campaign(missing)
        for campaign, root, expected in (("a", default, "a"),
                                         (None, runner.PROJECT / "campaigns/a/runs/guests", "a")):
            args = SimpleNamespace(campaign=campaign, run_root=root)
            with patch.object(runner.campaign_store, "require_execution") as gate:
                self.assertEqual(runner.execution_campaign(args), expected)
                gate.assert_called_once_with(expected)
        args = SimpleNamespace(campaign="b", run_root=runner.PROJECT / "campaigns/a/runs/guests")
        with patch.object(runner.campaign_store, "require_execution") as gate:
            with self.assertRaisesRegex(runner.campaign_store.CampaignError, "different campaigns"):
                runner.execution_campaign(args)
            gate.assert_not_called()

    def test_closed_guest_is_refused_before_runtime_lock_or_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            argv = ["run.py", "--build", "b", "--backend", "disk", "--workload", "swapin", "--campaign", "closed"]
            with patch.object(runner, "PROJECT", project), patch.object(sys, "argv", argv), \
                 patch.object(runner.os, "geteuid", return_value=1000), \
                 patch.object(runner.campaign_store, "require_execution", side_effect=runner.campaign_store.CampaignError("campaign closed is closed")), \
                 patch.object(runner, "validate") as validate, patch.object(runner.subprocess, "Popen") as launch:
                with self.assertRaisesRegex(SystemExit, "closed"):
                    runner.main()
                validate.assert_not_called()
                launch.assert_not_called()
            self.assertEqual(list(project.iterdir()), [])

    def test_unreserved_guest_refuses_before_any_runtime_write(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            argv = ["run.py", "--build", "b", "--backend", "disk", "--workload", "swapin", "--campaign", "demo"]
            with patch.object(runner, "PROJECT", project), patch.object(sys, "argv", argv), \
                 patch.object(runner.os, "geteuid", return_value=1000), \
                 patch.object(runner.campaign_store, "require_execution"), \
                 patch.object(runner, "validate") as validate, patch.object(runner.subprocess, "Popen") as launch:
                with self.assertRaisesRegex(SystemExit, "counted --reservation"):
                    runner.main()
                validate.assert_not_called()
                launch.assert_not_called()
            self.assertEqual(list(project.iterdir()), [])

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

    def test_kvm_is_default_and_tcg_guest_is_4gib(self):
        kvm_default, dmem, dcpus, daccel = runner.guest_shape({})
        self.assertFalse(kvm_default)
        self.assertEqual((dmem, dcpus), (8192, "8"))
        self.assertIn("-enable-kvm", daccel)
        tcg, mem, cpus, accel = runner.guest_shape({"SWAP_NEXT_ACCEL": "tcg"})
        self.assertTrue(tcg)
        self.assertEqual((mem, cpus), (4096, "4"))
        self.assertEqual(accel, ["-accel", "tcg,thread=multi,tb-size=256", "-machine", "pc", "-cpu", "max"])
        self.assertNotIn("-enable-kvm", accel)
        overridden, small, _, _ = runner.guest_shape({"SWAP_NEXT_ACCEL": "tcg", "SWAP_NEXT_TCG_MEM_MIB": "2560"})
        self.assertTrue(overridden)
        self.assertEqual(small, 2560)
        kvm, kmem, kcpus, kaccel = runner.guest_shape({"SWAP_NEXT_ACCEL": "kvm"})
        self.assertFalse(kvm)
        self.assertEqual((kmem, kcpus), (8192, "8"))
        self.assertIn("-enable-kvm", kaccel)
        with self.assertRaises(ValueError):
            runner.guest_shape({"SWAP_NEXT_ACCEL": "tcg", "SWAP_NEXT_TCG_MEM_MIB": "0"})
        with self.assertRaises(ValueError):
            runner.guest_shape({"SWAP_NEXT_ACCEL": "tcg,thread=multi"})

    def test_swap_image_preallocate_and_sparse_sizes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sparse, full = root / "sparse", root / "full"
            runner.create_swap_image(sparse, False, 8192)
            runner.create_swap_image(full, True, 4096)
            self.assertEqual(sparse.stat().st_size, 8192)
            self.assertEqual(full.stat().st_size, 4096)

    def test_xswap_without_linux_checkout_errors_out_early(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            argv = ["run.py", "--build", "xs-desc-v1", "--backend", "disk",
                    "--mode", "xswap", "--workload", "swapin"]
            with patch.object(runner, "PROJECT", project), patch.object(sys, "argv", argv), \
                 patch.object(runner.os, "geteuid", return_value=1000), \
                 patch.object(runner, "validate", side_effect=AssertionError("validated")):
                with self.assertRaisesRegex(SystemExit, "linux/ checkout missing"):
                    runner.main()
                with self.assertRaisesRegex(SystemExit, "linux/ checkout missing"):
                    runner.has_lifetime_fix(runner.LIFETIME_FIX)
            self.assertEqual(list(project.iterdir()), [])

    @unittest.skipUnless((runner.PROJECT / "linux" / ".git").exists(), "needs the linux/ checkout")
    def test_lifetime_fix_check_needs_a_real_commit(self):
        self.assertTrue(runner.has_lifetime_fix(runner.LIFETIME_FIX))
        with self.assertRaisesRegex(ValueError, "not a full SHA"):
            runner.has_lifetime_fix("not-a-commit")
        with self.assertRaisesRegex(ValueError, "cannot check"):
            runner.has_lifetime_fix("0" * 40)
        self.assertFalse(runner.needs_lifetime_fix("plain", "swapin"))
        self.assertFalse(runner.needs_lifetime_fix("xswap", "lifetime"))

    def test_runner_does_not_offline_host_cpus(self):
        text = (BASE / "run.py").read_text() + (BASE / "bench.sh").read_text()
        self.assertNotIn("/sys/devices/system/cpu", text)

    def test_revision6_matches_tcg_qemu_and_excludes_build(self):
        protocol = json.loads((runner.PROJECT / "campaigns/xswap-tcg-kbench-2026-10-29/protocol.json").read_text())
        tcg, mem, cpus, accel = runner.guest_shape({"SWAP_NEXT_ACCEL": "tcg"})
        self.assertTrue(tcg)
        self.assertEqual(protocol["accelerator"]["qemu"], accel)
        self.assertEqual((protocol["guest"]["mem_mib"], str(protocol["guest"]["vcpus"])), (mem, cpus))
        self.assertIn("470M", runner.excluded_workload_reason(protocol, "build"))
        self.assertIsNone(runner.excluded_workload_reason(protocol, "swapin"))
        self.assertIn("-enable-kvm", runner.guest_shape({})[3])

    def _execution_argv(self, workload):
        return ["run.py", "--build", "b", "--backend", "disk", "--mode", "plain",
                "--preallocate-swap", "--workload", workload, "--campaign", "demo",
                "--run-id", "run-1", "--reservation", "/tmp/ticket.json",
                "--protocol-revision", "6"]

    def _frozen(self, require="tcg"):
        protocol = json.loads((runner.PROJECT / "campaigns/xswap-tcg-kbench-2026-10-29/protocol.json").read_text())
        protocol["accelerator"]["require"] = require
        return protocol

    def test_excluded_build_is_refused_before_reservation_or_qemu(self):
        argv = self._execution_argv("build")
        with patch.object(sys, "argv", argv), patch.object(runner.os, "geteuid", return_value=1000), \
             patch.dict(runner.os.environ, {"SWAP_NEXT_ACCEL": "tcg"}, clear=False), \
             patch.object(runner, "execution_campaign", return_value="demo"), \
             patch.object(runner.guest_budget, "protocol", return_value=self._frozen()), \
             patch.object(runner.guest_budget, "consume_guest") as consume, \
             patch.object(runner.subprocess, "Popen") as launch, \
             patch.object(runner, "validate") as validate:
            with self.assertRaisesRegex(SystemExit, "workload excluded by protocol: build"):
                runner.main()
            consume.assert_not_called()
            launch.assert_not_called()
            validate.assert_not_called()

    def test_kvm_result_cannot_satisfy_a_tcg_protocol(self):
        argv = self._execution_argv("swapin")
        with patch.object(sys, "argv", argv), patch.object(runner.os, "geteuid", return_value=1000), \
             patch.dict(runner.os.environ, {"SWAP_NEXT_ACCEL": "kvm"}, clear=False), \
             patch.object(runner, "execution_campaign", return_value="demo"), \
             patch.object(runner.guest_budget, "protocol", return_value=self._frozen()), \
             patch.object(runner.guest_budget, "consume_guest") as consume, \
             patch.object(runner.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(SystemExit, "accelerator does not match protocol"):
                runner.main()
            consume.assert_not_called()
            launch.assert_not_called()

    def test_swapin_passes_the_exclusion_check(self):
        argv = self._execution_argv("swapin")
        with patch.object(sys, "argv", argv), patch.object(runner.os, "geteuid", return_value=1000), \
             patch.dict(runner.os.environ, {"SWAP_NEXT_ACCEL": "tcg"}, clear=False), \
             patch.object(runner, "execution_campaign", return_value="demo"), \
             patch.object(runner.guest_budget, "protocol", return_value=self._frozen()), \
             patch.object(runner.guest_budget, "consume_guest",
                          side_effect=runner.campaign_store.CampaignError("reached-consume")), \
             patch.object(runner.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(SystemExit, "reached-consume"):
                runner.main()
            launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class CompressionRunnerTests(unittest.TestCase):
    def args(self, **updates):
        values = dict(backend='compressed', mode='xswap', workload='swapin', config_id='c1-common',
                      topology_id='single', correctness_case=None, protocol_revision=8)
        values.update(updates)
        return SimpleNamespace(**values)

    def test_revision8_timing_binds_target_and_commandline(self):
        args = self.args()
        frozen = {'protocol_revision': 8, 'input_config_sha256': 'a' * 64,
                  'compression_workload': {'target_bytes': 134217728},
                  'cases': {'swapin-compressed': {'backend': 'compressed', 'mode': 'xswap', 'workload': 'swapin'}}}
        config = SimpleNamespace(correctness_case=lambda p, name: None,
                                 pinned_config=lambda *a, **kw: {'input_config_sha256': 'a' * 64})
        with patch.dict(sys.modules, {'configurations': config}):
            runner.revision8_context(args, frozen)
            self.assertEqual(args.compression_target_bytes, 134217728)
            commandline = runner.guest_commandline(args, 'image')
            self.assertIn('bench.config_id=c1-common', commandline)
            self.assertIn('bench.compression_target_bytes=134217728', commandline)
            self.assertNotIn('bench.correctness_case', commandline)
            for changes in ({'compression_workload': {'target_bytes': 1073741824}}, {'cases': {}}):
                with self.assertRaises(ValueError):
                    runner.revision8_context(self.args(), dict(frozen, **changes))
            with self.assertRaises(ValueError):
                runner.revision8_context(self.args(config_id='standard'), frozen)

    def test_revision8_correctness_requires_exact_catalog_identity(self):
        case = dict(id='c-compressed', backend='compressed', mode='xswap', workload='compression',
                    config_id='c1-common', topology_id='single', group='compressed-roundtrip', subcases=['roundtrip'])
        config = SimpleNamespace(correctness_case=lambda p, name: dict(case),
                                 pinned_config=lambda *a, **kw: {'input_config_sha256': 'a' * 64})
        with patch.dict(sys.modules, {'configurations': config}):
            args = self.args(workload='compression', correctness_case='c-compressed')
            runner.revision8_context(args, {'protocol_revision': 8})
            commandline = runner.guest_commandline(args, 'image')
            self.assertIn('bench.correctness_case=c-compressed', commandline)
            self.assertIn('bench.compression_cases=roundtrip', commandline)
            self.assertEqual(args.expected_case, case)
            with self.assertRaises(ValueError):
                runner.revision8_context(self.args(workload='compression', correctness_case='c-compressed', mode='plain'),
                                         {'protocol_revision': 8})

    def test_topology_is_auxiliary_and_resource_bound(self):
        self.assertEqual(runner.topology_options('single', '4', 4096), [])
        numa = runner.topology_options('numa2', '4', 4096)
        self.assertEqual(numa.count('-numa'), 2)
        self.assertIn('node,nodeid=1,memdev=c1-node1,cpus=2-3', numa)
        for cpus, ram in ((8, 4096), (4, 8192)):
            with self.assertRaises(ValueError):
                runner.topology_options('numa2', cpus, ram)

    def test_compressed_route_cannot_escape_revision8(self):
        for revision, mode, workload in ((7, 'xswap', 'swapin'), (8, 'plain', 'swapin'), (8, 'xswap', 'metadata')):
            with self.assertRaises(ValueError):
                runner.validate_workload('compressed', mode, workload, revision)
        runner.validate_workload('compressed', 'xswap', 'swapin', 8)
        runner.validate_workload('compressed', 'xswap', 'compression', 8)
