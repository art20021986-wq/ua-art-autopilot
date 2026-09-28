"""Actual handlers + real coordinator/SQLite/filesystem; fake Telegram and HTTP.

No production source import, Telegram token, external network, or live writes.
"""
import asyncio
import contextlib
import hashlib
import logging
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import types
import unittest


class Button:
    def __init__(self, text, callback_data):
        self.text, self.callback_data = text, callback_data


class Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class Stop(Exception):
    pass


telegram = types.ModuleType('telegram')
telegram.InlineKeyboardButton, telegram.InlineKeyboardMarkup = Button, Markup
telegram_ext = types.ModuleType('telegram.ext')
telegram_ext.ApplicationHandlerStop = Stop
sys.modules.setdefault('telegram', telegram)
sys.modules.setdefault('telegram.ext', telegram_ext)
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
from ua_crm_delete_bot import CoordinatorBackend, TelegramDeletionAdapter, register_adapter, APP_KEY
from deletion_core.coordinator import Coordinator
from deletion_core.deletion_state import application_schema_sha256, ImmediateTransaction, install_additive_schema
from deletion_core.retirement import retire_html
from build_bot_patch import build_candidate, SOURCE_SHA256


class FixtureBinding:
    """Small deterministic site, real durable coordinator and database."""
    def __init__(self, root):
        self.public_root = root
        self.journal_root = root / 'private'
        self.journal_root.mkdir(mode=0o700)
        self.config = {}
        (self.journal_root / 'runtime.json').write_text('{}')
        (root / 'site').mkdir()
        (root / 'video').mkdir()
        self.path = root / 'crm.db'
        self.mutex, self.local = threading.RLock(), threading.local()
        self.staff = {123}
        self.http_fail = False
        self.http_entered, self.http_release = threading.Event(), threading.Event()
        self.http_release.set()
        self.http_observations = 0
        self.neighbor = b'<article data-ua-card="UA-0003"><a href="UA-0003.html">other</a></article>'
        self.before = b'<main data-count="2"><article data-ua-card="UA-0002"><a href="UA-0002.html">target</a></article>' + self.neighbor + b'</main>'
        self.after = b'<main data-count="1">' + self.neighbor + b'</main>'
        (root / 'site/index.html').write_bytes(self.before)
        (root / 'video/UA-0002.html').write_bytes(b'<html>target</html>')
        (root / 'video/photo.jpg').write_bytes(b'original-media')
        with contextlib.closing(self.connect()) as conn:
            conn.execute('CREATE TABLE cars (id INTEGER PRIMARY KEY,auto_number TEXT UNIQUE,vin TEXT,published INTEGER,price_uah INTEGER,price_georgia INTEGER,photos TEXT)')
            conn.executemany('INSERT INTO cars VALUES (?,?,?,?,?,?,?)', [
                (8, 'UA-0002', 'WDD2452331J581014', 1, 12000, 10000, 'photo.jpg'),
                (9, 'UA-0003', 'OTHER', 1, 22000, 20000, 'other.jpg')])
            conn.commit()
            self.schema_sha = application_schema_sha256(conn)
            with self.fence(), ImmediateTransaction(conn, self.require_fence) as tx:
                install_additive_schema(tx, approved_application_schema_sha256=self.schema_sha)
                tx.commit()

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=1)
        conn.execute('PRAGMA foreign_keys=ON')
        return conn

    @contextlib.contextmanager
    def fence(self):
        with self.mutex:
            self.local.depth = getattr(self.local, 'depth', 0) + 1
            try:
                yield
            finally:
                self.local.depth -= 1

    def require_fence(self):
        if not getattr(self.local, 'depth', 0):
            raise RuntimeError('fixture fence not held')

    def authorize(self, actor):
        return actor in self.staff

    def get_staff(self, actor):
        return {'id': actor, 'role': 'owner'} if actor in self.staff else None

    def resolve_plan(self, row):
        return dict(mode='PUBLIC_OR_RESIDUAL', car_code=row['auto_number'],
                    direct=['video/UA-0002.html'], lists=['site/index.html'],
                    sitemaps=[], media=['video/photo.jpg'], local_only=[], routes={
                        'https://fixture.invalid/': 'site/index.html',
                        'https://fixture.invalid/video/UA-0002.html': 'video/UA-0002.html'})

    def transform_lists(self, code, before):
        return {name: retire_html(data, code).replace(b'data-count="2"', b'data-count="1"')
                for name, data in before.items()}

    def verify_local(self, plan, current):
        return current == {'site/index.html': self.after}

    def observe_http(self, plan):
        self.http_observations += 1
        self.http_entered.set()
        if not self.http_release.wait(timeout=3):
            raise RuntimeError('HTTP fixture timeout')
        if self.http_fail:
            raise RuntimeError('HTTP probe unavailable')
        return {url: {'url': url, 'redirected': False, 'observed_at': time.time(),
                      'status': 200 if (self.public_root / name).exists() else 404,
                      'body_sha256': hashlib.sha256((self.public_root / name).read_bytes()).hexdigest()
                      if (self.public_root / name).exists() else None}
                for url, name in plan['routes'].items()}

    def scalar(self, sql):
        with contextlib.closing(self.connect()) as conn:
            return conn.execute(sql).fetchone()[0]


