# SPDX-License-Identifier: GPL-2.0-only
import ast
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch
import evaluate_kernel
import run
from regimes import summarize_regimes, wilson

BASE = pathlib.Path(__file__).resolve().parent


class CampaignTests(unittest.TestCase):
    def test_campaign_stop_comes_from_protocol(self):
        protocol = json.loads((BASE/'protocol.json').read_text())
        with tempfile.TemporaryDirectory() as tmp, patch.object(run, 'PROJECT', pathlib.Path(tmp)), patch.object(evaluate_kernel, 'PROJECT', pathlib.Path(tmp)):
            # A stop file in the retired state directory must not halt anything.
            old = pathlib.Path(tmp)/'evolve'/'control'/'state'/'xswap-2026-10-21'/'STOP'
            old.parent.mkdir(parents=True)
            old.touch()
            protocol['deadline_utc'] = '2100-01-01T00:00:00+00:00'
            evaluate_kernel.bounded(protocol)
            stop = run.campaign_stop(protocol)
            self.assertNotEqual(stop, old)
            self.assertEqual(stop, pathlib.Path(tmp)/'campaigns'/protocol['campaign']/'STOP')
            stop.parent.mkdir(parents=True)
            stop.touch()
            with self.assertRaisesRegex(ValueError, 'STOP'):
                evaluate_kernel.bounded(protocol)
            # The global stop halts on its own, without the campaign file.
            stop.unlink()
            evaluate_kernel.bounded(protocol)
            (pathlib.Path(tmp)/'campaigns/STOP').touch()
            with self.assertRaisesRegex(ValueError, 'STOP'):
                evaluate_kernel.bounded(protocol)

    def test_state_and_protocol_are_isolated(self):
        old = json.loads((BASE.parent/'xswap/protocol.json').read_text())
        new = json.loads((BASE/'protocol.json').read_text())
        self.assertNotEqual(old['campaign'], new['campaign'])
        self.assertNotEqual(old['baseline_build'], new['baseline_build'])
        self.assertEqual(evaluate_kernel.BASE, BASE)
        self.assertEqual(run.BASE, BASE)
        # Inspect the actual adapter without requiring OpenEvolve installation.
        source = ast.parse((BASE.parents[1]/'evolve/loop.py').read_text())
        assignments = [n for n in source.body if isinstance(n, ast.Assign)]
        suites = next(ast.literal_eval(n.value) for n in assignments if any(isinstance(t, ast.Name) and t.id == 'SUITES' for t in n.targets))
        self.assertTrue(suites['xswap-structure'])
        suite_class = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'Suite')
        namespace = dict(PROJECT=BASE.parents[1], json=json)
        exec(compile(ast.Module(body=[suite_class], type_ignores=[]), '<suite>', 'exec'), namespace)
        first, second = namespace['Suite']('xswap'), namespace['Suite']('xswap-structure')
        self.assertNotEqual(first.state, second.state)
        self.assertNotEqual(first.report_path('same'), second.report_path('same'))

    def test_boot_budgets(self):
        protocol = json.loads((BASE/'protocol.json').read_text())
        self.assertEqual(protocol['calibration_order'], ['AB', 'BA'])
        self.assertEqual(protocol['order'], ['AB', 'BA']*5)
        self.assertEqual(len(protocol['backends'])*sum(map(len, protocol['order'])), 40)
        self.assertEqual(protocol['max_guest_attempts'], 96)
        self.assertFalse(protocol['performance_accepted'])
        self.assertFalse(protocol['auto_promote'])

    def test_regime_threshold_and_failures(self):
        runs = [dict(backend='disk', side='A', pair=i, pilot_pass=True, evidence_verified=True,
                     metrics={'mapped_clusters_after_settle': count}) for i, count in enumerate([219, 220])]
        runs.append(dict(backend='disk', side='A', pair=2, pilot_pass=False))
        result = summarize_regimes(runs, 219)['groups']['disk/A']
        self.assertEqual((result['high'], result['low'], result['invalid']), (1, 1, 1))
        self.assertEqual(len(result['runs']), 3)
        self.assertEqual(result['high_rate'], 0.5)
        self.assertAlmostEqual(result['high_rate_wilson_95'][0], 0.0945312057)
        unverified = dict(runs[0], evidence_verified=False)
        self.assertEqual(summarize_regimes([unverified], 219)['groups']['disk/A']['invalid'], 1)
        self.assertIsNone(wilson(0, 0))
        self.assertAlmostEqual(wilson(0, 10)[1], 0.2775327999)


if __name__ == '__main__':
    unittest.main()
