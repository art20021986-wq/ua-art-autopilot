#!/usr/bin/env python3
"""Package only exact public HTML and unchanged public Preview runtime.

The complete installation candidate is verified locally but private Python,
configuration and DB bytes never enter the resulting ZIP.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import zipfile
_helper = Path(__file__).resolve().parent/'stage_exact_preview.py'
_spec = importlib.util.spec_from_file_location('exact_preview_package_helpers',_helper)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
RUNTIME, SOURCE_ROUTING, read, encoded, require, sha = [_module.__dict__[key] for key in
    ('RUNTIME','SOURCE_ROUTING','read','encoded','require','sha')]
ANALYTICS_PATH = 'ua/a.js'
ANALYTICS_URL = 'https://www.uaart.com.ua/ua/a.js'
ANALYTICS_MIME = {'application/javascript','text/javascript'}
PREVIEW_ANALYTICS_MIME = 'application/javascript; charset=utf-8'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate','candidate-manifest','observer','repository','analytics-capture','analytics-receipt','output'):
        parser.add_argument('--'+name,required=True)
    args = parser.parse_args()
    root = Path(args.candidate).resolve(strict=True)
    evidence_raw = read(args.candidate_manifest)
    evidence = json.loads(evidence_raw)
    files = evidence.get('candidate_files',evidence.get('files',evidence))
    require(type(files) is dict and files and all(type(v) is dict and 'after_sha256' in v for v in files.values()),
            'EXACT_CANONICAL_CANDIDATE_FILE_MAP_REQUIRED')
    canonical_sha = sha(json.dumps(files,ensure_ascii=True,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
    if 'candidate_manifest_sha256' in evidence:
        require(evidence['candidate_manifest_sha256'] == canonical_sha,'CANDIDATE_MANIFEST_DIGEST_MISMATCH')
    for name,item in files.items():
        require(not name.startswith('/') and not any(p in ('','.','..') for p in name.split('/')) and '\\' not in name,
                'EXACT_CANDIDATE_RELATIVE_PATH_REQUIRED')
        read(root/name,item['after_sha256'])
    obs_raw = read(args.observer)
    obs = json.loads(obs_raw)
    if 'current_core_observation_sha256' in evidence:
        require(evidence['current_core_observation_sha256'] == sha(obs_raw),'CANDIDATE_CURRENT_OBSERVER_BINDING_MISMATCH')
    require(obs.get('status') == 'PASS_CORE_DOUBLE_READ_STABLE_OBSERVATION' and obs.get('export_completed') is True,
            'FINAL_COMPLETED_CURRENT_OBSERVER_REQUIRED')
    codes = obs['database']['published_codes']
    require(len(codes) == len(set(codes)) and all(re.fullmatch(r'UA-[0-9]{4,}',code) for code in codes),
            'EXACT_DYNAMIC_CURRENT_CODES_REQUIRED')
    html = sorted(f'{folder}/{code}.html' for folder in ('site','video') for code in ['index','katalog',*codes])
    require(set(html) <= set(files),'FULL_CURRENT_CORE_HTML_CANDIDATE_REQUIRED')
    payload = {'candidate/'+name:read(root/name,files[name]['after_sha256']) for name in html}
    runtime = Path(args.repository).resolve(strict=True)/'cloud/task088_v5_preview'
    payload.update({'runtime/'+name:read(runtime/name,pin) for name,pin in RUNTIME.items()})
    analytics_receipt_raw = read(args.analytics_receipt)
    analytics_receipt = json.loads(analytics_receipt_raw)
    required_capture = {'schema_version','url','final_url','method','status','content_type','bytes','sha256',
        'source_wrapper_sha256','redirect_followed','event_endpoint_called','captured_at_utc'}
    require(type(analytics_receipt) is dict and set(analytics_receipt) == required_capture,
            'EXACT_ANALYTICS_CAPTURE_RECEIPT_REQUIRED')
    require(analytics_receipt['schema_version'] == 'PR114-PUBLIC-ANALYTICS-CAPTURE-1' and
            analytics_receipt['url'] == ANALYTICS_URL and analytics_receipt['final_url'] == ANALYTICS_URL and
            analytics_receipt['method'] == 'GET' and analytics_receipt['status'] == 200 and
            analytics_receipt['content_type'] in ANALYTICS_MIME and analytics_receipt['redirect_followed'] is False and
            analytics_receipt['event_endpoint_called'] is False and
            analytics_receipt['source_wrapper_sha256'] == SOURCE_ROUTING['analitika_wsgi.py'] and
            type(analytics_receipt['bytes']) is int and 0 < analytics_receipt['bytes'] <= 1024*1024 and
            type(analytics_receipt['captured_at_utc']) is str and analytics_receipt['captured_at_utc'].endswith('Z'),
            'PINNED_SAFE_ANALYTICS_CAPTURE_REQUIRED')
    analytics_raw = read(args.analytics_capture,analytics_receipt['sha256'],1024*1024)
    require(len(analytics_raw) == analytics_receipt['bytes'],'ANALYTICS_CAPTURE_LENGTH_MISMATCH')
    payload['public/'+ANALYTICS_PATH] = analytics_raw
    payload['evidence/ua-a-js.json'] = analytics_receipt_raw
    package = {'contract':'PR114-EXACT-PUBLIC-PREVIEW-PACKAGE-2','observer_sha256':sha(obs_raw),
        'published_codes':codes,'candidate_html_sha256':{name:files[name]['after_sha256'] for name in html},
        'runtime_sha256':RUNTIME,'canonical_candidate_manifest_sha256':canonical_sha,
        'candidate_manifest_evidence_sha256':sha(evidence_raw),
        'public_wrapper_asset':{'path':ANALYTICS_PATH,'url':ANALYTICS_URL,'sha256':sha(analytics_raw),
            'bytes':len(analytics_raw),'source_content_type':analytics_receipt['content_type'],
            'content_type':PREVIEW_ANALYTICS_MIME,
            'source_wrapper_sha256':SOURCE_ROUTING['analitika_wsgi.py'],
            'capture_evidence_path':'evidence/ua-a-js.json','capture_evidence_sha256':sha(analytics_receipt_raw)},
        'private_sources_included':False,
        'browser_run':False,'preview_gate':'NOT_PASSED'}
    payload['package_manifest.json'] = encoded(package)
    fd = os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as output:
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as packed:
            for name,raw in sorted(payload.items()):
                info = zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
                info.external_attr = 0o100600 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                packed.writestr(info,raw)
        output.flush(); os.fsync(output.fileno())
    raw = read(args.output)
    print(json.dumps({'status':'EXACT_PUBLIC_PREVIEW_PACKAGE_PREPARED_NOT_STAGED','path':args.output,
                      'sha256':sha(raw),'bytes':len(raw),'members':len(payload),'html':len(html),'wrapper_assets':1,
                      'canonical_candidate_manifest_sha256':canonical_sha,'private_sources_included':False}))


if __name__ == '__main__':
    main()
