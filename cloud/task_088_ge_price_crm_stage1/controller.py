#!/usr/bin/env python3
"""Protected TASK088 CRM-only controller; nonproduction launches fail closed."""
from __future__ import annotations
import datetime as dt, hashlib, json, os, pathlib, re, shlex, tempfile, time
import urllib.error, urllib.parse, urllib.request, uuid

TASK_ID = 'TASK088-GE-PRICE-CRM-STAGE1'
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = 'https://www.pythonanywhere.com/api/v0/user/Carix/'
REMOTE_ROOT = '/home/Carix/autopilot_inbox/cloud/task_088_ge_price_crm_stage1/runs'
RECEIPT_REL = f'state/receipts/{TASK_ID}.json'
BACKUP_RECEIPT_REL = f'state/receipts/{TASK_ID}-BACKUP.json'
ROLLBACK_RECEIPT_REL = f'state/receipts/{TASK_ID}-ROLLBACK.json'
EVIDENCE_REL = 'cloud/task_088_ge_price_crm_stage1/evidence.json'
SOURCE_FILES = ('remote_installer.py', 'ui_patch.py', 'db_verification.py')
TARGET_PATHS = frozenset(('production/operator-ui/cars_ui.py', 'production/crm.db'))
BINDINGS = ('task_id', 'run_id', 'request_sha256', 'transaction_id', 'manifest_sha256')
DB_PROOFS = ('write_price_georgia', 'db_commit', 'read_back', 'price_uah_unchanged', 'ua_ge_independence', 'rollback_test_value')
MAX_BYTES = 8 * 1024 * 1024

class ControllerError(RuntimeError): pass

def now(): return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
def sha(value): return hashlib.sha256(value).hexdigest()
def canonical(value): return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()

def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write('\n'); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally: pathlib.Path(temporary).unlink(missing_ok=True)

def repo_file(relative):
    if not re.fullmatch(r'[A-Za-z0-9._/-]+', relative): raise ControllerError('REPO_PATH')
    rel = pathlib.PurePosixPath(relative)
    if rel.is_absolute() or '..' in rel.parts or '//' in relative: raise ControllerError('REPO_PATH')
    candidate = ROOT / relative
    if candidate.resolve() != candidate.absolute() or not candidate.is_file(): raise ControllerError('REPO_PATH')
    return candidate

