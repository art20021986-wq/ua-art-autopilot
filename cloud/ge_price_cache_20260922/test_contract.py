import base64,pathlib,sys,tempfile,unittest
from unittest.mock import patch
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import remote_installer as deploy

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
class CacheScope(unittest.TestCase):
 def test_exact_version_replacement_only(self):
  self.assertEqual(len(deploy.PAYLOAD),22)
  for name,item in deploy.PAYLOAD.items():
   self.assertTrue(name.startswith('/home/Carix/video/'));self.assertTrue(name.endswith('.html'))
   before=b'<head><script src="'+item['old'].encode()+b'"></script></head><p>11 700 $</p>'
   package={name:dict(item,before=deploy.sha(before),after=deploy.sha(before.replace(item['old'].encode(),item['new'].encode())))}
   with patch.object(deploy,'PAYLOAD',package),patch.object(deploy,'read',return_value=before):
    candidate=deploy.candidates()[name][1]
   self.assertEqual(candidate.replace(item['new'].encode(),item['old'].encode()),before)
 def test_wrong_tag_is_rejected(self):
  name,item=next(iter(deploy.PAYLOAD.items()));before=b'<html>no tag</html>'
  with patch.object(deploy,'PAYLOAD',{name:dict(item,before=deploy.sha(before))}),patch.object(deploy,'read',return_value=before):
   with self.assertRaisesRegex(RuntimeError,'CACHE_SLOT'):deploy.candidates()
if __name__=='__main__':unittest.main()
