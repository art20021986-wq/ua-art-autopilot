#!/usr/bin/env python3
"""Release-specific checks: exact inputs, new module guard and catalog repair."""
import hashlib
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

import candidate_builder
import deployment_remote as remote

PUBLISHER = b'''from pathlib import Path
def obnovit_katalog():
    Path('video/katalog.html').write_text(
        '<html><head><title>UA ART</title></head><body><div data-ua-card="UA-0001"></div></body></html>')
    return True, 'ok'
'''
FOLDERS = b'''import re
class CatalogSnapshotError(ValueError): pass
def parse_catalog(source):
    return frozenset(re.findall(r'data-ua-card="(UA-[0-9]{4})"', source))
def partition_by_catalog(cards, ids):
    if set(ids) - {c['auto_number'] for c in cards}:
        raise CatalogSnapshotError('Catalog contains car numbers absent from the CRM snapshot')
    return {}
'''


class ReleaseTests(unittest.TestCase):
    def test_builder_refuses_unexpected_inputs(self):
        with self.assertRaises(ValueError):
            candidate_builder.build({'cars_ui.py': b'other'}, {})

    def test_builder_pins_installed_cars_ui(self):
        self.assertEqual(candidate_builder.SOURCE_SHA256['cars_ui.py'],
                         '19adbff34be18402897ca4b54889c9361bcdd261f329218e147b72f8031f9ad6')

    def test_repair_rebuilds_and_proves_catalog(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'video').mkdir()
            (root/'publikaciya.py').write_bytes(PUBLISHER)
            (root/'ua_crm_catalog_folders.py').write_bytes(FOLDERS)
            with sqlite3.connect(root/'crm.db') as con:
                con.execute('CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT)')
                con.execute("INSERT INTO cars VALUES (7, 'UA-0001')")
            cwd = os.getcwd()
            try:
                with patch.object(remote, 'ROOT', root):
                    value = remote.repair_catalog()
            finally:
                os.chdir(cwd)
                sys.path.remove(str(root))
                sys.modules.pop('publikaciya', None)
        self.assertEqual(value['catalog_numbers'], {'video/katalog.html': ['UA-0001']})
        self.assertTrue(value['catalog_matches_crm'])

    def test_repair_stops_when_publisher_rejects(self):
        class Rejecting:
            @staticmethod
            def obnovit_katalog():
                return False, 'mismatch'
        with patch.dict(sys.modules, {'publikaciya': Rejecting}), \
             patch.object(os, 'chdir'):
            with self.assertRaises(remote.DeploymentError):
                remote.repair_catalog()


if __name__ == '__main__':
    unittest.main()