def required(environment, operation='execute'):
    if operation not in {'backup', 'execute', 'rollback'}: raise ControllerError('OPERATION')
    names = ('PYTHONANYWHERE_API_TOKEN', 'UAART_REQUEST_PATH', 'UAART_REQUEST_SHA256', 'UAART_TASK_ID', 'UAART_TASK_CLASS', 'UAART_RUN_ID', 'UAART_RECEIPT_PATH', 'UAART_TRANSACTION_ID', 'UAART_MANIFEST_SHA256', 'UAART_OPERATION')
    values = {name: str(environment.get(name, '')).strip() for name in names}
    if any(not value or any(c in value for c in '\r\n\0') for value in values.values()): raise ControllerError('MISSING_ENVIRONMENT')
    if values['UAART_OPERATION'] != operation or values['UAART_TASK_ID'] != TASK_ID or values['UAART_TASK_CLASS'] != 'CRITICAL': raise ControllerError('TASK_IDENTITY')
    receipt = {'backup': BACKUP_RECEIPT_REL, 'execute': RECEIPT_REL, 'rollback': ROLLBACK_RECEIPT_REL}[operation]
    if values['UAART_RECEIPT_PATH'] != receipt: raise ControllerError('RECEIPT_IDENTITY')
    if operation != 'execute' and environment.get(f'UAART_{operation.upper()}_RECEIPT_PATH') != receipt: raise ControllerError('RECEIPT_IDENTITY')
    if not re.fullmatch(r'[0-9]{1,30}', values['UAART_RUN_ID']): raise ControllerError('RUN_IDENTITY')
    if not re.fullmatch(r'[A-Za-z0-9._-]{1,180}', values['UAART_TRANSACTION_ID']): raise ControllerError('TRANSACTION_IDENTITY')
    for name in ('UAART_REQUEST_SHA256', 'UAART_MANIFEST_SHA256'):
        if not re.fullmatch(r'[0-9a-f]{64}', values[name]): raise ControllerError('SHA_IDENTITY')
    raw = repo_file(values['UAART_REQUEST_PATH']).read_bytes()
    if sha(raw) != values['UAART_REQUEST_SHA256']: raise ControllerError('REQUEST_IDENTITY')
    request = json.loads(raw)
    if request.get('task_id') != TASK_ID or request.get('production_required') is not True: raise ControllerError('PROTECTED_CRM_ROUTE_REQUIRED')
    execution, critical = request.get('execution', {}), request.get('critical', {})
    if (execution.get('production_required') is not True or request.get('read_only') is not False or set(request.get('changed_paths', [])) != TARGET_PATHS or critical.get('gate_b_authorized') is not True or critical.get('allow_crm_vehicle_data') is not True): raise ControllerError('REQUEST_CRM_SCOPE')
    expected_paths = {'receipt_path': RECEIPT_REL, 'backup_receipt_path': BACKUP_RECEIPT_REL, 'rollback_receipt_path': ROLLBACK_RECEIPT_REL, 'controller_path': 'cloud/task_088_ge_price_crm_stage1/controller.py'}
    if any(execution.get(key) != value for key, value in expected_paths.items()): raise ControllerError('EXECUTION_IDENTITY')
    manifest = json.loads(repo_file(str(critical.get('manifest_path', ''))).read_bytes())
    if (sha(canonical(manifest)) != values['UAART_MANIFEST_SHA256'] or critical.get('manifest_sha256') != values['UAART_MANIFEST_SHA256'] or manifest.get('task_id') != TASK_ID or {item.get('path') for item in manifest.get('operations', [])} != TARGET_PATHS or manifest.get('backup_required') is not True or manifest.get('rollback_required') is not True): raise ControllerError('MANIFEST_IDENTITY')
    plan = manifest.get('crm_price_plan')
    if operation != 'backup':
        backup = str(environment.get('UAART_BACKUP_MANIFEST_SHA256', ''))
        if not re.fullmatch(r'[0-9a-f]{64}', backup): raise ControllerError('BACKUP_IDENTITY')
        values['UAART_BACKUP_MANIFEST_SHA256'] = backup
    if operation in {'backup', 'execute', 'rollback'}:
        if not isinstance(plan, dict): raise ControllerError('PINNED_CRM_PLAN_REQUIRED')
        for key in ('source_before_sha256', 'source_after_sha256'):
            if not re.fullmatch(r'[0-9a-f]{64}', str(plan.get(key, ''))): raise ControllerError('PINNED_SOURCE_IDENTITY')
        if type(plan.get('test_car_id')) is not int or plan['test_car_id'] <= 0: raise ControllerError('UNPUBLISHED_TEST_CAR_REQUIRED')
        protected = plan.get('protected_paths')
        if not isinstance(protected, list) or not protected: raise ControllerError('PROTECTED_PATHS_REQUIRED')
        for path in protected:
            target = pathlib.PurePosixPath(path)
            if not target.is_absolute() or '..' in target.parts or not target.is_relative_to('/home/Carix') or str(target) in {'/home/Carix', '/home/Carix/cars_ui.py', '/home/Carix/crm.db'}: raise ControllerError('PROTECTED_PATH_SCOPE')
    values['plan'] = plan
    return values

def bindings(values): return {key: values['UAART_' + key.upper()] for key in BINDINGS}

