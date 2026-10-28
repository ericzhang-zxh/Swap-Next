# SPDX-License-Identifier: GPL-2.0-only
"""Migration preserves scientific inputs and recovers interrupted filesystem work."""
import contextlib
import fcntl
import hashlib
import importlib.util
import io
import json
import multiprocessing
import os
import queue
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location("campaign_migration", Path(__file__).parents[1] / "migrate.py")
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


def import_in_process(root, output, started):
    """Real subprocess importer; all files and locks belong to the temp fixture."""
    started.set()
    try:
        migration.Migration(root).import_state()
        output.put(("ok", None))
    except Exception as exc:
        output.put((type(exc).__name__, str(exc)))


def locked_runtime_writer(lock, target, acquired, release, finished):
    lock, target = Path(lock), Path(target)
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        acquired.set()
        if not release.wait(10):
            raise RuntimeError("test writer was not released")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".writer.tmp")
        temporary.write_text('{"created": 10, "guests": 1, "probe_guests": 0, "builds": 0}')
        os.replace(temporary, target)
    finished.set()


def racing_unlocked_writer(target, request, finished):
    if not request.wait(10):
        raise RuntimeError("exclusive-create race was not requested")
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"created": 10, "guests": 1, "probe_guests": 0, "builds": 0}')
    finished.set()


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.write(".gitignore", "evolve/control/state/\nevolve/swap-standard/state*/\n")
        self.write("campaigns/hosts.json", {"hurricpc": {"hostnames": []}, "grok-cloud": {"hostnames": []}})
        self.names = ["swap-standard-2026-10-22", "xswap-2026-10-21", "xswap-next-2026-10-24", "xswap-tcg-rev3-2026-10-25", "controller-only"]
        self.write("campaigns/migration-seed.json", {"campaigns": {name: {
            "line": "plain" if name.startswith("swap-standard") else "xswap",
            "machine": "grok-cloud" if "tcg" in name else "hurricpc",
            "status": "open" if "tcg" in name else "closed",
            "baseline_from": None,
            **({"protocol_ref": "benchmark/xswap/protocol.json"} if name == "xswap-2026-10-21" else {})
        } for name in self.names}})
        for name in self.names:
            self.write(f"evolve/control/campaigns/{name}/policy.json", {"seed_ref": "a" * 40})
        for filename, name in [("protocol.json", self.names[0]), ("protocol-xswap-next-2026-10-24.json", self.names[2]), ("protocol-tcg-revision3.json", self.names[3])]:
            self.write("benchmark/swap-standard/" + filename, {"campaign": name, "baseline_commit": "a" * 40, "budget": {"guest_attempts": 120, "wall_seconds": 64800}})
        self.write("benchmark/xswap/protocol.json", {"campaign": self.names[1], "budget": {"guest_attempts": 200, "wall_seconds": 80000}})
        self.write("results/xswap-next-2026-10-24/REPORT.md", "Measured 42; [protocol](../../benchmark/swap-standard/protocol-xswap-next-2026-10-24.json#rules).\n")
        self.write("results/xswap-next-2026-10-24/explainer.html", '<a href="../../benchmark/swap-standard/protocol-xswap-next-2026-10-24.json">42</a>')
        self.write("results/swap-standard-evolve-2026-10-22/REPORT.md", "42\n")
        self.write("results/swap-standard-integration-2026-10-22/REPORT.md", "43\n")
        self.write("results/pilot-summary.json", {"count": 42})
        self.write("patches/xswap-next-2026-10-24/one.patch", "unchanged patch\n")
        self.write("patches/xswap-reference/one.patch", "reference\n")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.write("evolve/control/state/xswap-next-2026-10-24/candidates.json", {"one": {"id": "one", "worktree": str(self.root / "worktrees/xswap-next-2026-10-24/one"), "status": "closed"}})
        self.write("evolve/control/state/xswap-next-2026-10-24/one/candidate.patch", "unchanged patch\n")
        self.write("evolve/control/state/xswap-next-2026-10-24/one/task.json", {"worktree": str(self.root / "worktrees/xswap-next-2026-10-24/one")})
        self.write("evolve/control/state/xswap-next-2026-10-24/events.jsonl", json.dumps({"time_unix": 1792831186, "path": str(self.root / "worktrees/one")}) + "\n")
        self.write("evolve/swap-standard/state-xswap-next-2026-10-24/ledger.json", [{"report": str(self.root / "benchmark/swap-standard/evaluations/x/report.json"), "started": 1792831186}])
        self.write("evolve/swap-standard/state-layout-v1/task-abc.json", {"path": str(self.root / "worktrees/one")})
        self.tool = migration.Migration(self.root)

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True).strip()

    def write(self, name, value):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value, indent=2) + "\n" if not isinstance(value, str) else value)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file() and ".git" not in p.relative_to(self.root).parts}

    def test_plan_changes_nothing(self):
        before = self.snapshot()
        plan = self.tool.plan()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertTrue(any(x["to"] == "campaigns/xswap-next-2026-10-24/protocol.json" for x in plan["moves"]))

    def test_apply_moves_and_keeps_bytes(self):
        tracked = {x: (self.root / x).read_bytes() for x in self.git("ls-files").splitlines()}
        self.tool.apply()
        manifest = json.loads((self.root / "campaigns/MOVED.json").read_text())
        moves = {x["from"]: x for x in manifest["moves"] if x["how"] == "git-mv"}
        for name, data in tracked.items():
            if name.startswith(("evolve/control/campaigns/", "results/", "patches/", "benchmark/swap-standard/protocol")):
                self.assertIn(name, moves)
                self.assertEqual((self.root / moves[name]["to"]).read_bytes(), data)
                self.assertEqual(moves[name]["sha256"], hashlib.sha256(data).hexdigest())
        self.assertTrue((self.root / "campaigns/swap-standard-2026-10-22/report/swap-standard-evolve-2026-10-22/REPORT.md").exists())
        self.assertTrue((self.root / "campaigns/_unassigned/patches/xswap-reference/one.patch").exists())
        self.assertTrue((self.root / "campaigns/swap-standard-2026-10-22/ledger/tasks/task-abc.json").exists())

    def test_no_absolute_paths_in_imported_state(self):
        self.tool.apply()
        for name, data in self.snapshot().items():
            if name.startswith("campaigns/"):
                self.assertNotIn(str(self.root).encode(), data, name)
                self.assertNotIn(b"/home/", data, name)

    def test_campaign_json_valid(self):
        self.tool.apply()
        with self.tool.store_root():
            for name in self.names:
                record = migration.store.load(name)
                self.assertEqual(record["campaign"], name)
            self.assertEqual(migration.store.load(self.names[3])["status"], "open")
            self.assertEqual(migration.store.load(self.names[3])["machine"], "grok-cloud")
            r = migration.store.load(self.names[1])
            self.assertEqual(r["budget"]["guest_attempts"], 200)
            self.assertEqual(r["protocol_sha256"], hashlib.sha256((self.root / r["protocol_ref"]).read_bytes()).hexdigest())

    def test_patch_mismatch_stops(self):
        self.write("evolve/control/state/xswap-next-2026-10-24/one/candidate.patch", "different\n")
        before = self.snapshot()
        with self.assertRaisesRegex(migration.MigrationError, "patch"):
            self.tool.apply()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_identical_existing_stop_is_preserved(self):
        name = "xswap-next-2026-10-24"
        self.write(f"evolve/control/state/{name}/STOP", "preserve owner stop\n")
        self.write(f"campaigns/{name}/STOP", "preserve owner stop\n")
        self.tool.apply()
        self.assertEqual((self.root / f"campaigns/{name}/STOP").read_text(), "preserve owner stop\n")

    def test_conflicting_existing_stop_refuses_before_moves(self):
        name = "xswap-next-2026-10-24"
        self.write(f"evolve/control/state/{name}/STOP", "old stop\n")
        self.write(f"campaigns/{name}/STOP", "different stop\n")
        before = self.snapshot()
        with self.assertRaisesRegex(migration.MigrationError, "destination already exists"):
            self.tool.apply()
        self.assertEqual(before, self.snapshot())

    def test_idempotent(self):
        self.tool.apply()
        before = self.snapshot()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.tool.apply()
        self.assertIn("already migrated", out.getvalue())
        self.assertEqual(before, self.snapshot())
        self.tool.links()
        before = self.snapshot()
        self.tool.links()
        self.assertEqual(before, self.snapshot())

    def test_links_rewritten(self):
        self.tool.apply()
        self.tool.links()
        report = self.root / "campaigns/xswap-next-2026-10-24/report/REPORT.md"
        self.assertEqual(report.read_text(), "Measured 42; [protocol](../protocol.json#rules).\n")
        self.assertEqual(report.with_name("explainer.html").read_text(), '<a href="../protocol.json">42</a>')

    def test_links_to_unmoved_evidence_and_directories(self):
        self.write("results/xswap-next-2026-10-24/links.md", "[evidence](../../benchmark/swap-standard/evaluations/id/report.json) [patches](../../patches/xswap-next-2026-10-24/)\n")
        self.git("add", "results")
        self.git("commit", "-qm", "evidence links")
        self.tool.apply()
        self.tool.links()
        text = (self.root / "campaigns/xswap-next-2026-10-24/report/links.md").read_text()
        self.assertEqual(text, "[evidence](../../../benchmark/swap-standard/evaluations/id/report.json) [patches](../patches/)\n")

    def test_links_preflight_does_not_overwrite_prose(self):
        self.tool.apply()
        path = self.root / "campaigns/xswap-next-2026-10-24/report/explainer.html"
        path.write_text("Later prose change")
        before = self.snapshot()
        with self.assertRaisesRegex(migration.MigrationError, "beyond migration links"):
            self.tool.links()
        self.assertEqual(before, self.snapshot())

    def test_partial_apply_resumes(self):
        original = self.tool.move
        calls = []
        def interrupt(entry):
            if len(calls) == 2:
                raise RuntimeError("simulated interruption")
            original(entry)
            calls.append(entry)
        with mock.patch.object(self.tool, "move", side_effect=interrupt):
            with self.assertRaisesRegex(RuntimeError, "interruption"):
                self.tool.apply()
        self.tool.apply()
        self.assertTrue((self.root / "campaigns/MOVED.json").exists())
        self.assertFalse((self.root / "campaigns/.migration-pending.json").exists())

    def test_existing_destination_refused_before_moves(self):
        self.write("campaigns/xswap-next-2026-10-24/protocol.json", "conflict")
        before = self.snapshot()
        with self.assertRaisesRegex(migration.MigrationError, "destination"):
            self.tool.apply()
        self.assertEqual(before, self.snapshot())

    def test_dirty_source_is_not_pinned_to_wrong_commit(self):
        self.write("results/xswap-next-2026-10-24/REPORT.md", "Uncommitted finding")
        before = self.snapshot()
        with self.assertRaisesRegex(migration.MigrationError, "uncommitted"):
            self.tool.apply()
        self.assertEqual(before, self.snapshot())

    def test_links_preserve_crlf_bytes(self):
        self.write("results/xswap-next-2026-10-24/crlf.md", "42 [protocol](../../benchmark/swap-standard/protocol-xswap-next-2026-10-24.json)\r\n")
        self.git("add", "results")
        self.git("commit", "-qm", "CRLF report")
        self.tool.apply()
        self.tool.links()
        self.assertEqual((self.root / "campaigns/xswap-next-2026-10-24/report/crlf.md").read_bytes(), b"42 [protocol](../protocol.json)\r\n")

    def test_tracked_legacy_paths_are_preserved_and_noted(self):
        self.write("results/xswap-next-2026-10-24/old.md", "Historical path /home/legacy/project\n")
        self.git("add", "results")
        self.git("commit", "-qm", "old evidence")
        self.tool.apply()
        self.assertEqual((self.root / "campaigns/xswap-next-2026-10-24/report/old.md").read_text(), "Historical path /home/legacy/project\n")
        manifest = (self.root / "campaigns/MOVED.json").read_text()
        self.assertIn("legacy_absolute_paths", manifest)
        self.assertNotIn("/home/legacy", manifest)


