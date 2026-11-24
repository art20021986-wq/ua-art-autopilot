"""Outage guard, candidate build on the exact installed sources, and the real candidate job with a failing storage."""
import asyncio
import difflib
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder as builder  # noqa: E402
import ua_order_outbox_guard as guard_module  # noqa: E402

# Installed sources read by ORDER-STORAGE-CHECK-20261114-R2 (bindings, notifications, storage are byte-exact).
EVIDENCE = json.loads((HERE.parent/'order_storage_check_001/evidence.json').read_text())
LIVE = {n: (EVIDENCE['sources']['/home/Carix/ua_order/%s.py' % n]['text'] + '\n').encode()
        for n in ('bindings', 'notifications', 'storage')}
REPOSITORY_TEXT = EVIDENCE['sources']['/home/Carix/ua_order/mysql_repository.py']['text'].encode()


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class GuardTests(unittest.TestCase):
    def test_reports_once_after_five_minutes_and_resets(self):
        clock = Clock()
        guard = guard_module.OutageGuard(clock=clock)
        with self.assertLogs(guard_module.log, 'WARNING'):
            self.assertFalse(guard.failed())
            clock.now = 299
            self.assertFalse(guard.failed())
            clock.now = 300
            self.assertTrue(guard.failed())
            clock.now = 900
            self.assertFalse(guard.failed())
            guard.ok()
            clock.now = 901
            self.assertFalse(guard.failed())
            clock.now = 1201
            self.assertTrue(guard.failed())


class BuildTests(unittest.TestCase):
    def test_live_snapshots_are_the_pinned_versions(self):
        for name in ('notifications', 'storage'):
            self.assertEqual(hashlib.sha256(LIVE[name]).hexdigest(), builder.DEPENDENCY_SHA256['ua_order/%s.py' % name])
        self.assertEqual(hashlib.sha256(LIVE['bindings']).hexdigest(), builder.SOURCE_SHA256['ua_order/bindings.py'])

    def test_bindings_change_is_only_the_job(self):
        after = (HERE/'ua_order_bindings.py').read_bytes().decode()
        added = [l[2:] for l in difflib.ndiff(LIVE['bindings'].decode().splitlines(), after.splitlines()) if l[:1] == '+']
        removed = [l[2:] for l in difflib.ndiff(LIVE['bindings'].decode().splitlines(), after.splitlines()) if l[:1] == '-']
        self.assertEqual(removed, ['        await dispatch_once(runtime.service.repository, deliver)'])
        self.assertIn('from .outbox_guard import OutageGuard', added)
        self.assertIn('        guard.ok()', added)
        self.assertEqual(len(added), 12)

    def test_repository_patch_logs_code_once(self):
        value = builder.patch_repository(REPOSITORY_TEXT)
        self.assertEqual(value.count(b'import logging\n'), 1)
        self.assertEqual(value.count(b"'MySQL error %s'"), 1)
        self.assertEqual(len(value.splitlines()) - len(REPOSITORY_TEXT.splitlines()), 3)
        with self.assertRaisesRegex(ValueError, 'REPOSITORY_ANCHOR'):
            builder.patch_repository(value)

    def test_build_checks_every_input(self):
        source = {'ua_order/bindings.py': LIVE['bindings'], 'ua_order/mysql_repository.py': REPOSITORY_TEXT}
        dependencies = {'ua_order/notifications.py': LIVE['notifications'], 'ua_order/storage.py': LIVE['storage']}
        pinned = dict(builder.SOURCE_SHA256, **{'ua_order/mysql_repository.py': hashlib.sha256(REPOSITORY_TEXT).hexdigest()})
        with patch.object(builder, 'SOURCE_SHA256', pinned):
            candidate = builder.build(source, dependencies)
            self.assertEqual(sorted(candidate), ['ua_order/bindings.py', 'ua_order/mysql_repository.py',
                                                 'ua_order/outbox_guard.py'])
            with self.assertRaisesRegex(ValueError, 'INPUT_HASH:ua_order/storage.py'):
                builder.build(source, dict(dependencies, **{'ua_order/storage.py': b'x'}))


