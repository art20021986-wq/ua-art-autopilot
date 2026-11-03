#!/usr/bin/env python3
"""The guard edit on catalog_design_guard.py as FINANCE-PROBE-20261103-R6 read it."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

import candidate_builder
import edit_catalog_guard

HERE = Path(__file__).resolve().parent
LIVE = (HERE / 'fixtures' / 'catalog_design_guard.txt').read_bytes()
TAG = ('<!--UA-GTAG-V1--><script async src="https://www.googletagmanager.com/gtag/js?id=G-X"></script>'
       '<script>gtag("config","G-X")</script><!--/UA-GTAG-V1-->')
SHELL = '<html><head>%s<meta name="x" content="y"><title>Каталог</title></head><body><p>Усі · 22</p></body></html>'


def load(text, name):
    path = Path(tempfile.mkdtemp()) / (name + '.py')
    path.write_bytes(text)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        after = candidate_builder.build({edit_catalog_guard.NAME: LIVE}, {})[edit_catalog_guard.NAME]
        cls.before, cls.after = load(LIVE, 'guard_before'), load(after, 'guard_after')

    def test_google_tag_block_no_longer_breaks_the_shell(self):
        golden, live = SHELL % '', SHELL % TAG
        self.assertNotEqual(self.before.shell_fingerprint(live), self.before.shell_fingerprint(golden))
        self.assertEqual(self.after.shell_fingerprint(live), self.after.shell_fingerprint(golden))

    def test_any_other_shell_change_still_refused(self):
        golden = SHELL % ''
        for changed in (SHELL % '<script src="https://evil.example/x.js"></script>',
                        (SHELL % TAG).replace('<title>Каталог', '<title>Інше'),
                        (SHELL % TAG).replace('<!--/UA-GTAG-V1-->', '')):
            self.assertNotEqual(self.after.shell_fingerprint(changed), self.after.shell_fingerprint(golden))

    def test_counts_still_normalized_and_edit_refused_twice(self):
        self.assertEqual(self.after.shell_fingerprint(SHELL % TAG), self.after.shell_fingerprint((SHELL % '').replace('22', '5')))
        once = candidate_builder.build({edit_catalog_guard.NAME: LIVE}, {})[edit_catalog_guard.NAME]
        with self.assertRaisesRegex(ValueError, 'CATALOG_GUARD_FRAGMENT'):
            edit_catalog_guard.build(edit_catalog_guard.NAME, once)


if __name__ == '__main__':
    unittest.main()
