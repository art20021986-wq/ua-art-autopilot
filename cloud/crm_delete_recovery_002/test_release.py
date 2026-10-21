"""Source-bound composed release tests, entirely inside temporary fixtures."""
from contextlib import closing
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time
import types
import unittest

import build_release as release

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE / 'install'), str(HERE / 'deletion_core')]
from package_install import Package, FixtureInstallTransaction, ExistingLocksLease
import test_runtime_current as fixtures


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


class ComposedReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = Path(os.environ['UA_DELETE_CURRENT_SOURCES']).resolve(strict=True)
        cls.workspace = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.workspace.cleanup)
        cls.staging = Path(cls.workspace.name) / 'release'
        cls.receipt = release.build(cls.sources, cls.staging)
        cls.package = Package(cls.staging, cls.receipt['manifest_sha256'])

    def test_stale_writer_evidence_is_rejected(self):
        raw = json.loads((self.staging / 'writers_receipt.json').read_bytes())
        raw['recipe_sha256']['cars_publication_patch.py'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'WRITER_RECIPE_RECEIPT_STALE'):
            release.validate_writer_receipt(release.encoded(raw), self.sources, None, {})
        raw = json.loads((self.staging / 'writers_receipt.json').read_bytes())
        raw['guard_unit_tests']['skipped'] = 1
        with self.assertRaisesRegex(ValueError, 'WRITER_TEST_RECEIPT_REQUIRED'):
            release.validate_writer_receipt(release.encoded(raw), self.sources, None, {})

    def test_full_package_install_runtime_delete_writer_and_route_compose(self):
        fixture = fixtures.CurrentSourceTests('test_current_schema_and_real_db_wrapper_complete')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        root = fixture.root
        for source in self.sources.glob('*.py'):
            shutil.copyfile(source, root / source.name)
        for destination, (name, expected) in release.EXTERNAL_GUARDS.items():
            path = root / destination
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.sources / name, path)
        # Test identity is synthetic and intentionally avoids the historical
        # incident ID8. The captured public markup is never deployed.
        with closing(sqlite3.connect(root / 'crm.db')) as conn:
            conn.execute('UPDATE cars SET id=888 WHERE id=8')
            conn.commit()
        for name in ('.start_safe.singleton.lock', '.ua_art_publish_transaction.lock'):
            (root / name).touch(mode=0o600)
        media = root / 'video' / 'retained-photo.jpg'
        media.write_bytes(b'synthetic retained media')
        public_before = {str(p.relative_to(root)): p.read_bytes()
                         for folder in ('site', 'video') for p in (root / folder).iterdir()}
        self.package.check_sources(root)
        tx = FixtureInstallTransaction(self.package, root, fixture.private)
        with ExistingLocksLease(root, inventory=lambda: []) as lease:
            tx.backup(lease)
            result = tx.apply(lease)
        self.assertEqual('OFFLINE_CODE_INSTALL_PASS', result['status'])
        self.assertFalse(result['production_restart_verified'])
        self.assertEqual(public_before, {name: (root / name).read_bytes() for name in public_before})
        for name, item in self.package.files.items():
            self.assertEqual(item['payload_sha256'], release.sha((root / name).read_bytes()))

        sys.path.insert(0, str(root))
        self.addCleanup(lambda: sys.path.remove(str(root)))
        runtime = importlib.import_module('ua_crm_deletion_core.runtime')
        core = importlib.import_module('ua_crm_deletion_core.coordinator')
        self.addCleanup(lambda: [sys.modules.pop(name, None) for name in list(sys.modules)
                                if name == 'ua_crm_deletion_core' or name.startswith('ua_crm_deletion_core.')])
        actual_fence = load('_composed_actual_fence', root / 'publication_fence.py')
        lock = root / '.ua_art_publish_transaction.lock'
        def fence(timeout=90):
            return actual_fence.PublicationFence(lock_path=lock, _test_only_path=True, timeout=timeout)
        def require_fence():
            return actual_fence.require_publication_fence(lock_path=lock)
        fence_module = types.SimpleNamespace(__file__=str(root / 'publication_fence.py'),
            publication_fence=fence, require_publication_fence=require_fence)
        counters = load('_composed_actual_counters', root / 'ua_site_counters.py')
        config = json.loads((root / 'ua_crm_deletion_state/runtime.json').read_bytes())
        binding = runtime.LegacyBinding(db=fixture.db, counters=counters, fence_module=fence_module,
            config=config, root=root, journal=fixture.private)
        def observe(plan):
            with self.assertRaises(actual_fence.FenceError):
                require_fence()  # HTTP observation must run after releasing all publication locks.
            return {url: {'url': url, 'status': 200 if (root / name).exists() else 410,
                          'body_sha256': release.sha((root / name).read_bytes()) if (root / name).exists() else None,
                          'redirected': False, 'observed_at': time.time()}
                    for url, name in plan['routes'].items()}
        binding.observe_http = observe
        worker = core.Coordinator(binding, schema_sha256=release.SCHEMA_SHA)
        token = worker.confirm(car_id=888, actor_id=101)
        intent = worker.admit(token=token, actor_id=101)
        self.assertEqual('COMPLETE', worker.resume(operation_id=intent['operation_id'])['status'])
        self.assertEqual('COMPLETE', worker.resume(operation_id=intent['operation_id'])['status'])
        self.assertEqual(b'synthetic retained media', media.read_bytes())
        with closing(sqlite3.connect(root / 'crm.db')) as conn:
            self.assertIsNone(conn.execute('SELECT id FROM cars WHERE id=888').fetchone())
            self.assertEqual((9900, 8000), conn.execute('SELECT price_uah,price_georgia FROM cars WHERE id=9').fetchone())
            self.assertEqual(('ok',), conn.execute('PRAGMA integrity_check').fetchone())

        writers = load('_composed_guard', root / 'ua_delete_public_guard.py')
        guard = writers.PublicDeletionGuard(root, root / 'crm.db', fence, require_fence)
        with self.assertRaises(writers.DeletedPublicationRefused):
            with guard.write(root / 'video' / (fixture.code + '.html'), '<html>stale card</html>'):
                self.fail('a delayed writer obtained permission to recreate the deleted card')
        routes = load('_composed_routes', root / 'ua_crm_deleted_routes.py')
        retired = routes.DeletedRoutes(db=root / 'crm.db', journal=fixture.private)
        self.assertIn('/video/' + fixture.code + '.html', retired.snapshot(car_code=fixture.code))
        response = []
        app = retired.wrap(lambda env, start: self.fail('deleted route reached old redirect'))
        app({'PATH_INFO': '/video/' + fixture.code + '.html', 'REQUEST_METHOD': 'GET'},
            lambda status, headers: response.append(status))
        self.assertEqual(['410 Gone'], response)


if __name__ == '__main__':
    unittest.main()
