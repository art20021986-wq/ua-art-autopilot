import ast
import asyncio
import concurrent.futures
import hashlib
import json
import logging
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

import build_candidate as builder
import ua_publish_requests as requests

HERE = Path(__file__).resolve().parent


def revision(value='v1', status='ferry'):
    return {'code': 'UA-0021', 'sha256': value, 'delivery_status': status}


class StoreFixture:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def enqueue(self, rev='v1'):
        return requests.enqueue(self.root, 21, revision(rev), 1, 10)


class StoreTests(StoreFixture, unittest.TestCase):
    def test_concurrent_double_taps_have_one_pending_token(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            tokens = list(pool.map(lambda _: self.enqueue(), range(8)))
        self.assertEqual(len(set(tokens)), 1)
        self.assertEqual(len(requests.pending(self.root)), 1)

    def test_request_survives_new_connection_and_process_state(self):
        token = self.enqueue()
        self.assertEqual(requests.pending(Path(str(self.root)))['21']['token'], token)

    def test_newer_revision_is_not_completed_by_old_worker(self):
        old = self.enqueue()
        new = self.enqueue('v2')
        self.assertFalse(requests.finish(self.root, old, 'verified', 'v1'))
        self.assertEqual(requests.pending(self.root)['21']['token'], new)

    def test_completion_receipt_survives_restart_until_delivered(self):
        token = self.enqueue()
        self.assertTrue(requests.finish(self.root, token, 'verified', 'v1'))
        self.assertEqual(requests.receipts(self.root)[0]['verified_revision'], 'v1')
        requests.delivered(self.root, token)
        self.assertEqual(requests.receipts(self.root), [])

    def test_cancelled_request_cannot_be_promoted_to_success(self):
        token = self.enqueue()
        requests.finish(self.root, token, 'cancelled')
        self.assertFalse(requests.finish(self.root, token, 'verified', 'v1'))

    def test_queue_directory_is_private(self):
        self.enqueue()
        self.assertEqual((self.root/'.crm_publish_requests').stat().st_mode & 0o777, 0o700)


class WorkerTests(StoreFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        raw = (HERE/'worker_source.txt').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), builder.SOURCE_SHA256['ua_crm_public_sync.py'])
        self.worker = types.ModuleType('candidate_worker')
        exec(builder.patch_worker(raw.decode()), self.worker.__dict__)
        self.worker.ROOT = self.root
        self.worker.STATE = self.root/'state.json'
        self.worker.LOCK = self.root/'worker.lock'
        self.rows = {'21': revision()}
        self.worker.snapshot = lambda: dict(self.rows)
        self.worker.LOG = Mock()
        self.verify = Mock()
        self.modules = patch.dict(sys.modules, {'ua_public_freshness': types.SimpleNamespace(
            verify_public=self.verify), 'ua_stage_catalog_sync': types.SimpleNamespace(reconcile=Mock())})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.worker.save_state({'version': 1, 'revisions': dict(self.rows), 'retry': {}})

    def test_explicit_request_overrides_unverified_baseline(self):
        self.enqueue()
        publisher = Mock(return_value=(True, 'ok'))
        self.assertEqual(self.worker.reconcile_once(publisher), 'published')
        publisher.assert_called_once_with('UA-0021')
        self.verify.assert_called_once_with('UA-0021')
        self.assertEqual(requests.receipts(self.root)[0]['state'], 'verified')

    def test_failure_remains_pending_and_retries_after_restart(self):
        self.enqueue()
        self.worker.reconcile_once(lambda _: (False, 'temporary error'), clock=lambda: 100)
        self.assertEqual(requests.receipts(self.root), [])
        publisher = Mock(return_value=(True, 'ok'))
        self.worker.reconcile_once(publisher, clock=lambda: 101)
        publisher.assert_not_called()
        self.worker.reconcile_once(publisher, clock=lambda: 116)
        self.assertEqual(requests.receipts(self.root)[0]['state'], 'verified')

    def test_public_url_failure_does_not_acknowledge_success(self):
        self.enqueue()
        self.verify.side_effect = RuntimeError('stale page')
        self.worker.reconcile_once(lambda _: (True, 'ok'))
        self.assertIn('21', requests.pending(self.root))
        self.assertEqual(requests.receipts(self.root), [])

    def test_concurrent_edit_requires_new_publication(self):
        self.enqueue()
        def publish(_):
            self.rows['21'] = revision('v2')
            return True, 'ok'
        self.assertEqual(self.worker.reconcile_once(publish), 'changed_during_publish')
        self.assertEqual(requests.receipts(self.root), [])
        self.worker.reconcile_once(lambda _: (True, 'ok'))
        self.assertEqual(requests.receipts(self.root)[0]['verified_revision'], 'v2')

    def test_deleted_card_cancels_pending_intent(self):
        self.enqueue()
        self.rows.clear()
        publisher = Mock()
        self.worker.reconcile_once(publisher)
        publisher.assert_not_called()
        self.assertEqual(requests.receipts(self.root)[0]['state'], 'cancelled')

    def test_archived_card_cannot_be_republished_by_pending_intent(self):
        self.enqueue()
        self.rows['21'] = revision('archive-revision', 'hidden')
        publisher = Mock()
        self.worker.reconcile_once(publisher)
        publisher.assert_not_called()
        self.assertEqual(requests.receipts(self.root)[0]['state'], 'cancelled')

    def test_double_tap_does_not_reset_retry_backoff(self):
        token = self.enqueue()
        self.worker.reconcile_once(lambda _: (False, 'busy'), clock=lambda: 100)
        self.assertEqual(self.enqueue(), token)
        publisher = Mock()
        self.worker.reconcile_once(publisher, clock=lambda: 101)
        publisher.assert_not_called()

    def test_new_intent_during_build_is_not_lost(self):
        old = self.enqueue()
        def publish(_):
            requests.enqueue(self.root, 21, revision('new-intent'), 1, 11)
            return True, 'ok'
        self.worker.reconcile_once(publish)
        self.assertIsNone(requests.current(self.root, old))
        self.assertEqual(len(requests.pending(self.root)), 1)


