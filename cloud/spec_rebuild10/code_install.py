"""Exact r2 source admission and paused code/data coordination, revision 1.

No application imports, network, process control, default authority or flock.
Unknown outcomes retain durable intent; recovery never implies permission to run.
"""
from __future__ import annotations
import ast
import contextlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import tarfile
import threading
import time
import uuid

from . import data_install as d
from cloud.writer_coordination_001 import server_fence

SCHEMA = 'UA-ART-SPEC-REBUILD10-CODE-INSTALL-1'
COMBINED_SCHEMA = 'UA-ART-SPEC-REBUILD10-COMBINED-INSTALL-1'
MANIFEST_SHA256 = '2605ca1a08207e94a77747b984930c07947bce8b3ee271a6454d06c9a702de40'
ARCHIVE_SHA256 = '46a20d282cd3114eb49364a4a6b662a09a2074f58ee837c3c1982f46c416933f'
DATA_INSTALLER_SHA256 = '72c7f6a26725bcb2170da2207c753e441eb11baa8f1be2b1be139d3c947e1173'
FENCE_SHA256 = '199a8744b3dd335899adcac92c52e30c462d7b471898d6b94a7ba944b9f05b85'
NEW_DIRECTORY = 'spec_rebuild10'
TERMINALS = ('CODE_LOCAL_INSTALLED', 'CODE_ROLLED_BACK_READBACK')


class CodeInstallError(d.DataInstallError):
    pass


def require(ok, reason):
    if not ok:
        raise CodeInstallError(reason)


def source_hash():
    return d.file_hash(Path(__file__).absolute())


def name_checked(name):
    require(isinstance(name, str) and str(PurePosixPath(name)) == name
            and not name.startswith('/') and '..' not in PurePosixPath(name).parts,
            'TARGET_PATH_INVALID')
    return name


def inspect_package(package_dir):
    """Read a pinned archive into bounded memory; never extract or execute it."""
    package = d.directory(Path(package_dir).absolute())
    manifest_raw = d.read(package / 'runtime-manifest.json')['data']
    manifest = json.loads(manifest_raw)
    value = dict(manifest)
    claimed = value.pop('manifest_sha256', None)
    require(claimed == d.digest(value) == MANIFEST_SHA256, 'EXACT_R2_MANIFEST_REQUIRED')
    require(manifest['file_count'] == len(manifest['files']) == 29
            and manifest['version'] == '20260909-r2', 'EXACT_29_TARGETS_REQUIRED')
    raw = d.read(package / 'runtime-package.tar.gz')['data']
    require(d.sha(raw) == ARCHIVE_SHA256, 'EXACT_R2_ARCHIVE_REQUIRED')
    payload, embedded_manifest = {}, False
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        for member in archive:
            name = name_checked(member.name)
            if name == 'manifest.json':
                require(not embedded_manifest and member.isfile() and member.size == len(manifest_raw), 'ARCHIVE_MANIFEST_SCOPE')
                require(archive.extractfile(member).read(len(manifest_raw) + 1) == manifest_raw, 'ARCHIVE_MANIFEST_CHANGED')
                embedded_manifest = True
                continue
            require(name in manifest['files'] and name not in payload and member.isfile()
                    and not member.issym() and not member.islnk()
                    and 0 <= member.size <= 4 * 1024 * 1024, 'ARCHIVE_MEMBER_SCOPE')
            stream = archive.extractfile(member)
            require(stream is not None, 'ARCHIVE_MEMBER_UNREADABLE')
            body = stream.read(4 * 1024 * 1024 + 1)
            item = manifest['files'][name]
            require(len(body) == item['bytes'] == member.size and d.sha(body) == item['sha256'], 'ARCHIVE_MEMBER_CHANGED')
            if name.endswith('.py'):
                tree = ast.parse(body, filename=name, feature_version=(3, 10))
                compile(tree, name, 'exec')
            else:
                require(name == 'spec_rebuild10/sources.json', 'NON_CODE_MEMBER')
                json.loads(body)
            payload[name] = body
    require(embedded_manifest and set(payload) == set(manifest['files']), 'EXACT_29_TARGETS_REQUIRED')
    require(d.read(package / 'runtime-manifest.json')['data'] == manifest_raw
            and d.file_hash(package / 'runtime-package.tar.gz') == ARCHIVE_SHA256, 'PACKAGE_CHANGED_DURING_READ')
    return manifest, payload


def make_install_plan(session, package_dir, before, *, coordination_plan_sha256, fence_sha256):
    require(fence_sha256 == FENCE_SHA256, 'EXACT_REVIEWED_FENCE_REQUIRED')
    manifest, _ = inspect_package(package_dir)
    require(set(before) == set(manifest['files']), 'EXACT_BEFORE_29_REQUIRED')
    for name, expected in before.items():
        name_checked(name)
        require(expected is None or isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected), 'BEFORE_HASH_REQUIRED')
        if name.startswith(NEW_DIRECTORY + '/') or name == 'spec_rebuild10_bootstrap.py':
            require(expected is None, 'NEW_RUNTIME_MUST_BE_ABSENT')
    for value in (coordination_plan_sha256, fence_sha256):
        require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'BINDING_SHA_REQUIRED')
    value = {'schema': SCHEMA, 'session': {k: session[k] for k in d.SESSION_KEYS},
             'manifest': manifest, 'archive_sha256': ARCHIVE_SHA256, 'before': dict(before),
             'after': {n: item['sha256'] for n, item in manifest['files'].items()},
             'dependencies': manifest['unchanged_execution_dependency_pins'],
             'directories_before': {NEW_DIRECTORY: None}, 'new_file_mode': 0o600, 'new_directory_mode': 0o700,
             'coordination_plan_sha256': coordination_plan_sha256, 'fence_sha256': fence_sha256,
             'installer_sha256': source_hash(), 'data_installer_sha256': DATA_INSTALLER_SHA256}
    return {**value, 'install_plan_sha256': d.digest(value)}


