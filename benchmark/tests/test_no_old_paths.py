# SPDX-License-Identifier: GPL-2.0-only
"""Tracked code must use the campaigns/ layout; no build or guest execution."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
OLD = (r"evolve/control/campaigns|evolve/control/state/[a-z]|evolve/control/state\" */"
       r"|evolve/swap-standard/state|confirmations|(^|[^-/a-z])(results|patches)/")
# Historical records and files that legitimately name the old layout.
EXCLUDE = (":!linux", ":!campaigns/*/report/**", ":!results/**",
           ":!evolve/control/migrate.py", ":!evolve/control/tests/test_migrate.py",
           ":!benchmark/tests/test_no_old_paths.py")
RUNNERS = ("benchmark/kernel/build.py", "benchmark/kernel/run.py", "benchmark/swap-standard/run.py",
           "benchmark/xswap-p123/run.py", "benchmark/xswap/run.py", "benchmark/xswap/evaluate_kernel.py",
           "benchmark/xswap-structure/run.py", "benchmark/xswap-structure/evaluate_kernel.py",
           "benchmark/xswap-hole-probe/run.py")
CODE = ("*.py", "*.sh", "*.yml")
# The unscoped controller mode (a suite without a campaign) keeps this path.
ALLOWED = ('state = PROJECT / "evolve/control/state"',)


def grep(pattern):
    result = subprocess.run(["git", "grep", "-n", "-E", pattern, "--", *CODE, *EXCLUDE],
                            cwd=ROOT, capture_output=True, text=True)
    return [line for line in result.stdout.splitlines()
            if not any(allowed in line for allowed in ALLOWED)]


class NoOldPathTests(unittest.TestCase):

    def test_code_uses_campaign_layout(self):
        self.assertEqual(grep(OLD), [])

    def test_no_old_global_stop(self):
        self.assertEqual(grep(r"evolve/control/state/STOP"), [])

    def test_every_runner_honours_global_stop(self):
        for path in RUNNERS:
            with self.subTest(path=path):
                source = (ROOT / path).read_text()
                self.assertTrue("campaigns/STOP" in source or "campaign_store.GLOBAL_STOP" in source)


if __name__ == "__main__":
    unittest.main()
