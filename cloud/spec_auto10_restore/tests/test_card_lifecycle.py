"""Actual pinned CRM callbacks + temporary SQLite/files + real thread/process lock.

No Telegram, network, running CRM, production directories or external services.
The catalog/publisher callbacks are deterministic local dependency fixtures;
these tests do not establish real publisher/golden-template deployment success.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

PACKAGE = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


integration = load("lifecycle_source_patch", PACKAGE / "lifecycle_integration.py")
lifecycle = load("card_lifecycle", PACKAGE / "runtime" / "card_lifecycle.py")
BASE_GUARD = (PACKAGE.parent / "task_083_publish_transaction" / "publish_transaction_guard.py").read_text()
HANDLERS = (PACKAGE / "tests" / "fixtures" / "lifecycle_current_handlers.py").read_text()


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.guard = types.ModuleType("publish_transaction_guard")
        installed = patch.dict(sys.modules, {'publish_transaction_guard': self.guard, 'card_lifecycle': lifecycle})
        installed.start()
        self.addCleanup(installed.stop)
        with patch.dict(os.environ, {"UA_ART_ROOT": str(self.root)}):
            exec(compile(integration.patch_publish_transaction_guard(BASE_GUARD), "<actual-guard-patched>", "exec"), self.guard.__dict__)
        self.guard.WAIT_SECONDS = 0.2
        for root in self.guard.ROOTS:
            root.mkdir()
            (root / "UA-0001.html").write_text('<html>original primary</html>')
            (root / "UA-0001-diag.html").write_text('<html>original diagnosis</html>')
            (root / "UA-0002.html").write_text('<html>other card unchanged</html>')
            (root / "UA-0001-owner-note.html").write_text('operator owned unknown file')
        with sqlite3.connect(self.guard.DB) as db:
            db.execute('CREATE TABLE cars(id INTEGER PRIMARY KEY AUTOINCREMENT, auto_number TEXT, published INTEGER, status TEXT, publish_pending INTEGER, updated_at TEXT, description TEXT)')
            db.executemany('INSERT INTO cars VALUES(?,?,?,?,?,?,?)', [(1, 'UA-0001', 1, 'sea_transit', 1, 'original-date', 'original text'), (2, 'UA-0002', 1, 'sea_transit', 0, 'other-date', 'other text')])
            db.execute('CREATE TABLE media(id INTEGER PRIMARY KEY, car_id INTEGER, file_id TEXT)')
            db.execute("INSERT INTO media VALUES(1,1,'saved-media-file-id')")
        self.spec = self.root / 'vin_specs_task111_v3.db'
        with sqlite3.connect(self.spec) as db:
            db.execute('CREATE TABLE additional_specification(car_uid TEXT, field_key TEXT, field_value TEXT)')
            db.execute("INSERT INTO additional_specification VALUES('UA-0001','wheelbase','2805')")
        self.spec_hash = hashlib.sha256(self.spec.read_bytes()).hexdigest()
        self.guard.rebuild_catalog = self.rebuild_catalog
        self.rebuild_catalog()
        self.before_files = self.site_files()

    def site_files(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for root in self.guard.ROOTS for path in root.glob('*') if path.is_file()}

    def rows(self, query='SELECT * FROM cars ORDER BY id'):
        with sqlite3.connect(self.guard.DB) as db:
            return db.execute(query).fetchall()

    def rebuild_catalog(self):
        with self.guard._exclusive_lock():
            rows = self.rows('SELECT auto_number FROM cars WHERE published=1 ORDER BY id')
            body = '<html><body>' + ''.join('<a href="' + row[0] + '.html">car</a>' for row in rows) + '</body></html>'
            for root in self.guard.ROOTS:
                (root / 'katalog.html').write_text(body)
            return True, 'catalog rebuilt'

    def assert_preserved(self):
        self.assertEqual(hashlib.sha256(self.spec.read_bytes()).hexdigest(), self.spec_hash)
        self.assertEqual(self.rows('SELECT * FROM media'), [(1, 1, 'saved-media-file-id')])
        for root in self.guard.ROOTS:
            self.assertEqual((root / 'UA-0001-owner-note.html').read_text(), 'operator owned unknown file')
            self.assertEqual((root / 'UA-0002.html').read_text(), '<html>other card unchanged</html>')

    def assert_withdrawn(self):
        for root in self.guard.ROOTS:
            self.assertFalse((root / 'UA-0001.html').exists())
            self.assertFalse((root / 'UA-0001-diag.html').exists())
            self.assertNotIn('UA-0001', (root / 'katalog.html').read_text())

    def test_delete_withdraws_both_roots_preserves_media_facts_and_retired_identifier(self):
        ok, _ = lifecycle.delete_card(1, 123, guard=self.guard)
        self.assertTrue(ok)
        self.assertEqual(len(self.rows()), 1)
        self.assert_withdrawn()
        self.assert_preserved()
        record = self.rows('SELECT auto_number,state,action,actor_id,previous_row_json FROM ua_spec_lifecycle_archive')[0]
        self.assertEqual(record[:4], ('UA-0001', 'COMPLETED', 'delete', 123))
        self.assertEqual(json.loads(record[4])['description'], 'original text')
        manifests = list((self.root / 'rezerv_publikacii' / 'SPEC_LIFECYCLE').glob('*/manifest.json'))
        self.assertEqual(json.loads(manifests[0].read_text())['state'], 'COMPLETED')

    def test_hide_withdraws_direct_links_and_retains_editable_crm_card(self):
        self.assertTrue(lifecycle.set_visibility(1, False, guard=self.guard)[0])
        self.assertEqual(self.rows('SELECT published,publish_pending,status FROM cars WHERE id=1'), [(0, 0, 'sea_transit')])
        self.assert_withdrawn()
        self.assert_preserved()

    def test_sold_uses_the_same_withdrawal_transaction(self):
        self.assertTrue(lifecycle.mark_sold(1, guard=self.guard)[0])
        self.assertEqual(self.rows('SELECT published,status FROM cars WHERE id=1'), [(0, 'sold')])
        self.assert_withdrawn()
        self.assert_preserved()

    def test_partial_catalog_failure_restores_deleted_row_and_all_pages(self):
        before = self.rows()
        def failed():
            (self.guard.ROOTS[0] / 'katalog.html').write_text('partial broken catalog')
            return False, 'injected failure after first catalog write'
        self.guard.rebuild_catalog = failed
        self.assertFalse(lifecycle.delete_card(1, guard=self.guard)[0])
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.site_files(), self.before_files)
        self.assertEqual(self.rows('SELECT state FROM ua_spec_lifecycle_archive'), [('ROLLED_BACK',)])
        self.assert_preserved()

    def test_failed_hide_preserves_concurrent_unrelated_crm_edit(self):
        def failed():
            with sqlite3.connect(self.guard.DB) as db:
                db.execute("UPDATE cars SET description='new owner edit',updated_at='owner-edit-time' WHERE id=1")
            return False, 'injected catalog failure'
        self.guard.rebuild_catalog = failed
        self.assertFalse(lifecycle.set_visibility(1, False, guard=self.guard)[0])
        self.assertEqual(self.rows('SELECT published,publish_pending,updated_at,description FROM cars WHERE id=1'), [(1, 1, 'owner-edit-time', 'new owner edit')])
        self.assertEqual(self.site_files(), self.before_files)

    def test_conflicting_concurrent_crm_edit_is_not_overwritten_silently(self):
        def failed():
            with sqlite3.connect(self.guard.DB) as db:
                db.execute("UPDATE cars SET published=1,updated_at='concurrent-other-publish' WHERE id=1")
            return False, 'injected catalog failure'
        self.guard.rebuild_catalog = failed
        with self.assertRaisesRegex(lifecycle.LifecycleError, 'КРИТИЧНО.*CONCURRENT_FIELD_CHANGE'):
            lifecycle.set_visibility(1, False, guard=self.guard)
        self.assertEqual(self.rows('SELECT updated_at FROM cars WHERE id=1'), [('concurrent-other-publish',)])

    def test_publish_failure_rolls_back_draft_and_new_pages(self):
        with sqlite3.connect(self.guard.DB) as db:
            db.execute('UPDATE cars SET published=0 WHERE id=1')
        for root in self.guard.ROOTS:
            (root / 'UA-0001.html').unlink()
            (root / 'UA-0001-diag.html').unlink()
        self.rebuild_catalog()
        before_files = self.site_files()
        before_rows = self.rows()
        def broken(code):
            with self.guard._exclusive_lock():
                (self.guard.ROOTS[0] / (code + '.html')).write_text('half publication')
                return False, 'injected publish failure'
        self.assertFalse(lifecycle.set_visibility(1, True, publisher=broken, guard=self.guard)[0])
        self.assertEqual(self.rows(), before_rows)
        self.assertEqual(self.site_files(), before_files)

    def test_successful_publish_calls_nested_publisher_without_deadlock(self):
        lifecycle.set_visibility(1, False, guard=self.guard)
        def publish(code):
            with self.guard._exclusive_lock():
                for root in self.guard.ROOTS:
                    (root / (code + '.html')).write_text('new verified page')
                    (root / (code + '-diag.html')).write_text('new verified diagnosis')
                return self.rebuild_catalog()
        self.assertTrue(lifecycle.set_visibility(1, True, publisher=publish, guard=self.guard)[0])
        self.assertEqual(self.rows('SELECT published FROM cars WHERE id=1'), [(1,)])
        self.assert_preserved()

    def test_symlink_target_rejected_without_touching_destination_or_crm(self):
        path = self.guard.ROOTS[0] / 'UA-0001.html'
        path.unlink()
        external = self.root / 'operator-document'
        external.write_text('do not modify')
        path.symlink_to(external)
        before = self.rows()
        self.assertFalse(lifecycle.delete_card(1, guard=self.guard)[0])
        self.assertEqual(external.read_text(), 'do not modify')
        self.assertEqual(self.rows(), before)
        self.assertTrue(path.is_symlink())

    def test_unreviewed_cascade_is_refused_before_deletion(self):
        with sqlite3.connect(self.guard.DB) as db:
            db.execute('CREATE TABLE dangerous_child(id INTEGER, car_id INTEGER REFERENCES cars(id) ON DELETE CASCADE)')
            db.execute('INSERT INTO dangerous_child VALUES(1,1)')
        ok, detail = lifecycle.delete_card(1, guard=self.guard)
        self.assertFalse(ok)
        self.assertIn('UNREVIEWED_CAR_DELETE_CASCADE', detail)
        self.assertEqual(len(self.rows()), 2)
        self.assertEqual(self.site_files(), self.before_files)
        self.assertEqual(self.rows('SELECT * FROM dangerous_child'), [(1, 1)])

    def test_guard_missing_reentrant_contract_fails_before_any_mutation(self):
        self.guard.LIFECYCLE_REENTRANT_LOCK = False
        with self.assertRaisesRegex(lifecycle.LifecycleError, 'SHARED_REENTRANT'):
            lifecycle.delete_card(1, guard=self.guard)
        self.assertEqual(len(self.rows()), 2)
        self.assertEqual(self.site_files(), self.before_files)

    def test_nested_lock_still_excludes_other_threads(self):
        observed = []
        entered = threading.Event()
        def contender():
            entered.set()
            try:
                with self.guard._exclusive_lock():
                    observed.append('entered')
            except self.guard.PublishError as exc:
                observed.append(str(exc))
        with self.guard._exclusive_lock():
            with self.guard._exclusive_lock():
                thread = threading.Thread(target=contender)
                thread.start()
                self.assertTrue(entered.wait(2))
                thread.join(2)
                self.assertFalse(thread.is_alive())
                self.assertEqual(observed, ['PUBLISH_LOCK_TIMEOUT'])
        with self.guard._exclusive_lock():
            pass

    def test_reentrant_lock_preserves_cross_process_flock_exclusion(self):
        script = "import fcntl,sys; f=open(sys.argv[1],'a+'); fcntl.flock(f,fcntl.LOCK_EX); print('ready',flush=True); input()"
        process = subprocess.Popen([sys.executable, '-I', '-B', '-c', script, str(self.guard.LOCK)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), 'ready')
            with self.assertRaisesRegex(self.guard.PublishError, 'PUBLISH_LOCK_TIMEOUT'):
                with self.guard._exclusive_lock():
                    self.fail('entered externally held lock')
        finally:
            process.communicate('\n', timeout=5)
        with self.guard._exclusive_lock():
            pass

    def test_actual_delete_callback_uses_transaction_not_bare_delete(self):
        class Stop(Exception):
            pass
        class Message:
            def __init__(self): self.messages = []
            async def reply_text(self, text, **kwargs): self.messages.append(text)
        async def ack(*args): pass
        message = Message()
        query = types.SimpleNamespace(data='car_delok:1', from_user=types.SimpleNamespace(id=123), message=message)
        namespace = {'_v168_ack': ack, 'ApplicationHandlerStop': Stop, 'log': logging.getLogger('lifecycle-test'),
                     'InlineKeyboardMarkup': lambda rows: rows,
                     'InlineKeyboardButton': lambda label, **kw: (label, kw)}
        exec(compile(integration.patch_cars_ui(HANDLERS), '<pinned-current-handler>', 'exec'), namespace)
        context = types.SimpleNamespace(user_data={'car_last': 1})
        with patch.dict(sys.modules, {'card_lifecycle': lifecycle, 'publish_transaction_guard': self.guard}):
            with self.assertRaises(Stop):
                asyncio.run(namespace['delete_ok'](types.SimpleNamespace(callback_query=query), context))
        self.assertNotIn('car_last', context.user_data)
        self.assert_withdrawn()
        self.assertEqual(len(self.rows()), 1)
        self.assertIn('удалена из CRM и с сайта', message.messages[-1])

    def test_unreviewed_actual_handler_or_lock_is_not_patched(self):
        with self.assertRaisesRegex(integration.IntegrationError, 'UNREVIEWED_FUNCTION:delete_ok'):
            integration.patch_cars_ui(HANDLERS.replace('DELETE FROM cars WHERE id=?', 'DELETE FROM cars'))
        with self.assertRaisesRegex(integration.IntegrationError, 'UNREVIEWED_FUNCTION:_exclusive_lock'):
            integration.patch_publish_transaction_guard(BASE_GUARD.replace('handle = open(LOCK, "a+")', 'handle = open(LOCK, "w")'))

    def test_identity_change_blocks_stale_page_rollback(self):
        with sqlite3.connect(self.guard.DB) as db:
            db.execute('ALTER TABLE cars ADD COLUMN vin TEXT')
            db.execute("UPDATE cars SET vin='ORIGINALVIN' WHERE id=1")
        def failed():
            with sqlite3.connect(self.guard.DB) as db:
                db.execute("UPDATE cars SET vin='DIFFERENTVIN' WHERE id=1")
            return False, 'injected error after identity changed'
        self.guard.rebuild_catalog = failed
        with self.assertRaisesRegex(lifecycle.LifecycleError, 'ROLLBACK_IDENTITY_CHANGED'):
            lifecycle.set_visibility(1, False, guard=self.guard)
        self.assertEqual(self.rows('SELECT vin FROM cars WHERE id=1'), [('DIFFERENTVIN',)])
        for root in self.guard.ROOTS:
            self.assertFalse((root / 'UA-0001.html').exists())

    def test_retired_identifier_cannot_publish_a_new_car_with_old_specification(self):
        self.assertTrue(lifecycle.delete_card(1, guard=self.guard)[0])
        with sqlite3.connect(self.guard.DB) as db:
            db.execute("INSERT INTO cars(auto_number,published,status,publish_pending) VALUES('UA-0001',0,'sea_transit',0)")
            new_id = db.execute('SELECT MAX(id) FROM cars').fetchone()[0]
        ok, detail = lifecycle.set_visibility(new_id, True, publisher=lambda code: self.fail('must not publish retired UID'), guard=self.guard)
        self.assertFalse(ok)
        self.assertIn('RETIRED_AUTO_NUMBER_REUSED', detail)
        self.assert_withdrawn()

    def test_duplicate_canonical_uid_is_rejected_before_withdrawal(self):
        with sqlite3.connect(self.guard.DB) as db:
            db.execute("INSERT INTO cars(auto_number,published,status) VALUES(' ua-0001 ',0,'sea_transit')")
        ok, detail = lifecycle.delete_card(1, guard=self.guard)
        self.assertFalse(ok)
        self.assertIn('DUPLICATE_UID', detail)
        self.assertEqual(len(self.rows()), 3)
        self.assertEqual(self.site_files(), self.before_files)

    def test_publication_identity_api_is_read_only_and_rejects_hidden_and_retired_uid(self):
        before_hash = hashlib.sha256(self.guard.DB.read_bytes()).hexdigest()
        with sqlite3.connect('file:' + str(self.guard.DB) + '?mode=ro', uri=True) as db:
            db.execute('PRAGMA query_only=ON')
            self.assertEqual(lifecycle.validate_publication_identity(db, 'ua-0001')['car_id'], 1)
        self.assertEqual(hashlib.sha256(self.guard.DB.read_bytes()).hexdigest(), before_hash)
        self.assertTrue(lifecycle.set_visibility(1, False, guard=self.guard)[0])
        with sqlite3.connect('file:' + str(self.guard.DB) + '?mode=ro', uri=True) as db:
            with self.assertRaisesRegex(lifecycle.LifecycleError, 'CARD_NOT_PUBLISHED'):
                lifecycle.validate_publication_identity(db, 'UA-0001')
        self.assertTrue(lifecycle.delete_card(1, guard=self.guard)[0])
        with sqlite3.connect(self.guard.DB) as db:
            db.execute("INSERT INTO cars(auto_number,published,status) VALUES('UA-0001',1,'sea_transit')")
        with sqlite3.connect('file:' + str(self.guard.DB) + '?mode=ro', uri=True) as db:
            with self.assertRaisesRegex(lifecycle.LifecycleError, 'RETIRED_AUTO_NUMBER_REUSED'):
                lifecycle.validate_publication_identity(db, 'UA-0001')

    def test_crash_after_delete_is_recovered_from_durable_archive(self):
        original = self.rows()
        def crash():
            raise KeyboardInterrupt('simulated process loss after row/page withdrawal')
        self.guard.rebuild_catalog = crash
        with self.assertRaises(KeyboardInterrupt):
            lifecycle.delete_card(1, guard=self.guard)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.rows('SELECT state FROM ua_spec_lifecycle_archive'), [('APPLIED',)])
        result = lifecycle.recover_pending(guard=self.guard)
        # The outer publisher-lock entry performs recovery before this explicit
        # call inspects its already-clean queue.
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(self.rows(), original)
        self.assertEqual(self.site_files(), self.before_files)
        self.assertEqual(self.rows('SELECT state FROM ua_spec_lifecycle_archive'), [('ROLLED_BACK',)])
        self.assert_preserved()

    def test_crash_during_rollback_resumes_after_already_restored_crm(self):
        original = self.rows()
        self.guard.rebuild_catalog = lambda: (False, 'injected catalog error')
        with patch.object(lifecycle._Snapshot, 'restore_files', side_effect=KeyboardInterrupt('simulated process loss in rollback')):
            with self.assertRaises(KeyboardInterrupt):
                lifecycle.delete_card(1, guard=self.guard)
        self.assertEqual(self.rows(), original)
        self.assertEqual(self.rows('SELECT state FROM ua_spec_lifecycle_archive'), [('ROLLBACK_DB_DONE',)])
        self.assertEqual(lifecycle.recover_pending(guard=self.guard)['status'], 'PASS')
        self.assertEqual(self.site_files(), self.before_files)
        self.assertEqual(lifecycle.recover_pending(guard=self.guard)['recovered'], [])

    def test_next_action_recovers_interrupted_operation_before_mutating_another_card(self):
        self.guard.rebuild_catalog = lambda: (_ for _ in ()).throw(KeyboardInterrupt('crash'))
        with self.assertRaises(KeyboardInterrupt):
            lifecycle.delete_card(1, guard=self.guard)
        self.guard.rebuild_catalog = self.rebuild_catalog
        self.assertTrue(lifecycle.set_visibility(2, False, guard=self.guard)[0])
        self.assertEqual(self.rows('SELECT id,published FROM cars ORDER BY id'), [(1, 1), (2, 0)])
        for root in self.guard.ROOTS:
            self.assertTrue((root / 'UA-0001.html').exists())
            self.assertFalse((root / 'UA-0002.html').exists())

    def test_regular_publisher_lock_recovers_before_another_card_is_added(self):
        self.guard.rebuild_catalog = lambda: (_ for _ in ()).throw(KeyboardInterrupt('crash'))
        with self.assertRaises(KeyboardInterrupt):
            lifecycle.delete_card(1, guard=self.guard)
        # A normal publisher obtains this lock independently of lifecycle/worker.
        with self.guard._exclusive_lock():
            self.assertEqual(self.rows('SELECT id FROM cars WHERE id=1'), [(1,)])
            with sqlite3.connect(self.guard.DB) as db:
                db.execute("INSERT INTO cars(id,auto_number,published,status) VALUES(3,'UA-0003',1,'sea_transit')")
            self.rebuild_catalog()
        lifecycle.recover_pending(guard=self.guard)
        for root in self.guard.ROOTS:
            text = (root / 'katalog.html').read_text()
            self.assertIn('UA-0001', text)
            self.assertIn('UA-0003', text)

    def test_completed_deleted_uid_is_retired_even_if_manual_insert_reuses_car_id(self):
        self.assertTrue(lifecycle.delete_card(1, guard=self.guard)[0])
        with sqlite3.connect(self.guard.DB) as db:
            db.execute("INSERT INTO cars(id,auto_number,published,status) VALUES(1,'UA-0001',1,'sea_transit')")
        with sqlite3.connect('file:' + str(self.guard.DB) + '?mode=ro', uri=True) as db:
            with self.assertRaisesRegex(lifecycle.LifecycleError, 'RETIRED_AUTO_NUMBER_REUSED'):
                lifecycle.validate_publication_identity(db, 'UA-0001')

    def test_pending_recovery_blocks_readonly_gate_outside_authorized_operation(self):
        self.guard.rebuild_catalog = lambda: (_ for _ in ()).throw(KeyboardInterrupt('crash'))
        with self.assertRaises(KeyboardInterrupt):
            lifecycle.set_visibility(1, False, guard=self.guard)
        with sqlite3.connect('file:' + str(self.guard.DB) + '?mode=ro', uri=True) as db:
            with self.assertRaisesRegex(lifecycle.LifecycleError, 'RECOVERY_REQUIRED'):
                lifecycle.validate_publication_identity(db, 'UA-0001', require_published=False)

    def test_own_nested_publication_passes_pending_gate_with_operation_token(self):
        lifecycle.set_visibility(1, False, guard=self.guard)
        def publish(code):
            with self.guard._exclusive_lock():
                with sqlite3.connect('file:' + str(self.guard.DB) + '?mode=ro', uri=True) as db:
                    self.assertEqual(lifecycle.validate_publication_identity(db, code)['car_id'], 1)
                for root in self.guard.ROOTS:
                    (root / (code + '.html')).write_text('published')
                    (root / (code + '-diag.html')).write_text('diagnosis')
                return self.rebuild_catalog()
        self.assertTrue(lifecycle.set_visibility(1, True, publisher=publish, guard=self.guard)[0])


if __name__ == '__main__':
    unittest.main()
