import copy
import datetime as dt
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import reconcile_r4 as r

ROOT = Path(__file__).resolve().parents[2]
NOW = dt.datetime(2026, 9, 27, 10, 0, tzinfo=dt.timezone.utc)


def fixture():
    resume = {'id': 266084, 'enabled': True, 'state': 'running'}
    server = dict(observed_at=NOW.isoformat(), verifier_sha256=r.VERIFIER,
                  backup_sha256=r.BACKUP, plan_sha256=r.PLAN, publisher_sha256=r.ORIGINAL,
                  backup_and_before_files_verified=True, protected_file_count=19,
                  journals={}, receipts={})
    for mode, error in [('install', 'TransportError:HTTP_502'), ('rollback', 'TransportError:BOT_STATE_TIMEOUT')]:
        result = dict(status='FAIL', error=error, crm_resume=resume)
        server['journals'][mode] = dict(backup_sha256=r.BACKUP, mode=mode, stage='FINISHED', result=result)
        server['receipts'][mode] = dict(result, run_id=r.RUN, mode=mode, safe_to_stop=True,
                                       crm_write=False, plan_sha256=r.PLAN, backup_manifest_sha256=r.BACKUP)
    return dict(expected_parent='a'*40, original_state_sha256={p:r.sha((ROOT/p).read_bytes()) for p in (r.HALT,r.TX,r.CLAIM)},
                server=server, queue=dict(observed_at=NOW.isoformat(), statuses_checked=['action_required','in_progress','pending','queued','waiting'], active_runs=[]),
                supervisor=dict(observed_at=NOW.isoformat(),bot_id=266084,enabled=True,state='Running',active_processes=['monitor','start_safe']),
                public=dict(observed_at=NOW.isoformat(),urls=['https://www.uaart.com.ua/video/index.html','https://www.uaart.com.ua/video/katalog.html'],status_codes=[200,200]))


class RecoveryTests(unittest.TestCase):
    def test_valid_observation(self):
        r.validate_observation(fixture(), NOW)

    def test_rejects_unsafe_and_stale_observations(self):
        mutations = [
            lambda e:e['server'].update(observed_at=(NOW-dt.timedelta(seconds=181)).isoformat()),
            lambda e:e['server'].update(observed_at=(NOW+dt.timedelta(seconds=1)).isoformat()),
            lambda e:e['server'].update(verifier_sha256='0'*64),
            lambda e:e['server'].update(backup_sha256='0'*64),
            lambda e:e['server'].update(publisher_sha256='0'*64),
            lambda e:e['server'].update(backup_and_before_files_verified=False),
            lambda e:e['server'].update(protected_file_count=18),
            lambda e:e['server']['journals']['install'].update(data_before={}),
            lambda e:e['server']['journals']['install'].update(stage='APPLYING'),
            lambda e:e['server']['journals']['rollback']['result'].update(restored=True),
            lambda e:e['server']['receipts']['install'].update(safe_to_stop=False),
            lambda e:e['server']['receipts']['rollback'].update(status='PASS'),
            lambda e:e['server']['receipts']['rollback'].update(run_id='1'),
            lambda e:e['server']['receipts']['install'].update(plan_sha256='0'*64),
            lambda e:e['queue'].update(active_runs=[123]),
            lambda e:e['queue'].update(statuses_checked=['in_progress']),
            lambda e:e['supervisor'].update(state='Stopping'),
            lambda e:e['supervisor'].update(active_processes=['monitor','start_safe','installer']),
            lambda e:e['public'].update(status_codes=[200,502]),
        ]
        for change in mutations:
            with self.subTest(change=mutations.index(change)):
                e=fixture();change(e)
                with self.assertRaises(ValueError):r.validate_observation(e,NOW)

    def test_proposal_preserves_failures_and_unchanged_validators(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'repo'
            shutil.copytree(ROOT,root,ignore=shutil.ignore_patterns('.git','__pycache__'))
            e=fixture();before={p:(root/p).read_bytes() for p in (r.HALT,r.TX,r.CLAIM)}
            for p in ('automation/control_plane.py','automation/transaction_watchdog.py',
                      'state/AUTOPILOT_RUNTIME_MANIFEST.json',r.REQUEST):
                before[p]=(root/p).read_bytes()
            writes=r.propose(root,e,'a'*40,NOW)
            self.assertEqual(len(writes),8)
            self.assertIsNone(writes[r.HALT])
            self.assertEqual(writes[r.HISTORY+'/claim.json'],before[r.CLAIM])
            decision=json.loads(writes[r.DECISION])
            self.assertFalse(decision['production_rollback_executed_successfully'])
            self.assertFalse(decision['application_installation_completed'])
            for p,value in writes.items():
                path=root/p
                if value is None:path.unlink()
                else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
            self.assertEqual(json.loads((root/r.CLAIM).read_bytes())['failure_history'],json.loads(before[r.CLAIM])['failure_history'])
            for p,b in before.items():
                if p not in (r.HALT,r.TX,r.CLAIM):self.assertEqual((root/p).read_bytes(),b)
            for command in [ ['python','-I','automation/transaction_watchdog.py','assert-clear'],
                             ['python','-I','automation/control_plane.py','verify-mode','--require','AUTOMATIC'] ]:
                result=subprocess.run(command,cwd=root,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            with self.assertRaises(ValueError):r.propose(root,e,'a'*40,NOW)

    def test_rejects_changed_main_or_original_state(self):
        with self.assertRaises(ValueError):r.propose(ROOT,fixture(),'b'*40,NOW)
        e=fixture();e['original_state_sha256'][r.CLAIM]='0'*64
        with self.assertRaises(ValueError):r.propose(ROOT,e,'a'*40,NOW)


if __name__=='__main__':unittest.main()
