#!/usr/bin/env python3
"""In-process, fail-closed complete17 code handoff. No CLI or application import.

The holder calls this library while it still owns every legacy lock. It never
spawns a publisher, releases locks, changes task settings, clears maintenance,
or writes CRM/HTML/media. Independently authenticated authorization + prior
writer drain evidence is mandatory; a fence receipt alone is insufficient.

A crash leaves a durable journal and paused tasks. Restart must reacquire the
reviewed fence through its recovery route and call rollback_only; it cannot
resume installation. Even CODE_INSTALLED_READBACK does NOT authorize unpause:
loaded WSGI/worker and the overall recovery transaction require separate proof.
"""
from __future__ import annotations
import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import time
import uuid

MANIFEST_SHA256 = '14f42086fc8bc94aefc4e4c83bda50e01107c30d2ad893c00d658f60d0c64fff'
SCHEMA = 'UA-ART-COMPLETE17-CODE-HANDOFF-4'
PROOF_STATUS = 'AUTHENTICATED_PAUSE_AND_PRIOR_WRITER_DRAIN_VERIFIED'
SESSION_KEYS = ('repository', 'account', 'production_root', 'task_id', 'expected_main',
                'plan_sha256', 'run_id', 'run_attempt', 'nonce', 'epoch')
MAX_FILE = 4 * 1024 * 1024
MAX_JOURNAL = 256 * 1024

class HandoffError(RuntimeError):
    pass

def require(ok, error):
    if not ok:
        raise HandoffError(error)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()

def sha(data):
    return hashlib.sha256(data).hexdigest()

def _directory(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path, 'DIRECTORY_PATH')
    for item in (path, *path.parents):
        s = item.lstat()
        require(stat.S_ISDIR(s.st_mode), 'DIRECTORY_TYPE')
    return path

def _name(name):
    require(isinstance(name, str) and name and not name.startswith('/'), 'TARGET_NAME')
    require(str(PurePosixPath(name)) == name and '..' not in PurePosixPath(name).parts, 'TARGET_TRAVERSAL')
    return name

def _read(path, *, absent=False):
    _directory(path.parent)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        if absent:
            return None
        raise
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= MAX_FILE,
                'FILE_TYPE_SIZE_OR_LINKS')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            data = stream.read(MAX_FILE + 1)
        after, linked = os.fstat(fd), path.lstat()
        key = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(len(data) <= MAX_FILE and key(before) == key(after) == key(linked), 'FILE_CHANGED_DURING_READ')
        return {'data': data, 'sha256': sha(data), 'mode': stat.S_IMODE(after.st_mode),
                'mtime_ns': after.st_mtime_ns, 'atime_ns': after.st_atime_ns,
                'device': after.st_dev, 'inode': after.st_ino}
    finally:
        os.close(fd)

