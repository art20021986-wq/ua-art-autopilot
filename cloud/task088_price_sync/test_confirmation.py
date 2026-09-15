"""Public, source-free anomaly-confirmation persistence contract."""
import hashlib
import sqlite3
import unittest

import uaart_price_sync_confirmation as C


class ConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.execute('BEGIN IMMEDIATE');C.install(self.db);self.db.commit()
        self.key=hashlib.sha256(b'public-fixture-operation').hexdigest()
        self.payload=dict(actor_id=700,chat_id=700,car_id=1,field='price_georgia',value=245000)

    def propose(self):
        self.db.execute('BEGIN IMMEDIATE')
        proposal=C.propose(self.db,event_key=self.key,payload=self.payload,now_ms=1000)
        self.db.commit()
        return proposal

    def test_bounds_only_request_confirmation_and_never_change_amount(self):
        for value in (245,245000):self.assertTrue(C.suspicious(value))
        for value in (None,1000,18000,200000):self.assertFalse(C.suspicious(value))
        self.assertEqual(self.propose()['payload']['value'],245000)

    def test_same_event_dedupes_but_distinct_event_creates_new_confirmation(self):
        first=self.propose();self.assertEqual(self.propose(),first)
        self.key=hashlib.sha256(b'second-conscious-operation').hexdigest()
        self.assertNotEqual(self.propose()['token'],first['token'])

    def test_conflicting_technical_repeat_fails_closed(self):
        self.propose();self.payload['value']=245
        with self.assertRaisesRegex(C.ConfirmationError,'IDENTITY_CONFLICT'):self.propose()

    def test_cancel_is_final_and_cannot_be_replayed_as_confirmation(self):
        proposal=self.propose();self.db.execute('BEGIN IMMEDIATE')
        C.decide(self.db,proposal['token'],state='CANCELLED',now_ms=1100);self.db.commit()
        self.db.execute('BEGIN IMMEDIATE')
        with self.assertRaisesRegex(C.ConfirmationError,'ALREADY_DECIDED'):
            C.decide(self.db,proposal['token'],state='CONFIRMED',now_ms=1200)
        self.db.rollback()
        self.assertEqual(C.get(self.db,proposal['token'])['state'],'CANCELLED')

    def test_actor_chat_and_card_are_bound_to_confirmation(self):
        proposal=self.propose()
        for kwargs in (dict(actor_id=701,chat_id=700,car_id=1),
                       dict(actor_id=700,chat_id=701,car_id=1),dict(actor_id=700,chat_id=700,car_id=2)):
            with self.assertRaisesRegex(C.ConfirmationError,'IDENTITY_MISMATCH'):C.check_identity(proposal,**kwargs)
        self.assertEqual(C.check_identity(proposal,actor_id=700,chat_id=700,car_id=1),self.payload)

    def test_payload_and_history_are_permanent(self):
        proposal=self.propose()
        for sql in (f'DELETE FROM {C.TABLE}',f"UPDATE {C.TABLE} SET payload_json='{{}}'"):
            with self.assertRaises(sqlite3.IntegrityError):self.db.execute(sql)
            self.db.rollback()
        self.assertEqual(C.get(self.db,proposal['token']),proposal)

    def test_explicit_schema_installation_requires_transaction(self):
        with self.assertRaisesRegex(C.ConfirmationError,'TRANSACTION_REQUIRED'):C.install(self.db)
