#!/usr/bin/env python3
"""Targeted regression for the existing pinned analytics bundle asset only."""
import sys
sys.dont_write_bytecode = True
import contextlib
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
RUNTIME = Path(os.environ.get('PR114_TEST_RUNTIME_ROOT',str(HERE.parents[1]/'task088_v5_preview')))
spec = importlib.util.spec_from_file_location('analytics_stage_target',HERE/'stage_exact_preview.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
SCRIPT = b'/* existing captured public analytics fixture; no service */\n'


class AnalyticsStageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pr114-analytics-stage-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('common','routing_proof','viewport_harness','wsgi_preview'):
            sys.modules.pop(name,None)
        m.PARENT = self.root/'private'; m.PARENT.mkdir(mode=0o700)
        m.TARGET = self.root/'dedicated.py'
        m.PRODUCTION = self.root/'production.py'
        m.PUBLIC = self.root/'video'; m.PUBLIC.mkdir()
        self.prod = b'# immutable fixture production WSGI\n'
        self.old_wsgi = b''
        m.PRODUCTION.write_bytes(self.prod)
        m.SOURCE_ROUTING = dict(m.SOURCE_ROUTING,**{'observed_wsgi_config.py':m.sha(self.prod)})
        self.old = m.PARENT/'old'; self.old.mkdir(mode=0o700)
        self.bundle = self.old/'candidate'; self.bundle.mkdir(mode=0o700)
        (self.bundle/'public').mkdir(mode=0o700)
        (self.bundle/'public/ua').mkdir(mode=0o700)
        (self.bundle/'public/ua/a.js').write_bytes(SCRIPT)
        proof = {'source_sha256':{
            'observed_wsgi_config.py':'3067d39ec9c2eb976114afc6744e2c34b088a8414e98eb3e33e0a47c1849e308',
            'analitika_wsgi.py':'a73be46099596322dcd607ecadd56140d45483a5ad38f1c1a0a0e395cfc8bc94',
            'uaart_bridge_wsgi.py':'b0c93d88d67e8c285c1bffb40bd6f2e40c2779af7a01cebd6beab4beda685150'},
            'static_mappings':[{'url':'/video/','directory':'/home/Carix/video/'}],
            'production_location':'https://www.uaart.com.ua/video/index.html','routing_evidence_sha256':'1'*64,
            'route':'/site/index.html','classification':'UNSERVED_LEGACY_USES_BASE_WSGI_REDIRECT'}
        self.manifest = {'redirects':{'/site/index.html':{'status':'302 Found','location':'/video/index.html','proof':proof}},
            'files':{'/ua/a.js':{'storage':'bundle','path':'public/ua/a.js','sha256':m.sha(SCRIPT),
                'bytes':len(SCRIPT),'content_type':'application/javascript; charset=utf-8'}}}
        keys = ('database_and_published_rows','source_hashes_and_stamps','routing_hashes_and_stamps',
            'core_html_hashes_and_stamps','diagnostic_hashes_and_stamps','supporting_html_hashes_and_stamps',
            'runtime_modules_hashes_and_stamps','known_runtime_source_overlap','referenced_media_metadata_only','home_routing_equal_core')
        self.obs = {'contract':'PR114-POINT4-CORE-READONLY-OBSERVATION-1',
            'status':'PASS_CORE_DOUBLE_READ_STABLE_OBSERVATION','export_completed':True,'blockers':[],
            'stability':dict.fromkeys(keys,True),'database':{'published_codes':['UA-0001']},
            'second_database':{'published_codes':['UA-0001']},'schema_sha256':'2'*64,'second_schema_sha256':'2'*64,
            'routing_sources':{n:{'sha256':p} for n,p in m.SOURCE_ROUTING.items()},'diagnostic_html':{}}
        m.write(self.root/'observer.json',m.encoded(self.obs))

    def prepare(self,reference='/ua/a.js?v=1'):
        (self.bundle/'manifest.json').write_bytes(m.encoded(self.manifest))
        self.config = {'contract':m.CONTRACT,'preview_origin':m.ORIGIN,'bundle_root':str(self.bundle),
            'manifest_sha256':m.sha(m.encoded(self.manifest)),'access_policy':'PUBLIC_READ_ONLY_PREVIEW_OWNER_AUTHORIZED'}
        m.write(self.old/'config.json',m.encoded(self.config))
        self.old_wsgi = ('import os\nos.environ["UA_ART_PREVIEW_CONFIG"] = '+repr(str(self.old/'config.json'))+'\n').encode()
        m.TARGET.write_bytes(self.old_wsgi)
        raw = ('<!doctype html><html><body>Fixture<script src="'+reference+'"></script></body></html>').encode()
        html = {f'{folder}/{name}.html':raw for folder in ('site','video') for name in ('index','katalog','UA-0001')}
        package = {'contract':'PR114-EXACT-PUBLIC-PREVIEW-PACKAGE-1','observer_sha256':m.sha(m.encoded(self.obs)),
            'published_codes':['UA-0001'],'runtime_sha256':m.RUNTIME,'canonical_candidate_manifest_sha256':'3'*64,
            'candidate_html_sha256':{name:m.sha(data) for name,data in html.items()}}
        package_path = self.root/'public.zip'
        with zipfile.ZipFile(package_path,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('package_manifest.json',m.encoded(package))
            for name,data in html.items(): archive.writestr('candidate/'+name,data)
            for name,pin in m.RUNTIME.items(): archive.writestr('runtime/'+name,m.read(RUNTIME/name,pin))
        self.args = SimpleNamespace(operation_id='analytics-fixture-001',package=str(package_path),
            package_sha256=m.sha(package_path.read_bytes()),observer=str(self.root/'observer.json'),
            observer_sha256=m.sha(m.encoded(self.obs)),existing_config=str(self.old/'config.json'),
            expected_wsgi_sha256=m.sha(self.old_wsgi),expected_config_sha256=m.sha(m.encoded(self.config)),max_seconds=30,
            analytics_observation=str(self.root/'analytics_observation.json'))
        self.current_analytics = {'contract':'PR114-CURRENT-PUBLIC-ANALYTICS-OBSERVATION-1',
            'core_observer_sha256':self.args.observer_sha256,'url':m.PRODUCTION_ORIGIN+'/ua/a.js',
            'final_url':m.PRODUCTION_ORIGIN+'/ua/a.js','http_status':200,
            'content_type':'application/javascript; charset=utf-8','sha256':m.sha(SCRIPT),'bytes':len(SCRIPT),
            'observed_at_utc':datetime.now(timezone.utc).isoformat()}
        self.record_current_analytics()
        self.html = html

    def record_current_analytics(self):
        raw = m.encoded(self.current_analytics)
        Path(self.args.analytics_observation).write_bytes(raw)
        self.args.analytics_observation_sha256 = m.sha(raw)

    def stage(self):
        try:
            with contextlib.redirect_stdout(io.StringIO()): m.stage(self.args)
        finally:
            self.assertEqual(m.TARGET.read_bytes(),self.old_wsgi)
            self.assertEqual(m.PRODUCTION.read_bytes(),self.prod)
        return m.PARENT/'pr114-preview-analytics-fixture-001'

    def test_existing_script_retained_exactly_and_private_routes_remain_denied(self):
        self.prepare()
        work = self.stage()
        manifest = json.loads((work/'candidate/manifest.json').read_bytes())
        self.assertEqual(manifest['files']['/ua/a.js'],self.manifest['files']['/ua/a.js'])
        self.assertEqual((work/'candidate/public/ua/a.js').read_bytes(),SCRIPT)
        self.assertEqual(manifest['asset_roots'],{'video':str(m.PUBLIC)})
        provenance = json.loads((work/'candidate/provenance.json').read_bytes())
        self.assertEqual(provenance['retained_public_asset_captures']['ua/a.js']['source_manifest_sha256'],self.config['manifest_sha256'])
        for name,data in self.html.items():
            target = work/'candidate'/('public' if name.startswith('video/') else 'offline')/name
            self.assertEqual(target.read_bytes(),data)
        app = sys.modules['wsgi_preview'].Preview(work/'config.json')
        def request(path,method='GET'):
            status=[]
            body=b''.join(app({'REQUEST_METHOD':method,'PATH_INFO':path,'QUERY_STRING':'v=1',
                'HTTP_HOST':'carix.pythonanywhere.com','wsgi.url_scheme':'https'},lambda s,h:status.append(s)))
            return status[0],body
        self.assertEqual(request('/ua/a.js'),('200 OK',SCRIPT))
        for route in ('/ua/a/e','/ua/other.js','/config.json','/manifest.json','/cars.db','/db.py',
                      '/site/UA-0001.html','/video/../config.json','/ua/%2e%2e/config.json'):
            self.assertEqual(request(route)[0],'404 Not Found',route)
        self.assertEqual(request('/ua/a.js','POST')[0],'405 Method Not Allowed')
        self.assertFalse((work/'02-switch-intent.json').exists())
        with self.assertRaisesRegex(ValueError,'EXISTING_OPERATION_INSPECT_FIRST_NO_REPEAT'): self.stage()

    def test_capture_sha_drift_rejected(self):
        self.prepare()
        (self.bundle/'public/ua/a.js').write_bytes(SCRIPT+b'changed')
        with self.assertRaisesRegex(ValueError,'INPUT_SHA256_MISMATCH'): self.stage()

    def test_current_response_mismatch_rejected(self):
        self.prepare()
        self.current_analytics['sha256'] = 'f'*64
        self.record_current_analytics()
        with self.assertRaisesRegex(ValueError,'CURRENT_PUBLIC_ANALYTICS_RESPONSE_BINDING_REQUIRED'): self.stage()

    def test_stale_current_response_rejected(self):
        self.prepare()
        self.current_analytics['observed_at_utc'] = (datetime.now(timezone.utc)-timedelta(minutes=16)).isoformat()
        self.record_current_analytics()
        with self.assertRaisesRegex(ValueError,'FRESH_PUBLIC_ANALYTICS_OBSERVATION_REQUIRED'): self.stage()

    def test_missing_current_response_rejected(self):
        self.prepare()
        Path(self.args.analytics_observation).unlink()
        with self.assertRaises(FileNotFoundError): self.stage()

    def test_current_response_pin_mismatch_rejected(self):
        self.prepare()
        self.args.analytics_observation_sha256 = '0'*64
        with self.assertRaisesRegex(ValueError,'INPUT_SHA256_MISMATCH'): self.stage()

    def test_capture_length_mismatch_rejected(self):
        self.manifest['files']['/ua/a.js']['bytes'] += 1
        self.prepare()
        with self.assertRaisesRegex(ValueError,'CAPTURE_LENGTH_MISMATCH'): self.stage()

    def test_missing_existing_capture_is_not_synthesized(self):
        self.manifest['files'] = {}
        self.prepare()
        with self.assertRaisesRegex(ValueError,'EXACT_EXISTING_ANALYTICS_CAPTURE_REQUIRED'): self.stage()

    def test_private_capture_path_rejected(self):
        self.manifest['files']['/ua/a.js']['path'] = '../../config.json'
        self.prepare()
        with self.assertRaisesRegex(ValueError,'EXACT_EXISTING_ANALYTICS_CAPTURE_REQUIRED'): self.stage()

    def test_symlink_capture_rejected(self):
        self.prepare()
        path = self.bundle/'public/ua/a.js'
        path.unlink()
        private = self.root/'private_config'; private.write_bytes(SCRIPT)
        path.symlink_to(private)
        with self.assertRaisesRegex(ValueError,'NO_SYMLINK_INPUT'): self.stage()

    def test_other_ua_script_not_admitted(self):
        self.prepare('/ua/private.js')
        with self.assertRaisesRegex(ValueError,'UNSERVED_PUBLIC_ASSET_ROUTE:ua/private.js'): self.stage()

    def test_private_route_not_admitted(self):
        self.prepare('/config.json')
        with self.assertRaisesRegex(ValueError,'UNSERVED_PUBLIC_ASSET_ROUTE:config.json'): self.stage()

    def test_encoded_traversal_not_admitted(self):
        self.prepare('/video/%2e%2e/config.json')
        with self.assertRaisesRegex(ValueError,'CANONICAL_PUBLIC_RELATIVE_PATH_REQUIRED'): self.stage()

    def test_package_pin_still_required_before_private_work_created(self):
        self.prepare()
        self.args.package_sha256 = '0'*64
        with self.assertRaisesRegex(ValueError,'INPUT_SHA256_MISMATCH'): self.stage()
        self.assertFalse((m.PARENT/'pr114-preview-analytics-fixture-001').exists())

    def test_cli_self_pin_still_required(self):
        result = subprocess.run([sys.executable,'-I','-B',str(HERE/'stage_exact_preview.py'),
            '--self-sha256','0'*64,'inspect','--work',str(self.root/'absent')],capture_output=True,text=True,timeout=10)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('PINNED_STAGING_HELPER_REQUIRED',result.stderr)


if __name__ == '__main__':
    assert sys.flags.isolated and sys.dont_write_bytecode
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(AnalyticsStageTests)
    names = [case.id() for case in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    evidence = {'status':'PASS_TARGETED_ANALYTICS_STAGE' if result.wasSuccessful() else 'FAIL',
        'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'tests':names,
        'stage_helper_sha256':m.sha(m.read(HERE/'stage_exact_preview.py')),
        'test_sha256':m.sha(m.read(__file__)),
        'limitations':['isolated temporary filesystem fixture','no server writes, switch, reload or browser',
            'existing full suites and Preview 24/24 were not rerun']}
    (HERE/'TARGETED_RESULT.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(evidence,indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