def make_combined_plan(code_plan, data_plan):
    for plan, schema in ((code_plan, SCHEMA), (data_plan, d.SCHEMA)):
        value = dict(plan)
        claimed = value.pop('install_plan_sha256', None)
        require(claimed == d.digest(value) and plan['schema'] == schema, 'CHILD_PLAN_BINDING')
    require(all(code_plan[key] == data_plan[key] for key in ('session', 'coordination_plan_sha256', 'fence_sha256')),
            'ONE_EXACT_SESSION_REQUIRED')
    require(data_plan['installer_sha256'] == DATA_INSTALLER_SHA256, 'EXACT_DATA_INSTALLER_REQUIRED')
    value = {'schema': COMBINED_SCHEMA, 'session': code_plan['session'],
             'coordination_plan_sha256': code_plan['coordination_plan_sha256'],
             'fence_sha256': code_plan['fence_sha256'], 'installer_sha256': source_hash(),
             'code_plan': code_plan, 'data_plan': data_plan,
             'install_order': ['code', 'data'], 'rollback_order': ['data', 'code'],
             'failure_policy': 'REMAIN_PAUSED_EXPLICIT_WHOLE_SET_RECOVERY',
             'manifest': {'manifest_sha256': d.digest({'code': MANIFEST_SHA256, 'data': data_plan['manifest']['manifest_sha256']})}}
    return {**value, 'install_plan_sha256': d.digest(value)}


