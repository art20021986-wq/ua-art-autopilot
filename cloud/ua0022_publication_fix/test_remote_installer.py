"""Production-free regressions for the narrow installer's rollback boundaries."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ua0022_installer_under_test', HERE / 'remote_installer.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class InstallerRegression(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'root'
        self.root.mkdir()
        self.package = Path(self.temp.name) / 'package'
        self.package.mkdir()
        self.original_root = runtime.ROOT
        runtime.ROOT = self.root
        self.old_modules = {}
        for name in ('_ua0022_bound_builder', 'publication_fence', 'publikaciya', 'publish_transaction_guard'):
            self.old_modules[name] = sys.modules.pop(name, None)
        for folder in ('video', 'site', 'rezerv_publikacii'):
            (self.root / folder).mkdir()
        for name in ('.start_safe.singleton.lock', '.ua_art_publish_transaction.lock'):
            (self.root / name).write_bytes(b'existing inode\n')
        for name in ('start_safe.py', 'run_all.py'):
            (self.root / name).write_text('# reviewed entrypoint fixture\n')
        for folder in ('video', 'site'):
            for name in ('index.html', 'katalog.html', 'UA-0015.html', 'UA-0022-diag.html'):
                (self.root / folder / name).write_text('<html>original ' + name + '</html>')
        self.conn = sqlite3.connect(self.root / 'crm.db')
        self.conn.executescript('''
            CREATE TABLE cars(id INTEGER PRIMARY KEY,auto_number TEXT,published INTEGER,
                status TEXT,publish_pending INTEGER,price_uah REAL,price_georgia REAL,description TEXT);
            INSERT INTO cars VALUES(32,'UA-0022',0,'kr_bought',0,18000,14000,'operator content');
            INSERT INTO cars VALUES(15,'UA-0015',1,'sea',0,20000,16000,'other content');
            CREATE TABLE media(id INTEGER PRIMARY KEY,car_id INTEGER,path TEXT);
            INSERT INTO media VALUES(1,32,'existing-photo');
        ''')
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        runtime.ROOT = self.original_root
        for name, module in self.old_modules.items():
            sys.modules.pop(name, None)
            if module is not None:
                sys.modules[name] = module
        self.temp.cleanup()

    def installer(self, success=True, edit_protected=False, media_addition=None):
        publisher = '''from pathlib import Path
def opublikovat(code, proba=False):
    root = Path(__file__).parent
    print('private publisher progress')
    for folder in ('video','site'):
        for name in (code+'.html',code+'-diag.html','katalog.html','index.html'):
            (root/folder/name).write_text('<html>published '+name+'</html>')
    (root/'video'/(code+'-new.html')).write_text('own new page')
'''
        if edit_protected:
            publisher += "    (root/'video'/'UA-0015.html').write_text('unexpected foreign write')\n"
        if media_addition:
            publisher += ('    extra = root / ' + repr(media_addition) + '\n'
                          '    extra.parent.mkdir(parents=True, exist_ok=True)\n'
                          "    extra.write_bytes(b'native generated JPEG derivative')\n")
        publisher += '    return ' + repr((success, 'private result')) + '\n'
        sources = {'cars_ui.py': 'def f():\n    return 1\n',
                   'stranica.py': 'def main():\n    return 2\n',
                   'publish_transaction_guard.py': "def verify_bundle(codes):\n    return {'targets': {codes[0]: {}}}\n",
                   'publikaciya.py': publisher}
        for name, data in sources.items():
            (self.root / name).write_text(data)
        source_sha = {name: runtime.sha((self.root / name).read_bytes()) for name in sources}
        helper = b'from contextlib import nullcontext\ndef publication_fence(timeout=90):\n    return nullcontext()\n'
        (self.package / 'publication_fence.py').write_bytes(helper)
        builder = ('SOURCE_SHA256 = ' + repr(source_sha) + '\nHELPER_SHA256 = ' + repr(runtime.sha(helper)) +
                   "\ndef transform(name, text):\n    return text+'\\n# installed narrow fence\\n'\n")
        (self.package / 'build_candidate.py').write_text(builder)
        (self.package / 'remote_installer.py').write_bytes((HERE / 'remote_installer.py').read_bytes())
        row = runtime.db_state()['target_row']
        backup = self.root / 'rezerv_publikacii' / 'TASKTEST-NONCETEST'
        plan = {'version': 1, 'contract': runtime.CONTRACT, 'task_id': 'TASKTEST', 'nonce': 'NONCETEST',
                'root': str(self.root), 'alwayson_id': 266084, 'backup_dir': str(backup),
                'receipt_dir': str(backup), 'source_sha256': source_sha,
                'runtime_entrypoint_sha256': {name: runtime.sha((self.root / name).read_bytes())
                                              for name in ('start_safe.py', 'run_all.py')},
                'helper_sha256': runtime.sha(helper),
                'package_sha256': {name: runtime.sha((self.package / name).read_bytes()) for name in
                                   ('build_candidate.py', 'publication_fence.py', 'remote_installer.py')},
                'target': {key: row[key] for key in ('id','auto_number','published','status','publish_pending')}}
        plan['target']['expected_row_sha256'] = runtime.digest(row)
        return runtime.Installer(plan, self.package)

    def test_singleton_missing_does_not_create_inode(self):
        path = self.root / '.start_safe.singleton.lock'
        path.unlink()
        with self.assertRaisesRegex(runtime.Stop, 'REQUIRED_FILE_ABSENT'):
            with runtime.singleton(timeout=0):
                self.fail('missing inode acquired')
        self.assertFalse(path.exists())

    def test_singleton_preserves_inode_and_bytes(self):
        path = self.root / '.start_safe.singleton.lock'
        original = (path.stat().st_ino, path.read_bytes())
        with runtime.singleton(timeout=0):
            self.assertEqual(path.stat().st_ino, original[0])
        self.assertEqual((path.stat().st_ino, path.read_bytes()), original)

    def test_exact_row_cas_rejects_operator_change(self):
        before = runtime.db_state()['target_row']
        self.conn.execute("UPDATE cars SET description='new operator value' WHERE id=32")
        self.conn.commit()
        with self.assertRaisesRegex(runtime.Stop, 'TARGET_ROW_CAS_FAILED'):
            runtime.cas_published(before, 1)
        row = runtime.db_state()['target_row']
        self.assertEqual(row['published'], 0)
        self.assertEqual(row['description'], 'new operator value')

    def test_stale_admission_rolls_back_as_noop_without_erasing_operator_changes(self):
        installer = self.installer()
        self.assertEqual(installer.backup_phase()['status'], 'PASS')
        path = self.root / 'cars_ui.py'
        path.write_text('def operator_change():\n    return 3\n')
        self.conn.execute("UPDATE cars SET price_uah=19999 WHERE id=32")
        self.conn.commit()
        with self.assertRaisesRegex(runtime.Stop, 'SOURCE_PREIMAGE_CHANGED'):
            installer.install_phase()
        receipt = installer.rollback_phase()
        self.assertTrue(receipt['no_mutation'])
        self.assertEqual(runtime.db_state()['target_row']['price_uah'], 19999)
        self.assertIn('operator_change', path.read_text())

    def test_publisher_failure_restores_only_own_rows_sources_and_pages(self):
        installer = self.installer(success=False)
        installer.backup_phase()
        before = runtime.db_state()
        pages = runtime.public_snapshot()
        sources = {name: (self.root / name).read_bytes() for name in runtime.MUTATED_SOURCES}
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            receipt = installer.install_phase()
        self.assertEqual(receipt['status'], 'FAIL')
        self.assertEqual(receipt['rollback_status'], 'PASS')
        self.assertEqual(stdout.getvalue(), '')
        self.assertEqual(runtime.db_state(), before)
        self.assertEqual(runtime.public_snapshot(), pages)
        for name, content in sources.items():
            self.assertEqual((self.root / name).read_bytes(), content)
        self.assertFalse((self.root / 'publication_fence.py').exists())
        self.assertFalse((self.root / 'video' / 'UA-0022-new.html').exists())
        self.assertIn('private publisher progress', (installer.backup / 'publisher_execution.log').read_text())

    def test_success_and_idempotent_receipt_have_bound_evidence(self):
        installer = self.installer()
        backup = installer.backup_phase()
        receipt = installer.install_phase()
        self.assertEqual(receipt['status'], 'PASS')
        self.assertEqual(receipt['backup_manifest_sha256'], backup['backup_manifest_sha256'])
        self.assertEqual(receipt['plan_sha256'], runtime.sha(runtime.encoded(installer.plan) + b'\n'))
        for flag in ('publication_pass','post_check_pass','integrity_pass','protected_pages_unchanged',
                     'other_rows_unchanged','ua_ge_prices_unchanged','target_media_unchanged'):
            self.assertIs(receipt[flag], True)
        self.assertEqual(runtime.db_state()['target_row']['published'], 1)
        self.assertTrue(installer.install_phase()['idempotent'])

    def test_rollback_rejects_later_operator_page_change(self):
        installer = self.installer()
        installer.backup_phase()
        installer.install_phase()
        path = self.root / 'video' / 'UA-0022.html'
        path.write_text('later operator edit')
        with self.assertRaisesRegex(runtime.Stop, 'ROLLBACK_PUBLIC_CAS_FAILED'):
            installer.rollback_phase()
        self.assertEqual(path.read_text(), 'later operator edit')
        self.assertEqual(runtime.db_state()['target_row']['published'], 1)

    def test_unknown_interrupted_publish_fails_closed(self):
        installer = self.installer()
        installer.backup_phase()
        journal = installer.journal()
        journal['state'] = 'PUBLISHING'
        installer.journal(journal)
        with self.assertRaisesRegex(runtime.Stop, 'AMBIGUOUS_PUBLICATION_POSTIMAGE'):
            installer.rollback_phase()

    def test_protected_page_drift_never_gets_overwritten_by_rollback(self):
        installer = self.installer(edit_protected=True)
        installer.backup_phase()
        with self.assertRaisesRegex(runtime.Stop, 'ROLLBACK_PROTECTED_PAGES_CHANGED'):
            installer.install_phase()
        self.assertEqual((self.root / 'video' / 'UA-0015.html').read_text(), 'unexpected foreign write')

    def test_backup_tampering_is_detected_before_any_install_write(self):
        installer = self.installer()
        installer.backup_phase()
        (installer.backup / 'files' / '0.gz').write_bytes(b'corrupt')
        with self.assertRaises((runtime.Stop, OSError)):
            installer.install_phase()
        self.assertEqual(runtime.db_state()['target_row']['published'], 0)
        self.assertFalse((self.root / 'publication_fence.py').exists())

    def original_photo(self):
        path = self.root / 'video' / 'foto' / 'UA-0022' / '001.jpg'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'operator original JPEG bytes')
        return path

    def test_native_first_publish_derivative_allowed_and_scoped_rollback_removes_it(self):
        original = self.original_photo()
        original_bytes = original.read_bytes()
        derivative = 'video/foto/UA-0022/m/001.jpg'
        installer = self.installer(media_addition=derivative)
        installer.backup_phase()
        receipt = installer.install_phase()
        self.assertEqual(receipt['status'], 'PASS')
        self.assertTrue(receipt['target_original_media_unchanged'])
        self.assertTrue(receipt['target_new_media_derivatives_only'])
        self.assertEqual(receipt['target_media_derivatives_added'], 1)
        self.assertFalse(receipt['target_media_unchanged'])
        self.assertEqual(original.read_bytes(), original_bytes)
        self.assertEqual(installer.rollback_phase()['status'], 'PASS')
        self.assertFalse((self.root / derivative).exists())
        self.assertEqual(original.read_bytes(), original_bytes)

    def test_foreign_filename_cannot_be_accepted_as_target_derivative(self):
        self.original_photo()
        derivative = 'video/foto/UA-0022/m/unbound.jpg'
        installer = self.installer(media_addition=derivative)
        installer.backup_phase()
        receipt = installer.install_phase()
        self.assertEqual(receipt['status'], 'FAIL')
        self.assertEqual(receipt['error_code'], 'TARGET_DERIVATIVE_ORIGINAL_NOT_BOUND')
        self.assertEqual(receipt['rollback_status'], 'PASS')
        self.assertFalse((self.root / derivative).exists())

    def test_wrong_subtree_cannot_be_accepted_as_target_derivative(self):
        self.original_photo()
        derivative = 'video/diag/UA-0022/m/001.jpg'
        installer = self.installer(media_addition=derivative)
        installer.backup_phase()
        receipt = installer.install_phase()
        self.assertEqual(receipt['status'], 'FAIL')
        self.assertEqual(receipt['error_code'], 'TARGET_MEDIA_ADDITION_OUT_OF_SCOPE')
        self.assertEqual(receipt['rollback_status'], 'PASS')
        self.assertFalse((self.root / derivative).exists())

    def test_native_video_count_rejected_before_any_install_mutation(self):
        installer = self.installer()
        installer.backup_phase()
        preview = self.root / 'video' / 'preview'
        preview.mkdir()
        (preview / 'UA-0022-ignored.mp4').write_bytes(b'preview')
        (self.root / 'video' / 'UA-0022-first.mp4').write_bytes(b'first')
        self.assertEqual(runtime.assert_native_video_dedup_inert(), 1)
        (self.root / 'video' / 'UA-0022-second.MOV').write_bytes(b'second')
        with self.assertRaisesRegex(runtime.Stop, 'TARGET_VIDEO_DEDUP_WOULD_MUTATE_UNBACKED_FILES'):
            installer.install_phase()
        self.assertEqual(installer.journal()['state'], 'BACKED_UP')
        self.assertEqual(runtime.db_state()['target_row']['published'], 0)
        self.assertFalse((self.root / 'publication_fence.py').exists())
        self.assertTrue(installer.rollback_phase()['no_mutation'])


if __name__ == '__main__':
    unittest.main()
