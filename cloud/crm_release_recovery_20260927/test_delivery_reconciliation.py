"""The fixture uses captured remote data with synthetic queue/health observations."""
import copy
import datetime as dt
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import reconcile_delivery as route


ROOT = Path(__file__).resolve().parents[2]


class DeliveryReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)/'repo'
        shutil.copytree(ROOT,cls.root,ignore=shutil.ignore_patterns('.git','__pycache__'))
        cls.original = {p.relative_to(cls.root).as_posix():p.read_bytes()
                        for p in cls.root.rglob('*') if p.is_file()}

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.main = 'b'*40
        remote = json.loads((self.root/'cloud/crm_release_recovery_20260927/reconciliation_readonly_20260927.json').read_text())['remote']
        self.now = dt.datetime.fromisoformat(remote['observed_at'])+dt.timedelta(seconds=5)
        when = remote['observed_at']
        self.evidence = {'expected_main':self.main,'owner_actor_id':'321059821','remote':remote,
            'processes':{'observed_at':when,'commands':sorted([route.BOT,route.MONITOR]),
                         'enabled_always_on_commands':sorted([route.BOT,route.MONITOR]),'bot_running':True},
            'github_queue':{'observed_at':when,'statuses':sorted(route.QUEUE_STATES),'complete':True,'runs':[]},
            'public_health':{'observed_at':when,'checks':[
                {'url':'https://www.uaart.com.ua/video/index.html','status':200},
                {'url':'https://www.uaart.com.ua/video/katalog.html','status':200}]},
            'full_crm_acceptance':False,'publication_repair_installed':False}

    def tearDown(self):
        for p in self.root.rglob('*'):
            relative = p.relative_to(self.root).as_posix()
            if (p.is_file() or p.is_symlink()) and relative not in self.original:
                p.unlink()
        for relative,payload in self.original.items():
            path=self.root/relative
            if path.is_symlink(): path.unlink()
            if not path.exists() or path.read_bytes()!=payload: path.write_bytes(payload)

    def propose(self, **changes):
        return route.propose(self.root,self.evidence,self.main,now=self.now,
                             owner_command=changes.get('owner_command',route.COMMAND))

    def test_proposal_does_not_mutate_inputs_and_preserves_exact_history(self):
        result=self.propose(); changes=result['changes']
        self.assertEqual(len(changes),9)
        self.assertIsNone(changes[route.HALT])
        for name in ('halt','transaction','claim'):
            old={'halt':route.HALT,'transaction':route.TRANSACTION,'claim':route.CLAIM}[name]
            self.assertEqual(changes[route.HISTORY+'/'+name+'.json'],self.original[old])
        for relative,payload in self.original.items():
            self.assertEqual((self.root/relative).read_bytes(),payload)

    def test_apply_only_proposed_bytes_passes_existing_guards_without_rollback_replay(self):
        changes=self.propose()['changes']
        for path,payload in changes.items():
            target=self.root/path
            if payload is None: target.unlink()
            else:
                target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(payload)
        runtime=route.parsed(self.root,'state/AUTOPILOT_RUNTIME_MANIFEST.json')
        cp=route.bound_module(self.root,'automation/control_plane.py','reconciled_cp_test',runtime)
        dog=route.bound_module(self.root,'automation/transaction_watchdog.py','reconciled_dog_test',runtime)
        self.assertEqual(cp.verify_execution_mode(root=self.root,required_mode='AUTOMATIC')['status'],'PASS')
        self.assertEqual(dog.assert_clear(root=self.root)['status'],'PASS')
        receipt=route.parsed(self.root,route.RECEIPT)
        self.assertFalse(receipt['full_crm_acceptance'])
        self.assertFalse(receipt['publication_repair_installed'])
        self.assertFalse(receipt['rollback_performed'])
        self.assertEqual(cp.validate_receipt(receipt,route.parsed(self.root,route.REQUEST),route.REQ_SHA,route.RUN),receipt)
        with self.assertRaises(Exception): self.propose()
        for relative,payload in self.original.items():
            if relative.startswith(('state/autostart_','tasks/launch/','tasks/approvals/')):
                self.assertEqual((self.root/relative).read_bytes(),payload)

    def test_each_bad_evidence_is_rejected_before_any_change(self):
        cases=[
            ('backup corruption',lambda e:e['remote']['backup_mismatches'].append('before/db.py')),
            ('db backup corruption',lambda e:e['remote'].__setitem__('backup_database_matches',False)),
            ('source drift',lambda e:e['remote']['code_sha256'].__setitem__('cars_ui.py','0'*64)),
            ('protected source drift',lambda e:e['remote']['protected_mismatches'].append('start_safe.py')),
            ('rollback may have run',lambda e:e['remote'].__setitem__('rollback_receipt_exists',True)),
            ('wrong run',lambda e:e['remote']['receipts']['install'].__setitem__('run_id','0')),
            ('incomplete install',lambda e:e['remote']['receipts']['install'].__setitem__('safe_to_stop',False)),
            ('unverified db',lambda e:e['remote']['receipts']['verify'].__setitem__('crm_unchanged',False)),
            ('wrong backup',lambda e:e['remote']['receipts']['backup'].__setitem__('backup_manifest_sha256','0'*64)),
            ('incomplete journal',lambda e:e['remote']['install_journal'].__setitem__('stage','APPLYING')),
            ('other writer',lambda e:e['processes']['commands'].append('python3 installer.py')),
            ('stopped bot',lambda e:e['processes'].__setitem__('bot_running',False)),
            ('incomplete queue',lambda e:e['github_queue'].__setitem__('complete',False)),
            ('active workflow',lambda e:e['github_queue']['runs'].append({'id':1})),
            ('wrong owner',lambda e:e.__setitem__('owner_actor_id','0')),
            ('wrong main',lambda e:e.__setitem__('expected_main','c'*40)),
            ('false acceptance',lambda e:e.__setitem__('full_crm_acceptance',True)),
            ('false installed claim',lambda e:e.__setitem__('publication_repair_installed',True)),
            ('public unavailable',lambda e:e['public_health']['checks'][0].__setitem__('status',503)),
            ('stale remote',lambda e:e['remote'].__setitem__('observed_at','2026-09-26T00:00:00+00:00')),
        ]
        good=copy.deepcopy(self.evidence)
        for name,mutate in cases:
            with self.subTest(name=name):
                self.evidence=copy.deepcopy(good); mutate(self.evidence)
                with self.assertRaises(route.ReconciliationError): self.propose()
                self.assertEqual((self.root/route.HALT).read_bytes(),self.original[route.HALT])
                self.assertFalse((self.root/route.RECEIPT).exists())

    def test_owner_command_is_required(self):
        with self.assertRaisesRegex(route.ReconciliationError,'OWNER_COMMAND'):
            self.propose(owner_command='')

    def test_changed_runtime_is_rejected(self):
        path=self.root/'automation/control_plane.py'; path.write_bytes(path.read_bytes()+b'\n')
        with self.assertRaisesRegex(route.ReconciliationError,'RUNTIME_CHANGED'): self.propose()

    def test_changed_halt_identity_is_rejected(self):
        value=route.parsed(self.root,route.HALT);value['task_id']='other'
        (self.root/route.HALT).write_bytes(route.encode(value))
        with self.assertRaises(route.ReconciliationError): self.propose()

    def test_existing_archive_is_not_overwritten(self):
        path=self.root/(route.HISTORY+'/halt.json');path.parent.mkdir(parents=True,exist_ok=True);path.write_text('old evidence')
        with self.assertRaisesRegex(route.ReconciliationError,'ALREADY_RECONCILED'): self.propose()


if __name__=='__main__': unittest.main()
