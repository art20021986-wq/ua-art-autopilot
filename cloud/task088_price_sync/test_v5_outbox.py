"""The v5 intention/audit schema is independent of existing cars and audit."""
import hashlib
import sqlite3
import unittest
import outbox as O


class V5OutboxTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.addCleanup(self.db.close)
        self.db.executescript("CREATE TABLE cars(id INTEGER PRIMARY KEY,auto_number TEXT,vin TEXT,published INTEGER,price_uah INTEGER,price_georgia INTEGER); INSERT INTO cars VALUES(1,'UA-0001','VIN1',1,20000,8000)")
        self.db.execute('BEGIN IMMEDIATE');O.install_v5(self.db);self.db.commit()

    def submit(self,key='edit1',**extra):
        self.db.execute('BEGIN IMMEDIATE')
        values=dict(event_key=hashlib.sha256(key.encode()).hexdigest(),car_id=1,field='price_georgia',value=18900,
                    actor_id=700,chat_id=700,now_ms=1000,provenance={'source':'SYNTHETIC_TEST'})
        values.update(extra)
        try:result=O.submit(self.db,**values);self.db.commit();return result
        except Exception:self.db.rollback();raise

    def test_intentions_do_not_mutate_cars_and_duplicate_is_noop(self):
        before=self.db.execute('SELECT * FROM cars').fetchall()
        first=self.submit();again=self.submit();second=self.submit('edit2')
        self.assertEqual(first['event_key'],again['event_key']);self.assertEqual(second['sequence'],2)
        self.assertEqual(self.db.execute('SELECT * FROM cars').fetchall(),before)
        self.assertEqual(self.db.execute(f'SELECT state FROM {O.V5_TABLE}').fetchall(),[('QUEUED',),('QUEUED',)])

    def test_same_identity_different_value_is_conflict(self):
        self.submit()
        with self.assertRaisesRegex(O.OutboxError,'PAYLOAD_CONFLICT'):self.submit(value=18000)

    def test_intent_and_audit_history_are_permanent_and_linked(self):
        event=self.submit()
        for sql in (f"UPDATE {O.V5_TABLE} SET value='1.00'",f'DELETE FROM {O.V5_TABLE}',
                    f"UPDATE {O.V5_AUDIT} SET payload_json='{{}}'",f'DELETE FROM {O.V5_AUDIT}'):
            with self.subTest(sql=sql),self.assertRaises(sqlite3.IntegrityError):self.db.execute(sql)
            self.db.rollback()
        self.assertEqual(self.db.execute(f'SELECT event_key FROM {O.V5_AUDIT}').fetchone()[0],event['event_key'])

    def test_later_intent_cannot_claim_before_previous_completes(self):
        first=self.submit();second=self.submit('edit2')
        self.db.execute('BEGIN IMMEDIATE')
        with self.assertRaisesRegex(O.OutboxError,'EARLIER_CAR_OPERATION'):
            O.claim_operation(self.db,event_key=second['event_key'],nonce='a'*64,now_ms=1001)
        self.db.rollback()
        self.db.execute('BEGIN IMMEDIATE')
        claim=O.claim_operation(self.db,event_key=first['event_key'],nonce='b'*64,now_ms=1001);self.db.commit()
        self.db.execute('BEGIN IMMEDIATE')
        resumed=O.claim_operation(self.db,event_key=first['event_key'],nonce='c'*64,now_ms=1002);self.db.commit()
        self.assertEqual(claim['claim_nonce'],resumed['claim_nonce'])

    def test_schema_install_rollback_preserves_existing_schema_and_prices(self):
        conn=sqlite3.connect(':memory:');self.addCleanup(conn.close)
        conn.execute('CREATE TABLE cars(id INTEGER PRIMARY KEY,price_uah INTEGER)');conn.execute('INSERT INTO cars VALUES(1,24500)');conn.commit()
        before=conn.execute('SELECT * FROM sqlite_master').fetchall()
        conn.execute('BEGIN IMMEDIATE');O.install_v5(conn);conn.rollback()
        self.assertEqual(conn.execute('SELECT * FROM sqlite_master').fetchall(),before)
        self.assertEqual(conn.execute('SELECT * FROM cars').fetchall(),[(1,24500)])


if __name__=='__main__':unittest.main()
