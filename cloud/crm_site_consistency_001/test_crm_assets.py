from pathlib import Path
import tempfile
import unittest
from crm_assets import save_immutable

class FakeImage:
 def __init__(self,data):self.data=data
 def save(self,stream,**kwargs):stream.write(self.data)

class AssetsTests(unittest.TestCase):
 def test_new_content_new_url_old_untouched(self):
  with tempfile.TemporaryDirectory() as d:
   old=Path(d)/'UA-0019.jpg';old.write_bytes(b'old cover')
   first=save_immutable(FakeImage(b'first'),d,'UA-0019','jpg')
   second=save_immutable(FakeImage(b'second'),d,'UA-0019','jpg')
   self.assertNotEqual(first,second)
   self.assertEqual(Path(first).read_bytes(),b'first')
   self.assertEqual(old.read_bytes(),b'old cover')
 def test_retry_reuses_identical_asset(self):
  with tempfile.TemporaryDirectory() as d:
   image=FakeImage(b'same')
   a=save_immutable(image,d,'UA-0019','jpg');b=save_immutable(image,d,'UA-0019','jpg')
   self.assertEqual(a,b);self.assertEqual(len(list(Path(d).iterdir())),1)
 def test_tamper_fails_closed(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(save_immutable(FakeImage(b'first'),d,'UA-0019','jpg'));p.write_bytes(b'changed')
   with self.assertRaisesRegex(RuntimeError,'mismatch'):save_immutable(FakeImage(b'first'),d,'UA-0019','jpg')
 def test_invalid_identity_rejected(self):
  with self.assertRaises(ValueError):save_immutable(FakeImage(b'x'),'/tmp','../x','jpg')
 def test_no_partial_asset_on_encoding_failure(self):
  class Broken:
   def save(self,*args,**kwargs):raise ValueError('encoding failure')
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(ValueError):save_immutable(Broken(),d,'UA-0019','jpg')
   self.assertEqual(list(Path(d).iterdir()),[])

if __name__=='__main__':unittest.main()
