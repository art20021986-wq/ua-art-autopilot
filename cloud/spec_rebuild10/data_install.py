"""Narrow durable 16-card data handoff under a borrowed, verified FenceLease.

No process control, network, default verifier, application import or lock-file
reopen. Public acceptance and starting workers are outside this transaction.
"""
from __future__ import annotations
import contextlib
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
import time
import uuid

SCHEMA = 'UA-ART-SPEC-REBUILD10-DATA-INSTALL-1'
PROOF_STATUS = 'AUTHENTICATED_PAUSE_AND_PRIOR_WRITER_DRAIN_VERIFIED'
UIDS = [f'UA-{n:04d}' for n in range(1, 17)]
DRAFTS = ['UA-0017', 'UA-0018']
PAGES = [f'{folder}/{uid}.html' for folder in ('video', 'site') for uid in UIDS]
DRAFT_PAGES = [f'{folder}/{uid}.html' for folder in ('video', 'site') for uid in DRAFTS]
SPEC_FIELDS = {
    'additional_specification': 'car_uid,field_key,field_value,normalized_value,source,source_url,confidence,is_price_field',
    'additional_specification_meta': 'car_uid,field_key,label_ru,category,unit,evidence_count,source_domains_json,source_urls_json,verification_status,model_match_score,is_manual,is_visible',
}
MAX_FILE = 32 * 1024 * 1024
MAX_JOURNAL = 1024 * 1024
SESSION_KEYS = ('repository', 'account', 'production_root', 'task_id', 'expected_main', 'plan_sha256', 'run_id', 'run_attempt', 'nonce', 'epoch')


class DataInstallError(RuntimeError):
    pass


def require(ok, reason):
    if not ok:
        raise DataInstallError(reason)


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(value):
    return sha(canonical(value))


def directory(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path, 'DIRECTORY_PATH')
    for item in (path, *path.parents):
        require(stat.S_ISDIR(item.lstat().st_mode), 'DIRECTORY_TYPE')
    return path


def read(path, absent=False):
    path = Path(path)
    directory(path.parent)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        if absent:
            return None
        raise
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= MAX_FILE, 'FILE_TYPE_SIZE_LINKS')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            data = stream.read(MAX_FILE + 1)
        key = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(len(data) <= MAX_FILE and key(before) == key(os.fstat(fd)) == key(path.lstat()), 'FILE_CHANGED_DURING_READ')
        return {'data': data, 'sha256': sha(data), 'mode': stat.S_IMODE(before.st_mode), 'atime_ns': before.st_atime_ns, 'mtime_ns': before.st_mtime_ns}
    finally:
        os.close(fd)


def file_hash(path):
    item = read(path, absent=True)
    return item['sha256'] if item is not None else None


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def exclusive(path, data, mode=0o600):
    directory(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        os.fchmod(stream.fileno(), mode)
        stream.flush()
        os.fsync(stream.fileno())
    sync(path.parent)


@contextlib.contextmanager
def db_read(path):
    read(path)
    with contextlib.closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=0)) as conn:
        conn.execute('PRAGMA query_only=ON')
        yield conn


def json_rows(conn, sql):
    cursor = conn.execute(sql)
    names = [x[0] for x in cursor.description]
    return [{k: {'bytes_hex': v.hex()} if isinstance(v, bytes) else v for k, v in zip(names, row)} for row in cursor]


def crm_rows(conn):
    return json_rows(conn, 'SELECT * FROM cars ORDER BY auto_number')


def schema_hash(conn):
    return digest(conn.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall())


def spec_snapshot(path):
    before = file_hash(path)
    with db_read(path) as conn:
        records = {table: conn.execute('SELECT ' + fields + ' FROM ' + table + ' ORDER BY car_uid,field_key').fetchall() for table, fields in SPEC_FIELDS.items()}
    require(file_hash(path) == before, 'LEGACY_SPEC_CHANGED_DURING_READ')
    require(len(records['additional_specification']) == len(records['additional_specification_meta']) == 557, 'LEGACY_FACT_SCOPE_557_REQUIRED')
    return {'path': 'vin_specs_task111_v3.db', 'file_sha256': before, 'semantic_sha256': digest(records), 'count': 557}


