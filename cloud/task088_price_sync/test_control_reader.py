"""Isolated authenticated-reader contracts; no real tokens or network calls."""
import base64
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import uaart_price_control_reader as reader


def git_sha(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()


class FakeGitHub:
    def __init__(self, files):
        self.files=files;self.calls=[];self.head="1"*40;self.tree="2"*40
        self.truncated=False;self.halt=False;self.error=None;self.change_final=False
    def get(self,path):
        self.calls.append(path)
        if self.error:raise reader.ReaderError(self.error)
        if path=="/git/ref/heads/main":
            count=self.calls.count(path)
            return {"ref":"refs/heads/main","object":{"type":"commit","sha":"3"*40 if self.change_final and count>1 else self.head}}
        if path=="/git/commits/"+self.head:return {"sha":self.head,"tree":{"sha":self.tree}}
        if path=="/git/trees/"+self.tree+"?recursive=1":
            entries=[{"path":key,"sha":git_sha(raw),"mode":"100644","type":"blob"} for key,raw in self.files.items()]
            if self.halt:entries.append({"path":reader.HALT,"sha":"f"*40,"mode":"100644","type":"blob"})
            return {"sha":self.tree,"truncated":self.truncated,"tree":entries}
        if path.startswith("/git/blobs/"):
            wanted=path.rsplit("/",1)[-1]
            raw=next(raw for raw in self.files.values() if git_sha(raw)==wanted)
            return {"sha":wanted,"encoding":"base64","content":base64.b64encode(raw).decode()}
        raise AssertionError("Unexpected test endpoint")


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/"private").mkdir(mode=0o700);(self.root/"cache").mkdir(mode=0o700)
        self.now=1000000
        task="TASK088-GE-PRICE-SITE-STAGE3-READER-TEST"
        # TEST-only canonical verifier scaffolding. The real canonical verifier
        # receives its own independent integration check below.
        verifier=b'''import json\ndef verify_execution_mode(*,root,required_mode):
 m=json.loads((root/'state/EXECUTION_MODE.json').read_bytes())
 assert (root/'state/MANUAL_MODE.md').read_text()=='INACTIVE'
 assert not (root/'state/AUTOPILOT_HALT.json').exists()
 assert m['mode']==required_mode and m['automatic_production'] is True
 return dict(status='PASS',mode=m['mode'],automatic_production=True)
'''
        self.files={reader.VERIFIER:verifier,reader.MODE:reader.encode({"mode":"AUTOMATIC","automatic_production":True}),
                    reader.MANUAL:b"INACTIVE","tasks/manifests/test.json":reader.encode({"price_event_delegation_sha256":"a"*64}),
                    "tasks/requests/test.json":reader.encode({"task_id":task}),"tasks/approvals/test.json":b'{"test_only":true}',
                    "tasks/gates/test.json":b'{"test_only":true}'}
        self.config={"contract":reader.CONTRACT,"root":str(self.root),"environment":"TEST",
                     "repository":reader.REPOSITORY,"ref":"refs/heads/main","task_id":task,"delegation_sha256":"a"*64,
                     "source":"github:"+reader.REPOSITORY+":main","max_age_ms":30000,"poll_interval_ms":10000,
                     "canonical_file_pins":{path:reader.sha(raw) for path,raw in self.files.items()},
                     "price_artifacts":{"manifest":"tasks/manifests/test.json","request":"tasks/requests/test.json",
                                        "owner_approval":"tasks/approvals/test.json","gate_b":"tasks/gates/test.json"},
                     "token_file":"private/github_reader_token","state_path":"private/control_state.json",
                     "freshness_path":"private/control_stamp.json","cache_dir":"cache"}
        self.config_path=self.root/"private/reader.json";self.write_config()
        self.api=FakeGitHub(self.files)
    def tearDown(self):self.temp.cleanup()
    def write_config(self):
        raw=reader.encode(self.config);self.config_path.write_bytes(raw);self.config_path.chmod(0o600)
        self.config_sha=reader.sha(raw)
    def instance(self):
        return reader.Reader(self.config_path,self.config_sha,test_root=self.root,test_api=self.api,clock=lambda:self.now)
    def stamp(self):return json.loads((self.root/"private/control_stamp.json").read_bytes())
    def test_complete_authenticated_tree_and_real_fresh_ref_produce_bound_cache(self):
        result=self.instance().tick();self.assertEqual(result["status"],"OBSERVED")
        self.assertFalse(result["production_authorized"])
        state=(self.root/"private/control_state.json").read_bytes()
        facts={kind:{"path":str(self.root/"private/control_state.json"),"sha256":reader.sha(state),"value":value}
               for kind,value in (("mode","AUTOMATIC"),("halt",False),("revocation",False))}
        self.assertEqual(self.stamp()["observations_sha256"],reader.sha(reader.encode(facts)))
        self.assertEqual(self.api.calls.count('/git/ref/heads/main'),2)
        self.assertEqual(self.stamp()["reader_config_sha256"],self.config_sha)
    def test_halt_presence_revokes_previous_fresh_stamp_immediately(self):
        worker=self.instance();self.assertEqual(worker.tick()["status"],"OBSERVED")
        self.api.halt=True
        self.assertEqual(worker.tick()["reason"],"CANONICAL_HALT_PRESENT")
        self.assertNotIn("observed_ms",self.stamp())
    def test_404_is_never_halt_clearance_or_anonymous_fallback(self):
        self.api.error="GITHUB_HTTP_404"
        result=self.instance().tick()
        self.assertEqual(result["status"],"BLOCKED");self.assertNotIn("observed_ms",self.stamp())
        self.assertEqual(len(self.api.calls),1)
    def test_truncated_tree_cannot_prove_halt_absence(self):
        self.api.truncated=True
        self.assertEqual(self.instance().tick()["reason"],"COMPLETE_AUTHORITATIVE_TREE_REQUIRED")
    def test_unpinned_remote_workflow_cannot_be_hidden_from_canonical_inventory(self):
        self.files['.github/workflows/unreviewed.yml']=b'name: unreviewed\n'
        self.assertEqual(self.instance().tick()["reason"],"COMPLETE_CANONICAL_WORKFLOW_SET_REQUIRED")
    def test_changed_main_ref_invalidates_completed_local_validation(self):
        self.api.change_final=True
        self.assertEqual(self.instance().tick()["reason"],"MAIN_CHANGED_DURING_OBSERVATION")
    def test_approval_content_drift_or_removal_blocks(self):
        worker=self.instance();self.files['tasks/approvals/test.json']=b'{"revoked":true}'
        self.assertEqual(worker.tick()["reason"],"CANONICAL_APPROVAL_OR_CONTROL_DRIFT")
        del self.files['tasks/approvals/test.json']
        self.assertEqual(worker.tick()["reason"],"CANONICAL_APPROVAL_OR_CONTROL_REMOVED")
    def test_manual_marker_is_checked_by_canonical_verifier_even_when_rehashed(self):
        self.files[reader.MANUAL]=b'ACTIVE';self.config['canonical_file_pins'][reader.MANUAL]=reader.sha(b'ACTIVE');self.write_config()
        self.assertEqual(self.instance().tick()["reason"],"CANONICAL_EXECUTION_MODE_REJECTED")
    def test_corrupted_cached_immutable_blob_cannot_be_reused(self):
        worker=self.instance();self.assertEqual(worker.tick()["status"],"OBSERVED")
        (self.root/'cache'/ (git_sha(self.files[reader.MODE])+'.blob')).write_bytes(b'changed')
        self.assertEqual(worker.tick()["reason"],"CANONICAL_GIT_BLOB_HASH_MISMATCH")
    def test_cached_blobs_never_replace_a_fresh_main_read(self):
        worker=self.instance();worker.tick();self.api.calls=[];self.now+=10000
        self.assertEqual(worker.tick()["status"],"OBSERVED")
        self.assertEqual(self.api.calls.count('/git/ref/heads/main'),2)
        self.assertFalse(any('/git/blobs/' in call for call in self.api.calls))
    def test_expired_final_read_cannot_renew_stamp(self):
        original=self.api.get
        def slow(path):
            result=original(path)
            if path=='/git/ref/heads/main' and self.api.calls.count(path)==2:self.now+=31000
            return result
        self.api.get=slow
        self.assertEqual(self.instance().tick()["reason"],"CANONICAL_OBSERVATION_EXPIRED")
    def test_reader_config_drift_is_rejected_before_new_network_reads(self):
        worker=self.instance();self.config_path.write_bytes(b'{}')
        self.assertEqual(worker.tick()["reason"],"INSTALLER_READER_CONFIG_CHANGED")
        self.assertEqual(self.api.calls,[])
    def test_public_output_location_and_symlink_are_rejected(self):
        self.config['state_path']='video/state.json';self.write_config()
        with self.assertRaises(reader.ReaderError):self.instance()
        self.config['state_path']='private/control_state.json';self.write_config()
        (self.root/'private/control_state.json').symlink_to(self.root/'elsewhere')
        with self.assertRaisesRegex(reader.ReaderError,'SYMLINK'):self.instance()
    def test_cache_outputs_cannot_overwrite_config_or_share_a_credential_directory(self):
        self.config['state_path']='private/reader.json';self.write_config()
        with self.assertRaisesRegex(reader.ReaderError,'DISTINCT_PRIVATE'):self.instance()
        self.config['state_path']='private/control_state.json'
        self.config['token_file']='cache/token';self.write_config()
        with self.assertRaisesRegex(reader.ReaderError,'DISTINCT_PRIVATE'):self.instance()
    def test_duplicate_json_keys_cannot_override_control(self):
        with self.assertRaisesRegex(reader.ReaderError,'DUPLICATE_JSON_KEY'):
            reader.parse(b'{"mode":"MANUAL","mode":"AUTOMATIC"}')
    def test_missing_credential_never_starts_anonymous_network(self):
        client=reader.GitHub(self.root/'private/missing_token')
        with patch.object(client.opener,'open') as network:
            with self.assertRaises(FileNotFoundError):client.get('/git/ref/heads/main')
            network.assert_not_called()
    def test_client_only_uses_authenticated_get_to_exact_repository(self):
        path=self.root/'private/token';path.write_bytes(b'test_only_not_a_real_credential');path.chmod(0o600)
        client=reader.GitHub(path)
        seen=[]
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return b'{"object":{}}'
        def open_(request,**kwargs):seen.append(request);return Response()
        with patch.object(client.opener,'open',side_effect=open_):client.get('/git/ref/heads/main')
        self.assertEqual(seen[0].get_method(),'GET')
        self.assertEqual(seen[0].full_url,'https://api.github.com/repos/'+reader.REPOSITORY+'/git/ref/heads/main')
        self.assertTrue(seen[0].get_header('Authorization').startswith('Bearer '))
        with self.assertRaisesRegex(reader.ReaderError,'ENDPOINT_NOT_ALLOWED'):client.get('/issues')
    def test_redirect_does_not_forward_credential(self):
        with self.assertRaisesRegex(reader.ReaderError,'REDIRECT_FORBIDDEN'):
            reader.NoRedirect().redirect_request(None,None,302,'m',{},'https://foreign.test')


