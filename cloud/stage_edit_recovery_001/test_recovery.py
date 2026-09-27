"""Regressions using hash-checked functions extracted from the installed sources."""

import asyncio
from contextlib import nullcontext
import datetime
import hashlib
import importlib.util
import json
import logging
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from build_candidate import (POLICY_SHA256, SYNC_HANDLER, SYNC_JOB,
                             patch_catalog_builder, patch_stage_handler, patch_ui)

HERE = Path(__file__).resolve().parent
FIXTURES = json.loads((HERE/'source_functions.json').read_text())
policy_path = HERE.parent/'delivery_status_001/delivery_status.py'
spec = importlib.util.spec_from_file_location('ua_delivery_status', policy_path)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def fragment(file, function):
    item = FIXTURES[file]['functions'][function]
    if hashlib.sha256(item['source'].encode()).hexdigest() != item['sha256']:
        raise ValueError('FIXTURE_CHANGED')
    return item['source']


def row(identity, status, published=1):
    return dict(id=identity, auto_number='UA-%04d' % identity,
                status=status, published=published,
                vin='TEST-VIN-%04d' % identity, price_uah=21200,
                photos='["original-photo"]')


class PublishError(Exception):
    pass


class PublicationRegressionTests(unittest.TestCase):
    def setUp(self):
        self.rows = [row(20, 'archive'), row(21, 'sea_loaded'), row(22, 'ua_arrived')]
        self.gallery_calls = []
        self.installs = []
        self.restores = []
        self.stranica = SimpleNamespace(
            mashiny=lambda: list(self.rows), nomer=lambda r: r['auto_number'],
            kadry_mashiny=lambda r: self.gallery_calls.append(r['auto_number']) or ['original'],
            sobrat_katalog=lambda rows, photos: '|'.join(r['auto_number'] for r in rows))
        self.modules = patch.dict(sys.modules, {
            'ua_delivery_status': policy, 'stranica': self.stranica,
            'master_card': SimpleNamespace(obrabotat_obshuyu=lambda html: html)})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def publisher(self, *, fixed):
        original = fragment('publikaciya.py', '_ua9_sobrat_katalog')
        namespace = {}
        exec(patch_catalog_builder(original) if fixed else original, namespace)
        self.modules_dict = patch.dict(sys.modules, {'publikaciya': SimpleNamespace(
            _ua9_sobrat_katalog=namespace['_ua9_sobrat_katalog'])})
        self.modules_dict.start()
        self.addCleanup(self.modules_dict.stop)
        ns = {'_task088_price_quiescence': nullcontext, '_code': str,
              'CONTRACT_ID': 'test-actual-transaction',
              'PublishError': PublishError, '_stage_diags': lambda codes: {},
              '_call_base': lambda fn, code, proba: fn(code),
              '_row_map': lambda: ({r['auto_number']: r for r in self.rows
                                   if r['published'] == 1 and policy.stage_number(r['status'])}, 'same'),
              '_protected_pages': lambda _: {'unrelated': 'unchanged'},
              '_validate_catalog': lambda *args: None,
              '_install_catalog': lambda html, code: self.installs.append((html, code)),
              '_verify_bundle': lambda codes: {'verified': codes},
              '_append_log': lambda text: None,
              'Snapshot': lambda codes: SimpleNamespace(root='temporary-backup',
                  restore=lambda: self.restores.append('restored') or {'status': 'PASS'})}
        exec('from __future__ import annotations\n' + fragment('publish_transaction_guard.py', '_build_catalog')
             + '\n' + fragment('publish_transaction_guard.py', '_publish_locked'), ns)
        return ns['_publish_locked']

    def test_actual_installed_transaction_reproduces_row_set_failure(self):
        ok, message, evidence = self.publisher(fixed=False)(lambda _: (True, 'ok'), ['UA-0021'])
        self.assertFalse(ok)
        self.assertIn('CATALOG_ROW_SET_MISMATCH', message)
        self.assertEqual(self.restores, ['restored'])
        self.assertEqual(self.installs, [])

    def test_reactivated_car_passes_same_strict_transaction_after_fix(self):
        before = json.dumps(self.rows, sort_keys=True)
        ok, _, evidence = self.publisher(fixed=True)(lambda _: (True, 'ok'), ['UA-0021'])
        self.assertTrue(ok)
        self.assertEqual(self.installs, [('UA-0021|UA-0022', 'UA-0021')])
        self.assertNotIn('UA-0020', self.gallery_calls)
        self.assertEqual(json.dumps(self.rows, sort_keys=True), before)
        self.assertEqual(self.restores, [])

    def test_all_sixteen_transitions_and_new_id(self):
        publish = self.publisher(fixed=True)
        for start in ('kr_bought', 'sea_loaded', 'ge_waiting', 'ua_arrived'):
            for target in ('kr_bought', 'sea_loaded', 'ge_waiting', 'ua_arrived'):
                with self.subTest(start=start, target=target):
                    self.rows[1]['status'] = start
                    self.assertTrue(publish(lambda _: (True, 'ok'), ['UA-0021'])[0])
                    self.rows[1]['status'] = target
                    self.assertTrue(publish(lambda _: (True, 'ok'), ['UA-0021'])[0])
        self.rows.append(row(9999, 'kr_bought'))
        self.assertTrue(publish(lambda _: (True, 'ok'), ['UA-9999'])[0])
        self.assertIn('UA-9999', self.installs[-1][0])

    def test_unpublished_and_unknown_excluded_from_one_shared_list(self):
        self.rows += [row(30, 'sea_loaded', 0), row(31, 'unexpected')]
        ok, _, _ = self.publisher(fixed=True)(lambda _: (True, 'ok'), ['UA-0021'])
        self.assertTrue(ok)
        self.assertEqual(self.gallery_calls, ['UA-0021', 'UA-0022'])

    def test_empty_catalog_and_reactivation(self):
        self.rows = [row(21, 'archive')]
        namespace = {}
        exec(patch_catalog_builder(fragment('publikaciya.py', '_ua9_sobrat_katalog')), namespace)
        self.assertEqual(namespace['_ua9_sobrat_katalog'](), ('', []))
        self.rows[0]['status'] = 'sea_loaded'
        html, rows = namespace['_ua9_sobrat_katalog']()
        self.assertEqual(html, 'UA-0021')
        self.assertEqual(len(rows), 1)