class MachineStateImportTests(unittest.TestCase):
    """A second worker receives MOVED through git, but has its own ignored state."""
    git = MigrationTests.git
    write = MigrationTests.write
    snapshot = MigrationTests.snapshot

    def setUp(self):
        MigrationTests.setUp(self)
        self.tool.apply()
        self.git("commit", "-qm", "tracked migration from first worker")
        shutil.rmtree(self.root / "evolve/control/state")
        shutil.rmtree(self.root / "evolve/swap-standard/state-layout-v1")
        shutil.rmtree(self.root / "evolve/swap-standard/state-xswap-next-2026-10-24")
        self.campaign = "xswap-tcg-rev3-2026-10-25"
        self.write(f"evolve/swap-standard/state-{self.campaign}/ledger.json", [{"campaign": self.campaign, "id": "new", "report": str(self.root / "benchmark/swap-standard/evaluations/new/report.json")}])
        self.write(f"evolve/control/state/{self.campaign}/candidates.json", {"new": {"id": "new", "campaign": self.campaign, "worktree": str(self.root / f"worktrees/{self.campaign}/new"), "status": "active"}})
        self.write(f"evolve/control/state/{self.campaign}/new/candidate.patch", "machine-local immutable patch\n")
        self.write(f"evolve/control/state/{self.campaign}/new/task.json", {"campaign": self.campaign, "path": str(self.root / "worktrees/new")})
        self.env = mock.patch.dict("os.environ", {"SWAP_NEXT_MACHINE": "grok-cloud"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_remote_manifest_does_not_skip_local_state(self):
        protocol = (self.root / f"campaigns/{self.campaign}/protocol.json").read_bytes()
        self.tool.import_state()
        record = json.loads((self.root / f"campaigns/{self.campaign}/candidates/new.json").read_text())
        self.assertEqual(record["worktree"], f"worktrees/{self.campaign}/new")
        self.assertEqual((self.root / f"campaigns/{self.campaign}/patches/new.patch").read_bytes(), b"machine-local immutable patch\n")
        self.assertEqual((self.root / f"campaigns/{self.campaign}/protocol.json").read_bytes(), protocol)
        receipt, journal = self.tool.state_paths("grok-cloud")
        self.assertTrue(receipt.exists())
        self.assertFalse(journal.exists())
        self.assertNotIn("swap-next-migration", self.git("ls-files"))
        before, received = self.snapshot(), receipt.read_bytes()
        self.tool.import_state()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(received, receipt.read_bytes())

    def add_budget_source(self):
        self.write(f"evolve/swap-standard/state-{self.campaign}/budget.json",
                   {"created": 10, "guests": 0, "probe_guests": 0, "builds": 0})
        return self.root / f"campaigns/{self.campaign}/ledger/budget.json"

    def test_receipt_replay_preserves_legitimate_destination_growth(self):
        budget = self.add_budget_source()
        self.tool.import_state()
        receipt, journal = self.tool.state_paths("grok-cloud")
        receipt_before = receipt.read_bytes()
        self.write(str(budget.relative_to(self.root)), {"created": 10, "guests": 1, "probe_guests": 0, "builds": 1})
        ledger = self.root / f"campaigns/{self.campaign}/ledger/ledger.json"
        rows = json.loads(ledger.read_text()) + [{"id": "later-evaluation", "status": "FAST_REJECT"}]
        ledger.write_text(json.dumps(rows))
        candidate = self.root / f"campaigns/{self.campaign}/candidates/new.json"
        record = json.loads(candidate.read_text())
        record.update(status="closed", reason="later candidate decision")
        candidate.write_text(json.dumps(record))
        before, index_before = self.snapshot(), self.git("diff", "--cached")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.tool.import_state()
        self.assertIn("already imported", output.getvalue())
        self.assertEqual(before, self.snapshot())
        self.assertEqual(index_before, self.git("diff", "--cached"))
        self.assertEqual(receipt_before, receipt.read_bytes())
        self.assertFalse(journal.exists())

    def test_changed_legacy_source_after_receipt_refuses_without_resetting_capacity(self):
        budget = self.add_budget_source()
        self.tool.import_state()
        receipt, journal = self.tool.state_paths("grok-cloud")
        receipt_before = receipt.read_bytes()
        self.write(str(budget.relative_to(self.root)), {"created": 10, "guests": 1, "probe_guests": 0, "builds": 0})
        self.write(f"evolve/swap-standard/state-{self.campaign}/budget.json",
                   {"created": 10, "guests": 2, "probe_guests": 0, "builds": 0})
        before = self.snapshot()
        with self.assertRaisesRegex(migration.MigrationError, "legacy sources changed after import"):
            self.tool.import_state()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(json.loads(budget.read_text())["guests"], 1)
        self.assertEqual(receipt_before, receipt.read_bytes())
        self.assertFalse(journal.exists())

    def test_receipt_does_not_restore_a_deleted_budget_from_stale_legacy_state(self):
        budget = self.add_budget_source()
        self.tool.import_state()
        receipt, _ = self.tool.state_paths("grok-cloud")
        saved = receipt.read_bytes()
        budget.unlink()
        before = self.snapshot()
        with self.assertRaisesRegex(migration.MigrationError, "destinations are missing"):
            self.tool.import_state()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(saved, receipt.read_bytes())
        self.assertFalse(budget.exists())

    def test_runtime_writer_locks_serialize_import_before_final_preflight(self):
        budget = self.add_budget_source()
        ctx = multiprocessing.get_context("fork")
        for suffix in ("ledger/.lock", ".lock", "ledger/.budget.lock"):
            with self.subTest(lock=suffix):
                acquired, release, finished, started = [ctx.Event() for _ in range(4)]
                output = ctx.Queue()
                lock = self.root / f"campaigns/{self.campaign}" / suffix
                writer = ctx.Process(target=locked_runtime_writer, args=(lock, budget, acquired, release, finished))
                importer = ctx.Process(target=import_in_process, args=(self.root, output, started))
                writer.start()
                self.assertTrue(acquired.wait(5))
                importer.start()
                try:
                    self.assertTrue(started.wait(5))
                    with self.assertRaises(queue.Empty):
                        output.get(timeout=.15)
                    release.set()
                    self.assertTrue(finished.wait(5))
                    kind, message = output.get(timeout=10)
                    self.assertEqual(kind, "MigrationError", message)
                    self.assertIn("conflict", message)
                    self.assertEqual(json.loads(budget.read_text())["guests"], 1)
                finally:
                    release.set()
                    for process in (writer, importer):
                        process.join(10)
                        if process.is_alive():
                            process.terminate()
                            process.join(5)
                        self.assertEqual(process.exitcode, 0)
                self.assertFalse(self.tool.state_paths("grok-cloud")[0].exists())
                budget.unlink()

    def test_exclusive_publication_preserves_an_unlocked_writer_winning_the_race(self):
        budget = self.add_budget_source()
        ctx = multiprocessing.get_context("fork")
        request, finished = ctx.Event(), ctx.Event()
        writer = ctx.Process(target=racing_unlocked_writer, args=(budget, request, finished))
        writer.start()
        real_link = migration.os.link
        def publish(source, target, *args, **kwargs):
            if Path(target) == budget:
                request.set()
                if not finished.wait(5):
                    raise RuntimeError("race writer failed")
            return real_link(source, target, *args, **kwargs)
        try:
            with mock.patch.object(migration.os, "link", side_effect=publish):
                with self.assertRaisesRegex(migration.MigrationError, "appeared during import"):
                    self.tool.import_state()
        finally:
            request.set()
            writer.join(10)
            if writer.is_alive():
                writer.terminate()
                writer.join(5)
        self.assertEqual(writer.exitcode, 0)
        self.assertEqual(json.loads(budget.read_text())["guests"], 1)
        receipt, journal = self.tool.state_paths("grok-cloud")
        self.assertFalse(receipt.exists())
        self.assertTrue(journal.exists())
        self.assertEqual(list(budget.parent.glob(".migration-*.tmp")), [])

    def test_receipt_before_journal_cleanup_recovers_without_replaying_old_budget(self):
        budget = self.add_budget_source()
        receipt, journal = self.tool.state_paths("grok-cloud")
        unlink = Path.unlink
        def interrupt(path, *args, **kwargs):
            if path == journal:
                raise RuntimeError("crash after receipt")
            return unlink(path, *args, **kwargs)
        with mock.patch.object(Path, "unlink", interrupt):
            with self.assertRaisesRegex(RuntimeError, "crash after receipt"):
                self.tool.import_state()
        self.assertTrue(receipt.exists())
        self.assertTrue(journal.exists())
        self.write(str(budget.relative_to(self.root)), {"created": 10, "guests": 1, "probe_guests": 0, "builds": 0})
        saved = receipt.read_bytes()
        self.tool.import_state()
        self.assertEqual(json.loads(budget.read_text())["guests"], 1)
        self.assertEqual(saved, receipt.read_bytes())
        self.assertFalse(journal.exists())

    def test_cloud_paths_are_normalized_without_changing_device_names(self):
        tool = migration.Migration(self.root)
        tool.project = Path("/workspace/Swap-Next")
        value = {"root": "/workspace/Swap-Next", "worktree": "/workspace/Swap-Next/worktrees/new", "sibling": "/workspace/xswap-replay", "device": "/dev/vda"}
        normalized = json.loads(tool.clean_paths(json.dumps(value).encode()))
        self.assertEqual(normalized, {"root": ".", "worktree": "worktrees/new", "sibling": "../xswap-replay", "device": "/dev/vda"})

    def test_state_import_resumes_partial_failure(self):
        real = self.tool.import_state_file
        calls = []
        def interrupt(entry):
            if len(calls) == 1: raise RuntimeError("interrupted state import")
            real(entry)
            calls.append(entry)
        with mock.patch.object(self.tool, "import_state_file", side_effect=interrupt):
            with self.assertRaisesRegex(RuntimeError, "interrupted state import"):
                self.tool.import_state()
        receipt, journal = self.tool.state_paths("grok-cloud")
        self.assertTrue(journal.exists())
        self.assertFalse(receipt.exists())
        self.tool.import_state()
        self.assertTrue(receipt.exists())
        self.assertFalse(journal.exists())
        self.assertTrue((self.root / f"campaigns/{self.campaign}/ledger/ledger.json").exists())

    def test_state_import_recovers_copy_before_staging(self):
        copied = []
        def interrupt(entry):
            path = self.root / entry["to"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.tool.content(entry))
            copied.append(entry["to"])
            raise RuntimeError("copied before git add")
        with mock.patch.object(self.tool, "import_state_file", side_effect=interrupt):
            with self.assertRaisesRegex(RuntimeError, "copied before git add"):
                self.tool.import_state()
        self.assertNotIn(copied[0], self.git("ls-files").splitlines())
        self.tool.import_state()
        self.assertIn(copied[0], self.git("ls-files").splitlines())

    def test_conflicting_remote_state_refused_before_writes(self):
        self.write(f"campaigns/{self.campaign}/ledger/ledger.json", [{"id": "remote"}])
        before = self.snapshot()
        with self.assertRaisesRegex(migration.MigrationError, "conflict"):
            self.tool.import_state()
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.tool.state_paths("grok-cloud")[1].exists())

    def test_mismatched_machine_refused_before_writes(self):
        with mock.patch.dict("os.environ", {"SWAP_NEXT_MACHINE": "hurricpc"}):
            before = self.snapshot()
            with self.assertRaisesRegex(migration.MigrationError, "machine"):
                self.tool.import_state()
            self.assertEqual(before, self.snapshot())
        self.assertFalse(self.tool.state_paths("hurricpc")[1].exists())

    def test_mismatched_campaign_record_refused_before_writes(self):
        self.write(f"evolve/control/state/{self.campaign}/candidates.json", {"new": {"id": "new", "campaign": "foreign"}})
        before = self.snapshot()
        with self.assertRaisesRegex(migration.MigrationError, "campaign"):
            self.tool.import_state()
        self.assertEqual(before, self.snapshot())

    def test_equivalence_normalizes_both_sides_without_rewriting_remote(self):
        source = self.root / f"evolve/swap-standard/state-{self.campaign}/ledger.json"
        remote = source.read_bytes()
        dest = self.root / f"campaigns/{self.campaign}/ledger/ledger.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(remote)
        self.git("add", "campaigns")
        self.git("commit", "-qm", "remote retained historical paths")
        self.tool.import_state()
        self.assertEqual(dest.read_bytes(), remote)

    def test_equivalent_normalized_remote_state_is_retained(self):
        source = self.root / f"evolve/swap-standard/state-{self.campaign}/ledger.json"
        data = self.tool.clean_paths(source.read_bytes())
        dest = self.root / f"campaigns/{self.campaign}/ledger/ledger.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        self.git("add", "campaigns")
        self.git("commit", "-qm", "equivalent remote ledger")
        before = dest.stat().st_mtime_ns
        self.tool.import_state()
        self.assertEqual(dest.read_bytes(), data)
        self.assertEqual(dest.stat().st_mtime_ns, before)


if __name__ == "__main__":
    unittest.main()
