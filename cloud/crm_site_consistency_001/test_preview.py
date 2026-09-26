import sys
import unittest
import subprocess
import tempfile
from pathlib import Path
from preview_controller import package
from preview_transport import API,E

class PreviewTests(unittest.TestCase):
 def test_no_runtime_upload_to_production_paths(self):
  api=API('fixture-token')
  for path in ['/home/Carix/crm.db','/home/Carix/stranica.py','/home/Carix/video/UA-0019.html']:
   with self.subTest(path=path),self.assertRaisesRegex(E,'PATH_SCOPE'):api.furl(path)
 def test_invalid_remote_arguments_stop_before_validation(self):
  for args in [['job.py','install','123'],['job.py','preview','not-a-run']]:
   with self.subTest(args=args),tempfile.TemporaryDirectory() as folder:
    path=Path(folder)/'preview.py';path.write_bytes(package())
    result=subprocess.run([sys.executable,'-I',str(path),*args[1:]],capture_output=True,timeout=10)
    self.assertEqual(result.returncode,2)

if __name__=='__main__':unittest.main()
