# SPDX-License-Identifier: GPL-2.0-only
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch
import run


class AttestationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = pathlib.Path(self.tmp.name)
        self.build = self.base/'build'
        self.image = self.build/'output/arch/x86/boot/bzImage'
        self.image.parent.mkdir(parents=True)
        self.image.write_bytes(b'synthetic-image')
        self.config = self.build/'output/.config'
        self.config.write_text('\n'.join(key+'=y' for key in ('CONFIG_XSWAP', 'CONFIG_SWAP', 'CONFIG_DEBUG_FS', 'CONFIG_PROC_PAGE_MONITOR', 'CONFIG_ZSWAP'))+'\n# CONFIG_TRANSPARENT_HUGEPAGE is not set\n')
        for name in run.SOURCES:
            (self.base/name).write_text('synthetic source '+name)
        self.initrd = self.base/'initramfs.cpio.gz'
        self.initrd.write_bytes(b'synthetic-initrd')
        self.protocol = dict(baseline_commit='a'*40, config_sha256=run.sha(self.config))
        self.manifest = dict(passed=True, commit='a'*40, image_sha256=run.sha(self.image),
                             config_sha256=run.sha(self.config), instrument_sha256=None)
        self.provenance = dict(initrd_sha256=run.sha(self.initrd),
                               sources={name: run.sha(self.base/name) for name in run.SOURCES})
        self.save()
        self.addCleanup(patch.stopall)
        patch.object(run, 'BASE', self.base).start()

    def save(self):
        (self.build/'result.json').write_text(json.dumps(self.manifest))
        (self.base/'initramfs.json').write_text(json.dumps(self.provenance))

    def test_attested(self):
        self.assertEqual(run.attest(self.build, self.protocol, 'disk')[0], self.manifest)

    def test_manifest_identity(self):
        for key, bad in [('passed', False), ('commit', 'b'*40), ('image_sha256', 'wrong'),
                         ('config_sha256', 'wrong'), ('instrument_sha256', 'wrong')]:
            with self.subTest(key=key):
                original = self.manifest[key]
                self.manifest[key] = bad
                self.save()
                with self.assertRaises(ValueError):
                    run.attest(self.build, self.protocol, 'disk')
                self.manifest[key] = original
        self.save()
        protocol = dict(self.protocol, config_sha256='wrong')
        with self.assertRaises(ValueError):
            run.attest(self.build, protocol, 'disk')

    def test_image_and_initrd_tampering(self):
        for path in (self.image, self.initrd, self.config):
            original = path.read_bytes()
            path.write_bytes(original+b'changed')
            with self.assertRaises(ValueError):
                run.attest(self.build, self.protocol, 'disk')
            path.write_bytes(original)

    def test_stale_sources(self):
        for name in run.SOURCES:
            path = self.base/name
            original = path.read_text()
            path.write_text('changed')
            with self.assertRaisesRegex(ValueError, 'stale initrd source'):
                run.attest(self.build, self.protocol, 'disk')
            path.write_text(original)

    def test_thp_rejected_even_with_matching_config_hash(self):
        original = self.config.read_text()
        for key in ('CONFIG_THP_SWAP', 'CONFIG_TRANSPARENT_HUGEPAGE'):
            self.config.write_text(original+key+'=y\n')
            self.manifest['config_sha256'] = self.protocol['config_sha256'] = run.sha(self.config)
            self.save()
            with self.assertRaisesRegex(ValueError, 'cluster-size assumption'):
                run.attest(self.build, self.protocol, 'disk')

    def test_zswap_required_even_disk_backend(self):
        self.config.write_text(self.config.read_text().replace('CONFIG_ZSWAP=y\n', ''))
        self.manifest['config_sha256'] = self.protocol['config_sha256'] = run.sha(self.config)
        self.save()
        with self.assertRaisesRegex(ValueError, 'required config'):
            run.attest(self.build, self.protocol, 'disk')


class BudgetTests(unittest.TestCase):
    protocol = dict(suite='xswap-hole-probe', max_guest_attempts=2, global_max_guest_attempts=96)

    def test_preserve_shared_entries_and_reserve_both(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            local, shared = base/'local/attempts.json', base/'shared/attempts.json'
            old = [{'run': 'old-run', 'arbitrary_retained_field': 42}]
            run.write_ledger(shared, old)
            run.reserve_attempt(self.protocol, local, shared, dict(run='new-run'))
            rows = run.read_ledger(shared)
            self.assertEqual(rows[0], old[0])
            self.assertEqual(rows[1]['suite'], 'xswap-hole-probe')
            self.assertEqual(run.read_ledger(local), rows[1:])

    def test_all_limits_count_failed_or_incomplete_attempts(self):
        for local, shared in [([{}, {}], []), ([], [{}]*96),
                              ([], [{'suite':'xswap-hole-probe'}]*2)]:
            with self.subTest(local=len(local), shared=len(shared)), self.assertRaises(ValueError):
                run.check_budgets(self.protocol, local, shared)

    def test_shared_reservation_survives_local_write_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            local, shared = base/'local.json', base/'shared.json'
            real_write = run.write_ledger
            def fail_local(path, rows):
                if path == local:
                    raise OSError('synthetic local failure')
                real_write(path, rows)
            with patch.object(run, 'write_ledger', fail_local), self.assertRaises(OSError):
                run.reserve_attempt(self.protocol, local, shared, dict(run='retained'))
            self.assertEqual(len(run.read_ledger(shared)), 1)

    def test_stop_derived_from_campaign(self):
        paths = run.stop_paths(dict(campaign='new-campaign'))
        self.assertEqual(paths[1].parts[-2:], ('new-campaign', 'STOP'))

    def test_deadline_and_frozen_bounds(self):
        protocol = json.loads((pathlib.Path(__file__).parent/'protocol.json').read_text())
        self.assertEqual(protocol['max_guest_attempts'], 2)
        self.assertEqual(protocol['global_max_guest_attempts'], 96)
        self.assertEqual(protocol['min_free_gib'], 80)
        self.assertEqual(protocol['baseline_commit'], '4f83412c1d59eaf6a4d2460cb47fe0177a3be0c4')
        self.assertTrue(run.expired(dict(deadline_utc='2000-01-01T00:00:00+00:00')))
        self.assertFalse(protocol['performance_accepted'])


if __name__ == '__main__':
    unittest.main()
