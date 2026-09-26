"""Read back the exact retained Kyiv Preview and protected live state.

Run with python3 -I -B. No server files, processes, CRM rows, or gates are
changed. Stdout is one sanitized JSON receipt; the caller preserves it.
"""
import sys
sys.dont_write_bytecode = True
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import types

ROOT = Path('/home/Carix')
STAGE = ROOT / 'autopilot_inbox/cloud/task088-v5-preview-stage-zlcw0vma'
WORK = STAGE / 'kyiv-preview-f3nbwi84'
BUNDLE = WORK / 'candidate'
SNAPSHOT = STAGE / 'snapshot'
MANIFEST_SHA = '7c5335f921487734c5af8a94df49d1ba04ba6f5bf97492d346ab619b7205fb28'
CAPTURE_SHA = '1e9be2779e1c6f7b508ed58e947a74d789b23fa9895bb865fa106f4671bb40bf'
WSGI = Path('/var/www/carix_pythonanywhere_com_wsgi.py')
WSGI_SHA = '17a74d0ad564992d698ffeed5a4472ec11f6b170f0fe757feeb4e15b93bc3460'
HELPERS = {
    'run_private_server_build.py': 'fe4ccd7ebb805f559722641cd24cc3f098ede1904b61ee15cd218a4fd52a790b',
    'capture_private_snapshot.py': '320576438dfb4c4128c2fd36f35603a22b2960f998632df8056c47a07d8cffd2',
}
RUNTIME = {
    'common.py': 'cb30a2b61d28438a9844e79b1bc8550f92885dab8b6dc0d76c2789827c9893fa',
    'routing_proof.py': 'fd483b95d5b0a2bc92146d1c137decb9e368706248b7469c9c1243a3fd622c5d',
    'viewport_harness.py': '3b6830eff2d35ed94688707018e606b0d404a00bcb4dce80fa0dadab89b0bae1',
    'wsgi_entry.py': '7b7b9056b55c41a5031e430cf470b10ae66fd812f792a3cd65cb931c1ced02e7',
    'wsgi_preview.py': 'ba8188817fe309e42082024007ff892342283937a76a45fe8e3fcc2c975c2ee4',
}
CONFIG = {
    'contract': 'UA-ART-V5-PROTECTED-PREVIEW-1',
    'preview_origin': 'https://carix.pythonanywhere.com',
    'bundle_root': str(BUNDLE), 'manifest_sha256': MANIFEST_SHA,
    'access_policy': 'PUBLIC_READ_ONLY_PREVIEW_OWNER_AUTHORIZED',
}


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def checked_path(path):
    if path.resolve(strict=True) != path or any(p.name.startswith('.') for p in path.parents if p.name):
        raise ValueError('EXACT_NONHIDDEN_REGULAR_PATH_REQUIRED')
    if path.name.startswith('.') or not path.is_file():
        raise ValueError('EXACT_NONHIDDEN_REGULAR_PATH_REQUIRED')
    return path


