"""Real worker/callback code with isolated SQLite, publisher and Telegram I/O."""
import asyncio
import hashlib
import importlib.util
import json
import logging
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from build_candidate import SOURCE_SHA256, build, patch_callbacks, patch_worker

FIXTURES = Path(__file__).with_name('fixtures')


def load(path):
    spec = importlib.util.spec_from_file_location('isolated_performance', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WorkerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 100.0
        raw = (FIXTURES/'worker_before.py').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), SOURCE_SHA256['ua_crm_public_sync.py'])
        self.path = self.root/'worker.py'
        self.path.write_text(patch_worker(raw.decode()))
        self.worker = self.new_worker()
        self.publish = Mock(return_value=(True, 'ok'))
        self.verify = Mock()
        self.hide = Mock()
        self.modules = patch.dict(sys.modules, {
            'ua_delivery_status': SimpleNamespace(public_status=lambda x: 'hidden' if x in ('archive', 'hidden') else x),
            'ua_stage_catalog_sync': SimpleNamespace(reconcile=self.hide),
            'ua_public_freshness': SimpleNamespace(verify_public=self.verify),
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)
        with sqlite3.connect(self.root/'crm.db') as conn:
            conn.execute('CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT, status TEXT, published INTEGER, price INTEGER)')
            conn.executemany('INSERT INTO cars VALUES(?,?,?,?,?)',
                             [(1, 'UA-0001', 'korea', 1, 100), (2, 'UA-0002', 'ferry', 1, 200)])
        self.worker.save_state({'version': 1, 'revisions': self.worker.snapshot(), 'retry': {}})
        self.initial = self.state()['revisions']

    def new_worker(self):
        worker = load(self.path)
        worker.ROOT = self.root
        worker.STATE = self.root/'state.json'
        worker.LOCK = self.root/'worker.lock'
        worker.LOG.disabled = True
        return worker

    def state(self):
        return json.loads(self.worker.STATE.read_text())

    def edit(self, identity=1, price=101, status=None):
        with sqlite3.connect(self.root/'crm.db') as conn:
            if status:
                conn.execute('UPDATE cars SET status=? WHERE id=?', (status, identity))
            else:
                conn.execute('UPDATE cars SET price=? WHERE id=?', (price, identity))

    def run_once(self):
        return self.worker.reconcile_once(publish=self.publish, clock=lambda: self.now)

    def test_unchanged_legacy_state_is_not_republished(self):
        state = self.state()
        for revision in state['revisions'].values():
            revision.pop('delivery_status')
        self.worker.save_state(state)
        self.assertEqual(self.run_once(), 'idle')
        self.publish.assert_not_called()

    def test_catalog_failure_has_one_attempt_for_all_pending_cars(self):
        self.edit(); self.edit(2, 201)
        self.publish.return_value = (False, 'CATALOG_ROW_SET_MISMATCH')
        self.assertEqual(self.run_once(), 'catalog_retry_pending')
        self.assertEqual(self.publish.call_count, 1)
        self.assertEqual(self.state()['revisions'], self.initial)
        for offset in (1, 15, 120, 899):
            self.now = 100 + offset
            self.worker.notify()
            self.assertEqual(self.run_once(), 'catalog_retry_pending')
        self.assertEqual(self.publish.call_count, 1)

    def test_cooldown_survives_restart_and_html_mtime_changes(self):
        self.edit()
        self.publish.return_value = (False, 'CATALOG_PUBLISHED_SET_MISMATCH')
        self.run_once()
        self.worker = self.new_worker()
        (self.root/'katalog.html').write_text('rewritten output')
        self.now += 400
        self.assertEqual(self.run_once(), 'catalog_retry_pending')
        self.assertEqual(self.publish.call_count, 1)

    def test_new_operator_edit_reopens_catalog_retry(self):
        self.edit()
        self.publish.return_value = (False, 'CATALOG_ROW_SET_MISMATCH')
        self.run_once()
        self.edit(2, 201)
        self.publish.return_value = (True, 'ok')
        self.assertEqual(self.run_once(), 'published')
        self.assertEqual(self.publish.call_count, 2)
        self.assertNotIn('catalog_retry', self.state())

    def test_catalog_retry_resumes_after_cooldown_without_new_data(self):
        self.edit()
        self.publish.return_value = (False, 'CATALOG_ROW_SET_MISMATCH')
        self.run_once()
        self.publish.return_value = (True, 'ok')
        self.now += 900
        self.assertEqual(self.run_once(), 'published')

    def test_transient_failure_does_not_starve_other_car(self):
        self.edit(); self.edit(2, 201)
        self.publish.side_effect = [(False, 'PUBLICATION_FENCE_TIMEOUT'), (True, 'ok')]
        self.assertEqual(self.run_once(), 'published')
        self.assertEqual(self.state()['revisions']['1'], self.initial['1'])
        self.assertNotEqual(self.state()['revisions']['2'], self.initial['2'])
        self.assertNotIn('catalog_retry', self.state())

    def test_transient_retry_grows_and_is_bounded(self):
        self.edit()
        self.publish.side_effect = TimeoutError('temporary')
        delays = []
        for _ in range(10):
            self.run_once()
            after = self.state()['retry']['1']['after']
            delays.append(after-self.now)
            self.now = after
        self.assertEqual(delays[:4], [15, 30, 60, 120])
        self.assertEqual(delays[-1], 900)
        self.assertEqual(max(delays), 900)

    def test_concurrent_edit_is_retained_for_next_publication(self):
        self.edit()
        self.publish.side_effect = lambda _: (self.edit(price=102) or True, 'ok')
        self.assertEqual(self.run_once(), 'changed_during_publish')
        self.assertEqual(self.state()['revisions'], self.initial)

    def test_hidden_card_uses_reconciler_without_full_publisher(self):
        self.edit(status='archive')
        self.assertEqual(self.run_once(), 'hidden')
        self.hide.assert_called_once_with(apply=True)
        self.publish.assert_not_called()
        self.verify.assert_not_called()

    def test_single_worker_lock_prevents_duplicate_publication(self):
        import fcntl
        self.edit()
        with self.worker.LOCK.open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.run_once(), 'busy')
        self.publish.assert_not_called()


class CallbackTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name)/'callbacks.py'
        path.write_text(patch_callbacks((FIXTURES/'callbacks_before.py').read_text()))
        self.module = load(path)
        self.module.log = logging.getLogger('test-callback')
        self.module.log.disabled = True
        self.notify = Mock()
        self.reconcile = Mock(side_effect=AssertionError('UI must not publish'))
        self.modules = patch.dict(sys.modules, {
            'ua_crm_public_sync': SimpleNamespace(notify=self.notify),
            'ua_stage_catalog_sync': SimpleNamespace(reconcile=self.reconcile),
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)

    async def test_saved_stage_returns_without_publication_or_lock(self):
        result = await asyncio.wait_for(self.module._ua004_sync_current_stage({'published': 1}), 0.5)
        self.assertIn('в фоне', result)
        self.assertNotIn('✅', result)
        self.notify.assert_called_once()
        self.reconcile.assert_not_called()

    async def test_unpublished_card_does_not_request_publication(self):
        self.assertEqual(await self.module._ua004_sync_current_stage({'published': 0}), '')
        self.notify.assert_not_called()

    async def test_periodic_job_only_wakes_existing_worker(self):
        for _ in range(10):
            await self.module._ua004_stage_reconcile_job(None)
        self.assertEqual(self.notify.call_count, 10)
        self.reconcile.assert_not_called()

    async def test_notification_error_does_not_claim_site_success(self):
        self.notify.side_effect = RuntimeError('worker unavailable')
        text = await self.module._ua004_sync_current_stage({'published': 1})
        self.assertIn('пока не подтверждено', text)


class SourcePinTest(unittest.TestCase):
    def test_rejects_changed_source_before_building(self):
        with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED:cars_ui.py'):
            build({'cars_ui.py': b'changed', 'ua_crm_public_sync.py': b'changed'})


if __name__ == '__main__':
    unittest.main()
