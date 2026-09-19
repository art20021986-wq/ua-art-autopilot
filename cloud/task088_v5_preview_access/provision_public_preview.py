"""Owner-authorized public, manifest-only Preview. Never changes Production."""
import sys
sys.dont_write_bytecode = True
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone

PARENT = Path('/home/Carix/autopilot_inbox/cloud')
BASE = PARENT / 'provision_preview_08fbf7a1.py'
BASE_SHA = '206ec6f601a4997e2f1129f9e6deb158293b811ce188eba7eff6d02ce062d3f6'
PUBLIC_SOURCE = PARENT / 'wsgi_preview_public_1.py'
PUBLIC_SHA = 'ba8188817fe309e42082024007ff892342283937a76a45fe8e3fcc2c975c2ee4'
POLICY = 'PUBLIC_READ_ONLY_PREVIEW_OWNER_AUTHORIZED'


def pinned(path, expected):
    if path.resolve(strict=True) != path or not path.is_file():
        raise ValueError('EXACT_REGULAR_SOURCE_REQUIRED')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('REVIEWED_SOURCE_DRIFT')
    return raw


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_public_app(app, domain):
    def call(path, method='GET', host=domain, scheme='https'):
        result = {}
        def start(status, headers):
            result.update(status=status, headers=dict(headers))
        result['body'] = b''.join(app({'PATH_INFO':path, 'REQUEST_METHOD':method,
            'HTTP_HOST':host, 'wsgi.url_scheme':scheme}, start))
        return result
    for route, item in app.files.items():
        result = call(route)
        if (result['status'] != '200 OK' or 'WWW-Authenticate' in result['headers']
                or hashlib.sha256(result['body']).hexdigest() != item['sha256']
                or 'noindex' not in result['headers'].get('X-Robots-Tag', '')):
            raise ValueError('PUBLIC_PINNED_RESOURCE_FAILED')
    private_paths = ('/config.json', '/manifest.json', '/provenance.json', '/cars.db',
        '/db.py', '/uaart-bridge', '/ua/a/e', '/video/../config.json', '/site/UA-0001.html')
    for path in private_paths:
        if call(path)['status'] != '404 Not Found':
            raise ValueError('PRIVATE_RESOURCE_EXPOSED')
    for method in ('POST', 'PUT', 'PATCH', 'DELETE', 'CONNECT', 'TRACE'):
        if call('/video/index.html', method)['status'] != '405 Method Not Allowed':
            raise ValueError('PUBLIC_WRITE_METHOD_EXPOSED')
    if (call('/video/index.html', host='www.uaart.com.ua')['status'] != '421 Misdirected Request'
            or call('/video/index.html', scheme='http')['status'] != '421 Misdirected Request'
            or call('/video/index.html', 'HEAD')['body'] != b''):
        raise ValueError('PUBLIC_PREVIEW_BOUNDARY_FAILED')
    return {'pinned_resources':len(app.files), 'private_routes_denied':len(private_paths),
            'status':'PASS', 'scope':'IN_PROCESS_REAL_BUNDLE_NOT_BROWSER_RENDERING'}


def main():
    os.umask(0o077)
    pinned(BASE, BASE_SHA)
    public_raw = pinned(PUBLIC_SOURCE, PUBLIC_SHA)
    base = load_module('reviewed_preview_provisioner', BASE)
    host = base.validate_inputs()
    appdir = Path(tempfile.mkdtemp(prefix='public-preview-app-', dir=base.STAGE))
    runtime = appdir / 'runtime'
    runtime.mkdir(mode=0o700)
    hashes = dict(base.RUNTIME, **{'wsgi_preview.py':PUBLIC_SHA})
    for name, expected in hashes.items():
        raw = public_raw if name == 'wsgi_preview.py' else base.checked_read(
            base.STAGE / 'package/cloud/task088_v5_preview' / name, True)
        if base.sha(raw) != expected:
            raise ValueError('RUNTIME_SOURCE_DRIFT')
        base.write_private(runtime / name, raw)
    for name, expected in hashes.items():
        pinned(runtime / name, expected)
    config_path = appdir / 'config.json'
    base.write_private(config_path, base.encode({'contract':'UA-ART-V5-PROTECTED-PREVIEW-1',
        'preview_origin':base.ORIGIN, 'bundle_root':str(base.STAGE / 'candidate'),
        'manifest_sha256':base.EXPECTED_MANIFEST, 'access_policy':POLICY}))
    sys.path.insert(0, str(runtime))
    module = load_module('reviewed_public_preview', runtime / 'wsgi_preview.py')
    verification = verify_public_app(module.Preview(config_path), base.DOMAIN)
    before = base.checked_read(base.TARGET)
    backup = appdir / 'default_wsgi.backup.py'
    base.write_private(backup, before)
    if base.sha(base.checked_read(backup, True)) != base.EXPECTED_DEFAULT_WSGI:
        raise ValueError('DEFAULT_WSGI_BACKUP_FAILED')
    code = ('# Owner-authorized public read-only Preview only\nimport os\nimport sys\n'
        'sys.dont_write_bytecode = True\n'
        'os.environ["UA_ART_PREVIEW_CONFIG"] = ' + repr(str(config_path)) + '\n'
        'sys.path.insert(0, ' + repr(str(runtime)) + ')\n'
        'from wsgi_entry import application\n').encode()
    compile(code, str(base.TARGET), 'exec')
    base.write_private(appdir / 'reviewed_wsgi.py', code)
    for name, expected in hashes.items():
        pinned(runtime / name, expected)
    if base.validate_inputs() != host:
        raise ValueError('HOST_STATE_DRIFT')
    base.replace_new_preview_wsgi(base.TARGET, before, code)
    result = {'kind':'OWNER_AUTHORIZED_PUBLIC_PREVIEW_PROVISIONED',
        'recorded_at_utc':datetime.now(timezone.utc).isoformat(), 'access_policy':POLICY,
        'origin':base.ORIGIN, 'manifest_sha256':base.EXPECTED_MANIFEST,
        'runtime_sha256':hashes, 'wsgi_sha256':base.sha(code), 'backup':str(backup),
        'verification':verification, 'new_preview_wsgi_written':True,
        'production_written':False, 'reload_requested':False, 'preview_gate':'NOT_PASSED'}
    result['production_wsgi_unchanged'] = base.sha(base.checked_read(base.PRODUCTION)) == base.EXPECTED_PRODUCTION_WSGI
    result['hosting_unchanged'] = base.host_state() == host
    base.write_private(appdir / 'PUBLIC_PROVISION_RECEIPT.json', base.encode(result))
    print(json.dumps(result, sort_keys=True))
    return 0 if result['production_wsgi_unchanged'] and result['hosting_unchanged'] else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'status':'FAIL', 'error_type':type(error).__name__,
            'new_preview_wsgi_written':'NOT_CONFIRMED', 'production_written':False,
            'preview_gate':'NOT_PASSED'}))
        raise SystemExit(1)
