"""Focused offline CAS, new-file compensation and whole-set rollback checks."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import install84 as installer


class BoundedReplacementTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.backup = self.root / 'backup'
        self.backup.mkdir()
        self.backup_patch = patch.object(installer, 'BACKUP', self.backup)
        self.backup_patch.start()

    def tearDown(self):
        self.backup_patch.stop()
        self.temporary.cleanup()

    def record(self, name, before, after):
        target = self.root / name
        if before is not None:
            target.write_bytes(before)
            target.chmod(0o640)
            meta = target.stat()
        else:
            meta = None
        return dict(target=str(target), before=None if before is None else installer.sha(before),
            after=installer.sha(after), raw=before, new=after, meta=meta)

    def test_existing_round_trip_retains_metadata(self):
        record = self.record('old.py', b'old', b'new')
        installer.replace(record, record['new'], record['before'])
        installer.compensate(record)
        current = Path(record['target']).stat()
        self.assertEqual(Path(record['target']).read_bytes(), b'old')
        self.assertEqual(current.st_mode, record['meta'].st_mode)
        self.assertEqual(current.st_mtime_ns, record['meta'].st_mtime_ns)

    def test_new_file_can_be_compensated_to_absence(self):
        record = self.record('new.py', None, b'new')
        installer.replace(record, record['new'], None)
        self.assertEqual(Path(record['target']).stat().st_nlink, 1)
        installer.compensate(record)
        self.assertFalse(Path(record['target']).exists())

    def test_new_file_creation_does_not_clobber_racing_writer(self):
        record = self.record('new.py', None, b'new')
        original_link = os.link
        def racing_link(source, target, **kwargs):
            Path(target).write_bytes(b'foreign')
            return original_link(source, target, **kwargs)
        with patch.object(installer.os, 'link', side_effect=racing_link):
            with self.assertRaises(FileExistsError):
                installer.replace(record, record['new'], None)
        self.assertEqual(Path(record['target']).read_bytes(), b'foreign')

    def test_foreign_target_rejects_complete_rollback_before_compensation(self):
        records = [self.record('old.py', b'old', b'new'), self.record('new.py', None, b'new-module')]
        (self.backup / '000.bin').write_bytes(b'old')
        for record in records:
            installer.replace(record, record['new'], record['before'])
        Path(records[1]['target']).write_bytes(b'foreign')
        with self.assertRaisesRegex(RuntimeError, 'FOREIGN_TARGET_BLOCKS_ROLLBACK'):
            installer.check_rollback_set(records)
        self.assertEqual(Path(records[0]['target']).read_bytes(), b'new')
        self.assertEqual(Path(records[1]['target']).read_bytes(), b'foreign')

    def test_partial_install_rolls_back_existing_and_new_files(self):
        records = [self.record('old.py', b'old', b'new'), self.record('new.py', None, b'new-module'),
                   self.record('untouched.html', b'page', b'new-page')]
        (self.backup / '000.bin').write_bytes(b'old')
        (self.backup / '002.bin').write_bytes(b'page')
        for record in records[:2]:
            installer.replace(record, record['new'], record['before'])
        installer.check_rollback_set(records)
        for record in reversed(records):
            installer.compensate(record)
        self.assertTrue(all(installer.fingerprint(record['target']) == record['before'] for record in records))


if __name__ == '__main__':
    unittest.main()
