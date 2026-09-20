#!/usr/bin/env python3
"""Focused isolated fixture for new Preview staging boundaries; no real server."""
import sys
sys.dont_write_bytecode = True
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import zipfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('preview_stage_fixture_target',HERE/'stage_exact_preview.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
repo = HERE.parents[2]
runtime = repo/'cloud/task088_v5_preview'


def reset_runtime():
    for name in ('common','routing_proof','viewport_harness','wsgi_preview'):
        sys.modules.pop(name,None)


def run():
    assert sys.flags.isolated and sys.dont_write_bytecode
    with tempfile.TemporaryDirectory(prefix='preview-stage-boundaries-') as temp:
        root = Path(temp)
        m.PARENT = root/'private';m.PARENT.mkdir(mode=0o700)
        www = root/'varwww';www.mkdir()
        m.TARGET = www/'dedicated.py'
        m.PRODUCTION = www/'production.py'
        m.PUBLIC = root/'video';m.PUBLIC.mkdir()
        production = b'# fixture production WSGI must remain unchanged\n'
        m.PRODUCTION.write_bytes(production)
        m.SOURCE_ROUTING = dict(m.SOURCE_ROUTING,observed_wsgi_config_py='unused')
        del m.SOURCE_ROUTING['observed_wsgi_config_py']
        m.SOURCE_ROUTING['observed_wsgi_config.py'] = m.sha(production)
        old = m.PARENT/'old';old.mkdir(mode=0o700)
        bundle = old/'candidate';bundle.mkdir(mode=0o700)
        real_route = json.loads((repo/'cloud/task088_v5_acceptance/resume_20260915_2/binding_1509_0446.json').read_text())
        # Use the exact reviewed public proof shape, not a new routing claim.
        proof = {'source_sha256':{
            'observed_wsgi_config.py':'3067d39ec9c2eb976114afc6744e2c34b088a8414e98eb3e33e0a47c1849e308',
            'analitika_wsgi.py':'a73be46099596322dcd607ecadd56140d45483a5ad38f1c1a0a0e395cfc8bc94',
            'uaart_bridge_wsgi.py':'b0c93d88d67e8c285c1bffb40bd6f2e40c2779af7a01cebd6beab4beda685150'},
            'static_mappings':[{'url':'/video/','directory':'/home/Carix/video/'}],
            'production_location':'https://www.uaart.com.ua/video/index.html','routing_evidence_sha256':'1'*64,
            'route':'/site/index.html','classification':'UNSERVED_LEGACY_USES_BASE_WSGI_REDIRECT'}
        oldmanifest = {'redirects':{'/site/index.html':{'status':'302 Found','location':'/video/index.html','proof':proof}}}
        (bundle/'manifest.json').write_bytes(m.encoded(oldmanifest))
        config = {'contract':m.CONTRACT,'preview_origin':m.ORIGIN,'bundle_root':str(bundle),
                  'manifest_sha256':m.sha(m.encoded(oldmanifest)),'access_policy':'PUBLIC_READ_ONLY_PREVIEW_OWNER_AUTHORIZED'}
        m.write(old/'config.json',m.encoded(config))
        old_wsgi = ('import os\nos.environ["UA_ART_PREVIEW_CONFIG"] = '+repr(str(old/'config.json'))+'\n').encode()
        m.TARGET.write_bytes(old_wsgi)
        stability_keys = ('database_and_published_rows','source_hashes_and_stamps','routing_hashes_and_stamps',
            'core_html_hashes_and_stamps','diagnostic_hashes_and_stamps','supporting_html_hashes_and_stamps',
            'runtime_modules_hashes_and_stamps','known_runtime_source_overlap','referenced_media_metadata_only','home_routing_equal_core')
        obs = {'contract':'PR114-POINT4-CORE-READONLY-OBSERVATION-1','status':'PASS_CORE_DOUBLE_READ_STABLE_OBSERVATION',
               'export_completed':True,'blockers':[],'stability':dict.fromkeys(stability_keys,True),
               'database':{'published_codes':['UA-0001']},'second_database':{'published_codes':['UA-0001']},
               'schema_sha256':'2'*64,'second_schema_sha256':'2'*64,
               'routing_sources':{n:{'sha256':p} for n,p in m.SOURCE_ROUTING.items()},'diagnostic_html':{}}
        m.write(root/'observer.json',m.encoded(obs))
        html = {f'{folder}/{name}.html':b'<!doctype html><html><body>Fixture public bytes</body></html>'
                for folder in ('site','video') for name in ('index','katalog','UA-0001')}
        analytics = b'(()=>{"use strict"})();\n'
        analytics_evidence = {'schema_version':'PR114-PUBLIC-ANALYTICS-CAPTURE-1',
            'url':m.ANALYTICS_URL,'final_url':m.ANALYTICS_URL,'method':'GET','status':200,
            'content_type':'application/javascript','bytes':len(analytics),'sha256':m.sha(analytics),
            'source_wrapper_sha256':m.SOURCE_ROUTING['analitika_wsgi.py'],'redirect_followed':False,
            'event_endpoint_called':False,'captured_at_utc':'2026-09-20T12:00:00Z'}
        analytics_evidence_raw = m.encoded(analytics_evidence)
        package = {'contract':'PR114-EXACT-PUBLIC-PREVIEW-PACKAGE-2','observer_sha256':m.sha(m.encoded(obs)),
            'published_codes':['UA-0001'],'runtime_sha256':m.RUNTIME,'canonical_candidate_manifest_sha256':'3'*64,
            'candidate_html_sha256':{n:m.sha(raw) for n,raw in html.items()},
            'public_wrapper_asset':{'path':m.ANALYTICS_PATH,'url':m.ANALYTICS_URL,'sha256':m.sha(analytics),
                'bytes':len(analytics),'source_content_type':'application/javascript',
                'content_type':m.PREVIEW_ANALYTICS_MIME,
                'source_wrapper_sha256':m.SOURCE_ROUTING['analitika_wsgi.py'],
                'capture_evidence_path':'evidence/ua-a-js.json',
                'capture_evidence_sha256':m.sha(analytics_evidence_raw)}}
        def make_package(path, manifest=package, asset=analytics, evidence=analytics_evidence_raw,
                         include_asset=True, include_evidence=True, extras=None):
          with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as packed:
            packed.writestr('package_manifest.json',m.encoded(manifest))
            for n,raw in html.items():packed.writestr('candidate/'+n,raw)
            for n in m.RUNTIME:packed.writestr('runtime/'+n,(runtime/n).read_bytes())
            if include_asset: packed.writestr('public/'+m.ANALYTICS_PATH,asset)
            if include_evidence: packed.writestr('evidence/ua-a-js.json',evidence)
            for name,raw in (extras or {}).items(): packed.writestr(name,raw)
        def arguments(path, operation):
            return SimpleNamespace(operation_id=operation,package=str(path),package_sha256=m.sha(path.read_bytes()),
                observer=str(root/'observer.json'),observer_sha256=m.sha(m.encoded(obs)),existing_config=str(old/'config.json'),
                expected_wsgi_sha256=m.sha(old_wsgi),expected_config_sha256=m.sha(m.encoded(config)),max_seconds=30)
        def rejected(name, code, **kwargs):
            path=root/(name+'.zip'); make_package(path,**kwargs)
            try:
                with contextlib.redirect_stdout(io.StringIO()):m.stage(arguments(path,'fixture-'+name))
            except (ValueError,KeyError) as error:
                assert code in str(error),(name,str(error))
            else: raise AssertionError('Unsafe analytics package accepted: '+name)
        rejected('missing-asset','ONLY_PUBLIC_HTML_AND_REVIEWED_RUNTIME_ALLOWED',include_asset=False)
        rejected('extra-route','ONLY_PUBLIC_HTML_AND_REVIEWED_RUNTIME_ALLOWED',extras={'public/ua/evil.js':b'evil'})
        rejected('asset-drift','PUBLIC_ANALYTICS_PACKAGE_BYTES_MISMATCH',asset=analytics+b'drift')
        event_evidence=copy.deepcopy(analytics_evidence);event_evidence['event_endpoint_called']=True
        event_raw=m.encoded(event_evidence);event_package=copy.deepcopy(package)
        event_package['public_wrapper_asset']['capture_evidence_sha256']=m.sha(event_raw)
        rejected('event-endpoint','SAFE_PUBLIC_ANALYTICS_CAPTURE_EVIDENCE_REQUIRED',manifest=event_package,evidence=event_raw)
        source_package=copy.deepcopy(package);source_package['public_wrapper_asset']['source_wrapper_sha256']='0'*64
        rejected('source-drift','EXACT_PUBLIC_ANALYTICS_ASSET_BINDING_REQUIRED',manifest=source_package)
        zip_path = root/'public.zip';make_package(zip_path)
        args = arguments(zip_path,'fixture-op-001')
        with contextlib.redirect_stdout(io.StringIO()):m.stage(args)
        work = m.PARENT/'pr114-preview-fixture-op-001'
        receipt_raw = (work/'01-stage-receipt.json').read_bytes()
        receipt = json.loads(receipt_raw)
        staged_manifest = json.loads((work/'candidate/manifest.json').read_bytes())
        assert staged_manifest['files']['/ua/a.js']['sha256'] == m.sha(analytics)
        assert '/ua/a/e' not in staged_manifest['files']
        assert m.TARGET.read_bytes() == old_wsgi and m.PRODUCTION.read_bytes() == production
        assert receipt['validation']['private_routes_denied'] == 9
        assert not (work/'02-switch-intent.json').exists()
        try:
            with contextlib.redirect_stdout(io.StringIO()):m.stage(args)
        except ValueError as e:assert 'EXISTING_OPERATION' in str(e)
        else:raise AssertionError('Repeated staging not rejected')
        reset_runtime()
        switch = SimpleNamespace(work=str(work),action='switch',stage_receipt_sha256=m.sha(receipt_raw),max_seconds=30)
        with contextlib.redirect_stdout(io.StringIO()):m.switch(switch)
        assert m.PRODUCTION.read_bytes() == production
        assert m.TARGET.read_bytes() == (work/'candidate-preview-wsgi.py').read_bytes()
        assert (work/'02-switch-intent.json').exists() and (work/'03-switch-receipt.json').exists()
        switched = m.TARGET.read_bytes()
        try:
            with contextlib.redirect_stdout(io.StringIO()):m.switch(switch)
        except ValueError as e:assert 'EXISTING_SWITCH_INTENT' in str(e)
        else:raise AssertionError('Repeated switch not rejected')
        assert m.TARGET.read_bytes() == switched
        assert m.inspect(work)['actual_outcome'] == 'CANDIDATE_PRESENT'
        m.TARGET.write_bytes(b'# unknown foreign change\n')
        assert m.inspect(work)['actual_outcome'] == 'UNKNOWN_FOREIGN_BYTES'
        try:
            with contextlib.redirect_stdout(io.StringIO()):m.switch(switch)
        except ValueError as e:assert 'EXISTING_SWITCH_INTENT' in str(e)
        else:raise AssertionError('Foreign bytes overwritten')
        assert m.TARGET.read_bytes() == b'# unknown foreign change\n'
        assert not any(p.suffix in ('.db','.sqlite') for p in work.rglob('*'))
        assert (work/'config.json').stat().st_mode & 0o777 == 0o600
        return {'status':'PASS_TARGETED_LOCAL_FIXTURE','checks':['five unsafe analytics package variants fail closed',
            'stage preserves dedicated and production WSGI',
            'pinned public runtime validates scoped bundle and nine denied private routes','separate durable switch intent and observed receipt',
            'unknown or repeated switch never replaces again','foreign bytes inspection preserved','private config mode and no DB export'],
            'limitations':['temporary fixture constants replace real server locations and production source hash',
                'no browser, network, current production binding, service reload or Preview acceptance'],
            'stage_helper_sha256':m.sha((HERE/'stage_exact_preview.py').read_bytes())}


if __name__ == '__main__':
    print(json.dumps(run(),indent=2))
