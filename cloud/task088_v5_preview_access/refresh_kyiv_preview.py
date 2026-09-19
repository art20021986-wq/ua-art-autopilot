"""One-time, source-pinned Kyiv visibility update of the separate Preview only.

Rebuild from the preserved original capture using the canonical renderer.
Retain the prior complete Preview for rollback. Never write CRM/Production.
"""
import sys
sys.dont_write_bytecode = True
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from datetime import datetime, timezone

PARENT = Path('/home/Carix/autopilot_inbox/cloud')
STAGE = PARENT / 'task088-v5-preview-stage-zlcw0vma'
OLD_APP = STAGE / 'public-preview-app-k5dav0pf'
BASE = PARENT / 'provision_preview_08fbf7a1.py'
BASE_SHA = '206ec6f601a4997e2f1129f9e6deb158293b811ce188eba7eff6d02ce062d3f6'
PUBLIC_HELPER = PARENT / 'provision_public_preview_1.py'
PUBLIC_HELPER_SHA = '58c8cf3a3e25254ea6f978c79cb9004f519d59be75400cc2efbd8b6c326bda40'
RENDERER = PARENT / 'uaart_market_prices_kyiv_1.py'
RENDERER_SHA = '35d9f212060b36b60c257db8da3ab1e6aed8b1905e1038cf33bc395b731332ed'
OLD_WSGI_SHA = '90248b83241ca611f846d810485066ca7ef2d2f076dcaa275bc6068ea9a0d273'
OLD_MANIFEST_SHA = '083cd2de139f2f9e695f76c4e9873252c3291b4adb90af488c069315b37abdd6'
KYIV = {'UA-0002', 'UA-0007', 'UA-0008', 'UA-0017', 'UA-0018'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pinned(path, expected):
    if path.resolve(strict=True) != path or not path.is_file():
        raise ValueError('EXACT_REGULAR_SOURCE_REQUIRED')
    raw = path.read_bytes()
    if sha(raw) != expected:
        raise ValueError('REVIEWED_SOURCE_DRIFT:' + path.name)
    return raw


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def current_rows():
    with sqlite3.connect('file:/home/Carix/crm.db?mode=ro', uri=True, timeout=10) as conn:
        conn.execute('PRAGMA query_only=ON')
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute('SELECT id,auto_number,price_uah,price_georgia,status,published FROM cars WHERE published=1 ORDER BY id')]