def validate_remote(value, mode, values):
    if not isinstance(value, dict) or any(value.get(key) != expected for key, expected in bindings(values).items()): raise ControllerError('REMOTE_IDENTITY')
    if value.get('mode') != mode or value.get('status') != 'PASS': raise ControllerError('REMOTE_' + mode.upper() + '_FAIL')
    if value.get('site_write') is not False or value.get('publisher_write') is not False or type(value.get('unexpected_changes')) is not int or value['unexpected_changes'] != 0: raise ControllerError('REMOTE_SCOPE')
    backup = value.get('backup_manifest_sha256')
    if not isinstance(backup, str) or not re.fullmatch(r'[0-9a-f]{64}', backup): raise ControllerError('REMOTE_BACKUP_IDENTITY')
    if mode != 'backup' and backup != values.get('UAART_BACKUP_MANIFEST_SHA256'): raise ControllerError('REMOTE_BACKUP_IDENTITY')
    if mode in {'install', 'verify'} and (not isinstance(value.get('db'), dict) or any(value['db'].get(key) != 'PASS' for key in DB_PROOFS)): raise ControllerError('REMOTE_DB_PROOF')
    if mode == 'verify' and value.get('ui_runtime') != 'PASS': raise ControllerError('UI_RUNTIME_NOT_VERIFIED')
    if mode == 'rollback' and (value.get('restored_exact') is not True or value.get('protected_files_unchanged') is not True or value.get('crm_unchanged') is not True or value.get('live_verify') != 'PASS'): raise ControllerError('REMOTE_ROLLBACK_PROOF')

