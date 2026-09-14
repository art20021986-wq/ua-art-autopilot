"""Build a fresh private Preview on Carix; no live writes or live imports.

Invoked only by the reviewed ZIP launcher, inside its newly created 0700 stage.
All detailed evidence remains private. Stdout contains hashes/counts/statuses.
"""
import sys
sys.dont_write_bytecode = True
import contextlib
import datetime
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import struct
import urllib.request
import zipfile

ROOT = Path('/home/Carix')
PARENT = ROOT / 'autopilot_inbox/cloud'


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    raw = encoded(value)
    with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return digest(raw)


def file_hash(path):
    with open(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('REGULAR_FILE_REQUIRED')
        value = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise ValueError('FILE_CHANGED_DURING_HASH')
    return {'sha256': value.hexdigest(), 'bytes': before.st_size}


def db_value(value):
    if value is None: return ['null']
    if isinstance(value, bytes): return ['blob', value.hex()]
    if isinstance(value, str): return ['text', value]
    if isinstance(value, int): return ['integer', str(value)]
    if isinstance(value, float): return ['real_ieee754', struct.pack('!d', value).hex()]
    raise ValueError('UNKNOWN_SQLITE_VALUE_TYPE')


def database_inventory():
    # One independent read-only transaction per observation. Values are never
    # logged; duplicate rows are preserved in the sorted digest multiset.
    connection = sqlite3.connect('file:/home/Carix/crm.db?mode=ro', uri=True, timeout=10)
    connection.execute('PRAGMA query_only=ON')
    connection.text_factory = lambda raw: raw.decode('utf-8', 'surrogateescape')
    try:
        connection.execute('BEGIN')
        schema = list(connection.execute('SELECT type,name,tbl_name,rootpage,sql FROM sqlite_master ORDER BY type,name,tbl_name'))
        tables = {}
        for name, in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            quoted = '"' + name.replace('"', '""') + '"'
            cursor = connection.execute('SELECT * FROM ' + quoted)
            columns = [item[0] for item in cursor.description]
            hashes = [digest(json.dumps([db_value(value) for value in row],
                ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode()) for row in cursor]
            tables[name] = {'rows': len(hashes), 'columns_sha256': digest(encoded(columns)),
                            'rows_sha256': digest(encoded(sorted(hashes)))}
        return {'schema_sha256': digest(encoded(schema)), 'tables': tables,
                'tables_sha256': digest(encoded(tables)), 'query_only': True}
    finally:
        connection.rollback()
        connection.close()


def html_inventory():
    paths = list(ROOT.glob('*.html'))
    for folder in ('video', 'site'):
        base = ROOT / folder
        if base.is_symlink() or not base.is_dir():
            raise ValueError('REGULAR_PUBLIC_ROOT_REQUIRED')
        for directory, dirs, files in os.walk(base, followlinks=False):
            if any((Path(directory) / name).is_symlink() for name in dirs):
                raise ValueError('LIVE_HTML_DIRECTORY_SYMLINK_REQUIRES_REVIEW')
            paths.extend(Path(directory) / name for name in files if name.lower().endswith('.html'))
    if len(paths) > 20000:
        raise ValueError('HTML_INVENTORY_BOUND_EXCEEDED')
    files = {str(path.relative_to(ROOT)): file_hash(path) for path in sorted(paths)}
    return {'files': files, 'count': len(files), 'sha256': digest(encoded(files))}


def source_inventory(names):
    paths = [(name, ROOT / name) for name in names]
    paths.append(('observed_wsgi_config.py', Path('/var/www/www_uaart_com_ua_wsgi.py')))
    files = {name: file_hash(path) if path.exists() else {'missing': True} for name, path in paths}
    return {'files': files, 'sha256': digest(encoded(files))}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('HOSTING_REDIRECT_FORBIDDEN')


def hosting_inventory():
    token = os.environ.get('API_TOKEN', '')
    if not token: raise ValueError('EXISTING_HOSTING_API_TOKEN_REQUIRED')
    request = urllib.request.Request(
        'https://www.pythonanywhere.com/api/v0/user/Carix/webapps/www.uaart.com.ua/static_files/',
        headers={'Authorization': 'Token ' + token}, method='GET')
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024: raise ValueError('HOSTING_RESPONSE_TOO_LARGE')
    data = json.loads(raw)
    if type(data) is not list: raise ValueError('HOSTING_LIST_REQUIRED')
    mappings = sorted([{'url': item['url'], 'directory': item['path']} for item in data], key=lambda x: x['url'])
    return {'static_mappings': mappings, 'sha256': digest(encoded(mappings))}


def capture_public_analytics(snapshot, manifest, original_archive_sha256, stage):
    """Capture the exact existing GET response; never call the event endpoint."""
    url = 'https://www.uaart.com.ua/ua/a.js'
    started_at = now()
    request = urllib.request.Request(url, headers={'Accept': 'application/javascript'}, method='GET')
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError('PUBLIC_ANALYTICS_EXACT_200_REQUIRED')
        content_type = response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
        if content_type not in ('application/javascript', 'text/javascript'):
            raise ValueError('PUBLIC_ANALYTICS_JAVASCRIPT_MIME_REQUIRED')
        raw = response.read(1024 * 1024 + 1)
    if not raw or len(raw) > 1024 * 1024:
        raise ValueError('PUBLIC_ANALYTICS_NONEMPTY_BOUNDED_BYTES_REQUIRED')
    receipt = {'url': url, 'method': 'GET', 'status': 200, 'content_type': content_type,
        'started_at_utc': started_at, 'finished_at_utc': now(), 'bytes': len(raw), 'sha256': digest(raw),
        'captured_path': 'ua/a.js', 'source_wrapper_sha256': manifest['sha256']['analitika_wsgi.py'],
        'original_capture_archive_sha256': original_archive_sha256, 'redirect_followed': False,
        'event_endpoint_called': False}
    target = snapshot / 'ua/a.js'
    target.parent.mkdir(mode=0o700)
    with open(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as output:
        output.write(raw)
    expanded = dict(manifest, sha256=dict(manifest['sha256'], **{'ua/a.js': digest(raw)}),
        original_capture_archive_sha256=original_archive_sha256, public_response_reads=[receipt])
    expanded_manifest_sha256 = save(snapshot / 'capture_manifest.expanded.json', expanded)
    # Only this newly extracted private snapshot changes; the original ZIP is
    # retained byte-for-byte and keeps its separately reported original hash.
    os.replace(snapshot / 'capture_manifest.expanded.json', snapshot / 'capture_manifest.json')
    expanded_archive = stage / 'task088-v5-private-expanded.zip'
    with open(os.open(expanded_archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as stream:
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as output:
            for name in sorted(set(expanded['sha256']) | {'capture_manifest.json'}):
                output.write(snapshot / name, name)
    result = {'archive': str(expanded_archive), 'archive_sha256': file_hash(expanded_archive)['sha256'],
              'manifest_sha256': expanded_manifest_sha256, 'public_response_read': receipt}
    save(stage / 'expanded_capture_receipt.json', result)
    return expanded, result


def extract_capture(archive, target):
    target.mkdir(mode=0o700)
    names = set()
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            name = item.filename
            if (name in names or name.startswith('/') or '\\' in name or '\x00' in name
                    or str(PurePosixPath(name)) != name or any(p in ('', '.', '..') for p in name.split('/'))
                    or item.is_dir() or stat.S_ISLNK(item.external_attr >> 16) or item.file_size > 32 * 1024 * 1024):
                raise ValueError('CAPTURE_ARCHIVE_PATH_OR_SIZE_INVALID')
            names.add(name)
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            raw = source.read(item)
            with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as output:
                output.write(raw)
    manifest = json.loads((target / 'capture_manifest.json').read_bytes())
    if names != set(manifest['sha256']) | {'capture_manifest.json'}:
        raise ValueError('CAPTURE_MANIFEST_CLOSURE_MISMATCH')
    if any(file_hash(target / name)['sha256'] != expected for name, expected in manifest['sha256'].items()):
        raise ValueError('CAPTURE_MANIFEST_HASH_MISMATCH')
    return manifest


def load_module(name, path):
    # Only reviewed package code from this private ZIP extraction is imported.
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(stage):
    stage = Path(stage)
    if (stage.parent != PARENT or not stage.name.startswith('task088-v5-preview-stage-')
            or stage.resolve(strict=True) != stage or stat.S_IMODE(stage.stat().st_mode) != 0o700):
        raise ValueError('NEW_PRIVATE_STAGE_REQUIRED')
    package = stage / 'package'
    capture = load_module('task088_reviewed_capture', package / 'cloud/task088_v5_acceptance/capture_private_snapshot.py')
    capture.STAGING = stage
    started = now()
    before = {'observed_at_utc': now(), 'db': database_inventory(), 'html': html_inventory(),
              'sources': source_inventory(capture.SOURCE_NAMES), 'hosting': hosting_inventory()}
    save(stage / 'protected_before.json', before)
    build_result, capture_result, expanded_capture, failure, after = None, None, None, None, None
    try:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer): capture.main()
        capture_result = json.loads(buffer.getvalue())
        archive = Path(capture_result['archive'])
        if archive.parent != stage or file_hash(archive)['sha256'] != capture_result['sha256']:
            raise ValueError('PRIVATE_CAPTURE_PATH_OR_HASH_MISMATCH')
        snapshot = stage / 'snapshot'
        manifest = extract_capture(archive, snapshot)
        manifest, expanded_capture = capture_public_analytics(snapshot, manifest, capture_result['sha256'], stage)
        routes = json.loads((package / 'cloud/task088_v5_acceptance/route_observations.json').read_bytes())
        if before['hosting']['static_mappings'] != routes['static_mappings']:
            raise ValueError('CURRENT_PRODUCTION_STATIC_MAPPING_DRIFT')
        routes['prior_observed_at_utc'] = routes['observed_at_utc']
        routes['observed_at_utc'] = now()
        routes['report_kind'] = 'FRESH_READ_ONLY_API_MAPPING_AND_EXACT_REVIEWED_WSGI_SOURCE_PROOF'
        routes['original_source_capture_sha256'] = capture_result['sha256']
        routes['source_capture_sha256'] = expanded_capture['archive_sha256']
        routes['source_capture_manifest_sha256'] = expanded_capture['manifest_sha256']
        routes['public_response_reads'] = [expanded_capture['public_response_read']]
        routes['source_sha256'] = {name: manifest['sha256'][name] for name in routes['source_sha256']}
        routes['route_response_observation'] = 'BASE_REDIRECT_PROVEN_FROM_PINNED_SOURCE_ANALYTICS_GET_RECORDED_SEPARATELY'
        save(stage / 'fresh_route_observations.json', routes)
        sys.path.insert(0, str(package / 'cloud/task088_v5_preview'))
        builder = load_module('task088_reviewed_builder', package / 'cloud/task088_v5_preview/build_preview.py')
        build_result = builder.build(snapshot, stage / 'candidate', 'https://www.uaart.com.ua',
            stage / 'fresh_route_observations.json', ROOT / 'video', ROOT / 'site')
        save(stage / 'build_result.json', build_result)
    except Exception as error:
        message = str(error).split(':', 1)[0]
        failure = {'type': type(error).__name__,
                   'code': message if re.fullmatch('[A-Z0-9_]{1,120}', message) else 'REDACTED_ERROR_MESSAGE'}
    finally:
        after = {'observed_at_utc': now(), 'db': database_inventory(), 'html': html_inventory(),
                 'sources': source_inventory(capture.SOURCE_NAMES), 'hosting': hosting_inventory()}
        save(stage / 'protected_after.json', after)
    checks = {
        'db_schema': before['db']['schema_sha256'] == after['db']['schema_sha256'],
        'all_db_tables': before['db']['tables'] == after['db']['tables'],
        'all_live_html': before['html']['files'] == after['html']['files'],
        'live_sources': before['sources']['files'] == after['sources']['files'],
        'production_static_mappings': before['hosting']['static_mappings'] == after['hosting']['static_mappings'],
    }
    protection = all(checks.values())
    result = {'kind': 'PRIVATE_READ_ONLY_SERVER_PREVIEW_BUILD', 'started_at_utc': started,
        'finished_at_utc': now(), 'stage': str(stage), 'archive_sha256': capture_result['sha256'] if capture_result else None,
        'expanded_capture_archive_sha256': expanded_capture['archive_sha256'] if expanded_capture else None,
        'expanded_capture_manifest_sha256': expanded_capture['manifest_sha256'] if expanded_capture else None,
        'public_analytics_capture': {key: expanded_capture['public_response_read'][key]
            for key in ('sha256', 'bytes', 'status', 'content_type', 'started_at_utc', 'finished_at_utc')}
            if expanded_capture else None,
        'published_count': capture_result['published_count'] if capture_result else None,
        'db_tables': len(before['db']['tables']), 'live_html_files': before['html']['count'],
        'source_protection': 'PASS' if protection else 'FAIL',
        'protection_checks': {name: 'PASS' if passed else 'FAIL' for name, passed in checks.items()},
        'build': build_result, 'failure': failure, 'preview_gate': 'NOT_PASSED', 'browser_run': False,
        'production_written': False, 'activated': False}
    save(stage / 'SERVER_BUILD_RECEIPT.json', result)
    print(json.dumps(result, sort_keys=True))
    return 0 if build_result and protection and not failure else 1


if __name__ == '__main__':
    os.umask(0o077)
    try:
        raise SystemExit(run(sys.argv[1]))
    except Exception as error:
        print(json.dumps({'build': 'FAIL', 'error_type': type(error).__name__,
                          'preview_gate': 'NOT_PASSED', 'production_written': False}))
        raise SystemExit(1)
