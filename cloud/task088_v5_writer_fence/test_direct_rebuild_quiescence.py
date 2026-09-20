"""Targeted exact-composition regressions for direct renderer price safety.

Synthetic DB and temporary publication lock only; no production imports/writes.
"""
import ast
import contextlib
import hashlib
import os
from pathlib import Path
import select
import sqlite3
import sys
import threading
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
for directory in (HERE, HERE.parent / 'task088_price_sync', HERE.parent / 'task088_stage3_renderer'):
    sys.path.insert(0, str(directory))
import integrate_private_sources as integration
import patch_cars_ui
import patch_guard
import patch_stranica
import publication_fence as fence
import test_guard_fence as legacy_fixture


class DirectRebuildQuiescenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = Path(os.environ['UA114_PRIVATE_BASE'])
        deps = Path(os.environ['UA114_DEPENDENCY_BASE'])
        prices = {
            'cars_ui.py': patch_cars_ui.patch_source((base / 'cars_ui.py').read_text()).encode(),
            'publish_transaction_guard.py': patch_guard.patch_source((base / 'publish_transaction_guard.py').read_text()).encode(),
            'stranica.py': patch_stranica.patch_stranica((base / 'stranica.py').read_bytes())[0],
        }
        cls.prices = prices
        cls.composed = integration.compose_price_candidate(prices,
            {name: (deps / name).read_bytes() for name in integration.DEPENDENCY_SHA256})
        os.environ['TASK088_PUBLISH_GUARD_SOURCE'] = str(base / 'publish_transaction_guard.py')
        legacy_fixture.GuardFenceTests.setUpClass()

    def setUp(self):
        self.fixture = legacy_fixture.GuardFenceTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.lock = self.fixture.root / 'shared.lock'
        real_require = fence.require_publication_fence
        self.patch(fence, 'publication_fence', lambda **kwargs: fence.PublicationFence(
            lock_path=self.lock, _test_only_path=True, **kwargs))
        self.patch(fence, 'require_publication_fence', lambda: real_require(lock_path=self.lock))
        self.guard = types.ModuleType('publish_transaction_guard')
        self.guard.__dict__.update(contextlib=contextlib, sqlite3=sqlite3,
            DB=self.fixture.path, PublishError=type('PublishError', (RuntimeError,), {}), WAIT_SECONDS=1,
            Snapshot=type('Snapshot', (), {'restore': lambda self: None}))
        # Execute the exact composed legacy helper and appended guard block;
        # exclude unrelated private publisher imports with production defaults.
        helper = [node for node in ast.parse(self.composed['publish_transaction_guard.py']).body
                  if isinstance(node, ast.FunctionDef) and node.name == '_task088_price_quiescence'][0]
        exec(compile(ast.Module(body=[helper], type_ignores=[]), '<exact-composed-base>', 'exec'), self.guard.__dict__)
        exec(integration.GUARD_BLOCK, self.guard.__dict__)
        modpatch = patch.dict(sys.modules, {'publish_transaction_guard': self.guard})
        modpatch.start()
        self.addCleanup(modpatch.stop)
        self.observed = []
        self.ns = {'zapisat': lambda *a, **k: self.observed.append('write'),
                   'obnovit_etalon': lambda *a, **k: self.observed.append('etalon'),
                   'main': lambda *a, **k: self.observed.append('render')}
        exec(integration.STRANICA_BLOCK, self.ns)

    def patch(self, obj, name, value):
        item = patch.object(obj, name, value)
        item.start()
        self.addCleanup(item.stop)

    def assert_released(self):
        self.assertIsNone(getattr(self.guard._ua114_price_tls, 'state', None))
        self.fixture.db.execute('BEGIN IMMEDIATE')
        self.fixture.db.rollback()

    def test_exact_legacy_helper_changes_only_connection_yield(self):
        def helpers(raw):
            return [node for node in ast.parse(raw).body if isinstance(node, ast.FunctionDef)
                    and node.name == '_task088_price_quiescence']
        before = helpers(self.prices['publish_transaction_guard.py'])[0]
        after = helpers(self.composed['publish_transaction_guard.py'])[0]
        self.assertEqual(len(helpers(self.composed['publish_transaction_guard.py'])), 2)
        yields = [n for n in ast.walk(before) if isinstance(n, ast.Yield)]
        self.assertEqual(len(yields), 1)
        yields[0].value = ast.Name(id='connection', ctx=ast.Load())
        self.assertEqual(ast.dump(before), ast.dump(after))

    def test_all_direct_entries_reject_actual_db_committed_checkpoint_before_work(self):
        event = self.fixture.advance_v5(self.fixture.submit_v5(), stop='DB_COMMITTED')
        self.assertEqual(event['state'], 'DB_COMMITTED')
        for name in ('main', 'zapisat', 'obnovit_etalon'):
            with self.subTest(entry=name):
                with self.assertRaisesRegex(self.guard.PublishError, 'V5_UNVERIFIED_PRICE_INTENTS'):
                    self.ns[name]()
                self.assertEqual(self.observed, [])
                self.assert_released()

    def test_guard_main_nested_writes_use_one_reserved_transaction_before_spec(self):
        starts = []
        real_connect = sqlite3.connect
        def connect(*a, **k):
            connection = real_connect(*a, **k)
            connection.set_trace_callback(lambda sql: starts.append(sql) if sql == 'BEGIN IMMEDIATE' else None)
            return connection
        self.patch(sqlite3, 'connect', connect)
        depths = []
        def write():
            fence.require_publication_fence()
            state = self.guard._ua114_price_tls.state
            depths.append(state['depth'])
            self.assertTrue(state['connection'].in_transaction)
            with self.assertRaises(sqlite3.OperationalError):
                self.fixture.db.execute('BEGIN IMMEDIATE')
            self.observed.append('spec/write')
        self.ns['_ua114_zapisat_base'] = write
        self.ns['_ua114_obnovit_etalon_base'] = write
        self.ns['_ua114_main_base'] = lambda: (self.ns['zapisat'](), self.ns['obnovit_etalon']())
        with self.guard._exclusive_lock(), self.guard._task088_price_quiescence():
            self.ns['main']()
            self.assertEqual(self.guard._ua114_price_tls.state['depth'], 1)
        self.assertEqual(starts, ['BEGIN IMMEDIATE'])
        self.assertEqual(depths, [3, 3])
        self.assertEqual(self.observed, ['spec/write', 'spec/write'])
        self.assert_released()

    def test_concurrent_thread_waits_for_outer_lease_and_cannot_bypass_fence(self):
        attempted = threading.Event()
        finished = threading.Event()
        errors = []
        def worker():
            attempted.set()
            try:
                with self.assertRaisesRegex(fence.FenceError, 'PUBLICATION_FENCE_REQUIRED'):
                    with self.guard._task088_price_quiescence():
                        self.fail('unfenced entry allowed')
                self.ns['main']()
            except BaseException as exc:
                errors.append(repr(exc))
            finally:
                finished.set()
        with self.guard._exclusive_lock(), self.guard._task088_price_quiescence():
            thread = threading.Thread(target=worker)
            thread.start()
            self.assertTrue(attempted.wait(1))
            self.assertFalse(finished.wait(.05))
            self.assertEqual(self.observed, [])
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(self.observed, ['render'])
        self.assert_released()

    def test_nested_exception_releases_connection_and_next_entry_succeeds(self):
        def fail():
            raise RuntimeError('renderer failed')
        self.ns['_ua114_zapisat_base'] = fail
        self.ns['_ua114_main_base'] = lambda: self.ns['zapisat']()
        with self.assertRaisesRegex(RuntimeError, 'renderer failed'):
            self.ns['main']()
        self.assert_released()
        self.ns['_ua114_main_base'] = lambda: self.observed.append('retry-new-operation')
        self.ns['main']()
        self.assertEqual(self.observed, ['retry-new-operation'])
        self.assert_released()

    def test_reentry_rejects_database_rebinding_and_ended_transaction(self):
        with self.guard._exclusive_lock(), self.guard._task088_price_quiescence():
            saved = self.guard.DB
            self.guard.DB = self.fixture.root / 'other.db'
            self.guard.DB.write_bytes(b'')
            try:
                with self.assertRaisesRegex(self.guard.PublishError, 'LEASE_CHANGED'):
                    self.ns['main']()
            finally:
                self.guard.DB = saved
            self.guard._ua114_price_tls.state['connection'].rollback()
            with self.assertRaisesRegex(self.guard.PublishError, 'TRANSACTION_REQUIRED'):
                self.ns['main']()
        self.assertEqual(self.observed, [])
        self.assert_released()

    @unittest.skipUnless(hasattr(os, 'fork'), 'requires POSIX fork')
    def test_fork_child_rejects_reentry_and_parent_context_cleanup_without_sqlite_calls(self):
        readfd, writefd = os.pipe()
        self.addCleanup(os.close, readfd)
        self.addCleanup(os.close, writefd)
        calls = []
        real_connect = sqlite3.connect
        class ConnectionProxy:
            def __init__(self, raw): self.raw = raw
            def __getattr__(self, name):
                value = getattr(self.raw, name)
                if name in ('close', 'rollback'):
                    def tracked(*a, **k):
                        calls.append(name)
                        return value(*a, **k)
                    return tracked
                return value
        self.patch(sqlite3, 'connect', lambda *a, **k: ConnectionProxy(real_connect(*a, **k)))
        with self.guard._exclusive_lock():
            cm = self.guard._task088_price_quiescence()
            cm.__enter__()
            pid = os.fork()
            if pid == 0:
                try:
                    rejected = []
                    # Parent publication descriptor is closed by fork cleanup;
                    # a fresh fence cannot be taken until parent releases it.
                    # Assert inherited guard exit never invokes its SQLite CM.
                    try:
                        cm.__exit__(None, None, None)
                    except self.guard.PublishError as exc:
                        rejected.append('FORK_REQUIRES_EXEC' in str(exc))
                    # Fresh ownership assertion stub solely isolates PID check.
                    fence.require_publication_fence = lambda: None
                    try:
                        with self.guard._task088_price_quiescence(): pass
                    except self.guard.PublishError as exc:
                        rejected.append('FORK_REQUIRES_EXEC' in str(exc))
                    os.write(writefd, repr((rejected, calls)).encode())
                finally:
                    os._exit(0)
            ready, _, _ = select.select([readfd], [], [], 3)
            self.assertTrue(ready, 'fork child did not complete')
            result = os.read(readfd, 4096).decode()
            _, status = os.waitpid(pid, 0)
            self.assertEqual(status, 0)
            self.assertEqual(result, '([True, True], [])')
            self.assertTrue(self.guard._ua114_price_tls.state['connection'].in_transaction)
            with self.assertRaises(sqlite3.OperationalError):
                self.fixture.db.execute('BEGIN IMMEDIATE')
            cm.__exit__(None, None, None)
        self.assertEqual(calls, ['rollback', 'close'])
        self.assert_released()

    def test_writer_only_missing_price_helper_fails_explicitly(self):
        guard = types.ModuleType('writer_only_guard')
        guard.__dict__.update(PublishError=RuntimeError, WAIT_SECONDS=1, DB=self.fixture.path,
                             Snapshot=type('Snapshot', (), {'restore': lambda self: None}))
        exec(integration.GUARD_BLOCK, guard.__dict__)
        with guard._exclusive_lock():
            with self.assertRaisesRegex(RuntimeError, 'COMPOSED_CANDIDATE_REQUIRED'):
                with guard._task088_price_quiescence(): pass


if __name__ == '__main__':
    unittest.main()