class CodeInstall:
    def __init__(self, lease, package_dir, plan, *, verify_window):
        require(type(lease) is server_fence.FenceLease, 'REAL_FENCE_LEASE_REQUIRED')
        self.lease, self.package_dir = lease, d.directory(Path(package_dir).absolute())
        self.plan = json.loads(d.canonical(plan))
        require(make_install_plan(lease.session, self.package_dir, plan['before'],
                coordination_plan_sha256=plan['coordination_plan_sha256'], fence_sha256=plan['fence_sha256']) == self.plan,
                'EXACT_PLAN_OR_SESSION_CHANGED')
        self.manifest, self.payload = inspect_package(self.package_dir)
        self.root, self.directory = d.directory(lease.root), d.directory(lease.directory)
        self.transaction = self.directory / 'spec-rebuild10-code-r1'
        self.journal_path = self.transaction / 'journal.jsonl'
        self.thread, self.verifier = threading.get_ident(), verify_window
        self.events, self.proof_digests, self.fd = [], [], None
        parents = {self.root, self.directory}
        for name in self.plan['before']:
            parent = (self.root / name).parent
            if parent != self.root / NEW_DIRECTORY:
                parents.update(p for p in (parent, *parent.parents) if p == self.root or self.root in p.parents)
        self.parent_pins = {str(p): self._identity(d.directory(p)) for p in parents}

    @staticmethod
    def _identity(path):
        value = path.lstat()
        return [value.st_dev, value.st_ino]

    def _check_local(self):
        require(type(self.lease) is server_fence.FenceLease and threading.get_ident() == self.thread
                and self.lease.held and self.lease.pid == os.getpid(), 'SAME_LIVE_HOLDER_REQUIRED')
        require(source_hash() == self.plan['installer_sha256'] and
                d.file_hash(Path(d.__file__).absolute()) == DATA_INSTALLER_SHA256, 'INSTALLER_SOURCE_CHANGED')
        require(d.file_hash(Path(server_fence.__file__).absolute()) == self.plan['fence_sha256']
                == self.lease.session['source_sha256'], 'FENCE_SOURCE_CHANGED')
        require({k: self.lease.session[k] for k in d.SESSION_KEYS} == self.plan['session'], 'HOLDER_SESSION_CHANGED')
        self.lease._check()
        for path, identity in self.parent_pins.items():
            require(self._identity(d.directory(Path(path))) == identity, 'TARGET_PARENT_REPLACED')

    def _guard(self, phase):
        self._check_local()
        require(callable(self.verifier), 'EXTERNAL_WRITER_VERIFICATION_REQUIRED')
        challenge = uuid.uuid4().hex + uuid.uuid4().hex
        result = self.verifier(self.plan, challenge, phase)
        expected = {'status': d.PROOF_STATUS, 'challenge': challenge, 'session': self.plan['session'],
                    'install_plan_sha256': self.plan['install_plan_sha256'],
                    'coordination_plan_sha256': self.plan['coordination_plan_sha256'],
                    'candidate_manifest_sha256': MANIFEST_SHA256}
        self._validate_proof(result, expected)
        self._check_local()
        self._dependencies()
        self.proof_digests.append(d.digest(result))
        return result

    @staticmethod
    def _validate_proof(result, expected):
        require(type(result) is dict and all(result.get(k) == v for k, v in expected.items()), 'EXTERNAL_WRITER_VERIFICATION_REQUIRED')
        now = time.time()
        require(type(result.get('issued_at')) in (float, int) and type(result.get('expires_at')) in (float, int)
                and 0 <= now - result['issued_at'] <= 10 and now < result['expires_at'] <= result['issued_at'] + 30, 'WINDOW_PROOF_STALE')
        for key in ('authorization_receipt_sha256', 'pause_readback_sha256', 'drain_receipt_sha256'):
            require(isinstance(result.get(key), str) and re.fullmatch('[0-9a-f]{64}', result[key]), 'WINDOW_EVIDENCE_HASH_REQUIRED')

    def _dependencies(self):
        for name, expected in self.plan['dependencies'].items():
            require(d.file_hash(self.root / name) == expected, 'SHELL_DEPENDENCY_CHANGED:' + name)

    def _hash(self, name):
        path = self.root / name
        if path.parent == self.root / NEW_DIRECTORY and not path.parent.exists():
            require(not path.parent.is_symlink(), 'NEW_DIRECTORY_SYMLINK')
            return None
        return d.file_hash(path)

    def _all(self, state):
        self._dependencies()
        for name, expected in self.plan[state].items():
            require(self._hash(name) == expected, 'TARGET_IMAGE_CHANGED:' + name)
        self._directory_state(state)

    def _directory_state(self, state=None):
        path = self.root / NEW_DIRECTORY
        created = [e for e in self.events if e['event'] == 'DIRECTORY_CREATED']
        if not path.exists():
            require(not path.is_symlink() and state != 'after', 'NEW_DIRECTORY_MISSING_OR_SYMLINK')
            return
        require(state != 'before' and len(created) == 1, 'UNOWNED_RUNTIME_DIRECTORY')
        require(self._identity(d.directory(path)) == created[0]['identity'], 'RUNTIME_DIRECTORY_REPLACED')
        allowed = {Path(n).name for n in self.plan['after'] if n.startswith(NEW_DIRECTORY + '/')}
        allowed.update(e['temporary'] for e in self.events if e['event'] == 'TEMP_READY'
                       and e['target'].startswith(NEW_DIRECTORY + '/'))
        require(all(p.name in allowed for p in path.iterdir()), 'FOREIGN_RUNTIME_DIRECTORY_ENTRY')

    def _append(self, event, **details):
        require(self.fd is not None, 'JOURNAL_NOT_OPEN')
        opened, current = os.fstat(self.fd), self.journal_path.lstat()
        require(stat.S_ISREG(opened.st_mode) and opened.st_nlink == 1
                and (opened.st_dev, opened.st_ino) == (current.st_dev, current.st_ino)
                and opened.st_size < d.MAX_JOURNAL, 'JOURNAL_REPLACED_OR_FULL')
        entry = {'seq': len(self.events), 'event': event, 'install_plan_sha256': self.plan['install_plan_sha256'], **details}
        raw = d.canonical(entry) + b'\n'
        require(os.write(self.fd, raw) == len(raw), 'JOURNAL_SHORT_WRITE')
        os.fsync(self.fd)
        d.sync(self.transaction)
        self.events.append(entry)

    def _load_events(self):
        require(json.loads(d.read(self.transaction / 'plan.json')['data']) == self.plan, 'RECOVERY_PLAN_CHANGED')
        raw = d.read(self.journal_path)['data']
        require(raw.endswith(b'\n') and len(raw) <= d.MAX_JOURNAL, 'JOURNAL_INCOMPLETE')
        events = [json.loads(line) for line in raw.splitlines()]
        require(events and events[0]['event'] == 'CODE_HANDOFF_ACCEPTED', 'JOURNAL_START')
        for i, event in enumerate(events):
            require(event.get('seq') == i and event.get('install_plan_sha256') == self.plan['install_plan_sha256'], 'JOURNAL_BINDING')
        self.events = events
        return raw

    def _storage(self):
        proof = self._guard('STORAGE_PREFLIGHT')
        quota = proof.get('storage_quota', {})
        require(quota.get('source') == 'AUTHENTICATED_PYTHONANYWHERE_ACCOUNT_QUOTA'
                and type(quota.get('used_bytes')) is int and type(quota.get('quota_bytes')) is int
                and 0 <= quota['used_bytes'] < quota['quota_bytes']
                and type(quota.get('observed_at')) in (float, int) and 0 <= time.time() - quota['observed_at'] <= 30
                and isinstance(quota.get('receipt_sha256'), str) and re.fullmatch('[0-9a-f]{64}', quota['receipt_sha256']), 'AUTHENTICATED_ACCOUNT_QUOTA_REQUIRED')
        ratio = quota['used_bytes'] / quota['quota_bytes']
        require(ratio < .90, 'ACCOUNT_QUOTA_EMERGENCY_STOP_90')
        require(ratio < .80, 'ACCOUNT_QUOTA_HEAVY_DEPLOY_GATE_80')
        needed = sum((self.root / n).stat().st_size for n, v in self.plan['before'].items() if v is not None)
        needed += sum(map(len, self.payload.values())) + max(map(len, self.payload.values())) + 2 * d.MAX_JOURNAL
        fs = os.statvfs(self.root)
        require(quota['quota_bytes'] - quota['used_bytes'] >= needed and fs.f_bavail * fs.f_frsize >= needed, 'STORAGE_CAPACITY_INSUFFICIENT')
        return {'required_bytes': needed, 'warning_70': ratio >= .70, 'quota_receipt_sha256': quota['receipt_sha256']}

    def _backup(self):
        self._all('before')
        backup = self.transaction / 'backup'
        backup.mkdir(mode=0o700)
        d.sync(self.transaction)
        records = {}
        for index, (name, expected) in enumerate(sorted(self.plan['before'].items())):
            item = None if expected is None else d.read(self.root / name)
            require((item['sha256'] if item else self._hash(name)) == expected, 'BACKUP_IMAGE_CHANGED')
            if item:
                filename = f'{index:02d}.bin'
                d.exclusive(backup / filename, item['data'])
                records[name] = {k: v for k, v in item.items() if k != 'data'} | {'backup': filename}
            else:
                records[name] = None
        value = {'install_plan_sha256': self.plan['install_plan_sha256'], 'files': records, 'directories': self.plan['directories_before']}
        d.exclusive(self.transaction / 'backup-manifest.json', d.canonical(value) + b'\n')
        self._all('before')
        self._append('BACKUP_COMPLETE', backup_manifest_sha256=d.digest(value))

    def _create_directory(self):
        path = self.root / NEW_DIRECTORY
        self._guard('BEFORE_DIRECTORY_CREATE')
        require(not path.exists() and not path.is_symlink(), 'NEW_DIRECTORY_MUST_BE_ABSENT')
        self._append('DIRECTORY_CREATE_INTENT', target=NEW_DIRECTORY)
        path.mkdir(mode=self.plan['new_directory_mode'])
        d.sync(self.root)
        self._append('DIRECTORY_CREATED', target=NEW_DIRECTORY, identity=self._identity(path), mode=stat.S_IMODE(path.stat().st_mode))

    def _replace(self, name, data, expected, metadata=None):
        path = self.root / name
        parent = d.directory(path.parent)
        require(self._hash(name) == expected, 'FOREIGN_WRITE_REFUSED:' + name)
        parent_identity = self._identity(parent)
        self._directory_state()
        if data is None:
            require(expected is not None, 'ABSENT_DELETE_FORBIDDEN')
            self._check_local()
            require(self._hash(name) == expected, 'FOREIGN_WRITE_REFUSED:' + name)
            path.unlink()
            d.sync(parent)
            return
        temporary = '.spec-code-' + uuid.uuid4().hex
        temp = parent / temporary
        mode = metadata['mode'] if metadata else (d.read(path)['mode'] if expected else self.plan['new_file_mode'])
        d.exclusive(temp, data, mode)
        if metadata:
            os.utime(temp, ns=(metadata['atime_ns'], metadata['mtime_ns']), follow_symlinks=False)
            fd = os.open(temp, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        self._append('TEMP_READY', target=name, temporary=temporary, identity=self._identity(temp), sha256=d.sha(data))
        self._check_local()
        require(self._identity(parent) == parent_identity and self._hash(name) == expected, 'FOREIGN_WRITE_REFUSED:' + name)
        if expected is None:
            # Exclusive publication without platform-specific renameat2 flags.
            os.link(temp, path, follow_symlinks=False)
            self._append('TEMP_LINKED', target=name, temporary=temporary)
            temp.unlink()
        else:
            os.replace(temp, path)
        d.sync(parent)

    def _staging(self):
        """Read-only proof for interrupted exclusive publication (two links)."""
        found = {}
        for event in self.events:
            if event['event'] != 'TEMP_READY':
                continue
            name, temporary = event['target'], event['temporary']
            require(name in self.plan['before'] and isinstance(temporary, str)
                    and re.fullmatch(r'\.spec-code-[0-9a-f]{32}', temporary)
                    and event['sha256'] in (self.plan['before'][name], self.plan['after'][name]), 'STAGING_SCOPE')
            path = (self.root / name).parent / temporary
            if not path.exists():
                require(not path.is_symlink(), 'STAGING_SYMLINK')
                continue
            d.directory(path.parent)
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                info = os.fstat(fd)
                require(stat.S_ISREG(info.st_mode) and info.st_nlink in (1, 2) and info.st_size <= d.MAX_FILE
                        and [info.st_dev, info.st_ino] == event['identity'], 'STAGING_IDENTITY_CHANGED')
                with os.fdopen(os.dup(fd), 'rb') as stream:
                    raw = stream.read(d.MAX_FILE + 1)
                require(d.sha(raw) == event['sha256'] and self._identity(path) == event['identity'], 'STAGING_BYTES_CHANGED')
                if info.st_nlink == 2:
                    require(self._identity(self.root / name) == event['identity'], 'STAGING_UNKNOWN_LINK')
                    found[name] = event['sha256']
            finally:
                os.close(fd)
        return found

    def preflight_rollback(self):
        """Verify every target, dependency, backup and owned directory; no writes."""
        self._guard('WHOLE_CODE_ROLLBACK_PREFLIGHT')
        self._load_events()
        self._directory_state()
        linked = self._staging()
        backup = json.loads(d.read(self.transaction / 'backup-manifest.json')['data'])
        entries = [e for e in self.events if e['event'] == 'BACKUP_COMPLETE']
        require(len(entries) == 1 and entries[0]['backup_manifest_sha256'] == d.digest(backup)
                and backup['install_plan_sha256'] == self.plan['install_plan_sha256']
                and set(backup['files']) == set(self.plan['before'])
                and backup['directories'] == self.plan['directories_before'], 'BACKUP_BINDING')
        originals = {}
        touched = {e['target'] for e in self.events if e['event'] == 'WRITE_INTENT'}
        require(touched <= set(self.plan['before']), 'JOURNAL_TARGET_SCOPE')
        for name, expected in self.plan['before'].items():
            current = linked[name] if name in linked else self._hash(name)
            allowed = (expected, self.plan['after'][name]) if name in touched else (expected,)
            require(current in allowed, 'FOREIGN_WRITE_REFUSED:' + name)
            item = backup['files'][name]
            if item is None:
                original = None
            else:
                require(re.fullmatch(r'[0-9]{2}\.bin', item['backup']), 'BACKUP_PATH_SCOPE')
                original = d.read(self.transaction / 'backup' / item['backup'])['data']
                require(type(item['mode']) is int and 0 <= item['mode'] <= 0o7777, 'BACKUP_MODE')
            require((d.sha(original) if original is not None else None) == expected, 'BACKUP_BYTES_CHANGED')
            originals[name] = original
        return backup, originals

    def _clean_staging(self):
        self._staging()
        for event in self.events[:]:
            if event['event'] != 'TEMP_READY':
                continue
            path = (self.root / event['target']).parent / event['temporary']
            if not path.exists():
                continue
            self._guard('BEFORE_STAGING_CLEANUP')
            require(self._identity(path) == event['identity'], 'STAGING_IDENTITY_CHANGED')
            self._append('STAGING_CLEANUP_INTENT', target=event['target'], temporary=event['temporary'])
            path.unlink()
            d.sync(path.parent)

    def apply(self):
        self._guard('BEFORE_CODE_HANDOFF')
        require(not self.transaction.exists() and not self.transaction.is_symlink(), 'SESSION_ALREADY_USED_RECOVERY_REQUIRED')
        self._all('before')
        require(inspect_package(self.package_dir)[1] == self.payload, 'CANDIDATE_CHANGED')
        storage = self._storage()
        self.transaction.mkdir(mode=0o700)
        d.sync(self.directory)
        self.fd = os.open(self.journal_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            d.exclusive(self.transaction / 'plan.json', d.canonical(self.plan) + b'\n')
            self._append('CODE_HANDOFF_ACCEPTED', storage=storage)
            self._backup()
            self._create_directory()
            for name, raw in sorted(self.payload.items()):
                if self.plan['before'][name] == self.plan['after'][name]:
                    continue
                self._guard('BEFORE_WRITE:' + name)
                self._append('WRITE_INTENT', target=name)
                self._replace(name, raw, self.plan['before'][name])
                require(self._hash(name) == self.plan['after'][name], 'WRITE_READBACK_FAILED')
                self._append('WRITE_DONE', target=name)
            self._guard('CODE_INSTALL_READBACK')
            self._all('after')
            self._append('CODE_LOCAL_INSTALLED')
            return self._terminal('CODE_LOCAL_INSTALLED')
        except Exception as error:
            self._append('RECOVERY_REQUIRED', error=type(error).__name__)
            raise CodeInstallError('CODE_OUTCOME_REQUIRES_DURABLE_RECOVERY_TASKS_REMAIN_PAUSED') from error
        finally:
            os.close(self.fd)
            self.fd = None

    def rollback_only(self):
        backup, originals = self.preflight_rollback()
        if self.events[-1]['event'] == 'CODE_ROLLED_BACK_READBACK':
            return self.finalize_terminal()
        self.fd = os.open(self.journal_path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            self._clean_staging()
            self._append('ROLLBACK_STARTED')
            for name in sorted(originals, reverse=True):
                current = self._hash(name)
                if current == self.plan['before'][name]:
                    continue
                self._guard('BEFORE_ROLLBACK_WRITE:' + name)
                self._append('ROLLBACK_WRITE_INTENT', target=name)
                self._replace(name, originals[name], self.plan['after'][name], backup['files'][name])
                self._append('ROLLBACK_WRITE_DONE', target=name)
            path = self.root / NEW_DIRECTORY
            if path.exists():
                self._guard('BEFORE_DIRECTORY_REMOVE')
                self._directory_state()
                require(not list(path.iterdir()), 'RUNTIME_DIRECTORY_NOT_EMPTY')
                self._append('DIRECTORY_REMOVE_INTENT', target=NEW_DIRECTORY, identity=self._identity(path))
                path.rmdir()
                d.sync(self.root)
                self._append('DIRECTORY_REMOVED', target=NEW_DIRECTORY)
            self._guard('CODE_ROLLBACK_READBACK')
            self._all('before')
            self._append('CODE_ROLLED_BACK_READBACK')
            return self._terminal('CODE_ROLLED_BACK_READBACK')
        finally:
            os.close(self.fd)
            self.fd = None

    def _terminal(self, status):
        value = {'schema': SCHEMA, 'status': status, 'session': self.plan['session'],
                 'install_plan_sha256': self.plan['install_plan_sha256'], 'journal_sha256': d.file_hash(self.journal_path),
                 'candidate_manifest_sha256': MANIFEST_SHA256, 'archive_sha256': ARCHIVE_SHA256,
                 'proof_digests': list(self.proof_digests), 'application_imported': False, 'tasks_resumed': False,
                 'unpause_authorized': False, 'runtime_loaded_verified': False, 'overall_gate_b': 'NOT_EVALUATED'}
        d.exclusive(self.transaction / ('terminal-' + status + '.json'), d.canonical(value) + b'\n')
        return value

    def finalize_terminal(self):
        self._guard('TERMINAL_FINALIZATION')
        self._load_events()
        state = self.events[-1]['event']
        require(state in TERMINALS, 'NO_DURABLE_TERMINAL_EVENT')
        self._all('after' if state == TERMINALS[0] else 'before')
        if not (self.transaction / ('terminal-' + state + '.json')).exists():
            self._terminal(state)
        return self.read_terminal()

    def read_terminal(self):
        self._guard('TERMINAL_READBACK')
        raw = self._load_events()
        state = self.events[-1]['event']
        require(state in TERMINALS, 'NO_TERMINAL_RESULT_RECOVER_REQUIRED')
        value = json.loads(d.read(self.transaction / ('terminal-' + state + '.json'))['data'])
        require(value.get('status') == state and value.get('session') == self.plan['session']
                and value.get('install_plan_sha256') == self.plan['install_plan_sha256']
                and value.get('candidate_manifest_sha256') == MANIFEST_SHA256 and value.get('archive_sha256') == ARCHIVE_SHA256
                and value.get('journal_sha256') == d.sha(raw)
                and all(value.get(k) is False for k in ('application_imported', 'tasks_resumed', 'unpause_authorized', 'runtime_loaded_verified'))
                and value.get('overall_gate_b') == 'NOT_EVALUATED', 'TERMINAL_RECEIPT_BINDING')
        self._all('after' if state == TERMINALS[0] else 'before')
        return value


class CombinedInstall:
    """One durable coordinator; mixed phases are always paused, never runnable."""
    def __init__(self, lease, package_dir, payload_dir, plan, *, verify_window):
        self.plan = json.loads(d.canonical(plan))
        require(make_combined_plan(plan['code_plan'], plan['data_plan']) == self.plan, 'EXACT_COMBINED_PLAN_REQUIRED')
        self.verifier, self.lease = verify_window, lease
        self.transaction = d.directory(lease.directory) / 'spec-rebuild10-combined-r1'
        self.journal_path = self.transaction / 'journal.jsonl'
        self.events, self.fd, self.proof_digests = [], None, []
        self.code = CodeInstall(lease, package_dir, plan['code_plan'], verify_window=self._child_proof)
        class CoordinatedData(d.DataInstall):
            # Data.apply's automatic compensation must not precede the combined
            # domain preflight. Explicit recovery is the only compensation route.
            def _rollback(inner):
                require(self.recovering, 'COMBINED_WHOLE_SET_RECOVERY_REQUIRED')
                return super()._rollback()
        self.recovering = False
        self.data = CoordinatedData(lease, payload_dir, plan['data_plan'], verify_window=self._child_proof)

    def _guard(self, phase):
        self.code._check_local()
        self.code._dependencies()
        self.data._check_local()
        require(callable(self.verifier), 'EXTERNAL_WRITER_VERIFICATION_REQUIRED')
        challenge = uuid.uuid4().hex + uuid.uuid4().hex
        result = self.verifier(self.plan, challenge, phase)
        expected = {'status': d.PROOF_STATUS, 'challenge': challenge, 'session': self.plan['session'],
                    'install_plan_sha256': self.plan['install_plan_sha256'],
                    'coordination_plan_sha256': self.plan['coordination_plan_sha256'],
                    'candidate_manifest_sha256': self.plan['manifest']['manifest_sha256']}
        CodeInstall._validate_proof(result, expected)
        self.code._check_local()
        self.code._dependencies()
        self.data._check_local()
        self.proof_digests.append(d.digest(result))
        return result

    def _child_proof(self, plan, challenge, phase):
        child = 'code' if plan == self.plan['code_plan'] else 'data' if plan == self.plan['data_plan'] else None
        require(child is not None, 'UNKNOWN_CHILD_PLAN')
        proof = self._guard(child.upper() + ':' + phase)
        # Translate only a validated combined challenge to its exact bound child.
        # The callback always sees the entire combined plan and explicit phase.
        return {**proof, 'challenge': challenge, 'install_plan_sha256': plan['install_plan_sha256'],
                'candidate_manifest_sha256': plan['manifest']['manifest_sha256'],
                'combined_install_plan_sha256': self.plan['install_plan_sha256']}

    _append = CodeInstall._append

    def _load_events(self):
        require(json.loads(d.read(self.transaction / 'plan.json')['data']) == self.plan, 'RECOVERY_PLAN_CHANGED')
        raw = d.read(self.journal_path)['data']
        require(raw.endswith(b'\n') and len(raw) <= d.MAX_JOURNAL, 'JOURNAL_INCOMPLETE')
        self.events = [json.loads(line) for line in raw.splitlines()]
        require(self.events and self.events[0]['event'] == 'COMBINED_ACCEPTED', 'JOURNAL_START')
        for i, event in enumerate(self.events):
            require(event.get('seq') == i and event.get('install_plan_sha256') == self.plan['install_plan_sha256'], 'JOURNAL_BINDING')
        return raw

    def apply(self):
        self._guard('BEFORE_COMBINED_HANDOFF')
        require(not self.transaction.exists() and not self.transaction.is_symlink()
                and not self.code.transaction.exists() and not self.data.transaction.exists(), 'COMBINED_SESSION_ALREADY_USED')
        self.code._all('before')
        self.code._storage()
        self.data._preflight()
        self.transaction.mkdir(mode=0o700)
        d.sync(self.transaction.parent)
        self.fd = os.open(self.journal_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            d.exclusive(self.transaction / 'plan.json', d.canonical(self.plan) + b'\n')
            self._append('COMBINED_ACCEPTED')
            self._append('CODE_APPLY_INTENT')
            self.code.apply()
            self._append('CODE_LOCAL_COMPLETE')
            self._guard('BEFORE_DATA_APPLY')
            self.code.read_terminal()
            self._append('DATA_APPLY_INTENT')
            self.data.apply()
            self._append('DATA_LOCAL_COMPLETE')
            self._verify_state('after')
            self._append('COMBINED_LOCAL_INSTALLED')
            return self._terminal('COMBINED_LOCAL_INSTALLED')
        except Exception as error:
            self._append('RECOVERY_REQUIRED', error=type(error).__name__)
            raise CodeInstallError('COMBINED_OUTCOME_REQUIRES_DURABLE_RECOVERY_TASKS_REMAIN_PAUSED') from error
        finally:
            os.close(self.fd)
            self.fd = None

    def _data_rollback_preflight(self):
        data = self.data
        data._guard('WHOLE_DATA_ROLLBACK_PREFLIGHT')
        data._protected()
        d.stable_db(data.root / 'crm.db')
        with d.db_read(data.root / 'crm.db') as conn:
            rows = d.digest(d.crm_rows(conn))
            crm = data.manifest['crm']
            require(rows in (crm['rows_before_sha256'], crm['rows_after_sha256']), 'FOREIGN_CRM_WRITE_REFUSED')
            data._crm(conn, 'before' if rows == crm['rows_before_sha256'] else 'after')
        if not data.transaction.exists():
            data._files('before')
            require(rows == crm['rows_before_sha256'], 'DATA_CHANGED_WITHOUT_JOURNAL')
            return False
        data._load_events()
        mutations = any(e['event'] in ('YEAR_UPDATE_INTENT', 'WRITE_INTENT') for e in data.events)
        backup_path = data.transaction / 'backup-manifest.json'
        entries = [e for e in data.events if e['event'] == 'BACKUP_COMPLETE']
        if not entries:
            require(not mutations, 'DATA_BACKUP_REQUIRED')
            data._files('before')
            require(rows == crm['rows_before_sha256'], 'DATA_CHANGED_WITHOUT_BACKUP')
            return False
        backup = json.loads(d.read(backup_path)['data'])
        require(len(entries) == 1 and entries[0]['backup_manifest_sha256'] == d.digest(backup)
                and backup['install_plan_sha256'] == data.plan['install_plan_sha256']
                and set(backup['files']) == set(data.manifest['files']), 'DATA_BACKUP_BINDING')
        require(d.file_hash(data.transaction / 'backup' / 'crm.db') == backup['crm_backup_sha256'], 'CRM_BACKUP_CHANGED')
        touched = {e['target'] for e in data.events if e['event'] == 'WRITE_INTENT'}
        require(touched <= set(data.manifest['files']), 'DATA_JOURNAL_TARGET_SCOPE')
        for name, item in data.manifest['files'].items():
            allowed = (item['before_sha256'], item['after_sha256']) if name in touched else (item['before_sha256'],)
            require(d.file_hash(data.root / name) in allowed, 'FOREIGN_WRITE_REFUSED:' + name)
            saved = backup['files'][name]
            if saved is not None:
                require(re.fullmatch(r'[0-9]{2}\.bin', saved['backup']), 'DATA_BACKUP_PATH_SCOPE')
            original = None if saved is None else d.read(data.transaction / 'backup' / saved['backup'])['data']
            require((d.sha(original) if original is not None else None) == item['before_sha256'], 'DATA_BACKUP_BYTES_CHANGED')
        return True

    def preflight_rollback(self):
        self._guard('WHOLE_COMBINED_ROLLBACK_PREFLIGHT')
        self._load_events()
        code_started = self.code.transaction.exists()
        if code_started:
            self.code._load_events()
            backups = any(e['event'] == 'BACKUP_COMPLETE' for e in self.code.events)
            if backups:
                self.code.preflight_rollback()
            else:
                require(not any(e['event'] in ('WRITE_INTENT', 'DIRECTORY_CREATE_INTENT') for e in self.code.events), 'CODE_BACKUP_REQUIRED')
                self.code._all('before')
                code_started = False
        else:
            self.code._all('before')
        data_started = self._data_rollback_preflight()
        return code_started, data_started

    def rollback_only(self):
        code_started, data_started = self.preflight_rollback()
        if self.events[-1]['event'] == 'COMBINED_ROLLED_BACK_READBACK':
            return self.finalize_terminal()
        self.fd = os.open(self.journal_path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            self._append('COMBINED_ROLLBACK_STARTED')
            self.recovering = True
            if data_started:
                self._append('DATA_ROLLBACK_INTENT')
                self.data.rollback_only()
            # Never roll code back until the entire data domain is proven before.
            self._verify_data_before()
            self._append('DATA_BEFORE_VERIFIED')
            if code_started:
                self._append('CODE_ROLLBACK_INTENT')
                self.code.rollback_only()
            self._verify_state('before')
            self._append('COMBINED_ROLLED_BACK_READBACK')
            return self._terminal('COMBINED_ROLLED_BACK_READBACK')
        finally:
            self.recovering = False
            os.close(self.fd)
            self.fd = None

    def _verify_data_before(self):
        self.data._guard('COMBINED_DATA_BEFORE_READBACK')
        self.data._files('before')
        self.data._protected()
        d.stable_db(self.data.root / 'crm.db')
        with d.db_read(self.data.root / 'crm.db') as conn:
            self.data._crm(conn, 'before')

    def _verify_state(self, state):
        self._guard('COMBINED_' + state.upper() + '_READBACK')
        if self.code.transaction.exists():
            self.code._load_events()
        self.code._all(state)
        self.data._files(state)
        self.data._protected()
        d.stable_db(self.data.root / 'crm.db')
        with d.db_read(self.data.root / 'crm.db') as conn:
            self.data._crm(conn, state)

    def _terminal(self, status):
        value = {'schema': COMBINED_SCHEMA, 'status': status, 'session': self.plan['session'],
                 'install_plan_sha256': self.plan['install_plan_sha256'], 'journal_sha256': d.file_hash(self.journal_path),
                 'code_plan_sha256': self.code.plan['install_plan_sha256'], 'data_plan_sha256': self.data.plan['install_plan_sha256'],
                 'code_journal_sha256': d.file_hash(self.code.journal_path) if self.code.journal_path.exists() else None,
                 'data_journal_sha256': d.file_hash(self.data.journal_path) if self.data.journal_path.exists() else None,
                 'proof_digests': list(self.proof_digests), 'tasks_resumed': False, 'unpause_authorized': False,
                 'runtime_loaded_verified': False, 'overall_gate_b': 'NOT_EVALUATED',
                 'new_card_publication': 'OWNER_MANUAL_ONLY_17_THEN_18'}
        d.exclusive(self.transaction / ('terminal-' + status + '.json'), d.canonical(value) + b'\n')
        return value

    def finalize_terminal(self):
        self._guard('COMBINED_TERMINAL_FINALIZATION')
        self._load_events()
        status = self.events[-1]['event']
        require(status in ('COMBINED_LOCAL_INSTALLED', 'COMBINED_ROLLED_BACK_READBACK'), 'NO_DURABLE_TERMINAL_EVENT')
        self._verify_state('after' if status == 'COMBINED_LOCAL_INSTALLED' else 'before')
        if not (self.transaction / ('terminal-' + status + '.json')).exists():
            self._terminal(status)
        return self.read_terminal()

    def read_terminal(self):
        self._guard('COMBINED_TERMINAL_READBACK')
        raw = self._load_events()
        status = self.events[-1]['event']
        require(status in ('COMBINED_LOCAL_INSTALLED', 'COMBINED_ROLLED_BACK_READBACK'), 'NO_TERMINAL_RESULT_RECOVER_REQUIRED')
        value = json.loads(d.read(self.transaction / ('terminal-' + status + '.json'))['data'])
        require(value.get('status') == status and value.get('session') == self.plan['session']
                and value.get('install_plan_sha256') == self.plan['install_plan_sha256']
                and value.get('code_plan_sha256') == self.code.plan['install_plan_sha256']
                and value.get('data_plan_sha256') == self.data.plan['install_plan_sha256']
                and value.get('journal_sha256') == d.sha(raw)
                and value.get('code_journal_sha256') == (d.file_hash(self.code.journal_path) if self.code.journal_path.exists() else None)
                and value.get('data_journal_sha256') == (d.file_hash(self.data.journal_path) if self.data.journal_path.exists() else None)
                and all(value.get(k) is False for k in ('tasks_resumed', 'unpause_authorized', 'runtime_loaded_verified'))
                and value.get('overall_gate_b') == 'NOT_EVALUATED', 'COMBINED_RECEIPT_BINDING')
        self._verify_state('after' if status == 'COMBINED_LOCAL_INSTALLED' else 'before')
        return value
