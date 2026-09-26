import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from crm_revision import snapshot

class RevisionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.db=sqlite3.connect(self.root/'crm.db')
  self.db.executescript('CREATE TABLE cars (id INTEGER,auto_number TEXT,published INTEGER,price_uah INTEGER);CREATE TABLE media(id INTEGER,car_id INTEGER,status TEXT);CREATE TABLE additional_specification(id INTEGER,car_uid TEXT,field_value TEXT);INSERT INTO cars VALUES(1,"UA-0001",1,12000),(2,"UA-0002",1,15000),(3,"UA-0003",0,10000);INSERT INTO media VALUES(1,1,"pending");INSERT INTO additional_specification VALUES(1,"UA-0001","old");')
  self.spec=sqlite3.connect(self.root/'vin_specs_task111_v3.db')
  self.spec.executescript('CREATE TABLE additional_specification(id INTEGER,car_uid TEXT,field_value TEXT);CREATE TABLE additional_specification_meta(car_uid TEXT,field_key TEXT,is_visible INTEGER);CREATE TABLE spec84_fact_bindings(car_uid TEXT,vin TEXT,generation INTEGER);INSERT INTO additional_specification VALUES(1,"UA-0001","old");INSERT INTO additional_specification_meta VALUES("UA-0001","engine",1);')
  self.spec.commit()
  self.db.commit();(self.root/'.video_sinhron.json').write_text('{}')
 def tearDown(self):self.spec.close();self.db.close();self.tmp.cleanup()
 def check_mutation(self,sql):
  before=snapshot(self.root);self.db.execute(sql);self.db.commit();after=snapshot(self.root)
  self.assertNotEqual(before['1'],after['1']);self.assertEqual(before['2'],after['2'])
 def test_media_only_edit(self):self.check_mutation('UPDATE media SET status="ready" WHERE id=1')
 def test_spec_only_edit(self):
  before=snapshot(self.root);self.spec.execute('UPDATE additional_specification SET field_value="new" WHERE id=1');self.spec.commit();after=snapshot(self.root)
  self.assertNotEqual(before['1'],after['1']);self.assertEqual(before['2'],after['2'])
 def test_visibility_only_edit(self):
  before=snapshot(self.root);self.spec.execute('UPDATE additional_specification_meta SET is_visible=0');self.spec.commit();after=snapshot(self.root)
  self.assertNotEqual(before['1'],after['1']);self.assertEqual(before['2'],after['2'])
 def test_car_edit(self):self.check_mutation('UPDATE cars SET price_uah=13000 WHERE id=1')
 def test_ledger_only_edit(self):
  before=snapshot(self.root);(self.root/'.video_sinhron.json').write_text(json.dumps({'foto:UA-0001':{'001.jpg':'a'}}));after=snapshot(self.root)
  self.assertNotEqual(before['1'],after['1']);self.assertEqual(before['2'],after['2'])
 def test_stable_and_unpublished_excluded(self):
  self.assertEqual(snapshot(self.root),snapshot(self.root));self.assertNotIn('3',snapshot(self.root))
 def test_duplicate_code_rejected(self):
  self.db.execute('UPDATE cars SET auto_number="UA-0001" WHERE id=2');self.db.commit()
  with self.assertRaisesRegex(RuntimeError,'duplicate'):snapshot(self.root)

if __name__=='__main__':unittest.main()
