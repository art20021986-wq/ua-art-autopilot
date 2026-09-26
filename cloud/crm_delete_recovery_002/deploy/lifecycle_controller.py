"""Source-bound installation lifecycle candidate. CLI defaults to inspection.

No provider request occurs on import or inspection. New installation requires
the existing repository authority, exact separate owner approval, and a ready
independent watchdog. Recovery is restricted to this journal's prior pause.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import copy
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent


def _bootstrap_cli_sources():
    """Verify all local executable modules before importing any release code."""
    if '--help' in sys.argv or '-h' in sys.argv:
        print('Read-only: --plan PATH --plan-sha256 SHA. Execution additionally requires --execute and all existing authority gates. Recovery: --recover CONTEXT --context-sha256 SHA.')
        raise SystemExit(0)
    def argument(name):
        if name not in sys.argv or sys.argv.index(name) + 1 >= len(sys.argv):
            raise SystemExit('Missing hash-bound lifecycle argument: ' + name)
        return sys.argv[sys.argv.index(name) + 1]
    def bound(path, digest):
        path = Path(path)
        if not path.is_absolute() or path.resolve(strict=True) != path:
            raise SystemExit('Noncanonical bootstrap source')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise SystemExit('Bootstrap source hash mismatch')
        return json.loads(raw)
    if '--recover' in sys.argv:
        context = bound(argument('--recover'), argument('--context-sha256'))
        plan = bound(context['lifecycle_plan_path'], context['lifecycle_plan_sha256'])
        if plan['package_manifest_sha256'] != context['package_manifest_sha256']:
            raise SystemExit('Recovery manifest binding mismatch')
    else:
        plan = bound(argument('--plan'), argument('--plan-sha256'))
    for name in ('lifecycle_controller.py', 'lifecycle_worker.py', 'package_install.py', 'watchdog.py'):
        path = HERE / name
        if path.resolve(strict=True) != path or hashlib.sha256(path.read_bytes()).hexdigest() != plan['package_sources'][name]:
            raise SystemExit('Executable package source changed: ' + name)


if __name__ == '__main__':
    _bootstrap_cli_sources()
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from package_install import Package, atomic, canonical_root, encoded, fingerprint, relative, require, sha
from lifecycle_worker import InstallWorker

BASE = 'https://www.pythonanywhere.com/api/v0/user/Carix/'
COMMAND = 'python3.10 /home/Carix/start_safe.py'
TASK = 'UA-ART-CRM-DELETE-RECOVERY-002-INSTALL'
PARENT_TASK = 'UA-ART-CRM-DELETE-RECOVERY-002'
ACCEPTANCE_SCOPE = 'INSTALLATION_AND_RUNTIME_HTTP_VERIFY'


def read_bound(path, expected):
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path and path.is_file(), 'BOUND_REGULAR_PATH_REQUIRED')
    raw = path.read_bytes()
    require(sha(raw) == expected, 'BOUND_SOURCE_OR_DOCUMENT_HASH_MISMATCH')
    return raw


def load_control_plane(path, expected):
    read_bound(path, expected)
    spec = importlib.util.spec_from_file_location('_ua002_trusted_control_plane', path)
    cp = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = cp
    spec.loader.exec_module(cp)
    return cp


def installation_policy_sha256(plan):
    """Bind immutable behavior without hashing the request/approval envelope.

    main_commit can contain the approval/request documents and is verified live;
    excluding it and their hashes avoids a policy -> approval -> commit cycle.
    The executable authority sources and repository scope remain policy-bound.
    """
    static = {key: plan[key] for key in ('version', 'task_id', 'parent_task_id', 'acceptance_scope', 'package_sources',
        'package_manifest_path', 'package_manifest_sha256', 'maximum_seconds', 'provider', 'http_checks')}
    static['authority_policy'] = {key: plan['authority'][key] for key in
        ('control_plane_sha256', 'critical_workflow_sha256', 'trusted_controller_sha256')}
    return sha(encoded(static))


def verify_installation_policy(plan, request=None, approval=None):
    require(plan.get('version') == 1 and plan.get('task_id') == TASK and
            plan.get('parent_task_id') == PARENT_TASK and plan.get('acceptance_scope') == ACCEPTANCE_SCOPE,
            'INSTALLATION_POLICY_SCOPE')
    digest = installation_policy_sha256(plan)
    require(plan.get('installation_policy_sha256') == digest, 'INSTALLATION_POLICY_CHANGED')
    if request is not None:
        require(request.get('installation_policy_sha256') == digest, 'REQUEST_INSTALLATION_POLICY_BINDING')
        expected = plan['authority']['installation_approval']
        critical = request.get('critical') or {}
        require(critical.get('owner_approval_path') == expected['path'] and
                critical.get('owner_approval_sha256') == expected['sha256'], 'REQUEST_INSTALLATION_APPROVAL_BINDING')
    if approval is not None:
        require(request is not None, 'APPROVAL_EXACT_REQUEST_REQUIRED')
        subject = copy.deepcopy(request)
        subject['critical']['owner_approval_sha256'] = '0' * 64
        subject_sha = sha((json.dumps(subject, ensure_ascii=False, sort_keys=True,
            separators=(',', ':')) + '\n').encode('utf-8'))
        require(approval.get('request_subject_sha256') == subject_sha and
                approval.get('manifest_sha256') == request['critical']['manifest_sha256'],
                'APPROVAL_INSTALLATION_POLICY_BINDING')
    return digest


def verify_open_transaction(*, root, authority, cp, claim, request, request_sha,
                            backup_rel, backup_path, transaction_rel, expected_state='OPEN'):
    """Eligibility is not an OPEN transaction; verify the persisted exact state."""
    path = relative(root, transaction_rel)
    require(expected_state in ('OPEN', 'PREPARING', 'ROLLING_BACK'), 'EXACT_TRANSACTION_PHASE_REQUIRED')
    require(path.is_file(), 'PERSISTED_OPEN_TRANSACTION_REQUIRED')
    value = json.loads(path.read_bytes())
    keys = {'autostart_ledger_path', 'backup_manifest_sha256', 'backup_receipt_path',
        'backup_receipt_sha256', 'expires_at', 'mode_epoch', 'opened_at', 'prepared_at',
        'request_path', 'request_sha256', 'run_id', 'schema_version', 'status', 'task_id', 'transaction_id'}
    require(set(value) == keys and value.get('schema_version') == cp.PRODUCTION_TRANSACTION_SCHEMA and
            value.get('status') == expected_state and value.get('request_path') == authority['request_path'] and
            value.get('request_sha256') == request_sha and value.get('run_id') == str(authority['run_id']) and
            value.get('transaction_id') == str(authority['transaction_id']) and value.get('task_id') == TASK and
            value.get('backup_receipt_path') == backup_rel and value.get('mode_epoch') == claim.get('mode_epoch') and
            value.get('autostart_ledger_path') == claim.get('autostart_ledger_path') and
            claim.get('production_transaction_id') == str(authority['transaction_id']) and
            claim.get('production_transaction_path') == transaction_rel and
            claim.get('production_transaction_status') == expected_state, 'PERSISTED_TRANSACTION_NOT_EXACT_OPEN')
    now = datetime.now(timezone.utc)
    prepared, expiry = (cp.parse_utc(str(value[key])) for key in ('prepared_at', 'expires_at'))
    require(prepared <= now and (expected_state == 'ROLLING_BACK' or now < expiry), 'OPEN_TRANSACTION_TIME_BINDING')
    ledger = json.loads(relative(root, value['autostart_ledger_path']).read_bytes())
    require(value['expires_at'] == ledger.get('expires_at'), 'OPEN_TRANSACTION_LEDGER_EXPIRY')
    require(Path(backup_path) == relative(root, backup_rel), 'OPEN_TRANSACTION_BACKUP_SCOPE')
    if expected_state == 'PREPARING':
        require(value['opened_at'] is None and value['backup_manifest_sha256'] is None and
                value['backup_receipt_sha256'] is None and not Path(backup_path).exists(),
                'PREPARING_BACKUP_STATE_REQUIRED')
        return {'transaction_path': transaction_rel, 'transaction_status': expected_state,
                'transaction_sha256': sha(encoded(value)), 'backup_receipt_sha256': None}
    opened = cp.parse_utc(str(value['opened_at']))
    require(prepared <= opened <= now and opened < expiry, 'OPEN_TRANSACTION_TIME_BINDING')
    require(isinstance(value['backup_manifest_sha256'], str) and
            re.fullmatch(r'[0-9a-f]{64}', value['backup_manifest_sha256']), 'OPEN_TRANSACTION_BACKUP_MANIFEST')
    receipt = json.loads(read_bound(backup_path, value['backup_receipt_sha256']))
    receipt_keys = {'task_id', 'request_sha256', 'run_id', 'transaction_id', 'manifest_sha256',
        'backup_manifest_sha256', 'schema_version', 'operation', 'status', 'backup', 'unexpected_changes'}
    require(set(receipt) == receipt_keys and receipt.get('schema_version') == 'UA-ART-PRODUCTION-BACKUP-RECEIPT-1' and
            receipt.get('operation') == 'backup' and receipt.get('status') == 'PASS' and receipt.get('backup') == 'PASS' and
            type(receipt.get('unexpected_changes')) is int and receipt['unexpected_changes'] == 0 and
            receipt.get('task_id') == TASK and receipt.get('request_sha256') == request_sha and
            receipt.get('run_id') == str(authority['run_id']) and
            receipt.get('transaction_id') == str(authority['transaction_id']) and
            receipt.get('manifest_sha256') == request.get('critical', {}).get('manifest_sha256') and
            receipt.get('backup_manifest_sha256') == value['backup_manifest_sha256'], 'OPEN_TRANSACTION_BACKUP_BINDING')
    return {'transaction_path': transaction_rel, 'transaction_status': expected_state,
            'transaction_sha256': sha(encoded(value)), 'backup_receipt_sha256': value['backup_receipt_sha256']}


def verify_pinned_recovery_sources(*, root, source_root, authority, claim, request_sha, backup_rel, transaction_rel):
    """The workflow overlays exactly five current durable files on pinned code."""
    source_commit = authority['code_source_commit']
    require(claim.get('autostart_source_commit') == source_commit, 'PINNED_RECOVERY_CLAIM_SOURCE')
    ledger_rel = claim['autostart_ledger_path']
    ledger = json.loads(relative(root, ledger_rel).read_bytes())
    require(ledger.get('source_commit') == source_commit, 'PINNED_RECOVERY_LEDGER_SOURCE')
    subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', source_commit, authority['main_commit']],
                   check=True, timeout=20, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    claim_rel = 'state/claims/%s.%s.%s.json' % (TASK, request_sha, authority['run_id'])
    paths = (claim_rel, transaction_rel, authority['request_path'], ledger_rel, backup_rel)
    require(len(set(paths)) == 5, 'PINNED_DURABLE_PATH_ALIAS')
    digests = {}
    for name in paths:
        current, overlaid = relative(root, name), relative(source_root, name)
        require(current.is_file() and overlaid.is_file(), 'PINNED_DURABLE_FILE_REQUIRED')
        raw = current.read_bytes()
        require(len(raw) <= 2 * 1024 * 1024 and overlaid.read_bytes() == raw, 'PINNED_DURABLE_OVERLAY_MISMATCH')
        digests[name] = sha(raw)
    return {'code_source_commit': source_commit, 'authority_main_commit': authority['main_commit'],
            'durable_overlay_sha256': digests}


class RepositoryAdmission:
    def __init__(self, plan):
        self.plan = plan

    def check(self, *, operation='execute'):
        require(operation in ('backup', 'execute', 'rollback'), 'EXACT_INSTALLATION_OPERATION_REQUIRED')
        authority = self.plan['authority']
        root = canonical_root(authority['repository_root'])
        source_root = canonical_root(authority.get('source_repository_root', root))
        # This concrete existing halt is always checked first, including before
        # importing a control-plane module. Never clear it or enable recovery
        # exceptions for a new installation.
        if operation != 'rollback':
            require(not (root / 'state/AUTOPILOT_HALT.json').exists(), 'EXISTING_AUTOPILOT_HALT_BLOCKS_INSTALL')
        policy_sha = verify_installation_policy(self.plan)
        expected = authority['main_commit']
        require(re.fullmatch(r'[0-9a-f]{40}', expected), 'IMMUTABLE_MAIN_COMMIT_REQUIRED')
        def git(*args):
            return subprocess.check_output(['git', '-C', str(root), *args], timeout=20,
                                           stderr=subprocess.DEVNULL).decode().strip()
        require(git('rev-parse', 'HEAD') == expected, 'LOCAL_AUTHORITY_COMMIT_DRIFT')
        remote = git('ls-remote', 'origin', 'refs/heads/main').split()
        require(len(remote) == 2 and remote == [expected, 'refs/heads/main'], 'REMOTE_MAIN_DRIFT')
        source_commit = authority.get('code_source_commit', expected)
        require(re.fullmatch(r'[0-9a-f]{40}', source_commit), 'IMMUTABLE_CODE_SOURCE_COMMIT_REQUIRED')
        actual_source = subprocess.check_output(['git', '-C', str(source_root), 'rev-parse', 'HEAD'],
                                               timeout=20, stderr=subprocess.DEVNULL).decode().strip()
        require(actual_source == source_commit, 'PINNED_CODE_SOURCE_COMMIT_DRIFT')
        require(operation == 'rollback' or (source_root == root and source_commit == expected),
                'NEW_INSTALLATION_REQUIRES_CURRENT_SOURCE')
        cp_path = source_root / 'automation/control_plane.py'
        read_bound(cp_path, authority['control_plane_sha256'])
        read_bound(source_root / '.github/workflows/uaart_critical.yml', authority['critical_workflow_sha256'])
        cp = load_control_plane(cp_path, authority['control_plane_sha256'])
        if operation == 'rollback':
            # Existing control-plane recovery interface grants no new write.
            # The exact consumed ROLLING_BACK transaction is required below.
            _, claim, request, request_sha = cp._load_claim_for_recovery(
                authority['request_path'], authority['run_id'], root=root)
            backup_rel = cp.safe_repo_path(request['execution']['backup_receipt_path'])
            backup_path = relative(root, backup_rel)
            transaction_rel = cp.transaction_relative_path(cp._identity(request, request_sha, authority['run_id']))
        else:
            cp.verify_execution_mode(root=root, required_mode='AUTOMATIC', allow_halt_for_recovery=False)
            values = cp._production_transaction_context(authority['request_path'], authority['run_id'],
                                                        authority['transaction_id'], root=root)
            _, claim, request, request_sha, backup_rel, backup_path, transaction_rel = values
        require(request.get('task_id') == TASK and request.get('parent_task_id') == PARENT_TASK and
                request.get('acceptance_scope') == ACCEPTANCE_SCOPE and request.get('production_required') is True,
                'EXACT_PRODUCTION_TASK_REQUIRED')
        require(request_sha == authority['request_sha256'], 'EXACT_REQUEST_HASH_REQUIRED')
        recovery_source = None
        if operation == 'rollback':
            recovery_source = verify_pinned_recovery_sources(root=root, source_root=source_root,
                authority=authority, claim=claim, request_sha=request_sha,
                backup_rel=backup_rel, transaction_rel=transaction_rel)
        transaction = verify_open_transaction(root=root, authority=authority, cp=cp,
            claim=claim, request=request, request_sha=request_sha, backup_rel=backup_rel,
            backup_path=backup_path, transaction_rel=transaction_rel,
            expected_state={'backup':'PREPARING', 'execute':'OPEN', 'rollback':'ROLLING_BACK'}[operation])
        trusted = claim.get('trusted_package') or {}
        require(trusted.get('controller_sha256') == authority['trusted_controller_sha256'],
                'CONTROL_PLANE_CONTROLLER_BINDING')
        approval = authority['installation_approval']
        path = relative(root, approval['path'])
        approved = json.loads(read_bound(path, approval['sha256']))
        verify_installation_policy(self.plan, request=request, approval=approved)
        approval_keys = {'approved_at', 'authorization_id', 'authorized_environment', 'expires_at', 'gate_a_sha256',
            'launch_nonce', 'manifest_sha256', 'mode_epoch', 'owner', 'owner_authorized', 'production_allowed',
            'request_path', 'request_subject_sha256', 'schema_version', 'task_id'}
        require(set(approved) == approval_keys and approved.get('task_id') == TASK and
                approved.get('schema_version') == 'UA-ART-PRODUCTION-AUTHORIZATION-1' and
                approved.get('owner_authorized') is True and approved.get('production_allowed') is True and
                approved.get('authorized_environment') == 'production' and
                approved.get('request_path') == authority['request_path'] and
                approved.get('manifest_sha256') == request['critical']['manifest_sha256'] and
                approved.get('gate_a_sha256') == request['critical']['gate_a_sha256'] and
                approved.get('mode_epoch') == claim.get('mode_epoch') and
                approved.get('owner') == 'Артём Бровинский / UA ART COMPANY LLC',
                'SEPARATE_PACKAGE_BOUND_INSTALLATION_COMMAND_REQUIRED')
        return {'status': 'EXISTING_AUTHORITY_PASS', 'main_commit': expected,
                'request_sha256': request_sha, 'installation_approval_sha256': approval['sha256'],
                'run_id': authority['run_id'], 'transaction_id': authority['transaction_id'],
                'installation_policy_sha256': policy_sha, 'open_transaction': transaction,
                'recovery_source': recovery_source,
                'package_manifest_sha256': self.plan['package_manifest_sha256'], 'checked_epoch': time.time()}


class ProviderAPI:
    def __init__(self, token=None, *, clock=time.monotonic, sleep=time.sleep):
        self.token = token if token is not None else os.environ.get('PYTHONANYWHERE_API_TOKEN', '').strip()
        require(bool(self.token), 'PROVIDER_CREDENTIAL_NOT_AVAILABLE')
        self._clock, self._sleep, self._last_request = clock, sleep, None

    def request(self, method, endpoint, fields=None):
        allowed = {'always_on/', 'schedule/', 'always_on/266084/', 'webapps/www.uaart.com.ua/reload/'}
        require(endpoint in allowed and method in ('GET', 'PATCH', 'POST'), 'PROVIDER_OPERATION_SCOPE')
        require(method == 'GET' or (method, endpoint) in {
            ('PATCH', 'always_on/266084/'), ('POST', 'webapps/www.uaart.com.ua/reload/')}, 'PROVIDER_MUTATION_SCOPE')
        data = urllib.parse.urlencode(fields or {}).encode() if method != 'GET' else None
        req = urllib.request.Request(BASE + endpoint, data=data, method=method,
            headers={'Authorization': 'Token ' + self.token, 'Content-Type': 'application/x-www-form-urlencoded'})
        if self._last_request is not None:
            remaining = 3.2 - (self._clock() - self._last_request)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request = self._clock()
        try:
            with urllib.request.build_opener(NoRedirect()).open(req, timeout=30) as response:
                raw = response.read(512 * 1024 + 1)
        except Exception as exc:
            raise RuntimeError('PROVIDER_REQUEST_FAILED:' + type(exc).__name__) from None
        require(len(raw) <= 512 * 1024, 'PROVIDER_RESPONSE_BOUND')
        return json.loads(raw or b'{}')

    def supervisor(self):
        row = self.request('GET', 'always_on/266084/')
        require(row.get('id') == 266084 and row.get('command') == COMMAND, 'CRM_SUPERVISOR_IDENTITY_DRIFT')
        return row

    def set_enabled(self, enabled):
        self.supervisor()
        self.request('PATCH', 'always_on/266084/', {'enabled': str(bool(enabled)).lower()})
        deadline = self._clock() + 75
        while self._clock() < deadline:
            row = self.supervisor()
            if row.get('enabled') is enabled and (not enabled or str(row.get('state', '')).lower() == 'running'):
                return {'id': 266084, 'enabled': enabled, 'state': row.get('state')}
            self._sleep(.5)
        raise RuntimeError('CRM_ENABLE_READBACK_TIMEOUT' if enabled else 'CRM_DISABLE_READBACK_TIMEOUT')

    def reload(self):
        return self.request('POST', 'webapps/www.uaart.com.ua/reload/')


def provider_inventory(api, plan, *, clock=time.time):
    def rows(value):
        if isinstance(value, dict):
            value = value.get('results', value.get('objects', value.get('tasks')))
        require(isinstance(value, list) and all(isinstance(row, dict) for row in value), 'PROVIDER_LIST_SHAPE')
        return value
    always, schedule = rows(api.request('GET', 'always_on/')), rows(api.request('GET', 'schedule/'))
    normalize = lambda row: {'id': row['id'], 'command_sha256': sha(str(row['command']).encode()), 'enabled': row['enabled']}
    aa = sorted([normalize(row) for row in always], key=lambda row: row['id'])
    ss = sorted([dict(normalize(row), hour=row.get('hour'), minute=row['minute'], interval=row['interval'])
                 for row in schedule], key=lambda row: row['id'])
    require(aa == plan['provider']['always_on'] and ss == plan['provider']['scheduled'], 'FRESH_PROVIDER_INVENTORY_DRIFT')
    now = datetime.fromtimestamp(clock(), timezone.utc)
    required_window = plan['maximum_seconds'] + 900 + 120
    for row in ss:
        if row['enabled'] is False:
            continue
        minute, hour = row['minute'], row['hour']
        require(type(minute) is int and 0 <= minute < 60, 'SCHEDULE_MINUTE_UNSUPPORTED')
        if row['interval'] == 'daily' and type(hour) is int and 0 <= hour < 24:
            when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if when <= now:
                when += timedelta(days=1)
        elif row['interval'] == 'hourly':
            when = now.replace(minute=minute, second=0, microsecond=0)
            if when <= now:
                when += timedelta(hours=1)
        else:
            raise RuntimeError('SCHEDULE_INTERVAL_UNSUPPORTED')
        require((when - now).total_seconds() > required_window, 'SCHEDULE_DUE_DURING_INSTALL')
    monitor = next((row for row in always if row['id'] == 270984), None)
    require(monitor is not None, 'REVIEWED_MONITOR_MISSING')
    argv = shlex.split(monitor['command'])
    require(bool(argv), 'MONITOR_COMMAND_EMPTY')
    argv[0] = Path(argv[0]).name
    require(plan['provider']['monitor_python_sha256'] == sha(encoded(argv)), 'MONITOR_PROCESS_SOURCE_BINDING')
    return {'observed_epoch': clock(), 'always_on_sha256': sha(encoded(aa)), 'scheduled_sha256': sha(encoded(ss))}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


def probe_http(plan, *, installed):
    checks = plan['http_checks']['installed' if installed else 'baseline']
    require(isinstance(checks, list) and 0 < len(checks) <= 12, 'EXACT_BOUNDED_HTTP_ACCEPTANCE_REQUIRED')
    opener = urllib.request.build_opener(NoRedirect())
    evidence = []
    for item in checks:
        parsed = urllib.parse.urlsplit(item['url'])
        require(parsed.scheme == 'https' and parsed.hostname in ('uaart.com.ua', 'www.uaart.com.ua') and
                not parsed.username and not parsed.fragment and parsed.port in (None, 443), 'HTTP_SCOPE')
        request = urllib.request.Request(item['url'], headers={'Cache-Control': 'no-cache'})
        try:
            response = opener.open(request, timeout=15)
        except urllib.error.HTTPError as response:
            status, body = response.code, response.read(8 * 1024 * 1024 + 1)
        else:
            with response:
                status, body = response.status, response.read(8 * 1024 * 1024 + 1)
        require(status == item['status'] and len(body) <= 8 * 1024 * 1024, 'HTTP_STATUS_OR_SIZE_MISMATCH')
        if item.get('body_sha256') is not None:
            require(sha(body) == item['body_sha256'], 'HTTP_BODY_MISMATCH')
        evidence.append({'url': item['url'], 'status': status, 'body_sha256': sha(body), 'observed_epoch': time.time()})
    return evidence


class Lifecycle:
    def __init__(self, *, plan, context, context_sha256, directory, admission, api, worker,
                 probe=probe_http, watchdog_ready=lambda: False, fault=lambda stage: None):
        self.plan, self.context, self.context_sha = plan, context, context_sha256
        self.directory = canonical_root(directory)
        self.path = self.directory / 'lifecycle.json'
        self.result_path = Path(context['result_path'])
        require(self.result_path.parent == self.directory, 'EXACT_RESULT_DIRECTORY')
        self.admission, self.api, self.worker = admission, api, worker
        self.probe, self.watchdog_ready, self.fault = probe, watchdog_ready, fault

    def save(self, journal, stage, **fields):
        journal.update(stage=stage, **fields)
        atomic(self.path, encoded(journal))
        self.fault(stage)

    def identity(self):
        return {'context_sha256': self.context_sha, 'package_manifest_sha256': self.plan['package_manifest_sha256'],
                'owner_pid': self.context['owner_pid'], 'start_ticks': self.context['start_ticks'], 'pgid': self.context['pgid']}

    def terminal(self, journal, status, **extra):
        value = dict(self.identity(), status=status, safe_to_stop=True,
                     live_telegram_action_verified=False, **extra)
        self.save(journal, 'TERMINAL', result=value)
        atomic(self.result_path, encoded(value))
        return value

    def run(self, *, recovery=False):
        lock = self.directory / 'lifecycle.lock'
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return self._run(recovery=recovery)
        finally:
            os.close(fd)

    def _run(self, *, recovery):
        if self.path.exists():
            journal = json.loads(self.path.read_bytes())
            require(all(journal.get(k) == v for k, v in self.identity().items()), 'LIFECYCLE_JOURNAL_IDENTITY')
            if journal['stage'] == 'TERMINAL':
                # The durable terminal journal precedes its external result.
                # Repair a crash in that gap without repeating any operation.
                if self.result_path.exists():
                    require(json.loads(self.result_path.read_bytes()) == journal['result'], 'TERMINAL_RESULT_CONFLICT')
                else:
                    atomic(self.result_path, encoded(journal['result']))
                return journal['result']
            require(recovery, 'EXISTING_LIFECYCLE_REQUIRES_RECOVERY')
            require(journal.get('admission', {}).get('status') == 'EXISTING_AUTHORITY_PASS', 'ORIGINAL_ADMISSION_REQUIRED')
        else:
            if recovery:
                # The first provider mutation is always preceded by a durable
                # PAUSE_INTENT. No journal proves this owner never paused CRM.
                return self.terminal(dict(self.identity()), 'RECOVERED', no_pause_or_application_write=True)
            admitted = self.admission.check()
            require(admitted.get('status') == 'EXISTING_AUTHORITY_PASS', 'ADMISSION_REQUIRED')
            inventory = provider_inventory(self.api, self.plan)
            require(self.api.supervisor().get('enabled') is True, 'CRM_MUST_START_ENABLED')
            require(self.watchdog_ready() is True, 'INDEPENDENT_WATCHDOG_NOT_READY')
            journal = dict(self.identity(), stage='ADMITTED', admission=admitted, provider_inventory=inventory)
            atomic(self.path, encoded(journal))
        if recovery and journal['stage'] == 'ADMITTED':
            return self.terminal(journal, 'RECOVERED', no_pause_or_application_write=True)
        try:
            if journal['stage'] == 'ADMITTED':
                # Recheck immediately before the first provider mutation.
                self.admission.check()
                provider_inventory(self.api, self.plan)
                self.save(journal, 'PAUSE_INTENT')
                self.api.set_enabled(False)
                self.save(journal, 'PAUSED')
                self.save(journal, 'INSTALLING')
                mechanical = self.worker.backup_and_apply()
                self.save(journal, 'INSTALLED', mechanical=mechanical, installed=True)
            elif journal['stage'] in ('PAUSE_INTENT', 'PAUSED', 'INSTALLING', 'ROLLBACK_PAUSE_INTENT', 'ROLLBACK_STARTED'):
                self.api.set_enabled(False)
                outcome = self.worker.recover()
                self.save(journal, 'INSTALLED' if outcome == 'INSTALLED' else 'BASELINE_READY', installed=outcome == 'INSTALLED')
            if journal['stage'] in ('INSTALLED', 'BASELINE_READY', 'RELOAD_INTENT'):
                self.save(journal, 'RELOAD_INTENT')
                self.api.reload()
                checks = self.probe(self.plan, installed=journal['installed'])
                self.save(journal, 'READY_RESUME', http=checks)
            if journal['stage'] == 'READY_RESUME':
                self.save(journal, 'RESUME_INTENT', resume_epoch=time.time())
            if journal['stage'] == 'RESUME_INTENT':
                resumed = self.api.set_enabled(True)
                self.save(journal, 'RESUMED', crm_resume=resumed)
            if journal['stage'] == 'RESUMED':
                started = self.worker.startup(since_epoch=journal['resume_epoch'], installed=journal['installed'])
                return self.terminal(journal, 'COMPLETE' if journal['installed'] else 'ROLLED_BACK',
                                     crm_resume=journal['crm_resume'], runtime=started,
                                     http=journal.get('http', []))
            raise RuntimeError('UNSUPPORTED_LIFECYCLE_STAGE')
        except Exception as exc:
            # A resume request may have succeeded despite an API timeout. Keep
            # RESUME_INTENT so the watchdog retries only resume/read-back.
            if journal['stage'] == 'RESUME_INTENT':
                raise
            if journal['stage'] in ('PAUSE_INTENT', 'PAUSED', 'INSTALLING', 'INSTALLED', 'RELOAD_INTENT',
                                    'READY_RESUME', 'RESUMED'):
                try:
                    self.save(journal, 'ROLLBACK_PAUSE_INTENT', original_error=type(exc).__name__)
                    self.api.set_enabled(False)
                    self.save(journal, 'ROLLBACK_STARTED')
                    outcome = self.worker.recover()
                    if outcome == 'INSTALLED':
                        self.worker.rollback()
                    self.save(journal, 'BASELINE_READY', installed=False)
                    self.api.reload()
                    checks = self.probe(self.plan, installed=False)
                    self.save(journal, 'RESUME_INTENT', resume_epoch=time.time(), http=checks)
                    resumed = self.api.set_enabled(True)
                    self.save(journal, 'RESUMED', crm_resume=resumed)
                    started = self.worker.startup(since_epoch=journal['resume_epoch'], installed=False)
                    return self.terminal(journal, 'ROLLED_BACK', crm_resume=resumed, runtime=started, http=checks)
                except Exception as restore:
                    if journal['stage'] == 'RESUME_INTENT':
                        raise
                    return self.terminal(journal, 'BLOCKED', error_code=type(restore).__name__,
                                         recovery_confirmed=False, crm_resume_confirmed=False)
            raise


def load_plan(path, expected):
    path = Path(path)
    plan = json.loads(read_bound(path, expected))
    require(plan.get('version') == 1 and plan.get('task_id') == TASK and
            plan.get('parent_task_id') == PARENT_TASK and plan.get('acceptance_scope') == ACCEPTANCE_SCOPE,
            'LIFECYCLE_PLAN_CONTRACT')
    require(type(plan.get('maximum_seconds')) is int and 60 <= plan['maximum_seconds'] <= 1200, 'BOUNDED_LIFECYCLE_REQUIRED')
    verify_installation_policy(plan)
    for name in ('lifecycle_controller.py', 'lifecycle_worker.py', 'package_install.py', 'watchdog.py'):
        read_bound(HERE / name, plan['package_sources'][name])
    manifest = Path(plan['package_manifest_path'])
    require(manifest.is_relative_to(path.parent), 'STAGED_MANIFEST_SCOPE')
    package = Package(manifest.parent, plan['package_manifest_sha256'])
    require(not package.report()['runtime_payload_missing'] and not package.report()['writer_payload_missing'],
            'COMPLETE_RELEASE_PAYLOAD_REQUIRED')
    return plan, package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--plan-sha256')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--recover', type=Path)
    parser.add_argument('--context-sha256')
    args = parser.parse_args()
    require(not args.execute and not args.recover, 'PHASE_REMOTE_WORKER_REQUIRED_FOR_MUTATION')
    if args.recover:
        from watchdog import BoundContext
        raw_context = json.loads(read_bound(args.recover, args.context_sha256))
        bound = BoundContext(args.recover, args.context_sha256, raw_context['watchdog_source_sha256'])
        context = bound.data
        plan, package = load_plan(context['lifecycle_plan_path'], context['lifecycle_plan_sha256'])
        context_path, context_sha = args.recover, args.context_sha256
        ready = lambda: True  # Recovery is itself the independent watchdog child.
    else:
        require(args.plan is not None and args.plan_sha256, 'HASH_BOUND_PLAN_REQUIRED')
        plan, package = load_plan(args.plan, args.plan_sha256)
        if not args.execute:
            print(json.dumps(dict(package.report(), lifecycle_source_verified=True, provider_requests=0), sort_keys=True))
            return 0
        # No pause/journal/watchdog until the existing authority approves this
        # exact release and separate installation command.
        RepositoryAdmission(plan).check()
        from watchdog import launch_watchdog
        try:
            os.setsid()
        except PermissionError:
            pass
        require(os.getpid() == os.getpgrp() == os.getsid(0), 'DEDICATED_OWNER_SESSION_REQUIRED')
        context_path = args.plan.parent / 'context.json'
        require(not context_path.exists(), 'EXISTING_CONTEXT_REQUIRES_RECOVERY')
        context = {'owner_pid': os.getpid(), 'start_ticks': int(Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()[19]),
                   'pgid': os.getpgrp(), 'deadline_epoch': time.time() + plan['maximum_seconds'],
                   'result_path': str(args.plan.parent / 'result.json'),
                   'recovery_argv': [sys.executable, '-I', '-B', str(Path(__file__).resolve()), '--recover',
                                     str(context_path), '--context-sha256', '@CONTEXT_SHA256@'],
                   'recovery_source_sha256': plan['package_sources']['lifecycle_controller.py'],
                   'watchdog_source_sha256': plan['package_sources']['watchdog.py'],
                   'package_manifest_sha256': plan['package_manifest_sha256'],
                   'package_manifest_path': plan['package_manifest_path'],
                   'lifecycle_plan_path': str(args.plan), 'lifecycle_plan_sha256': args.plan_sha256,
                   'credential_env_names': ['PYTHONANYWHERE_API_TOKEN']}
        raw = encoded(context)
        atomic(context_path, raw)
        context_sha = sha(raw)
        argv = [context_sha if value == '@CONTEXT_SHA256@' else value for value in context['recovery_argv']]
        launch_watchdog(context_path, context_sha, plan['package_sources']['watchdog.py'], argv)
        ready = lambda: True  # launch_watchdog returns only after exact readiness read-back.
    watchdog_argv = [sys.executable, '-I', '-B', str(HERE / 'watchdog.py'), '--watch', str(context_path),
                     '--context-sha256', context_sha, '--watchdog-sha256', plan['package_sources']['watchdog.py']]
    watchdog_argv[0] = Path(watchdog_argv[0]).name
    allowed = [plan['provider']['monitor_python_sha256'], sha(encoded(watchdog_argv))]
    worker = InstallWorker(package, allowed_python_sha256=allowed)
    lifecycle = Lifecycle(plan=plan, context=context, context_sha256=context_sha, directory=context_path.parent,
        admission=RepositoryAdmission(plan), api=ProviderAPI(), worker=worker, watchdog_ready=ready)
    result = lifecycle.run(recovery=bool(args.recover))
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] in ('COMPLETE', 'RECOVERED') else 1


if __name__ == '__main__':
    raise SystemExit(main())
