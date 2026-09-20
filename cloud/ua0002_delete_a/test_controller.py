#!/usr/bin/env python3
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('stage_a_adapter_controller',HERE/'controller.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)

def worker_result(operation='install_verify'):
    return {'operation':operation,'plan_sha256':'a'*64,'status':'PASS','safe_to_stop':True,
        'crm_resume':{'id':266084,'enabled':True,'state':'Running'},
        'installer':{'status':'PASS','operation':operation,'plan_sha256':'a'*64,'target_absent':True,
        'source_checksum_pass':True,'integrity_pass':True,'backup_manifest_sha256':'b'*64,
        'post_check_pass':True,'target_retired_local':True,'database_unchanged':True,
        'other_pages_unchanged':True,'media_mutations':0,'rollback_policy':'FORWARD_RETIREMENT_ONLY'}}

class Response:
    def __init__(self,url,status=200,payload=b'unchanged'):
        self.url,self.status,self.payload=url,status,payload
    def geturl(self):return self.url
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,size):return self.payload[:size]

class ControllerContractTests(unittest.TestCase):
    def test_remote_scope_refuses_production_upload_delete_or_results_write(self):
        api=c.API('test-token','123')
        for method,path in [('POST','files/path/home/Carix/cars_ui.py'),('DELETE','always_on/'),
            ('PATCH','always_on/266084/'),('POST','files/path'+api.folder+'/install_verify-result.json')]:
            with self.assertRaises(c.AdapterError):api.request(method,path)
    def test_redirect_always_refused(self):
        with self.assertRaises(c.AdapterError):c.NoRedirect().redirect_request(None,None,302,'',{},c.BASE)
    def test_not_ready_pack_refused_before_transport(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'tasks/requests').mkdir(parents=True);(root/'tasks/manifests').mkdir()
            manifest={'readiness':'NOT_READY'};mh=c.sha(c.canonical(manifest))
            request={'task_id':c.TASK_ID,'production_required':True,'critical':{'manifest_path':'tasks/manifests/'+c.TASK_ID+'.json','manifest_sha256':mh,'gate_b_authorized':True}}
            rp=root/'tasks/requests'/f'{c.TASK_ID}.json';rp.write_bytes(c.canonical(request))
            (root/'tasks/manifests'/f'{c.TASK_ID}.json').write_bytes(c.canonical(manifest))
            env={'PYTHONANYWHERE_API_TOKEN':'test-token','UAART_REQUEST_PATH':str(rp.relative_to(root)),
                'UAART_REQUEST_SHA256':c.sha(rp.read_bytes()),'UAART_TASK_ID':c.TASK_ID,'UAART_TASK_CLASS':'CRITICAL',
                'UAART_RUN_ID':'123','UAART_TRANSACTION_ID':'tx-test','UAART_MANIFEST_SHA256':mh}
            with self.assertRaisesRegex(c.AdapterError,'PACK_NOT_READY'):c.load(env,root)
    def test_final_state_requires_target_absence_db_and_other_pages(self):
        for key in ('target_absent','post_check_pass','target_retired_local','database_unchanged','other_pages_unchanged','integrity_pass'):
            value=worker_result();value['installer'][key]=False
            with self.assertRaises(c.AdapterError):c.validate_result(value,'a'*64,'install_verify')
    def test_nonterminal_and_unresumed_rejected(self):
        for key in ('safe_to_stop','status'):
            value=worker_result();value[key]=False
            with self.assertRaises(c.AdapterError):c.validate_result(value,'a'*64,'install_verify')
        value=worker_result();value['crm_resume']['enabled']=False
        with self.assertRaises(c.AdapterError):c.validate_result(value,'a'*64,'install_verify')
    def test_forward_recovery_can_prove_completed_desired_state(self):
        value=worker_result();value['status']='FAIL';value['forward_recovery']=value.pop('installer')
        value['forward_recovery']['operation']='recover';value['error']='KnownRetirementError:private_detail'
        installed=c.validate_result(value,'a'*64,'install_verify')
        self.assertTrue(installed['_controller_recovery_performed'])
        self.assertEqual(installed['_controller_initial_error_code'],'KnownRetirementError')
        self.assertNotIn('private_detail',json.dumps(installed))
    def test_exact_terminal_failure_cleanup_never_becomes_success(self):
        plan={'test':True};plan_sha=c.sha(c.canonical(plan))
        for state in ('terminal_failure','nonterminal','wrong_identity'):
            value={'plan_sha256':plan_sha,'operation':'install_verify','safe_to_stop':True,'status':'FAIL'}
            if state=='nonterminal':value['safe_to_stop']=False
            if state=='wrong_identity':value['plan_sha256']='0'*64
            class Fake:
                folder=c.REMOTE_ROOT+'123'
                def __init__(self):self.results=[None,c.canonical(value)];self.stopped=[]
                def upload_new(self,*args):pass
                def read(self,*args):return self.results.pop(0)
                def trigger(self,*args):return 999
                def stop_owned(self,*args):self.stopped.append(args)
            api=Fake()
            with patch.object(c,'FILES',()):
                with self.assertRaises(c.AdapterError):
                    c.remote({'UAART_RUN_ID':'123','PYTHONANYWHERE_API_TOKEN':'unused'}, {'execution':{'file_sha256':{}}},plan,'install_verify',api=api)
            self.assertEqual(len(api.stopped),1 if state=='terminal_failure' else 0)
    def test_rollback_republication_policy_is_rejected(self):
        value=worker_result('rollback');value['installer']['rollback_policy']='RESTORE_OLD_LISTING'
        with self.assertRaisesRegex(c.AdapterError,'SOLD_REPUBLICATION_POLICY_REFUSED'):c.validate_result(value,'a'*64,'rollback')
    def test_receipt_cannot_pass_without_public_acceptance(self):
        values={'UAART_REQUEST_SHA256':'a'*64,'UAART_RUN_ID':'123','UAART_TRANSACTION_ID':'tx-test','UAART_MANIFEST_SHA256':'c'*64}
        installed=worker_result()['installer']
        with self.assertRaisesRegex(c.AdapterError,'PUBLIC_ACCEPTANCE_REQUIRED'):c.receipt_value(values,installed,'rollback',[])
        receipt=c.receipt_value(values,installed,'rollback',[{'status':404}])
        self.assertTrue(receipt['restored']);self.assertTrue(receipt['crm_unchanged'])
    def test_public_acceptance_rejects_live_sold_card(self):
        proof={'absent':['video/UA-0002.html','video/UA-0002-diag.html'],
            'shared_sha256':{name:c.sha(b'unchanged') for name in ('video/index.html','video/katalog.html','video/sitemap.xml')}}
        class Bad:
            def open(self,request,timeout):return Response(request.full_url)
        with self.assertRaisesRegex(c.AdapterError,'SOLD_TARGET_STILL_PUBLIC'):c.verify_public(proof,'123',Bad())
        class Good:
            def open(self,request,timeout):
                if 'UA-0002' in request.full_url:raise urllib.error.HTTPError(request.full_url,410,'gone',{},None)
                return Response(request.full_url)
        checks=c.verify_public(proof,'123',Good());self.assertEqual(len(checks),5)
    def test_public_wrong_shared_bytes_and_cross_target_refused(self):
        proof={'absent':['video/UA-0002.html','video/UA-0002-diag.html','video/UA-0003.html'],
            'shared_sha256':{name:c.sha(b'unchanged') for name in ('video/index.html','video/katalog.html','video/sitemap.xml')}}
        with self.assertRaisesRegex(c.AdapterError,'RETIRED_PATH_SCOPE'):c.verify_public(proof,'123')

if __name__=='__main__':unittest.main()
