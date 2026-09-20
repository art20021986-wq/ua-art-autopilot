#!/usr/bin/env python3
"""UA0002 exact task adapter; forward-only retirement recovery, no live side effects on import."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

TASK_ID = 'UA-ART-UA0002-CRITICAL-DELETE-A-001'
CONTRACT = 'UA-ART-UA0002-CRITICAL-DELETE-001-v1.0'
PACKAGE = 'cloud/ua0002_delete_a'
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = 'https://www.pythonanywhere.com/api/v0/user/Carix/'
REMOTE_ROOT = '/home/Carix/autopilot_inbox/cloud/ua0002_delete_a/'
FILES = ('remote_stage_a.py', 'remote_lifecycle.py', 'publication_fence.py',
         'visibility_lifecycle.py', 'ua_site_counters.py', 'uaart_price_sync_runtime.py', 'provenance.json')
MAX_BYTES = 4 * 1024 * 1024
HEX = re.compile(r'[0-9a-f]{64}')

class AdapterError(RuntimeError):
    pass

def require(condition, code):
    if not condition:
        raise AdapterError(code)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode()

def reqsha(value):
    require(isinstance(value, str) and HEX.fullmatch(value), 'SHA256_REQUIRED')
    return value

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AdapterError('REDIRECT_FORBIDDEN')

class API:
    def __init__(self, token, run_id, opener=None):
        require(bool(token) and len(token) <= 256 and not re.search(r'[\s\x00-\x1f]', token), 'CREDENTIAL_UNAVAILABLE')
        require(re.fullmatch(r'[0-9]{1,30}', run_id), 'RUN_ID_INVALID')
        self._token, self.run_id = token, run_id
        self.folder = REMOTE_ROOT + run_id
        self._opener = opener or urllib.request.build_opener(NoRedirect())
    def request(self, method, endpoint, data=None, headers=None, allowed=(200,)):
        file_endpoint = endpoint.startswith('files/path' + self.folder + '/')
        if file_endpoint:
            name = endpoint[len('files/path' + self.folder + '/'):]
            require(name in set(FILES) | {'plan.json', 'backup-result.json', 'install_verify-result.json', 'rollback-result.json'}, 'REMOTE_FILE_SCOPE')
            require(method in {'GET', 'POST'}, 'REMOTE_FILE_METHOD')
            if method == 'POST':
                require(name in set(FILES) | {'plan.json'}, 'REMOTE_RESULT_WRITE_FORBIDDEN')
        else:
            require(endpoint == 'always_on/' or re.fullmatch(r'always_on/[0-9]{1,12}/', endpoint), 'REMOTE_ENDPOINT_SCOPE')
            require(method in {'GET', 'POST', 'DELETE'}, 'REMOTE_API_METHOD')
            require(method != 'POST' or endpoint == 'always_on/', 'REMOTE_TASK_UPDATE_FORBIDDEN')
            require(method != 'DELETE' or endpoint != 'always_on/', 'REMOTE_TASK_DELETE_SCOPE')
        actual = {'Authorization': 'Token ' + self._token, 'User-Agent': 'uaart-ua0002-retirement/1', 'Accept-Encoding': 'identity'}
        actual.update(headers or {})
        url = BASE + endpoint
        request = urllib.request.Request(url, data=data, headers=actual, method=method)
        try:
            with self._opener.open(request, timeout=40) as response:
                require(response.geturl() == url, 'RESPONSE_ORIGIN_MISMATCH')
                status, payload = response.status, response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status = exc.code
            payload = exc.read(MAX_BYTES + 1)
            exc.close()
        require(status in allowed, 'PA_HTTP_' + str(status))
        require(len(payload) <= MAX_BYTES, 'REMOTE_SIZE_LIMIT')
        return status, payload
    def read(self, name):
        status, payload = self.request('GET', 'files/path' + self.folder + '/' + name, allowed=(200, 404))
        return payload if status == 200 else None
    def upload_new(self, name, payload):
        old = self.read(name)
        if old is not None:
            require(old == payload, 'REMOTE_IMMUTABLE_DRIFT')
            return
        boundary = 'ua0002-' + uuid.uuid4().hex
        body = ('--' + boundary + '\r\nContent-Disposition: form-data; name="content"; filename="' + name + '"\r\nContent-Type: application/octet-stream\r\n\r\n').encode() + payload + ('\r\n--' + boundary + '--\r\n').encode()
        self.request('POST', 'files/path' + self.folder + '/' + name, body,
                     {'Content-Type': 'multipart/form-data; boundary=' + boundary}, allowed=(200, 201))
        require(self.read(name) == payload, 'UPLOAD_READBACK_MISMATCH')
    def tasks(self):
        _, payload = self.request('GET', 'always_on/')
        value = json.loads(payload)
        if isinstance(value, dict):
            value = value.get('results', value.get('objects', value.get('tasks')))
        require(isinstance(value, list) and len(value) <= 100 and all(isinstance(v, dict) for v in value), 'ALWAYS_ON_SHAPE')
        return value
    def owned(self, command, description):
        matches = [v for v in self.tasks() if v.get('description') == description]
        require(len(matches) <= 1, 'OWNED_WORKER_DUPLICATE')
        if not matches:
            return None
        require(matches[0].get('command') == command and type(matches[0].get('id')) is int, 'OWNED_WORKER_IDENTITY')
        return matches[0]['id']
    def trigger(self, command, description):
        old = self.owned(command, description)
        if old is not None:
            return old
        data = urllib.parse.urlencode({'command': command, 'description': description, 'enabled': 'true'}).encode()
        _, payload = self.request('POST', 'always_on/', data, {'Content-Type': 'application/x-www-form-urlencoded'}, allowed=(200, 201, 202))
        identifier = json.loads(payload).get('id')
        require(type(identifier) is int and identifier > 0, 'CREATED_WORKER_ID_INVALID')
        return identifier
    def stop_owned(self, identifier, command, description):
        endpoint = 'always_on/' + str(identifier) + '/'
        status, payload = self.request('GET', endpoint, allowed=(200, 404))
        if status == 404:
            return
        value = json.loads(payload)
        require(value.get('id') == identifier and value.get('command') == command and value.get('description') == description, 'OWNED_WORKER_CLEANUP_IDENTITY')
        self.request('DELETE', endpoint, allowed=(200, 202, 204, 404))
        status, _ = self.request('GET', endpoint, allowed=(200, 404))
        require(status == 404, 'OWNED_WORKER_STOP_UNCONFIRMED')

def load(environment, root=ROOT):
    keys = ('PYTHONANYWHERE_API_TOKEN', 'UAART_REQUEST_PATH', 'UAART_REQUEST_SHA256', 'UAART_TASK_ID',
            'UAART_TASK_CLASS', 'UAART_RUN_ID', 'UAART_TRANSACTION_ID', 'UAART_MANIFEST_SHA256')
    values = {key: str(environment.get(key, '')).strip() for key in keys}
    require(all(values.values()), 'CANONICAL_ENVIRONMENT_INCOMPLETE')
    require(values['UAART_TASK_ID'] == TASK_ID and values['UAART_TASK_CLASS'] == 'CRITICAL', 'TASK_SCOPE')
    require(re.fullmatch(r'[0-9]{1,30}', values['UAART_RUN_ID']), 'RUN_ID_INVALID')
    relative = 'tasks/requests/' + TASK_ID + '.json'
    require(values['UAART_REQUEST_PATH'] == relative, 'REQUEST_PATH_SCOPE')
    payload = (root / relative).read_bytes()
    require(sha(payload) == reqsha(values['UAART_REQUEST_SHA256']), 'REQUEST_HASH_MISMATCH')
    request = json.loads(payload)
    require(request.get('task_id') == TASK_ID and request.get('production_required') is True, 'REQUEST_PRODUCTION_SCOPE')
    manifest_rel = 'tasks/manifests/' + TASK_ID + '.json'
    critical = request.get('critical', {})
    require(critical.get('manifest_path') == manifest_rel and critical.get('manifest_sha256') == reqsha(values['UAART_MANIFEST_SHA256']), 'MANIFEST_BINDING')
    manifest = json.loads((root / manifest_rel).read_bytes())
    require(sha(canonical(manifest)) == values['UAART_MANIFEST_SHA256'], 'MANIFEST_HASH_MISMATCH')
    # Local drafts intentionally refuse before remote API access.
    require(manifest.get('readiness') == 'READY_FOR_APPROVED_EXECUTION', 'PACK_NOT_READY')
    require(critical.get('gate_b_authorized') is True, 'GATE_B_NOT_AUTHORIZED')
    require(manifest.get('recovery_semantics') == 'RESTORE_SAFE_INVARIANTS_KEEP_SOLD_TARGET_RETIRED', 'RECOVERY_SEMANTICS')
    plan = dict(manifest['deployment'])
    require(plan.get('contract') == CONTRACT and plan.get('root') == '/home/Carix', 'PLAN_SCOPE')
    require(plan.get('target') == {'id': 8, 'auto_number': 'UA-0002', 'vin': 'WDD2452322J561014'}, 'PLAN_TARGET')
    require(plan.get('stage_a_requires_target_absent') is True, 'TARGET_ABSENT_ADMISSION_REQUIRED')
    plan.update({'run_id': values['UAART_RUN_ID'], 'transaction_id': values['UAART_TRANSACTION_ID'],
                 'request_sha256': values['UAART_REQUEST_SHA256'], 'manifest_sha256': values['UAART_MANIFEST_SHA256']})
    return values, request, plan

def validate_terminal(value, plan_sha, operation):
    require(isinstance(value, dict) and value.get('plan_sha256') == plan_sha and value.get('operation') == operation, 'REMOTE_RESULT_IDENTITY')
    require(value.get('safe_to_stop') is True, 'WORKER_NONTERMINAL_RETAINED')

def validate_result(value, plan_sha, operation):
    validate_terminal(value, plan_sha, operation)
    recovered = value.get('status') == 'FAIL' and operation != 'backup' and isinstance(value.get('forward_recovery'), dict)
    require(value.get('status') == 'PASS' or recovered, 'REMOTE_PHASE_FAILED')
    resumed = value.get('crm_resume', {})
    require(resumed.get('id') == 266084 and resumed.get('enabled') is True and str(resumed.get('state', '')).lower() == 'running', 'CRM_RESUME_NOT_PROVEN')
    installed = value.get('forward_recovery') if recovered else value.get('installer')
    require(isinstance(installed, dict) and installed.get('status') == 'PASS', 'INSTALLER_PASS_MISSING')
    require(installed.get('plan_sha256') == plan_sha and installed.get('target_absent') is True, 'INSTALLER_PLAN_OR_TARGET_ABSENCE')
    for name in ('source_checksum_pass', 'integrity_pass'):
        require(installed.get(name) is True, 'INSTALLER_EVIDENCE_' + name.upper())
    if operation != 'backup':
        for name in ('post_check_pass', 'target_retired_local', 'database_unchanged', 'other_pages_unchanged'):
            require(installed.get(name) is True, 'INSTALLER_EVIDENCE_' + name.upper())
        require(installed.get('media_mutations') == 0 and type(installed.get('media_mutations')) is int, 'MEDIA_MUTATION_DETECTED')
        require(installed.get('rollback_policy') == 'FORWARD_RETIREMENT_ONLY', 'SOLD_REPUBLICATION_POLICY_REFUSED')
    reqsha(installed.get('backup_manifest_sha256'))
    installed = dict(installed)
    installed['_controller_recovery_performed'] = recovered or installed.get('operation') == 'recover'
    if recovered:
        initial = str(value.get('error', 'INITIAL_PHASE_FAILED')).split(':')[0][:80]
        installed['_controller_initial_error_code'] = initial if re.fullmatch(r'[A-Za-z0-9_.-]+', initial) else 'INITIAL_PHASE_FAILED'
    return installed

def remote(values, request, plan, operation, *, api=None, deadline_seconds=1500):
    require(operation in {'backup', 'install_verify', 'rollback'}, 'OPERATION_SCOPE')
    api = api or API(values['PYTHONANYWHERE_API_TOKEN'], values['UAART_RUN_ID'])
    hashes = request['execution']['file_sha256']
    for name in FILES:
        payload = (HERE / name).read_bytes()
        require(sha(payload) == hashes.get(PACKAGE + '/' + name), 'PACKAGE_HASH_' + name)
        api.upload_new(name, payload)
    payload = canonical(plan); plan_sha = sha(payload)
    api.upload_new('plan.json', payload)
    result_name = operation + '-result.json'
    plan_path = api.folder + '/plan.json'
    result_path = api.folder + '/' + result_name
    command = ('cd ' + api.folder + ' && python3.10 -B remote_lifecycle.py --operation ' + operation
               + ' --plan ' + plan_path + ' --plan-sha256 ' + plan_sha + ' --result ' + result_path)
    description = TASK_ID + ' ' + values['UAART_RUN_ID'] + ' ' + operation
    result = api.read(result_name)
    if result is not None:
        value = json.loads(result)
        validate_terminal(value, plan_sha, operation)
        identifier = api.owned(command, description)
        if identifier is not None:
            api.stop_owned(identifier, command, description)
        validate_result(value, plan_sha, operation)
        return value
    if operation == 'rollback':
        active = [v for v in api.tasks() if v.get('description') == TASK_ID + ' ' + values['UAART_RUN_ID'] + ' install_verify']
        require(not active or api.read('install_verify-result.json') is not None, 'INSTALL_WORKER_ACTIVE_RECOVERY_DEFERRED')
    identifier = api.trigger(command, description)
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        result = api.read(result_name)
        if result is not None:
            value = json.loads(result)
            # Only terminal, exact-identity workers may be stopped; cleanup is not a PASS.
            validate_terminal(value, plan_sha, operation)
            api.stop_owned(identifier, command, description)
            validate_result(value, plan_sha, operation)
            return value
        time.sleep(4)
    raise AdapterError('REMOTE_TIMEOUT_WORKER_RETAINED')

def verify_public(installed, run_id, opener=None):
    """Read-only external acceptance after the same CRM supervisor has resumed."""
    opener = opener or urllib.request.build_opener(NoRedirect())
    absent = installed.get('absent')
    shared = installed.get('shared_sha256')
    require(isinstance(absent, list) and isinstance(shared, dict), 'PUBLIC_PROOF_SHAPE')
    require({'video/UA-0002.html', 'video/UA-0002-diag.html'} <= set(absent), 'PRIMARY_RETIREMENTS_MISSING')
    require({'video/index.html', 'video/katalog.html', 'video/sitemap.xml'} <= set(shared), 'SHARED_PUBLIC_PROOF_MISSING')
    checks = []
    paths = []
    for path in absent:
        require(re.fullmatch(r'(?:site|video)/UA-0002(?:-diag)?(?:-[0-9a-f]{6,10})?\.html', path), 'RETIRED_PATH_SCOPE')
        if path.startswith('video/'):
            paths.append((path, None))
    for path, digest in shared.items():
        require(re.fullmatch(r'(?:site|video)/(?:index\.html|katalog\.html|sitemap\.xml)', path), 'SHARED_PATH_SCOPE')
        reqsha(digest)
        if path.startswith('video/'):
            paths.append((path, digest))
    for path, digest in paths:
        url = 'https://www.uaart.com.ua/' + path + '?ua0002_verify=' + run_id
        request = urllib.request.Request(url, method='GET', headers={'Cache-Control': 'no-cache', 'Accept-Encoding': 'identity', 'User-Agent': 'uaart-ua0002-verification/1'})
        try:
            with opener.open(request, timeout=20) as response:
                require(response.geturl() == url, 'PUBLIC_REDIRECT_FORBIDDEN')
                status, body = response.status, response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status, body = exc.code, b''
            exc.close()
        require(len(body) <= MAX_BYTES, 'PUBLIC_SIZE_LIMIT')
        if digest is None:
            require(status in {404, 410}, 'SOLD_TARGET_STILL_PUBLIC')
        else:
            require(status == 200 and sha(body) == digest, 'PUBLIC_SHARED_BYTES_MISMATCH')
        checks.append({'path': path, 'status': status, 'sha256': digest})
    return checks

def write_receipt(root, relative, value):
    require(relative.startswith('state/receipts/') and re.fullmatch(r'state/receipts/[A-Za-z0-9_.-]+\.json', relative), 'RECEIPT_PATH_SCOPE')
    target = root / relative
    require(not target.exists() and not target.is_symlink(), 'RECEIPT_ALREADY_EXISTS')
    target.parent.mkdir(parents=True, exist_ok=True)
    require(target.parent.resolve().is_relative_to(root.resolve()), 'RECEIPT_PATH_ESCAPE')
    with target.open('xb') as handle:
        handle.write(canonical(value))

def receipt_value(values, installed, operation, public_checks):
    base = {'task_id': TASK_ID, 'request_sha256': values['UAART_REQUEST_SHA256'], 'run_id': values['UAART_RUN_ID'],
            'transaction_id': values['UAART_TRANSACTION_ID'], 'manifest_sha256': values['UAART_MANIFEST_SHA256'],
            'backup_manifest_sha256': installed['backup_manifest_sha256'], 'unexpected_changes': 0}
    if operation == 'backup':
        return base | {'schema_version': 'UA-ART-PRODUCTION-BACKUP-RECEIPT-1', 'operation': 'backup', 'status': 'PASS', 'backup': 'PASS'}
    require(public_checks, 'PUBLIC_ACCEPTANCE_REQUIRED')
    if operation == 'rollback':
        # "restored" is bound in the exact manifest to safe invariants, with the sold
        # target permanently absent. No original listing or CRM row is restored.
        return base | {'schema_version': 'UA-ART-PRODUCTION-ROLLBACK-RECEIPT-1', 'operation': 'rollback',
            'status': 'PASS', 'rollback': 'PASS', 'restored': True, 'protected_files_unchanged': True,
            'crm_unchanged': True, 'live_verify': 'PASS'}
    return base | {'contract_id': 'UA-ART-CRITICAL-ADAPTER-V1.0', 'status': 'FINISHED', 'task_class': 'CRITICAL',
        'target_environment': 'production', 'tests': 'PASS', 'production': 'PASS', 'backup': 'PASS',
        'live_verify': 'PASS', 'protected_files_unchanged': True, 'crm_unchanged': True,
        'rollback_ready': True, 'rollback': 'PASS', 'production_required': True,
        'recovery_semantics': 'RESTORE_SAFE_INVARIANTS_KEEP_SOLD_TARGET_RETIRED',
        'target_republished': False, 'recovery_performed': installed.get('_controller_recovery_performed', False),
        'public_verification': public_checks}

def execute(operation, environment=None, *, root=ROOT):
    environment = os.environ if environment is None else environment
    values, request, plan = load(environment, root)
    result = remote(values, request, plan, operation)
    installed = validate_result(result, sha(canonical(plan)), operation)
    if operation != 'backup':
        require(installed['backup_manifest_sha256'] == environment.get('UAART_BACKUP_MANIFEST_SHA256'), 'BACKUP_MANIFEST_BINDING')
    public = [] if operation == 'backup' else verify_public(installed, values['UAART_RUN_ID'])
    receipt = receipt_value(values, installed, operation, public)
    if operation == 'backup':
        path = request['execution']['backup_receipt_path']
    elif operation == 'rollback':
        path = request['execution']['rollback_receipt_path']
        recovery = {'task_id': TASK_ID, 'operation': 'FORWARD_RECOVERY', 'target_republished': False,
            'backup_manifest_sha256': installed['backup_manifest_sha256'], 'public_verification': public,
            'restored_semantics': 'safe non-target invariants; sold target remains absent', 'worker_evidence': installed}
        write_receipt(root, 'state/receipts/' + TASK_ID + '-FORWARD-RECOVERY.json', recovery)
    else:
        path = request['execution']['receipt_path']
        if installed.get('_controller_recovery_performed'):
            recovery = {'task_id': TASK_ID, 'operation': 'FORWARD_RECOVERY', 'target_republished': False,
                'initial_error_code': installed.get('_controller_initial_error_code'),
                'backup_manifest_sha256': installed['backup_manifest_sha256'], 'public_verification': public,
                'restored_semantics': 'safe non-target invariants; sold target remains absent', 'worker_evidence': installed}
            write_receipt(root, 'state/receipts/' + TASK_ID + '-FORWARD-RECOVERY.json', recovery)
    write_receipt(root, path, receipt)
    return receipt

if __name__ == '__main__':
    try:
        execute('install_verify')
    except Exception as exc:
        code = str(exc) if isinstance(exc, AdapterError) and re.fullmatch(r'[A-Za-z0-9_.-]+', str(exc)) else 'ADAPTER_STOP'
        print('UA0002_ADAPTER_STOP:' + code)
        raise SystemExit(1) from None
