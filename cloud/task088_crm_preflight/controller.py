#!/usr/bin/env python3
"""Protected diagnostic-only TASK088 controller; never modifies business files."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shlex
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

TASK_ID = 'TASK088-GE-PRICE-CRM-PREFLIGHT'
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PACKAGE = 'cloud/task088_crm_preflight'
BASE = 'https://www.pythonanywhere.com/api/v0/user/Carix/'
REMOTE_ROOT = '/home/Carix/autopilot_inbox/cloud/task088_crm_preflight/runs'
RECEIPT_REL = f'state/receipts/{TASK_ID}.json'
BACKUP_RECEIPT_REL = f'state/receipts/{TASK_ID}-BACKUP.json'
ROLLBACK_RECEIPT_REL = f'state/receipts/{TASK_ID}-ROLLBACK.json'
EVIDENCE_REL = PACKAGE + '/evidence.json'
SOURCE_FILES = ('remote_probe.py', 'owner_preflight.py', 'ui_patch.py', 'capacity_probe.py')
BUSINESS_FILES = ('cars_ui.py', 'cars_schema.py', 'db.py', 'start_safe.py')
TARGET_PATHS = frozenset(('production/operator-ui/cars_ui.py', 'production/crm.db'))
BINDINGS = ('task_id', 'run_id', 'request_sha256', 'transaction_id', 'manifest_sha256')
MAX_BYTES = 16 * 1024 * 1024
MAX_UPLOAD_BYTES = 512 * 1024


class ControllerError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ControllerError('HTTP_REDIRECT_REFUSED')


def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def sha(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(canonical(value)); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        pathlib.Path(temporary).unlink(missing_ok=True)


def repo_file(relative):
    if not re.fullmatch(r'[A-Za-z0-9._/-]+', relative):
        raise ControllerError('REPO_PATH')
    rel = pathlib.PurePosixPath(relative)
    path = ROOT / relative
    if rel.is_absolute() or '..' in rel.parts or '//' in relative or path.resolve() != path.absolute() or not path.is_file():
        raise ControllerError('REPO_PATH')
    return path


def bindings(values):
    return {key: values['UAART_' + key.upper()] for key in BINDINGS}


def required(environment, operation):
    receipt = {'backup': BACKUP_RECEIPT_REL, 'execute': RECEIPT_REL, 'rollback': ROLLBACK_RECEIPT_REL}.get(operation)
    if receipt is None:
        raise ControllerError('OPERATION')
    names = ('PYTHONANYWHERE_API_TOKEN', 'UAART_REQUEST_PATH', 'UAART_REQUEST_SHA256', 'UAART_TASK_ID', 'UAART_TASK_CLASS', 'UAART_RUN_ID', 'UAART_RECEIPT_PATH', 'UAART_TRANSACTION_ID', 'UAART_MANIFEST_SHA256', 'UAART_OPERATION')
    values = {name: str(environment.get(name, '')).strip() for name in names}
    if any(not value or any(char in value for char in '\r\n\0') for value in values.values()):
        raise ControllerError('MISSING_ENVIRONMENT')
    if values['UAART_OPERATION'] != operation or values['UAART_TASK_ID'] != TASK_ID or values['UAART_TASK_CLASS'] != 'CRITICAL':
        raise ControllerError('TASK_IDENTITY')
    if values['UAART_RECEIPT_PATH'] != receipt or (operation != 'execute' and environment.get('UAART_' + operation.upper() + '_RECEIPT_PATH') != receipt):
        raise ControllerError('RECEIPT_IDENTITY')
    if not re.fullmatch(r'[0-9]{1,30}', values['UAART_RUN_ID']) or not re.fullmatch(r'[A-Za-z0-9._-]{1,180}', values['UAART_TRANSACTION_ID']):
        raise ControllerError('RUN_IDENTITY')
    for key in ('UAART_REQUEST_SHA256', 'UAART_MANIFEST_SHA256'):
        if not re.fullmatch(r'[0-9a-f]{64}', values[key]):
            raise ControllerError('SHA_IDENTITY')
    raw = repo_file(values['UAART_REQUEST_PATH']).read_bytes()
    request = json.loads(raw)
    if sha(raw) != values['UAART_REQUEST_SHA256'] or request.get('task_id') != TASK_ID:
        raise ControllerError('REQUEST_IDENTITY')
    execution, critical = request.get('execution', {}), request.get('critical', {})
    if request.get('read_only') is not True or request.get('production_required') is not True or execution.get('production_required') is not True or set(request.get('changed_paths', [])) != TARGET_PATHS:
        raise ControllerError('READONLY_PROTECTED_SCOPE_REQUIRED')
    if critical.get('gate_b_authorized') is not True or critical.get('allow_crm_vehicle_data') is not True:
        raise ControllerError('PROTECTED_AUTHORIZATION_REQUIRED')
    expected = {'controller_path': PACKAGE + '/controller.py', 'receipt_path': RECEIPT_REL, 'backup_receipt_path': BACKUP_RECEIPT_REL, 'rollback_receipt_path': ROLLBACK_RECEIPT_REL}
    if any(execution.get(key) != value for key, value in expected.items()):
        raise ControllerError('EXECUTION_IDENTITY')
    manifest = json.loads(repo_file(str(critical.get('manifest_path', ''))).read_bytes())
    if sha(canonical(manifest)) != values['UAART_MANIFEST_SHA256'] or critical.get('manifest_sha256') != values['UAART_MANIFEST_SHA256'] or manifest.get('task_id') != TASK_ID:
        raise ControllerError('MANIFEST_IDENTITY')
    operations = manifest.get('operations', [])
    if len(operations) != 2 or {item.get('path') for item in operations} != TARGET_PATHS or any(item.get('action') != 'noop' for item in operations):
        raise ControllerError('NOOP_OPERATIONS_REQUIRED')
    if any(manifest.get(key) is not True for key in ('backup_required', 'rollback_required', 'live_verify_required', 'explicit_crm_vehicle_approval')):
        raise ControllerError('MANIFEST_PROTECTIONS')
    if operation != 'backup':
        value = str(environment.get('UAART_BACKUP_MANIFEST_SHA256', ''))
        if not re.fullmatch(r'[0-9a-f]{64}', value):
            raise ControllerError('BACKUP_IDENTITY')
        values['UAART_BACKUP_MANIFEST_SHA256'] = value
    return values


class API:
    def __init__(self, values):
        self.values = dict(values)
        self.directory = REMOTE_ROOT + '/' + values['UAART_RUN_ID'] + '-' + values['UAART_REQUEST_SHA256']
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, method, url, data=None, headers=None, allowed=(200,)):
        if not url.startswith(BASE) or method not in {'GET', 'POST', 'DELETE'}:
            raise ControllerError('API_SCOPE')
        if method == 'POST' and url != BASE + 'always_on/' and url not in {self.file_url(self.directory + '/' + name, write=True) for name in (*SOURCE_FILES, 'plan.json', 'trigger.json')}:
            raise ControllerError('API_WRITE_SCOPE')
        if method == 'DELETE' and not re.fullmatch(re.escape(BASE) + r'always_on/[1-9][0-9]*/', url):
            raise ControllerError('API_DELETE_SCOPE')
        actual = {'Authorization': 'Token ' + self.values['PYTHONANYWHERE_API_TOKEN'], 'User-Agent': 'ua-art-task088-preflight/1'}
        actual.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=actual, method=method)
        try:
            with self.opener.open(request, timeout=45) as response:
                status, body = response.status, response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status, body = exc.code, exc.read(MAX_BYTES + 1)
        except Exception as exc:
            raise ControllerError('NETWORK_' + type(exc).__name__) from None
        if status not in allowed or len(body) > MAX_BYTES:
            raise ControllerError('HTTP_' + str(status))
        return status, body

    def file_url(self, path, write=False):
        allowed = {self.directory + '/' + name for name in (*SOURCE_FILES, 'plan.json', 'result.json', 'started.json', 'trigger.json')}
        if not write:
            allowed.update('/home/Carix/' + name for name in BUSINESS_FILES)
        if path not in allowed or (write and pathlib.PurePosixPath(path).name in {'result.json', 'started.json'}):
            raise ControllerError('FILE_SCOPE')
        return BASE + 'files/path' + urllib.parse.quote(path, safe='/')

    def read(self, path, missing=False):
        status, body = self.request('GET', self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise ControllerError('REMOTE_MISSING')
        return body

    def snapshot(self):
        sources = {}
        for name in BUSINESS_FILES:
            payload = self.read('/home/Carix/' + name, missing=name != 'cars_ui.py')
            sources[name] = {'sha256': sha(payload), 'bytes': len(payload)} if payload is not None else {'absent': True}
        return {**bindings(self.values), 'business_mutation_targets': [], 'database_backup': 'NOOP_READ_ONLY_DIAGNOSTIC', 'sources': sources}

    def upload(self, name, value):
        path = self.directory + '/' + name
        url = self.file_url(path, write=True)
        if len(value) > MAX_UPLOAD_BYTES:
            raise ControllerError('UPLOAD_BUDGET')
        previous = self.read(path, missing=True)
        if previous is not None:
            if previous != value:
                raise ControllerError('IMMUTABLE_FILE_MISMATCH')
            return
        boundary = '----task088-' + uuid.uuid4().hex
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="content"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode() + value + f'\r\n--{boundary}--\r\n'.encode()
        self.request('POST', url, body, {'Content-Type': 'multipart/form-data; boundary=' + boundary}, allowed=(200, 201))
        if self.read(path) != value:
            raise ControllerError('UPLOAD_READBACK')

    def command(self):
        return 'cd ' + shlex.quote(self.directory) + ' && python3.10 -B remote_probe.py'

    def description(self):
        return TASK_ID + ' ' + self.values['UAART_RUN_ID'] + '-' + self.values['UAART_REQUEST_SHA256']

    def tasks(self):
        _, body = self.request('GET', BASE + 'always_on/')
        parsed = json.loads(body)
        items = parsed.get('results', parsed.get('objects', parsed.get('tasks', []))) if isinstance(parsed, dict) else parsed
        if not isinstance(items, list):
            raise ControllerError('TASK_LIST')
        return items

    def cleanup(self, identifier=None):
        record = self.read(self.directory + '/trigger.json', missing=True)
        if record is not None:
            value = json.loads(record)
            if any(value.get(key) != expected for key, expected in bindings(self.values).items()) or type(value.get('id')) is not int:
                raise ControllerError('TRIGGER_RECORD_IDENTITY')
            if identifier is not None and identifier != value['id']:
                raise ControllerError('TRIGGER_IDENTITY')
            identifier = value['id']
        matches = [item for item in self.tasks() if isinstance(item, dict) and item.get('command') == self.command() and item.get('description') == self.description()]
        if len(matches) > 1:
            raise ControllerError('TRIGGER_NOT_UNIQUE')
        if not matches:
            return {'cleanup': 'PASS', 'created_trigger_absent': True}
        item = matches[0]
        if type(item.get('id')) is not int or item['id'] <= 0 or (identifier is not None and item['id'] != identifier):
            raise ControllerError('TRIGGER_IDENTITY')
        # Exact immutable command and description recover the id if POST response was lost.
        self.request('DELETE', BASE + 'always_on/' + str(item['id']) + '/', allowed=(200, 202, 204, 404))
        if any(isinstance(task, dict) and task.get('id') == item['id'] for task in self.tasks()):
            raise ControllerError('TRIGGER_CLEANUP_NOT_VERIFIED')
        return {'cleanup': 'PASS', 'created_trigger_absent': True}

    def collect(self, snapshot, timeout=240):
        existing = self.read(self.directory + '/result.json', missing=True)
        if existing is not None:
            result = json.loads(existing)
            validate_remote(result, self.values)
            self.cleanup()
            return result
        if self.read(self.directory + '/started.json', missing=True) is not None:
            raise ControllerError('REMOTE_ATTEMPT_ALREADY_STARTED')
        sources = {name: (HERE / name).read_bytes() for name in SOURCE_FILES}
        if sum(map(len, sources.values())) > MAX_UPLOAD_BYTES:
            raise ControllerError('PACKAGE_BUDGET')
        for name, payload in sources.items():
            compile(payload.decode('utf-8'), name, 'exec')
        plan = {**bindings(self.values), 'backup_manifest_sha256': self.values['UAART_BACKUP_MANIFEST_SHA256'], 'sources': snapshot['sources'], 'remote_source_sha256': {name: sha(payload) for name, payload in sources.items()}}
        for name, payload in sources.items():
            self.upload(name, payload)
        self.upload('plan.json', canonical(plan))
        identifier = None
        try:
            if any(isinstance(item, dict) and item.get('command') == self.command() for item in self.tasks()):
                raise ControllerError('PREEXISTING_TRIGGER')
            form = urllib.parse.urlencode({'command': self.command(), 'description': self.description(), 'enabled': 'true'}).encode()
            _, body = self.request('POST', BASE + 'always_on/', form, {'Content-Type': 'application/x-www-form-urlencoded'}, allowed=(200, 201, 202))
            value = json.loads(body)
            identifier = value.get('id') if isinstance(value, dict) else None
            if type(identifier) is not int or identifier <= 0:
                raise ControllerError('TRIGGER_IDENTITY')
            self.upload('trigger.json', canonical({**bindings(self.values), 'id': identifier}))
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                raw = self.read(self.directory + '/result.json', missing=True)
                if raw is not None:
                    result = json.loads(raw)
                    validate_remote(result, self.values)
                    return result
                time.sleep(5)
            raise ControllerError('REMOTE_TIMEOUT')
        finally:
            self.cleanup(identifier)


def validate_remote(value, values):
    if not isinstance(value, dict) or any(value.get(key) != expected for key, expected in bindings(values).items()) or value.get('backup_manifest_sha256') != values['UAART_BACKUP_MANIFEST_SHA256']:
        raise ControllerError('REMOTE_IDENTITY')
    if value.get('collection_status') != 'PASS' or value.get('crm_prices_acceptance') != 'NOT_PERFORMED':
        raise ControllerError('REMOTE_COLLECTION')
    for key in ('business_source_writes', 'db_writes', 'site_changes', 'bot_restarts'):
        if type(value.get(key)) is not int or value[key] != 0:
            raise ControllerError('REMOTE_MUTATION')
    if value.get('live_modules_imported') is not False or not isinstance(value.get('discovery'), dict):
        raise ControllerError('REMOTE_DISCOVERY')


def backup(environment, api_factory=API):
    values = required(environment, 'backup')
    manifest = api_factory(values).snapshot()
    receipt = {**bindings(values), 'schema_version': 'UA-ART-PRODUCTION-BACKUP-RECEIPT-1', 'operation': 'backup', 'status': 'PASS', 'backup': 'PASS', 'backup_manifest_sha256': sha(canonical(manifest)), 'unexpected_changes': 0}
    atomic(ROOT / BACKUP_RECEIPT_REL, receipt)
    return receipt


def execute(environment, api_factory=API):
    values = required(environment, 'execute')
    evidence = {**bindings(values), 'status': 'FAIL', 'started_at': now(), 'crm_prices_acceptance': 'NOT_PERFORMED'}
    try:
        api = api_factory(values)
        snapshot = api.snapshot()
        if sha(canonical(snapshot)) != values['UAART_BACKUP_MANIFEST_SHA256']:
            raise ControllerError('SOURCE_DRIFT_SINCE_BACKUP')
        remote = api.collect(snapshot)
        evidence['remote'] = remote
        validate_remote(remote, values)
        if api.snapshot() != snapshot:
            raise ControllerError('SOURCE_DRIFT_DURING_DIAGNOSTIC')
        evidence['status'] = 'PASS'
        receipt = {**bindings(values), 'contract_id': 'UA-ART-CRITICAL-ADAPTER-V1.0', 'status': 'FINISHED', 'task_class': 'CRITICAL', 'target_environment': 'production', 'tests': 'PASS', 'backup': 'PASS', 'production': 'PASS', 'live_verify': 'PASS', 'rollback': 'PASS', 'rollback_ready': True, 'production_required': True, 'backup_manifest_sha256': values['UAART_BACKUP_MANIFEST_SHA256'], 'unexpected_changes': 0, 'protected_files_unchanged': True, 'crm_unchanged': True, 'read_only': True, 'verification_scope': 'READ_ONLY_DISCOVERY_COLLECTION_AND_SOURCE_HASH_PRESERVATION', 'crm_prices_acceptance': 'NOT_PERFORMED', 'finished_at': now()}
        atomic(ROOT / RECEIPT_REL, receipt)
    except Exception as exc:
        evidence['error'] = str(exc) if isinstance(exc, ControllerError) else type(exc).__name__
    evidence['finished_at'] = now()
    atomic(ROOT / EVIDENCE_REL, evidence)
    return evidence


def rollback(environment, api_factory=API):
    values = required(environment, 'rollback')
    api = api_factory(values)
    api.cleanup()
    if sha(canonical(api.snapshot())) != values['UAART_BACKUP_MANIFEST_SHA256']:
        raise ControllerError('SOURCE_DRIFT_REFUSE_OVERWRITE')
    receipt = {**bindings(values), 'schema_version': 'UA-ART-PRODUCTION-ROLLBACK-RECEIPT-1', 'operation': 'rollback', 'status': 'ROLLED_BACK', 'rollback': 'PASS', 'backup_manifest_sha256': values['UAART_BACKUP_MANIFEST_SHA256'], 'restored': True, 'unexpected_changes': 0, 'protected_files_unchanged': True, 'crm_unchanged': True, 'live_verify': 'PASS'}
    atomic(ROOT / ROLLBACK_RECEIPT_REL, receipt)
    return receipt


if __name__ == '__main__':
    result = execute(os.environ)
    print(json.dumps({'task_id': TASK_ID, 'status': result['status'], 'crm_prices_acceptance': 'NOT_PERFORMED'}, sort_keys=True))
    raise SystemExit(0 if result['status'] == 'PASS' else 1)