class API:
    def __init__(self, values):
        self.values = dict(values)
        self.directory = REMOTE_ROOT + '/' + values['UAART_RUN_ID'] + '-' + values['UAART_REQUEST_SHA256']
    def request(self, method, url, data=None, headers=None, allowed=(200,)):
        actual = {'Authorization': 'Token ' + self.values['PYTHONANYWHERE_API_TOKEN'], 'User-Agent': 'ua-art-task088/2'}
        actual.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=actual, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response: status, body = response.status, response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc: status, body = exc.code, exc.read(MAX_BYTES + 1)
        except Exception as exc: raise ControllerError('NETWORK:' + type(exc).__name__) from exc
        if len(body) > MAX_BYTES or status not in allowed: raise ControllerError(f'HTTP_{status}')
        return status, body
    def file_url(self, path):
        candidate, root = pathlib.PurePosixPath(path), pathlib.PurePosixPath(self.directory)
        if not candidate.is_absolute() or str(candidate) != path or '..' in candidate.parts or root not in candidate.parents: raise ControllerError('REMOTE_SCOPE')
        return BASE + 'files/path' + urllib.parse.quote(path, safe='/')
    def read(self, path, missing=False):
        status, body = self.request('GET', self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing: return None
            raise ControllerError('REMOTE_MISSING')
        return body
    def upload(self, path, value):
        previous = self.read(path, missing=True)
        if previous is not None:
            if previous != value: raise ControllerError('REMOTE_PACKAGE_PREEXISTING_MISMATCH')
            return
        boundary = '----uaart-' + uuid.uuid4().hex
        filename = pathlib.PurePosixPath(path).name
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="content"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode() + value + f'\r\n--{boundary}--\r\n'.encode()
        self.request('POST', self.file_url(path), body, {'Content-Type': 'multipart/form-data; boundary=' + boundary}, allowed=(200, 201))
        if self.read(path) != value: raise ControllerError('UPLOAD_READBACK')
    def upload_package(self):
        sources = {name: (HERE / name).read_bytes() for name in SOURCE_FILES}
        for name, source in sources.items(): compile(source.decode('utf-8'), name, 'exec')
        for name, source in sources.items(): self.upload(self.directory + '/' + name, source)
        if self.values.get('plan') is not None:
            self.upload(self.directory + '/plan.json', canonical({**self.values['plan'], **bindings(self.values)}))
    def run(self, mode, timeout=600):
        if mode not in {'backup', 'install', 'verify', 'rollback'}: raise ControllerError('REMOTE_MODE')
        receipt_path = self.directory + '/receipt-' + mode + '.json'
        previous = self.read(receipt_path, missing=True)
        if previous is not None:
            value = json.loads(previous); validate_remote(value, mode, self.values); return value
        args = ['python3.10', 'remote_installer.py', '--mode', mode]
        for key in BINDINGS[1:]: args.extend(['--' + key.replace('_', '-'), self.values['UAART_' + key.upper()]])
        if mode != 'backup': args.extend(['--backup-manifest-sha256', self.values['UAART_BACKUP_MANIFEST_SHA256']])
        command = 'cd ' + shlex.quote(self.directory) + ' && ' + shlex.join(args)
        form = urllib.parse.urlencode({'command': command, 'description': TASK_ID + ' ' + mode, 'enabled': 'true'}).encode()
        _, body = self.request('POST', BASE + 'always_on/', form, {'Content-Type': 'application/x-www-form-urlencoded'}, allowed=(200, 201, 202))
        created = json.loads(body); identifier = created.get('id') if isinstance(created, dict) else None
        if type(identifier) is not int or identifier <= 0: raise ControllerError('TRIGGER_IDENTITY')
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                raw = self.read(receipt_path, missing=True)
                if raw is not None:
                    value = json.loads(raw); validate_remote(value, mode, self.values); return value
                time.sleep(5)
            raise ControllerError('REMOTE_TIMEOUT')
        finally: self.request('DELETE', BASE + f'always_on/{identifier}/', allowed=(200, 202, 204, 404))
    def bot_task(self):
        _, body = self.request('GET', BASE + 'always_on/'); parsed = json.loads(body)
        objects = parsed.get('results', parsed.get('objects', parsed.get('tasks', []))) if isinstance(parsed, dict) else parsed
        if not isinstance(objects, list): raise ControllerError('BOT_TASK_LIST')
        matches = [item for item in objects if isinstance(item, dict) and item.get('enabled') is True and item.get('command') == 'python3.10 /home/Carix/start_safe.py']
        if len(matches) != 1 or type(matches[0].get('id')) is not int: raise ControllerError('BOT_TASK_NOT_UNIQUE')
        return matches[0]
    def restart(self):
        identifier = self.bot_task()['id']
        self.request('POST', BASE + f'always_on/{identifier}/restart/', b'', allowed=(200, 201, 202, 204))
        if self.bot_task()['id'] != identifier: raise ControllerError('BOT_TASK_POST_RESTART')
        return {'restart_requested': True, 'task_id': identifier, 'ui_runtime': 'NOT_VERIFIED'}

def execute(environment, api_factory=API):
    values = required(environment)
    evidence = {**bindings(values), 'status': 'FAIL', 'started_at': now()}
    try:
        api = api_factory(values); api.bot_task(); api.upload_package()
        installed = api.run('install'); validate_remote(installed, 'install', values)
        evidence['install'] = installed; evidence['restart'] = api.restart()
        verified = api.run('verify'); validate_remote(verified, 'verify', values)
        evidence['verify'] = verified
        receipt = {**bindings(values), 'contract_id': 'UA-ART-CRITICAL-ADAPTER-V1.0', 'status': 'FINISHED', 'task_class': 'CRITICAL', 'production_required': True, 'target_environment': 'production', 'production': 'PASS', 'tests': 'PASS', 'backup': 'PASS', 'backup_manifest_sha256': values['UAART_BACKUP_MANIFEST_SHA256'], 'rollback_ready': True, 'live_verify': 'PASS', 'unexpected_changes': 0, 'site_unchanged': True, 'publisher_unchanged': True, 'ui_runtime': 'PASS', 'db': verified['db'], 'finished_at': now()}
        atomic(ROOT / RECEIPT_REL, receipt); evidence['status'] = 'PASS'
    except Exception as exc:
        evidence['error'] = type(exc).__name__ + ':' + str(exc)
        evidence['rollback'] = 'DEFERRED_TO_PROTECTED_CRITICAL_WORKFLOW'
    evidence['finished_at'] = now(); atomic(ROOT / EVIDENCE_REL, evidence)
    return evidence

if __name__ == '__main__':
    result = execute(os.environ)
    print(json.dumps({'task_id': TASK_ID, 'status': result['status']}, sort_keys=True))
    raise SystemExit(0 if result['status'] == 'PASS' else 1)