def read(path, expected=None, limit=32 * 1024 * 1024):
    checked_path(path)
    with open(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError('REGULAR_BOUNDED_FILE_REQUIRED')
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        if (before.st_ino, before.st_mtime_ns, before.st_size) != (after.st_ino, after.st_mtime_ns, after.st_size):
            raise ValueError('FILE_CHANGED_DURING_READ')
    if expected is not None and sha(raw) != expected:
        raise ValueError('PINNED_FILE_HASH_MISMATCH')
    return raw


def load_helper(name):
    path = STAGE / 'package/cloud/task088_v5_acceptance' / name
    raw = read(path, HELPERS[name], 128 * 1024)
    module = types.ModuleType('reviewed_' + path.stem)
    module.__file__ = str(path)
    # Execute the already verified bytes, avoiding a second import-time read.
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def observed(call):
    try:
        return {'status': 'OBSERVED', 'value': call()}
    except Exception as error:
        message = str(error)
        return {'status': 'NOT_OBSERVED', 'error_type': type(error).__name__,
                'code': message if re.fullmatch('[A-Z0-9_]{1,120}', message) else 'REDACTED_ERROR_MESSAGE'}


def public_html(audit):
    # The reviewed inventory scans only HTML under the three public roots.
    # Refuse hidden HTML/subtrees before that helper could hash any such file.
    if any(path.name.startswith('.') for path in ROOT.glob('*.html')):
        raise ValueError('HIDDEN_PUBLIC_HTML_REQUIRES_REVIEW')
    for folder in ('video', 'site'):
        for directory, dirs, files in os.walk(ROOT / folder, followlinks=False):
            if any(name.startswith('.') for name in dirs):
                raise ValueError('HIDDEN_PUBLIC_SUBTREE_REQUIRES_REVIEW')
            if any(name.startswith('.') and name.lower().endswith('.html') for name in files):
                raise ValueError('HIDDEN_PUBLIC_HTML_REQUIRES_REVIEW')
    return audit.html_inventory()


def inventory(audit, capture):
    return {'observed_at_utc': now(),
            'db': observed(audit.database_inventory),
            'html': observed(lambda: public_html(audit)),
            'sources': observed(lambda: audit.source_inventory(capture.SOURCE_NAMES)),
            'hosting': observed(audit.hosting_inventory)}


def current_rows():
    connection = sqlite3.connect('file:/home/Carix/crm.db?mode=ro', uri=True, timeout=10)
    connection.execute('PRAGMA query_only=ON')
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('BEGIN')
        return [dict(row) for row in connection.execute(
            'SELECT id,auto_number,price_uah,price_georgia,status,published FROM cars WHERE published=1 ORDER BY id')]
    finally:
        connection.rollback()
        connection.close()


def compare(before, after):
    selectors = {'db_schema': ('db', 'schema_sha256'), 'all_db_tables': ('db', 'tables'),
                 'all_live_html': ('html', 'files'), 'live_sources': ('sources', 'files'),
                 'production_static_mappings': ('hosting', 'static_mappings')}
    result = {}
    for label, (component, field) in selectors.items():
        a, b = before.get(component, {}), after.get(component, {})
        if a.get('status') != 'OBSERVED' or b.get('status') != 'OBSERVED':
            result[label] = 'NOT_OBSERVED'
        else:
            result[label] = 'MATCH' if a['value'][field] == b['value'][field] else 'MISMATCH'
    return result


def baseline(path, current):
    raw = read(path, limit=4 * 1024 * 1024)
    data = json.loads(raw)
    wrapped = {key: {'status': 'OBSERVED', 'value': data[key]}
               for key in ('db', 'html', 'sources', 'hosting')}
    return {'path': str(path), 'sha256': sha(raw),
            'baseline_pin': 'PREEXISTING_REPORT_HASH_RECORDED_NOW',
            'comparison': compare(wrapped, current)}


def relative(value):
    if (type(value) is not str or not value or str(PurePosixPath(value)) != value
            or value.startswith('/') or '\\' in value or '%' in value or '\x00' in value
            or any(part in ('', '.', '..') or part.startswith('.') for part in value.split('/'))):
        raise ValueError('EXACT_NONHIDDEN_RELATIVE_PATH_REQUIRED')
    return value


def preview_binding(audit):
    manifest = json.loads(read(BUNDLE / 'manifest.json', MANIFEST_SHA))
    read(BUNDLE / 'provenance.json', manifest['provenance_sha256'])
    config = read(WORK / 'config.json', sha(encoded(CONFIG)), 4096)
    if json.loads(config) != CONFIG or manifest.get('preview_gate') != 'NOT_PASSED':
        raise ValueError('EXACT_PUBLIC_PREVIEW_CONFIG_REQUIRED')
    read(WSGI, WSGI_SHA, 4096)
    for name, expected in RUNTIME.items():
        read(WORK / 'runtime' / name, expected, 256 * 1024)
    if manifest['asset_roots'] != {'video': '/home/Carix/video', 'site': '/home/Carix/site'}:
        raise ValueError('EXACT_PUBLIC_ASSET_ROOTS_REQUIRED')
    files = manifest['files']
    if type(files) is not dict or len(files) != 679:
        raise ValueError('EXACT_679_RESOURCE_MANIFEST_REQUIRED')
    mismatches = []
    for route, item in sorted(files.items()):
        route_relative = relative(route[1:]) if route.startswith('/') else relative('')
        item_relative = relative(item['path'])
        if item['storage'] == 'bundle' and item_relative == 'public/' + route_relative:
            path = BUNDLE / item_relative
        elif (item['storage'] == 'asset' and item.get('root') in ('video', 'site')
              and route_relative == item['root'] + '/' + item_relative
              and Path(item_relative).suffix.lower() not in ('.py', '.db', '.json', '.html')):
            path = ROOT / item['root'] / item_relative
        else:
            raise ValueError('EXACT_MANIFEST_RESOURCE_MAPPING_REQUIRED')
        result = observed(lambda: audit.file_hash(checked_path(path)))
        if result.get('value') != {'sha256': item['sha256'], 'bytes': item['bytes']}:
            mismatches.append({'path': route, 'status': 'MISMATCH' if result['status'] == 'OBSERVED' else 'NOT_OBSERVED'})
    return {'status': 'MATCH' if not mismatches else 'MISMATCH', 'manifest_sha256': MANIFEST_SHA,
            'config_sha256': sha(config), 'wsgi_sha256': WSGI_SHA, 'runtime_sha256': RUNTIME,
            'resources_checked': len(files), 'resource_mismatches': mismatches}


def captured_binding(audit, capture):
    manifest = json.loads(read(SNAPSHOT / 'capture_manifest.json', CAPTURE_SHA))
    hashes = manifest['sha256']
    captured = json.loads(read(SNAPSHOT / 'published_price_rows.json', hashes['published_price_rows.json']))
    rows = current_rows()
    sources = {}
    for name in (*capture.SOURCE_NAMES, 'observed_wsgi_config.py'):
        path = Path('/var/www/www_uaart_com_ua_wsgi.py') if name == 'observed_wsgi_config.py' else ROOT / name
        expected = hashes.get(name)
        if expected is None:
            sources[name] = 'CAPTURE_NOT_PRESENT'
        else:
            result = observed(lambda: audit.file_hash(checked_path(path)))
            sources[name] = ('MATCH' if result['value']['sha256'] == expected else 'MISMATCH') if result['status'] == 'OBSERVED' else 'NOT_OBSERVED'
    return {'capture_manifest_sha256': CAPTURE_SHA, 'source_comparison': sources,
            'published_rows': {'status': 'MATCH' if rows == captured else 'MISMATCH',
                'captured_count': len(captured), 'current_count': len(rows),
                'captured_rows_sha256': sha(encoded(captured)), 'current_rows_sha256': sha(encoded(rows)),
                'query_only': True, 'row_values_exported': False}}


def main():
    report = {'kind': 'READ_ONLY_PREVIEW_FRESHNESS_READBACK', 'readback_only': True,
              'started_at_utc': now(), 'preview_gate': 'NOT_PASSED', 'full_preview': 'NOT_PASSED',
              'production_written': False, 'crm_written': False, 'server_files_written': False,
              'stage': str(STAGE), 'work': str(WORK)}
    try:
        if not sys.flags.isolated or not sys.dont_write_bytecode:
            raise ValueError('PYTHON_ISOLATED_NO_BYTECODE_REQUIRED')
        audit = load_helper('run_private_server_build.py')
        capture = load_helper('capture_private_snapshot.py')
        report['helper_sha256'] = HELPERS
        before = inventory(audit, capture)
        report['captured_binding_before'] = observed(lambda: captured_binding(audit, capture))
        report['preview_binding'] = observed(lambda: preview_binding(audit))
        report['captured_binding_after'] = observed(lambda: captured_binding(audit, capture))
        after = inventory(audit, capture)
        report['during_observation'] = compare(before, after)
        report['before_inventory_sha256'] = sha(encoded(before))
        report['current_inventory'] = after
        report['since_preview'] = {
            'kyiv_preview': observed(lambda: baseline(WORK / 'protected_after.json', after)),
            'original_preview': observed(lambda: baseline(STAGE / 'protected_after.json', after)),
        }
        report['status'] = 'READBACK_COMPLETE_REVIEW_MATCHES_AND_DRIFT'
    except Exception as error:
        report['status'] = 'READBACK_INCOMPLETE'
        report['failure'] = observed(lambda: (_ for _ in ()).throw(error))
    report['finished_at_utc'] = now()
    print(json.dumps(report, sort_keys=True, separators=(',', ':'), ensure_ascii=True))
    return 0 if report['status'] == 'READBACK_COMPLETE_REVIEW_MATCHES_AND_DRIFT' else 1


if __name__ == '__main__':
    raise SystemExit(main())
