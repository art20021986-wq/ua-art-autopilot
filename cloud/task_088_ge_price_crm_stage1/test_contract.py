from __future__ import annotations
import pathlib, unittest
HERE=pathlib.Path(__file__).resolve().parent
class TestPackage(unittest.TestCase):
    def test_files(self):
        for name in ("controller.py","remote_installer.py"):
            p=HERE/name
            self.assertTrue(p.is_file())
            compile(p.read_text(encoding="utf-8"),str(p),"exec")
    def test_scope(self):
        s=(HERE/"remote_installer.py").read_text(encoding="utf-8")
        self.assertIn('/home/Carix',s)
        self.assertIn('cars_ui.py',s)
        self.assertIn('crm.db',s)
        self.assertIn('"site_write":False',s)
        self.assertNotIn('uaart.com.ua',s)
if __name__=="__main__": unittest.main()
