"""Public v5 full-generation fence; real pinned guard source is checked privately."""
import contextlib
import sqlite3
import sys
import unittest
from unittest.mock import patch

from patch_guard import HELPER
import test_v5_runtime as V5
O = V5.O


class PublicGuardContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture=V5.V5RuntimeTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.modules=patch.dict(sys.modules,{'uaart_price_sync_outbox':O})
        self.modules.start();self.addCleanup(self.modules.stop)
        self.ns={'contextlib':contextlib,'sqlite3':sqlite3,'DB':self.fixture.db,'PublishError':RuntimeError}
        exec(compile(HELPER,'<public-v5-generation-fence>','exec'),self.ns)

    def test_empty_queue_preserves_manual_first_publication(self):
        with self.ns['_task088_price_quiescence']():pass

    def test_accepted_pending_operation_blocks_generation_before_price_commit(self):
        self.fixture.submit()
        self.assertEqual(self.fixture.row()['price_georgia'],8000)
        with self.assertRaisesRegex(RuntimeError,'V5_UNVERIFIED_PRICE_INTENTS'):
            with self.ns['_task088_price_quiescence']():self.fail('must not enter publication')

    def test_actual_runtime_complete_receipt_allows_generation(self):
        event=self.fixture.submit();self.fixture.worker.tick()
        self.assertEqual(self.fixture.event(event['event_key'])['state'],'COMPLETED')
        with self.ns['_task088_price_quiescence']():pass

    def test_next_pending_operation_invalidates_old_completion_for_generation(self):
        self.fixture.submit();self.fixture.worker.tick();self.fixture.submit(value=18500)
        with self.assertRaisesRegex(RuntimeError,'V5_UNVERIFIED_PRICE_INTENTS'):
            with self.ns['_task088_price_quiescence']():self.fail('must not enter publication')

    def test_untracked_second_market_price_drift_blocks_full_generation(self):
        self.fixture.submit();self.fixture.worker.tick()
        with sqlite3.connect(self.fixture.db) as conn:conn.execute('UPDATE cars SET price_uah=24500 WHERE id=1')
        with self.assertRaisesRegex(RuntimeError,'V5_UNTRACKED_CRM_PRICE_CHANGE'):
            with self.ns['_task088_price_quiescence']():self.fail('must not enter publication')

    def test_fence_prevents_concurrent_admission_until_publication_exits(self):
        with self.ns['_task088_price_quiescence']():
            with sqlite3.connect(self.fixture.db,timeout=0) as conn:
                with self.assertRaises(sqlite3.OperationalError):conn.execute('BEGIN IMMEDIATE')