def main():
    os.umask(0o077)
    pinned(BASE, BASE_SHA)
    base = load('kyiv_reviewed_base', BASE)
    pinned(PUBLIC_HELPER, PUBLIC_HELPER_SHA)
    helper = load('kyiv_reviewed_public_helper', PUBLIC_HELPER)
    renderer = pinned(RENDERER, RENDERER_SHA)
    before_wsgi = pinned(base.TARGET, OLD_WSGI_SHA)
    pinned(base.PRODUCTION, base.EXPECTED_PRODUCTION_WSGI)
    old_manifest = json.loads(pinned(STAGE / 'candidate/manifest.json', OLD_MANIFEST_SHA))
    pinned(STAGE / 'candidate/provenance.json', old_manifest['provenance_sha256'])
    host = base.host_state()
    package_manifest = json.loads(pinned(STAGE / 'package/package_manifest.json', base.EXPECTED_PACKAGE_MANIFEST))
    entries = package_manifest['sha256']
    work = Path(tempfile.mkdtemp(prefix='kyiv-preview-', dir=STAGE))
    package = work / 'package'
    for name, expected in entries.items():
        raw = pinned(STAGE / 'package' / name, expected)
        if name == 'cloud/task088_stage3_renderer/uaart_market_prices.py':
            raw = renderer
        target = package / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        base.write_private(target, raw)
    audit = load('kyiv_readonly_inventory', package / 'cloud/task088_v5_acceptance/run_private_server_build.py')
    capture = load('kyiv_readonly_capture_contract', package / 'cloud/task088_v5_acceptance/capture_private_snapshot.py')
    def inventory():
        return {'db':audit.database_inventory(), 'html':audit.html_inventory(),
                'sources':audit.source_inventory(capture.SOURCE_NAMES), 'hosting':audit.hosting_inventory()}
    before = inventory()
    base.write_private(work / 'protected_before.json', base.encode(before))
    snapshot = STAGE / 'snapshot'
    captured = json.loads(base.checked_read(snapshot / 'capture_manifest.json', True))
    for name, expected_hash in captured['sha256'].items():
        if name == 'published_price_rows.json' or name == 'ua/a.js':
            continue
        path = base.PRODUCTION if name == 'observed_wsgi_config.py' else Path('/home/Carix') / name
        if audit.file_hash(path)['sha256'] != expected_hash:
            raise ValueError('LIVE_INPUT_CHANGED_SINCE_CAPTURE:' + name)
    rows = json.loads(pinned(snapshot / 'published_price_rows.json', captured['sha256']['published_price_rows.json']))
    if current_rows() != rows:
        raise ValueError('FRESH_CRM_ROWS_DIFFER_FROM_CANDIDATE_CAPTURE')
    sys.path.insert(0, str(package / 'cloud/task088_v5_preview'))
    builder = load('kyiv_reviewed_builder', package / 'cloud/task088_v5_preview/build_preview.py')
    from uaart_market_prices import georgia_price_visible
    if {row['auto_number'] for row in rows if not georgia_price_visible(row)} != KYIV:
        raise ValueError('KYIV_SET_MISMATCH')
    result = builder.build(snapshot, work / 'candidate', 'https://www.uaart.com.ua',
        STAGE / 'fresh_route_observations.json', Path('/home/Carix/video'), Path('/home/Carix/site'))
    if result['missing_assets'] or result['missing_linked_pages']:
        raise ValueError('CANDIDATE_RESOURCES_MISSING')
    new_manifest = json.loads(base.checked_read(work / 'candidate/manifest.json', True))
    if set(old_manifest['files']) != set(new_manifest['files']):
        raise ValueError('PREVIEW_ROUTE_SET_CHANGED')
    changed = []
    marker = re.compile(br'<!-- UA-ART-MARKET-PRICES-V1:START -->.*?<!-- UA-ART-MARKET-PRICES-V1:END -->', re.S)
    for route, item in old_manifest['files'].items():
        new = new_manifest['files'][route]
        if item['sha256'] == new['sha256']:
            continue
        if route == '/__uaart_preview__/viewport.html':
            continue  # The canonical harness pins the new document hashes.
        old_bytes = pinned(STAGE / 'candidate' / item['path'], item['sha256'])
        new_bytes = pinned(work / 'candidate' / new['path'], new['sha256'])
        if marker.sub(b'<PRICE>', old_bytes) != marker.sub(b'<PRICE>', new_bytes):
            raise ValueError('NON_PRICE_PREVIEW_DIFF')
        changed.append(route)
    expected = {'/video/' + code + '.html' for code in KYIV} | {'/video/katalog.html'}
    if set(changed) != expected:
        raise ValueError('UNEXPECTED_CHANGED_PREVIEW_PAGE_SET')
    offline_changed = []
    for old in sorted((STAGE / 'candidate/offline').rglob('*.html')):
        relative = old.relative_to(STAGE / 'candidate')
        new = work / 'candidate' / relative
        before_html, after_html = base.checked_read(old, True), base.checked_read(new, True)
        if before_html != after_html:
            if marker.sub(b'<PRICE>', before_html) != marker.sub(b'<PRICE>', after_html):
                raise ValueError('NON_PRICE_OFFLINE_DIFF')
            offline_changed.append('/' + relative.relative_to('offline').as_posix())
    if set(offline_changed) != {p.replace('/video/', '/site/') for p in expected}:
        raise ValueError('UNEXPECTED_OFFLINE_DIFF')
    receipt = json.loads(base.checked_read(OLD_APP / 'PUBLIC_PROVISION_RECEIPT.json', True))
    expected_runtime = dict(base.RUNTIME, **{'wsgi_preview.py':
        'ba8188817fe309e42082024007ff892342283937a76a45fe8e3fcc2c975c2ee4'})
    if receipt['runtime_sha256'] != expected_runtime:
        raise ValueError('PUBLIC_RUNTIME_RECEIPT_DRIFT')
    runtime = work / 'runtime'; runtime.mkdir(mode=0o700)
    for name, expected_hash in receipt['runtime_sha256'].items():
        base.write_private(runtime / name, pinned(OLD_APP / 'runtime' / name, expected_hash))
    config = {'contract':'UA-ART-V5-PROTECTED-PREVIEW-1', 'preview_origin':base.ORIGIN,
              'bundle_root':str(work / 'candidate'), 'manifest_sha256':result['manifest_sha256'],
              'access_policy':'PUBLIC_READ_ONLY_PREVIEW_OWNER_AUTHORIZED'}
    config_path = work / 'config.json'; base.write_private(config_path, base.encode(config))
    sys.path.insert(0, str(runtime))
    preview = load('kyiv_reviewed_wsgi', runtime / 'wsgi_preview.py')
    verification = helper.verify_public_app(preview.Preview(config_path), base.DOMAIN)
    after = inventory(); base.write_private(work / 'protected_after.json', base.encode(after))
    if before != after or current_rows() != rows:
        raise ValueError('LIVE_PROTECTED_DATA_CHANGED_DURING_PREVIEW_BUILD')
    if base.host_state() != host:
        raise ValueError('PREVIEW_HOSTING_CHANGED')
    pinned(base.PRODUCTION, base.EXPECTED_PRODUCTION_WSGI)
    base.write_private(work / 'prior_preview_wsgi.backup.py', before_wsgi)
    code = ('# Owner-authorized Kyiv price visibility Preview\nimport os\nimport sys\n'
        'sys.dont_write_bytecode = True\n'
        'os.environ["UA_ART_PREVIEW_CONFIG"] = ' + repr(str(config_path)) + '\n'
        'sys.path.insert(0, ' + repr(str(runtime)) + ')\n'
        'from wsgi_entry import application\n').encode()
    compile(code, str(base.TARGET), 'exec')
    base.write_private(work / 'reviewed_wsgi.py', code)
    base.replace_new_preview_wsgi(base.TARGET, before_wsgi, code)
    output = {'status':'KYIV_PREVIEW_UPDATED_PENDING_BROWSER', 'recorded_at_utc':datetime.now(timezone.utc).isoformat(),
        'work':str(work), 'build':result, 'renderer_sha256':RENDERER_SHA,
        'changed_public_price_pages':sorted(changed), 'changed_offline_price_pages':sorted(offline_changed),
        'non_price_bytes_unchanged':True, 'fresh_crm_rows_match':True, 'all_live_protected_data_unchanged':True,
        'kyiv_cars':sorted(KYIV), 'verification':verification, 'wsgi_sha256':sha(code),
        'prior_preview_retained':str(STAGE / 'candidate'), 'backup':str(work / 'prior_preview_wsgi.backup.py'),
        'preview_gate':'NOT_PASSED', 'production_written':False, 'reload_requested':False}
    base.write_private(work / 'KYIV_PREVIEW_RECEIPT.json', base.encode(output))
    print(json.dumps(output, sort_keys=True))


if __name__ == '__main__':
    main()
