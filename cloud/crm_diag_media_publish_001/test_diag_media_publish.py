#!/usr/bin/env python3
"""Builder and behaviour tests on the exact installed ua_crm_public_sync.py (from probe R5)."""
import hashlib
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
EXPORT = HERE.parents[1] / 'cloud/crm_video_probe_20261012_r5/sanitized_sources.txt'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


builder = load('build_public_sync', HERE / 'build_public_sync.py')


def installed_source():
    text = EXPORT.read_text(encoding='utf-8')
    start = text.index('# ===== ua_crm_public_sync.py =====\n') + len('# ===== ua_crm_public_sync.py =====\n')
    body = text[start:text.index('# ===== ua_publish_requests.py')].rstrip('\n') + '\n'
    return body.encode('utf-8')


class SyncFixture:
    """Real original and patched modules over a temporary CRM and diag folder."""

    def __init__(self, temp):
        self.root = Path(temp)
        (self.root / 'video/diag').mkdir(parents=True)
        with sqlite3.connect(self.root / 'crm.db') as con:
            con.execute('CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT, published INT, status TEXT)')
            con.executemany('INSERT INTO cars VALUES (?,?,?,?)',
                            [(30, 'UA-0020', 1, 'ua_arrived'), (5, 'UA-0005', 1, 'kr_bought')])
        (self.root / 'ua_delivery_status.py').write_text('def public_status(value):\n    return value or "hidden"\n')
        files = load('ua_diag_files', HERE / 'ua_diag_files.py')
        files.DIAG = self.root / 'video/diag'
        sys.path.insert(0, str(self.root))
        original = installed_source()
        (self.root / 'original_sync.py').write_bytes(original)
        (self.root / 'patched_sync.py').write_bytes(builder.build(original))
        self.original = load('original_sync', self.root / 'original_sync.py')
        self.patched = load('patched_sync', self.root / 'patched_sync.py')
        for module in (self.original, self.patched):
            module.ROOT = self.root

    def close(self):
        sys.path.remove(str(self.root))
        for name in ('ua_delivery_status', 'ua_diag_files', 'original_sync', 'patched_sync'):
            sys.modules.pop(name, None)

    def put(self, name, size=2000):
        path = self.root / 'video/diag/UA-0020' / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b'x' * size)


class DiagMediaPublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.sync = SyncFixture(self.temp.name)

    def tearDown(self):
        self.sync.close()
        self.temp.cleanup()

    def test_export_is_the_installed_source(self):
        self.assertEqual(hashlib.sha256(installed_source()).hexdigest(), builder.EXPECTED_SHA256)

    def test_cards_without_diag_files_keep_their_revision(self):
        self.sync.put('notes.txt')
        self.assertEqual(self.sync.patched.snapshot(), self.sync.original.snapshot())

    def test_downloaded_video_changes_only_that_card(self):
        before = self.sync.patched.snapshot()
        self.sync.put('01.mp4')
        after = self.sync.patched.snapshot()
        self.assertNotEqual(after['30']['sha256'], before['30']['sha256'])
        self.assertEqual(after['5'], before['5'])

    def test_posters_partial_downloads_and_reencoding_do_not_republish(self):
        self.sync.put('01.mp4')
        base = self.sync.patched.snapshot()
        for name in ('01.poster.jpg', '01.mp4.poster.jpg', '01.mp4.iskhodnoe', '02.mp4.vremenno'):
            self.sync.put(name)
        self.sync.put('01.mp4', size=9000)
        self.assertEqual(self.sync.patched.snapshot(), base)

    def test_small_photos_ignored_like_the_page(self):
        base = self.sync.patched.snapshot()
        self.sync.put('01.jpg', size=500)
        self.assertEqual(self.sync.patched.snapshot(), base)
        self.sync.put('01.jpg', size=5000)
        self.assertNotEqual(self.sync.patched.snapshot(), base)

    def test_builder_refuses_other_source(self):
        with self.assertRaises(builder.BuildError):
            builder.build(b'def snapshot():\n    pass\n')


if __name__ == '__main__':
    unittest.main()