class JobTests(unittest.TestCase):
    """The candidate bindings.py with the installed notifications.py and storage.py; crm/telegram are stubs."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        package = Path(self.temporary.name)/'ua_order'
        package.mkdir()
        (package/'__init__.py').write_text('')
        (package/'bindings.py').write_bytes((HERE/'ua_order_bindings.py').read_bytes())
        (package/'outbox_guard.py').write_bytes((HERE/'ua_order_outbox_guard.py').read_bytes())
        (package/'notifications.py').write_bytes(LIVE['notifications'])
        (package/'storage.py').write_bytes(LIVE['storage'])
        (package/'crm.py').write_text('def detail_view(row, catalog):\n    return {"text": "x"}\n')
        (package/'telegram.py').write_text('class CRMAdapter:\n    def __init__(self, *a, **k): pass\n'
                                           '    def register(self, app, group): pass\nclass CustomerAdapter: pass\n'
                                           'def _markup(rows): return rows\n')
        sys.path.insert(0, self.temporary.name)
        self.addCleanup(sys.path.remove, self.temporary.name)
        for name in [n for n in sys.modules if n == 'ua_order' or n.startswith('ua_order.')]:
            del sys.modules[name]
        self.bindings = importlib.import_module('ua_order.bindings')
        self.storage = importlib.import_module('ua_order.storage')
        self.guard = importlib.import_module('ua_order.outbox_guard')

    def start(self, repository):
        clock = Clock()
        jobs = []
        app = types.SimpleNamespace(handlers={}, bot=None, job_queue=types.SimpleNamespace(
            get_jobs_by_name=lambda name: [], run_repeating=lambda callback, **k: jobs.append((callback, k))))
        runtime = types.SimpleNamespace(service=types.SimpleNamespace(repository=repository, catalog=None))
        with patch.object(self.bindings, 'OutageGuard', lambda: self.guard.OutageGuard(clock=clock)):
            self.bindings.owner_inbox(app, runtime, owner_id=1)
        self.assertEqual(jobs[0][1], {'interval': 5, 'first': 1, 'name': 'ua_order_outbox'})
        return jobs[0][0], clock

    def test_short_outage_is_silent_long_outage_reported_once(self):
        storage = self.storage

        class Down:
            def claim_notification(self):
                raise storage.StorageUnavailable('Order storage unavailable')
        job, clock = self.start(Down())
        with self.assertLogs(self.guard.log, 'WARNING'):
            for moment in (0, 5, 46, 295):
                clock.now = moment
                self.assertIsNone(asyncio.run(job(None)))
            clock.now = 300
            with self.assertRaisesRegex(storage.StorageUnavailable, '5\\+ minutes'):
                asyncio.run(job(None))
            clock.now = 305
            self.assertIsNone(asyncio.run(job(None)))

    def test_recovery_resets_and_other_errors_still_reach_the_handler(self):
        storage = self.storage
        state = {'down': True}

        class Flaky:
            def claim_notification(self):
                if state['down'] == 'boom':
                    raise KeyError('other')
                if state['down']:
                    raise storage.StorageUnavailable('Order storage unavailable')
                return None
        job, clock = self.start(Flaky())
        with self.assertLogs(self.guard.log, 'WARNING'):
            asyncio.run(job(None))
            clock.now = 200
            state['down'] = False
            asyncio.run(job(None))
            state['down'] = True
            clock.now = 450
            asyncio.run(job(None))
            clock.now = 700
            asyncio.run(job(None))
        state['down'] = 'boom'
        with self.assertRaises(KeyError):
            asyncio.run(job(None))


if __name__ == '__main__':
    unittest.main()