class HandlerStop(Exception):
    pass


class CRMRouteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.card = row(21, 'archive')
        self.writes = []
        self.query = SimpleNamespace(data='car_setstage:21:ferry', from_user=SimpleNamespace(id=1),
                                     message=SimpleNamespace(reply_text=AsyncMock()))
        self.worker = SimpleNamespace(start=Mock(), notify=Mock())
        self.modules = patch.dict(sys.modules, {'ua_delivery_status': policy,
                                               'ua_crm_public_sync': self.worker})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        ns = {'ApplicationHandlerStop': HandlerStop, '_v168_ack': AsyncMock(),
              'drop_wait': Mock(), 'card_of': lambda _: self.card, 'set_field': self.set_field,
              '_date': datetime.date, 'eta_of': lambda _: (None, None),
              'log': logging.getLogger(__name__),
              'InlineKeyboardButton': lambda text, **kw: (text, kw),
              'InlineKeyboardMarkup': lambda rows: rows,
              'S': SimpleNamespace(status_label=lambda code: policy.public_label(code) or 'Скрыт из каталога')}
        exec('from __future__ import annotations\n' + SYNC_HANDLER + '\n' + SYNC_JOB + '\n' +
             patch_stage_handler(fragment('cars_ui.py', 'stage_set')), ns)
        self.ns = ns

    def set_field(self, identity, field, value, actor):
        self.writes.append((identity, field, value))
        self.card[field] = value

    async def invoke(self, callback):
        self.query.data = callback
        with self.assertRaises(HandlerStop):
            await self.ns['stage_set'](SimpleNamespace(callback_query=self.query), SimpleNamespace())

    async def test_current_and_old_active_buttons_preserve_other_fields(self):
        for public, stored, _, _ in policy.CHOICES:
            for callback in (public, stored):
                with self.subTest(callback=callback):
                    await self.invoke('car_setstage:21:' + callback)
                    self.assertEqual(self.card['status'], stored)
                    self.assertEqual(self.card['price_uah'], 21200)
                    self.assertEqual(self.card['photos'], '["original-photo"]')
        self.assertEqual(self.worker.notify.call_count, 8)

    async def test_router_intercepts_old_and_current_buttons_before_legacy_handlers(self):
        handlers = []
        legacy = AsyncMock()
        source = '\n'.join(fragment('cars_ui.py', f) for f in (
            'stage_set', '_ua004_sync_current_stage', '_ua004_stage_reconcile_job',
            'stage_router_register'))
        ns = dict(self.ns)
        ns.update({
            '_UA117_BASE_REGISTER': lambda app: app.add_handler(
                (legacy, re.compile(r'^car_setstage:')), group=-4),
            'CallbackQueryHandler': lambda callback, pattern: (callback, re.compile(pattern)),
        })
        exec('from __future__ import annotations\n' + patch_ui(source), ns)
        ns['_ua117_block_removed_stage'] = ns['stage_set']
        ns['register'](SimpleNamespace(
            add_handler=lambda handler, group: handlers.append((group, handler))))
        for requested in ('korea', 'ferry', 'georgia', 'kyiv', 'kr_bought', 'sea_loaded',
                          'ge_waiting', 'ua_arrived', 'ge_to_kyiv', 'archive'):
            self.query.data = 'car_setstage:21:' + requested
            with self.assertRaises(HandlerStop):
                for _, (callback, pattern) in sorted(handlers, key=lambda x: x[0]):
                    if pattern.match(self.query.data):
                        await callback(SimpleNamespace(callback_query=self.query), SimpleNamespace())
            self.assertEqual(self.card['status'], policy.storage_status(requested))
        legacy.assert_not_awaited()

    async def test_unknown_callbacks_keep_existing_hidden_policy(self):
        for value in ('archive', 'sold', 'ge_to_kyiv', 'unexpected'):
            await self.invoke('car_setstage:21:' + value)
            self.assertEqual(self.card['status'], 'hidden')

    async def test_missing_and_malformed_card_never_written(self):
        await self.invoke('car_setstage:bad:ferry')
        self.card = None
        await self.invoke('car_setstage:21:ferry')
        self.assertEqual(self.writes, [])
        self.worker.notify.assert_not_called()

    async def test_draft_stage_saved_without_publishing(self):
        self.card['published'] = 0
        await self.invoke('car_setstage:21:ferry')
        self.assertEqual(self.card['status'], 'sea_loaded')
        self.worker.notify.assert_not_called()
        self.assertIn('не опубликована', self.query.message.reply_text.call_args.args[0])

    async def test_queue_ack_does_not_claim_public_success(self):
        await self.invoke('car_setstage:21:ferry')
        message = self.query.message.reply_text.call_args.args[0]
        self.assertIn('поставлено в очередь', message)
        self.assertNotIn('синхронизированы', message)

    async def test_failed_start_does_not_claim_queue_started(self):
        self.worker.start.side_effect = RuntimeError('worker unavailable')
        with self.assertLogs(level='ERROR'):
            await self.invoke('car_setstage:21:ferry')
        self.assertIn('пока не запущено', self.query.message.reply_text.call_args.args[0])
        self.worker.notify.assert_not_called()

    async def test_periodic_check_never_gives_up_after_three_failures(self):
        self.worker.start.side_effect = [RuntimeError('temporary')]*3 + [None]
        with self.assertLogs(level='ERROR'):
            for _ in range(4):
                await self.ns['_ua004_stage_reconcile_job'](None)
        self.worker.notify.assert_called_once_with()


class DurableWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.publish = Mock(return_value=(True, 'ok'))
        self.verify = Mock()
        self.modules = patch.dict(sys.modules, {'ua_delivery_status': policy,
            'ua_public_freshness': SimpleNamespace(verify_public=self.verify),
            'ua_stage_catalog_sync': SimpleNamespace(reconcile=Mock())})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.ns = {'ROOT': root, 'STATE': root/'state.json', 'LOCK': root/'worker.lock',
                   'LOG': logging.getLogger(__name__)}
        functions = '\n'.join(fragment('ua_crm_public_sync.py', f)
                              for f in ('snapshot', 'save_state', 'reconcile_once'))
        exec('import sqlite3,json,hashlib,os,tempfile,fcntl,time\n' + functions, self.ns)
        self.database = root/'crm.db'
        with sqlite3.connect(self.database) as conn:
            conn.execute('CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT, status TEXT, published INTEGER)')
            conn.execute("INSERT INTO cars VALUES(21,'UA-0021','archive',1)")
        self.initial = self.ns['snapshot']()
        self.ns['save_state']({'version': 1, 'revisions': self.initial, 'retry': {}})
        self.change('sea_loaded')

    def change(self, status):
        with sqlite3.connect(self.database) as conn:
            conn.execute('UPDATE cars SET status=? WHERE id=21', (status,))

    def state(self):
        return json.loads(self.ns['STATE'].read_text())

    def run_once(self):
        return self.ns['reconcile_once'](self.publish, clock=lambda: 100)

    def test_reactivated_revision_acknowledged_only_after_public_verification(self):
        self.assertEqual(self.run_once(), 'published')
        self.publish.assert_called_once_with('UA-0021')
        self.verify.assert_called_once_with('UA-0021')
        self.assertEqual(self.state()['revisions'], self.ns['snapshot']())

    def test_public_failure_retains_old_revision_and_durable_retry(self):
        self.verify.side_effect = RuntimeError('stale public HTML')
        with self.assertLogs(level='ERROR'):
            self.assertEqual(self.run_once(), 'idle')
        self.assertEqual(self.state()['revisions'], self.initial)
        self.assertEqual(self.state()['retry']['21']['count'], 1)
        self.verify.side_effect = None
        self.assertEqual(self.ns['reconcile_once'](self.publish, clock=lambda: 116), 'published')
        self.assertEqual(self.state()['retry'], {})

    def test_durable_retry_survives_more_than_three_failed_attempts(self):
        self.publish.return_value = (False, 'temporary publish failure')
        with self.assertLogs(level='ERROR'):
            for attempt in range(4):
                self.assertEqual(self.ns['reconcile_once'](
                    self.publish, clock=lambda: 100 + 500*attempt), 'idle')
        self.assertEqual(self.state()['retry']['21']['count'], 4)
        self.assertEqual(self.state()['revisions'], self.initial)
        self.publish.return_value = (True, 'ok')
        self.assertEqual(self.ns['reconcile_once'](self.publish, clock=lambda: 2500), 'published')
        self.assertEqual(self.state()['retry'], {})

    def test_future_card_is_discovered_without_resetting_existing_revisions(self):
        self.change('archive')
        with sqlite3.connect(self.database) as conn:
            conn.execute("INSERT INTO cars VALUES(9999,'UA-9999','sea_loaded',1)")
        self.assertEqual(self.run_once(), 'published')
        self.publish.assert_called_once_with('UA-9999')
        self.assertEqual(self.state()['revisions']['21'], self.initial['21'])
        self.assertEqual(self.state()['revisions'], self.ns['snapshot']())

    def test_newer_edit_during_publish_is_not_overwritten_or_acknowledged(self):
        self.publish.side_effect = lambda _: (self.change('ua_arrived') or True, 'ok')
        with self.assertLogs(level='WARNING'):
            self.assertEqual(self.run_once(), 'changed_during_publish')
        self.assertEqual(self.state()['revisions'], self.initial)
        with sqlite3.connect(self.database) as conn:
            self.assertEqual(conn.execute('SELECT status FROM cars WHERE id=21').fetchone()[0], 'ua_arrived')


if __name__ == '__main__':
    unittest.main()
