import importlib.util
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from build_gallery_patch import SOURCES
from test_public_fields import CARD,PAGE

class PublicationGate(unittest.TestCase):
    def test_checks_final_html_before_returning_to_writer(self):
        wrapper=SOURCES['publikaciya.py'][2]
        with tempfile.TemporaryDirectory() as d:
            path=pathlib.Path(d)/'publisher.py'
            path.write_text('def _master(code):\n    return RESULT\n'+wrapper)
            spec=importlib.util.spec_from_file_location('gate_fixture',path)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            media=types.SimpleNamespace(verify_photo_structure=lambda *args:None)
            gallery=types.SimpleNamespace(gallery_paths=lambda card:[])
            with patch.dict(sys.modules,{'public_media':media,'crm_gallery':gallery}):
                module.RESULT=(PAGE.replace('167 007','167 008'),None,CARD)
                with self.assertRaisesRegex(RuntimeError,'mileage'):
                    module._master('UA-0022')
                module.RESULT=(PAGE,None,CARD)
                self.assertEqual(module._master('UA-0022'),module.RESULT)
                module.RESULT=(None,None,None)
                with self.assertRaisesRegex(RuntimeError,'missing'):
                    module._master('UA-0022')

if __name__=='__main__':unittest.main()