def no_sidecars(path):
    for suffix in ('-wal', '-shm', '-journal'):
        require(file_hash(Path(str(path) + suffix)) is None, 'DATABASE_SIDECAR_PRESENT:' + path.name + suffix)


def stable_db(path):
    read(path)
    no_sidecars(path)


def make_manifest(snapshot_root, payload_dir):
    """Read-only exact candidate preparation; this does not grant installation."""
    root, payload = directory(Path(snapshot_root).absolute()), directory(Path(payload_dir).absolute())
    stable_db(root / 'crm.db')
    stable_db(root / 'vin_specs_task111_v3.db')
    stable_db(payload / 'spec-rebuild.db')
    with db_read(root / 'crm.db') as conn:
        rows, schema = crm_rows(conn), schema_hash(conn)
        require(not conn.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name='cars'").fetchall(), 'CARS_TRIGGER_FORBIDDEN')
    require([r['auto_number'] for r in rows] == UIDS + DRAFTS, 'EXACT_18_CRM_ROWS_REQUIRED')
    require([r['auto_number'] for r in rows if r['published'] == 1] == UIDS, 'EXACT_16_PUBLISHED_REQUIRED')
    old = next(r for r in rows if r['auto_number'] == 'UA-0016')
    require(str(old['year']) == '1999' and old['vin'].endswith('1028'), 'EXACT_OWNER_YEAR_PRECONDITION_REQUIRED')
    new = dict(old, year='2017' if isinstance(old['year'], str) else 2017)
    after = [new if r['auto_number'] == 'UA-0016' else r for r in rows]
    files = {}
    for name in PAGES:
        before, candidate = read(root / name), read(payload / 'candidate' / name)
        files[name] = {'before_sha256': before['sha256'], 'after_sha256': candidate['sha256'], 'mode': before['mode'], 'payload': 'candidate/' + name}
    require(file_hash(root / 'spec-rebuild.db') is None, 'NEW_STORE_MUST_NOT_EXIST')
    no_sidecars(root / 'spec-rebuild.db')
    with db_read(payload / 'spec-rebuild.db') as conn:
        require(conn.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'CANDIDATE_STORE_INTEGRITY')
        require(conn.execute('SELECT COUNT(*) FROM facts').fetchone()[0] == 557, 'CANDIDATE_FACT_SCOPE_557_REQUIRED')
        vehicles = conn.execute('SELECT uid,published,tombstoned FROM vehicles ORDER BY uid').fetchall()
        require(vehicles == [(uid, 1, 0) for uid in UIDS] + [(uid, 0, 0) for uid in DRAFTS], 'CANDIDATE_VEHICLE_SCOPE')
    files['spec-rebuild.db'] = {'before_sha256': None, 'after_sha256': file_hash(payload / 'spec-rebuild.db'), 'mode': 0o600, 'payload': 'spec-rebuild.db'}
    value = {'schema': SCHEMA, 'scope': '32_HTML_NEW_STORE_ONE_YEAR_CELL_NO_PUBLICATION_NO_UNPAUSE', 'files': files,
             'crm': {'path': 'crm.db', 'schema_sha256': schema, 'rows_before_sha256': digest(rows), 'rows_after_sha256': digest(after),
                     'before_row': old, 'after_row': new, 'draft_rows_sha256': digest(rows[-2:])},
             'legacy_spec': spec_snapshot(root / 'vin_specs_task111_v3.db'),
             'draft_files': {name: file_hash(root / name) for name in DRAFT_PAGES}}
    return {**value, 'manifest_sha256': digest(value)}


def validate_manifest(manifest):
    value = dict(manifest)
    claimed = value.pop('manifest_sha256', None)
    require(claimed == digest(value) and value.get('schema') == SCHEMA, 'MANIFEST_HASH_SCHEMA')
    require(value.get('scope') == '32_HTML_NEW_STORE_ONE_YEAR_CELL_NO_PUBLICATION_NO_UNPAUSE', 'MANIFEST_OPERATION_SCOPE')
    require(set(value['files']) == set(PAGES) | {'spec-rebuild.db'}, 'MANIFEST_TARGET_SCOPE')
    require(set(value['draft_files']) == set(DRAFT_PAGES), 'MANIFEST_DRAFT_SCOPE')
    for name, item in value['files'].items():
        require(item['payload'] == ('spec-rebuild.db' if name == 'spec-rebuild.db' else 'candidate/' + name), 'MANIFEST_PAYLOAD_PATH')
        require(re.fullmatch('[0-9a-f]{64}', item['after_sha256']), 'MANIFEST_HASH')
        require(item['before_sha256'] is None if name == 'spec-rebuild.db' else bool(re.fullmatch('[0-9a-f]{64}', item['before_sha256'])), 'MANIFEST_BEFORE_HASH')
        require(type(item['mode']) is int and 0 <= item['mode'] <= 0o777, 'MANIFEST_MODE')
    crm = value['crm']
    before, after = crm['before_row'], crm['after_row']
    require(before['auto_number'] == 'UA-0016' and before['published'] == 1 and str(before['year']) == '1999'
            and before['vin'].endswith('1028') and str(after['year']) == '2017'
            and {k: v for k, v in before.items() if k != 'year'} == {k: v for k, v in after.items() if k != 'year'}, 'ONE_OWNER_YEAR_CELL_REQUIRED')
    require(crm['path'] == 'crm.db' and value['legacy_spec']['path'] == 'vin_specs_task111_v3.db'
            and value['legacy_spec']['count'] == 557, 'DATABASE_SCOPE')
    return manifest


def make_install_plan(session, payload_dir, manifest, *, coordination_plan_sha256, fence_sha256):
    validate_manifest(manifest)
    require(re.fullmatch('[0-9a-f]{64}', coordination_plan_sha256 or '') and re.fullmatch('[0-9a-f]{64}', fence_sha256 or ''), 'BINDING_SHA_REQUIRED')
    payload = directory(Path(payload_dir).absolute())
    for name, item in manifest['files'].items():
        require(file_hash(payload / item['payload']) == item['after_sha256'], 'CANDIDATE_CHANGED:' + name)
    value = {'schema': SCHEMA, 'session': {k: session[k] for k in SESSION_KEYS}, 'manifest': manifest,
             'coordination_plan_sha256': coordination_plan_sha256, 'fence_sha256': fence_sha256,
             'installer_sha256': sha(Path(__file__).read_bytes())}
    return {**value, 'install_plan_sha256': digest(value)}


class DataInstall:
    def __init__(self, lease, payload_dir, plan, *, verify_window):
        self.lease, self.payload_dir = lease, directory(Path(payload_dir).absolute())
        self.plan = json.loads(canonical(plan))
        self.manifest = validate_manifest(self.plan['manifest'])
        self.root, self.directory = directory(lease.root), directory(lease.directory)
        self.transaction = self.directory / 'spec-rebuild10-data'
        self.journal_path = self.transaction / 'journal.jsonl'
        self.thread, self.verifier = threading.get_ident(), verify_window
        self.events, self.proof_digests, self.fd = [], [], None
        self.parent_pins = {str(p): (p.stat().st_dev, p.stat().st_ino) for p in (self.root, self.root / 'site', self.root / 'video', self.directory)}
        require(make_install_plan(lease.session, self.payload_dir, self.manifest,
                coordination_plan_sha256=plan['coordination_plan_sha256'], fence_sha256=plan['fence_sha256']) == self.plan,
                'EXACT_PLAN_OR_SESSION_CHANGED')
        self.payload = {name: read(self.payload_dir / item['payload'])['data'] for name, item in self.manifest['files'].items()}
        require(all(sha(raw) == self.manifest['files'][name]['after_sha256'] for name, raw in self.payload.items()), 'CACHED_CANDIDATE_CHANGED')
        self.database_inodes = {name: ((self.root / name).stat().st_dev, (self.root / name).stat().st_ino) for name in ('crm.db', 'vin_specs_task111_v3.db')}

    def _check_local(self):
        require(threading.get_ident() == self.thread and self.lease.pid == os.getpid() and self.lease.held, 'SAME_LIVE_HOLDER_REQUIRED')
        require(type(self.lease).__name__ == 'FenceLease', 'REAL_FENCE_LEASE_REQUIRED')
        fence_path = Path(inspect.getfile(type(self.lease))).absolute()
        require(file_hash(fence_path) == self.plan['fence_sha256'] and self.lease.session['source_sha256'] == self.plan['fence_sha256'], 'FENCE_SOURCE_CHANGED')
        require(file_hash(Path(__file__).absolute()) == self.plan['installer_sha256'], 'INSTALLER_SOURCE_CHANGED')
        require({k: self.lease.session[k] for k in SESSION_KEYS} == self.plan['session'], 'HOLDER_SESSION_CHANGED')
        self.lease._check()
        for name, expected in self.database_inodes.items():
            current = (self.root / name).lstat()
            require(stat.S_ISREG(current.st_mode) and current.st_nlink == 1 and (current.st_dev, current.st_ino) == expected, 'DATABASE_INODE_CHANGED')
        for name, expected in self.parent_pins.items():
            path = directory(Path(name))
            require((path.stat().st_dev, path.stat().st_ino) == expected, 'TARGET_PARENT_REPLACED')

    def _guard(self, phase):
        self._check_local()
        require(callable(self.verifier), 'EXTERNAL_WRITER_VERIFICATION_REQUIRED')
        challenge = uuid.uuid4().hex + uuid.uuid4().hex
        result = self.verifier(self.plan, challenge, phase)
        expected = {'status': PROOF_STATUS, 'challenge': challenge, 'session': self.plan['session'],
                    'install_plan_sha256': self.plan['install_plan_sha256'], 'coordination_plan_sha256': self.plan['coordination_plan_sha256'],
                    'candidate_manifest_sha256': self.manifest['manifest_sha256']}
        require(type(result) is dict and all(result.get(k) == v for k, v in expected.items()), 'EXTERNAL_WRITER_VERIFICATION_REQUIRED')
        now = time.time()
        require(type(result.get('issued_at')) in (float, int) and type(result.get('expires_at')) in (float, int)
                and 0 <= now - result['issued_at'] <= 10 and now < result['expires_at'] <= result['issued_at'] + 30, 'WINDOW_PROOF_STALE')
        for key in ('authorization_receipt_sha256', 'pause_readback_sha256', 'drain_receipt_sha256'):
            require(isinstance(result.get(key), str) and re.fullmatch('[0-9a-f]{64}', result[key]), 'WINDOW_EVIDENCE_HASH_REQUIRED')
        self._check_local()
        self.proof_digests.append(digest(result))
        return result

    def _append(self, event, **details):
        require(self.fd is not None, 'JOURNAL_NOT_OPEN')
        opened, current = os.fstat(self.fd), self.journal_path.lstat()
        require((opened.st_dev, opened.st_ino) == (current.st_dev, current.st_ino) and opened.st_size < MAX_JOURNAL, 'JOURNAL_REPLACED_OR_FULL')
        entry = {'seq': len(self.events), 'event': event, 'install_plan_sha256': self.plan['install_plan_sha256'], **details}
        raw = canonical(entry) + b'\n'
        require(os.write(self.fd, raw) == len(raw), 'JOURNAL_SHORT_WRITE')
        os.fsync(self.fd)
        sync(self.transaction)
        self.events.append(entry)

    def _protected(self):
        no_sidecars(self.root / 'spec-rebuild.db')
        for name, expected in self.manifest['draft_files'].items():
            require(file_hash(self.root / name) == expected, 'DRAFT_PAGE_CHANGED:' + name)
        require(spec_snapshot(self.root / 'vin_specs_task111_v3.db') == self.manifest['legacy_spec'], 'LEGACY_SPEC_CHANGED')
        stable_db(self.root / 'vin_specs_task111_v3.db')

    def _crm(self, conn, state):
        rows = crm_rows(conn)
        require(schema_hash(conn) == self.manifest['crm']['schema_sha256'], 'CRM_SCHEMA_CHANGED')
        require(digest(rows) == self.manifest['crm']['rows_' + state + '_sha256'], 'CRM_FULL_ROWS_CHANGED')
        require(digest(rows[-2:]) == self.manifest['crm']['draft_rows_sha256'], 'DRAFT_ROWS_CHANGED')

    def _files(self, state):
        for name, item in self.manifest['files'].items():
            require(file_hash(self.root / name) == item[state + '_sha256'], 'TARGET_IMAGE_CHANGED:' + name)

    def _preflight(self):
        self._files('before')
        self._protected()
        stable_db(self.root / 'crm.db')
        stable_db(self.payload_dir / 'spec-rebuild.db')
        with db_read(self.root / 'crm.db') as conn:
            self._crm(conn, 'before')
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
        original_bytes = sum((self.root / name).stat().st_size for name, item in self.manifest['files'].items() if item['before_sha256'] is not None)
        candidate_bytes = sum(len(v) for v in self.payload.values())
        needed = original_bytes + candidate_bytes + max(len(v) for v in self.payload.values()) + 3 * (self.root / 'crm.db').stat().st_size + 2 * MAX_JOURNAL
        fs = os.statvfs(self.root)
        require(quota['quota_bytes'] - quota['used_bytes'] >= needed and fs.f_bavail * fs.f_frsize >= needed, 'STORAGE_CAPACITY_INSUFFICIENT')
        return {'required_bytes': needed, 'warning_70': ratio >= .70, 'quota_receipt_sha256': quota['receipt_sha256']}

    def _backup(self):
        self._guard('BEFORE_BACKUP')
        backup_dir = self.transaction / 'backup'
        backup_dir.mkdir(mode=0o700)
        sync(self.transaction)
        records = {}
        for index, (name, item) in enumerate(sorted(self.manifest['files'].items())):
            current = read(self.root / name, absent=True)
            require((current['sha256'] if current else None) == item['before_sha256'], 'BACKUP_IMAGE_CHANGED')
            if current:
                backup_name = f'{index:02d}.bin'
                exclusive(backup_dir / backup_name, current['data'])
                records[name] = {k: v for k, v in current.items() if k != 'data'} | {'backup': backup_name}
            else:
                records[name] = None
        # SQLite backup is for durable diagnosis/recovery evidence. Rollback never
        # restores this entire DB over foreign changes: only our exact year cell.
        backup_path = backup_dir / 'crm.db'
        exclusive(backup_path, b'')
        with db_read(self.root / 'crm.db') as source, contextlib.closing(sqlite3.connect(str(backup_path), timeout=0)) as target:
            self._crm(source, 'before')
            source.backup(target)
            target.commit()
            self._crm(target, 'before')
        fd = os.open(backup_path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        sync(backup_dir)
        value = {'install_plan_sha256': self.plan['install_plan_sha256'], 'files': records, 'crm_backup_sha256': file_hash(backup_path)}
        exclusive(self.transaction / 'backup-manifest.json', canonical(value) + b'\n')
        self._append('BACKUP_COMPLETE', backup_manifest_sha256=digest(value))

    def _replace(self, name, data, expected, metadata=None):
        no_sidecars(self.root / 'spec-rebuild.db')
        path = self.root / name
        require(file_hash(path) == expected, 'FOREIGN_WRITE_REFUSED:' + name)
        if data is None:
            if expected is not None:
                path.unlink()
                sync(path.parent)
            return
        temp = path.parent / ('.spec-data-' + uuid.uuid4().hex)
        mode = metadata['mode'] if metadata else self.manifest['files'][name]['mode']
        try:
            exclusive(temp, data, mode)
            if metadata:
                os.utime(temp, ns=(metadata['atime_ns'], metadata['mtime_ns']), follow_symlinks=False)
                fd = os.open(temp, os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            require(file_hash(path) == expected, 'FOREIGN_WRITE_REFUSED:' + name)
            os.replace(temp, path)
            sync(path.parent)
        finally:
            if temp.exists():
                temp.unlink()
                sync(temp.parent)

    def _write_year(self, conn, reverse=False):
        old = self.manifest['crm']['after_row' if reverse else 'before_row']
        new = self.manifest['crm']['before_row' if reverse else 'after_row']
        def authorizer(action, arg1, arg2, database, trigger):
            if action == sqlite3.SQLITE_UPDATE:
                return sqlite3.SQLITE_OK if (arg1, arg2, database, trigger) == ('cars', 'year', 'main', None) else sqlite3.SQLITE_DENY
            if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_DELETE, sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        # Keep the restrictive callback until this short-lived connection closes.
        # Disabling it with None is only supported from CPython 3.11; on the
        # production Python 3.10 it poisons subsequent readback/rollback calls.
        # Reads and transaction control remain allowed, every other DML write
        # stays denied for the rest of the connection's lifetime.
        conn.set_authorizer(authorizer)
        result = conn.execute('UPDATE cars SET year=? WHERE id=? AND auto_number=? AND vin=? AND published=1 AND year=?',
                              (new['year'], old['id'], old['auto_number'], old['vin'], old['year']))
        require(result.rowcount == 1, 'YEAR_UPDATE_NOT_EXACTLY_ONE')

    def _terminal(self, state):
        value = {'schema': SCHEMA, 'status': state, 'install_plan_sha256': self.plan['install_plan_sha256'],
                 'candidate_manifest_sha256': self.manifest['manifest_sha256'], 'session': self.plan['session'],
                 'journal_sha256': file_hash(self.journal_path), 'proof_digests': list(self.proof_digests),
                 'scope': self.manifest['scope'], 'tasks_resumed': False, 'unpause_authorized': False,
                 'runtime_loaded_verified': False, 'overall_gate_b': 'NOT_EVALUATED', 'new_card_publication': 'OWNER_MANUAL_ONLY_17_THEN_18',
                 'crm_rows_sha256': self.manifest['crm']['rows_' + ('after' if state == 'DATA_LOCAL_COMMITTED' else 'before') + '_sha256'],
                 'legacy_spec_semantic_sha256': self.manifest['legacy_spec']['semantic_sha256']}
        path = self.transaction / ('terminal-' + state + '.json')
        if path.exists():
            require(json.loads(read(path)['data']) == value, 'TERMINAL_ALREADY_EXISTS_CHANGED')
        else:
            exclusive(path, canonical(value) + b'\n')
        return value

    def apply(self):
        self._guard('BEFORE_DATA_HANDOFF')
        require(not self.transaction.exists() and not self.transaction.is_symlink(), 'SESSION_ALREADY_USED_RECOVERY_REQUIRED')
        storage = self._preflight()
        self.transaction.mkdir(mode=0o700)
        sync(self.directory)
        self.fd = os.open(self.journal_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        conn = None
        try:
            exclusive(self.transaction / 'plan.json', canonical(self.plan) + b'\n')
            self._append('DATA_HANDOFF_ACCEPTED', storage=storage)
            self._backup()
            self._guard('BEFORE_CRM_TRANSACTION')
            stable_db(self.root / 'crm.db')
            conn = sqlite3.connect((self.root / 'crm.db').as_uri() + '?mode=rw', uri=True, timeout=0, isolation_level=None)
            conn.execute('BEGIN IMMEDIATE')
            self._crm(conn, 'before')
            self._protected()
            self._guard('BEFORE_YEAR_UPDATE')
            self._append('YEAR_UPDATE_INTENT')
            self._write_year(conn)
            self._crm(conn, 'after')
            for name, item in sorted(self.manifest['files'].items()):
                self._guard('BEFORE_WRITE:' + name)
                self._append('WRITE_INTENT', target=name, before=item['before_sha256'], after=item['after_sha256'])
                self._replace(name, self.payload[name], item['before_sha256'])
                require(file_hash(self.root / name) == item['after_sha256'], 'FILE_READBACK_FAILED')
                self._append('WRITE_DONE', target=name)
            self._files('after')
            self._protected()
            self._crm(conn, 'after')
            self._guard('BEFORE_SQL_COMMIT')
            self._append('BEFORE_SQL_COMMIT')
            conn.commit()  # Last live write: files have all been fsynced/read back.
            self._append('SQL_COMMITTED')
            conn.close()
            conn = None
            self._guard('COMMITTED_READBACK')
            self._files('after')
            self._protected()
            with db_read(self.root / 'crm.db') as check:
                self._crm(check, 'after')
            self._append('DATA_LOCAL_COMMITTED')
            return self._terminal('DATA_LOCAL_COMMITTED')
        except Exception as error:
            if conn is not None:
                conn.rollback()
                conn.close()
                conn = None
            self._append('INSTALL_FAILED', error=type(error).__name__)
            if any(e['event'] in ('YEAR_UPDATE_INTENT', 'WRITE_INTENT') for e in self.events):
                try:
                    self._rollback()
                except Exception as recovery:
                    self._append('RECOVERY_REQUIRED', error=type(recovery).__name__)
                    raise DataInstallError('ROLLBACK_BLOCKED_TASKS_REMAIN_PAUSED') from recovery
            raise
        finally:
            if conn is not None:
                conn.close()  # Process-death simulation rolls back uncommitted SQL.
            os.close(self.fd)
            self.fd = None

    def _load_events(self):
        require(json.loads(read(self.transaction / 'plan.json')['data']) == self.plan, 'RECOVERY_PLAN_CHANGED')
        raw = read(self.journal_path)['data']
        require(raw.endswith(b'\n') and len(raw) <= MAX_JOURNAL, 'JOURNAL_INCOMPLETE')
        events = [json.loads(line) for line in raw.splitlines()]
        require(events and events[0]['event'] == 'DATA_HANDOFF_ACCEPTED', 'JOURNAL_START')
        for index, event in enumerate(events):
            require(event.get('seq') == index and event.get('install_plan_sha256') == self.plan['install_plan_sha256'], 'JOURNAL_BINDING')
        self.events = events
        return raw

    def _rollback(self):
        self._guard('BEFORE_ROLLBACK')
        backup = json.loads(read(self.transaction / 'backup-manifest.json')['data'])
        entries = [e for e in self.events if e['event'] == 'BACKUP_COMPLETE']
        require(len(entries) == 1 and entries[0]['backup_manifest_sha256'] == digest(backup)
                and backup['install_plan_sha256'] == self.plan['install_plan_sha256'], 'BACKUP_BINDING')
        originals = {}
        for name, item in self.manifest['files'].items():
            current = file_hash(self.root / name)
            require(current in (item['before_sha256'], item['after_sha256']), 'FOREIGN_WRITE_REFUSED:' + name)
            saved = backup['files'][name]
            originals[name] = None if saved is None else read(self.transaction / 'backup' / saved['backup'])['data']
            require((sha(originals[name]) if originals[name] is not None else None) == item['before_sha256'], 'BACKUP_BYTES_CHANGED')
        self._protected()
        conn = sqlite3.connect((self.root / 'crm.db').as_uri() + '?mode=rw', uri=True, timeout=0, isolation_level=None)
        try:
            conn.execute('BEGIN IMMEDIATE')
            current_rows = digest(crm_rows(conn))
            require(current_rows in (self.manifest['crm']['rows_before_sha256'], self.manifest['crm']['rows_after_sha256']), 'FOREIGN_CRM_WRITE_REFUSED')
            state = 'before' if current_rows == self.manifest['crm']['rows_before_sha256'] else 'after'
            self._crm(conn, state)
            if state == 'after':
                self._guard('BEFORE_YEAR_ROLLBACK')
                self._append('YEAR_ROLLBACK_INTENT')
                self._write_year(conn, reverse=True)
                self._crm(conn, 'before')
            for name in sorted(originals, reverse=True):
                item = self.manifest['files'][name]
                self._guard('BEFORE_ROLLBACK_WRITE:' + name)
                current = file_hash(self.root / name)
                require(current in (item['before_sha256'], item['after_sha256']), 'FOREIGN_WRITE_REFUSED:' + name)
                if current == item['before_sha256']:
                    continue
                self._append('ROLLBACK_WRITE_INTENT', target=name)
                self._replace(name, originals[name], item['after_sha256'], backup['files'][name])
                self._append('ROLLBACK_WRITE_DONE', target=name)
            self._files('before')
            self._protected()
            self._crm(conn, 'before')
            self._guard('BEFORE_ROLLBACK_SQL_COMMIT')
            self._append('BEFORE_ROLLBACK_SQL_COMMIT')
            conn.commit()
        finally:
            conn.close()
        self._guard('ROLLBACK_READBACK')
        self._files('before')
        self._protected()
        with db_read(self.root / 'crm.db') as check:
            self._crm(check, 'before')
        self._append('DATA_ROLLED_BACK_READBACK')
        return self._terminal('DATA_ROLLED_BACK_READBACK')

    def rollback_only(self):
        self._guard('BEFORE_CRASH_RECOVERY')
        directory(self.transaction)
        self._load_events()
        if self.events[-1]['event'] == 'DATA_ROLLED_BACK_READBACK':
            return self.finalize_terminal()
        self.fd = os.open(self.journal_path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            return self._rollback()
        finally:
            os.close(self.fd)
            self.fd = None

    def finalize_terminal(self):
        """Finish only a missing receipt after authenticated terminal readback.

        A torn journal is never silently truncated or interpreted as success.
        This method writes no application data and never repeats installation.
        """
        self._guard('TERMINAL_FINALIZATION')
        self._load_events()
        state = self.events[-1]['event']
        require(state in ('DATA_LOCAL_COMMITTED', 'DATA_ROLLED_BACK_READBACK'), 'NO_DURABLE_TERMINAL_EVENT')
        desired = 'after' if state == 'DATA_LOCAL_COMMITTED' else 'before'
        self._files(desired)
        self._protected()
        with db_read(self.root / 'crm.db') as conn:
            self._crm(conn, desired)
        if not (self.transaction / ('terminal-' + state + '.json')).exists():
            self._terminal(state)
        return self.read_terminal()

    def read_terminal(self):
        self._guard('TERMINAL_READBACK')
        raw = self._load_events()
        state = self.events[-1]['event']
        require(state in ('DATA_LOCAL_COMMITTED', 'DATA_ROLLED_BACK_READBACK'), 'NO_TERMINAL_RESULT_RECOVER_REQUIRED')
        result = json.loads(read(self.transaction / ('terminal-' + state + '.json'))['data'])
        require(result.get('status') == state and result.get('install_plan_sha256') == self.plan['install_plan_sha256']
                and result.get('session') == self.plan['session'] and result.get('journal_sha256') == sha(raw)
                and result.get('tasks_resumed') is False and result.get('unpause_authorized') is False
                and result.get('runtime_loaded_verified') is False and result.get('overall_gate_b') == 'NOT_EVALUATED', 'TERMINAL_RECEIPT_BINDING')
        desired = 'after' if state == 'DATA_LOCAL_COMMITTED' else 'before'
        self._files(desired)
        self._protected()
        with db_read(self.root / 'crm.db') as conn:
            self._crm(conn, desired)
        return result
