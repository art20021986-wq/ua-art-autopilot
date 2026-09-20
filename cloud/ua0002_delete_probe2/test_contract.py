#!/usr/bin/env python3
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ua0002_probe2', HERE / 'controller.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

class Response:
    status = 200
    headers = {}
    def __init__(self, url, payload=b'pass\n'):
        self.url, self.payload = url, payload
    def geturl(self): return self.url
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, size):
        value, self.payload = self.payload[:size], self.payload[size:]
        return value

class Opener:
    def __init__(self): self.calls=[]
    def open(self, request, timeout):
        self.calls.append((request.get_method(),request.full_url,request.data))
        return Response(request.full_url)

class ContractTests(unittest.TestCase):
    def test_fixed_transport_refuses_unknown_and_database(self):
        op=Opener(); api=c.ReadOnlyAPI('test-value',opener=op)
        api.read('files/path/home/Carix/db.py')
        self.assertEqual(op.calls, [('GET',c.BASE+'files/path/home/Carix/db.py',None)])
        for endpoint in ('files/path/home/Carix/crm.db','files/path/home/Carix/.env','always_on/123/','schedule/123/','files/path/home/Carix/video/index.html','../secrets','https://evil.invalid/'):
            with self.assertRaises(c.ProbeError): api.read(endpoint)
        self.assertEqual(len(op.calls),1)
    def test_redirect_refused_even_same_origin(self):
        with self.assertRaises(c.ProbeError):
            c.RefuseRedirects().redirect_request(None,None,302,'',{},c.BASE+'always_on/')
    def test_size_and_response_origin_bound(self):
        class Wrong:
            def open(self, req, timeout): return Response('https://evil.invalid/')
        with self.assertRaises(c.ProbeError): c.ReadOnlyAPI('test-value',opener=Wrong()).read('always_on/')
        class Large:
            def open(self, req, timeout):
                r=Response(req.full_url);r.headers={'Content-Length':str(c.MAX_BYTES+1)};return r
        with self.assertRaises(c.ProbeError): c.ReadOnlyAPI('test-value',opener=Large()).read('always_on/')
    def test_credentials_omitted_globals_and_definitions(self):
        raw=b'API_TOKEN="global-private"\ndef delete_ok():\n    return "UA-0002"\ndef connect():\n    password="secret-private"\n    return password\ndef log_action(token="default-private"):\n    return token\n'
        facts,excerpt=c.inspect_source(raw,'/home/Carix/cars_ui.py')
        self.assertEqual(facts['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertIn('delete_ok',excerpt)
        for secret in ('global-private','secret-private','default-private'):
            self.assertNotIn(secret,excerpt)
            self.assertNotIn(secret,json.dumps(facts))
        self.assertEqual(sum(x['excerpt']=='OMITTED_SENSITIVE_LITERAL' for x in facts['definitions']),2)
    def test_only_selected_functions_and_whitelisted_classes(self):
        raw=b'def unrelated_business_function():\n    return "private_business_logic"\nclass ApplicationSecrets:\n    def connect(self):\n        return "class_business_logic"\ndef delete_ok():\n    return "selected_logic"\n'
        facts,excerpt=c.inspect_source(raw,'/home/Carix/cars_ui.py')
        self.assertIn('selected_logic',excerpt)
        self.assertNotIn('private_business_logic',excerpt)
        self.assertNotIn('class_business_logic',excerpt)
        self.assertEqual(sum(x['excerpt']=='OMITTED_NOT_SELECTED' for x in facts['definitions']),2)
        self.assertEqual(facts['definitions'][1]['methods'][0]['name'],'connect')
    def test_selected_class_is_file_scoped_and_secret_class_omitted(self):
        raw=b'class Soedinenie:\n    password="class-secret-private"\n    def execute(self):\n        return None\nclass _UaKursor:\n    def execute(self, sql):\n        return sql\nclass ApplicationSecrets:\n    def run(self):\n        return "unselected-private"\n'
        facts,excerpt=c.inspect_source(raw,'/home/Carix/db.py')
        self.assertNotIn('class-secret-private',excerpt)
        self.assertNotIn('unselected-private',excerpt)
        self.assertIn('class _UaKursor',excerpt)
        self.assertEqual(facts['definitions'][0]['excerpt'],'OMITTED_SENSITIVE_LITERAL')
        self.assertEqual(facts['definitions'][1]['excerpt'],'SANITIZED_AST_RENDERING')
        _,wrong_file=c.inspect_source(raw,'/home/Carix/start_safe.py')
        self.assertNotIn('class _UaKursor',wrong_file)
    def test_selected_class_secret_method_default_omitted(self):
        raw=b'class Soedinenie:\n    def connect(self, token="default-private"):\n        return token\n'
        facts,excerpt=c.inspect_source(raw,'/home/Carix/db.py')
        self.assertEqual(excerpt,'')
        self.assertEqual(facts['definitions'][0]['excerpt'],'OMITTED_SENSITIVE_LITERAL')
    def test_provider_commands_never_exported(self):
        raw=json.dumps([{'id':266084,'enabled':True,'state':'Running','command':'TOKEN=private-value python3.10 /home/Carix/start_safe.py'}]).encode()
        facts=c.inspect_tasks(raw)
        self.assertNotIn('private-value',json.dumps(facts))
        self.assertEqual(facts['tasks'][0]['known_modules'],['start_safe.py'])
        self.assertFalse(facts['os_processes_verified'])
    def test_schedule_only_exact_known_commands_and_safe_fields(self):
        known=sorted(c.KNOWN_SCHEDULE_COMMANDS)[0]
        raw=json.dumps([
            {'id':12,'command':known,'hour':8,'minute':2,'interval':'daily'},
            {'id':13,'command':known+' TOKEN=private-value','hour':'private-hour','minute':'private-minute','interval':'private-interval','description':'private-description'},
        ]).encode()
        facts=c.inspect_schedules(raw)
        self.assertEqual(facts['tasks'][0]['command'],known)
        self.assertEqual(facts['tasks'][0]['hour'],8)
        self.assertEqual(facts['tasks'][0]['minute'],2)
        self.assertEqual(facts['tasks'][0]['interval'],'daily')
        self.assertNotIn('command',facts['tasks'][1])
        self.assertFalse(facts['tasks'][1]['known_command'])
        self.assertNotIn('private-',json.dumps(facts))
        self.assertFalse(facts['os_processes_verified'])
        with self.assertRaises(c.ProbeError):c.inspect_schedules(b'{"unexpected": true}')
    def test_fixed_scope_contains_only_five_sources_and_two_lists(self):
        self.assertEqual(len(c.ENDPOINTS),7)
        self.assertEqual(set(c.SOURCE_NAMES),{'db.py','ua_spec84_runtime.py','start_safe.py','uaart_connection_monitor.py','ua_site_counters.py'})
        self.assertEqual(set(c.ENDPOINTS)-{'files/path'+path for path in c.SOURCE_PATHS},{'always_on/','schedule/'})
    def test_public_page_facts_no_queries_or_page_text(self):
        raw=b'<article data-code="UA-0002"><a href="UA-0002.html?token=private">customer-private</a></article><a href="UA-00020.html">other</a>'
        facts=c.inspect_page(raw,'/home/Carix/video/katalog.html')
        self.assertIn('UA-0002.html',facts['target_links'])
        self.assertNotIn('customer-private',json.dumps(facts))
        self.assertNotIn('token',json.dumps(facts))
    def test_partial_errors_produce_explicit_evidence_no_claim_of_deletion(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);request=root/c.REQUEST;request.parent.mkdir(parents=True)
            request.write_text(json.dumps({'task_id':c.TASK_ID,'production_required':False,'read_only':True}))
            env={'UAART_TASK_ID':c.TASK_ID,'UAART_TASK_CLASS':'STANDARD','UAART_REQUEST_PATH':c.REQUEST,
                 'UAART_REQUEST_SHA256':c.sha(request.read_bytes()),'UAART_RUN_ID':'12345','UAART_RECEIPT_PATH':c.RECEIPT}
            class Partial:
                def read(self, endpoint):
                    if endpoint in ('always_on/','schedule/'): return b'[]'
                    if endpoint.endswith('db.py'): return b'def connect():\n    return None\n'
                    raise c.ProbeError('HTTP_404')
            receipt=c.execute(env,root=root,api=Partial())
            evidence=json.loads((root/c.EVIDENCE).read_text())
            self.assertFalse(receipt['deletion_performed'])
            self.assertFalse(evidence['database_row_verified'])
            self.assertFalse(evidence['os_writers_verified'])
            self.assertEqual(evidence['remote_write_count'],0)
            self.assertEqual(evidence['schedule']['tasks'],[])
            self.assertTrue(receipt['unavailable_or_unparsed_paths'])
            self.assertEqual(len(evidence['path_status']),len(c.ENDPOINTS))
            with self.assertRaises(c.ProbeError):c.execute(env,root=root,api=Partial())
    def test_error_message_never_exposes_transport_details(self):
        class Bad:
            def read(self, endpoint): raise RuntimeError('authorization=private-value')
        payload,status=c.safe_fetch(Bad(),'always_on/')
        self.assertIsNone(payload)
        self.assertEqual(status['error'],'UNEXPECTED_READ_ERROR')

if __name__=='__main__': unittest.main()