def _sync(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def _exclusive(path, data, mode=0o600):
    _directory(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        os.fchmod(stream.fileno(), mode)
        stream.flush()
        os.fsync(stream.fileno())
    _sync(path.parent)

def _hash(path):
    value = _read(path, absent=True)
    return None if value is None else value['sha256']

def inspect_candidate(candidate):
    candidate = _directory(Path(candidate))
    raw = _read(candidate / 'manifest.json')['data']
    require(sha(raw) == MANIFEST_SHA256, 'EXACT_COMPLETE17_MANIFEST_REQUIRED')
    manifest = json.loads(raw)
    require(manifest['candidate_id'] == 'UA-ART-SPEC-AUTO10-COMPLETE-17-V3'
            and manifest['module_count'] == 17 and manifest['target_root'] == '/home/Carix', 'CANDIDATE_SCOPE')
    names = set(manifest['files'])
    require(len(names) == 17, 'TARGET_COUNT')
    found = set()
    for root, dirs, files in os.walk(candidate, followlinks=False):
        for item in dirs + files:
            require(not (Path(root) / item).is_symlink(), 'CANDIDATE_SYMLINK')
        found.update(str((Path(root) / name).relative_to(candidate)) for name in files)
    require(found == names | {'manifest.json'}, 'EXACT_CANDIDATE_FILE_SET')
    payload = {}
    for name in names:
        _name(name)
        item = _read(candidate / name)
        require(item['sha256'] == manifest['files'][name]['after_sha256'], 'CANDIDATE_HASH:' + name)
        compile(item['data'], name, 'exec')
        payload[name] = item['data']
    return manifest, payload

def make_install_plan(session, candidate, live_preconditions, *, coordination_plan_sha256):
    """Pure preparation. Preconditions must come from authenticated live capture.

    Assembly before_sha256 is intentionally not reused as a live precondition.
    A new helper may be absent on production despite existing in the assembler.
    """
    manifest, _ = inspect_candidate(candidate)
    require(set(live_preconditions) == set(manifest['files']), 'EXACT_LIVE_PRECONDITIONS_REQUIRED')
    for value in live_preconditions.values():
        require(value is None or isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'PRECONDITION_HASH')
    require(re.fullmatch('[0-9a-f]{64}', coordination_plan_sha256 or ''), 'COORDINATION_PLAN_HASH')
    binding = {key: session[key] for key in SESSION_KEYS}
    value = {'schema': SCHEMA, 'session': binding, 'candidate_manifest_sha256': MANIFEST_SHA256,
             'coordination_plan_sha256': coordination_plan_sha256,
             'installer_sha256': sha(Path(__file__).read_bytes()),
             'before': live_preconditions, 'after': {n: x['after_sha256'] for n, x in manifest['files'].items()},
             'dependencies': manifest['execution_dependency_pins'],
             'scope': 'CODE_ONLY_NO_APPLICATION_IMPORT_NO_UNPAUSE'}
    return {**value, 'install_plan_sha256': sha(canonical(value))}

class CodeHandoff:
    """No trustworthy verifier is bundled here. Integration MUST provide it.

    verify_window(plan, challenge, phase) independently checks current authority,
    exact approved plan + main/run/nonce/epoch, durable platform pause, prior
    invocation drain (including WSGI/manual), and current pause ownership.
    Its return is validated below, but a locally manufactured mapping is not
    proof. No CLI, default adapter, environment switch, or verified=True exists.
    """
    def __init__(self, lease, candidate, plan, *, verify_window):
        self.lease, self.candidate = lease, Path(candidate)
        self.plan = json.loads(canonical(plan))
        self.verifier = verify_window
        self.root = _directory(lease.root)
        self.directory = _directory(lease.directory)
        self.transaction = self.directory / 'code-handoff'
        self.journal_path = self.transaction / 'journal.jsonl'
        self.events = []
        self.fd = None
        self.manifest, self.payload = inspect_candidate(candidate)
        rebuilt = make_install_plan(lease.session, candidate, plan['before'],
                                    coordination_plan_sha256=plan['coordination_plan_sha256'])
        require(rebuilt == plan, 'INSTALL_PLAN_CHANGED_OR_WRONG_SESSION')
        self.proof_digests = []

    def _guard(self, phase):
        self.lease._check()
        require(sha(Path(__file__).read_bytes()) == self.plan['installer_sha256'], 'INSTALLER_SOURCE_CHANGED')
        require({k: self.lease.session[k] for k in SESSION_KEYS} == self.plan['session'], 'HOLDER_SESSION_CHANGED')
        require(self.lease.held and self.lease.pid == os.getpid(), 'SAME_LIVE_HOLDER_REQUIRED')
        challenge = uuid.uuid4().hex + uuid.uuid4().hex
        result = self.verifier(self.plan, challenge, phase)
        expected = {'status': PROOF_STATUS, 'challenge': challenge,
                    'session': self.plan['session'], 'install_plan_sha256': self.plan['install_plan_sha256'],
                    'coordination_plan_sha256': self.plan['coordination_plan_sha256'],
                    'candidate_manifest_sha256': MANIFEST_SHA256}
        require(type(result) is dict and all(result.get(k) == v for k, v in expected.items()), 'VERIFIED_WINDOW_REQUIRED')
        now = time.time()
        require(type(result.get('issued_at')) in (int, float) and type(result.get('expires_at')) in (int, float)
                and 0 <= now - result['issued_at'] <= 10
                and now < result['expires_at'] <= result['issued_at'] + 30, 'WINDOW_PROOF_STALE')
        for key in ('authorization_receipt_sha256', 'pause_readback_sha256', 'drain_receipt_sha256'):
            require(isinstance(result.get(key), str) and re.fullmatch('[0-9a-f]{64}', result[key]), 'WINDOW_EVIDENCE_HASH_REQUIRED')
        self.lease._check()
        require(self.lease.held and self.lease.pid == os.getpid(), 'SAME_LIVE_HOLDER_REQUIRED')
        require(sha(Path(__file__).read_bytes()) == self.plan['installer_sha256'], 'INSTALLER_SOURCE_CHANGED')
        require({k: self.lease.session[k] for k in SESSION_KEYS} == self.plan['session'], 'HOLDER_SESSION_CHANGED')
        self.proof_digests.append(sha(canonical(result)))
        return result

    def _append(self, event, **details):
        require(self.fd is not None, 'JOURNAL_NOT_OPEN')
        linked, opened = self.journal_path.lstat(), os.fstat(self.fd)
        require((linked.st_dev, linked.st_ino) == (opened.st_dev, opened.st_ino), 'JOURNAL_REPLACED')
        value = {'seq': len(self.events), 'event': event, 'install_plan_sha256': self.plan['install_plan_sha256'],
                 'holder_instance': self.lease.instance, **details}
        raw = canonical(value) + b'\n'
        require(os.write(self.fd, raw) == len(raw), 'JOURNAL_SHORT_WRITE')
        os.fsync(self.fd)
        _sync(self.transaction)
        self.events.append(value)

    def _dependencies(self):
        for name, expected in self.plan['dependencies'].items():
            _name(name)
            require(_hash(self.root / name) == expected, 'UNCHANGED_DEPENDENCY_DRIFT:' + name)

    def _all(self, expected):
        self._dependencies()
        for name, digest in expected.items():
            require(_hash(self.root / name) == digest, 'TARGET_READBACK_MISMATCH:' + name)

    def _backup(self):
        self._all(self.plan['before'])
        originals = [_read(self.root/name, absent=True) for name in self.plan['before']]
        needed = sum(len(item['data']) for item in originals if item is not None) + \
                 sum(len(value) for value in self.payload.values()) + \
                 max(len(value) for value in self.payload.values()) + 1024 * 1024
        proof = self._guard('STORAGE_PREFLIGHT')
        quota = proof.get('storage_quota')
        require(type(quota) is dict and set(quota) == {'source','used_bytes','quota_bytes','observed_at','receipt_sha256'},
                'AUTHENTICATED_ACCOUNT_QUOTA_REQUIRED')
        require(quota['source'] == 'AUTHENTICATED_PYTHONANYWHERE_ACCOUNT_QUOTA'
                and type(quota['used_bytes']) is int and type(quota['quota_bytes']) is int
                and 0 <= quota['used_bytes'] <= quota['quota_bytes'] and quota['quota_bytes'] > 0
                and type(quota['observed_at']) in (float,int) and 0 <= time.time()-quota['observed_at'] <= 30
                and isinstance(quota['receipt_sha256'],str) and re.fullmatch('[0-9a-f]{64}',quota['receipt_sha256']),
                'AUTHENTICATED_ACCOUNT_QUOTA_REQUIRED')
        ratio = quota['used_bytes'] / quota['quota_bytes']
        require(ratio < 0.90, 'ACCOUNT_QUOTA_EMERGENCY_STOP_90')
        require(ratio < 0.80, 'ACCOUNT_QUOTA_HEAVY_DEPLOY_GATE_80')
        require(quota['quota_bytes']-quota['used_bytes'] >= needed, 'ACCOUNT_QUOTA_FREE_BYTES_INSUFFICIENT')
        usage = os.statvfs(self.root)
        # PA statvfs describes a shared filesystem, not the paid account quota.
        # It is valid only as an additional absolute free-byte capacity check.
        require(usage.f_bavail * usage.f_frsize >= needed, 'FILESYSTEM_FREE_BYTES_INSUFFICIENT')
        self._append('STORAGE_PREFLIGHT', required_bytes=needed,
                     quota_receipt_sha256=quota['receipt_sha256'], account_used_bytes=quota['used_bytes'],
                     account_quota_bytes=quota['quota_bytes'], account_warning_70=ratio >= 0.70)
        backup = self.transaction / 'backup'
        backup.mkdir(mode=0o700)
        records = {}
        for index, name in enumerate(sorted(self.plan['before'])):
            original = _read(self.root / name, absent=True)
            require((None if original is None else original['sha256']) == self.plan['before'][name], 'BACKUP_PRECONDITION_CHANGED')
            if original is None:
                records[name] = {'absent': True}
            else:
                filename = str(index) + '.bin'
                _exclusive(backup / filename, original['data'])
                records[name] = {k: v for k, v in original.items() if k != 'data'} | {'file': filename, 'absent': False}
        raw = canonical({'install_plan_sha256': self.plan['install_plan_sha256'], 'files': records}) + b'\n'
        _exclusive(backup / 'manifest.json', raw)
        self._all(self.plan['before'])
        self._append('BACKUP_READY', backup_manifest_sha256=sha(raw))
        return records

    def _replace(self, name, data, expected, *, metadata=None):
        """Hash-conditional write in an owned, proven quiet window, never rm+mv."""
        path = self.root / _name(name)
        parent = _directory(path.parent)
        observed = _read(path, absent=True)
        require((None if observed is None else observed['sha256']) == expected, 'CONDITIONAL_WRITE_DRIFT:' + name)
        fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        temp = '.uaart-install-' + self.plan['session']['nonce'] + '-' + uuid.uuid4().hex
        try:
            directory = os.fstat(fd)
            if data is not None:
                mode = metadata['mode'] if metadata else (observed['mode'] if observed else 0o600)
                _exclusive(parent / temp, data, mode)
                staged = _read(parent / temp)
                self._append('TEMP_READY', target=name, temporary=temp, device=staged['device'],
                             inode=staged['inode'], sha256=staged['sha256'])
                if metadata:
                    os.utime(temp, ns=(metadata['atime_ns'], metadata['mtime_ns']), dir_fd=fd, follow_symlinks=False)
                require(_hash(path) == expected, 'CONDITIONAL_WRITE_DRIFT:' + name)
                require((parent.lstat().st_dev, parent.lstat().st_ino) == (directory.st_dev, directory.st_ino), 'TARGET_DIRECTORY_REPLACED')
                if expected is None:
                    # No renameat2 dependency (PA errno 22); hardlink is exclusive.
                    os.link(temp, path.name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
                    os.unlink(temp, dir_fd=fd)
                else:
                    os.replace(temp, path.name, src_dir_fd=fd, dst_dir_fd=fd)
            else:
                require(expected is not None, 'ABSENT_DELETE_FORBIDDEN')
                require(_hash(path) == expected, 'CONDITIONAL_DELETE_DRIFT:' + name)
                os.unlink(path.name, dir_fd=fd)
            os.fsync(fd)
        finally:
            try:
                os.unlink(temp, dir_fd=fd)
            except FileNotFoundError:
                pass
            os.close(fd)

    def _terminal(self, status):
        receipt = {'schema': SCHEMA, 'status': status, 'scope': self.plan['scope'],
                   'session': self.plan['session'], 'install_plan_sha256': self.plan['install_plan_sha256'],
                   'coordination_plan_sha256': self.plan['coordination_plan_sha256'],
                   'candidate_manifest_sha256': MANIFEST_SHA256,
                   'journal_sha256': sha(_read(self.journal_path)['data']),
                   'proof_digests': self.proof_digests, 'application_imported': False,
                   'crm_html_media_writes': 0, 'tasks_resumed': False, 'overall_gate_b': 'NOT_EVALUATED',
                   'loaded_runtime_verified': False, 'unpause_authorized': False}
        _exclusive(self.transaction / ('terminal-' + status + '.json'), canonical(receipt) + b'\n')
        return receipt

    def _clean_owned_staging(self):
        """Resolve the hardlink-publication crash window using durable inode proof."""
        for event in list(self.events):
            if event['event'] != 'TEMP_READY':
                continue
            name, temporary = event['target'], event['temporary']
            require(name in self.plan['before'] and isinstance(temporary, str)
                    and re.fullmatch(r'\.uaart-install-' + self.plan['session']['nonce'] + r'-[0-9a-f]{32}', temporary),
                    'STAGING_JOURNAL_SCOPE')
            require(event['sha256'] in (self.plan['before'][name], self.plan['after'][name]), 'STAGING_HASH_SCOPE')
            parent = _directory((self.root / name).parent)
            fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            opened = None
            try:
                try:
                    opened = os.open(temporary, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                except FileNotFoundError:
                    continue
                info = os.fstat(opened)
                require(stat.S_ISREG(info.st_mode) and info.st_nlink in (1, 2) and info.st_size <= MAX_FILE
                        and (info.st_dev, info.st_ino) == (event['device'], event['inode']), 'STAGING_IDENTITY_CHANGED')
                raw = os.read(opened, MAX_FILE + 1)
                require(sha(raw) == event['sha256'], 'STAGING_BYTES_CHANGED')
                if info.st_nlink == 2:
                    target = os.stat(Path(name).name, dir_fd=fd, follow_symlinks=False)
                    require((target.st_dev, target.st_ino) == (info.st_dev, info.st_ino), 'STAGING_UNKNOWN_LINK')
                current = os.stat(temporary, dir_fd=fd, follow_symlinks=False)
                require((current.st_dev, current.st_ino) == (info.st_dev, info.st_ino), 'STAGING_REPLACED')
                self._guard('BEFORE_STAGING_CLEANUP:' + name)
                self._append('STAGING_CLEANUP_INTENT', target=name, temporary=temporary)
                os.unlink(temporary, dir_fd=fd)
                os.fsync(fd)
            finally:
                if opened is not None:
                    os.close(opened)
                os.close(fd)

    def _rollback(self):
        self._guard('BEFORE_ROLLBACK')
        ready = [e for e in self.events if e['event'] == 'BACKUP_READY']
        require(len(ready) == 1, 'COMPLETE_BACKUP_REQUIRED')
        raw = _read(self.transaction / 'backup' / 'manifest.json')['data']
        require(sha(raw) == ready[0]['backup_manifest_sha256'], 'BACKUP_MANIFEST_CHANGED')
        backup = json.loads(raw)
        require(backup['install_plan_sha256'] == self.plan['install_plan_sha256']
                and set(backup['files']) == set(self.plan['before']), 'BACKUP_SCOPE')
        self._clean_owned_staging()
        # Validate all backed-up bytes and current write domains before restoring
        # any file. An unrelated write is never overwritten during rollback.
        data = {}
        for name, item in backup['files'].items():
            original = None if item['absent'] else _read(self.transaction / 'backup' / item['file'])['data']
            require((None if original is None else sha(original)) == self.plan['before'][name], 'BACKUP_BYTES_CHANGED')
            data[name] = original
        touched = list(dict.fromkeys(e['target'] for e in self.events if e['event'] == 'WRITE_INTENT'))
        require(set(touched) <= set(self.plan['before']), 'JOURNAL_TARGET_SCOPE')
        for name in touched:
            require(_hash(self.root / name) in (self.plan['before'][name], self.plan['after'][name]), 'ROLLBACK_FOREIGN_WRITE:' + name)
        self._append('ROLLBACK_STARTED')
        for name in reversed(touched):
            current = _hash(self.root / name)
            if current == self.plan['before'][name]:
                continue
            self._guard('BEFORE_ROLLBACK_WRITE:' + name)
            self._append('ROLLBACK_WRITE_INTENT', target=name)
            self._replace(name, data[name], self.plan['after'][name], metadata=backup['files'][name] if data[name] is not None else None)
            self._append('ROLLBACK_WRITE_DONE', target=name)
        self._all(self.plan['before'])
        self._guard('ROLLBACK_READBACK')
        self._all(self.plan['before'])
        self._append('CODE_ROLLED_BACK_READBACK')
        return self._terminal('CODE_ROLLED_BACK_READBACK')

    def install(self):
        self._guard('BEFORE_HANDOFF')
        require(not self.transaction.exists() and not self.transaction.is_symlink(),
                'INSTALL_SESSION_ALREADY_USED_ROLLBACK_OR_READBACK_REQUIRED')
        self._all(self.plan['before'])
        # Exclusive directory is the permanent idempotency marker, even on error.
        self.transaction.mkdir(mode=0o700)
        _sync(self.directory)
        self.fd = os.open(self.journal_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            self._append('HANDOFF_ACCEPTED', session=self.plan['session'])
            _exclusive(self.transaction / 'plan.json', canonical(self.plan) + b'\n')
            self._backup()
            self._guard('BEFORE_INSTALL')
            for name in sorted(self.payload):
                if self.plan['before'][name] == self.plan['after'][name]:
                    continue
                self._guard('BEFORE_WRITE:' + name)
                self._append('WRITE_INTENT', target=name, before=self.plan['before'][name], after=self.plan['after'][name])
                self._replace(name, self.payload[name], self.plan['before'][name])
                require(_hash(self.root / name) == self.plan['after'][name], 'WRITE_READBACK_FAILED:' + name)
                self._append('WRITE_DONE', target=name)
            self._all(self.plan['after'])
            self._guard('INSTALL_READBACK')
            self._all(self.plan['after'])
            self._append('CODE_INSTALLED_READBACK')
            return self._terminal('CODE_INSTALLED_READBACK')
        except Exception as error:
            self._append('INSTALL_FAILED', error=type(error).__name__)
            if any(e['event'] == 'WRITE_INTENT' for e in self.events):
                try:
                    self._rollback()
                except Exception as rollback_error:
                    self._append('RECOVERY_REQUIRED', error=type(rollback_error).__name__)
                    raise HandoffError('ROLLBACK_BLOCKED_TASKS_REMAIN_PAUSED') from rollback_error
            raise
        finally:
            os.close(self.fd)
            self.fd = None

    def read_terminal(self):
        """Idempotent current-result readback; never repeats an installation."""
        self._guard('TERMINAL_READBACK')
        _directory(self.transaction)
        require(json.loads(_read(self.transaction / 'plan.json')['data']) == self.plan, 'RECOVERY_PLAN_CHANGED')
        raw = _read(self.journal_path)['data']
        require(raw.endswith(b'\n') and len(raw) <= MAX_JOURNAL, 'JOURNAL_INCOMPLETE')
        events = [json.loads(line) for line in raw.splitlines()]
        require(events and events[-1]['event'] in ('CODE_INSTALLED_READBACK', 'CODE_ROLLED_BACK_READBACK'),
                'NO_CURRENT_TERMINAL_RESULT')
        for index, event in enumerate(events):
            require(event.get('seq') == index and event.get('install_plan_sha256') == self.plan['install_plan_sha256'],
                    'JOURNAL_BINDING')
        status = events[-1]['event']
        result = json.loads(_read(self.transaction / ('terminal-' + status + '.json'))['data'])
        require(result.get('status') == status and result.get('session') == self.plan['session']
                and result.get('install_plan_sha256') == self.plan['install_plan_sha256']
                and result.get('journal_sha256') == sha(raw)
                and result.get('unpause_authorized') is False and result.get('tasks_resumed') is False
                and result.get('candidate_manifest_sha256') == MANIFEST_SHA256
                and result.get('scope') == self.plan['scope'] and result.get('loaded_runtime_verified') is False
                and result.get('overall_gate_b') == 'NOT_EVALUATED' and result.get('crm_html_media_writes') == 0,
                'TERMINAL_RECEIPT_BINDING')
        self._all(self.plan['after'] if status == 'CODE_INSTALLED_READBACK' else self.plan['before'])
        return result

    def rollback_only(self):
        """Crash recovery requires a new live fence AND independent drain proof.

        Existing session intent must be recovered by the upstream route; this
        method never forges a new lease or removes a stale intent itself.
        """
        self._guard('BEFORE_CRASH_RECOVERY')
        _directory(self.transaction)
        require(json.loads(_read(self.transaction / 'plan.json')['data']) == self.plan, 'RECOVERY_PLAN_CHANGED')
        self.fd = os.open(self.journal_path, os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            item = os.fstat(self.fd)
            require(stat.S_ISREG(item.st_mode) and item.st_nlink == 1 and item.st_size <= MAX_JOURNAL, 'JOURNAL_TYPE_OR_SIZE')
            raw = os.read(self.fd, MAX_JOURNAL + 1)
            require(raw.endswith(b'\n') and len(raw) <= MAX_JOURNAL, 'JOURNAL_INCOMPLETE')
            self.events = [json.loads(line) for line in raw.splitlines()]
            for i, event in enumerate(self.events):
                require(event.get('seq') == i and event.get('install_plan_sha256') == self.plan['install_plan_sha256'], 'JOURNAL_BINDING')
            require(self.events and self.events[0]['event'] == 'HANDOFF_ACCEPTED', 'JOURNAL_START')
            require(not any(e['event'] == 'CODE_ROLLED_BACK_READBACK' for e in self.events), 'ALREADY_ROLLED_BACK')
            return self._rollback()
        finally:
            os.close(self.fd)
            self.fd = None
