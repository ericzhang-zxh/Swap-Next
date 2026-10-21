# SPDX-License-Identifier: GPL-2.0-only
"""Campaign selection and global emergency stop are controller boundaries."""
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import controller as c
from analysis import Invalid

class CampaignTests(unittest.TestCase):
    def test_invalid_or_unknown_campaign_does_not_mutate_paths(self):
        old = c.POLICY, c.STATE, c.WORKTREES
        for name in ("../escape", "/absolute", "a/b", "missing-campaign-xyz"):
            with self.assertRaises(Invalid):
                c.configure_campaign(name)
            self.assertEqual((c.POLICY, c.STATE, c.WORKTREES), old)

    def test_global_and_campaign_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            control = pathlib.Path(tmp)
            state = control / "state/campaign"
            state.mkdir(parents=True)
            with patch.object(c, "CONTROL", control), patch.object(c, "STATE", state):
                c.active()
                for flag in (control / "state/STOP", state / "STOP"):
                    flag.touch()
                    with self.assertRaises(Invalid):
                        c.active()
                    flag.unlink()
                c.active()
