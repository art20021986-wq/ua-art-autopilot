#!/usr/bin/env python3
'''Offline unit and integration tests for the CRM-SPEED-001 Gate A engine.

These tests build a fully synthetic fixture tree that mimics the shape of
/home/Carix (never the real production tree) and run the gate engine
against it using CRM_SPEED_SOURCE_BASE and CRM_SPEED_QA_BASE overrides.
No production path is read or written by this test file.
'''

import os
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import crm_speed_gate_a as gate  # noqa: E402
import verify_gate_a  # noqa: E402


FIXTURE_USERCUSTOMIZE = (
    "import sys\n"
    "import team_bot\n"
    "\n"
    "print('loaded')\n"
)

FIXTURE_ENTRY = (
    "import sys\n"
    "\n"
    "\n"
    "def bootstrap():\n"
    "    return True\n"
    "\n"
    "\n"
    "if __name__ == '__main__':\n"
    "    bootstrap()\n"
)

FIXTURE_ENTRY_NO_MAIN = (
    "def bootstrap():\n"
    "    return True\n"
)

FIXTURE_AVTOPEREDACHA = (
    "import subprocess\n"
    "import sqlite3\n"
    "\n"
    "\n"
    "def kolonki_cars():\n"
    "    conn = sqlite3.connect('crm.db')\n"
    "    rows = conn.execute('SELECT 1').fetchall()\n"
    "    conn.close()\n"
    "    return rows\n"
    "\n"
    "\n"
    "def otpechatok():\n"
    "    return kolonki_cars()\n"
    "\n"
    "\n"
    "def shag():\n"
    "    otpechatok()\n"
    "    subprocess.run(['python3', 'stranica.py'])\n"
)

FIXTURE_SAMOKONTROL = (
    "import sqlite3\n"
    "\n"
    "\n"
    "def kolonki():\n"
    "    conn = sqlite3.connect('crm.db')\n"
    "    data = conn.execute('SELECT 1').fetchall()\n"
    "    conn.close()\n"
    "    return data\n"
    "\n"
    "\n"
    "def proverit_bazu():\n"
    "    return kolonki()\n"
)

FIXTURE_CARS_UI = (
    "async def gallery(update, context):\n"
    "    await update.message.reply_photo(open('a.jpg', 'rb'))\n"
    "\n"
    "\n"
    "async def video_gallery(update, context):\n"
    "    await update.message.reply_video(open('a.mp4', 'rb'))\n"
    "\n"
    "\n"
    "def diag_photo_show(update, context):\n"
    "    update.message.reply_photo(open('b.jpg', 'rb'))\n"
    "\n"
    "\n"
    "def diag_video_show(update, context):\n"
    "    update.message.reply_video(open('b.mp4', 'rb'))\n"
    "\n"
    "\n"
    "def save_photo(car_id, path):\n"
    "    return True\n"
    "\n"
    "\n"
    "def delete_photo(car_id, path):\n"
    "    return True\n"
)


