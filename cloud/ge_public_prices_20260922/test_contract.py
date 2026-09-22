import base64, contextlib, hashlib, importlib.util, json, pathlib, sqlite3, sys, tempfile, unittest
from unittest.mock import patch
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import uaart_public_prices_v1 as runtime
import remote_installer as deploy

class PublicPrices(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.db=pathlib.Path(self.temp.name)/'crm.db'
  with sqlite3.connect(self.db) as c:
   c.execute('CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT,status TEXT,price_uah,price_georgia,price_total,published INTEGER,private_note TEXT)')
   c.executemany('INSERT INTO cars VALUES(?,?,?,?,?,?,?,?)',[(1,'UA-0010','ge_waiting',11700,8750,None,1,'SECRET'),(2,'UA-0007','ua_arrived',9300,8000,None,1,'SECRET'),(3,'UA-0009','ge_waiting',11500,None,None,1,'SECRET'),(4,'UA-9999','ge_waiting',1,2,None,0,'PRIVATE')])
 def test_only_public_prices_without_writes(self):
  before=self.db.read_bytes();value=runtime.snapshot(self.db);text=json.dumps(value)
  self.assertNotIn('SECRET',text);self.assertNotIn('PRIVATE',text);self.assertNotIn('UA-9999',text)
  self.assertEqual(before,self.db.read_bytes());self.assertIn('8 750 $',value['cars']['UA-0010']['full'])
  self.assertNotIn('georgia',value['cars']['UA-0007']['full']);self.assertIn('Цена уточняется',value['cars']['UA-0009']['full'])
  self.assertNotIn('<span',text)
 def test_independent_live_updates(self):
  with sqlite3.connect(self.db) as c: c.execute('UPDATE cars SET price_georgia=8765 WHERE id=1')
  text=runtime.snapshot(self.db)['cars']['UA-0010']['full'];self.assertIn('8 765 $',text);self.assertIn('11 700 $',text)
  with sqlite3.connect(self.db) as c: c.execute('UPDATE cars SET price_uah=11800 WHERE id=1')
  text=runtime.snapshot(self.db)['cars']['UA-0010']['full'];self.assertIn('8 765 $',text);self.assertIn('11 800 $',text)
 def test_route_delegation_and_no_private_errors(self):
  app=runtime.wrap(lambda e,s:[b'original']);self.assertEqual(app({'PATH_INFO':'/existing'},lambda *a:None),[b'original'])
  status=[]
  with patch.object(runtime,'snapshot',side_effect=sqlite3.OperationalError('PRIVATE_PATH')):
   body=app({'PATH_INFO':runtime.ROUTE},lambda s,h:status.append(s))
  self.assertEqual(status,['503 Service Unavailable']);self.assertNotIn(b'PRIVATE',b''.join(body))
  status=[];self.assertEqual(app({'PATH_INFO':runtime.ROUTE,'REQUEST_METHOD':'POST'},lambda s,h:status.append(s)),[b'']);self.assertEqual(status,['405 Method Not Allowed'])
 def test_invalid_amount_never_replaces_current_prices(self):
  with sqlite3.connect(self.db) as c:c.execute("UPDATE cars SET price_georgia='garbage' WHERE id=1")
  with self.assertRaises(ValueError):runtime.snapshot(self.db)
 def test_package_bound_to_source(self):
  for name,item in deploy.PAYLOAD.items():
   source=base64.b64decode(item['source']);local=HERE/pathlib.Path(name).name
   if not item['append']:self.assertEqual(source,local.read_bytes());self.assertEqual(deploy.sha(source),item['after'])
   elif name.endswith('.js'):self.assertEqual(source,(HERE/'prices.js').read_bytes())
   else:self.assertEqual(source,(HERE/'wsgi_append.txt').read_bytes())

class Installation(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=pathlib.Path(self.temp.name)
  self.target=root/'existing';self.target.write_bytes(b'original');self.new=root/'new'
  payload={str(self.target):{'before':deploy.sha(b'original'),'after':deploy.sha(b'original+prices'),'append':True,'source':base64.b64encode(b'+prices').decode()},str(self.new):{'before':None,'after':deploy.sha(b'new'),'append':False,'source':base64.b64encode(b'new').decode()}}
  for name,value in [('PAYLOAD',payload),('BACKUP_ROOT',root/'backups')]:p=patch.object(deploy,name,value);p.start();self.addCleanup(p.stop)
  p=patch.object(deploy,'validate_runtime',return_value={'published_count':3});p.start();self.addCleanup(p.stop)
 def test_backup_install_rollback_exact(self):
  b=deploy.backup('test')['backup_manifest_sha256'];self.assertEqual(self.target.read_bytes(),b'original');self.assertFalse(self.new.exists())
  deploy.install('test',b);self.assertEqual(self.target.read_bytes(),b'original+prices');self.assertTrue(self.new.exists())
  deploy.rollback('test',b);self.assertEqual(self.target.read_bytes(),b'original');self.assertFalse(self.new.exists())
 def test_drift_blocks_install(self):
  b=deploy.backup('test')['backup_manifest_sha256'];self.target.write_bytes(b'foreign')
  with self.assertRaisesRegex(RuntimeError,'PREIMAGE_DRIFT'):deploy.install('test',b)
  self.assertFalse(self.new.exists());self.assertEqual(self.target.read_bytes(),b'foreign')
 def test_rollback_never_overwrites_foreign_changes(self):
  b=deploy.backup('test')['backup_manifest_sha256'];deploy.install('test',b);self.target.write_bytes(b'foreign')
  with self.assertRaisesRegex(RuntimeError,'ROLLBACK_FOREIGN_CHANGE'):deploy.rollback('test',b)
  self.assertEqual(self.target.read_bytes(),b'foreign');self.assertTrue(self.new.exists())
 def test_corrupted_backup_blocks_install(self):
  b=deploy.backup('test')['backup_manifest_sha256'];(deploy.BACKUP_ROOT/'test'/'0.before').write_bytes(b'bad')
  with self.assertRaisesRegex(RuntimeError,'BACKUP_CORRUPT'):deploy.install('test',b)
  self.assertEqual(self.target.read_bytes(),b'original');self.assertFalse(self.new.exists())
if __name__=='__main__':unittest.main()
