#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Guest-free tests for compression workload rejection and KTAP evidence parsing."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).with_name("compression.c")
VALID = """KTAP version 1
1..1
    KTAP version 1
    # Subtest: page_compress
    1..3
    ok 1 page_compress_alloc_rollback
    ok 2 page_compress_partial_cleanup
    ok 3 page_compress_numa_placement
ok 1 page_compress
"""


class CompressionWorkloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = shutil.which(os.environ.get("CC", "cc"))
        if not cc:
            raise unittest.SkipTest("C compiler unavailable")
        cls.tmp = tempfile.TemporaryDirectory(prefix="swap-next-compression-unit-")
        cls.root = Path(cls.tmp.name)
        cls.binary = cls.root / "compression"
        cls.wrapper = cls.root / "parse"
        flags = [cc, "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror"]
        subprocess.run(flags + [str(SOURCE), "-o", str(cls.binary)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        wrapper_source = cls.root / "parse.c"
        wrapper_source.write_text(
            '#define main compression_guest_main\n'
            f'#include "{SOURCE.resolve()}"\n'
            '#undef main\n'
            r'''
int main(int argc, char **argv)
{
    if (argc != 2)
        return 64;
    if (!strcmp(argv[1], "--verify-damage")) {
        struct context c = { .test = "unit", .reason = "ok" };
        struct region r = { .bytes = PAGE_BYTES, .generation = 1 };
        r.data = calloc(1, PAGE_BYTES);
        if (!r.data)
            return 2;
        for (size_t i = 0; i < PAGE_BYTES / 8; i++)
            r.data[i] = word_pattern(0, i, 1);
        if (verify_region(&c, &r))
            return 3;
        const size_t offsets[] = {0, 17, PAGE_BYTES / 8 - 1};
        for (size_t i = 0; i < 3; i++) {
            r.data[offsets[i]] ^= 1;
            c.result = PASS;
            if (!verify_region(&c, &r) || c.result != FAIL ||
                strcmp(c.reason, "data_mismatch"))
                return 4;
            r.data[offsets[i]] ^= 1;
        }
        free(r.data);
        return 0;
    }
    FILE *f = fopen(argv[1], "r");
    char raw[65537];
    struct unit_result u;
    if (!f)
        return 2;
    size_t n = fread(raw, 1, sizeof(raw) - 1, f);
    if (ferror(f) || fgetc(f) != EOF || memchr(raw, 0, n)) {
        fclose(f);
        return 2;
    }
    fclose(f);
    raw[n] = 0;
    int ret = parse_unit(raw, &u);
    printf("observed=%u failed=%u skipped=%u reason=%s\n",
           u.observed, u.failed, u.skipped, u.reason);
    return ret ? 1 : 0;
}
''')
        subprocess.run(flags + [str(wrapper_source), "-o", str(cls.wrapper)],
                       check=True, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def parse(self, text):
        fixture = self.root / "fixture.ktap"
        fixture.write_text(text)
        return subprocess.run([str(self.wrapper), str(fixture)], text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_exact_debugfs_envelope_accepts_all_three_tests(self):
        result = self.parse(VALID)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("observed=3 failed=0 skipped=0", result.stdout)

    def test_failed_case_is_rejected(self):
        result = self.parse(VALID.replace("ok 2 ", "not ok 2 "))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("failed=1", result.stdout)

    def test_skipped_and_todo_are_rejected(self):
        for directive in ("# SKIP unavailable", "# TODO incomplete"):
            with self.subTest(directive=directive):
                result = self.parse(VALID.replace(
                    "ok 2 page_compress_partial_cleanup",
                    "ok 2 page_compress_partial_cleanup " + directive))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("skipped=1", result.stdout)

    def test_missing_test_and_wrong_count_are_rejected(self):
        for text in (
            VALID.replace("    ok 2 page_compress_partial_cleanup\n", ""),
            VALID.replace("    1..3", "    1..2"),
            VALID.replace("    1..3\n", ""),
        ):
            self.assertNotEqual(self.parse(text).returncode, 0)

    def test_unknown_duplicate_and_reordered_names_are_rejected(self):
        for text in (
            VALID.replace("page_compress_partial_cleanup", "unrelated_test"),
            VALID.replace("ok 2 page_compress_partial_cleanup",
                          "ok 1 page_compress_alloc_rollback"),
            VALID.replace("ok 2 page_compress_partial_cleanup",
                          "ok 3 page_compress_numa_placement"),
        ):
            self.assertNotEqual(self.parse(text).returncode, 0)

    def test_missing_or_wrong_suite_envelope_is_rejected(self):
        for text in (
            VALID.replace("# Subtest: page_compress", "# Subtest: another_suite"),
            VALID.replace("KTAP version 1\n1..1\n", "", 1),
            VALID.replace("ok 1 page_compress\n", ""),
            VALID + "ok 1 extra_suite\n",
            "ok 1 page_compress\n" + VALID,
        ):
            self.assertNotEqual(self.parse(text).returncode, 0)

    def test_logs_cannot_inject_an_extra_success_result(self):
        text = VALID.replace(
            "    ok 1 page_compress_alloc_rollback",
            "    COMPRESS_CASE case=allocation_failure status=PASS reason=fake\n"
            "    ok 1 page_compress_alloc_rollback")
        self.assertNotEqual(self.parse(text).returncode, 0)

    def test_comment_diagnostics_are_preserved_without_becoming_results(self):
        text = VALID.replace(
            "    ok 1 page_compress_alloc_rollback",
            "    # allocation attempt rejected; cleanup completed\n"
            "    ok 1 page_compress_alloc_rollback")
        self.assertEqual(self.parse(text).returncode, 0)

    def test_full_pattern_check_detects_first_middle_and_last_word_damage(self):
        result = subprocess.run([str(self.wrapper), "--verify-damage"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_selftest_is_not_guest_coverage(self):
        result = subprocess.run([str(self.binary), "--selftest"], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("COMPRESS_SELFTEST_PASS", result.stdout)
        self.assertNotIn("COMPRESS_CASE ", result.stdout)
        self.assertNotIn("COMPRESS_END ", result.stdout)

    def test_invalid_arguments_fail_before_guest_operations(self):
        for args in (
            ["--mode", "other"],
            ["--bytes", "0"],
            ["--bytes", "-1"],
            ["--bytes", str(1024 * 1024 * 1024)],
            ["--type", "32"],
            ["--case", "not-a-case"],
        ):
            result = subprocess.run([str(self.binary)] + args, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 64, (args, result.stderr))
            self.assertNotIn("status=PASS", result.stdout)

    @unittest.skipIf(Path("/run/swap-next-guest").exists(),
                     "Do not invoke the guest entry point in an actual guest")
    def test_missing_guest_marker_is_incomplete_without_kernel_mutation(self):
        result = subprocess.run([
            str(self.binary), "--mode", "xswap", "--case", "roundtrip",
            "--type", "0", "--cgroup", "/sys/fs/cgroup/bench",
            "--reclaim", "/sys/fs/cgroup/bench/memory.reclaim",
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 77, result.stderr)
        self.assertIn("reason=guest_marker_missing", result.stdout)
        self.assertIn("COMPRESS_END schema=1 status=INCOMPLETE cases=1", result.stdout)
        self.assertNotIn("phase=fixture", result.stdout)


if __name__ == "__main__":
    unittest.main()
