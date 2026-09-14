"""Public CRM admission helpers; actual private-source handlers have a separate Gate."""
import ast
import json
import sqlite3
import sys
import types
import unittest
from unittest.mock import patch

import outbox as O
import uaart_price_sync_confirmation as C
from patch_cars_ui import HELPERS


class PublicCrmIntentTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript('''CREATE TABLE staff(user_id INTEGER PRIMARY KEY,active INTEGER,role TEXT);
            INSERT INTO staff VALUES(700,1,'manager'),(701,1,'admin'),(702,1,'owner'),(703,0,'manager');
            CREATE TABLE cars(id INTEGER PRIMARY KEY,auto_number TEXT,vin TEXT,published INTEGER,
                price_uah INTEGER,price_georgia INTEGER,updated_at TEXT,title TEXT);
            INSERT INTO cars VALUES(1,'UA-0001','TESTVIN1',1,20000,8000,'old','Protected');
            CREATE TABLE audit(actor_id INTEGER,field TEXT);''')
        self.db.execute('BEGIN IMMEDIATE');O.install(self.db);C.install(self.db);self.db.commit()
        self.modules=patch.dict(sys.modules,{'uaart_price_sync_outbox':O,'uaart_price_sync_confirmation':C})
        self.modules.start();self.addCleanup(self.modules.stop)
        nodes=[n for n in ast.parse(HELPERS).body if isinstance(n,ast.FunctionDef)]
        self.ns={'db':types.SimpleNamespace(ROLE_OWNER='owner',ROLE_ADMIN='admin',ROLE_MANAGER='manager'),
                 '_v168_empty':lambda value:value in (None,'',0),
                 'InlineKeyboardButton':lambda text,**kw:dict(text=text,**kw)}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<public-crm-admission>','exec'),self.ns)

    def admit(self,value=18000,field='price_georgia',message=50,actor=700,expected=None,causal=False):
        identity=(actor,message,900+message)
        provenance=dict(source='TELEGRAM_UPDATE',chat_id=actor,chat_type='private',actor_id=actor,
                        message_id=message,update_id=900+message,bot_id=12345)
        self.db.execute('BEGIN IMMEDIATE')
        before=dict(self.db.execute('SELECT * FROM cars WHERE id=1').fetchone())
        try:
            result=self.ns['_task088_sync_prepare'](self.db,before,field,value,actor,identity,
                provenance,expected,False,None,None,causal)
            self.db.commit();return result
        except Exception:self.db.rollback();raise

    def events(self):
        return [O.get_operation(self.db,r[0]) for r in self.db.execute(f'SELECT event_key FROM {O.V5_TABLE} ORDER BY sequence')]

    def test_operator_intent_never_mutates_price_before_worker(self):
        kind,event=self.admit();self.assertEqual(kind,'queued')
        self.assertEqual(event['value'],'18000.00')
        self.assertEqual(self.db.execute('SELECT price_uah,price_georgia FROM cars').fetchone()[:],(20000,8000))
        self.assertEqual(self.db.execute('SELECT count(*) FROM audit').fetchone()[0],0)
        self.ns['_task088_sync_readback'](self.db,event)

    def test_every_conscious_input_including_same_amount_gets_own_fifo_entry(self):
        for message,value in enumerate((18000,18500,18300,18900,18900),50):self.admit(value,message=message)
        self.assertEqual([e['value'] for e in self.events()],['18000.00','18500.00','18300.00','18900.00','18900.00'])
        self.assertEqual([e['state'] for e in self.events()],['QUEUED']*5)

    def test_technical_replay_is_idempotent_and_conflict_is_rejected(self):
        self.admit();self.admit();self.assertEqual(len(self.events()),1)
        with self.assertRaises(O.OutboxError):self.admit(18500)
        self.assertEqual(len(self.events()),1)

    def test_anomaly_creates_durable_exact_amount_with_confirmation_buttons(self):
        kind,proposal=self.admit(245000);self.assertEqual(kind,'proposal')
        reply=self.ns['_task088_sync_proposal_reply'](proposal,'Цена Грузии')
        self.assertIn('245 000 $',reply)
        rows=self.ns['_task088_sync_rows'](reply,[])
        self.assertTrue(rows[0][0]['callback_data'].startswith('price5:yes:'))
        self.assertEqual(self.events(),[])

    def test_all_existing_operator_roles_allowed_and_inactive_staff_rejected(self):
        for actor in (700,701,702):self.admit(actor=actor)
        with self.assertRaisesRegex(RuntimeError,'PERMISSION_DENIED'):self.admit(actor=703)
        self.assertEqual(len(self.events()),3)

    def test_causal_voice_corrections_follow_pending_same_market_predecessors(self):
        self.admit(18000,expected=(8000,),causal=True)
        self.admit(21000,field='price_uah',message=51)
        self.admit(18500,message=52,expected=(8000,),causal=True)
        self.assertEqual([json.loads(e['expected_old_json']) if e['expected_old_json'] else None for e in self.events()],
                         [[8000],None,[18000]])

    def test_external_drift_at_admission_is_rejected(self):
        kind,result=self.admit(expected=(7999,),causal=True)
        self.assertEqual((kind,result),('reply',(False,'conflict')))
        self.assertEqual(self.events(),[])

    def test_ukraine_georgia_inputs_use_distinct_fields(self):
        self.admit();self.admit(24500,field='price_uah')
        self.assertEqual([e['field'] for e in self.events()],['price_georgia','price_uah'])