class RealCanonicalVerifierTest(unittest.TestCase):
    VERIFIED_STAGE2_BASELINE='0c85a6561d80c4d8789b3a482ae41cdaf9d0f667'
    def setUp(self):
        # A working tree may contain an as-yet unapproved workflow change. That
        # must not be treated as activated runtime. Test against the immutable
        # Stage 2 closing commit, then independently exercise drift rejection.
        # Missing baseline objects fail this test; CI must fetch its history.
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        repository=Path(__file__).resolve().parents[2]
        archive=subprocess.run(['git','archive',self.VERIFIED_STAGE2_BASELINE,'automation','state','tasks',
            '.github/workflows','cloud/task088_crm_preflight','cloud/task_088_ge_price_crm_stage1'],
            cwd=repository,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            for member in source.getmembers():
                path=reader.local(self.root,member.name.rstrip('/'))
                if member.isdir():path.mkdir(parents=True,exist_ok=True)
                elif member.isfile():
                    path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_bytes(source.extractfile(member).read())
                else:raise AssertionError('Canonical snapshot must contain regular files only')
        self.pin=reader.sha((self.root/reader.VERIFIER).read_bytes())
    def tearDown(self):self.temp.cleanup()
    def test_existing_committed_verifier_runs_without_substitute_flags(self):
        result=reader.verify_canonical(self.root,self.pin)
        self.assertEqual(result['mode'],'AUTOMATIC')
        self.assertIs(result['automatic_production'],True)
    def test_real_verifier_rejects_runtime_workflow_drift(self):
        path=self.root/'.github/workflows/uaart_critical.yml'
        path.write_bytes(path.read_bytes()+b'\n# unactivated change\n')
        with self.assertRaisesRegex(reader.ReaderError,'CANONICAL_EXECUTION_MODE_REJECTED'):
            reader.verify_canonical(self.root,self.pin)
    def test_real_verifier_rejects_manual_marker_and_halt(self):
        (self.root/reader.HALT).write_text('{}')
        with self.assertRaisesRegex(reader.ReaderError,'CANONICAL_EXECUTION_MODE_REJECTED'):
            reader.verify_canonical(self.root,self.pin)
        (self.root/reader.HALT).unlink()
        (self.root/reader.MANUAL).write_text('Status: ACTIVE\n')
        with self.assertRaisesRegex(reader.ReaderError,'CANONICAL_EXECUTION_MODE_REJECTED'):
            reader.verify_canonical(self.root,self.pin)


class BindingReaderIntegrationTests(unittest.TestCase):
    """Real v5 binding consumes the reader's output in an isolated TEST root."""
    import test_binding as fixtures
    put = fixtures.BindingTests.put
    rebuild_chain = fixtures.BindingTests.rebuild_chain
    provider = fixtures.BindingTests.provider
    authorize = fixtures.BindingTests.authorize
    provenance = fixtures.BindingV5Tests.provenance
    new_operation = fixtures.BindingV5Tests.new_operation
    tearDown = fixtures.BindingTests.tearDown

    def setUp(self):
        self.fixtures.BindingV5Tests.setUp(self)
        (self.root/'cache').mkdir(mode=0o700)
        source=Path(reader.__file__).read_bytes()
        (self.root/'uaart_price_control_reader.py').write_bytes(source)
        self.code['uaart_price_control_reader.py']=reader.sha(source)
        origin='github:'+reader.REPOSITORY+':main'
        self.controls.clear()
        self.controls.update(provenance='EXTERNAL_CACHE',
            observations={semantic:{'path':'private/control_state.json','format':'JSON_FIELD','field':[field]}
                          for semantic,field in (('mode','mode'),('halt','halt'),('revocation','revoked'))},
            freshness={'source':origin,'path':'private/control_stamp.json','max_age_ms':30000,
                       'reader_contract':reader.CONTRACT,'producer_path':'uaart_price_control_reader.py'})
        self.writers['control_contract_sha256']=reader.sha(reader.encode(self.controls))
        self.artifacts['writer_fences']=self.put('evidence/writers.json',self.writers)
        self.delegation['writer_fence_report_sha256']=self.artifacts['writer_fences']['sha256']
        self.rebuild_chain()
        # This fixture tests producer/consumer integration, not the canonical
        # policy itself; the committed real verifier is exercised above.
        self.files={reader.MODE:b'{"mode":"AUTOMATIC"}',reader.MANUAL:b'INACTIVE',
            reader.VERIFIER:b"def verify_execution_mode(*,root,required_mode):\n return dict(status='PASS',mode='AUTOMATIC',automatic_production=True)\n"}
        refs={name:self.artifacts[name]['path'] for name in ('manifest','request','owner_approval','gate_b')}
        self.files.update({path:(self.root/path).read_bytes() for path in refs.values()})
        config={'contract':reader.CONTRACT,'root':str(self.root),'environment':'TEST',
            'repository':reader.REPOSITORY,'ref':'refs/heads/main','task_id':self.task,
            'delegation_sha256':reader.sha(reader.encode(self.delegation)),'source':origin,
            'max_age_ms':30000,'poll_interval_ms':10000,
            'canonical_file_pins':{path:reader.sha(raw) for path,raw in self.files.items()},
            'price_artifacts':refs,'token_file':'private/github_reader_token',
            'state_path':'private/control_state.json','freshness_path':'private/control_stamp.json','cache_dir':'cache'}
        reference=self.put('private/reader.json',config)
        config=json.loads((self.root/'private/config.json').read_bytes())
        config['control_reader']=reference
        self.pin_binding(config)
        self.api=FakeGitHub(self.files)
        self.reader=reader.Reader(self.root/reference['path'],reference['sha256'],
                                  test_root=self.root,test_api=self.api,clock=lambda:self.now)
        self.assertEqual(self.reader.tick()['status'],'OBSERVED')

    def pin_binding(self,config):
        config_ref=self.put('private/config.json',config)
        self.anchor_ref=self.put('private/anchor.json',{'contract':self.fixtures.binding.ANCHOR_CONTRACT,
            'config_path':config_ref['path'],'config_sha256':config_ref['sha256']})

    def test_reader_observation_authorizes_actual_v5_claim_with_bounded_expiry(self):
        self.now+=25000
        proof=self.authorize()
        self.assertEqual(proof['operator_user_id'],700)
        self.assertEqual(proof['event_key'],self.event['event_key'])
        self.assertEqual(proof['expires_ms'],1000000+30000)

    def test_failed_refresh_invalidates_an_existing_authorization(self):
        provider=self.provider();self.authorize(provider)
        self.api.error='GITHUB_HTTP_404'
        self.assertEqual(self.reader.tick()['status'],'BLOCKED')
        with self.assertRaises(self.fixtures.binding.BindingError):self.authorize(provider)

    def test_rehashed_reader_for_another_delegation_cannot_authorize(self):
        config=json.loads((self.root/'private/config.json').read_bytes())
        value=json.loads((self.root/'private/reader.json').read_bytes())
        value['delegation_sha256']='e'*64
        config['control_reader']=self.put('private/reader.json',value)
        self.pin_binding(config)
        with self.assertRaisesRegex(self.fixtures.binding.BindingError,'CONTROL_READER_DELEGATION_MISMATCH'):
            self.provider()


if __name__=='__main__':unittest.main()