def _write(root, rel, content):
    full = os.path.join(root, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w', encoding='utf-8') as fh:
        fh.write(content)


def _build_fixture_tree(root):
    files = {
        '.local/lib/python3.10/site-packages/usercustomize.py': FIXTURE_USERCUSTOMIZE,
        '.local/lib/python3.13/site-packages/usercustomize.py': FIXTURE_USERCUSTOMIZE,
        'start_safe.py': FIXTURE_ENTRY,
        'run_all.py': FIXTURE_ENTRY,
        'cars_ui.py': FIXTURE_CARS_UI,
        'avtoperedacha.py': FIXTURE_AVTOPEREDACHA,
        'samokontrol.py': FIXTURE_SAMOKONTROL,
        'db.py': "def get_connection():\n    return None\n",
        'team_bot.py': "def main():\n    return None\n",
        'stranica.py': "def generate():\n    return None\n",
    }
    for rel, content in files.items():
        _write(root, rel, content)

    db_path = os.path.join(root, 'crm.db')
    conn = sqlite3.connect(db_path)
    conn.execute('CREATE TABLE cards (id INTEGER PRIMARY KEY, code TEXT)')
    conn.execute("INSERT INTO cards (code) VALUES ('UA-0009')")
    conn.commit()
    conn.close()

    backup_dir = os.path.join(root, 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, 'crm_speed_20260827_1038_before.tar.gz')
    seed_path = os.path.join(backup_dir, '_seed.txt')
    with open(seed_path, 'w', encoding='utf-8') as fh:
        fh.write('seed')
    with tarfile.open(backup_path, 'w:gz') as tf:
        tf.add(seed_path, arcname='_seed.txt')
    os.remove(seed_path)
    return gate.fingerprint_file(backup_path)['sha256']


class GateHelperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='crm_speed_test_')
        self.source_base = os.path.join(self.tmp, 'home_carix')
        self.qa_base = os.path.join(self.tmp, 'qa')
        os.makedirs(self.source_base, exist_ok=True)
        self.backup_sha = _build_fixture_tree(self.source_base)
        os.environ['CRM_SPEED_BACKUP_SHA256'] = self.backup_sha

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ.pop('CRM_SPEED_BACKUP_SHA256', None)
        os.environ.pop('CRM_SPEED_UA0009_URL', None)

    def test_resolve_inputs_ok(self):
        ok, info, blockers = gate.resolve_required_inputs(self.source_base)
        self.assertTrue(ok, blockers)
        self.assertIn('crm.db', info)

    def test_resolve_inputs_missing_blocks(self):
        os.remove(os.path.join(self.source_base, 'cars_ui.py'))
        ok, info, blockers = gate.resolve_required_inputs(self.source_base)
        self.assertFalse(ok)
        self.assertTrue(any('cars_ui.py' in b for b in blockers))

    def test_resolve_inputs_rejects_symlink(self):
        target = os.path.join(self.source_base, 'db.py')
        link_target_dir = os.path.join(self.tmp, 'outside')
        os.makedirs(link_target_dir, exist_ok=True)
        real_outside = os.path.join(link_target_dir, 'real_db.py')
        shutil.copyfile(target, real_outside)
        os.remove(target)
        try:
            os.symlink(real_outside, target)
        except (OSError, NotImplementedError):
            self.skipTest('symlinks not supported in this environment')
        ok, info, blockers = gate.resolve_required_inputs(self.source_base)
        self.assertFalse(ok)
        self.assertTrue(any('db.py' in b for b in blockers))

    def test_backup_verification_matches(self):
        ok, sha, blocker = gate.verify_backup_archive(self.source_base, expected_sha=self.backup_sha)
        self.assertTrue(ok)
        self.assertIsNone(blocker)

    def test_backup_verification_mismatch(self):
        ok, sha, blocker = gate.verify_backup_archive(self.source_base, expected_sha='0' * 64)
        self.assertFalse(ok)
        self.assertIsNotNone(blocker)

    def test_safe_writer_rejects_traversal(self):
        writer = gate.SafeWriter(os.path.join(self.tmp, 'writer_root'))
        with self.assertRaises(ValueError):
            writer.write_text('../escape.txt', 'x')

    def test_transform_usercustomize_removes_forbidden_import(self):
        result = gate.transform_usercustomize(FIXTURE_USERCUSTOMIZE, 'usercustomize.py')
        self.assertTrue(result.ok)
        self.assertNotIn('import team_bot', result.new_source)
        compile(result.new_source, 'usercustomize.py', 'exec')

    def test_transform_usercustomize_idempotent_on_clean_file(self):
        clean = "import sys\nprint('ok')\n"
        result = gate.transform_usercustomize(clean, 'usercustomize.py')
        self.assertTrue(result.ok)
        self.assertEqual(result.new_source, clean)

    def test_transform_singleton_entry_requires_main_anchor(self):
        result = gate.transform_singleton_entry(FIXTURE_ENTRY_NO_MAIN, 'start_safe.py')
        self.assertFalse(result.ok)
        self.assertIn('missing_anchor', result.reason)

    def test_transform_singleton_entry_injects_guard(self):
        result = gate.transform_singleton_entry(FIXTURE_ENTRY, 'start_safe.py')
        self.assertTrue(result.ok)
        self.assertIn(gate.SINGLETON_MARKER, result.new_source)
        compile(result.new_source, 'start_safe.py', 'exec')

    def test_singleton_guard_template_rejects_duplicate(self):
        self.assertTrue(gate._exercise_singleton_guard_template())

    def test_transform_avtoperedacha_requires_all_three_anchors(self):
        result = gate.transform_avtoperedacha("def kolonki_cars():\n    return []\n", 'avtoperedacha.py')
        self.assertFalse(result.ok)
        self.assertIn('missing_anchor_functions', result.reason)

    def test_transform_avtoperedacha_removes_subprocess_and_adds_timeout(self):
        result = gate.transform_avtoperedacha(FIXTURE_AVTOPEREDACHA, 'avtoperedacha.py')
        self.assertTrue(result.ok)
        compile(result.new_source, 'avtoperedacha.py', 'exec')
        self.assertNotIn('subprocess.run', result.new_source)
        self.assertIn('_crm_speed_enqueue_rebuild', result.new_source)
        self.assertIn('timeout=5', result.new_source)

    def test_transform_samokontrol_adds_timeout(self):
        result = gate.transform_samokontrol(FIXTURE_SAMOKONTROL, 'samokontrol.py')
        self.assertTrue(result.ok)
        self.assertIn('timeout=5', result.new_source)
        compile(result.new_source, 'samokontrol.py', 'exec')

    def test_transform_cars_ui_requires_all_four_anchors(self):
        partial = "async def gallery(update, context):\n    return None\n"
        result = gate.transform_cars_ui(partial, 'cars_ui.py')
        self.assertFalse(result.ok)
        self.assertIn('missing_anchor_functions', result.reason)

    def test_transform_cars_ui_removes_media_calls_and_keeps_storage_functions(self):
        result = gate.transform_cars_ui(FIXTURE_CARS_UI, 'cars_ui.py')
        self.assertTrue(result.ok)
        compile(result.new_source, 'cars_ui.py', 'exec')
        hits = gate.find_reachable_media_calls(result.new_source, gate.REQUIRED_ADMIN_FUNCS)
        self.assertEqual(hits, [])
        self.assertIn('def save_photo(car_id, path):', result.new_source)
        self.assertIn('def delete_photo(car_id, path):', result.new_source)
        self.assertIn('return True', result.new_source)

    def test_debounce_queue_collapses_burst(self):
        ns = {}
        exec(compile(gate.REBUILD_QUEUE_TEMPLATE, 'rebuild_queue.py', 'exec'), ns)
        ns['_crm_speed_rebuild_state']['debounce_seconds'] = 0.02
        calls = {'count': 0}

        def cb():
            calls['count'] += 1

        ns['set_rebuild_callback'](cb)
        for _ in range(5):
            ns['_crm_speed_enqueue_rebuild']()
        time.sleep(0.3)
        self.assertEqual(calls['count'], 1)

    def test_deterministic_repeat_ten_times(self):
        outputs = set()
        for _ in range(10):
            result = gate.transform_avtoperedacha(FIXTURE_AVTOPEREDACHA, 'avtoperedacha.py')
            outputs.add(result.new_source)
        self.assertEqual(len(outputs), 1)

    def test_full_gate_a_run_pass_path(self):
        receipt = gate.run_gate_a(source_base=self.source_base, qa_base=self.qa_base)
        self.assertEqual(receipt['status'], 'GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL', receipt.get('blockers'))
        self.assertEqual(receipt['production_write'], 'NO')
        problems = verify_gate_a.verify(receipt)
        self.assertEqual(problems, [])

    def test_full_gate_a_run_blocked_when_missing_input(self):
        os.remove(os.path.join(self.source_base, 'run_all.py'))
        receipt = gate.run_gate_a(source_base=self.source_base, qa_base=self.qa_base)
        self.assertEqual(receipt['status'], 'BLOCKED')
        self.assertTrue(any('run_all.py' in b for b in receipt['blockers']))
        problems = verify_gate_a.verify(receipt)
        self.assertTrue(len(problems) > 0)

    def test_repeated_gate_a_runs_are_safe(self):
        for _ in range(3):
            receipt = gate.run_gate_a(source_base=self.source_base, qa_base=self.qa_base)
            self.assertIn(receipt['status'], ('GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL', 'BLOCKED'))


if __name__ == '__main__':
    unittest.main()
