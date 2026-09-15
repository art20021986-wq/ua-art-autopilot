"""One-time provisioning for the observed NEW Carix Preview app only.

No reload, Production write, live application import, credential echo or API
mutation. This is pinned to one reviewed build and one default Preview WSGI.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import base64
import datetime
import fcntl
import getpass
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import stat
import tempfile
import urllib.request
import warnings

STAGE = Path('/home/Carix/autopilot_inbox/cloud/task088-v5-preview-stage-zlcw0vma')
DOMAIN = 'carix.pythonanywhere.com'
API_DOMAIN = 'Carix.pythonanywhere.com'
ORIGIN = 'https://' + DOMAIN
TARGET = Path('/var/www/carix_pythonanywhere_com_wsgi.py')
PRODUCTION = Path('/var/www/www_uaart_com_ua_wsgi.py')
EXPECTED_DEFAULT_WSGI = 'e6e40b1b3c329130935e95c60cf18d76fddedf7e8bf5be40f7e768d9a9e5b45e'
EXPECTED_PRODUCTION_WSGI = '3067d39ec9c2eb976114afc6744e2c34b088a8414e98eb3e33e0a47c1849e308'
EXPECTED_MANIFEST = '083cd2de139f2f9e695f76c4e9873252c3291b4adb90af488c069315b37abdd6'
EXPECTED_PACKAGE = '4f64d00e55f419e50876770a18c0c336bc1e53704e468bbefc434237e5a5baad'
EXPECTED_PACKAGE_MANIFEST = 'faf3c49aae147df9d4ed140b03da54c7c6b1f531b12fefa19169cad040f347bd'
RUNTIME = {
    'common.py': 'cb30a2b61d28438a9844e79b1bc8550f92885dab8b6dc0d76c2789827c9893fa',
    'routing_proof.py': 'fd483b95d5b0a2bc92146d1c137decb9e368706248b7469c9c1243a3fd622c5d',
    'viewport_harness.py': '3b6830eff2d35ed94688707018e606b0d404a00bcb4dce80fa0dadab89b0bae1',
    'wsgi_preview.py': '0d34eae83e0226e592e30dca7f06bcd4a165a6ef8e5da4354890b8f093e9aeaf',
    'wsgi_entry.py': '7b7b9056b55c41a5031e430cf470b10ae66fd812f792a3cd65cb931c1ced02e7',
}
USERNAME = 'uaart-preview'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def checked_read(path, private=False, limit=4 * 1024 * 1024):
    path = Path(path)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError('EXACT_NON_SYMLINK_PATH_REQUIRED')
    with open(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError('REGULAR_BOUNDED_FILE_REQUIRED')
        if private and (stat.S_IMODE(before.st_mode) != 0o600 or before.st_uid != os.getuid()):
            raise ValueError('OWNED_MODE_0600_FILE_REQUIRED')
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        if len(raw) > limit or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('FILE_CHANGED_DURING_READ')
    return raw


def write_private(path, raw):
    with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('HOST_API_REDIRECT_FORBIDDEN')


def host_state():
    token = os.environ.get('API_TOKEN', '')
    if not token: raise ValueError('EXISTING_HOST_API_TOKEN_REQUIRED')
    opener = urllib.request.build_opener(NoRedirect())
    base = 'https://www.pythonanywhere.com/api/v0/user/Carix/webapps/' + API_DOMAIN + '/'
    values = []
    for suffix in ('', 'static_files/'):
        request = urllib.request.Request(base + suffix, headers={'Authorization': 'Token ' + token}, method='GET')
        with opener.open(request, timeout=20) as response:
            if response.status != 200: raise ValueError('HOST_API_200_REQUIRED')
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024: raise ValueError('HOST_API_RESPONSE_TOO_LARGE')
        values.append(json.loads(raw))
    config, mappings = values
    if (type(config) is not dict or str(config.get('domain_name', '')).lower() != DOMAIN
            or str(config.get('python_version', '')) not in ('3.10', 'python310')
            or config.get('force_https') is not True or mappings != []):
        raise ValueError('EXACT_NEW_PREVIEW_APP_HTTPS_NO_STATIC_MAPS_REQUIRED')
    return {'domain_name': DOMAIN, 'python_version': '3.10', 'force_https': True, 'static_mappings': []}


def validate_inputs():
    if (str(STAGE) != '/home/Carix/autopilot_inbox/cloud/task088-v5-preview-stage-zlcw0vma'
            or TARGET != Path('/var/www/carix_pythonanywhere_com_wsgi.py')
            or PRODUCTION != Path('/var/www/www_uaart_com_ua_wsgi.py')
            or DOMAIN != 'carix.pythonanywhere.com' or API_DOMAIN != 'Carix.pythonanywhere.com'
            or ORIGIN != 'https://carix.pythonanywhere.com'
            or STAGE.resolve(strict=True) != STAGE or stat.S_IMODE(STAGE.stat().st_mode) != 0o700):
        raise ValueError('EXACT_OBSERVED_PREVIEW_TARGET_REQUIRED')
    if sha(checked_read(TARGET)) != EXPECTED_DEFAULT_WSGI:
        raise ValueError('NEW_PREVIEW_DEFAULT_WSGI_DRIFT')
    if sha(checked_read(PRODUCTION)) != EXPECTED_PRODUCTION_WSGI:
        raise ValueError('PRODUCTION_WSGI_DRIFT')
    package_receipt = json.loads(checked_read(STAGE / 'PACKAGE_RECEIPT.json', True))
    if (package_receipt.get('package_archive_sha256') != EXPECTED_PACKAGE
            or package_receipt.get('package_manifest_sha256') != EXPECTED_PACKAGE_MANIFEST
            or package_receipt.get('stage') != str(STAGE)):
        raise ValueError('EXACT_REVIEWED_PACKAGE_RECEIPT_REQUIRED')
    package = STAGE / 'package'
    if any(path.is_symlink() for path in package.rglob('*')):
        raise ValueError('PACKAGE_SYMLINK_FORBIDDEN')
    raw = checked_read(package / 'package_manifest.json', True)
    if sha(raw) != EXPECTED_PACKAGE_MANIFEST: raise ValueError('REVIEWED_PACKAGE_MANIFEST_DRIFT')
    entries = json.loads(raw)['sha256']
    actual = {path.relative_to(package).as_posix() for path in package.rglob('*') if path.is_file()}
    if actual != set(entries) | {'package_manifest.json'}:
        raise ValueError('EXACT_PACKAGE_FILE_CLOSURE_REQUIRED')
    for name, expected in entries.items():
        if (str(PurePosixPath(name)) != name or name.startswith('/') or '..' in name.split('/')
                or '\\' in name or sha(checked_read(package / name, True)) != expected):
            raise ValueError('REVIEWED_PACKAGE_SOURCE_DRIFT')
    candidate = STAGE / 'candidate'
    raw = checked_read(candidate / 'manifest.json', True)
    if sha(raw) != EXPECTED_MANIFEST: raise ValueError('EXACT_CURRENT_CANDIDATE_REQUIRED')
    manifest = json.loads(raw)
    if (manifest.get('preview_gate') != 'NOT_PASSED' or manifest.get('source_origin') != 'https://www.uaart.com.ua'
            or sha(checked_read(candidate / 'provenance.json', True)) != manifest.get('provenance_sha256')):
        raise ValueError('CANDIDATE_PROVENANCE_DRIFT')
    receipt = json.loads(checked_read(STAGE / 'SERVER_BUILD_RECEIPT.json', True))
    if (receipt.get('stage') != str(STAGE) or receipt.get('source_protection') != 'PASS'
            or not receipt.get('protection_checks') or any(v != 'PASS' for v in receipt['protection_checks'].values())
            or receipt.get('build', {}).get('manifest_sha256') != EXPECTED_MANIFEST
            or receipt.get('failure') is not None or receipt.get('production_written') is not False):
        raise ValueError('ACTUAL_READ_ONLY_BUILD_RECEIPT_REQUIRED')
    for name, expected in RUNTIME.items():
        if sha(checked_read(package / 'cloud/task088_v5_preview' / name, True)) != expected:
            raise ValueError('REVIEWED_PREVIEW_RUNTIME_DRIFT')
    return host_state()


def password_from_owner(secret_file=False):
    if secret_file:
        raw = checked_read(STAGE / 'preview-password.txt', True, limit=1024)
        password = raw.decode('utf-8').removesuffix('\n').removesuffix('\r')
    else:
        if not sys.stdin.isatty(): raise ValueError('OWNER_TTY_REQUIRED_NO_ECHO_FALLBACK')
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            password = getpass.getpass('Preview password (hidden; 16+ characters): ')
            confirmation = getpass.getpass('Repeat Preview password (hidden): ')
        if not hmac.compare_digest(password.encode(), confirmation.encode()):
            raise ValueError('PASSWORD_CONFIRMATION_MISMATCH')
    if (not 16 <= len(password) <= 256 or any(ord(char) < 32 or ord(char) == 127 for char in password)):
        raise ValueError('STRONG_NONEMPTY_PREVIEW_PASSWORD_REQUIRED')
    return password


def make_config(password):
    salt = secrets.token_bytes(32)
    return {'contract': 'UA-ART-V5-PROTECTED-PREVIEW-1', 'preview_origin': ORIGIN,
        'bundle_root': str(STAGE / 'candidate'), 'manifest_sha256': EXPECTED_MANIFEST,
        'basic_auth': {'username': USERNAME, 'salt_hex': salt.hex(), 'iterations': 600000,
            'password_hash_hex': hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 600000).hex()}}


def auth_selftest(runtime, config_path, password):
    for name, expected in RUNTIME.items():
        if sha(checked_read(runtime / name, True)) != expected:
            raise ValueError('REVIEWED_RUNTIME_REQUIRED_BEFORE_ANY_IMPORT')
    sys.path.insert(0, str(runtime))
    specification = importlib.util.spec_from_file_location('task088_private_preview_wsgi', runtime / 'wsgi_preview.py')
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    app = module.Preview(config_path)
    def call(path, authorization='', method='GET', host=DOMAIN, scheme='https'):
        result = {}
        def response(status, headers): result.update(status=status, headers=headers)
        result['body'] = b''.join(app({'REQUEST_METHOD': method, 'wsgi.url_scheme': scheme,
            'HTTP_HOST': host, 'PATH_INFO': path, 'HTTP_AUTHORIZATION': authorization}, response))
        return result
    for path in ('/', *app.files, *app.redirects, '/config.json', '/ua/a/e'):
        if call(path)['status'] != '401 Unauthorized': raise ValueError('UNAUTHENTICATED_ROUTE_NOT_BLOCKED')
    for invalid in ('Basic invalid', 'Bearer invalid', 'Basic ' + base64.b64encode(b'invalid:password').decode()):
        if call('/video/index.html', invalid)['status'] != '401 Unauthorized':
            raise ValueError('INVALID_CREDENTIAL_NOT_BLOCKED')
    valid = 'Basic ' + base64.b64encode((USERNAME + ':' + password).encode()).decode()
    checks = [(call('/video/index.html', valid), '200 OK'), (call('/ua/a/e', valid, 'POST'), '405 Method Not Allowed'),
        (call('/config.json', valid), '404 Not Found'), (call('/video/index.html', valid, host='www.uaart.com.ua'), '421 Misdirected Request'),
        (call('/video/index.html', valid, scheme='http'), '421 Misdirected Request')]
    if any(result['status'] != expected or password.encode() in result['body'] for result, expected in checks):
        raise ValueError('AUTHENTICATED_PREVIEW_BOUNDARY_SELFTEST_FAILED')
    for name, expected in RUNTIME.items():
        if sha(checked_read(runtime / name, True)) != expected: raise ValueError('RUNTIME_CHANGED_DURING_SELFTEST')
    return {'unauthenticated_routes_checked': len(app.files) + len(app.redirects) + 3,
            'status': 'PASS', 'network_or_javascript_execution': False}


def replace_new_preview_wsgi(target, before, candidate):
    if target != TARGET or target == PRODUCTION: raise ValueError('ONLY_NEW_PREVIEW_WSGI_WRITE_ALLOWED')
    if target.samefile(PRODUCTION): raise ValueError('PREVIEW_MUST_NOT_HARDLINK_PRODUCTION')
    # The platform-owned /var/www directory may not permit renames. Hold the
    # existing file descriptor locked, compare bytes again, then write/fsync and
    # read back. On write failure restore only this NEW app's original bytes.
    fd = os.open(target, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
    with open(fd, 'r+b') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode): raise ValueError('REGULAR_PREVIEW_WSGI_REQUIRED')
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        if stream.read() != before: raise ValueError('PREVIEW_WSGI_CHANGED_BEFORE_WRITE')
        try:
            stream.seek(0); stream.write(candidate); stream.truncate(); stream.flush(); os.fsync(stream.fileno())
            stream.seek(0)
            if stream.read() != candidate: raise ValueError('PREVIEW_WSGI_READBACK_FAILED')
        except Exception:
            stream.seek(0); stream.write(before); stream.truncate(); stream.flush(); os.fsync(stream.fileno())
            raise


class InstalledPreviewVerificationError(Exception):
    def __init__(self, wsgi_sha256, backup):
        super().__init__('NEW_PREVIEW_WRITTEN_POST_WRITE_VERIFICATION_FAILED')
        self.wsgi_sha256, self.backup = wsgi_sha256, str(backup)


def provision(secret_file=False):
    os.umask(0o077)
    before_host = validate_inputs()
    password = password_from_owner(secret_file)
    appdir = Path(tempfile.mkdtemp(prefix='preview-app-', dir=STAGE))
    runtime = appdir / 'runtime'; runtime.mkdir(mode=0o700)
    for name in RUNTIME:
        write_private(runtime / name, checked_read(STAGE / 'package/cloud/task088_v5_preview' / name, True))
    config_path = appdir / 'config.json'
    write_private(config_path, encode(make_config(password)))
    auth = auth_selftest(runtime, config_path, password)
    del password
    before = checked_read(TARGET)
    backup = appdir / 'default_wsgi.backup.py'
    write_private(backup, before)
    if sha(checked_read(backup, True)) != EXPECTED_DEFAULT_WSGI: raise ValueError('VERIFIED_DEFAULT_WSGI_BACKUP_REQUIRED')
    code = ('# TASK088 dedicated authenticated Preview only\nimport os\nimport sys\n'
        'sys.dont_write_bytecode = True\n'
        'os.environ["UA_ART_PREVIEW_CONFIG"] = ' + repr(str(config_path)) + '\n'
        'sys.path.insert(0, ' + repr(str(runtime)) + ')\n'
        'from wsgi_entry import application\n').encode()
    compile(code, str(TARGET), 'exec')
    write_private(appdir / 'reviewed_wsgi.py', code)
    # This second check is immediately before the sole non-staging write.
    if validate_inputs() != before_host: raise ValueError('PREVIEW_HOST_STATE_CHANGED')
    replace_new_preview_wsgi(TARGET, before, code)
    try:
        if sha(checked_read(PRODUCTION)) != EXPECTED_PRODUCTION_WSGI:
            raise ValueError('PRODUCTION_WSGI_CHANGED_EXTERNALLY')
        if host_state() != before_host: raise ValueError('PREVIEW_HOST_STATE_CHANGED_AFTER_WRITE')
    except Exception:
        raise InstalledPreviewVerificationError(sha(code), backup) from None
    result = {'kind': 'NEW_PREVIEW_APP_PROVISIONED_NO_RELOAD', 'domain': DOMAIN,
        'observed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'manifest_sha256': EXPECTED_MANIFEST, 'wsgi_sha256': sha(code), 'previous_wsgi_sha256': sha(before),
        'backup': str(backup), 'config_path': str(config_path), 'config_sha256': sha(checked_read(config_path, True)),
        'auth_selftest': auth, 'production_wsgi_unchanged': True, 'production_written': False,
        'reload_requested': False, 'preview_gate': 'NOT_PASSED', 'password_echoed': False,
        'plaintext_password_written': False}
    write_private(appdir / 'PROVISION_RECEIPT.json', encode(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--secret-file', action='store_true',
        help='Read only the owner-provisioned stage/preview-password.txt, mode0600; never supply a password argument.')
    modes.add_argument('--check-only', action='store_true', help='Read-only readiness checks; no password prompt or file writes.')
    arguments = parser.parse_args()
    try:
        if not sys.flags.isolated: raise ValueError('PYTHON_ISOLATED_MODE_REQUIRED')
        if arguments.check_only:
            result = {'kind': 'NEW_PREVIEW_READINESS_CHECK_ONLY', 'hosting': validate_inputs(),
                'manifest_sha256': EXPECTED_MANIFEST, 'password_requested': False, 'files_written': False,
                'reload_requested': False, 'preview_gate': 'NOT_PASSED'}
        else:
            result = provision(arguments.secret_file)
    except Exception as error:
        result = {'status': 'FAIL', 'error_type': type(error).__name__,
            'reload_requested': False, 'preview_gate': 'NOT_PASSED',
            'new_preview_wsgi_written': False if arguments.check_only else 'NOT_CONFIRMED'}
        if isinstance(error, InstalledPreviewVerificationError):
            result.update(new_preview_wsgi_written=True, wsgi_sha256=error.wsgi_sha256,
                          backup=error.backup, post_write_verification='FAIL')
        print(json.dumps(result, sort_keys=True)); return 1
    print(json.dumps(result, sort_keys=True)); return 0


if __name__ == '__main__':
    raise SystemExit(main())
