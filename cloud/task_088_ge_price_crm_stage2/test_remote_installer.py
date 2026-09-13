"""Installer safety tests exercise real SQLite backups, hash gates and atomic source rollback."""
import datetime as dt
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

import patcher
import remote_installer as remote
from test_fixtures import FIXTURE

SOURCE = FIXTURE + '''
def jload(value, default=None):
    try:
        return json.loads(value) if value else default
    except Exception:
        return default
def jdump(value):
    return json.dumps(value, ensure_ascii=False)
def price_history(card):
    return jload(card.get("price_history"), {}) or {}
'''
DB_SOURCE = '''
import sqlite3
from datetime import datetime
DB_FILE = "/forbidden/live/database.db"
ZAMOK_OZHIDANIE = 10
class Soedinenie(sqlite3.Connection):
    pass
def connect():
    conn = sqlite3.connect(DB_FILE, timeout=ZAMOK_OZHIDANIE, factory=Soedinenie)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
def now():
    return datetime.now().isoformat(timespec="seconds")
raise RuntimeError("WHOLE LIVE MODULE MUST NEVER BE IMPORTED")
'''
UTIL_SOURCE = '''
def stage_of(value):
    return int(value or 1)
def num(value):
    return str(value)
raise RuntimeError("WHOLE LIVE UTILS MUST NEVER BE IMPORTED")
'''


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.safe = self.root / 'autopilot_inbox/cloud/task_088_ge_price_crm_stage2'
        self.safe.mkdir(parents=True)
        self.original_sha = patcher.digest(SOURCE)
        self.candidate_sha = patcher.digest(patcher.build_candidate(SOURCE, expected_sha256=self.original_sha)[0])
        self.plan = dict(task_id=remote.TASK_ID, run_id='test-123', request_sha256='a'*64,
            transaction_id='transaction-123', manifest_sha256='b'*64, nonce='fresh-nonce-123',
            operation='backup', source_path=str(self.root/'cars_ui.py'), db_path=str(self.root/'crm.db'),
            db_module_path=str(self.root/'db.py'), parser_path=str(self.root/'price_parser.py'),
            utils_path=str(self.root/'cars_schema.py'), expected_source_sha256=self.original_sha,
            expected_candidate_sha256=self.candidate_sha,
            quota=dict(measured_at=remote.now(), total_bytes=10**11, used_bytes=10**9),
            exact_process=dict(pid=999, start_ticks='123', cmdline_sha256='c'*64),
            remote_package_sha256={name: remote.sha(Path(remote.__file__).parent/name) for name in ('remote_installer.py','patcher.py','runtime.py')})
        self.directory = self.safe / 'runs' / (self.plan['run_id'] + '-' + self.plan['request_sha256'])
        self.directory.mkdir(parents=True)
        (self.root/'cars_ui.py').write_text(SOURCE)
        (self.root/'db.py').write_text(DB_SOURCE)
        (self.root/'cars_schema.py').write_text(UTIL_SOURCE)
        (self.root/'price_parser.py').write_text('raise RuntimeError("PARSER MODULE MUST NEVER BE IMPORTED")\n')
        self.plan['expected_dependency_sha256'] = {self.plan[key]: remote.sha(self.plan[key]) for key in remote.DEPENDENCY_KEYS}
        receipt = self.root/'autopilot_inbox/cloud/task_088_ge_price_crm_stage1/receipt.json'
        receipt.parent.mkdir(parents=True)
        receipt.write_text(json.dumps(dict(task_id='TASK088-GE-PRICE-CRM-STAGE1', status='PASS',
            after_sha256={self.plan['source_path']:self.original_sha})))
        self.plan.update(stage1_receipt_path=str(receipt), expected_stage1_receipt_sha256=remote.sha(receipt))
        with sqlite3.connect(self.plan['db_path']) as conn:
            conn.executescript('''CREATE TABLE cars(id INTEGER PRIMARY KEY,price_uah INTEGER,price_georgia INTEGER,
                price_history TEXT,updated_at TEXT,status TEXT,vin TEXT);
                CREATE TABLE audit(actor_id INTEGER,action TEXT,entity_type TEXT,entity_id INTEGER,
                field TEXT,old_value TEXT,new_value TEXT,created_at TEXT);
                INSERT INTO cars VALUES(1,18000,NULL,'{"1":18000}','old','1','PRESERVEDVIN');
                INSERT INTO cars VALUES(2,22000,19000,'{}','old','2','SECONDVIN');''')
        self.before_facts = remote.database_facts(self.plan['db_path'])
        self.original_builder = patcher.build_candidate
        self.original_process_facts = remote.process_facts
        self.patches = [mock.patch.object(remote, 'ROOT', self.root), mock.patch.object(remote, 'SAFE', self.safe),
            mock.patch.object(patcher, 'EXPECTED_SOURCE_SHA256', self.original_sha),
            mock.patch.object(patcher, 'build_candidate', side_effect=lambda source: self.original_builder(source, expected_sha256=self.original_sha)),
            mock.patch.object(remote, 'process_facts', return_value=self.plan['exact_process'])]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def operation(self, operation, **updates):
        plan = dict(self.plan, operation=operation, **updates)
        return remote.run_operation(plan, operation, self.directory)

    def successful_backup(self):
        result = self.operation('backup')
        self.assertEqual(result['status'], 'BACKUP_PASS', result)
        self.plan['backup_manifest_sha256'] = result['backup_manifest_sha256']
        self.plan['expected_candidate_sha256'] = result['candidate_sha256']
        return result

    def test_online_backup_then_install_verify_rollback_without_live_db_writes(self):
        result = self.successful_backup()
        self.assertEqual(result['shadow_handler_acceptance'], 'NOT_PERFORMED')
        self.assertEqual(remote.database_facts(self.plan['db_path']), self.before_facts)
        manifest = json.loads((self.directory/'backup-manifest.json').read_text())
        self.assertEqual(manifest['runtime_compatibility'], 'PENDING_LIVE_CHECKS')
        self.assertEqual(remote.sha(self.root/'cars_ui.py'), self.original_sha)
        installed = self.operation('execute')
        self.assertEqual(installed['status'], 'INSTALLED_AWAITING_VERIFICATION', installed)
        verified = self.operation('verify')
        self.assertEqual(verified['status'], 'INSTALLATION_VERIFIED', verified)
        self.assertEqual(verified['stage2_acceptance'], 'PENDING_TELEGRAM_CHECKS')
        self.assertEqual(verified['telegram_ui_acceptance'], 'NOT_PERFORMED')
        restored = self.operation('rollback')
        self.assertEqual(restored['status'], 'ROLLED_BACK', restored)
        self.assertEqual(remote.sha(self.root/'cars_ui.py'), self.original_sha)
        self.assertEqual(remote.database_facts(self.plan['db_path']), self.before_facts)

    def test_replayed_operation_cannot_overwrite_result(self):
        self.successful_backup()
        first = remote.sha(self.directory/'backup-result.json')
        with self.assertRaises(FileExistsError):
            self.operation('backup')
        self.assertEqual(remote.sha(self.directory/'backup-result.json'), first)

    def test_nonce_cannot_be_reused_in_another_request_or_run(self):
        self.successful_backup()
        another = dict(self.plan, run_id='other-run', request_sha256='d'*64)
        directory = self.safe / 'runs' / (another['run_id'] + '-' + another['request_sha256'])
        directory.mkdir()
        with self.assertRaisesRegex(remote.Refused, 'IDENTITY_ALREADY_CLAIMED:nonce'):
            remote.run_operation(another, 'backup', directory)
        self.assertFalse((directory/'cars_ui.original.py').exists())

    def test_approved_candidate_mismatch_refuses_before_source_backup(self):
        result = self.operation('backup', expected_candidate_sha256='f'*64)
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('APPROVED_CANDIDATE_HASH_MISMATCH', result['error'])
        self.assertFalse((self.directory/'cars_ui.original.py').exists())
        self.assertEqual(remote.sha(self.root/'cars_ui.py'), self.original_sha)

    def test_process_identity_drift_after_backup_refuses_install(self):
        self.successful_backup()
        changed = dict(self.plan['exact_process'], pid=1001, start_ticks='999')
        with mock.patch.object(remote, 'process_facts', return_value=changed):
            result = self.operation('execute')
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('PROCESS_IDENTITY_CHANGED_AFTER_BACKUP', result['error'])
        self.assertEqual(remote.sha(self.root/'cars_ui.py'), self.original_sha)

    def absent_parser(self):
        parser = self.root/'price_parser.py'
        parser.unlink()
        self.plan['expected_dependency_sha256'].pop(str(parser))
        self.plan['expected_absent_dependency_paths'] = [str(parser)]

    def test_explicit_absent_optional_parser_allows_static_install_and_verify(self):
        self.absent_parser()
        self.successful_backup()
        manifest = json.loads((self.directory/'backup-manifest.json').read_text())
        self.assertEqual(manifest['facts']['protected_source_sha256'][self.plan['parser_path']], 'ABSENT')
        self.assertEqual(self.operation('execute')['status'], 'INSTALLED_AWAITING_VERIFICATION')
        self.assertEqual(self.operation('verify')['status'], 'INSTALLATION_VERIFIED')
        self.assertFalse((self.root/'price_parser.py').exists())

    def test_new_parser_after_backup_blocks_install(self):
        self.absent_parser()
        self.successful_backup()
        (self.root/'price_parser.py').write_text('raise RuntimeError("DO NOT IMPORT")')
        result = self.operation('execute')
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('EXPECTED_ABSENT_PARSER_APPEARED', result['error'])
        self.assertEqual(remote.sha(self.root/'cars_ui.py'), self.original_sha)

    def test_importable_parser_elsewhere_blocks_absence_claim_without_import(self):
        self.absent_parser()
        alternate = self.root/'alternate-site-packages'
        alternate.mkdir()
        (alternate/'price_parser.py').write_text('raise RuntimeError("MUST NOT IMPORT")')
        with mock.patch.object(remote.sys, 'path', list(remote.sys.path)+[str(alternate)]):
            result = self.operation('backup')
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('EXPECTED_ABSENT_PARSER_IMPORTABLE', result['error'])
        self.assertFalse((self.directory/'cars_ui.original.py').exists())

    def test_supervisor_observations_record_evidence_and_compare_stable_identity(self):
        observation = dict(source='PYTHONANYWHERE_AUTHENTICATED_API',supervisor_id=266084,
            command='python3.10 '+str(self.root/'start_safe.py'),status='Running',enabled=True,observed_at=remote.now())
        self.plan['exact_process'] = dict(verification_mode='authenticated_supervisor',supervisor_id=266084,
            command_argv=['python3.10',str(self.root/'start_safe.py')],observed_evidence=observation)
        with mock.patch.object(remote,'process_facts',new=self.original_process_facts):
            self.successful_backup()
            manifest=json.loads((self.directory/'backup-manifest.json').read_text())
            self.assertEqual(manifest['facts']['supervisor_observation'],observation)
            self.plan['exact_process']['observed_evidence']=dict(observation,observed_at=remote.now())
            installed=self.operation('execute')
            self.assertEqual(installed['status'],'INSTALLED_AWAITING_VERIFICATION',installed)
            verified=self.operation('verify')
            self.assertEqual(verified['status'],'INSTALLATION_VERIFIED',verified)
            self.assertEqual(verified['process_verification']['os_pid_inspection'],'NO_OS_PID_INSPECTION')

    def test_dependency_drift_refuses_before_backup_or_live_mutation(self):
        (self.root/'db.py').write_text(DB_SOURCE+'\n# changed\n')
        result = self.operation('backup')
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('DEPENDENCY_HASH_CHANGED', result['error'])
        self.assertFalse((self.directory/'crm.online-backup.db').exists())
        self.assertEqual(remote.sha(self.root/'cars_ui.py'), self.original_sha)

    def test_live_database_change_after_backup_refuses_install(self):
        self.successful_backup()
        with sqlite3.connect(self.plan['db_path']) as conn:
            conn.execute('UPDATE cars SET price_uah=20000 WHERE id=2')
        result = self.operation('execute')
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('DATABASE_CHANGED_AFTER_BACKUP', result['error'])
        self.assertEqual(remote.sha(self.root/'cars_ui.py'), self.original_sha)

    def test_tampered_backup_refuses_install(self):
        self.successful_backup()
        with (self.directory/'cars_ui.original.py').open('a') as stream:
            stream.write('\n# corrupted')
        result = self.operation('execute')
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('BACKUP_ARTIFACT_HASH_MISMATCH', result['error'])
        self.assertEqual(remote.sha(self.root/'cars_ui.py'), self.original_sha)

    def test_rollback_refuses_overwriting_unrelated_new_source(self):
        self.successful_backup()
        self.operation('execute')
        with (self.root/'cars_ui.py').open('a') as stream:
            stream.write('\n# later operator change')
        fingerprint = remote.sha(self.root/'cars_ui.py')
        result = self.operation('rollback')
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('ROLLBACK_SOURCE_DRIFT', result['error'])
        self.assertEqual(remote.sha(self.root/'cars_ui.py'), fingerprint)

    def test_stale_quota_does_not_create_backup(self):
        quota = dict(self.plan['quota'], measured_at=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=1)).isoformat())
        result = self.operation('backup', quota=quota)
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('ACCOUNT_QUOTA_STALE', result['error'])
        self.assertFalse((self.directory/'crm.online-backup.db').exists())

    def test_dangerous_live_db_trigger_is_never_executed_by_installer(self):
        with sqlite3.connect(self.plan['db_path']) as conn:
            conn.execute('CREATE TRIGGER bad AFTER UPDATE OF price_georgia ON cars BEGIN UPDATE cars SET price_uah=42 WHERE id=NEW.id; END')
        self.successful_backup()
        result = self.operation('execute')
        self.assertEqual(result['status'], 'INSTALLED_AWAITING_VERIFICATION', result)
        with sqlite3.connect(self.plan['db_path']) as conn:
            self.assertEqual(conn.execute('SELECT price_uah,price_georgia FROM cars WHERE id=1').fetchone(), (18000,None))

    def test_schema_mismatch_refuses_backup(self):
        result = self.operation('backup', expected_schema_sha256='f'*64)
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('LIVE_SCHEMA_CHANGED', result['error'])
        self.assertFalse((self.directory/'crm.online-backup.db').exists())


class ProcessDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.proc = Path(self.tmp.name)
        self.patch = mock.patch.object(remote, 'PROC', self.proc)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.expected = dict(command_argv=['python3.10', str(remote.ROOT/'start_safe.py')], supervisor_id=266084)

    def process(self, pid, argv, ticks='123'):
        path = self.proc/str(pid)
        path.mkdir(exist_ok=True)
        (path/'cmdline').write_bytes(b'\0'.join(x.encode() for x in argv)+b'\0')
        # State is field 3; starttime is field 22 (index 19 after comm).
        (path/'stat').write_text(str(pid)+' (python3.10) '+' '.join(['S']+['0']*18+[ticks]+['0']*5))

    def supervisor_expected(self, **evidence_updates):
        evidence = dict(source='PYTHONANYWHERE_AUTHENTICATED_API', supervisor_id=266084,
            command='python3.10 '+str(remote.ROOT/'start_safe.py'),status='Running',enabled=True,
            observed_at=remote.now())
        evidence.update(evidence_updates)
        return dict(verification_mode='authenticated_supervisor', supervisor_id=266084,
            command_argv=['python3.10',str(remote.ROOT/'start_safe.py')],observed_evidence=evidence)

    def test_authenticated_supervisor_accepts_fresh_controller_observation_without_pid_claim(self):
        expected = self.supervisor_expected()
        found = remote.process_facts(expected)
        self.assertEqual(found['supervisor_id'],266084)
        self.assertEqual(found['os_pid_inspection'],'NO_OS_PID_INSPECTION')
        self.assertNotIn('pid',found)
        self.assertNotIn('start_ticks',found)
        later = self.supervisor_expected(observed_at=remote.now())
        self.assertEqual(remote.process_facts(later),found)

    def test_authenticated_supervisor_refuses_stale_stopped_or_wrong_command(self):
        stale=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(minutes=6)).isoformat()
        for update, reason in (({'observed_at':stale},'SUPERVISOR_OBSERVATION_STALE'),
                ({'status':'Stopped'},'AUTHENTICATED_SUPERVISOR_IDENTITY_OR_STATE'),
                ({'command':'python3.10 /home/Carix/other.py'},'AUTHENTICATED_SUPERVISOR_IDENTITY_OR_STATE'),
                ({'enabled':False},'AUTHENTICATED_SUPERVISOR_IDENTITY_OR_STATE')):
            with self.subTest(update=update), self.assertRaisesRegex(remote.Refused,reason):
                remote.process_facts(self.supervisor_expected(**update))

    def test_discovery_accepts_unique_full_argv_with_executable_path(self):
        self.process(1234, ['/usr/local/bin/python3.10', self.expected['command_argv'][1]])
        self.process(2345, ['python3.10', self.expected['command_argv'][1], '--other'])
        self.process(3456, ['python3.10', self.expected['command_argv'][1]+'.other'])
        found = remote.process_facts(self.expected)
        self.assertEqual(found['pid'], 1234)
        self.assertEqual(found['start_ticks'], '123')
        self.assertEqual(found['supervisor_id'], 266084)

    def test_discovery_refuses_duplicate_or_missing_process(self):
        with self.assertRaisesRegex(remote.Refused, 'EXACT_CRM_PROCESS_MATCH_COUNT:0'):
            remote.process_facts(self.expected)
        for pid in (1234, 2345):
            self.process(pid, self.expected['command_argv'])
        with self.assertRaisesRegex(remote.Refused, 'EXACT_CRM_PROCESS_MATCH_COUNT:2'):
            remote.process_facts(self.expected)

    def test_explicit_pid_mode_refuses_reused_pid(self):
        self.process(1234, self.expected['command_argv'])
        found = remote.process_facts(self.expected)
        explicit = {key: found[key] for key in ('pid','start_ticks','cmdline_sha256')}
        self.assertEqual(remote.process_facts(explicit), explicit)
        self.process(1234, self.expected['command_argv'], ticks='999')
        with self.assertRaisesRegex(remote.Refused, 'PROCESS_IDENTITY_CHANGED'):
            remote.process_facts(explicit)


if __name__ == '__main__':
    unittest.main()
