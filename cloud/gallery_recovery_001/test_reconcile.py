import copy
import datetime as dt
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import reconcile as r

ROOT=Path(__file__).resolve().parents[2]

class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for name in (r.SOURCE,r.REGISTRATION,r.REQUEST,r.HALT,r.TX,r.CLAIM,
                     'state/AUTOPILOT_RUNTIME_MANIFEST.json',
                     'cloud/gallery_desktop_001/deployment_remote.py',
                     'cloud/gallery_desktop_001/deployment_controller.py'):
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
        self.e=json.loads((Path(__file__).parent/'observation.json').read_bytes())
        self.e.update(expected_parent='reviewed-parent',original_state_sha256={p:r.sha((self.root/p).read_bytes()) for p in (r.HALT,r.TX,r.CLAIM)})
        self.now=dt.datetime.now(dt.timezone.utc)

    def proposal(self):
        return r.propose(self.root,self.e,'reviewed-parent',self.now)

    def test_proposal_preserves_originals_and_no_application_writes(self):
        before={p:(self.root/p).read_bytes() for p in (r.HALT,r.TX,r.CLAIM)}
        writes=self.proposal()
        self.assertEqual(len(writes),8)
        self.assertIsNone(writes[r.HALT])
        for name,path in [('halt',r.HALT),('transaction',r.TX),('claim',r.CLAIM)]:
            self.assertEqual(writes[r.HISTORY+'/'+name+'.json'],before[path])
            self.assertEqual((self.root/path).read_bytes(),before[path])
        decision=json.loads(writes[r.DECISION])
        self.assertEqual(decision['application_writes'],0)
        self.assertFalse(decision['production_install_controller_executed'])
        self.assertFalse(decision['production_rollback_controller_executed'])
        self.assertTrue(all(p.startswith('state/') for p in writes))

    def test_no_claim_of_successful_install_or_rollback(self):
        writes=self.proposal();decision=json.loads(writes[r.DECISION])
        self.assertEqual(decision['semantic_outcome'],'ABORTED_DURING_BACKUP_BEFORE_APPLICATION_WRITE')
        self.assertEqual(json.loads(writes[r.CLAIM])['task_execution_status'],'FAILED')
        self.assertFalse(any('/receipts/' in p for p in writes))

    def test_executed_application_stage_is_rejected(self):
        for suffix in ('open','controller_production','controller_nonproduction','rollback_execute','finalize'):
            with self.subTest(stage=suffix):
                e=copy.deepcopy(self.e)
                next(j for j in e['jobs'] if j['name']=='execute / critical / '+suffix)['conclusion']='success'
                with self.assertRaisesRegex(ValueError,'WRITE_STAGE_EXECUTED'):
                    r.validate_observation(e)

    def test_nonterminal_or_wrong_workflow_rejected(self):
        for key,value in [('id',123),('head_sha','other'),('status','in_progress'),('conclusion','success')]:
            with self.subTest(key=key):
                e=copy.deepcopy(self.e);e['workflow_run'][key]=value
                with self.assertRaises(ValueError):r.validate_observation(e)

    def test_state_drift_rejected_without_output(self):
        for path in (r.HALT,r.TX,r.CLAIM):
            with self.subTest(path=path):
                p=self.root/path;original=p.read_bytes();p.write_bytes(original+b' ')
                with self.assertRaisesRegex(ValueError,'STATE_DRIFT'):self.proposal()
                p.write_bytes(original)

    def test_opened_boundary_rejected(self):
        p=self.root/r.TX;tx=json.loads(p.read_bytes());tx['backup_manifest_sha256']='a'*64
        p.write_bytes(r.canonical(tx));self.e['original_state_sha256'][r.TX]=r.sha(p.read_bytes())
        with self.assertRaisesRegex(ValueError,'WRITE_CREDENTIAL_BOUNDARY'):self.proposal()

    def test_unregistered_route_or_changed_code_rejected(self):
        (self.root/r.SOURCE).write_bytes(b'changed route')
        with self.assertRaisesRegex(ValueError,'UNREGISTERED_ROUTE'):self.proposal()

    def test_replay_archive_collision_rejected(self):
        p=self.root/r.DECISION;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
        with self.assertRaisesRegex(ValueError,'RECONCILIATION_ALREADY_EXISTS'):self.proposal()

if __name__=='__main__':unittest.main()