class Message:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class Application:
    def __init__(self):
        self.bot_data, self.tasks, self.notifications, self.jobs = {}, [], [], []
        self.bot = types.SimpleNamespace(send_message=self.send)
        self.job_queue = types.SimpleNamespace(run_repeating=self.add_job)

    def create_task(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.append(task)
        return task

    def add_job(self, callback, **kwargs):
        self.jobs.append((callback, kwargs))

    async def send(self, **kwargs):
        self.notifications.append(kwargs)

    async def drain(self):
        while self.tasks:
            tasks, self.tasks = self.tasks, []
            await asyncio.gather(*tasks)


async def ack(query):
    query.acked = True


class ActualHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.binding = FixtureBinding(Path(self.temp.name))
        self.coordinator = Coordinator(self.binding, schema_sha256=self.binding.schema_sha)
        self.backend = CoordinatorBackend(self.coordinator)
        self.log = logging.getLogger('delete-adapter-test')
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        self.app = Application()
        self.adapter = register_adapter(self.app, backend=self.backend,
            get_staff=self.binding.get_staff, ack=ack, logger=self.log)
        self.context = types.SimpleNamespace(application=self.app, user_data={'car_last': 8})
        # Execute the exact replacement handlers that the builder injects.
        self.handlers = {'Update': object, 'ContextTypes': types.SimpleNamespace(DEFAULT_TYPE=object),
                         'ApplicationHandlerStop': Stop, '_v168_ack': ack}
        exec(compile((ROOT / 'replacement_handlers.py.txt').read_text(), 'patched-cars-handlers', 'exec'), self.handlers)

    async def asyncTearDown(self):
        self.binding.http_release.set()
        await self.app.drain()
        self.temp.cleanup()

    async def invoke(self, name, data, actor=123, drain=True):
        query = types.SimpleNamespace(data=data, from_user=types.SimpleNamespace(id=actor),
                                      message=Message(), acked=False)
        with self.assertRaises(Stop):
            await self.handlers[name](types.SimpleNamespace(callback_query=query), self.context)
        self.assertTrue(query.acked)
        if drain:
            await self.app.drain()
        return query

    async def token(self):
        query = await self.invoke('delete_ask', 'car_del:8')
        return query.message.replies[-1][1]['reply_markup'].inline_keyboard[0][0].callback_data

    async def test_confirmation_displays_bound_code_id_vin_version(self):
        query = await self.invoke('delete_ask', 'car_del:8')
        message, kwargs = query.message.replies[-1]
        for expected in ('UA-0002', 'ID: 8', '1014', 'Версия:'):
            self.assertIn(expected, message)
        self.assertNotIn('WDD2452331J581014', message)
        button = kwargs['reply_markup'].inline_keyboard[0][0].callback_data
        self.assertLessEqual(len(button.encode()), 64)
        self.assertEqual(42, len(button))

    async def test_unauthorized_actor_cannot_create_or_admit(self):
        query = await self.invoke('delete_ask', 'car_del:8', actor=999)
        self.assertIn('не разрешён', query.message.replies[0][0])
        token = await self.token()
        await self.invoke('delete_ok', token, actor=999)
        self.assertEqual(0, self.binding.scalar('SELECT count(*) FROM ua_delete_intents'))

    async def test_numeric_legacy_confirmation_never_deletes(self):
        query = await self.invoke('delete_ok', 'car_delok:8')
        self.assertIn('устарело', query.message.replies[0][0])
        self.assertEqual(2, self.binding.scalar('SELECT count(*) FROM cars'))

    async def test_real_completion_preserves_neighbor_and_media(self):
        query = await self.invoke('delete_ok', await self.token())
        self.assertIn('✅ Завершил', query.message.replies[-1][0])
        self.assertEqual(0, self.binding.scalar('SELECT count(*) FROM cars WHERE id=8'))
        self.assertEqual(22000, self.binding.scalar('SELECT price_uah FROM cars WHERE id=9'))
        self.assertEqual(self.binding.after, (self.binding.public_root / 'site/index.html').read_bytes())
        self.assertEqual(b'original-media', (self.binding.public_root / 'video/photo.jpg').read_bytes())
        self.assertFalse((self.binding.public_root / 'video/UA-0002.html').exists())
        self.assertNotIn('car_last', self.context.user_data)
        self.assertEqual(2, self.binding.http_observations)

    async def test_double_click_has_one_durable_operation(self):
        token = await self.token()
        one = await self.invoke('delete_ok', token, drain=False)
        two = await self.invoke('delete_ok', token, drain=False)
        await self.app.drain()
        self.assertIn('уже выполняется', two.message.replies[0][0])
        self.assertEqual(1, self.binding.scalar('SELECT count(*) FROM ua_delete_intents'))
        self.assertIn('✅ Завершил', one.message.replies[-1][0])

    async def test_price_change_invalidates_old_confirmation(self):
        token = await self.token()
        with contextlib.closing(self.binding.connect()) as conn:
            conn.execute('UPDATE cars SET price_uah=12500 WHERE id=8')
            conn.commit()
        query = await self.invoke('delete_ok', token)
        self.assertFalse(any('✅' in text for text, _ in query.message.replies))
        self.assertEqual(12500, self.binding.scalar('SELECT price_uah FROM cars WHERE id=8'))
        self.assertEqual(0, self.binding.scalar('SELECT count(*) FROM ua_delete_intents'))

    async def test_completed_repeat_reports_prior_receipt_without_republishing(self):
        token = await self.token()
        await self.invoke('delete_ok', token)
        updated_site = self.binding.after + b'<!-- subsequent operator change -->'
        (self.binding.public_root / 'site/index.html').write_bytes(updated_site)
        query = await self.invoke('delete_ok', token)
        self.assertIn('уже было завершено', query.message.replies[-1][0])
        self.assertEqual(updated_site, (self.binding.public_root / 'site/index.html').read_bytes())
        self.assertEqual(2, self.binding.http_observations)
        self.assertEqual(1, self.binding.scalar('SELECT count(*) FROM ua_delete_intents'))

    async def test_failed_http_never_reports_success_and_pauses_job(self):
        self.binding.http_fail = True
        query = await self.invoke('delete_ok', await self.token())
        self.assertFalse(any('✅' in text for text, _ in query.message.replies))
        self.assertEqual(1, self.binding.scalar('SELECT count(*) FROM cars WHERE id=8'))
        self.assertEqual('REQUESTED', self.binding.scalar('SELECT state FROM ua_delete_intents'))
        observations = self.binding.http_observations
        await self.adapter.resume_job(self.context)
        self.assertEqual(observations, self.binding.http_observations)

    async def test_restart_resumes_same_durable_job(self):
        self.binding.http_fail = True
        await self.invoke('delete_ok', await self.token())
        old = self.binding.scalar('SELECT operation_id FROM ua_delete_intents')
        self.binding.http_fail = False
        restarted = TelegramDeletionAdapter(CoordinatorBackend(Coordinator(
            self.binding, schema_sha256=self.binding.schema_sha)),
            get_staff=self.binding.get_staff, ack=ack, logger=self.log)
        await restarted.resume_job(self.context)
        self.assertEqual(old, self.binding.scalar('SELECT operation_id FROM ua_delete_intents'))
        self.assertEqual('COMPLETE', self.binding.scalar('SELECT state FROM ua_delete_intents'))
        self.assertIn('✅ Завершил', self.app.notifications[-1]['text'])
        self.assertEqual(123, self.app.notifications[-1]['chat_id'])

    async def test_slow_http_does_not_block_callback_or_event_loop(self):
        token = await self.token()
        self.binding.http_release.clear()
        query = await asyncio.wait_for(self.invoke('delete_ok', token, drain=False), timeout=.2)
        for _ in range(100):
            if self.binding.http_entered.is_set():
                break
            await asyncio.sleep(.01)
        self.assertTrue(self.binding.http_entered.is_set())
        unrelated = await asyncio.wait_for(self.invoke('delete_ok', 'car_delok:8', drain=False), timeout=.2)
        self.assertIn('устарело', unrelated.message.replies[0][0])
        self.assertFalse(any('✅' in text for text, _ in query.message.replies))
        self.binding.http_release.set()
        await self.app.drain()

    async def test_missing_backend_fails_closed_with_crm_preserved(self):
        del self.app.bot_data[APP_KEY]
        query = await self.invoke('delete_ok', 'car_delok:8')
        self.assertIn('не подключён', query.message.replies[0][0])
        self.assertEqual(2, self.binding.scalar('SELECT count(*) FROM cars'))

    async def test_restart_job_registered_once_and_required(self):
        same = register_adapter(self.app, backend=self.backend, get_staff=self.binding.get_staff,
                                ack=ack, logger=self.log)
        self.assertIs(same, self.adapter)
        self.assertEqual(1, len(self.app.jobs))
        self.assertEqual(1, self.app.jobs[0][1]['first'])
        other = Application()
        other.job_queue = None
        with self.assertRaisesRegex(RuntimeError, 'JOB_QUEUE_REQUIRED'):
            register_adapter(other, backend=self.backend, get_staff=self.binding.get_staff,
                             ack=ack, logger=self.log)
        self.assertNotIn(APP_KEY, other.bot_data)

    async def test_startup_receipt_does_not_claim_live_telegram_acceptance(self):
        import json
        path = self.binding.journal_root / 'startup.json'
        receipt = json.loads(path.read_text())
        self.assertEqual('REGISTERED', receipt['phase'])
        self.assertFalse(receipt['live_telegram_action_verified'])
        self.assertFalse(receipt['application_running'])
        self.app.running = True
        self.app.updater = types.SimpleNamespace(running=True)
        await self.adapter.resume_job(self.context)
        receipt = json.loads(path.read_text())
        self.assertEqual('RUNNING', receipt['phase'])
        self.assertTrue(receipt['application_running'])
        self.assertTrue(receipt['updater_running'])
        self.assertFalse(receipt['live_telegram_action_verified'])

    async def test_invalid_startup_config_does_not_activate_adapter(self):
        (self.binding.journal_root / 'runtime.json').write_text('{"changed":true}')
        other = Application()
        with self.assertRaisesRegex(RuntimeError, 'STARTUP_CONFIG_CHANGED'):
            register_adapter(other, backend=self.backend, get_staff=self.binding.get_staff,
                             ack=ack, logger=self.log)
        self.assertNotIn(APP_KEY, other.bot_data)


class BuilderTests(unittest.TestCase):
    def test_changed_source_is_rejected_before_mutation(self):
        with self.assertRaisesRegex(ValueError, 'Source hash mismatch'):
            build_candidate(b'not the reviewed source')


if __name__ == '__main__':
    unittest.main()
