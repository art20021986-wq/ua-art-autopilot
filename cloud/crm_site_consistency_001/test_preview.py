import sys
import unittest
from unittest.mock import patch
from preview_controller import package
from preview_transport import API,E

class PreviewTests(unittest.TestCase):
 def test_no_runtime_upload_to_production_paths(self):
  api=API('fixture-token')
  for path in ['/home/Carix/crm.db','/home/Carix/stranica.py','/home/Carix/video/UA-0019.html']:
   with self.subTest(path=path),self.assertRaisesRegex(E,'PATH_SCOPE'):api.furl(path)
 def test_invalid_remote_arguments_stop_before_validation(self):
  for args in [['job.py','install','123'],['job.py','preview','not-a-run']]:
   with self.subTest(args=args),patch.object(sys,'argv',args),self.assertRaises(SystemExit):exec(compile(package(),'remote','exec'),{})

if __name__=='__main__':unittest.main()
