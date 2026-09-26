#!/usr/bin/env python3
"""Add one hash-bound public analytics script to the exact reviewed Preview package.

This helper is offline and fail-closed. It never calls the analytics event
endpoint, edits Production, imports application code, stages, switches or reloads.
"""
import argparse
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import zipfile

_helper = Path(__file__).resolve().parent/'stage_exact_preview.py'
_spec = importlib.util.spec_from_file_location('analytics_package_upgrade_helpers',_helper)
stage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stage)

SOURCE_CONTRACT = 'PR114-EXACT-PUBLIC-PREVIEW-PACKAGE-1'
TARGET_CONTRACT = 'PR114-EXACT-PUBLIC-PREVIEW-PACKAGE-2'
ANALYTICS_PATH = 'ua/a.js'
ANALYTICS_URL = 'https://www.uaart.com.ua/ua/a.js'
CAPTURE_CONTRACT = 'PR114-PUBLIC-ANALYTICS-CAPTURE-1'
SOURCE_MIME = {'application/javascript','text/javascript'}
PREVIEW_MIME = 'application/javascript; charset=utf-8'


def validate_capture(raw, receipt_raw):
    return stage.validate_public_analytics_capture(raw,receipt_raw)


def upgrade(source_raw, capture_raw, receipt_raw):
    with zipfile.ZipFile(io.BytesIO(source_raw)) as packed:
        infos = packed.infolist(); names = [item.filename for item in infos]
        stage.require(len(names) == len(set(names)) and len(names) < 200,'BOUNDED_UNIQUE_SOURCE_MEMBERS_REQUIRED')
        stage.require(all(not item.is_dir() and not stat.S_ISLNK(item.external_attr >> 16) and
            item.file_size <= stage.LIMIT for item in infos),'BOUNDED_REGULAR_SOURCE_MEMBERS_REQUIRED')
        package = json.loads(packed.read('package_manifest.json'))
        stage.require(package.get('contract') == SOURCE_CONTRACT and package.get('private_sources_included') is False and
            package.get('preview_gate') == 'NOT_PASSED' and package.get('browser_run') is False,
            'EXACT_REVIEWED_SOURCE_PACKAGE_REQUIRED')
        html = package.get('candidate_html_sha256',{}); runtime = package.get('runtime_sha256',{})
        expected = {'package_manifest.json',*('candidate/'+name for name in html),*('runtime/'+name for name in runtime)}
        stage.require(set(names) == expected,'EXACT_SOURCE_PACKAGE_CLOSURE_REQUIRED')
        for name,pin in html.items():
            stage.require(stage.sha(packed.read('candidate/'+name)) == pin,'SOURCE_HTML_SHA256_MISMATCH:'+name)
        stage.require(runtime == stage.RUNTIME,'SOURCE_RUNTIME_MAP_MISMATCH')
        for name,pin in runtime.items():
            stage.require(stage.sha(packed.read('runtime/'+name)) == pin,'SOURCE_RUNTIME_SHA256_MISMATCH:'+name)
        payload = {name:packed.read(name) for name in names if name != 'package_manifest.json'}
    receipt = validate_capture(capture_raw,receipt_raw)
    target = dict(package)
    target['contract'] = TARGET_CONTRACT
    target['public_wrapper_asset'] = {'path':ANALYTICS_PATH,'url':ANALYTICS_URL,
        'sha256':stage.sha(capture_raw),'bytes':len(capture_raw),'source_content_type':receipt['content_type'],
        'content_type':PREVIEW_MIME,'source_wrapper_sha256':stage.SOURCE_ROUTING['analitika_wsgi.py'],
        'capture_evidence_path':'evidence/ua-a-js.json','capture_evidence_sha256':stage.sha(receipt_raw)}
    payload['package_manifest.json'] = stage.encoded(target)
    payload['public/'+ANALYTICS_PATH] = capture_raw
    payload['evidence/ua-a-js.json'] = receipt_raw
    output = io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as packed:
        for name,raw in sorted(payload.items()):
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.external_attr=0o100600 << 16
            info.compress_type=zipfile.ZIP_DEFLATED;packed.writestr(info,raw)
    return output.getvalue(), target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-package','source-package-sha256','analytics-capture','analytics-receipt','output'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    source=stage.read(args.source_package,args.source_package_sha256,16*1024*1024)
    capture=stage.read(args.analytics_capture,limit=1024*1024)
    receipt=stage.read(args.analytics_receipt,limit=64*1024)
    raw,manifest=upgrade(source,capture,receipt)
    target=Path(args.output).absolute()
    stage.require(not target.exists() and target.parent.resolve(strict=True) == target.parent,'EXCLUSIVE_OUTPUT_REQUIRED')
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as output:
        output.write(raw);output.flush();os.fsync(output.fileno())
    print(json.dumps({'status':'PASS_EXACT_ANALYTICS_PACKAGE_UPGRADE_NOT_STAGED','path':str(target),
        'sha256':stage.sha(raw),'bytes':len(raw),'contract':manifest['contract'],'wrapper_assets':1,
        'source_package_sha256':stage.sha(source),'production_written':False,'preview_started':False}))


if __name__ == '__main__': main()