class Stop(Exception):
    pass


class UITests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        fixture = json.loads((HERE/'ui_source_functions.json').read_text())
        source = '\n\n'.join(code for functions in fixture['functions'].values() for code in functions)
        source += '\ndef register(app):\n    app.add_handler(CallbackQueryHandler(toggle_publish, pattern=r"^car_pub:"), group=g)\n'
        self.source = builder.patch_ui(source)
        self.ns = {'ApplicationHandlerStop': Stop, 'log': logging.getLogger('oneclick-test')}
        exec('from __future__ import annotations\n'+self.source, self.ns)
        self.card = {'id':21, 'published':1, 'status':'sea_loaded', 'auto_number':'UA-0021'}
        self.progress = types.SimpleNamespace(chat_id=100, message_id=200, edit_text=AsyncMock())
        self.query = types.SimpleNamespace(data='car_ad:21', from_user=types.SimpleNamespace(id=1),
            message=types.SimpleNamespace(reply_text=AsyncMock(return_value=self.progress)))
        self.ns.update(_ua099_require_staff=AsyncMock(return_value=(self.query, {'admin':True})),
            _ua099_card=lambda _:dict(self.card), _ua099_back=lambda cid:('back',cid),
            S=types.SimpleNamespace(missing_required=lambda card:[]), db=types.SimpleNamespace(update_card_field=Mock()))
        self.tasks = []
        def create_task(coro, **kwargs):
            self.tasks.append(coro)
        self.app = types.SimpleNamespace(create_task=create_task, job_queue=object())
        self.context = types.SimpleNamespace(application=self.app, bot=types.SimpleNamespace(edit_message_text=AsyncMock()))
        self.policy = patch.dict(sys.modules, {'ua_delivery_status':types.SimpleNamespace(stage_number=lambda s: 2 if s=='sea_loaded' else 0)})
        self.policy.start()
        self.addCleanup(self.policy.stop)
        self.addCleanup(lambda:[task.close() for task in self.tasks])

    async def test_published_flag_does_not_open_ad_copy_or_claim_success(self):
        with self.assertRaises(Stop):
            await self.ns['ad_screen'](object(),self.context)
        self.assertEqual(len(self.tasks),1)
        text=self.query.message.reply_text.call_args.args[0]
        self.assertNotIn('опубликовано',text)
        self.assertNotIn('Готовое объявление',text)
        self.ns['db'].update_card_field.assert_not_called()

    async def test_draft_also_schedules_same_one_click_path(self):
        self.card['published']=0
        with self.assertRaises(Stop):
            await self.ns['ad_screen'](object(),self.context)
        self.assertEqual(len(self.tasks),1)

    async def test_missing_data_does_not_schedule_publication(self):
        self.ns['S'].missing_required=lambda card:['VIN']
        with self.assertRaises(Stop):
            await self.ns['ad_screen'](object(),self.context)
        self.assertEqual(self.tasks,[])
        self.assertIn('VIN',self.query.message.reply_text.call_args.args[0])

    async def test_removed_preview_cannot_build_or_publish(self):
        self.query.data='car_preview:21'
        with self.assertRaises(Stop):
            await self.ns['preview'](object(),self.context)
        self.assertEqual(self.tasks,[])
        self.ns['db'].update_card_field.assert_not_called()

    async def test_old_toggle_is_inert(self):
        self.query.data='car_pub:21'
        with self.assertRaises(Stop):
            await self.ns['_ua_oneclick_legacy_publish'](object(),self.context)
        self.ns['db'].update_card_field.assert_not_called()

    def test_requested_buttons_removed_from_all_new_views(self):
        self.assertNotIn('Уже в каталоге',self.source)
        self.assertNotIn('Как видит покупатель',self.source)
        self.assertIn('car_hide:',self.source)
        self.assertIn('car_sold:',self.source)
        self.assertIn('car_del:',self.source)

    def test_prepare_never_toggles_existing_publication_off(self):
        sync=types.SimpleNamespace(ROOT='/test',snapshot=lambda:{'21':revision()},start=Mock(),notify=Mock())
        store=types.SimpleNamespace(enqueue=Mock(return_value='token'))
        with patch.dict(sys.modules,{'ua_crm_public_sync':sync,'ua_publish_requests':store}):
            self.ns['_ua_oneclick_prepare'](21,1,dict(self.card),100,200)
        self.ns['db'].update_card_field.assert_not_called()
        sync.notify.assert_called_once()

    def test_prepare_draft_sets_only_publication_intent(self):
        self.card['published']=0
        sync=types.SimpleNamespace(ROOT='/test',snapshot=lambda:{'21':revision()},start=Mock(),notify=Mock())
        with patch.dict(sys.modules,{'ua_crm_public_sync':sync,'ua_publish_requests':types.SimpleNamespace(enqueue=Mock())}):
            self.ns['_ua_oneclick_prepare'](21,1,dict(self.card),100,200)
        self.ns['db'].update_card_field.assert_called_once_with('cars',21,'published',1,1)

    def test_changed_status_cannot_be_overwritten_by_late_submission(self):
        expected=dict(self.card)
        self.card['status']='archive'
        sync=types.SimpleNamespace(ROOT='/test',snapshot=Mock(),start=Mock(),notify=Mock())
        with patch.dict(sys.modules,{'ua_crm_public_sync':sync}):
            with self.assertRaisesRegex(ValueError,'CARD_CHANGED'):
                self.ns['_ua_oneclick_prepare'](21,1,expected,100,200)
        self.ns['db'].update_card_field.assert_not_called()

    def test_second_draft_tap_joins_already_enabled_publication(self):
        expected={**self.card,'published':0}
        sync=types.SimpleNamespace(ROOT='/test',snapshot=lambda:{'21':revision()},start=Mock(),notify=Mock())
        with patch.dict(sys.modules,{'ua_crm_public_sync':sync,'ua_publish_requests':types.SimpleNamespace(enqueue=Mock())}):
            self.ns['_ua_oneclick_prepare'](21,1,expected,100,200)
        self.ns['db'].update_card_field.assert_not_called()

    async def _receipt_case(self, *, fresh=True, telegram_error=False):
        receipt={'identity':'21','code':'UA-0021','token':'token','state':'verified',
                 'verified_revision':'v1','chat_id':100,'message_id':200}
        store=types.SimpleNamespace(receipts=Mock(return_value=[receipt]),current=Mock(return_value=receipt),
                                    enqueue=Mock(),delivered=Mock())
        sync=types.SimpleNamespace(ROOT='/test',snapshot=lambda:{'21':revision('v2')},notify=Mock(),start=Mock())
        self.ns['_ua_oneclick_verified']=Mock(return_value=fresh)
        self.ns['_ua_emergency_schedule_spec']=Mock()
        if telegram_error:
            self.context.bot.edit_message_text.side_effect=RuntimeError('temporary Telegram outage')
        with patch.dict(sys.modules,{'ua_crm_public_sync':sync,'ua_publish_requests':store}):
            await self.ns['_ua_oneclick_receipts'](self.context)
        return store,sync

    async def test_receipt_delivered_only_after_public_freshness_check(self):
        store,sync=await self._receipt_case()
        self.ns['_ua_oneclick_verified'].assert_called_once()
        self.context.bot.edit_message_text.assert_awaited_once()
        store.delivered.assert_called_once_with('/test','token')
        self.assertIn('✅',self.context.bot.edit_message_text.call_args.kwargs['text'])

    async def test_stale_receipt_requeues_current_data_without_success_message(self):
        store,sync=await self._receipt_case(fresh=False)
        self.context.bot.edit_message_text.assert_not_awaited()
        store.enqueue.assert_called_once()
        sync.notify.assert_called_once()
        store.delivered.assert_not_called()

    async def test_telegram_outage_keeps_receipt_for_retry(self):
        with self.assertLogs('oneclick-test',level='ERROR'):
            store,sync=await self._receipt_case(telegram_error=True)
        store.delivered.assert_not_called()
        store.enqueue.assert_not_called()

    async def test_staff_rejection_schedules_nothing(self):
        self.ns['_ua099_require_staff']=AsyncMock(side_effect=Stop)
        with self.assertRaises(Stop):
            await self.ns['ad_screen'](object(),self.context)
        self.assertEqual(self.tasks,[])


if __name__=='__main__':
    unittest.main()
