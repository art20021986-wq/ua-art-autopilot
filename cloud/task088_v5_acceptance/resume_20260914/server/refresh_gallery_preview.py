"""Rebuild only the retained dedicated Preview with the reviewed gallery fix.

Run from the pinned delivery .pyz using python3.10 -I -B and an independently
fresh quota JSON. No HTTP image requests or production writes. Retains a new
private work directory and an exact previous Preview WSGI backup; switches only
the dedicated Preview WSGI with compare-and-swap. Does not reload either app.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import types
import zipfile

PARENT = Path('/home/Carix/autopilot_inbox/cloud')
STAGE = PARENT / 'task088-v5-preview-stage-zlcw0vma'
OLD = STAGE / 'kyiv-preview-f3nbwi84'
BUILDER_SHA = 'ce6fb512f2b2c5dadb81c6412b1da28a43b8ba0d8b9d325f93c03833d9368cc9'
OLD_BUILDER_SHA = '9d9ae6caa4a33d3a717dee3f96c9d695b5977873edb5b3aa56fd891ee15f6ecc'
PACKAGE_SHA = 'faf3c49aae147df9d4ed140b03da54c7c6b1f531b12fefa19169cad040f347bd'
RENDERER_SHA = '35d9f212060b36b60c257db8da3ab1e6aed8b1905e1038cf33bc395b731332ed'
PRODUCTION_SHA = '3067d39ec9c2eb976114afc6744e2c34b088a8414e98eb3e33e0a47c1849e308'
GALLERY_ROUTES_SHA = '457df9c40064e7e5c5510d339e264e549ddfc4b1a2ae2bd2380c0501b46c2c74'
HELPERS = {
    'provision_preview_08fbf7a1.py': '206ec6f601a4997e2f1129f9e6deb158293b811ce188eba7eff6d02ce062d3f6',
    'provision_public_preview_1.py': '58c8cf3a3e25254ea6f978c79cb9004f519d59be75400cc2efbd8b6c326bda40',
    'check_preview_freshness_20260914_1545.py': 'f31949ba6efd759f2faab1e730dfa2210c9dd6f0eb3dcc1c1e926ae6cb041972',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def load(name, raw, path):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def pinned(path, expected, limit=4 * 1024 * 1024):
    if path.resolve(strict=True) != path or not path.is_file() or path.stat().st_size > limit:
        raise ValueError('EXACT_BOUNDED_FILE_REQUIRED')
    with open(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit or sha(raw) != expected:
        raise ValueError('REVIEWED_SOURCE_HASH_MISMATCH')
    return raw


def fresh_quota(path, required):
    if path.resolve(strict=True) != path or not path.is_file() or path.stat().st_size > 8192:
        raise ValueError('EXACT_QUOTA_FILE_REQUIRED')
    raw = path.read_bytes()
    q = json.loads(raw)
    stamp = datetime.datetime.fromisoformat(q['observed_at'].replace('Z', '+00:00'))
    age = (datetime.datetime.now(datetime.timezone.utc) - stamp).total_seconds()
    if (stamp.tzinfo is None or not 0 <= age <= 1800
            or q.get('source') != 'PYTHONANYWHERE_AUTHENTICATED_ACCOUNT' or q.get('account') != 'Carix'
            or type(q.get('used_bytes')) is not int or type(q.get('limit_bytes')) is not int
            or not 0 <= q['used_bytes'] < q['limit_bytes']
            or q['used_bytes'] + required > q['limit_bytes'] * 0.8
            or shutil.disk_usage(STAGE).free < required):
        raise ValueError('FRESH_AUTHENTICATED_QUOTA_AND_DISK_REQUIRED')
    return {'sha256': sha(raw), 'observed_at': q['observed_at'], 'required_private_bytes': required}


def require_inventory(check, audit, capture):
    result = check.inventory(audit, capture)
    if any(result[name]['status'] != 'OBSERVED' for name in ('db', 'html', 'sources', 'hosting')):
        raise ValueError('FULL_LIVE_READ_ONLY_INVENTORY_REQUIRED')
    return result


def require_captured(check, audit, capture):
    result = check.captured_binding(audit, capture)
    if (result['published_rows']['status'] != 'MATCH'
            or any(value != 'MATCH' for value in result['source_comparison'].values())):
        raise ValueError('CAPTURED_SOURCE_OR_CRM_DRIFT')
    return result


def baseline_inventory(value):
    return {name: value[name]['value'] for name in ('db', 'html', 'sources', 'hosting')}


def captured_gallery_routes(check):
    captured = json.loads(check.read(check.SNAPSHOT / 'capture_manifest.json', check.CAPTURE_SHA))['sha256']
    rows = json.loads(check.read(check.SNAPSHOT / 'published_price_rows.json', captured['published_price_rows.json']))
    routes = set()
    for row in rows:
        code = row['auto_number']
        if re.fullmatch(r'UA-[0-9]{4}', code) is None:
            raise ValueError('EXACT_CAPTURED_CAR_IDENTITY_REQUIRED')
        name = 'video/' + code + '.html'
        html = check.read(check.SNAPSHOT / name, captured[name]).decode('utf-8')
        declarations = re.findall(r'\b(?:var|let|const)\s+kadry\s*=\s*(\[.*?\])\s*;', html, re.S)
        if len(declarations) != 1:
            raise ValueError('ONE_CAPTURED_GALLERY_LITERAL_REQUIRED')
        paths = json.loads(declarations[0])
        if (type(paths) is not list or any(type(path) is not str
                or re.fullmatch(r'foto/' + code + r'/[0-9]{3}\.jpg', path) is None for path in paths)):
            raise ValueError('EXACT_CAPTURED_GALLERY_PHOTO_PATHS_REQUIRED')
        routes.update('/video/' + path for path in paths)
    if len(routes) != 560 or sha(check.encoded(sorted(routes))) != GALLERY_ROUTES_SHA:
        raise ValueError('INDEPENDENT_560_GALLERY_ROUTE_BINDING_REQUIRED')
    return routes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--quota-json', required=True)
    args = parser.parse_args()
    work = None
    switched = False
    switch_attempted = False
    old_wsgi = candidate_wsgi = None
    result = {'kind': 'DEDICATED_PREVIEW_GALLERY_MANIFEST_REFRESH', 'started_at_utc': now(),
        'production_written': False, 'crm_written': False, 'reload_requested': False,
        'http_image_requests': 0, 'preview_gate': 'NOT_PASSED', 'full_preview': 'NOT_PASSED'}
    try:
        if not sys.flags.isolated or not sys.dont_write_bytecode:
            raise ValueError('PYTHON_ISOLATED_NO_BYTECODE_REQUIRED')
        modules = {name: load('gallery_' + name[:-3], pinned(PARENT / name, expected), PARENT / name)
                   for name, expected in HELPERS.items()}
        base = modules['provision_preview_08fbf7a1.py']
        public = modules['provision_public_preview_1.py']
        check = modules['check_preview_freshness_20260914_1545.py']
        if STAGE.resolve(strict=True) != STAGE or stat.S_IMODE(STAGE.stat().st_mode) != 0o700:
            raise ValueError('EXACT_PRIVATE_STAGE_REQUIRED')
        archive = Path(sys.argv[0]).absolute()
        if archive.resolve(strict=True) != archive or archive.parent != PARENT:
            raise ValueError('EXACT_PRIVATE_DELIVERY_ARCHIVE_REQUIRED')
        with zipfile.ZipFile(archive) as packed:
            if sorted(packed.namelist()) != ['__main__.py', 'build_preview.py']:
                raise ValueError('EXACT_GALLERY_DELIVERY_CLOSURE_REQUIRED')
            builder_raw = packed.read('build_preview.py')
        if sha(builder_raw) != BUILDER_SHA:
            raise ValueError('REVIEWED_GALLERY_BUILDER_REQUIRED')
        compile(builder_raw, 'build_preview.py', 'exec')
        audit = check.load_helper('run_private_server_build.py')
        capture = check.load_helper('capture_private_snapshot.py')
        old_binding = check.preview_binding(audit)
        if old_binding['status'] != 'MATCH':
            raise ValueError('PREVIOUS_PREVIEW_BINDING_DRIFT')
        old_wsgi = pinned(check.WSGI, check.WSGI_SHA)
        pinned(base.PRODUCTION, PRODUCTION_SHA)
        host_before = base.host_state()
        before = require_inventory(check, audit, capture)
        captured = require_captured(check, audit, capture)
        gallery_routes = captured_gallery_routes(check)
        old_manifest = json.loads(check.read(check.BUNDLE / 'manifest.json', check.MANIFEST_SHA))
        original_package = json.loads(pinned(STAGE / 'package/package_manifest.json', PACKAGE_SHA))
        entries = original_package['sha256']
        if not 0 < len(entries) < 40:
            raise ValueError('BOUNDED_ORIGINAL_PACKAGE_REQUIRED')
        payload = {}
        builder_name = 'cloud/task088_v5_preview/build_preview.py'
        for name, expected in entries.items():
            check.relative(name)
            if name == 'cloud/task088_stage3_renderer/uaart_market_prices.py':
                expected = RENDERER_SHA
            payload[name] = pinned(OLD / 'package' / name, expected)
        if sha(payload[builder_name]) != OLD_BUILDER_SHA:
            raise ValueError('ORIGINAL_BUILDER_REQUIRED')
        payload[builder_name] = builder_raw
        required = 3 * (sum(len(raw) for raw in payload.values())
                       + sum(item['bytes'] for item in old_manifest['files'].values() if item['storage'] == 'bundle')) + 32 * 1024 * 1024
        quota = fresh_quota(Path(args.quota_json).absolute(), required)
        work = Path(tempfile.mkdtemp(prefix='gallery-preview-', dir=STAGE))
        result['work'] = str(work)
        package = work / 'package'
        for name, raw in payload.items():
            target = package / name
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            base.write_private(target, raw)
            pinned(target, sha(raw))
        base.write_private(work / 'package_manifest.json', base.encode({'sha256': {n: sha(b) for n, b in payload.items()}}))
        base.write_private(work / 'protected_before.json', base.encode(baseline_inventory(before)))
        sys.path.insert(0, str(package / 'cloud/task088_v5_preview'))
        builder = load('gallery_reviewed_builder', builder_raw, package / builder_name)
        built = builder.build(check.SNAPSHOT, work / 'candidate', 'https://www.uaart.com.ua',
                              STAGE / 'fresh_route_observations.json', Path('/home/Carix/video'), Path('/home/Carix/site'))
        if built['missing_assets'] or built['missing_linked_pages'] or built['served_pages'] != 20 or built['unchanged_linked_pages'] != 20:
            raise ValueError('COMPLETE_UNCHANGED_PREVIEW_PAGE_SET_REQUIRED')
        new_manifest = json.loads(check.read(work / 'candidate/manifest.json', built['manifest_sha256']))
        old_files, new_files = old_manifest['files'], new_manifest['files']
        if not set(old_files) < set(new_files):
            raise ValueError('ADDITIONAL_GALLERY_ASSETS_REQUIRED')
        for route, item in old_files.items():
            if new_files[route] != item:
                raise ValueError('PREEXISTING_PREVIEW_RESOURCE_CHANGED')
            if item['storage'] == 'bundle':
                if check.read(check.BUNDLE / item['path'], item['sha256']) != check.read(work / 'candidate' / item['path'], item['sha256']):
                    raise ValueError('PREEXISTING_PUBLIC_BYTES_CHANGED')
        added = sorted(set(new_files) - set(old_files))
        if len(added) != 542 or set(added) != gallery_routes - set(old_files):
            raise ValueError('EXACT_542_CAPTURED_GALLERY_ADDITIONS_REQUIRED')
        for route in added:
            item = new_files[route]
            if (not re.fullmatch(r'/video/foto/UA-[0-9]{4}/[0-9]{3}\.jpg', route)
                    or item.get('storage') != 'asset' or item.get('root') != 'video'
                    or item.get('path') != route.removeprefix('/video/') or item.get('content_type') != 'image/jpeg'):
                raise ValueError('ONLY_EXPLICIT_GALLERY_JPEG_ADDITIONS_ALLOWED')
        old_offline = {str(p.relative_to(check.BUNDLE / 'offline')): check.read(p) for p in (check.BUNDLE / 'offline').rglob('*.html')}
        new_offline = {str(p.relative_to(work / 'candidate/offline')): check.read(p) for p in (work / 'candidate/offline').rglob('*.html')}
        if len(old_offline) != 19 or old_offline != new_offline:
            raise ValueError('OFFLINE_PROTECTED_HTML_CHANGED')
        runtime = work / 'runtime'
        runtime.mkdir(mode=0o700)
        for name, expected in check.RUNTIME.items():
            base.write_private(runtime / name, pinned(OLD / 'runtime' / name, expected))
        config_path = work / 'config.json'
        config = dict(check.CONFIG, bundle_root=str(work / 'candidate'), manifest_sha256=built['manifest_sha256'])
        base.write_private(config_path, base.encode(config))
        sys.path.insert(0, str(runtime))
        preview = load('gallery_reviewed_preview', pinned(runtime / 'wsgi_preview.py', check.RUNTIME['wsgi_preview.py']), runtime / 'wsgi_preview.py')
        verification = public.verify_public_app(preview.Preview(config_path), base.DOMAIN)
        after = require_inventory(check, audit, capture)
        base.write_private(work / 'protected_after.json', base.encode(baseline_inventory(after)))
        if any(value != 'MATCH' for value in check.compare(before, after).values()) or require_captured(check, audit, capture) != captured:
            raise ValueError('LIVE_STATE_CHANGED_DURING_PRIVATE_BUILD')
        if base.host_state() != host_before:
            raise ValueError('PREVIEW_HOST_CONFIGURATION_DRIFT')
        fresh_quota(Path(args.quota_json).absolute(), 1024 * 1024)
        pinned(base.PRODUCTION, PRODUCTION_SHA)
        pinned(check.WSGI, check.WSGI_SHA)
        base.write_private(work / 'prior_preview_wsgi.backup.py', old_wsgi)
        candidate_wsgi = ('# Owner-authorized Preview gallery asset manifest refresh\nimport os\nimport sys\n'
            'sys.dont_write_bytecode = True\n'
            'os.environ["UA_ART_PREVIEW_CONFIG"] = ' + repr(str(config_path)) + '\n'
            'sys.path.insert(0, ' + repr(str(runtime)) + ')\n'
            'from wsgi_entry import application\n').encode()
        compile(candidate_wsgi, str(check.WSGI), 'exec')
        base.write_private(work / 'reviewed_wsgi.py', candidate_wsgi)
        switch_attempted = True
        base.replace_new_preview_wsgi(check.WSGI, old_wsgi, candidate_wsgi)
        switched = True
        pinned(check.WSGI, sha(candidate_wsgi))
        pinned(base.PRODUCTION, PRODUCTION_SHA)
        final = require_inventory(check, audit, capture)
        if any(value != 'MATCH' for value in check.compare(before, final).values()) or base.host_state() != host_before:
            raise ValueError('POST_SWITCH_LIVE_OR_HOST_STATE_DRIFT')
        base.write_private(work / 'protected_after_switch.json', base.encode(baseline_inventory(final)))
        result.update(status='PREVIEW_ONLY_UPDATED_PENDING_RELOAD_AND_BROWSER', build=built,
            builder_sha256=BUILDER_SHA, added_gallery_assets=len(added), added_gallery_routes=added,
            captured_gallery_routes_sha256=GALLERY_ROUTES_SHA, captured_gallery_routes=560,
            old_manifest_sha256=check.MANIFEST_SHA, manifest_sha256=built['manifest_sha256'],
            config_sha256=sha(base.encode(config)), runtime_sha256=check.RUNTIME,
            old_wsgi_sha256=check.WSGI_SHA, wsgi_sha256=sha(candidate_wsgi),
            backup=str(work / 'prior_preview_wsgi.backup.py'), all_existing_resources_unchanged=len(old_files),
            price_pages_unchanged=20, linked_pages_unchanged=20, offline_pages_unchanged=19,
            protected_state_comparison=check.compare(before, final), verification=verification, quota=quota,
            finished_at_utc=now())
        base.write_private(work / 'GALLERY_PREVIEW_RECEIPT.json', base.encode(result))
    except Exception as error:
        message = str(error)
        result.update(status='PREVIEW_REFRESH_INCOMPLETE', error_type=type(error).__name__,
            code=message if re.fullmatch('[A-Z0-9_]{1,120}', message) else 'REDACTED_ERROR_MESSAGE', finished_at_utc=now())
        if switch_attempted and not switched:
            try:
                current_wsgi = base.checked_read(check.WSGI)
                switched = current_wsgi == candidate_wsgi
                if current_wsgi != old_wsgi and not switched:
                    result['preview_write_state'] = 'UNKNOWN_PARTIAL_OR_FOREIGN_CHANGE_REQUIRES_REVIEW'
            except Exception:
                result['preview_write_state'] = 'UNOBSERVED_AFTER_SWITCH_ATTEMPT'
        if switched:
            try:
                base.replace_new_preview_wsgi(check.WSGI, candidate_wsgi, old_wsgi)
                pinned(check.WSGI, check.WSGI_SHA)
                result['preview_rollback'] = 'RESTORED_PREVIOUS_EXACT_WSGI'
            except Exception as rollback_error:
                result['preview_rollback'] = 'FAILED_OR_FOREIGN_CHANGE_REQUIRES_REVIEW'
                result['rollback_error_type'] = type(rollback_error).__name__
        result['dedicated_preview_wsgi_changed'] = ('UNVERIFIED' if 'preview_write_state' in result
            else switched and result.get('preview_rollback') != 'RESTORED_PREVIOUS_EXACT_WSGI')
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(',', ':')))
    return 0 if result['status'] == 'PREVIEW_ONLY_UPDATED_PENDING_RELOAD_AND_BROWSER' else 1


if __name__ == '__main__':
    raise SystemExit(main())
